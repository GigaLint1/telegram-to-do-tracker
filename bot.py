import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
)

import database as db
import scheduler as sched
from handlers import (
    add_task_handler,
    checkin_handler,
    list_tasks_handler,
    remove_task_callback,
    remove_task_handler,
    schedule_change_callback,
    schedule_handler,
    show_stats_callback,
    start_handler,
    stats_handler,
    toggle_task_callback,
)


def main() -> None:
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set. Create a .env file with your token.")

    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s — %(message)s",
        level=logging.INFO,
    )
    # Silence noisy PTB internals
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    db.init_db()

    application = ApplicationBuilder().token(token).build()

    # Commands
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("addtask", add_task_handler))
    application.add_handler(CommandHandler("removetask", remove_task_handler))
    application.add_handler(CommandHandler("listtasks", list_tasks_handler))
    application.add_handler(CommandHandler("checkin", checkin_handler))
    application.add_handler(CommandHandler("stats", stats_handler))
    application.add_handler(CommandHandler("schedule", schedule_handler))

    # Callback queries
    application.add_handler(CallbackQueryHandler(toggle_task_callback, pattern=r"^toggle_task:"))
    application.add_handler(CallbackQueryHandler(remove_task_callback, pattern=r"^remove_task:"))
    application.add_handler(CallbackQueryHandler(schedule_change_callback, pattern=r"^schedule_set:"))
    application.add_handler(CallbackQueryHandler(show_stats_callback, pattern=r"^show_stats$"))

    # Seed all scheduled jobs from DB (must happen before run_polling)
    sched.register_all_jobs(application)

    logging.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
