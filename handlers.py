import logging
import re
from datetime import date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import database as db
import gamification as gami
import scheduler as sched
from config import ACHIEVEMENTS, SLOT_LABELS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------

def build_checklist_keyboard(tasks: list, completed_ids: set) -> InlineKeyboardMarkup:
    buttons = []
    for task in tasks:
        done = task["id"] in completed_ids
        label = f"{'✅' if done else '⬜'} {task['name']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"toggle_task:{task['id']}")])
    buttons.append([InlineKeyboardButton("📊 My Stats", callback_data="show_stats")])
    return InlineKeyboardMarkup(buttons)


def build_remove_keyboard(tasks: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"🗑️ {task['name']}", callback_data=f"remove_task:{task['id']}")]
        for task in tasks
    ]
    return InlineKeyboardMarkup(buttons)


def build_schedule_keyboard(times_row) -> InlineKeyboardMarkup:
    slots = [
        ("morning_time", "🌅 Morning"),
        ("midday_time", "☀️ Midday"),
        ("evening_time", "🌙 Evening"),
    ]
    buttons = []
    for slot_key, label in slots:
        current = times_row[slot_key]
        buttons.append([
            InlineKeyboardButton(
                f"{label}: {current}",
                callback_data=f"schedule_set:{slot_key}",
            )
        ])
    tz = times_row["timezone"]
    buttons.append([InlineKeyboardButton(f"🌍 Timezone: {tz}", callback_data="schedule_set:timezone")])
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _checklist_header(tasks: list, completed_ids: set) -> str:
    done = len([t for t in tasks if t["id"] in completed_ids])
    total = len(tasks)
    pct = int((done / total) * 100) if total > 0 else 0
    bar = _progress_bar(done, total)
    return f"📋 *Today's Tasks* — {done}/{total} done {bar}"


def _progress_bar(done: int, total: int, length: int = 8) -> str:
    if total == 0:
        return ""
    filled = int((done / total) * length)
    return "[" + "█" * filled + "░" * (length - filled) + "]"


def _achievement_message(keys: list[str]) -> str:
    lines = ["🏆 *Achievement Unlocked!*"]
    for key in keys:
        info = ACHIEVEMENTS.get(key, {})
        lines.append(f"{info.get('icon', '🎖️')} *{info.get('name', key)}* — {info.get('description', '')}")
    return "\n".join(lines)


def _level_up_message(new_level: int) -> str:
    title = gami.get_level_title(new_level)
    return f"🎉 *Level Up!*\nYou reached {title}!"


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)
    db.ensure_user_stats(user.id)
    db.ensure_scheduled_times(user.id)
    sched.register_user_jobs(context.application, user.id, user.id)

    name = user.first_name or "there"
    await update.message.reply_text(
        f"👋 Hey {name}! Welcome to your *Daily To-Do Bot*!\n\n"
        f"I'll keep you accountable with daily check-ins and help you build streaks. "
        f"Here's what you can do:\n\n"
        f"• `/addtask <name>` — Add a daily repeating task\n"
        f"• `/checkin` — View & tick off today's tasks\n"
        f"• `/stats` — See your XP, level, and streak\n"
        f"• `/listtasks` — View all your tasks\n"
        f"• `/removetask` — Remove a task\n"
        f"• `/schedule` — Change your reminder times\n\n"
        f"I'll message you at *8:00 AM*, *12:00 PM*, and *8:00 PM* (UTC) by default.\n"
        f"Start by adding your first task! 🚀",
        parse_mode="Markdown",
    )


async def add_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "Usage: `/addtask <task name>`\nExample: `/addtask Morning run`",
            parse_mode="Markdown",
        )
        return

    name = " ".join(context.args).strip()
    if len(name) > 100:
        await update.message.reply_text("Task name too long (max 100 characters).")
        return

    task_id = db.add_task(user.id, name)
    total = db.get_total_task_count(user.id)

    # Check Task Collector achievement
    if total >= 10:
        if db.unlock_achievement(user.id, "task_collector"):
            info = ACHIEVEMENTS["task_collector"]
            await update.message.reply_text(
                f"🏆 *Achievement Unlocked!*\n{info['icon']} *{info['name']}* — {info['description']}",
                parse_mode="Markdown",
            )

    await update.message.reply_text(
        f"✅ Added: *{name}*\nUse /checkin to see your updated list.",
        parse_mode="Markdown",
    )


async def remove_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tasks = db.get_active_tasks(user.id)
    if not tasks:
        await update.message.reply_text("You have no active tasks. Add one with /addtask!")
        return

    keyboard = build_remove_keyboard(tasks)
    await update.message.reply_text(
        "Tap a task to remove it:",
        reply_markup=keyboard,
    )


async def list_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tasks = db.get_active_tasks(user.id)
    if not tasks:
        await update.message.reply_text("No active tasks. Add one with /addtask!")
        return

    lines = ["📋 *Your Daily Tasks:*"]
    for i, task in enumerate(tasks, 1):
        lines.append(f"{i}. {task['emoji']} {task['name']}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def checkin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tasks = db.get_active_tasks(user.id)
    if not tasks:
        await update.message.reply_text(
            "You have no tasks yet! Add some with `/addtask <name>`.",
            parse_mode="Markdown",
        )
        return

    today = date.today().isoformat()
    completed_ids = set(db.get_today_completions(user.id, today))
    header = _checklist_header(tasks, completed_ids)
    keyboard = build_checklist_keyboard(tasks, completed_ids)

    await update.message.reply_text(header, reply_markup=keyboard, parse_mode="Markdown")


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_user_stats(user.id)
    msg = gami.format_stats_message(user.id)
    await update.message.reply_text(msg, parse_mode="Markdown")


async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_scheduled_times(user.id)

    # /schedule morning 09:30  — direct update
    if len(context.args) == 2:
        slot_name, time_str = context.args
        slot_map = {"morning": "morning_time", "midday": "midday_time", "evening": "evening_time"}
        slot_key = slot_map.get(slot_name.lower())
        if not slot_key:
            await update.message.reply_text(
                "Usage: `/schedule [morning|midday|evening] HH:MM`",
                parse_mode="Markdown",
            )
            return
        if not re.match(r"^\d{2}:\d{2}$", time_str):
            await update.message.reply_text("Time must be in HH:MM format (e.g. 09:30).")
            return
        db.update_scheduled_time(user.id, slot_key, time_str)
        sched.register_user_jobs(context.application, user.id, user.id)
        label = SLOT_LABELS.get(slot_key, slot_name)
        await update.message.reply_text(
            f"{label} reminder updated to *{time_str}*.",
            parse_mode="Markdown",
        )
        return

    # No args — show current schedule with inline buttons
    times_row = db.get_scheduled_times(user.id)
    keyboard = build_schedule_keyboard(times_row)
    await update.message.reply_text(
        "⏰ *Your Reminder Schedule*\n\nTap a slot to change it, or use:\n"
        "`/schedule morning HH:MM`\n`/schedule midday HH:MM`\n`/schedule evening HH:MM`",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Callback query handlers
# ---------------------------------------------------------------------------

async def toggle_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # Must be called first within 10s

    user = update.effective_user
    task_id = int(query.data.split(":")[1])
    today = date.today().isoformat()

    is_now_complete = db.toggle_task_completion(task_id, user.id, today)
    result = gami.process_task_toggle(user.id, task_id, today, is_now_complete)

    tasks = db.get_active_tasks(user.id)
    completed_ids = set(db.get_today_completions(user.id, today))
    keyboard = build_checklist_keyboard(tasks, completed_ids)
    header = _checklist_header(tasks, completed_ids)

    try:
        await query.edit_message_text(
            text=header,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except BadRequest:
        # Message too old or unchanged — send fresh
        await context.bot.send_message(
            chat_id=user.id,
            text=header,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    # XP feedback toast already shown via query.answer() — send bonus notifications
    if is_now_complete and result["bonus_earned"]:
        done, total = db.get_completion_fraction(user.id, today)
        await context.bot.send_message(
            chat_id=user.id,
            text=f"🎊 *All tasks done!* +{result['xp_earned']} XP (includes +50 bonus!)\n"
                 f"Streak: 🔥 {db.get_user_stats(user.id)['current_streak']} day(s)",
            parse_mode="Markdown",
        )

    if result["new_achievements"]:
        await context.bot.send_message(
            chat_id=user.id,
            text=_achievement_message(result["new_achievements"]),
            parse_mode="Markdown",
        )

    if result["leveled_up"]:
        await context.bot.send_message(
            chat_id=user.id,
            text=_level_up_message(result["new_level"]),
            parse_mode="Markdown",
        )


async def remove_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    task_id = int(query.data.split(":")[1])
    db.deactivate_task(task_id, user.id)

    remaining = db.get_active_tasks(user.id)
    if not remaining:
        try:
            await query.edit_message_text("All tasks removed. Add new ones with /addtask!")
        except BadRequest:
            pass
    else:
        keyboard = build_remove_keyboard(remaining)
        try:
            await query.edit_message_reply_markup(reply_markup=keyboard)
        except BadRequest:
            pass


async def schedule_change_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    slot_key = query.data.split(":")[1]

    if slot_key == "timezone":
        await query.answer()
        await query.edit_message_text(
            "To change your timezone, use:\n`/schedule tz <Timezone>`\n\n"
            "Examples: `Europe/London`, `America/New_York`, `Asia/Tokyo`\n\n"
            "Find your timezone at: worldtimeserver.com",
            parse_mode="Markdown",
        )
        return

    label = SLOT_LABELS.get(slot_key, slot_key)
    await query.answer(f"Use /schedule {slot_key.replace('_time','')} HH:MM to update", show_alert=True)


async def show_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    db.ensure_user_stats(user.id)
    msg = gami.format_stats_message(user.id)
    await context.bot.send_message(chat_id=user.id, text=msg, parse_mode="Markdown")
