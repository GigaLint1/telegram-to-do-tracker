"""
All PTB JobQueue job functions and helpers to register/remove per-user jobs.

PTB v20+ manages the asyncio event loop internally via run_polling().
Jobs MUST be registered via application.job_queue.run_daily() — never via
a standalone APScheduler instance, which would create event loop conflicts.
"""

import logging
from datetime import time as dt_time, date

import pytz
from telegram.ext import ContextTypes

import database as db
import gamification as gami
import llm
from config import SLOT_LABELS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------

async def send_checkin_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the read-only status reminder to the user at a scheduled time."""
    data = context.job.data
    user_id = data["user_id"]
    slot = data["slot"]
    chat_id = context.job.chat_id

    tasks = db.get_active_tasks(user_id)
    if not tasks:
        return

    today = date.today().isoformat()
    completed_ids = set(db.get_today_completions(user_id, today))
    done = len([t for t in tasks if t["id"] in completed_ids])
    total = len(tasks)

    stats = db.get_user_stats(user_id)
    streak = stats["current_streak"] if stats else 0

    # LLM-generated (or static fallback) motivational message
    motivation = await llm.generate_motivational_message(slot, done, total, streak)

    if slot == "morning":
        greeting = f"🌅 *Good morning!*\n_{motivation}_\n\nHere's your day:"
    elif slot == "midday":
        pct = int((done / total) * 100) if total > 0 else 0
        greeting = f"☀️ *Midday check-in!* You're {pct}% done.\n_{motivation}_"
    else:
        if done == total and total > 0:
            greeting = f"🌙 *Evening wrap-up!* 🎉 You completed everything today!\n_{motivation}_"
        else:
            remaining = total - done
            greeting = f"🌙 *Evening wrap-up!* {remaining} task{'s' if remaining != 1 else ''} to go.\n_{motivation}_"

    # Build read-only status text
    from handlers import build_status_text
    status = build_status_text(user_id)

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{greeting}\n\n{status}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to send reminder to {user_id}: {e}")


async def end_of_day_streak_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global job at 23:59 UTC — finalises streaks for all users."""
    today = date.today().isoformat()
    users = db.get_all_users_with_schedule()
    for row in users:
        try:
            gami.finalize_daily_streaks(row["user_id"], today)
        except Exception as e:
            logger.error(f"Streak finalisation failed for {row['user_id']}: {e}")


# ---------------------------------------------------------------------------
# Job registration helpers
# ---------------------------------------------------------------------------

def _parse_hhmm(time_str: str):
    h, m = time_str.split(":")
    return int(h), int(m)


def register_user_jobs(application, user_id: int, chat_id: int) -> None:
    """Register (or re-register) the three daily reminder jobs for one user."""
    times_row = db.get_scheduled_times(user_id)
    if not times_row:
        return

    tz_name = times_row["timezone"] or "UTC"
    try:
        tz = pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        tz = pytz.UTC

    slots = [
        ("morning", times_row["morning_time"]),
        ("midday",  times_row["midday_time"]),
        ("evening", times_row["evening_time"]),
    ]

    for slot, time_str in slots:
        job_name = f"reminder_{user_id}_{slot}"
        for job in application.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

        try:
            hour, minute = _parse_hhmm(time_str)
        except ValueError:
            logger.warning(f"Bad time format '{time_str}' for user {user_id} slot {slot}")
            continue

        job_time = dt_time(hour=hour, minute=minute, tzinfo=tz)
        application.job_queue.run_daily(
            callback=send_checkin_reminder,
            time=job_time,
            chat_id=chat_id,
            user_id=user_id,
            name=job_name,
            data={"user_id": user_id, "slot": slot},
        )
        logger.info(f"Registered job {job_name} at {time_str} {tz_name}")


def remove_user_jobs(application, user_id: int) -> None:
    for slot in ("morning", "midday", "evening"):
        for job in application.job_queue.get_jobs_by_name(f"reminder_{user_id}_{slot}"):
            job.schedule_removal()


def register_all_jobs(application) -> None:
    """Seed all jobs from DB. Called from bot.py before run_polling()."""
    application.job_queue.run_daily(
        callback=end_of_day_streak_update,
        time=dt_time(23, 59, tzinfo=pytz.UTC),
        name="streak_eod_global",
    )

    rows = db.get_all_users_with_schedule()
    for row in rows:
        register_user_jobs(application, row["user_id"], row["user_id"])

    logger.info(f"Registered jobs for {len(rows)} user(s).")
