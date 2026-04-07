XP_PER_TASK = 10
XP_BONUS_ALL_TASKS = 50
LEVEL_XP_BASE = 100  # XP needed per level (linear)

DEFAULT_MORNING_TIME = "09:00"
DEFAULT_MIDDAY_TIME = "13:30"
DEFAULT_EVENING_TIME = "20:30"
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

MOTIVATIONAL_MESSAGES = motivational_quotes = [
    "🌟 'Do or do not. There is no try.' — Yoda (Star Wars: The Empire Strikes Back)",
    "⚡ 'Gotta catch 'em all!' — Ash Ketchum (Pokémon)",
    "🛡️ 'Spartans never die.' — Master Chief (Halo)",
    "💼 'It's not about changing the world. It's about doing our best to leave the world the way it is.' — Soldier: 92 (Team Fortress 2)",
    "🔥 'I'm not gonna run away, I never go back on my word!' — Naruto Uzumaki (Naruto)",
    "⚔️ 'I want to become a swordsman so powerful that I don't have to rely on anyone.' — Roronoa Zoro (One Piece)",
    "💰 'I have a plan. I just need more money.' — Arthur Morgan (Red Dead Redemption 2)",
    "🧠 'The mind is everything. What you think, you become.' — Buddha/One Punch Man",
    "👾 'I am inevitable.' — Thanos (Marvel: Avengers: Endgame)",
    "✨ 'You must always believe that something wonderful is about to happen.' — Whis (Dragon Ball Super)",
    "🌙 'It doesn't matter if you betray the world, as long as you don't betray yourself.' — Itachi Uchiha (Naruto)",
    "🔥 'A man's dream will never die!' — Portgas D. Ace (One Piece)",
    "🥔 'I'll take a potato chip... and EAT IT!' — Light Yagami (Death Note)",
    "🌙 'The night is darkest just before the dawn.' — Batman (The Dark Knight Rises)",
    "💪 'Sasuke, I'm going to kill you and take back everything!' — Naruto Uzumaki (Naruto)",
    "🦸 'I can't defeat you. So, I'll take my own path to victory.' — Deku (My Hero Academia)",
]

SLOT_LABELS = {
    "morning_time": "🌅 Morning",
    "midday_time": "☀️ Midday",
    "evening_time": "🌙 Evening",
}
