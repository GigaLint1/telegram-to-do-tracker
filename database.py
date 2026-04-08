import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Railway sometimes gives postgres:// — psycopg2 needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


class _Conn:
    """Wraps a psycopg2 connection to expose sqlite3-style .execute()."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        cur = self._raw.cursor()
        cur.execute(sql, params or None)
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


@contextmanager
def get_db():
    raw = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn = _Conn(raw)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_NOW = "to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"


def init_db() -> None:
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    BIGINT PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                joined_at  TEXT NOT NULL DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id               SERIAL PRIMARY KEY,
                user_id          BIGINT NOT NULL,
                name             TEXT NOT NULL,
                emoji            TEXT NOT NULL DEFAULT '✅',
                created_at       TEXT NOT NULL DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
                is_active        INTEGER NOT NULL DEFAULT 1,
                duration_minutes INTEGER,
                task_type        TEXT NOT NULL DEFAULT 'recurring'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_completions (
                id                SERIAL PRIMARY KEY,
                task_id           INTEGER NOT NULL,
                user_id           BIGINT NOT NULL,
                date              TEXT NOT NULL,
                completed_at      TEXT NOT NULL DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
                completion_source TEXT DEFAULT 'timer',
                UNIQUE(task_id, user_id, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id              BIGINT PRIMARY KEY,
                total_xp             INTEGER NOT NULL DEFAULT 0,
                current_streak       INTEGER NOT NULL DEFAULT 0,
                longest_streak       INTEGER NOT NULL DEFAULT 0,
                level                INTEGER NOT NULL DEFAULT 1,
                last_completion_date TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id              SERIAL PRIMARY KEY,
                user_id         BIGINT NOT NULL,
                achievement_key TEXT NOT NULL,
                unlocked_at     TEXT NOT NULL DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
                UNIQUE(user_id, achievement_key)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_times (
                user_id         BIGINT PRIMARY KEY,
                morning_time    TEXT NOT NULL DEFAULT '08:00',
                midday_time     TEXT NOT NULL DEFAULT '12:00',
                evening_time    TEXT NOT NULL DEFAULT '20:00',
                timezone        TEXT NOT NULL DEFAULT 'UTC',
                mid_task_prompt TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_sessions (
                id               SERIAL PRIMARY KEY,
                task_id          INTEGER NOT NULL,
                user_id          BIGINT NOT NULL,
                started_at       TEXT NOT NULL,
                ended_at         TEXT,
                duration_seconds INTEGER,
                date             TEXT NOT NULL
            )
        """)


# ---------------------------------------------------------------------------
# User functions
# ---------------------------------------------------------------------------

def upsert_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name
            """,
            (user_id, username, first_name),
        )


def get_user(user_id: int) -> Optional[dict]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = %s", (user_id,)).fetchone()


# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------

def add_task(user_id: int, name: str, emoji: str = "✅", duration_minutes: Optional[int] = None) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (user_id, name, emoji, duration_minutes) VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, name, emoji, duration_minutes),
        )
        return cur.fetchone()["id"]


def deactivate_task(task_id: int, user_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET is_active = 0 WHERE id = %s AND user_id = %s",
            (task_id, user_id),
        )


def update_task(task_id: int, user_id: int, name: Optional[str] = None, duration_minutes: Optional[int] = None) -> None:
    """Update task fields. Pass duration_minutes=-1 to clear the duration target."""
    with get_db() as conn:
        if name is not None:
            conn.execute(
                "UPDATE tasks SET name = %s WHERE id = %s AND user_id = %s",
                (name, task_id, user_id),
            )
        if duration_minutes is not None:
            new_val = None if duration_minutes == -1 else duration_minutes
            conn.execute(
                "UPDATE tasks SET duration_minutes = %s WHERE id = %s AND user_id = %s",
                (new_val, task_id, user_id),
            )


def get_active_tasks(user_id: int) -> list:
    """Returns active recurring tasks only."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE user_id = %s AND is_active = 1 AND task_type = 'recurring' ORDER BY id",
            (user_id,),
        ).fetchall()


def get_active_adhoc_tasks(user_id: int) -> list:
    """Returns active ad-hoc (one-off) tasks."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE user_id = %s AND is_active = 1 AND task_type = 'adhoc' ORDER BY id",
            (user_id,),
        ).fetchall()


def add_adhoc_task(user_id: int, name: str, emoji: str = "📝") -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (user_id, name, emoji, task_type) VALUES (%s, %s, %s, 'adhoc') RETURNING id",
            (user_id, name, emoji),
        )
        return cur.fetchone()["id"]


def get_task(task_id: int, user_id: int) -> Optional[dict]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE id = %s AND user_id = %s",
            (task_id, user_id),
        ).fetchone()


def get_total_task_count(user_id: int) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        return row["cnt"] if row else 0


# ---------------------------------------------------------------------------
# Daily completion functions
# ---------------------------------------------------------------------------

def toggle_task_completion(task_id: int, user_id: int, today: str) -> bool:
    """Toggle a task complete/incomplete. Returns True if now complete, False if unchecked."""
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM daily_completions WHERE task_id = %s AND user_id = %s AND date = %s",
            (task_id, user_id, today),
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM daily_completions WHERE task_id = %s AND user_id = %s AND date = %s",
                (task_id, user_id, today),
            )
            return False
        else:
            conn.execute(
                "INSERT INTO daily_completions (task_id, user_id, date) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (task_id, user_id, today),
            )
            return True


def mark_task_done(task_id: int, user_id: int, today: str, source: str = "timer") -> bool:
    """Mark a task complete for today (one-way). Returns True if inserted, False if already done."""
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO daily_completions (task_id, user_id, date, completion_source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (task_id, user_id, today, source),
        )
        return cur.rowcount > 0


def get_today_completions(user_id: int, today: str) -> list[int]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT task_id FROM daily_completions WHERE user_id = %s AND date = %s",
            (user_id, today),
        ).fetchall()
        return [r["task_id"] for r in rows]


def get_completion_fraction(user_id: int, today: str) -> tuple[int, int]:
    """Returns (done, total) for active recurring tasks only."""
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = %s AND is_active = 1 AND task_type = 'recurring'",
            (user_id,),
        ).fetchone()["cnt"]
        done = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM daily_completions dc
            JOIN tasks t ON dc.task_id = t.id
            WHERE dc.user_id = %s AND dc.date = %s AND t.is_active = 1 AND t.task_type = 'recurring'
            """,
            (user_id, today),
        ).fetchone()["cnt"]
        return done, total


# ---------------------------------------------------------------------------
# User stats functions
# ---------------------------------------------------------------------------

def get_user_stats(user_id: int) -> Optional[dict]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM user_stats WHERE user_id = %s", (user_id,)
        ).fetchone()


def upsert_user_stats(
    user_id: int,
    total_xp: int,
    current_streak: int,
    longest_streak: int,
    level: int,
    last_completion_date: Optional[str],
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO user_stats
                (user_id, total_xp, current_streak, longest_streak, level, last_completion_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                total_xp             = EXCLUDED.total_xp,
                current_streak       = EXCLUDED.current_streak,
                longest_streak       = EXCLUDED.longest_streak,
                level                = EXCLUDED.level,
                last_completion_date = EXCLUDED.last_completion_date
            """,
            (user_id, total_xp, current_streak, longest_streak, level, last_completion_date),
        )


def ensure_user_stats(user_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO user_stats (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,)
        )


# ---------------------------------------------------------------------------
# Achievement functions
# ---------------------------------------------------------------------------

def get_user_achievements(user_id: int) -> list:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM achievements WHERE user_id = %s ORDER BY unlocked_at",
            (user_id,),
        ).fetchall()


def unlock_achievement(user_id: int, achievement_key: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO achievements (user_id, achievement_key) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, achievement_key),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Scheduled times functions
# ---------------------------------------------------------------------------

def ensure_scheduled_times(user_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO scheduled_times (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,)
        )


def get_scheduled_times(user_id: int) -> Optional[dict]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM scheduled_times WHERE user_id = %s", (user_id,)
        ).fetchone()


def update_scheduled_time(user_id: int, slot: str, time_str: str) -> None:
    allowed = {"morning_time", "midday_time", "evening_time"}
    if slot not in allowed:
        raise ValueError(f"Invalid slot: {slot}")
    with get_db() as conn:
        conn.execute(
            f"UPDATE scheduled_times SET {slot} = %s WHERE user_id = %s",
            (time_str, user_id),
        )


def update_timezone(user_id: int, tz: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE scheduled_times SET timezone = %s WHERE user_id = %s",
            (tz, user_id),
        )


def get_all_users_with_schedule() -> list:
    with get_db() as conn:
        return conn.execute("SELECT * FROM scheduled_times").fetchall()


DEFAULT_MID_TASK_PROMPT = (
    "The user is currently working on a task. Send them a very short (1 sentence), "
    "specific and energetic motivational nudge. No generic phrases. No emojis in text."
)


def get_user_prompt(user_id: int) -> str:
    """Returns the user's custom mid-task prompt, or the default if none is set."""
    row = get_scheduled_times(user_id)
    if row and row["mid_task_prompt"]:
        return row["mid_task_prompt"]
    return DEFAULT_MID_TASK_PROMPT


def set_user_prompt(user_id: int, prompt: Optional[str]) -> None:
    """Set (or clear with None) the user's custom mid-task prompt."""
    with get_db() as conn:
        conn.execute(
            "UPDATE scheduled_times SET mid_task_prompt = %s WHERE user_id = %s",
            (prompt, user_id),
        )


# ---------------------------------------------------------------------------
# Task session functions (timer)
# ---------------------------------------------------------------------------

def get_active_session(user_id: int) -> Optional[dict]:
    """Returns the currently running session (ended_at IS NULL), or None."""
    with get_db() as conn:
        return conn.execute(
            """
            SELECT ts.*, t.name as task_name, t.duration_minutes
            FROM task_sessions ts
            JOIN tasks t ON ts.task_id = t.id
            WHERE ts.user_id = %s AND ts.ended_at IS NULL
            ORDER BY ts.started_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()


def start_session(user_id: int, task_id: int, date_str: str) -> int:
    """Insert a new session row. Returns the session id."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO task_sessions (task_id, user_id, started_at, date) VALUES (%s, %s, %s, %s) RETURNING id",
            (task_id, user_id, now, date_str),
        )
        return cur.fetchone()["id"]


def end_session(session_id: int) -> int:
    """Close a session, compute duration_seconds. Returns elapsed seconds."""
    now = datetime.now(timezone.utc)
    with get_db() as conn:
        row = conn.execute(
            "SELECT started_at FROM task_sessions WHERE id = %s", (session_id,)
        ).fetchone()
        if not row:
            return 0
        started = datetime.fromisoformat(row["started_at"])
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = int((now - started).total_seconds())
        conn.execute(
            "UPDATE task_sessions SET ended_at = %s, duration_seconds = %s WHERE id = %s",
            (now.isoformat(), elapsed, session_id),
        )
        return elapsed


def get_today_session_totals(user_id: int, date_str: str) -> dict[int, int]:
    """Returns {task_id: total_seconds_today} for all completed sessions today."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT task_id, SUM(duration_seconds) as total
            FROM task_sessions
            WHERE user_id = %s AND date = %s AND ended_at IS NOT NULL
            GROUP BY task_id
            """,
            (user_id, date_str),
        ).fetchall()
        return {r["task_id"]: r["total"] for r in rows}


def get_today_totals_including_active(user_id: int, date_str: str) -> dict[int, int]:
    """
    Like get_today_session_totals but also adds live elapsed time of any active session.
    Returns {task_id: total_seconds_today}.
    """
    totals = get_today_session_totals(user_id, date_str)
    with get_db() as conn:
        active = conn.execute(
            "SELECT task_id, started_at FROM task_sessions WHERE user_id = %s AND ended_at IS NULL",
            (user_id,),
        ).fetchone()
    if active:
        started = datetime.fromisoformat(active["started_at"])
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = int((datetime.now(timezone.utc) - started).total_seconds())
        tid = active["task_id"]
        totals[tid] = totals.get(tid, 0) + elapsed
    return totals
