from datetime import date, timedelta
from typing import Optional

import database as db
from config import (
    XP_PER_TASK,
    XP_BONUS_ALL_TASKS,
    LEVEL_XP_BASE,
    STREAK_FREEZE_THRESHOLD,
    ACHIEVEMENTS,
    LEVEL_TITLES,
)


def calculate_level(total_xp: int) -> int:
    return 1 + (total_xp // LEVEL_XP_BASE)


def xp_to_next_level(total_xp: int) -> int:
    current_level = calculate_level(total_xp)
    next_threshold = current_level * LEVEL_XP_BASE
    return next_threshold - total_xp


def get_level_title(level: int) -> str:
    title = "Newcomer"
    for lvl, name in sorted(LEVEL_TITLES.items()):
        if level >= lvl:
            title = name
    return f"Level {level} — {title}"


def process_task_toggle(user_id: int, task_id: int, today_str: str, is_now_complete: bool) -> dict:
    """
    Recalculates gamification state after a task toggle.
    is_now_complete: True if the task was just checked off, False if unchecked.

    Returns dict with:
      - xp_earned: int
      - bonus_earned: bool
      - old_level: int
      - new_level: int
      - leveled_up: bool
      - new_achievements: list[str]
    """
    stats = db.get_user_stats(user_id)
    if not stats:
        db.ensure_user_stats(user_id)
        stats = db.get_user_stats(user_id)

    total_xp = stats["total_xp"]
    old_level = stats["level"]

    xp_earned = 0
    bonus_earned = False

    if is_now_complete:
        xp_earned += XP_PER_TASK
        done, total = db.get_completion_fraction(user_id, today_str)
        if total > 0 and done == total:
            xp_earned += XP_BONUS_ALL_TASKS
            bonus_earned = True
    else:
        # Unchecking: remove XP for this task (and bonus if it was earned today)
        done, total = db.get_completion_fraction(user_id, today_str)
        # After the toggle, done is already decremented in DB
        # Remove base XP
        xp_earned = -XP_PER_TASK
        # If previously all tasks were done (done+1 == total before uncheck), remove bonus too
        if total > 0 and done + 1 == total:
            xp_earned -= XP_BONUS_ALL_TASKS

    new_total_xp = max(0, total_xp + xp_earned)
    new_level = calculate_level(new_total_xp)

    # Update streak only when completing (not unchecking)
    current_streak = stats["current_streak"]
    longest_streak = stats["longest_streak"]
    last_date = stats["last_completion_date"]

    if is_now_complete:
        done, total = db.get_completion_fraction(user_id, today_str)
        if total > 0 and done == total:
            # Full completion — update streak
            yesterday = (date.fromisoformat(today_str) - timedelta(days=1)).isoformat()
            if last_date == yesterday or last_date == today_str:
                if last_date != today_str:
                    current_streak += 1
            else:
                current_streak = 1
            longest_streak = max(longest_streak, current_streak)
            last_date = today_str

    db.upsert_user_stats(
        user_id,
        total_xp=new_total_xp,
        current_streak=current_streak,
        longest_streak=longest_streak,
        level=new_level,
        last_completion_date=last_date,
    )

    # Refresh stats for achievement checks
    updated_stats = db.get_user_stats(user_id)
    new_achievements = _check_and_unlock_achievements(user_id, updated_stats)

    return {
        "xp_earned": xp_earned,
        "bonus_earned": bonus_earned,
        "old_level": old_level,
        "new_level": new_level,
        "leveled_up": new_level > old_level,
        "new_achievements": new_achievements,
    }


def finalize_daily_streaks(user_id: int, today_str: str) -> None:
    """
    Called by the end-of-day scheduled job.
    If the user didn't complete everything today, handle streak freeze or reset.
    """
    stats = db.get_user_stats(user_id)
    if not stats:
        return

    last_date = stats["last_completion_date"]
    if last_date == today_str:
        # Already processed (full completion was logged live)
        return

    done, total = db.get_completion_fraction(user_id, today_str)
    if total == 0:
        return

    current_streak = stats["current_streak"]
    longest_streak = stats["longest_streak"]

    fraction = done / total
    if fraction >= STREAK_FREEZE_THRESHOLD:
        # Freeze: no increment, no reset, but mark today so we don't re-process
        pass
    else:
        # Reset streak
        current_streak = 0

    db.upsert_user_stats(
        user_id,
        total_xp=stats["total_xp"],
        current_streak=current_streak,
        longest_streak=longest_streak,
        level=stats["level"],
        last_completion_date=last_date,  # keep old date — today wasn't a full win
    )


def _check_and_unlock_achievements(user_id: int, stats) -> list[str]:
    """Checks all achievement conditions. Returns list of newly unlocked keys."""
    newly_unlocked = []

    done_today, total_today = None, None

    def _get_today_fraction():
        nonlocal done_today, total_today
        if done_today is None:
            from datetime import date as _date
            today = _date.today().isoformat()
            done_today, total_today = db.get_completion_fraction(user_id, today)
        return done_today, total_today

    checks = {
        "first_completion": lambda: stats["total_xp"] > 0,
        "first_perfect_day": lambda: _get_today_fraction()[0] == _get_today_fraction()[1] and _get_today_fraction()[1] > 0,
        "streak_3": lambda: stats["current_streak"] >= 3,
        "streak_7": lambda: stats["current_streak"] >= 7,
        "streak_30": lambda: stats["current_streak"] >= 30,
        "perfect_week": lambda: stats["longest_streak"] >= 7,
        "level_5": lambda: stats["level"] >= 5,
        "level_10": lambda: stats["level"] >= 10,
        "task_collector": lambda: db.get_total_task_count(user_id) >= 10,
    }

    for key, condition_fn in checks.items():
        try:
            if condition_fn() and db.unlock_achievement(user_id, key):
                newly_unlocked.append(key)
        except Exception:
            pass

    return newly_unlocked


def format_stats_message(user_id: int) -> str:
    stats = db.get_user_stats(user_id)
    if not stats:
        return "No stats yet. Use /checkin to start tracking!"

    level = stats["level"]
    total_xp = stats["total_xp"]
    streak = stats["current_streak"]
    longest = stats["longest_streak"]
    xp_needed = xp_to_next_level(total_xp)
    title = get_level_title(level)

    progress_bar = _xp_bar(total_xp)

    achievements = db.get_user_achievements(user_id)
    unlocked_keys = {a["achievement_key"] for a in achievements}
    achievement_lines = []
    for key, info in ACHIEVEMENTS.items():
        icon = info["icon"] if key in unlocked_keys else "🔒"
        achievement_lines.append(f"  {icon} {info['name']} — {info['description']}")

    lines = [
        f"📊 *Your Stats*",
        f"",
        f"🏅 {title}",
        f"✨ XP: {total_xp} ({xp_needed} to next level)",
        f"{progress_bar}",
        f"",
        f"🔥 Current streak: {streak} day{'s' if streak != 1 else ''}",
        f"🏆 Longest streak: {longest} day{'s' if longest != 1 else ''}",
        f"",
        f"🎖️ *Achievements ({len(unlocked_keys)}/{len(ACHIEVEMENTS)})*",
    ] + achievement_lines

    return "\n".join(lines)


def _xp_bar(total_xp: int) -> str:
    level = calculate_level(total_xp)
    level_start = (level - 1) * LEVEL_XP_BASE
    level_end = level * LEVEL_XP_BASE
    progress = total_xp - level_start
    bar_length = 10
    filled = int((progress / LEVEL_XP_BASE) * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)
    return f"[{bar}] {progress}/{LEVEL_XP_BASE} XP"
