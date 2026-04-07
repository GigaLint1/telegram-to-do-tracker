import sqlite3
from contextlib import contextmanager
from typing import Optional

DB_PATH = "todo_bot.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                joined_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                name       TEXT NOT NULL,
                emoji      TEXT NOT NULL DEFAULT '✅',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                is_active  INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS daily_completions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id      INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                date         TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(task_id, user_id, date)
            );

            CREATE TABLE IF NOT EXISTS user_stats (
                user_id              INTEGER PRIMARY KEY,
                total_xp             INTEGER NOT NULL DEFAULT 0,
                current_streak       INTEGER NOT NULL DEFAULT 0,
                longest_streak       INTEGER NOT NULL DEFAULT 0,
                level                INTEGER NOT NULL DEFAULT 1,
                last_completion_date TEXT
            );

            CREATE TABLE IF NOT EXISTS achievements (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                achievement_key TEXT NOT NULL,
                unlocked_at     TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, achievement_key)
            );

            CREATE TABLE IF NOT EXISTS scheduled_times (
                user_id      INTEGER PRIMARY KEY,
                morning_time TEXT NOT NULL DEFAULT '08:00',
                midday_time  TEXT NOT NULL DEFAULT '12:00',
                evening_time TEXT NOT NULL DEFAULT '20:00',
                timezone     TEXT NOT NULL DEFAULT 'UTC'
            );
        """)


# ---------------------------------------------------------------------------
# User functions
# ---------------------------------------------------------------------------

def upsert_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name),
        )


def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------

def add_task(user_id: int, name: str, emoji: str = "✅") -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (user_id, name, emoji) VALUES (?, ?, ?)",
            (user_id, name, emoji),
        )
        return cur.lastrowid


def deactivate_task(task_id: int, user_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET is_active = 0 WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )


def get_active_tasks(user_id: int) -> list:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND is_active = 1 ORDER BY id",
            (user_id,),
        ).fetchall()


def get_total_task_count(user_id: int) -> int:
    """Total tasks ever added (active or not), for Task Collector achievement."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = ?",
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
            "SELECT id FROM daily_completions WHERE task_id = ? AND user_id = ? AND date = ?",
            (task_id, user_id, today),
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM daily_completions WHERE task_id = ? AND user_id = ? AND date = ?",
                (task_id, user_id, today),
            )
            return False
        else:
            conn.execute(
                "INSERT OR IGNORE INTO daily_completions (task_id, user_id, date) VALUES (?, ?, ?)",
                (task_id, user_id, today),
            )
            return True


def get_today_completions(user_id: int, today: str) -> list[int]:
    """Returns list of completed task_ids for today."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT task_id FROM daily_completions WHERE user_id = ? AND date = ?",
            (user_id, today),
        ).fetchall()
        return [r["task_id"] for r in rows]


def get_completion_fraction(user_id: int, today: str) -> tuple[int, int]:
    """Returns (completed_count, total_active_tasks)."""
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = ? AND is_active = 1",
            (user_id,),
        ).fetchone()["cnt"]
        done = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM daily_completions dc
            JOIN tasks t ON dc.task_id = t.id
            WHERE dc.user_id = ? AND dc.date = ? AND t.is_active = 1
            """,
            (user_id, today),
        ).fetchone()["cnt"]
        return done, total


# ---------------------------------------------------------------------------
# User stats functions
# ---------------------------------------------------------------------------

def get_user_stats(user_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM user_stats WHERE user_id = ?", (user_id,)
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
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                total_xp             = excluded.total_xp,
                current_streak       = excluded.current_streak,
                longest_streak       = excluded.longest_streak,
                level                = excluded.level,
                last_completion_date = excluded.last_completion_date
            """,
            (user_id, total_xp, current_streak, longest_streak, level, last_completion_date),
        )


def ensure_user_stats(user_id: int) -> None:
    """Create default stats row if it doesn't exist."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (user_id,)
        )


# ---------------------------------------------------------------------------
# Achievement functions
# ---------------------------------------------------------------------------

def get_user_achievements(user_id: int) -> list:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM achievements WHERE user_id = ? ORDER BY unlocked_at",
            (user_id,),
        ).fetchall()


def unlock_achievement(user_id: int, achievement_key: str) -> bool:
    """Returns True if newly unlocked, False if already existed."""
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO achievements (user_id, achievement_key) VALUES (?, ?)",
                (user_id, achievement_key),
            )
            return True
        except sqlite3.IntegrityError:
            return False


# ---------------------------------------------------------------------------
# Scheduled times functions
# ---------------------------------------------------------------------------

def ensure_scheduled_times(user_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO scheduled_times (user_id) VALUES (?)", (user_id,)
        )


def get_scheduled_times(user_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM scheduled_times WHERE user_id = ?", (user_id,)
        ).fetchone()


def update_scheduled_time(user_id: int, slot: str, time_str: str) -> None:
    """slot: 'morning_time' | 'midday_time' | 'evening_time'"""
    allowed = {"morning_time", "midday_time", "evening_time"}
    if slot not in allowed:
        raise ValueError(f"Invalid slot: {slot}")
    with get_db() as conn:
        conn.execute(
            f"UPDATE scheduled_times SET {slot} = ? WHERE user_id = ?",
            (time_str, user_id),
        )


def update_timezone(user_id: int, tz: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE scheduled_times SET timezone = ? WHERE user_id = ?",
            (tz, user_id),
        )


def get_all_users_with_schedule() -> list:
    with get_db() as conn:
        return conn.execute("SELECT * FROM scheduled_times").fetchall()
