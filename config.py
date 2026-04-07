XP_PER_TASK = 10
XP_BONUS_ALL_TASKS = 50
LEVEL_XP_BASE = 100  # XP needed per level (linear)

DEFAULT_MORNING_TIME = "08:00"
DEFAULT_MIDDAY_TIME = "12:00"
DEFAULT_EVENING_TIME = "20:00"
DEFAULT_TIMEZONE = "UTC"

STREAK_FREEZE_THRESHOLD = 0.5  # >= 50% tasks done = streak frozen (no increment, no reset)

ACHIEVEMENTS = {
    "first_completion": {
        "name": "First Step",
        "description": "Complete your first task",
        "icon": "🌱",
    },
    "first_perfect_day": {
        "name": "Perfect Day",
        "description": "Complete ALL tasks in a single day",
        "icon": "⭐",
    },
    "streak_3": {
        "name": "On a Roll",
        "description": "Reach a 3-day streak",
        "icon": "🔥",
    },
    "streak_7": {
        "name": "Week Warrior",
        "description": "Reach a 7-day streak",
        "icon": "🗡️",
    },
    "streak_30": {
        "name": "Iron Will",
        "description": "Reach a 30-day streak",
        "icon": "🏆",
    },
    "perfect_week": {
        "name": "Perfect Week",
        "description": "Complete all tasks every day for 7 consecutive days",
        "icon": "💎",
    },
    "level_5": {
        "name": "Rising Star",
        "description": "Reach level 5",
        "icon": "🌟",
    },
    "level_10": {
        "name": "Veteran",
        "description": "Reach level 10",
        "icon": "🎖️",
    },
    "task_collector": {
        "name": "Task Collector",
        "description": "Add 10 or more tasks to your list",
        "icon": "📋",
    },
}

LEVEL_TITLES = {
    1: "Newcomer",
    2: "Apprentice",
    3: "Journeyman",
    4: "Adept",
    5: "Expert",
    7: "Master",
    10: "Champion",
    15: "Legend",
    20: "Mythic",
}

MOTIVATIONAL_MESSAGES = [
    "You've got this! 💪",
    "Small steps every day lead to big results. 🚀",
    "Consistency is the key to success. 🗝️",
    "Let's make today count! ⚡",
    "Your future self will thank you. 🙏",
    "Progress, not perfection. 🌊",
    "One task at a time. You can do it! 🎯",
    "Every checkmark is a win. 🏅",
]

SLOT_LABELS = {
    "morning_time": "🌅 Morning",
    "midday_time": "☀️ Midday",
    "evening_time": "🌙 Evening",
}
