# Telegram Daily To-Do Tracker

A personal Telegram bot I built to keep myself accountable on daily habits and tasks. It's just a simple idea for an interactive todo app that tracks progress in a (very minimally) gamified fashion with some leeway to prompt some fun messages to yourself lol.

## What it does

You set up a list of recurring daily tasks (things like "Study 2h", "Morning run 30m", "Meditate 20m"). The bot messages you three times a day with a status update and an AI-generated motivational message based on where you're at — how many tasks you've done, your current streak, time of day, etc.

The main flow is timer-based. You use `/starttask` to pick what you're working on, the bot starts tracking time, and once you've logged enough time to hit your daily target for that task it automatically marks it complete and awards you XP. You can keep logging time even after hitting the target if you want.

While a timer is running, the bot nudges you every 20 minutes with a short motivational message. You can customise exactly what kind of message you want — aggressive, calm, specific to how you study, whatever works for you.

There's a light gamification system on top: XP per task, bonus XP for clearing everything in a day, levels, streaks, and achievements. Nothing too serious, just enough to make consistency feel rewarding.

## Features

- **Daily task list** with optional time targets (`/addtask Study 2h`)
- **Session timer** — start and stop timers on tasks, time accumulates across multiple sessions per day
- **Auto-completion** — tasks tick themselves off when you've hit your daily time target
- **Status view** — see exactly where you're at for the day, including live timer progress
- **3x daily reminders** — morning, midday, and evening check-ins at times you set
- **20-min mid-task nudges** while a timer is running (skips scheduled reminders while you're focused)
- **AI motivational messages** via Groq (free) — context-aware, not the same generic quotes every time
- **Customisable AI prompt** — tell the bot how you want to be motivated (`/prompt`)
- **XP, levels, streaks, and achievements**
- **Fully autonomous** — runs on Railway, messages you even when your computer is off

## Commands

| Command | What it does |
|---|---|
| `/status` | Today's task progress — time tracked, what's done, what's running |
| `/starttask` | Start a timer on a task |
| `/endtask` | Stop the running timer |
| `/addtask <name> [duration]` | Add a daily task, e.g. `/addtask Study 2h` |
| `/edittask` | Edit a task's name or duration target |
| `/removetask` | Remove a task |
| `/listtasks` | See all active tasks |
| `/stats` | XP, level, streak, and achievements |
| `/schedule` | Change your reminder times and timezone |
| `/prompt` | View or change your mid-task AI motivational prompt |
| `/start` | Initial setup |

## Setup

**1. Get a bot token from [@BotFather](https://t.me/BotFather)**

**2. Clone and install dependencies**
```bash
git clone https://github.com/GigaLint1/telegram-to-do-tracker.git
cd telegram-to-do-tracker
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

**3. Create a `.env` file**
```
TELEGRAM_BOT_TOKEN=your_token_here
GROQ_API_KEY=your_groq_key_here   # optional, get free at console.groq.com
```

**4. Run it**
```bash
python bot.py
```

## Deploying to Railway (to run 24/7)

1. Push the repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add `TELEGRAM_BOT_TOKEN` and optionally `GROQ_API_KEY` as environment variables
4. Railway picks up the `Procfile` automatically and keeps it running

## Tech stack

- **Python** + `python-telegram-bot` v21 (async)
- **SQLite** for local persistence
- **APScheduler** via PTB's built-in JobQueue for scheduled messages
- **Groq API** (`llama-3.1-8b-instant`) for AI messages, with static fallback if no key is set
- **Railway** for hosting
