"""Call Center dashboard routes."""

from __future__ import annotations

import os
import json
import shutil
import signal
import subprocess
from math import ceil
from pathlib import Path
from typing import Optional

import requests
from flask import (
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from ..auth import current_user, role_required
from dashboard.queries import (
    list_telegram_admin_accounts,
    upsert_telegram_admin_accounts,
    delete_telegram_admin_account,
    list_admin_users,
)
from .queries import (
    upsert_cc_conversation,
    fetch_cc_conversations,
    fetch_cc_conversation,
    fetch_cc_messages,
    save_cc_message,
    mark_conversation_read,
    close_conversation,
    reopen_conversation,
    fetch_cc_unread_total,
    upsert_cc_telegram_settings,
    fetch_cc_telegram_settings,
    add_cc_telegram_group,
    list_cc_telegram_groups,
    delete_cc_telegram_group,
    send_cc_telegram_notification,
)
from . import call_center_bp

PAGE_SIZE = 50
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers — bridge management
# ---------------------------------------------------------------------------

def _cc_runtime_paths() -> dict:
    root = PROJECT_ROOT
    session = root / (os.getenv("ASKA_CC_WHATSAPP_SESSION_PATH") or ".wa_cc_session")
    status = root / (os.getenv("ASKA_CC_WHATSAPP_STATUS_PATH") or "runtime/whatsapp_cc_status.json")
    pid = root / "runtime" / "whatsapp_cc.pid"
    log = root / "runtime" / "whatsapp_cc.log"
    return {"root": root, "session": session, "status": status, "pid": pid, "log": log}


def _load_cc_bridge_status() -> dict:
    paths = _cc_runtime_paths()
    try:
        if paths["status"].exists():
            return json.loads(paths["status"].read_text("utf-8"))
    except Exception:
        pass
    return {}


def _read_pid(pid_path: Path) -> Optional[int]:
    try:
        text = pid_path.read_text("utf-8").strip()
        return int(text) if text else None
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _stop_existing_bridge(pid_path: Path) -> None:
    pid = _read_pid(pid_path)
    if pid and _pid_alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    try:
        pid_path.unlink()
    except Exception:
        pass


def _cc_bridge_http_port() -> int:
    return int(os.getenv("ASKA_CC_HTTP_PORT") or "3100")


def _send_via_bridge(to: str, message: str) -> dict:
    """Send an outbound WA message through the CC bridge HTTP API."""
    port = _cc_bridge_http_port()
    token = (os.getenv("ASKA_CC_WHATSAPP_INTERNAL_TOKEN") or "").strip()
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/send",
            json={"to": to, "message": message},
            headers={"X-ASKA-CC-TOKEN": token, "Content-Type": "application/json"},
            timeout=30,
        )
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


def _restart_cc_bridge(reset_session: bool = True) -> dict:
    paths = _cc_runtime_paths()
    _stop_existing_bridge(paths["pid"])

    # Clean stale lock files
    try:
        client_dir = paths["session"] / f"session-{os.getenv('ASKA_CC_WHATSAPP_CLIENT_ID', 'cc-main')}"
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
            for lp in client_dir.rglob(lock_name):
                try:
                    lp.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    if reset_session and paths["session"].exists():
        shutil.rmtree(paths["session"], ignore_errors=True)

    paths["log"].parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    from dotenv import dotenv_values
    env_file = paths["root"] / ".env"
    if env_file.exists():
        for k, v in dotenv_values(env_file).items():
            if k and v is not None and k not in env:
                env[k] = str(v)

    if not (env.get("ASKA_CC_WHATSAPP_INTERNAL_TOKEN") or "").strip():
        raise RuntimeError("ASKA_CC_WHATSAPP_INTERNAL_TOKEN belum diset di .env")

    if "ASKA_CC_WHATSAPP_STATUS_PATH" not in env:
        env["ASKA_CC_WHATSAPP_STATUS_PATH"] = str(paths["status"])

    with paths["log"].open("a", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            ["npm", "run", "wa:cc"],
            cwd=str(paths["root"]),
            env=env,
            stdout=logf,
            stderr=logf,
            start_new_session=True,
        )

    paths["pid"].write_text(str(proc.pid), encoding="utf-8")
    return {"pid": proc.pid, "log_path": str(paths["log"])}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@call_center_bp.route("/")
@role_required("admin")
def inbox() -> Response:
    """Main inbox view listing all conversations."""
    args = request.args
    page = max(1, int(args.get("page", 1)))
    status_filter = args.get("status") or None
    search = (args.get("search") or "").strip() or None
    offset = (page - 1) * PAGE_SIZE

    conversations, total = fetch_cc_conversations(
        status_filter=status_filter,
        search=search,
        limit=PAGE_SIZE,
        offset=offset,
    )
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return render_template(
        "cc_inbox.html",
        conversations=conversations,
        total=total,
        page=page,
        total_pages=total_pages,
        status_filter=status_filter or "all",
        search=search or "",
    )


@call_center_bp.route("/thread/<int:conv_id>")
@role_required("admin")
def thread(conv_id: int) -> Response:
    """Conversation thread view."""
    conv = fetch_cc_conversation(conv_id)
    if not conv:
        flash("Percakapan tidak ditemukan.", "danger")
        return redirect(url_for("call_center.inbox"))

    messages = fetch_cc_messages(conv_id, limit=500)
    mark_conversation_read(conv_id)

    # Sidebar conversations
    conversations, _ = fetch_cc_conversations(limit=50)

    return render_template(
        "cc_thread.html",
        conversation=conv,
        messages=messages,
        conversations=conversations,
    )


# ── API endpoints ─────────────────────────────────────────────────────────────

@call_center_bp.route("/api/send", methods=["POST"])
@role_required("admin")
def api_send() -> Response:
    """Send a reply to a WA user."""
    user = current_user() or {}
    data = request.get_json(silent=True) or {}
    conv_id = data.get("conversation_id")
    message_text = (data.get("message") or "").strip()

    if not conv_id or not message_text:
        return jsonify({"error": "conversation_id and message required"}), 400

    conv = fetch_cc_conversation(int(conv_id))
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    # Send via WA bridge HTTP API
    result = _send_via_bridge(conv["wa_user_id"], message_text)
    if result.get("error"):
        return jsonify({"error": f"Gagal kirim: {result['error']}"}), 502

    # Save message to DB
    admin_name = user.get("full_name") or user.get("email") or "Admin"
    msg = save_cc_message(
        conversation_id=int(conv_id),
        direction="outbound",
        message_text=message_text,
        admin_user_id=user.get("id"),
        admin_display_name=admin_name,
        wa_message_id=result.get("messageId"),
    )

    return jsonify({"ok": True, "message": msg})


@call_center_bp.route("/api/conversations")
@role_required("admin")
def api_conversations() -> Response:
    """JSON API for polling conversations."""
    status_filter = request.args.get("status") or None
    search = (request.args.get("search") or "").strip() or None
    conversations, total = fetch_cc_conversations(
        status_filter=status_filter,
        search=search,
        limit=50,
    )
    return jsonify({"conversations": conversations, "total": total})


@call_center_bp.route("/api/messages/<int:conv_id>")
@role_required("admin")
def api_messages(conv_id: int) -> Response:
    """JSON API for polling messages."""
    after_id = request.args.get("after_id", type=int)
    messages = fetch_cc_messages(conv_id, limit=200, after_id=after_id)
    return jsonify({"messages": messages})


@call_center_bp.route("/api/close/<int:conv_id>", methods=["POST"])
@role_required("admin")
def api_close(conv_id: int) -> Response:
    close_conversation(conv_id)
    return jsonify({"ok": True})


@call_center_bp.route("/api/reopen/<int:conv_id>", methods=["POST"])
@role_required("admin")
def api_reopen(conv_id: int) -> Response:
    reopen_conversation(conv_id)
    return jsonify({"ok": True})


# ── Settings ──────────────────────────────────────────────────────────────────

@call_center_bp.route("/settings")
@role_required("admin")
def settings() -> Response:
    """Redirect legacy /settings to WhatsApp settings."""
    return redirect(url_for("call_center.settings_wa"))


@call_center_bp.route("/settings/wa", methods=["GET", "POST"])
@role_required("admin")
def settings_wa() -> Response:
    """Call Center — Konfigurasi WhatsApp Bridge."""
    bridge_status = _load_cc_bridge_status()
    return render_template("cc_settings_wa.html", bridge_status=bridge_status)


@call_center_bp.route("/settings/telegram", methods=["GET", "POST"])
@role_required("admin")
def settings_telegram() -> Response:
    """Call Center — Notifikasi Telegram + user yang boleh dapat notif."""
    actor = current_user() or {}

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        if action == "save_telegram_token":
            token = request.form.get("bot_token") or ""
            upsert_cc_telegram_settings(token, updated_by=actor.get("id"))
            flash("Token bot Telegram Call Center disimpan.", "success")

        elif action == "delete_group":
            gid = request.form.get("group_id") or ""
            if gid.isdigit() and delete_cc_telegram_group(int(gid)):
                flash("Grup Telegram dihapus.", "success")
            else:
                flash("Gagal menghapus grup.", "danger")

        elif action == "test_notification":
            result = send_cc_telegram_notification("Test User", "Ini pesan tes dari Call Center.")
            if result.get("skipped") == "token_missing":
                flash("Token bot belum diisi.", "warning")
            elif result.get("sent", 0) == 0:
                flash("Notifikasi belum terkirim. Pastikan bot sudah ditambahkan ke grup.", "warning")
            else:
                flash(f"Tes notifikasi terkirim ke {result['sent']} grup.", "success")

        elif action == "add_admins":
            raw_usernames = request.form.getlist("telegram_username[]")
            raw_admin_ids = request.form.getlist("dashboard_user_id[]")
            admin_users_list = list_admin_users()
            admin_ids = {str(u.get("id")) for u in admin_users_list if u.get("id") is not None}
            entries_map = {}
            errors = []
            for idx, (raw_username, raw_admin_id) in enumerate(zip(raw_usernames, raw_admin_ids), start=1):
                username = (raw_username or "").strip().lstrip("@").lower()
                admin_id = (raw_admin_id or "").strip()
                if not username and not admin_id:
                    continue
                if not username:
                    errors.append(f"Username Telegram di baris {idx} kosong.")
                    continue
                if admin_id not in admin_ids:
                    errors.append(f"Admin dashboard belum dipilih untuk @{username}.")
                    continue
                entries_map[username] = int(admin_id)
            if entries_map:
                payload = [
                    {"telegram_username": u, "dashboard_user_id": uid}
                    for u, uid in entries_map.items()
                ]
                saved = upsert_telegram_admin_accounts(payload, created_by=actor.get("id"), scope="call_center")
                flash(f"{saved} admin Telegram Call Center disimpan.", "success")
            for err in errors:
                flash(err, "warning")

        elif action == "delete_admin":
            mapping_id = (request.form.get("mapping_id") or "").strip()
            if mapping_id.isdigit():
                deleted = delete_telegram_admin_account(int(mapping_id))
                if deleted:
                    flash("Admin Telegram dihapus dari daftar penerima notifikasi Call Center.", "success")
                else:
                    flash("Mapping tidak ditemukan.", "warning")
            else:
                flash("ID mapping tidak valid.", "danger")

        return redirect(url_for("call_center.settings_telegram"))

    telegram_settings = fetch_cc_telegram_settings()
    telegram_groups = list_cc_telegram_groups()
    telegram_admins = list_telegram_admin_accounts(scope="call_center")
    admin_users = list_admin_users()

    return render_template(
        "cc_settings_telegram.html",
        telegram_settings=telegram_settings,
        telegram_groups=telegram_groups,
        telegram_admins=telegram_admins,
        admin_users=admin_users,
    )


@call_center_bp.route("/settings/bridge-status")
@role_required("admin")
def bridge_status() -> Response:
    return jsonify(_load_cc_bridge_status())


@call_center_bp.route("/settings/generate-qr", methods=["POST"])
@role_required("admin")
def generate_qr() -> Response:
    try:
        runtime = _restart_cc_bridge(reset_session=True)
        msg = "Bridge Call Center direstart. Tunggu 5-15 detik sampai QR muncul."
        if request.is_json:
            return jsonify({"success": True, "message": msg, "runtime": runtime})
        flash(msg, "success")
    except Exception as exc:
        msg = f"Gagal generate QR: {exc}"
        if request.is_json:
            return jsonify({"success": False, "message": msg}), 500
        flash(msg, "danger")
    return redirect(url_for("call_center.settings_wa"))
