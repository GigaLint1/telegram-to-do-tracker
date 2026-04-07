import logging
import re
from datetime import date
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import database as db
import gamification as gami
import scheduler as sched
from config import ACHIEVEMENTS, SLOT_LABELS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------------------------

def parse_duration(s: str) -> Optional[int]:
    """
    Parse duration strings into minutes.
    Supports: '2h', '30m', '1h30m', '1h 30m', '90m', '2h30', '120' (bare int = minutes).
    Returns None if unparseable.
    """
    s = s.strip().lower()
    # e.g. '1h30m', '1h 30m', '1h30'
    m = re.fullmatch(r'(\d+)\s*h\s*(\d+)\s*m?', s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # e.g. '2h'
    m = re.fullmatch(r'(\d+)\s*h', s)
    if m:
        return int(m.group(1)) * 60
    # e.g. '30m'
    m = re.fullmatch(r'(\d+)\s*m', s)
    if m:
        return int(m.group(1))
    # bare number = minutes
    m = re.fullmatch(r'(\d+)', s)
    if m:
        return int(m.group(1))
    return None


def fmt_duration(seconds: int) -> str:
    """Format seconds into a human-readable string: '1h 23m', '45m', '3h'."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0 and mins > 0:
        return f"{hours}h {mins}m"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{mins}m"


def fmt_minutes(minutes: int) -> str:
    """Format a duration target in minutes: '2h', '30m', '1h 30m'."""
    return fmt_duration(minutes * 60)


# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------

def build_checklist_keyboard(
    tasks: list,
    completed_ids: set,
    session_totals: Optional[dict] = None,
) -> InlineKeyboardMarkup:
    buttons = []
    for task in tasks:
        done = task["id"] in completed_ids
        check = "✅" if done else "⬜"
        label = f"{check} {task['name']}"

        # Append time progress if task has a duration target
        if session_totals is not None and task["duration_minutes"]:
            spent_secs = session_totals.get(task["id"], 0)
            target_secs = task["duration_minutes"] * 60
            spent_str = fmt_duration(spent_secs)
            target_str = fmt_minutes(task["duration_minutes"])
            hit = "✓" if spent_secs >= target_secs else ""
            label += f"  [{spent_str} / {target_str}{' ' + hit if hit else ''}]"

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


def build_starttask_keyboard(tasks: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"▶️ {task['name']}", callback_data=f"start_task:{task['id']}")]
        for task in tasks
    ]
    return InlineKeyboardMarkup(buttons)


def build_edittask_keyboard(tasks: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"✏️ {task['name']}", callback_data=f"edit_task:{task['id']}")]
        for task in tasks
    ]
    return InlineKeyboardMarkup(buttons)


def build_editfield_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit name", callback_data=f"edit_name:{task_id}")],
        [InlineKeyboardButton("⏱️ Edit duration", callback_data=f"edit_duration:{task_id}")],
    ])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _checklist_header(tasks: list, completed_ids: set) -> str:
    done = len([t for t in tasks if t["id"] in completed_ids])
    total = len(tasks)
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


def _get_checklist(user_id: int):
    today = date.today().isoformat()
    tasks = db.get_active_tasks(user_id)
    completed_ids = set(db.get_today_completions(user_id, today))
    session_totals = db.get_today_session_totals(user_id, today)
    header = _checklist_header(tasks, completed_ids)
    keyboard = build_checklist_keyboard(tasks, completed_ids, session_totals)
    return header, keyboard


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
        f"• `/addtask <name> [duration]` — Add a task (e.g. `/addtask Study 2h`)\n"
        f"• `/checkin` — View & tick off today's tasks\n"
        f"• `/starttask` — Start a timer on a task\n"
        f"• `/endtask` — Stop the running timer\n"
        f"• `/edittask` — Edit a task's name or duration\n"
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
            "Usage: `/addtask <name> [duration]`\n"
            "Examples:\n"
            "  `/addtask Morning run`\n"
            "  `/addtask Study 2h`\n"
            "  `/addtask Meditate 20m`",
            parse_mode="Markdown",
        )
        return

    args = context.args
    duration_minutes = None

    # Try to parse last token as a duration
    if len(args) >= 2:
        parsed = parse_duration(args[-1])
        if parsed is not None:
            duration_minutes = parsed
            args = args[:-1]

    name = " ".join(args).strip()
    if len(name) > 100:
        await update.message.reply_text("Task name too long (max 100 characters).")
        return

    db.add_task(user.id, name, duration_minutes=duration_minutes)
    total = db.get_total_task_count(user.id)

    if total >= 10:
        if db.unlock_achievement(user.id, "task_collector"):
            info = ACHIEVEMENTS["task_collector"]
            await update.message.reply_text(
                f"🏆 *Achievement Unlocked!*\n{info['icon']} *{info['name']}* — {info['description']}",
                parse_mode="Markdown",
            )

    duration_str = f" _(target: {fmt_minutes(duration_minutes)})_" if duration_minutes else ""
    await update.message.reply_text(
        f"✅ Added: *{name}*{duration_str}\nUse /checkin to see your updated list.",
        parse_mode="Markdown",
    )


async def remove_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tasks = db.get_active_tasks(user.id)
    if not tasks:
        await update.message.reply_text("You have no active tasks. Add one with /addtask!")
        return

    keyboard = build_remove_keyboard(tasks)
    await update.message.reply_text("Tap a task to remove it:", reply_markup=keyboard)


async def list_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tasks = db.get_active_tasks(user.id)
    if not tasks:
        await update.message.reply_text("No active tasks. Add one with /addtask!")
        return

    lines = ["📋 *Your Daily Tasks:*"]
    for i, task in enumerate(tasks, 1):
        duration_str = f" _{fmt_minutes(task['duration_minutes'])} target_" if task["duration_minutes"] else ""
        lines.append(f"{i}. {task['emoji']} {task['name']}{duration_str}")

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

    header, keyboard = _get_checklist(user.id)
    await update.message.reply_text(header, reply_markup=keyboard, parse_mode="Markdown")


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_user_stats(user.id)
    msg = gami.format_stats_message(user.id)
    await update.message.reply_text(msg, parse_mode="Markdown")


async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_scheduled_times(user.id)

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

    times_row = db.get_scheduled_times(user.id)
    keyboard = build_schedule_keyboard(times_row)
    await update.message.reply_text(
        "⏰ *Your Reminder Schedule*\n\nTap a slot to change it, or use:\n"
        "`/schedule morning HH:MM`\n`/schedule midday HH:MM`\n`/schedule evening HH:MM`",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def starttask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    # Block if a session is already running
    active = db.get_active_session(user.id)
    if active:
        await update.message.reply_text(
            f"⏱️ You already have a timer running on *{active['task_name']}*.\n"
            f"Send /endtask to stop it first.",
            parse_mode="Markdown",
        )
        return

    tasks = db.get_active_tasks(user.id)
    if not tasks:
        await update.message.reply_text("No tasks yet. Add one with /addtask!")
        return

    keyboard = build_starttask_keyboard(tasks)
    await update.message.reply_text(
        "⏱️ *Which task are you starting?*",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def endtask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    active = db.get_active_session(user.id)

    if not active:
        await update.message.reply_text(
            "No active timer. Start one with /starttask."
        )
        return

    elapsed = db.end_session(active["id"])
    task_name = active["task_name"]
    duration_minutes = active["duration_minutes"]

    lines = [
        f"⏹️ *{task_name}* — session ended",
        f"⏱️ Time: *{fmt_duration(elapsed)}*",
    ]

    if duration_minutes:
        target_secs = duration_minutes * 60
        pct = int((elapsed / target_secs) * 100) if target_secs > 0 else 0
        lines.append(f"🎯 Target: {fmt_minutes(duration_minutes)} ({pct}% complete)")

    if elapsed >= 1800:  # 30+ minutes — give encouragement
        lines.append("🔥 Great focus session!")
    elif elapsed >= 600:  # 10+ minutes
        lines.append("👍 Nice work!")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def edittask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tasks = db.get_active_tasks(user.id)
    if not tasks:
        await update.message.reply_text("No active tasks to edit.")
        return

    keyboard = build_edittask_keyboard(tasks)
    await update.message.reply_text(
        "✏️ *Which task do you want to edit?*",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Callback query handlers
# ---------------------------------------------------------------------------

async def toggle_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    task_id = int(query.data.split(":")[1])
    today = date.today().isoformat()

    is_now_complete = db.toggle_task_completion(task_id, user.id, today)
    result = gami.process_task_toggle(user.id, task_id, today, is_now_complete)

    header, keyboard = _get_checklist(user.id)

    try:
        await query.edit_message_text(text=header, reply_markup=keyboard, parse_mode="Markdown")
    except BadRequest:
        await context.bot.send_message(
            chat_id=user.id, text=header, reply_markup=keyboard, parse_mode="Markdown"
        )

    if is_now_complete and result["bonus_earned"]:
        stats = db.get_user_stats(user.id)
        await context.bot.send_message(
            chat_id=user.id,
            text=f"🎊 *All tasks done!* +{result['xp_earned']} XP (includes +50 bonus!)\n"
                 f"Streak: 🔥 {stats['current_streak']} day(s)",
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

    await query.answer(f"Use /schedule {slot_key.replace('_time', '')} HH:MM to update", show_alert=True)


async def show_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    db.ensure_user_stats(user.id)
    msg = gami.format_stats_message(user.id)
    await context.bot.send_message(chat_id=user.id, text=msg, parse_mode="Markdown")


async def start_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    task_id = int(query.data.split(":")[1])

    # Check again in case another session started between showing keyboard and tapping
    active = db.get_active_session(user.id)
    if active:
        try:
            await query.edit_message_text(
                f"⏱️ You already have a timer running on *{active['task_name']}*.\n"
                f"Send /endtask to stop it first.",
                parse_mode="Markdown",
            )
        except BadRequest:
            pass
        return

    task = db.get_task(task_id, user.id)
    if not task:
        await query.answer("Task not found.", show_alert=True)
        return

    today = date.today().isoformat()
    db.start_session(user.id, task_id, today)

    duration_hint = f"\n🎯 Target: {fmt_minutes(task['duration_minutes'])}" if task["duration_minutes"] else ""

    try:
        await query.edit_message_text(
            f"⏱️ *Timer started for {task['name']}!*{duration_hint}\n\n"
            f"Send /endtask when you're done.",
            parse_mode="Markdown",
        )
    except BadRequest:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"⏱️ *Timer started for {task['name']}!*{duration_hint}\n\nSend /endtask when you're done.",
            parse_mode="Markdown",
        )


async def edit_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show name/duration choice buttons for the selected task."""
    query = update.callback_query
    await query.answer()

    task_id = int(query.data.split(":")[1])
    user = update.effective_user
    task = db.get_task(task_id, user.id)
    if not task:
        await query.answer("Task not found.", show_alert=True)
        return

    duration_info = f" _(target: {fmt_minutes(task['duration_minutes'])})_" if task["duration_minutes"] else " _(no target)_"
    keyboard = build_editfield_keyboard(task_id)

    try:
        await query.edit_message_text(
            f"Editing: *{task['name']}*{duration_info}\n\nWhat would you like to change?",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except BadRequest:
        pass


async def edit_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set pending edit state and prompt the user to type the new value."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    field = parts[0]   # 'edit_name' or 'edit_duration'
    task_id = int(parts[1])

    user = update.effective_user
    task = db.get_task(task_id, user.id)
    if not task:
        await query.answer("Task not found.", show_alert=True)
        return

    context.user_data["pending_edit"] = {
        "task_id": task_id,
        "field": "name" if field == "edit_name" else "duration",
    }

    if field == "edit_name":
        prompt = f"Send the new name for *{task['name']}*:"
    else:
        prompt = (
            f"Send the new duration for *{task['name']}*\n"
            f"Examples: `2h`, `30m`, `1h30m`\n"
            f"Or send `none` to remove the target."
        )

    try:
        await query.edit_message_text(prompt, parse_mode="Markdown")
    except BadRequest:
        await context.bot.send_message(chat_id=user.id, text=prompt, parse_mode="Markdown")


async def edit_task_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Captures the plain-text reply for a pending edit."""
    pending = context.user_data.get("pending_edit")
    if not pending:
        return  # Not waiting for an edit reply — ignore

    user = update.effective_user
    task_id = pending["task_id"]
    field = pending["field"]
    text = update.message.text.strip()

    task = db.get_task(task_id, user.id)
    if not task:
        await update.message.reply_text("Task not found.")
        context.user_data.pop("pending_edit", None)
        return

    if field == "name":
        if len(text) > 100:
            await update.message.reply_text("Name too long (max 100 characters). Try again:")
            return
        db.update_task(task_id, user.id, name=text)
        await update.message.reply_text(
            f"✅ Task renamed to *{text}*.", parse_mode="Markdown"
        )

    elif field == "duration":
        if text.lower() == "none":
            db.update_task(task_id, user.id, duration_minutes=-1)
            await update.message.reply_text(
                f"✅ Duration target removed from *{task['name']}*.", parse_mode="Markdown"
            )
        else:
            minutes = parse_duration(text)
            if minutes is None:
                await update.message.reply_text(
                    "Couldn't parse that. Try `2h`, `30m`, `1h30m`, or `none` to remove.\nSend it again:"
                )
                return
            db.update_task(task_id, user.id, duration_minutes=minutes)
            await update.message.reply_text(
                f"✅ Duration for *{task['name']}* set to *{fmt_minutes(minutes)}*.",
                parse_mode="Markdown",
            )

    context.user_data.pop("pending_edit", None)
