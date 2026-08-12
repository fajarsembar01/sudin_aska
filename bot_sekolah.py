# bot_sekolah.py
import json
import logging
import os
import threading
import urllib.parse as urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from handlers import handle_message, handle_voice, reload_qa_chain, start


def _start_refresh_server() -> None:
    token = os.getenv("ASKA_TELEGRAM_REFRESH_TOKEN") or os.getenv("ASKA_REFRESH_TOKEN")
    if not token:
        logging.info("Refresh server disabled (ASKA_TELEGRAM_REFRESH_TOKEN not set).")
        return

    host = os.getenv("ASKA_TELEGRAM_REFRESH_HOST", "127.0.0.1")
    port = int(os.getenv("ASKA_TELEGRAM_REFRESH_PORT", "5101"))

    class RefreshHandler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802 - http.server signature
            parsed = urlparse.urlparse(self.path)
            if parsed.path != "/api/admin/refresh-knowledge":
                self._send(404, {"error": "Not found"})
                return

            header_token = self.headers.get("X-ASKA-REFRESH-TOKEN")
            query_token = urlparse.parse_qs(parsed.query or "").get("token", [None])[0]
            provided = header_token or query_token
            if provided != token:
                self._send(403, {"error": "Unauthorized"})
                return

            try:
                reload_qa_chain()
            except Exception as exc:
                logging.exception("Failed to reload QA chain")
                self._send(500, {"error": f"Reload failed: {exc}"})
                return

            self._send(200, {"status": "ok"})

        def log_message(
            self, format, *args
        ):  # noqa: A003 - match BaseHTTPRequestHandler signature
            return

    try:
        server = HTTPServer((host, port), RefreshHandler)
    except OSError as exc:
        logging.error("Failed to start refresh server on %s:%s: %s", host, port, exc)
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logging.info(
        "Refresh server active at http://%s:%s/api/admin/refresh-knowledge", host, port
    )


load_dotenv()
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
if not TOKEN:
    logging.error("TELEGRAM_BOT_TOKEN tidak ditemukan. Bot AI tidak dapat dijalankan.")
    raise SystemExit(1)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

_start_refresh_server()

print("ASKA AKTIF...")
app.run_polling()
