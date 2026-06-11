"""Call Center dashboard routes."""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import base64
import json
import mimetypes
import shutil
import signal
import subprocess
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from dotenv import dotenv_values
from flask import (
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from ..auth import current_user, role_required
from dashboard.queries import (
    list_telegram_admin_accounts,
    upsert_telegram_admin_accounts,
    delete_telegram_admin_account,
    list_admin_users,
    record_admin_action,
)
from .queries import (
    upsert_cc_conversation,
    fetch_cc_conversations,
    fetch_cc_conversation,
    fetch_cc_messages,
    fetch_cc_message,
    save_cc_message,
    update_cc_message_text,
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
    list_cc_message_drafts,
    list_cc_message_draft_categories,
    get_cc_message_draft,
    create_cc_message_draft,
    update_cc_message_draft,
    delete_cc_message_draft,
    toggle_cc_message_draft_pin,
    fetch_cc_media_db_refs,
    clear_cc_media_db_refs,
    ensure_cc_wa_routing_contact,
    get_cc_wa_routing,
    list_cc_wa_routing,
    summarize_cc_wa_routing,
    save_cc_wa_routing,
    delete_cc_wa_routing,
    normalize_cc_route_mode,
    normalize_cc_bridge_key,
    compose_cc_conversation_user_key,
    split_cc_conversation_user_key,
    ensure_default_cc_wa_bridge_account,
    list_cc_wa_bridge_accounts,
    get_cc_wa_bridge_account,
    save_cc_wa_bridge_account,
    delete_cc_wa_bridge_account,
    get_default_cc_wa_bridge_account,
    fetch_cc_public_whatsapp_cta_settings,
    upsert_cc_public_whatsapp_cta_settings,
    delete_cc_public_whatsapp_cta_settings,
    CC_PUBLIC_WHATSAPP_DEFAULT_MESSAGE,
    fetch_cc_statistics,
)
from . import call_center_api_bp, call_center_bp
from .media import (
    CC_MEDIA_ROOT,
    call_center_media_label,
    resolve_call_center_media_path,
    save_call_center_media,
    save_call_center_media_with_error,
)

PAGE_SIZE = 50
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _project_env_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    try:
        return str(dotenv_values(PROJECT_ROOT / ".env").get(name) or default)
    except Exception:
        return default


def _cc_bridge_auth_error() -> Optional[tuple[Response, int]]:
    token_expected = (_project_env_value("ASKA_CC_WHATSAPP_INTERNAL_TOKEN") or "").strip()
    if not token_expected:
        return jsonify({"error": "ASKA_CC_WHATSAPP_INTERNAL_TOKEN belum dikonfigurasi"}), 501

    provided_token = (
        request.headers.get("X-ASKA-CC-TOKEN")
        or request.args.get("token")
        or ""
    ).strip()
    if provided_token != token_expected:
        return jsonify({"error": "Unauthorized"}), 403

    return None


def _run_async(coro):
    """Safely run async coroutine inside sync Flask handlers."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers — bridge management
# ---------------------------------------------------------------------------

def _bridge_accounts() -> list[dict]:
    ensure_default_cc_wa_bridge_account()
    rows = list_cc_wa_bridge_accounts(include_inactive=True)
    return rows or [get_default_cc_wa_bridge_account()]


def _resolve_bridge_account(bridge_key: Optional[str] = None) -> dict:
    ensure_default_cc_wa_bridge_account()
    key = normalize_cc_bridge_key(bridge_key)
    row = get_cc_wa_bridge_account(key)
    if row:
        return row
    if key != "main":
        raise ValueError(f"Akun bridge '{key}' tidak ditemukan.")
    return get_default_cc_wa_bridge_account()


def _cc_runtime_paths(account: Optional[dict] = None) -> dict:
    account = account or _resolve_bridge_account(None)
    root = PROJECT_ROOT
    bridge_key = normalize_cc_bridge_key(account.get("bridge_key"))
    default_session = ".wa_cc_session" if bridge_key == "main" else f".wa_cc_session_{bridge_key}"
    default_status = "runtime/whatsapp_cc_status.json" if bridge_key == "main" else f"runtime/whatsapp_cc_status_{bridge_key}.json"
    default_pid = "runtime/whatsapp_cc.pid" if bridge_key == "main" else f"runtime/whatsapp_cc_{bridge_key}.pid"
    default_log = "runtime/whatsapp_cc.log" if bridge_key == "main" else f"runtime/whatsapp_cc_{bridge_key}.log"

    session = root / (str(account.get("session_path") or default_session).strip() or default_session)
    status = root / (str(account.get("status_path") or default_status).strip() or default_status)
    pid = root / (str(account.get("pid_path") or default_pid).strip() or default_pid)
    log = root / (str(account.get("log_path") or default_log).strip() or default_log)
    return {"root": root, "session": session, "status": status, "pid": pid, "log": log}


def _cc_systemd_service() -> str:
    """Nama systemd service untuk bridge CC, atau string kosong jika tidak pakai systemd."""
    return (_project_env_value("ASKA_CC_SYSTEMD_SERVICE") or "aska-wa-cc").strip()


def _systemd_service_active(service: str) -> bool:
    """True jika systemd service sedang active (running)."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", service],
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _systemd_service_exists(service: str) -> bool:
    """True jika unit file systemd untuk service ini ditemukan."""
    try:
        result = subprocess.run(
            ["systemctl", "list-unit-files", "--quiet", service],
            capture_output=True, timeout=5,
        )
        return service in (result.stdout.decode(errors="replace") or "")
    except Exception:
        return False


def _bridge_http_alive(bridge_key: Optional[str] = None) -> bool:
    """Cek apakah bridge HTTP API merespons di portnya — cara paling akurat."""
    port = _cc_bridge_http_port(bridge_key=bridge_key)
    try:
        resp = requests.get(
            f"http://127.0.0.1:{port}/health",
            timeout=2,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _load_cc_bridge_status(bridge_key: Optional[str] = None) -> dict:
    def _load_one(account: dict) -> dict:
        paths = _cc_runtime_paths(account=account)
        status: dict = {}
        try:
            if paths["status"].exists():
                status = json.loads(paths["status"].read_text("utf-8"))
        except Exception:
            status = {}

        key = normalize_cc_bridge_key(account.get("bridge_key"))
        running = _bridge_http_alive(bridge_key=key)
        if not running:
            pid = _read_pid(paths["pid"])
            if pid and _pid_alive(pid):
                running = True
                status["pid"] = pid

        status["bridgeKey"] = key
        status["bridgeName"] = account.get("display_name") or key
        status["httpPort"] = int(account.get("http_port") or 3100)
        status["isActive"] = bool(account.get("is_active", True))
        status["isRunning"] = running
        status["statusPath"] = str(paths["status"])
        status["pidPath"] = str(paths["pid"])
        status["logPath"] = str(paths["log"])
        detected_number = _normalize_wa_user_id(
            status.get("whatsappNumber")
            or status.get("waNumber")
            or status.get("selfNumber")
            or ""
        )
        manual_number = _normalize_wa_user_id(account.get("wa_number_hint") or "")
        status["whatsappNumberDetected"] = detected_number
        status["whatsappNumberManual"] = manual_number
        status["whatsappNumber"] = detected_number or manual_number
        status["whatsappNumberSource"] = (
            "detected"
            if detected_number
            else ("manual" if manual_number else "")
        )

        if not running:
            current_state = (status.get("state") or "").strip().lower()
            if current_state in {"starting", "authenticated", "ready", "qr", "disconnected"}:
                status["state"] = "stopped"
                if not (status.get("message") or "").strip() or current_state == "starting":
                    status["message"] = "Bridge tidak berjalan. Jalankan Generate QR untuk memulai lagi."
        return status

    if bridge_key:
        account = _resolve_bridge_account(bridge_key)
        return _load_one(account)

    accounts = _bridge_accounts()
    statuses = [_load_one(acc) for acc in accounts]
    if not statuses:
        return {
            "state": "stopped",
            "message": "Belum ada akun bridge aktif.",
            "isRunning": False,
            "qrText": "",
            "accounts": [],
        }

    active_statuses = [s for s in statuses if bool(s.get("isActive", True))]
    baseline_statuses = active_statuses or statuses
    any_ready = any((s.get("state") or "").lower() == "ready" and bool(s.get("isRunning")) for s in baseline_statuses)
    any_running = any(bool(s.get("isRunning")) for s in baseline_statuses)
    summary = dict(statuses[0])
    summary["accounts"] = statuses
    summary["isRunning"] = any_running
    if any_ready:
        summary["state"] = "ready"
        summary["message"] = "Minimal satu akun bridge sedang aktif."
    return summary


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


def _stop_existing_bridge(account: dict) -> None:
    paths = _cc_runtime_paths(account=account)
    # Fallback: kill via PID
    pid = _read_pid(paths["pid"])
    if pid and _pid_alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    try:
        paths["pid"].unlink()
    except Exception:
        pass


def _cc_bridge_http_port(bridge_key: Optional[str] = None) -> int:
    account = _resolve_bridge_account(bridge_key)
    try:
        return int(account.get("http_port") or 3100)
    except Exception:
        return 3100


def _normalize_wa_user_id(raw_user_id: str) -> str:
    return "".join(ch for ch in str(raw_user_id or "") if ch.isdigit())


def _to_bool_flag(raw_value) -> bool:
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _settings_wa_redirect(bridge_key: Optional[str] = None) -> Response:
    key = normalize_cc_bridge_key(bridge_key)
    return redirect(url_for("call_center.settings_wa", bridge_key=key))


def _format_public_whatsapp_url(number: Optional[str], message: Optional[str]) -> str:
    digits = _normalize_wa_user_id(number or "")
    if not digits:
        return ""
    if digits.startswith("0"):
        digits = f"62{digits[1:]}"
    text = (message or CC_PUBLIC_WHATSAPP_DEFAULT_MESSAGE).strip()
    return f"https://wa.me/{digits}?text={quote(text, safe='')}"


def _normalize_bridge_filter(raw_value: Optional[str]) -> tuple[str, Optional[str]]:
    value = (raw_value or "all").strip().lower()
    if value in {"", "all", "*"}:
        return "all", None
    key = normalize_cc_bridge_key(value)
    return key, key


def _jakarta_now() -> datetime:
    try:
        return datetime.now(ZoneInfo("Asia/Jakarta"))
    except Exception:
        return datetime.now()


def _send_via_bridge(
    to: str,
    message: str = "",
    media: Optional[dict] = None,
    *,
    bridge_key: Optional[str] = None,
) -> dict:
    """Send an outbound WA message through the CC bridge HTTP API."""
    port = _cc_bridge_http_port(bridge_key=bridge_key)
    token = (_project_env_value("ASKA_CC_WHATSAPP_INTERNAL_TOKEN") or "").strip()
    try:
        timeout = float(_project_env_value("ASKA_CC_BRIDGE_SEND_TIMEOUT_SECONDS", "20") or 20)
    except (TypeError, ValueError):
        timeout = 20.0
    payload = {"to": to, "message": message or ""}
    if media:
        payload["media"] = media
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/send",
            json=payload,
            headers={"X-ASKA-CC-TOKEN": token, "Content-Type": "application/json"},
            timeout=max(5.0, min(timeout, 25.0)),
        )
        try:
            result = resp.json()
        except ValueError:
            body = (resp.text or "").replace("\n", " ").strip()
            result = {"error": body[:240] or f"HTTP {resp.status_code}"}
        if resp.status_code >= 400 and not result.get("error"):
            result["error"] = f"HTTP {resp.status_code}"
        return result
    except Exception as exc:
        return {"error": str(exc)}


def _dispatch_to_ai_whatsapp(
    *,
    raw_user_id: str,
    username: str,
    message: str,
    bridge_key: Optional[str] = None,
) -> dict:
    """Run AI response flow and send the answer back through CC bridge."""
    from account_status import BLOCKING_STATUSES, build_status_notice
    from db import get_whatsapp_user_status, save_chat
    from web_aska.handlers import process_channel_request

    normalized_id = _normalize_wa_user_id(raw_user_id)
    if not normalized_id:
        return {"ok": False, "error": "Nomor WhatsApp tidak valid untuk mode AI."}

    user_id = int(normalized_id)
    status_info = get_whatsapp_user_status(user_id)
    status_value = (status_info or {}).get("status")

    blocked = False
    block_type = None
    chat_log_id = None

    if status_value in BLOCKING_STATUSES:
        blocked = True
        block_type = "status"
        notice = build_status_notice(
            status_value,
            reason=(status_info or {}).get("status_reason"),
            channel="whatsapp",
        )
        save_chat(user_id, username, message, role="user", topic="whatsapp")
        ai_reply = notice.message if notice else "Akses WhatsApp kamu sedang dibatasi oleh sekolah."
        save_chat(user_id, "ASKA", ai_reply, role="aska", topic="whatsapp")
    else:
        ai_reply, chat_log_id = _run_async(
            process_channel_request(
                user_id,
                message,
                username=username,
                topic="whatsapp",
            )
        )

    ai_reply = str(ai_reply or "").strip()
    if not ai_reply:
        ai_reply = "ASKA lagi gangguan teknis sebentar. Coba kirim ulang beberapa saat lagi ya."

    bridge_key = normalize_cc_bridge_key(bridge_key)
    send_result = _send_via_bridge(to=raw_user_id, message=ai_reply, bridge_key=bridge_key)
    send_error = (send_result or {}).get("error")
    wa_message_id = (send_result or {}).get("messageId")

    return {
        "ok": not bool(send_error),
        "route_mode": "ai",
        "is_active": True,
        "bridge_key": bridge_key,
        "blocked": blocked,
        "blockType": block_type,
        "chat_log_id": chat_log_id,
        "reply_text": ai_reply,
        "wa_message_id": wa_message_id,
        "reply_sent": not bool(send_error),
        "reply_error": send_error,
    }


def _edit_via_bridge(wa_message_id: str, message: str, *, bridge_key: Optional[str] = None) -> dict:
    """Edit an outbound WA message through the CC bridge HTTP API."""
    port = _cc_bridge_http_port(bridge_key=bridge_key)
    token = (_project_env_value("ASKA_CC_WHATSAPP_INTERNAL_TOKEN") or "").strip()
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/edit",
            json={"messageId": wa_message_id, "message": message or ""},
            headers={"X-ASKA-CC-TOKEN": token, "Content-Type": "application/json"},
            timeout=8,
        )
        try:
            result = resp.json()
        except ValueError:
            result = {"error": (resp.text or "").strip() or f"HTTP {resp.status_code}"}
        if resp.status_code >= 400 and not result.get("error"):
            result["error"] = f"HTTP {resp.status_code}"
        return result
    except Exception as exc:
        return {"error": str(exc)}


def _media_payload_from_upload(uploaded_file) -> tuple[Optional[dict], Optional[str]]:
    """Build a base64 media payload from a Flask upload."""
    if not uploaded_file or not (uploaded_file.filename or "").strip():
        return None, None

    filename = Path(uploaded_file.filename).name
    try:
        content = uploaded_file.read()
    except Exception as exc:
        return None, f"Gagal membaca file: {exc}"

    if not content:
        return None, "File kosong."

    mime_type = (
        getattr(uploaded_file, "mimetype", None)
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )
    return {
        "mimetype": mime_type,
        "filename": filename,
        "data": base64.b64encode(content).decode("ascii"),
    }, None


def _bridge_media_from_saved(media_meta: dict) -> Optional[dict]:
    """Read the stored/compressed media back into the bridge payload format."""
    media_path = media_meta.get("media_path")
    target_path = resolve_call_center_media_path(media_path)
    if not target_path or not target_path.is_file():
        return None

    try:
        content = target_path.read_bytes()
    except OSError:
        return None

    return {
        "mimetype": media_meta.get("media_mime_type") or "application/octet-stream",
        "filename": media_meta.get("media_filename") or target_path.name,
        "data": base64.b64encode(content).decode("ascii"),
    }


def _inbound_media_max_bytes() -> int:
    try:
        return max(1, int(_project_env_value("ASKA_CC_INBOUND_MEDIA_MAX_BYTES", "307200")))
    except ValueError:
        return 300 * 1024


def _save_inbound_media(media_payload, *, message_id: Optional[str] = None) -> dict:
    # Tanpa limit ukuran secara default. Jika perlu diaktifkan lagi:
    # inbound_limit = _inbound_media_max_bytes()
    # return save_call_center_media(
    #     media_payload,
    #     message_id=message_id,
    #     max_image_bytes=inbound_limit,
    #     max_pdf_bytes=inbound_limit,
    #     max_file_bytes=inbound_limit,
    # )
    return save_call_center_media(
        media_payload,
        message_id=message_id,
    )


def _draft_media_max_bytes() -> int:
    try:
        return max(1, int(_project_env_value("ASKA_CC_DRAFT_MEDIA_MAX_BYTES", "1048576")))
    except ValueError:
        return 1024 * 1024


def _outbound_media_max_bytes() -> int:
    default_limit = _project_env_value("ASKA_CC_DRAFT_MEDIA_MAX_BYTES", "1048576")
    try:
        return max(1, int(_project_env_value("ASKA_CC_OUTBOUND_MEDIA_MAX_BYTES", default_limit)))
    except ValueError:
        return 1024 * 1024


def _save_outbound_media(media_payload) -> tuple[dict, Optional[str]]:
    # Tanpa limit ukuran secara default. Jika perlu diaktifkan lagi:
    # outbound_limit = _outbound_media_max_bytes()
    # return save_call_center_media_with_error(
    #     media_payload,
    #     max_image_bytes=outbound_limit,
    #     max_pdf_bytes=outbound_limit,
    #     max_file_bytes=outbound_limit,
    # )
    return save_call_center_media_with_error(
        media_payload,
    )


def _save_draft_media(media_payload) -> tuple[dict, Optional[str]]:
    # Tanpa limit ukuran secara default. Jika perlu diaktifkan lagi:
    # draft_limit = _draft_media_max_bytes()
    # return save_call_center_media_with_error(
    #     media_payload,
    #     max_image_bytes=draft_limit,
    #     max_pdf_bytes=draft_limit,
    #     max_file_bytes=draft_limit,
    # )
    return save_call_center_media_with_error(
        media_payload,
    )


def _sync_history_via_bridge(chat_limit: int, limit_per_chat: int, *, bridge_key: Optional[str] = None) -> dict:
    """Ask the local CC bridge to import recent WhatsApp chat history."""
    port = _cc_bridge_http_port(bridge_key=bridge_key)
    token = (_project_env_value("ASKA_CC_WHATSAPP_INTERNAL_TOKEN") or "").strip()
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/sync-history",
            json={
                "chatLimit": chat_limit,
                "limitPerChat": limit_per_chat,
                "bridge_key": normalize_cc_bridge_key(bridge_key),
            },
            headers={"X-ASKA-CC-TOKEN": token, "Content-Type": "application/json"},
            timeout=180,
        )
        data = resp.json()
        if resp.status_code >= 400:
            return {"error": data.get("error") or f"HTTP {resp.status_code}"}
        return data
    except Exception as exc:
        return {"error": str(exc)}


def _restart_cc_bridge(account: dict, reset_session: bool = True) -> dict:
    paths = _cc_runtime_paths(account=account)
    _stop_existing_bridge(account)
    bridge_key = normalize_cc_bridge_key(account.get("bridge_key"))
    client_id = (str(account.get("client_id") or "").strip() or f"cc-{bridge_key}")
    http_port = int(account.get("http_port") or 3100)
    internal_url = (
        str(account.get("internal_url") or "").strip()
        or _project_env_value("ASKA_CC_WHATSAPP_INTERNAL_URL")
        or "http://127.0.0.1:5002/api/callcenter/inbound"
    )

    # Bersihkan lock file Chromium yang mungkin tersisa
    try:
        client_dir = paths["session"] / f"session-{client_id}"
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

    # ── Kelola via systemd jika service tersedia ──────────────────────────────
    # ── Fallback: spawn subprocess langsung ───────────────────────────────────
    env = os.environ.copy()
    env_file = paths["root"] / ".env"
    if env_file.exists():
        for k, v in dotenv_values(env_file).items():
            if k and v is not None and k not in env:
                env[k] = str(v)

    if not (env.get("ASKA_CC_WHATSAPP_INTERNAL_TOKEN") or "").strip():
        raise RuntimeError("ASKA_CC_WHATSAPP_INTERNAL_TOKEN belum diset di .env")

    env["ASKA_CC_BRIDGE_KEY"] = bridge_key
    env["ASKA_CC_WHATSAPP_CLIENT_ID"] = client_id
    env["ASKA_CC_HTTP_PORT"] = str(http_port)
    env["ASKA_CC_WHATSAPP_SESSION_PATH"] = str(paths["session"])
    env["ASKA_CC_WHATSAPP_STATUS_PATH"] = str(paths["status"])
    env["ASKA_CC_WHATSAPP_INTERNAL_URL"] = internal_url

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
    return {
        "bridge_key": bridge_key,
        "pid": proc.pid,
        "http_port": http_port,
        "log_path": str(paths["log"]),
        "status_path": str(paths["status"]),
        "managed_by": "subprocess",
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@call_center_api_bp.route("/inbound", methods=["POST"])
def api_callcenter_inbound() -> Response:
    """Receive inbound messages directly in the dashboard app."""
    auth_error = _cc_bridge_auth_error()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    raw_user_id = _normalize_wa_user_id(str(data.get("user_id") or ""))
    if not raw_user_id:
        return jsonify({"error": "user_id required"}), 400
    bridge_key = normalize_cc_bridge_key(data.get("bridge_key"))
    try:
        bridge_account = _resolve_bridge_account(bridge_key)
    except Exception:
        bridge_key = normalize_cc_bridge_key(None)
        bridge_account = _resolve_bridge_account(bridge_key)

    conversation_user_key = compose_cc_conversation_user_key(raw_user_id, bridge_key)
    if not conversation_user_key:
        return jsonify({"error": "conversation key invalid"}), 400

    username = str(data.get("username") or raw_user_id).strip()[:120] or raw_user_id
    message = str(data.get("message") or "").strip()
    message_id = data.get("message_id") or None
    media_payload = data.get("media") or {}
    media_meta = _save_inbound_media(media_payload, message_id=message_id)
    if not message and (media_payload or media_meta):
        message = call_center_media_label(
            media_meta.get("media_mime_type")
            or (media_payload.get("mimetype") if isinstance(media_payload, dict) else None)
        )
    if not message:
        return jsonify({"error": "message required"}), 400

    try:
        default_route_mode = normalize_cc_route_mode(
            bridge_account.get("default_route_mode") or "manual"
        )
        route_rule = get_cc_wa_routing(raw_user_id, bridge_key=bridge_key)
        if not route_rule:
            # First contact follows bridge default mode (manual/ai).
            route_rule = ensure_cc_wa_routing_contact(
                raw_user_id,
                display_name=username,
                route_mode=default_route_mode,
                bridge_key=bridge_key,
            ) or {}
        route_mode = normalize_cc_route_mode(route_rule.get("route_mode") or default_route_mode)
        is_active = bool(route_rule.get("is_active", True))

        if not is_active:
            return jsonify(
                {
                    "ok": True,
                    "ignored": True,
                    "reason": "wa_route_inactive",
                    "route_mode": route_mode,
                    "is_active": False,
                    "bridge_key": bridge_key,
                }
            )

        if route_mode == "ai":
            # Keep AI traffic visible in Call Center inbox as well.
            conv = upsert_cc_conversation(wa_user_id=conversation_user_key, display_name=username)
            inbound_msg = save_cc_message(
                conversation_id=conv["id"],
                direction="inbound",
                message_text=message,
                wa_message_id=message_id,
                **media_meta,
            )
            if inbound_msg.get("duplicate"):
                return jsonify(
                    {
                        "ok": True,
                        "route_mode": "ai",
                        "is_active": True,
                        "bridge_key": bridge_key,
                        "conversation_id": conv.get("id"),
                        "message_id": inbound_msg.get("id"),
                        "duplicate": True,
                        "skipped_ai": True,
                    }
                )

            ai_result = _dispatch_to_ai_whatsapp(
                raw_user_id=raw_user_id,
                username=username,
                message=message,
                bridge_key=bridge_key,
            )

            reply_text = str(ai_result.get("reply_text") or "").strip()
            if reply_text:
                save_cc_message(
                    conversation_id=conv["id"],
                    direction="outbound",
                    message_text=reply_text,
                    admin_display_name="ASKA",
                    wa_message_id=ai_result.get("wa_message_id"),
                    increment_unread=False,
                )

            ai_result["conversation_id"] = conv.get("id")
            ai_result["message_id"] = inbound_msg.get("id")
            ai_result["duplicate"] = False
            ai_result["bridge_key"] = bridge_key
            http_code = 200 if ai_result.get("ok") else 502
            return jsonify(ai_result), http_code

        conv = upsert_cc_conversation(wa_user_id=conversation_user_key, display_name=username)
        msg = save_cc_message(
            conversation_id=conv["id"],
            direction="inbound",
            message_text=message,
            wa_message_id=message_id,
            **media_meta,
        )

        if not msg.get("duplicate"):
            try:
                send_cc_telegram_notification(username, message)
            except Exception:
                pass

        return jsonify(
            {
                "ok": True,
                "route_mode": "manual",
                "is_active": True,
                "bridge_key": bridge_key,
                "conversation_id": conv.get("id"),
                "message_id": msg.get("id"),
                "duplicate": bool(msg.get("duplicate")),
            }
        )
    except Exception as exc:
        current_app.logger.exception("api_callcenter_inbound error")
        return jsonify({"error": str(exc)}), 500


@call_center_api_bp.route("/import-history", methods=["POST"])
def api_callcenter_import_history() -> Response:
    """Import WhatsApp history pushed by the Call Center bridge."""
    auth_error = _cc_bridge_auth_error()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    request_bridge_key = normalize_cc_bridge_key(data.get("bridge_key"))
    items = data.get("messages") or []
    if not isinstance(items, list):
        return jsonify({"error": "messages must be a list"}), 400
    if len(items) > 5000:
        return jsonify({"error": "messages limit exceeded"}), 413

    try:
        saved = 0
        duplicates = 0
        skipped = 0
        conversations: set[int] = set()

        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue

            raw_user_id = _normalize_wa_user_id(str(item.get("user_id") or ""))
            bridge_key = normalize_cc_bridge_key(item.get("bridge_key") or request_bridge_key)
            try:
                bridge_account = _resolve_bridge_account(bridge_key)
            except Exception:
                bridge_key = normalize_cc_bridge_key(None)
                bridge_account = _resolve_bridge_account(bridge_key)
            message = str(item.get("message") or "").strip()
            direction = str(item.get("direction") or "inbound").strip().lower()
            if not raw_user_id or direction not in {"inbound", "outbound"}:
                skipped += 1
                continue

            conversation_user_key = compose_cc_conversation_user_key(raw_user_id, bridge_key)
            if not conversation_user_key:
                skipped += 1
                continue

            media_payload = item.get("media") or {}
            media_meta = _save_inbound_media(media_payload, message_id=item.get("message_id") or None)
            if not message and (media_payload or media_meta):
                message = call_center_media_label(
                    media_meta.get("media_mime_type")
                    or (media_payload.get("mimetype") if isinstance(media_payload, dict) else None)
                )
            if not message:
                skipped += 1
                continue

            username = str(item.get("username") or raw_user_id).strip()[:120] or raw_user_id
            message_id = item.get("message_id") or None
            created_at = item.get("created_at") or item.get("timestamp") or None

            conv = upsert_cc_conversation(
                wa_user_id=conversation_user_key,
                display_name=username,
                last_message_at=created_at,
            )
            ensure_cc_wa_routing_contact(
                raw_user_id,
                display_name=username,
                route_mode=normalize_cc_route_mode(
                    bridge_account.get("default_route_mode") or "manual"
                ),
                bridge_key=bridge_key,
            )
            if not conv:
                skipped += 1
                continue

            msg = save_cc_message(
                conversation_id=conv["id"],
                direction=direction,
                message_text=message,
                admin_display_name="WhatsApp Import" if direction == "outbound" else None,
                wa_message_id=message_id,
                created_at=created_at,
                increment_unread=False,
                **media_meta,
            )
            conversations.add(conv["id"])
            if msg.get("duplicate"):
                duplicates += 1
            else:
                saved += 1

        return jsonify(
            {
                "ok": True,
                "saved": saved,
                "duplicates": duplicates,
                "skipped": skipped,
                "conversations": len(conversations),
            }
        )
    except Exception as exc:
        current_app.logger.exception("api_callcenter_import_history error")
        return jsonify({"error": str(exc)}), 500


@call_center_bp.route("/")
@role_required("admin")
def inbox() -> Response:
    """Main inbox view listing all conversations."""
    args = request.args
    page = max(1, int(args.get("page", 1)))
    raw_status = (args.get("status") or "").strip().lower()
    if raw_status in {"open", "closed", "unread"}:
        status_filter = raw_status
    elif raw_status == "all":
        status_filter = None
    else:
        status_filter = "unread"
    search = (args.get("search") or "").strip() or None
    raw_bridge_filter = (args.get("bridge") or "").strip()
    if not raw_bridge_filter:
        raw_bridge_filter = "main"
    bridge_filter, bridge_key = _normalize_bridge_filter(raw_bridge_filter)
    offset = (page - 1) * PAGE_SIZE

    conversations, total = fetch_cc_conversations(
        status_filter=status_filter,
        search=search,
        bridge_key=bridge_key,
        limit=PAGE_SIZE,
        offset=offset,
    )
    total_pages = max(1, ceil(total / PAGE_SIZE))
    bridge_accounts = _bridge_accounts()

    return render_template(
        "cc_inbox.html",
        conversations=conversations,
        total=total,
        page=page,
        total_pages=total_pages,
        status_filter=status_filter or "all",
        search=search or "",
        bridge_filter=bridge_filter,
        bridge_accounts=bridge_accounts,
    )


@call_center_bp.route("/stats")
@role_required("admin")
def stats() -> Response:
    """Call Center statistics dashboard."""
    now_jkt = _jakarta_now()
    period = (request.args.get("period") or "daily").strip().lower()
    if period not in {"daily", "monthly", "yearly", "all"}:
        period = "daily"

    selected_date = (request.args.get("date") or "").strip()
    selected_month = (request.args.get("month") or "").strip()
    selected_year = request.args.get("year", type=int)

    if period == "daily":
        try:
            datetime.strptime(selected_date, "%Y-%m-%d")
        except Exception:
            selected_date = now_jkt.strftime("%Y-%m-%d")
        selected_month = ""
        selected_year = None
    elif period == "monthly":
        try:
            datetime.strptime(selected_month, "%Y-%m")
        except Exception:
            selected_month = now_jkt.strftime("%Y-%m")
        selected_date = ""
        selected_year = None
    elif period == "yearly":
        if not selected_year or selected_year < 2000 or selected_year > (now_jkt.year + 1):
            selected_year = now_jkt.year
        selected_date = ""
        selected_month = ""
    else:
        selected_date = ""
        selected_month = ""
        selected_year = None

    raw_bridge_filter = (request.args.get("bridge") or "").strip()
    if not raw_bridge_filter:
        raw_bridge_filter = "all"
    bridge_filter, bridge_key = _normalize_bridge_filter(raw_bridge_filter)
    bridge_accounts = _bridge_accounts()

    stats_data = fetch_cc_statistics(
        period_mode=period,
        selected_date=selected_date or None,
        selected_month=selected_month or None,
        selected_year=selected_year,
        bridge_key=bridge_key,
    )

    # Pastikan kategori selalu tampil, walau nilainya 0.
    issue_defaults = ["Kependudukan", "Teknis", "Regulasi", "Lainnya"]
    issue_map = {
        str(item.get("issue_category") or ""): item
        for item in (stats_data.get("issue_stats") or [])
    }
    stats_data["issue_stats"] = [
        issue_map.get(
            name,
            {
                "issue_category": name,
                "total_messages": 0,
                "unique_numbers": 0,
                "active_contact_days": 0,
            },
        )
        for name in issue_defaults
    ]

    period_label = "Semua periode"
    if period == "daily":
        period_label = f"Harian ({selected_date})"
    elif period == "monthly":
        period_label = f"Bulanan ({selected_month})"
    elif period == "yearly":
        period_label = f"Tahunan ({selected_year})"

    year_options = list(range(now_jkt.year, 2019, -1))

    response = current_app.make_response(render_template(
        "cc_stats.html",
        stats_data=stats_data,
        period=period,
        period_label=period_label,
        selected_date=selected_date,
        selected_month=selected_month,
        selected_year=selected_year,
        bridge_filter=bridge_filter,
        bridge_accounts=bridge_accounts,
        year_options=year_options,
    ))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@call_center_bp.route("/thread/<int:conv_id>")
@role_required("admin")
def thread(conv_id: int) -> Response:
    """Conversation thread view."""
    page = request.args.get("page", default=1, type=int) or 1
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    raw_status = (request.args.get("status") or "").strip().lower()
    if raw_status in {"open", "closed", "unread"}:
        status_filter = raw_status
    elif raw_status == "all":
        status_filter = None
    else:
        status_filter = "unread"

    search = (request.args.get("search") or "").strip() or None
    raw_bridge_filter = (request.args.get("bridge") or "").strip()
    if not raw_bridge_filter:
        raw_bridge_filter = "main"
    bridge_filter, bridge_key = _normalize_bridge_filter(raw_bridge_filter)
    conv = fetch_cc_conversation(conv_id)
    if not conv:
        flash("Percakapan tidak ditemukan.", "danger")
        return redirect(url_for("call_center.inbox"))

    messages = fetch_cc_messages(conv_id, limit=500)
    # Status terbaca TIDAK diubah saat membuka thread.
    # unread_count hanya di-reset ketika admin mengirim balasan (lihat api_send).
    # mark_conversation_read(conv_id)  # DINONAKTIFKAN — aktifkan kembali jika diperlukan

    # Sidebar conversations
    conversations, total = fetch_cc_conversations(
        status_filter=status_filter,
        search=search,
        bridge_key=bridge_key,
        limit=PAGE_SIZE,
        offset=offset,
    )
    total_pages = max(1, ceil(total / PAGE_SIZE))
    bridge_accounts = _bridge_accounts()

    response = current_app.make_response(render_template(
        "cc_thread.html",
        conversation=conv,
        messages=messages,
        conversations=conversations,
        sidebar_page=page,
        sidebar_total_pages=total_pages,
        status_filter=status_filter or "all",
        search=search or "",
        bridge_filter=bridge_filter,
        bridge_accounts=bridge_accounts,
    ))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@call_center_bp.route("/media/<path:filename>")
@role_required("admin")
def media_file(filename: str) -> Response:
    """Serve stored WhatsApp media for authenticated dashboard admins."""
    target_path = resolve_call_center_media_path(filename)
    if not target_path or not target_path.is_file():
        abort(404)
    safe_name = target_path.relative_to(CC_MEDIA_ROOT.resolve()).as_posix()
    return send_from_directory(CC_MEDIA_ROOT, safe_name)


# ── API endpoints ─────────────────────────────────────────────────────────────

@call_center_bp.route("/api/send", methods=["POST"])
@role_required("admin")
def api_send() -> Response:
    """Send a reply to a WA user."""
    user = current_user() or {}
    media_payload = None

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        data = request.form
        uploaded_file = request.files.get("media")
        media_payload, upload_error = _media_payload_from_upload(uploaded_file)
        if upload_error:
            return jsonify({"error": upload_error}), 400
    else:
        data = request.get_json(silent=True) or {}
        media_payload = data.get("media") or None

    conv_id = data.get("conversation_id")
    message_text = (data.get("message") or "").strip()
    draft_id = data.get("draft_id")
    admin_user_id = user.get("id")

    if not conv_id or (not message_text and not media_payload and not draft_id):
        return jsonify({"error": "conversation_id and message/media required"}), 400

    # Keep admin identity on web UI only via admin_display_name.
    # Outbound WhatsApp message should not append admin signature.
    outbound_text = message_text

    conv = fetch_cc_conversation(int(conv_id))
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    media_meta = {}
    bridge_media = None
    media_from_upload = False
    if media_payload:
        media_meta, media_error = _save_outbound_media(media_payload)
        if not media_meta:
            return jsonify({
                "error": media_error or "File tidak didukung atau terlalu besar."
            }), 400

        bridge_media = _bridge_media_from_saved(media_meta)
        if not bridge_media:
            return jsonify({"error": "Gagal menyiapkan file untuk dikirim."}), 500
        media_from_upload = True
    elif draft_id and admin_user_id:
        try:
            draft = get_cc_message_draft(int(draft_id), int(admin_user_id))
        except Exception:
            draft = None
        if draft and draft.get("media_path"):
            media_meta = {
                "media_path": draft.get("media_path"),
                "media_mime_type": draft.get("media_mime_type"),
                "media_filename": draft.get("media_filename"),
                "media_size": draft.get("media_size"),
            }
            bridge_media = _bridge_media_from_saved(media_meta)
            if not bridge_media:
                return jsonify({"error": "Gagal menyiapkan file draft untuk dikirim."}), 500

    if not outbound_text and not bridge_media:
        return jsonify({"error": "Pesan atau lampiran wajib diisi."}), 400

    # Send via WA bridge HTTP API
    result = _send_via_bridge(
        conv.get("wa_user_id_raw") or conv["wa_user_id"],
        outbound_text,
        media=bridge_media,
        bridge_key=conv.get("bridge_key"),
    )
    if result.get("error"):
        if media_from_upload and media_meta.get("media_path"):
            target_path = resolve_call_center_media_path(media_meta.get("media_path"))
            if target_path and target_path.is_file():
                try:
                    target_path.unlink()
                except OSError:
                    pass
        return jsonify({"error": f"Gagal kirim: {result['error']}"}), 502

    # Save message to DB
    admin_name = user.get("full_name") or user.get("email") or "Admin"
    db_message_text = outbound_text or call_center_media_label(media_meta.get("media_mime_type"))
    msg = save_cc_message(
        conversation_id=int(conv_id),
        direction="outbound",
        message_text=db_message_text,
        admin_user_id=user.get("id"),
        admin_display_name=admin_name,
        wa_message_id=result.get("messageId"),
        **media_meta,
    )
    # Tandai percakapan sebagai terbaca setelah admin berhasil mengirim balasan.
    mark_conversation_read(int(conv_id))

    if draft_id:
        try:
            record_admin_action(
                user_id=user.get("id"),
                feature_key="call_center",
                action="SEND",
                target_type="CALL_CENTER_DRAFT",
                target_id=int(draft_id),
                target_name=f"Draft #{draft_id}",
            )
        except Exception:
            pass

    return jsonify({"ok": True, "message": msg})


@call_center_bp.route("/api/conversations")
@role_required("admin")
def api_conversations() -> Response:
    """JSON API for polling conversations."""
    status_filter = request.args.get("status") or None
    search = (request.args.get("search") or "").strip() or None
    bridge_filter, bridge_key = _normalize_bridge_filter(request.args.get("bridge"))
    conversations, total = fetch_cc_conversations(
        status_filter=status_filter,
        search=search,
        bridge_key=bridge_key,
        limit=50,
    )
    return jsonify({"conversations": conversations, "total": total, "bridge_filter": bridge_filter})


@call_center_bp.route("/api/messages/<int:conv_id>")
@role_required("admin")
def api_messages(conv_id: int) -> Response:
    """JSON API for polling messages."""
    after_id = request.args.get("after_id", type=int)
    messages = fetch_cc_messages(conv_id, limit=200, after_id=after_id)
    return jsonify({"messages": messages})


@call_center_bp.route("/api/message/<int:message_id>", methods=["POST", "PUT"])
@role_required("admin")
def api_message_detail(message_id: int) -> Response:
    """Edit an outbound message that was already sent."""
    return _handle_message_edit(message_id)


@call_center_bp.route("/edit-message", methods=["POST"])
@role_required("admin")
def message_edit() -> Response:
    """Edit endpoint outside /api for proxies that restrict API paths."""
    return _handle_message_edit_from_request()


@call_center_bp.route("/api/edit-message", methods=["POST"])
@role_required("admin")
def api_message_edit() -> Response:
    """FormData-compatible edit endpoint for production proxies."""
    return _handle_message_edit_from_request()


def _handle_message_edit_from_request() -> Response:
    data = request.form if request.form else (request.get_json(silent=True) or {})
    try:
        message_id = int(data.get("message_id") or 0)
    except (TypeError, ValueError):
        message_id = 0
    if not message_id:
        return jsonify({"error": "message_id wajib diisi."}), 400
    return _handle_message_edit(message_id, data=data)


def _handle_message_edit(message_id: int, data=None) -> Response:
    user = current_user() or {}
    admin_user_id = user.get("id")
    if not admin_user_id:
        return jsonify({"error": "Unauthorized"}), 401

    if data is None:
        data = request.form if request.form else (request.get_json(silent=True) or {})
    message_text = (data.get("message") or data.get("message_text") or "").strip()
    if not message_text:
        return jsonify({"error": "Pesan wajib diisi."}), 400

    message = fetch_cc_message(message_id)
    if not message:
        return jsonify({"error": "Pesan tidak ditemukan."}), 404
    if message.get("direction") != "outbound":
        return jsonify({"error": "Hanya pesan admin yang bisa diedit."}), 400
    if message_text == (message.get("message_text") or ""):
        return jsonify({"ok": True, "message": message, "wa_edit_applied": False})

    updated = update_cc_message_text(
        message_id=message_id,
        message_text=message_text,
        edited_by_admin_user_id=admin_user_id,
    )
    if not updated:
        return jsonify({"error": "Pesan tidak bisa diedit."}), 400

    wa_edit_applied = False
    wa_edit_warning = None
    wa_message_id = (message.get("wa_message_id") or "").strip()
    conv = fetch_cc_conversation(int(message.get("conversation_id") or 0)) if message.get("conversation_id") else None
    bridge_key = (conv or {}).get("bridge_key")
    if wa_message_id:
        result = _edit_via_bridge(wa_message_id, message_text, bridge_key=bridge_key)
        if result.get("error"):
            wa_edit_warning = f"Pesan dashboard sudah diedit, tapi WhatsApp belum berubah: {result['error']}"
        else:
            wa_edit_applied = bool(result.get("ok"))

    try:
        record_admin_action(
            user_id=admin_user_id,
            feature_key="call_center",
            action="UPDATE",
            target_type="CALL_CENTER_MESSAGE",
            target_id=message_id,
            target_name=f"Message #{message_id}",
        )
    except Exception:
        pass

    return jsonify(
        {
            "ok": True,
            "message": updated,
            "wa_edit_applied": wa_edit_applied,
            "wa_edit_warning": wa_edit_warning,
        }
    )


@call_center_bp.route("/api/drafts/<int:draft_id>/use", methods=["POST"])
@role_required("admin")
def api_draft_use(draft_id: int) -> Response:
    user = current_user() or {}
    try:
        record_admin_action(
            user_id=user.get("id"),
            feature_key="call_center",
            action="USE",
            target_type="CALL_CENTER_DRAFT",
            target_id=draft_id,
            target_name=f"Draft #{draft_id}",
        )
    except Exception:
        pass
    return jsonify({"ok": True})


@call_center_bp.route("/api/close/<int:conv_id>", methods=["POST"])
@role_required("admin")
def api_close(conv_id: int) -> Response:
    user = current_user() or {}
    close_conversation(conv_id)
    try:
        record_admin_action(
            user_id=user.get("id"),
            feature_key="call_center",
            action="CLOSE",
            target_type="CALL_CENTER_CONVERSATION",
            target_id=conv_id,
            target_name=f"Conversation #{conv_id}",
        )
    except Exception:
        pass
    return jsonify({"ok": True})


@call_center_bp.route("/api/reopen/<int:conv_id>", methods=["POST"])
@role_required("admin")
def api_reopen(conv_id: int) -> Response:
    user = current_user() or {}
    reopen_conversation(conv_id)
    try:
        record_admin_action(
            user_id=user.get("id"),
            feature_key="call_center",
            action="REOPEN",
            target_type="CALL_CENTER_CONVERSATION",
            target_id=conv_id,
            target_name=f"Conversation #{conv_id}",
        )
    except Exception:
        pass
    return jsonify({"ok": True})


@call_center_bp.route("/api/drafts", methods=["GET", "POST"])
@role_required("admin")
def api_drafts() -> Response:
    user = current_user() or {}
    admin_user_id = user.get("id")
    if not admin_user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        if request.method == "GET":
            raw_category = (request.args.get("category") or "").strip()
            category = raw_category if raw_category and raw_category.lower() != "all" else None
            drafts = list_cc_message_drafts(admin_user_id=admin_user_id, category=category)
            categories = list_cc_message_draft_categories(admin_user_id=admin_user_id)
            return jsonify({"drafts": drafts, "categories": categories})

        media_payload = None
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            data = request.form
            media_payload, upload_error = _media_payload_from_upload(request.files.get("media"))
            if upload_error:
                return jsonify({"error": upload_error}), 400
        else:
            data = request.get_json(silent=True) or {}
            media_payload = data.get("media") or None

        title = (data.get("title") or "").strip()
        category = (data.get("category") or "").strip() or "Umum"
        message_text = (data.get("message_text") or "").strip()
        media_meta = {}
        if media_payload:
            media_meta, media_error = _save_draft_media(media_payload)
            if not media_meta:
                return jsonify({
                    "error": media_error or "Lampiran draft tidak didukung atau terlalu besar."
                }), 400

        if not title:
            return jsonify({"error": "Judul draft wajib diisi."}), 400
        if not message_text and not media_meta:
            return jsonify({"error": "Isi draft atau lampiran wajib diisi."}), 400

        draft = create_cc_message_draft(
            admin_user_id=admin_user_id,
            title=title,
            category=category,
            message_text=message_text,
            **media_meta,
        )
        try:
            record_admin_action(
                user_id=admin_user_id,
                feature_key="call_center",
                action="CREATE",
                target_type="CALL_CENTER_DRAFT",
                target_id=draft.get("id"),
                target_name=title,
            )
        except Exception:
            pass
        return jsonify({"ok": True, "draft": draft})
    except Exception as exc:
        current_app.logger.exception("Call Center draft API error")
        return jsonify({"error": f"Gagal memproses draft: {exc}"}), 500


@call_center_bp.route("/api/drafts/<int:draft_id>", methods=["PUT", "DELETE"])
@role_required("admin")
def api_draft_detail(draft_id: int) -> Response:
    user = current_user() or {}
    admin_user_id = user.get("id")
    if not admin_user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        if request.method == "DELETE":
            deleted = delete_cc_message_draft(draft_id=draft_id, admin_user_id=admin_user_id)
            if not deleted:
                return jsonify({"error": "Draft tidak ditemukan."}), 404
            try:
                record_admin_action(
                    user_id=admin_user_id,
                    feature_key="call_center",
                    action="DELETE",
                    target_type="CALL_CENTER_DRAFT",
                    target_id=draft_id,
                    target_name=f"Draft #{draft_id}",
                )
            except Exception:
                pass
            return jsonify({"ok": True})

        existing = get_cc_message_draft(draft_id=draft_id, admin_user_id=admin_user_id)
        if not existing:
            return jsonify({"error": "Draft tidak ditemukan."}), 404

        media_payload = None
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            data = request.form
            media_payload, upload_error = _media_payload_from_upload(request.files.get("media"))
            if upload_error:
                return jsonify({"error": upload_error}), 400
        else:
            data = request.get_json(silent=True) or {}
            media_payload = data.get("media") or None

        title = (data.get("title") or "").strip()
        category = (data.get("category") or "").strip() or "Umum"
        message_text = (data.get("message_text") or "").strip()
        remove_media = str(data.get("remove_media") or "").strip().lower() in {"1", "true", "yes", "on"}
        media_meta: dict = {}
        update_media = False
        if media_payload:
            media_meta, media_error = _save_draft_media(media_payload)
            if not media_meta:
                return jsonify({
                    "error": media_error or "Lampiran draft tidak didukung atau terlalu besar."
                }), 400
            update_media = True
        elif remove_media:
            media_meta = {
                "media_path": None,
                "media_mime_type": None,
                "media_filename": None,
                "media_size": None,
            }
            update_media = True

        if not title:
            return jsonify({"error": "Judul draft wajib diisi."}), 400
        if not message_text and not media_meta and not existing.get("media_path"):
            return jsonify({"error": "Isi draft atau lampiran wajib diisi."}), 400
        if not message_text and remove_media and not media_payload:
            return jsonify({"error": "Isi draft atau lampiran wajib diisi."}), 400

        updated = update_cc_message_draft(
            draft_id=draft_id,
            admin_user_id=admin_user_id,
            title=title,
            category=category,
            message_text=message_text,
            update_media=update_media,
            **media_meta,
        )
        if not updated:
            return jsonify({"error": "Draft tidak ditemukan."}), 404
        try:
            record_admin_action(
                user_id=admin_user_id,
                feature_key="call_center",
                action="UPDATE",
                target_type="CALL_CENTER_DRAFT",
                target_id=draft_id,
                target_name=title,
            )
        except Exception:
            pass
        return jsonify({"ok": True, "draft": updated})
    except Exception as exc:
        current_app.logger.exception("Call Center draft detail API error")
        return jsonify({"error": f"Gagal memproses draft: {exc}"}), 500


@call_center_bp.route("/api/drafts/<int:draft_id>/pin", methods=["POST"])
@role_required("admin")
def api_draft_pin(draft_id: int) -> Response:
    user = current_user() or {}
    admin_user_id = user.get("id")
    if not admin_user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        updated = toggle_cc_message_draft_pin(draft_id=draft_id, admin_user_id=admin_user_id)
        if not updated:
            return jsonify({"error": "Draft tidak ditemukan."}), 404

        action = "PIN" if updated.get("pinned") else "UNPIN"
        try:
            record_admin_action(
                user_id=admin_user_id,
                feature_key="call_center",
                action=action,
                target_type="CALL_CENTER_DRAFT",
                target_id=draft_id,
                target_name=updated.get("title") or f"Draft #{draft_id}",
            )
        except Exception:
            pass
        return jsonify({"ok": True, "draft": updated})
    except Exception as exc:
        current_app.logger.exception("Call Center draft pin API error")
        return jsonify({"error": f"Gagal mengubah pin draft: {exc}"}), 500


# ── Media Manager ─────────────────────────────────────────────────────────────

@call_center_bp.route("/media-manager")
@role_required("admin")
def media_manager() -> Response:
    """Media Manager page — list and delete stored CC media files."""
    return render_template("cc_media_manager.html")


def _build_media_list(sort_by: str = "newest", type_filter: str = "all") -> dict:
    """Core logic for listing media files. Extracted for testability."""
    _SORT_OPTIONS = {"newest", "oldest", "largest", "smallest"}
    _TYPE_OPTIONS = {"all", "image", "video", "audio", "document"}
    if sort_by not in _SORT_OPTIONS:
        sort_by = "newest"
    if type_filter not in _TYPE_OPTIONS:
        type_filter = "all"

    media_root = CC_MEDIA_ROOT.resolve()
    items: list[dict] = []

    if media_root.is_dir():
        for file_path in media_root.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                stat = file_path.stat()
            except OSError:
                continue

            relative_path = file_path.relative_to(media_root).as_posix()
            mime_type, _ = mimetypes.guess_type(file_path.name)
            if not mime_type:
                mime_type = "application/octet-stream"

            items.append({
                "path": relative_path,
                "filename": file_path.name,
                "size": stat.st_size,
                "mime_type": mime_type,
                "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

    # Apply type filter
    if type_filter != "all":
        def _matches_type(item: dict) -> bool:
            mt = item["mime_type"]
            if type_filter == "image":
                return mt.startswith("image/")
            if type_filter == "video":
                return mt.startswith("video/")
            if type_filter == "audio":
                return mt.startswith("audio/")
            if type_filter == "document":
                return not (mt.startswith("image/") or mt.startswith("video/") or mt.startswith("audio/"))
            return True
        items = [i for i in items if _matches_type(i)]

    # Sort
    if sort_by == "newest":
        items.sort(key=lambda x: x["uploaded_at"], reverse=True)
    elif sort_by == "oldest":
        items.sort(key=lambda x: x["uploaded_at"])
    elif sort_by == "largest":
        items.sort(key=lambda x: x["size"], reverse=True)
    elif sort_by == "smallest":
        items.sort(key=lambda x: x["size"])

    total_size = sum(i["size"] for i in items)
    return {"items": items, "total_size": total_size, "count": len(items)}


@call_center_bp.route("/api/media-list")
@role_required("admin")
def api_media_list() -> Response:
    """Return JSON list of all files in CC_MEDIA_ROOT with metadata.

    Query params:
      sort  — newest (default) | oldest | largest | smallest
      type  — all (default) | image | video | audio | document
    """
    sort_by = (request.args.get("sort") or "newest").strip().lower()
    type_filter = (request.args.get("type") or "all").strip().lower()
    return jsonify(_build_media_list(sort_by=sort_by, type_filter=type_filter))


def _delete_media_files(raw_paths: list) -> dict:
    """Core logic for deleting media files. Extracted for testability."""
    deleted: list[str] = []
    failed: list[dict] = []
    valid_paths: list[str] = []

    for raw_path in raw_paths:
        if not isinstance(raw_path, str):
            failed.append({"path": str(raw_path), "reason": "invalid path type"})
            continue

        target_path = resolve_call_center_media_path(raw_path)
        if not target_path:
            failed.append({"path": raw_path, "reason": "path traversal rejected"})
            continue

        if not target_path.exists():
            # Already gone — still clean up DB refs
            valid_paths.append(raw_path)
            deleted.append(raw_path)
            continue

        try:
            target_path.unlink()
            deleted.append(raw_path)
            valid_paths.append(raw_path)
        except OSError as exc:
            failed.append({"path": raw_path, "reason": str(exc)})

    # Clear DB references for all successfully deleted (or already-missing) paths
    db_updated = 0
    if valid_paths:
        try:
            db_updated = clear_cc_media_db_refs(valid_paths)
        except Exception:
            pass

    return {"ok": True, "deleted": deleted, "failed": failed, "db_updated": db_updated}


@call_center_bp.route("/api/media-delete", methods=["POST"])
@role_required("admin")
def api_media_delete() -> Response:
    """Delete one or more media files from disk and clear DB references.

    Request body (JSON): {"paths": ["2025/05/21/abc.jpg", ...]}
    """
    data = request.get_json(silent=True) or {}
    raw_paths = data.get("paths") or []
    if not isinstance(raw_paths, list) or not raw_paths:
        return jsonify({"error": "paths must be a non-empty list"}), 400
    return jsonify(_delete_media_files(raw_paths))


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
    actor = current_user() or {}
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        selected_bridge_key = normalize_cc_bridge_key(request.form.get("selected_bridge_key") or "main")

        if action == "save_wa_route":
            wa_user_id = _normalize_wa_user_id(request.form.get("wa_user_id") or "")
            route_bridge_key = normalize_cc_bridge_key(
                request.form.get("selected_bridge_key") or selected_bridge_key
            )
            display_name = (request.form.get("display_name") or "").strip() or None
            route_mode = (request.form.get("route_mode") or "manual").strip().lower()
            is_active = _to_bool_flag(request.form.get("is_active"))
            notes = (request.form.get("notes") or "").strip() or None

            try:
                row = save_cc_wa_routing(
                    wa_user_id,
                    bridge_key=route_bridge_key,
                    display_name=display_name,
                    route_mode=route_mode,
                    is_active=is_active,
                    notes=notes,
                    updated_by=actor.get("id"),
                )
                try:
                    record_admin_action(
                        user_id=actor.get("id"),
                        feature_key="call_center",
                        action="UPDATE",
                        target_type="CALL_CENTER_WA_ROUTING",
                        target_name=f"WA {row.get('wa_user_id')}",
                        metadata={
                            "route_mode": row.get("route_mode"),
                            "is_active": row.get("is_active"),
                        },
                    )
                except Exception:
                    pass
                flash(
                    f"Routing WA +{row.get('wa_user_id')} [{route_bridge_key}] disimpan ({row.get('route_mode')}, "
                    f"{'aktif' if row.get('is_active') else 'nonaktif'}).",
                    "success",
                )
            except ValueError as exc:
                flash(str(exc), "danger")
            except Exception as exc:
                flash(f"Gagal menyimpan routing WA: {exc}", "danger")

        elif action == "delete_wa_route":
            wa_user_id = _normalize_wa_user_id(request.form.get("wa_user_id") or "")
            route_bridge_key = normalize_cc_bridge_key(
                request.form.get("selected_bridge_key") or selected_bridge_key
            )
            if not wa_user_id:
                flash("Nomor WA tidak valid.", "warning")
            elif delete_cc_wa_routing(wa_user_id, bridge_key=route_bridge_key):
                try:
                    record_admin_action(
                        user_id=actor.get("id"),
                        feature_key="call_center",
                        action="DELETE",
                        target_type="CALL_CENTER_WA_ROUTING",
                        target_name=f"WA {wa_user_id} [{route_bridge_key}]",
                    )
                except Exception:
                    pass
                flash(f"Routing WA +{wa_user_id} [{route_bridge_key}] dihapus.", "success")
            else:
                flash("Routing WA tidak ditemukan.", "warning")

        elif action == "save_bridge_account":
            raw_bridge_key = (request.form.get("bridge_key") or "").strip()
            if not raw_bridge_key:
                flash("Bridge key wajib diisi.", "warning")
                return _settings_wa_redirect(selected_bridge_key)
            bridge_key = normalize_cc_bridge_key(raw_bridge_key)
            display_name = (request.form.get("display_name") or "").strip() or None
            wa_number_hint = _normalize_wa_user_id(request.form.get("wa_number_hint") or "") or None
            default_route_mode = normalize_cc_route_mode(
                request.form.get("default_route_mode") or "manual"
            )
            client_id = (request.form.get("client_id") or "").strip() or None
            internal_url = (request.form.get("internal_url") or "").strip() or None
            session_path = (request.form.get("session_path") or "").strip() or None
            status_path = (request.form.get("status_path") or "").strip() or None
            pid_path = (request.form.get("pid_path") or "").strip() or None
            log_path = (request.form.get("log_path") or "").strip() or None
            is_active = _to_bool_flag(request.form.get("is_active"))
            try:
                http_port = int(request.form.get("http_port") or 0)
            except Exception:
                http_port = 0

            try:
                row = save_cc_wa_bridge_account(
                    bridge_key=bridge_key,
                    display_name=display_name,
                    wa_number_hint=wa_number_hint,
                    default_route_mode=default_route_mode,
                    client_id=client_id,
                    http_port=http_port,
                    session_path=session_path,
                    status_path=status_path,
                    pid_path=pid_path,
                    log_path=log_path,
                    internal_url=internal_url,
                    is_active=is_active,
                    updated_by=actor.get("id"),
                )
                flash(f"Akun bridge '{row.get('display_name')}' disimpan.", "success")
            except Exception as exc:
                flash(f"Gagal menyimpan akun bridge: {exc}", "danger")

        elif action == "delete_bridge_account":
            bridge_key = normalize_cc_bridge_key(request.form.get("bridge_key"))
            if delete_cc_wa_bridge_account(bridge_key):
                flash(f"Akun bridge '{bridge_key}' dihapus.", "success")
            else:
                flash("Akun bridge tidak bisa dihapus (main/protected atau tidak ditemukan).", "warning")

        elif action in {"start_bridge_account", "stop_bridge_account"}:
            bridge_key = normalize_cc_bridge_key(request.form.get("bridge_key"))
            try:
                account = _resolve_bridge_account(bridge_key)
                if action == "start_bridge_account":
                    reset_session = _to_bool_flag(request.form.get("reset_session"))
                    _restart_cc_bridge(account, reset_session=reset_session)
                    flash(f"Bridge '{bridge_key}' dijalankan ulang.", "success")
                else:
                    _stop_existing_bridge(account)
                    flash(f"Bridge '{bridge_key}' dihentikan.", "success")
            except Exception as exc:
                flash(f"Aksi bridge '{bridge_key}' gagal: {exc}", "danger")

        elif action == "save_public_whatsapp_cta":
            wa_number = _normalize_wa_user_id(request.form.get("public_wa_number") or "")
            opening_message = (request.form.get("public_opening_message") or "").strip()
            if not wa_number:
                flash("Nomor WhatsApp tombol login wajib diisi.", "warning")
            else:
                row = upsert_cc_public_whatsapp_cta_settings(
                    wa_number=wa_number,
                    opening_message=opening_message,
                    updated_by=actor.get("id"),
                )
                try:
                    record_admin_action(
                        user_id=actor.get("id"),
                        feature_key="call_center",
                        action="UPDATE",
                        target_type="CALL_CENTER_PUBLIC_WHATSAPP_CTA",
                        target_name=f"WA {row.get('wa_number')}",
                    )
                except Exception:
                    pass
                flash("Tombol WhatsApp login ASKA disimpan.", "success")

        elif action == "reset_public_whatsapp_cta":
            if delete_cc_public_whatsapp_cta_settings():
                flash("Setting tombol WhatsApp login direset ke fallback bridge/env.", "success")
            else:
                flash("Setting tombol WhatsApp login belum pernah disimpan.", "info")

        return _settings_wa_redirect(selected_bridge_key)

    ensure_default_cc_wa_bridge_account(updated_by=actor.get("id"))
    bridge_accounts = list_cc_wa_bridge_accounts(include_inactive=True)
    selected_bridge_key = normalize_cc_bridge_key(request.args.get("bridge_key") or "main")
    selected_bridge = get_cc_wa_bridge_account(selected_bridge_key) or get_default_cc_wa_bridge_account()
    selected_bridge_key = normalize_cc_bridge_key(selected_bridge.get("bridge_key"))
    bridge_status = _load_cc_bridge_status(bridge_key=selected_bridge_key)
    bridge_statuses = [_load_cc_bridge_status(bridge_key=acc.get("bridge_key")) for acc in bridge_accounts]
    bridge_status_map = {
        normalize_cc_bridge_key(item.get("bridgeKey")): item
        for item in bridge_statuses
    }
    route_search = (request.args.get("q") or "").strip()
    route_bridge_filter, route_bridge_key = _normalize_bridge_filter(request.args.get("route_bridge"))
    route_page = request.args.get("route_page", type=int) or 1
    route_page = max(1, route_page)
    route_page_size = 10
    route_offset = (route_page - 1) * route_page_size

    route_rows, route_total = list_cc_wa_routing(
        search=route_search,
        limit=route_page_size,
        offset=route_offset,
        bridge_key=route_bridge_key,
    )
    route_total_pages = max(1, ceil(route_total / route_page_size)) if route_total else 1

    if route_page > route_total_pages:
        route_page = route_total_pages
        route_offset = (route_page - 1) * route_page_size
        route_rows, route_total = list_cc_wa_routing(
            search=route_search,
            limit=route_page_size,
            offset=route_offset,
            bridge_key=route_bridge_key,
        )

    route_summary = summarize_cc_wa_routing(bridge_key=route_bridge_key)
    public_whatsapp_cta = fetch_cc_public_whatsapp_cta_settings()
    fallback_public_number = (
        bridge_status.get("whatsappNumber")
        or selected_bridge.get("wa_number_hint")
        or _project_env_value("ASKA_WHATSAPP_URL", "082143646463")
    )
    public_whatsapp_number = public_whatsapp_cta.get("wa_number") or _normalize_wa_user_id(fallback_public_number)
    public_whatsapp_message = (
        public_whatsapp_cta.get("opening_message")
        or CC_PUBLIC_WHATSAPP_DEFAULT_MESSAGE
    )
    public_whatsapp_preview_url = _format_public_whatsapp_url(
        public_whatsapp_number,
        public_whatsapp_message,
    )
    return render_template(
        "cc_settings_wa.html",
        bridge_status=bridge_status,
        bridge_statuses=bridge_statuses,
        bridge_status_map=bridge_status_map,
        bridge_accounts=bridge_accounts,
        selected_bridge=selected_bridge,
        selected_bridge_key=selected_bridge_key,
        route_rows=route_rows,
        route_summary=route_summary,
        route_search=route_search,
        route_bridge_filter=route_bridge_filter,
        route_page=route_page,
        route_total=route_total,
        route_total_pages=route_total_pages,
        route_page_size=route_page_size,
        public_whatsapp_cta=public_whatsapp_cta,
        public_whatsapp_number=public_whatsapp_number,
        public_whatsapp_message=public_whatsapp_message,
        public_whatsapp_preview_url=public_whatsapp_preview_url,
    )


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
            try:
                record_admin_action(
                    user_id=actor.get("id"),
                    feature_key="call_center",
                    action="UPDATE",
                    target_type="CALL_CENTER_TELEGRAM_SETTINGS",
                    target_name="Telegram Bot Token",
                )
            except Exception:
                pass
            flash("Token bot Telegram Call Center disimpan.", "success")

        elif action == "delete_group":
            gid = request.form.get("group_id") or ""
            if gid.isdigit() and delete_cc_telegram_group(int(gid)):
                try:
                    record_admin_action(
                        user_id=actor.get("id"),
                        feature_key="call_center",
                        action="DELETE",
                        target_type="CALL_CENTER_TELEGRAM_GROUP",
                        target_id=int(gid),
                        target_name=f"Telegram Group #{gid}",
                    )
                except Exception:
                    pass
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
                try:
                    record_admin_action(
                        user_id=actor.get("id"),
                        feature_key="call_center",
                        action="CREATE",
                        target_type="CALL_CENTER_TELEGRAM_ADMIN",
                        target_name="Call Center Telegram Admins",
                        metadata={"count": saved},
                    )
                except Exception:
                    pass
                flash(f"{saved} admin Telegram Call Center disimpan.", "success")
            for err in errors:
                flash(err, "warning")

        elif action == "delete_admin":
            mapping_id = (request.form.get("mapping_id") or "").strip()
            if mapping_id.isdigit():
                deleted = delete_telegram_admin_account(int(mapping_id))
                if deleted:
                    try:
                        record_admin_action(
                            user_id=actor.get("id"),
                            feature_key="call_center",
                            action="DELETE",
                            target_type="CALL_CENTER_TELEGRAM_ADMIN",
                            target_id=int(mapping_id),
                            target_name=f"Telegram Admin #{mapping_id}",
                        )
                    except Exception:
                        pass
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
    raw_bridge_key = (request.args.get("bridge_key") or "").strip()
    if raw_bridge_key:
        bridge_key = normalize_cc_bridge_key(raw_bridge_key)
        try:
            return jsonify(_load_cc_bridge_status(bridge_key=bridge_key))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 404
    return jsonify(_load_cc_bridge_status())


@call_center_bp.route("/settings/generate-qr", methods=["POST"])
@role_required("admin")
def generate_qr() -> Response:
    payload = request.get_json(silent=True) or request.form
    bridge_key = normalize_cc_bridge_key(payload.get("bridge_key") or "main")
    account = _resolve_bridge_account(bridge_key)
    try:
        runtime = _restart_cc_bridge(account, reset_session=True)
        msg = f"Bridge '{bridge_key}' direstart. Tunggu 5-15 detik sampai QR muncul."
        if request.is_json:
            return jsonify({"success": True, "message": msg, "runtime": runtime})
        flash(msg, "success")
    except Exception as exc:
        msg = f"Gagal generate QR: {exc}"
        if request.is_json:
            return jsonify({"success": False, "message": msg}), 500
        flash(msg, "danger")
    return _settings_wa_redirect(bridge_key)


@call_center_bp.route("/settings/sync-history", methods=["POST"])
@role_required("admin")
def sync_history() -> Response:
    payload = request.get_json(silent=True) or request.form
    bridge_key = normalize_cc_bridge_key(payload.get("bridge_key") or "main")
    try:
        chat_limit = int(payload.get("chat_limit") or payload.get("chatLimit") or 25)
    except Exception:
        chat_limit = 25
    try:
        limit_per_chat = int(payload.get("limit_per_chat") or payload.get("limitPerChat") or 50)
    except Exception:
        limit_per_chat = 50

    chat_limit = max(1, min(chat_limit, 200))
    limit_per_chat = max(1, min(limit_per_chat, 500))

    result = _sync_history_via_bridge(
        chat_limit=chat_limit,
        limit_per_chat=limit_per_chat,
        bridge_key=bridge_key,
    )
    if result.get("error"):
        msg = f"Gagal sync histori: {result['error']}"
        if request.is_json:
            return jsonify({"success": False, "message": msg}), 502
        flash(msg, "danger")
        return _settings_wa_redirect(bridge_key)

    msg = (
        "Sync histori selesai: "
        f"{result.get('saved', 0)} pesan baru, "
        f"{result.get('duplicates', 0)} duplikat, "
        f"{result.get('skipped', 0)} dilewati."
    )
    if request.is_json:
        return jsonify({"success": True, "message": msg, "result": result})
    flash(msg, "success")
    return _settings_wa_redirect(bridge_key)
