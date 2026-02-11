# bot_notif.py
import logging
import os

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

from telegram_admin_commands import (
    admin_pending,
    admin_approve,
    admin_reject,
    admin_register_group,
    admin_unregister_group,
    handle_verification_callback,
    handle_guestbook_callback,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def notif_start(update, context):
    message = (
        "Halo! Ini bot notifikasi admin ASKA.\n"
        "Gunakan /pending untuk daftar akun menunggu verifikasi.\n"
        "Gunakan /register_group di grup untuk mendaftarkan notifikasi."
    )
    await update.effective_message.reply_text(message)


def _load_token() -> str:
    load_dotenv()
    token = (os.getenv("TELEGRAM_NOTIF_BOT_TOKEN") or "").strip()
    if not token:
        try:
            from dashboard.queries import fetch_telegram_notification_settings

            settings = fetch_telegram_notification_settings() or {}
            token = (settings.get("bot_token") or "").strip()
        except Exception as exc:
            logging.error("Gagal memuat token bot notifikasi: %s", exc)
    return token


TOKEN = _load_token()
if not TOKEN:
    logging.error("Token bot notifikasi tidak ditemukan. Set TELEGRAM_NOTIF_BOT_TOKEN atau isi di dashboard.")
    raise SystemExit(1)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", notif_start))
app.add_handler(CommandHandler("pending", admin_pending))
app.add_handler(CommandHandler("approve", admin_approve))
app.add_handler(CommandHandler("reject", admin_reject))
app.add_handler(CommandHandler("register_group", admin_register_group))
app.add_handler(CommandHandler("unregister_group", admin_unregister_group))
app.add_handler(CallbackQueryHandler(handle_verification_callback, pattern="^verify:"))
app.add_handler(CallbackQueryHandler(handle_guestbook_callback, pattern="^guestbook:"))

print("BOT NOTIFIKASI AKTIF...")
app.run_polling()
