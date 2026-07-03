import logging
import os

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler

from dashboard.supporter.telegram import resolve_supporter_bot_token
from dashboard.supporter.telegram_commands import (
    handle_supporter_callback,
    supporter_pending,
    supporter_register_group,
    supporter_start,
    supporter_unregister_group,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


def _load_token() -> str:
    load_dotenv()
    return resolve_supporter_bot_token() or (os.getenv("TELEGRAM_SUPPORTER_BOT_TOKEN") or "").strip()


TOKEN = _load_token()
if not TOKEN:
    logging.error("Token bot Supporter tidak ditemukan. Set TELEGRAM_SUPPORTER_BOT_TOKEN.")
    raise SystemExit(1)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", supporter_start))
app.add_handler(CommandHandler("pending", supporter_pending))
app.add_handler(CommandHandler("register_group", supporter_register_group))
app.add_handler(CommandHandler("unregister_group", supporter_unregister_group))
app.add_handler(CallbackQueryHandler(handle_supporter_callback, pattern="^supporter:"))

print("BOT SUPPORTER AKTIF...")
app.run_polling()
