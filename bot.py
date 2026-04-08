import logging
import os

from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import database as db
import scheduler as sched
from handlers import (
    add_task_handler,
    edit_field_callback,
    edit_task_callback,
    edit_task_reply_handler,
    edittask_handler,
    endtask_handler,
    list_tasks_handler,
    manual_complete_callback,
    prompt_handler,
    quick_add_callback,
    remove_task_callback,
    remove_task_handler,
    schedule_change_callback,
    schedule_handler,
    start_handler,
    start_task_callback,
    starttask_handler,
    stats_handler,
    status_handler,
    todo_complete_callback,
    todo_handler,
    week_handler,
)

BOT_COMMANDS = [
    BotCommand("status",     "View today's task progress"),
    BotCommand("todo",       "View/add one-off to-do items"),
    BotCommand("week",       "Last 7 days summary"),
    BotCommand("starttask",  "Start a timer on a task"),
    BotCommand("endtask",    "Stop the running timer"),
    BotCommand("addtask",    "Add a new daily task"),
    BotCommand("edittask",   "Edit a task's name or duration"),
    BotCommand("removetask", "Remove a task"),
    BotCommand("listtasks",  "List all active tasks"),
    BotCommand("stats",      "View XP, level, and streak"),
    BotCommand("schedule",   "Change reminder times"),
    BotCommand("prompt",     "Change your mid-task AI prompt"),
    BotCommand("start",      "Welcome and setup"),
]


async def post_init(application) -> None:
    """Runs once after the bot is initialised — sets the command menu in Telegram."""
    await application.bot.set_my_commands(BOT_COMMANDS)
    logging.getLogger(__name__).info("Bot command menu set.")


def main() -> None:
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set. Create a .env file with your token.")

    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s — %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    db.init_db()

    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # Commands
    application.add_handler(CommandHandler("start",      start_handler))
    application.add_handler(CommandHandler("addtask",    add_task_handler))
    application.add_handler(CommandHandler("removetask", remove_task_handler))
    application.add_handler(CommandHandler("listtasks",  list_tasks_handler))
    application.add_handler(CommandHandler("status",     status_handler))
    application.add_handler(CommandHandler("todo",       todo_handler))
    application.add_handler(CommandHandler("week",       week_handler))
    application.add_handler(CommandHandler("stats",      stats_handler))
    application.add_handler(CommandHandler("schedule",   schedule_handler))
    application.add_handler(CommandHandler("starttask",  starttask_handler))
    application.add_handler(CommandHandler("endtask",    endtask_handler))
    application.add_handler(CommandHandler("edittask",   edittask_handler))
    application.add_handler(CommandHandler("prompt",     prompt_handler))

    # Callback queries
    application.add_handler(CallbackQueryHandler(remove_task_callback,      pattern=r"^remove_task:"))
    application.add_handler(CallbackQueryHandler(schedule_change_callback,  pattern=r"^schedule_set:"))
    application.add_handler(CallbackQueryHandler(start_task_callback,       pattern=r"^start_task:"))
    application.add_handler(CallbackQueryHandler(edit_task_callback,        pattern=r"^edit_task:"))
    application.add_handler(CallbackQueryHandler(edit_field_callback,       pattern=r"^edit_name:|^edit_duration:"))
    application.add_handler(CallbackQueryHandler(todo_complete_callback,    pattern=r"^todo_done:"))
    application.add_handler(CallbackQueryHandler(manual_complete_callback,  pattern=r"^manual_done:"))
    application.add_handler(CallbackQueryHandler(quick_add_callback,        pattern=r"^quick_add:"))

    # Plain-text message handler for pending edittask replies (must be last)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_reply_handler))

    # Seed all scheduled jobs from DB
    sched.register_all_jobs(application)

    logging.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
