from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import socket
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from flask import has_request_context, request

from utils import current_jakarta_time, to_jakarta

from .db_access import get_cursor
from .queries import (
    fetch_telegram_notification_settings,
    list_telegram_notification_groups,
)


def _resolve_bot_token() -> Optional[str]:
    settings = fetch_telegram_notification_settings() or {}
    token = (settings.get("bot_token") or "").strip()
    if not token:
        token = (os.getenv("TELEGRAM_NOTIF_BOT_TOKEN") or "").strip()
    return token or None


def _normalize_base_url(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.endswith("/"):
        raw = raw[:-1]
    return raw


def _resolve_local_lan_ip() -> str:
    """Best-effort local LAN IP discovery for links opened from mobile devices."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 80))
            ip = str(sock.getsockname()[0] or "").strip()
    except Exception:
        return ""
    return ip


def _prefer_lan_base_url(value: Optional[str]) -> str:
    clean = _normalize_base_url(value)
    if not clean:
        return ""

    parsed = urllib.parse.urlsplit(clean)
    hostname = (parsed.hostname or "").strip()
    if not hostname:
        return clean

    should_swap = hostname == "localhost" or hostname.startswith("127.")
    if not should_swap:
        try:
            host_ip = ipaddress.ip_address(hostname)
            should_swap = isinstance(
                host_ip, ipaddress.IPv4Address
            ) and host_ip in ipaddress.ip_network("172.16.0.0/12")
        except ValueError:
            should_swap = False

    if not should_swap:
        return clean

    lan_ip = _resolve_local_lan_ip()
    if not lan_ip:
        return clean
    try:
        ipaddress.ip_address(lan_ip)
    except ValueError:
        return clean

    netloc = lan_ip if parsed.port is None else f"{lan_ip}:{parsed.port}"
    return urllib.parse.urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )


def _dashboard_base_url() -> str:
    candidates = [
        _normalize_base_url(os.getenv("DASHBOARD_PUBLIC_BASE_URL")),
        _normalize_base_url(os.getenv("DASHBOARD_BASE_URL")),
    ]
    for item in candidates:
        if item:
            return item
    if has_request_context():
        return _prefer_lan_base_url(request.url_root)
    return ""


def _list_admin_recipients() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (
                COALESCE(
                    tu.telegram_user_id::text,
                    LOWER(TRIM(ta.telegram_username))
                )
            )
                ta.telegram_username,
                tu.telegram_user_id
            FROM telegram_admin_accounts ta
            JOIN dashboard_users u ON u.id = ta.dashboard_user_id AND u.role = 'admin'
            LEFT JOIN telegram_users tu ON LOWER(tu.username) = LOWER(ta.telegram_username)
            WHERE ta.notification_scope = %s
            ORDER BY
                COALESCE(
                    tu.telegram_user_id::text,
                    LOWER(TRIM(ta.telegram_username))
                ),
                LOWER(ta.telegram_username) ASC
            """,
            ("default",),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def _ensure_guestbook_delivery_schema() -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS telegram_guestbook_delivery_messages (
                transaction_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (transaction_id, chat_id)
            )
            """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tg_guestbook_delivery_chat
            ON telegram_guestbook_delivery_messages (chat_id)
            """)


def upsert_guestbook_delivery_message(
    *,
    transaction_id: int,
    chat_id: int,
    message_id: int,
) -> None:
    if not transaction_id or not chat_id or not message_id:
        return
    _ensure_guestbook_delivery_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO telegram_guestbook_delivery_messages (
                transaction_id,
                chat_id,
                message_id
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (transaction_id, chat_id) DO UPDATE
            SET message_id = EXCLUDED.message_id,
                updated_at = NOW()
            """,
            (int(transaction_id), int(chat_id), int(message_id)),
        )


def list_guestbook_delivery_messages(*, transaction_id: int) -> List[Dict[str, int]]:
    if not transaction_id:
        return []
    _ensure_guestbook_delivery_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT transaction_id, chat_id, message_id
            FROM telegram_guestbook_delivery_messages
            WHERE transaction_id = %s
            ORDER BY chat_id ASC
            """,
            (int(transaction_id),),
        )
        rows = cur.fetchall() or []
    output: list[dict] = []
    for row in rows:
        data = dict(row)
        try:
            output.append(
                {
                    "transaction_id": int(data.get("transaction_id")),
                    "chat_id": int(data.get("chat_id")),
                    "message_id": int(data.get("message_id")),
                }
            )
        except (TypeError, ValueError):
            continue
    return output


def delete_guestbook_delivery_message(*, transaction_id: int, chat_id: int) -> None:
    if not transaction_id or not chat_id:
        return
    _ensure_guestbook_delivery_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM telegram_guestbook_delivery_messages
            WHERE transaction_id = %s AND chat_id = %s
            """,
            (int(transaction_id), int(chat_id)),
        )


def _send_telegram_message_with_meta(
    bot_token: str,
    chat_id: int,
    text: str,
    *,
    reply_markup: Optional[dict] = None,
) -> tuple[bool, Optional[int]]:
    if not bot_token or not chat_id or not text:
        return False, None
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    payload = urllib.parse.urlencode(data)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:  # nosec - external API call
        response_body = resp.read()
        if not (200 <= resp.status < 300):
            return False, None
    message_id = None
    try:
        parsed = json.loads(response_body.decode("utf-8")) if response_body else {}
        if isinstance(parsed, dict) and parsed.get("ok") is False:
            return False, None
        result = parsed.get("result") if isinstance(parsed, dict) else None
        if isinstance(result, dict) and result.get("message_id") is not None:
            message_id = int(result.get("message_id"))
    except Exception:
        message_id = None
    return True, message_id


def _send_telegram_message(
    bot_token: str,
    chat_id: int,
    text: str,
    *,
    reply_markup: Optional[dict] = None,
) -> bool:
    delivered, _ = _send_telegram_message_with_meta(
        bot_token,
        chat_id,
        text,
        reply_markup=reply_markup,
    )
    return delivered


def _resolve_local_upload_photo_path(photo_path: Optional[str]) -> Optional[Path]:
    raw = str(photo_path or "").strip()
    if not raw:
        return None

    project_root = Path(__file__).resolve().parents[1]
    upload_root = (project_root / "uploads").resolve()
    normalized = raw.replace("\\", "/")

    if normalized.startswith("/"):
        candidate = Path(normalized).resolve()
    elif "uploads/" in normalized:
        relative = normalized.split("uploads/", 1)[1].lstrip("/")
        candidate = (upload_root / relative).resolve()
    else:
        candidate = (project_root / normalized.lstrip("/")).resolve()

    try:
        candidate.relative_to(upload_root)
    except ValueError:
        return None

    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _encode_multipart_form(
    *,
    fields: Dict[str, str],
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = f"codex-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode(
                "utf-8"
            )
        )

    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def _send_telegram_photo(
    bot_token: str,
    chat_id: int,
    photo_path: str,
    *,
    caption: Optional[str] = None,
    reply_markup: Optional[dict] = None,
) -> bool:
    delivered, _ = _send_telegram_photo_with_meta(
        bot_token,
        chat_id,
        photo_path,
        caption=caption,
        reply_markup=reply_markup,
    )
    return delivered


def _send_telegram_photo_with_meta(
    bot_token: str,
    chat_id: int,
    photo_path: str,
    *,
    caption: Optional[str] = None,
    reply_markup: Optional[dict] = None,
) -> tuple[bool, Optional[int]]:
    local_photo_path = _resolve_local_upload_photo_path(photo_path)
    if not bot_token or not chat_id or not local_photo_path:
        return False, None

    mime_type, _ = mimetypes.guess_type(local_photo_path.name)
    safe_mime_type = mime_type or "application/octet-stream"
    with local_photo_path.open("rb") as handle:
        photo_bytes = handle.read()

    fields: Dict[str, str] = {"chat_id": str(chat_id)}
    clean_caption = str(caption or "").strip()
    if clean_caption:
        fields["caption"] = clean_caption
    if reply_markup:
        fields["reply_markup"] = json.dumps(reply_markup)

    payload, boundary = _encode_multipart_form(
        fields=fields,
        file_field="photo",
        filename=local_photo_path.name,
        file_bytes=photo_bytes,
        content_type=safe_mime_type,
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec - external API call
        response_body = resp.read()
        if not (200 <= resp.status < 300):
            return False, None
    message_id = None
    try:
        parsed = json.loads(response_body.decode("utf-8")) if response_body else {}
        if isinstance(parsed, dict) and parsed.get("ok") is False:
            return False, None
        result = parsed.get("result") if isinstance(parsed, dict) else None
        if isinstance(result, dict) and result.get("message_id") is not None:
            message_id = int(result.get("message_id"))
    except Exception:
        message_id = None
    return True, message_id


def _broadcast_notification(
    *,
    text: str,
    reply_markup: Optional[dict] = None,
    exclude_chat_ids: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    token = _resolve_bot_token()
    if not token:
        return {"sent": 0, "group_sent": 0, "skipped": "token_missing"}

    recipients = _list_admin_recipients()
    groups = list_telegram_notification_groups()

    sent = 0
    missing: List[str] = []
    for recipient in recipients:
        telegram_user_id = recipient.get("telegram_user_id")
        if not telegram_user_id:
            missing.append(recipient.get("telegram_username") or "")
            continue
        target_chat_id = int(telegram_user_id)
        if exclude_chat_ids and target_chat_id in exclude_chat_ids:
            continue
        try:
            if _send_telegram_message(
                token,
                target_chat_id,
                text,
                reply_markup=reply_markup,
            ):
                sent += 1
        except Exception:
            continue

    group_sent = 0
    for group in groups:
        chat_id = group.get("chat_id")
        if not chat_id:
            continue
        target_chat_id = int(chat_id)
        if exclude_chat_ids and target_chat_id in exclude_chat_ids:
            continue
        try:
            if _send_telegram_message(
                token,
                target_chat_id,
                text,
                reply_markup=reply_markup,
            ):
                group_sent += 1
        except Exception:
            continue

    return {
        "sent": sent,
        "group_sent": group_sent,
        "missing_usernames": [name for name in missing if name],
        "total_admins": len(recipients),
        "total_groups": len(groups),
    }


def notify_hospitality_verified(
    *,
    assessment_id: int,
    school_name: Optional[str],
    staff_name: Optional[str],
    transaction_id: Optional[int] = None,
) -> Dict[str, Any]:
    lines = [
        "Hospitality terverifikasi",
        f"Assessment ID: {assessment_id}",
        f"Sekolah: {school_name or '-'}",
        f"Staff: {staff_name or '-'}",
    ]
    if transaction_id:
        lines.append(f"Buku Tamu ID: {transaction_id}")
    time_label = _time_label()
    if time_label:
        lines.append(f"Waktu: {time_label}")
    return _broadcast_notification(text="\\n".join(lines))


def notify_verification_status_update(
    *,
    user_id: int,
    full_name: Optional[str],
    status_label: str,
    actor_name: Optional[str],
    actor_username: Optional[str],
    exclude_chat_ids: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    actor_display = "-"
    if actor_name and actor_username:
        actor_display = f"{actor_name} (@{actor_username})"
    elif actor_name:
        actor_display = actor_name
    elif actor_username:
        actor_display = f"@{actor_username}"

    timestamp = to_jakarta(current_jakarta_time())
    time_label = timestamp.strftime("%d %b %Y, %H:%M") if timestamp else ""

    lines = [
        "Update verifikasi akun",
        f"ID: {user_id}",
        f"Nama: {full_name or '-'}",
        f"Status: {status_label}",
        f"Diverifikasi oleh: {actor_display}",
    ]
    if time_label:
        lines.append(f"Waktu: {time_label}")
    return _broadcast_notification(
        text="\n".join(lines),
        exclude_chat_ids=exclude_chat_ids,
    )


def _normalize_guestbook_photo_links(
    *,
    photo_links: Optional[List[Dict[str, str]]] = None,
    photo_url: Optional[str] = None,
    previous_photo_url: Optional[str] = None,
) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    candidates: list[dict] = []
    if photo_links:
        candidates.extend(photo_links)
    else:
        if photo_url:
            candidates.append({"text": "Foto Transaksi", "url": photo_url})
        if previous_photo_url:
            candidates.append({"text": "Foto Sebelumnya", "url": previous_photo_url})

    for item in candidates:
        text = str((item or {}).get("text") or "").strip()
        url = _prefer_lan_base_url(str((item or {}).get("url") or "").strip())
        if not url:
            continue
        if not text:
            text = "🖼️ Lihat Foto"
        if len(text) > 64:
            text = f"{text[:61]}..."
        key = (text, url)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"text": text, "url": url})

    return normalized


def _with_button_icon(text: Optional[str]) -> str:
    label = str(text or "").strip()
    if not label:
        return "🖼️ Foto"
    if label.startswith(("📄", "🖼️", "✅", "❌", "⏳")):
        return label
    lowered = label.lower()
    if "detail" in lowered:
        return f"📄 {label}"
    if "foto" in lowered:
        return f"🖼️ {label}"
    return label


def _build_detail_photo_rows(
    *,
    detail_url: Optional[str],
    photo_buttons: List[Dict[str, str]],
) -> list[list[dict]]:
    rows: list[list[dict]] = []
    detail_button = None
    clean_detail_url = str(detail_url or "").strip()
    if clean_detail_url:
        detail_button = {
            "text": "📄 Detail",
            "url": _prefer_lan_base_url(clean_detail_url),
        }

    normalized_photos = [
        {"text": _with_button_icon(btn.get("text")), "url": btn.get("url")}
        for btn in photo_buttons
        if str(btn.get("url") or "").strip()
    ]

    if detail_button and normalized_photos:
        first_photo = normalized_photos.pop(0)
        rows.append([detail_button, first_photo])
    elif detail_button:
        rows.append([detail_button])

    for button in normalized_photos:
        rows.append([button])
    return rows


def _filter_guestbook_photo_buttons(
    photo_buttons: List[Dict[str, str]],
    *,
    remove_transaction_photo: bool = False,
    prefer_profile_over_previous: bool = True,
) -> List[Dict[str, str]]:
    if not photo_buttons:
        return []

    has_profile_button = any(
        "foto profil" in str(btn.get("text") or "").strip().lower()
        for btn in photo_buttons
    )
    filtered: list[dict] = []
    for button in photo_buttons:
        label = str(button.get("text") or "").strip().lower()
        if remove_transaction_photo and "foto transaksi" in label:
            continue
        if (
            prefer_profile_over_previous
            and has_profile_button
            and "foto sebelumnya" in label
        ):
            continue
        filtered.append(button)
    return filtered


def _build_guestbook_detail_url(
    transaction_id: int,
    *,
    status: str = "pending",
) -> Optional[str]:
    if not transaction_id:
        return None
    base_url = _dashboard_base_url()
    if not base_url:
        return None
    # Public read-only detail page; no dashboard login required.
    return f"{base_url}/daftar-tamu/public/detail/{int(transaction_id)}"


def _infer_guestbook_detail_url_from_photo_links(
    *,
    transaction_id: int,
    photo_links: Optional[List[Dict[str, str]]],
) -> Optional[str]:
    if not transaction_id:
        return None
    for item in photo_links or []:
        raw_url = str((item or {}).get("url") or "").strip()
        if not raw_url:
            continue
        parsed = urllib.parse.urlsplit(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        base_url = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, "", "", "")
        ).rstrip("/")
        if not base_url:
            continue
        return f"{base_url}/daftar-tamu/public/detail/{int(transaction_id)}"
    return None


def _compact_text(value: Optional[str], limit: int = 96) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 1)].rstrip()}…"


def _compact_note_text(value: Optional[str], limit: int = 55) -> str:
    """Trim note preview without cutting the last word mid-way."""
    safe_limit = max(1, int(limit))
    text = " ".join(str(value or "").split())
    if len(text) <= safe_limit:
        return text

    preview = text[:safe_limit].rstrip()
    if safe_limit < len(text) and not text[safe_limit].isspace():
        last_space = preview.rfind(" ")
        if last_space > 0:
            preview = preview[:last_space].rstrip()

    if not preview:
        preview = text[:safe_limit].rstrip()
    return f"{preview}..."


def _build_guest_preview(
    *,
    guest_summary: Optional[str] = None,
    guest_names: Optional[List[str]] = None,
) -> str:
    normalized_names: list[str] = []
    seen_keys: set[str] = set()

    for raw_name in guest_names or []:
        name = str(raw_name or "").strip()
        if not name:
            continue
        dedupe_key = name.casefold()
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        normalized_names.append(name)

    if not normalized_names:
        clean_summary = str(guest_summary or "").strip()
        if clean_summary:
            summary_parts = [
                part.strip() for part in clean_summary.split(",") if part.strip()
            ]
            normalized_names = summary_parts or [clean_summary]

    if not normalized_names:
        return ""
    if len(normalized_names) == 1:
        return normalized_names[0]
    return f"{normalized_names[0]}, ..."


def _status_label_with_icon(status_label: Optional[str]) -> str:
    raw_label = str(status_label or "").strip()
    if not raw_label:
        return "-"

    label = raw_label
    for prefix in ("✅", "❌", "⏳"):
        if label.startswith(prefix):
            label = label[len(prefix) :].strip()
            break

    lowered = label.lower()
    if any(
        keyword in lowered
        for keyword in ("disetujui", "terverifikasi", "verified", "approved", "acc")
    ):
        return "✅ Terverifikasi"
    if any(
        keyword in lowered for keyword in ("ditolak", "tolak", "rejected", "invalid")
    ):
        return "❌ Ditolak"
    if any(keyword in lowered for keyword in ("pending", "menunggu", "review")):
        return "⏳ Menunggu Verifikasi"
    return label


def notify_guestbook_status_update(
    *,
    transaction_id: int,
    school_name: Optional[str],
    status_label: str,
    actor_name: Optional[str],
    actor_username: Optional[str],
    purpose: Optional[str] = None,
    notes: Optional[str] = None,
    guest_summary: Optional[str] = None,
    guest_names: Optional[List[str]] = None,
    photo_links: Optional[List[Dict[str, str]]] = None,
    photo_url: Optional[str] = None,
    previous_photo_url: Optional[str] = None,
    detail_url: Optional[str] = None,
    exclude_chat_ids: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    actor_display = str(actor_name or "").strip() or "-"

    timestamp = to_jakarta(current_jakarta_time())
    time_label = timestamp.strftime("%d %b %Y, %H:%M") if timestamp else ""
    guest_preview = _build_guest_preview(
        guest_summary=guest_summary,
        guest_names=guest_names,
    )

    lines = [
        f"📘 Buku Tamu • {_status_label_with_icon(status_label)}",
        f"#{transaction_id} • {_compact_text(school_name or '-', 72)}",
        f"Verifikator: {_compact_text(actor_display, 64)}",
    ]
    if guest_preview:
        lines.append(f"Tamu: {_compact_text(guest_preview, 72)}")
    if purpose:
        lines.append(f"Keperluan: {_compact_text(purpose, 84)}")
    if notes:
        lines.append(f"Catatan: {_compact_note_text(notes, 55)}")
    if time_label:
        lines.append(f"🕒 {time_label}")

    photo_buttons = _normalize_guestbook_photo_links(
        photo_links=photo_links,
        photo_url=photo_url,
        previous_photo_url=previous_photo_url,
    )
    photo_buttons = _filter_guestbook_photo_buttons(
        photo_buttons,
        remove_transaction_photo=True,
        prefer_profile_over_previous=True,
    )
    resolved_detail_url = (detail_url or "").strip() or _build_guestbook_detail_url(
        transaction_id,
        status="history",
    )
    if not resolved_detail_url:
        resolved_detail_url = _infer_guestbook_detail_url_from_photo_links(
            transaction_id=transaction_id,
            photo_links=photo_buttons,
        )
    keyboard = _build_detail_photo_rows(
        detail_url=resolved_detail_url,
        photo_buttons=photo_buttons,
    )
    reply_markup = {"inline_keyboard": keyboard} if keyboard else None

    return _broadcast_notification(
        text="\n".join(lines),
        reply_markup=reply_markup,
        exclude_chat_ids=exclude_chat_ids,
    )


def notify_guestbook_duplicate_warning(
    *,
    school_name: Optional[str],
    guest_names: Optional[List[str]],
    visit_at=None,
) -> Dict[str, Any]:
    unique_names: list[str] = []
    seen: set[str] = set()
    for raw_name in guest_names or []:
        clean_name = str(raw_name or "").strip()
        if not clean_name:
            continue
        key = clean_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_names.append(clean_name)

    guest_text = ", ".join(unique_names) if unique_names else "-"
    timestamp = to_jakarta(visit_at) if visit_at else to_jakarta(current_jakarta_time())
    time_label = timestamp.strftime("%d %b %Y, %H:%M") if timestamp else ""

    lines = [
        "Peringatan kunjungan ulang tamu SUDIN",
        f"Sekolah: {school_name or '-'}",
        f"Tamu: {guest_text}",
        "Status acuan: hanya data yang sudah terverifikasi hari ini.",
    ]
    if time_label:
        lines.append(f"Waktu input: {time_label}")
    return _broadcast_notification(text="\n".join(lines))


def _actor_display(actor_name: Optional[str], actor_username: Optional[str]) -> str:
    if actor_name and actor_username:
        return f"{actor_name} (@{actor_username})"
    if actor_name:
        return actor_name
    if actor_username:
        return f"@{actor_username}"
    return "-"


def _time_label() -> str:
    timestamp = to_jakarta(current_jakarta_time())
    return timestamp.strftime("%d %b %Y, %H:%M") if timestamp else ""


def notify_reopen_request(
    *,
    request_id: int,
    assessment_id: int,
    school_name: Optional[str],
    period_name: Optional[str],
    staff_name: Optional[str],
    requested_by_name: Optional[str],
    reason: Optional[str],
) -> Dict[str, Any]:
    lines = [
        "Permintaan reopen penilaian",
        f"Request ID: {request_id}",
        f"Assessment ID: {assessment_id}",
        f"Sekolah: {school_name or '-'}",
        f"Periode: {period_name or '-'}",
        f"Pengaju: {requested_by_name or staff_name or '-'}",
    ]
    clean_reason = (reason or "").strip()
    if clean_reason:
        lines.append(f"Alasan: {clean_reason}")
    time_label = _time_label()
    if time_label:
        lines.append(f"Waktu: {time_label}")
    return _broadcast_notification(text="\n".join(lines))


def notify_reopen_status_update(
    *,
    request_id: int,
    assessment_id: int,
    school_name: Optional[str],
    period_name: Optional[str],
    staff_name: Optional[str],
    status_label: str,
    actor_name: Optional[str],
    actor_username: Optional[str],
    reviewer_note: Optional[str] = None,
) -> Dict[str, Any]:
    lines = [
        "Update permintaan reopen penilaian",
        f"Request ID: {request_id}",
        f"Assessment ID: {assessment_id}",
        f"Sekolah: {school_name or '-'}",
        f"Periode: {period_name or '-'}",
        f"Assessor: {staff_name or '-'}",
        f"Status: {status_label}",
        f"Diverifikasi oleh: {_actor_display(actor_name, actor_username)}",
    ]
    clean_note = (reviewer_note or "").strip()
    if clean_note:
        lines.append(f"Catatan: {clean_note}")
    time_label = _time_label()
    if time_label:
        lines.append(f"Waktu: {time_label}")
    return _broadcast_notification(text="\n".join(lines))


def notify_assignment_request(
    *,
    request_id: int,
    coordinator_name: Optional[str],
    staff_name: Optional[str],
    school_name: Optional[str],
    period_name: Optional[str],
    note: Optional[str] = None,
) -> Dict[str, Any]:
    lines = [
        "Permintaan penugasan monev",
        f"Request ID: {request_id}",
        f"Koordinator: {coordinator_name or '-'}",
        f"Staff: {staff_name or '-'}",
        f"Sekolah: {school_name or '-'}",
        f"Periode: {period_name or '-'}",
    ]
    clean_note = (note or "").strip()
    if clean_note:
        lines.append(f"Catatan: {clean_note}")
    time_label = _time_label()
    if time_label:
        lines.append(f"Waktu: {time_label}")
    return _broadcast_notification(text="\n".join(lines))


def notify_assignment_request_status_update(
    *,
    request_id: int,
    coordinator_name: Optional[str],
    staff_name: Optional[str],
    school_name: Optional[str],
    period_name: Optional[str],
    status_label: str,
    actor_name: Optional[str],
    actor_username: Optional[str],
    reviewer_note: Optional[str] = None,
) -> Dict[str, Any]:
    lines = [
        "Update permintaan penugasan monev",
        f"Request ID: {request_id}",
        f"Koordinator: {coordinator_name or '-'}",
        f"Staff: {staff_name or '-'}",
        f"Sekolah: {school_name or '-'}",
        f"Periode: {period_name or '-'}",
        f"Status: {status_label}",
        f"Diverifikasi oleh: {_actor_display(actor_name, actor_username)}",
    ]
    clean_note = (reviewer_note or "").strip()
    if clean_note:
        lines.append(f"Catatan: {clean_note}")
    time_label = _time_label()
    if time_label:
        lines.append(f"Waktu: {time_label}")
    return _broadcast_notification(text="\n".join(lines))


def notify_team_member_request(
    *,
    request_id: int,
    team_name: Optional[str],
    staff_name: Optional[str],
    requested_by_name: Optional[str],
    note: Optional[str] = None,
) -> Dict[str, Any]:
    lines = [
        "Permintaan anggota tim monev",
        f"Request ID: {request_id}",
        f"Tim: {team_name or '-'}",
        f"Staff: {staff_name or '-'}",
        f"Pengaju: {requested_by_name or '-'}",
    ]
    clean_note = (note or "").strip()
    if clean_note:
        lines.append(f"Catatan: {clean_note}")
    time_label = _time_label()
    if time_label:
        lines.append(f"Waktu: {time_label}")
    return _broadcast_notification(text="\n".join(lines))


def notify_team_member_request_status_update(
    *,
    request_id: int,
    team_name: Optional[str],
    staff_name: Optional[str],
    requested_by_name: Optional[str],
    status_label: str,
    actor_name: Optional[str],
    actor_username: Optional[str],
    reviewer_note: Optional[str] = None,
) -> Dict[str, Any]:
    lines = [
        "Update permintaan anggota tim monev",
        f"Request ID: {request_id}",
        f"Tim: {team_name or '-'}",
        f"Staff: {staff_name or '-'}",
        f"Pengaju: {requested_by_name or '-'}",
        f"Status: {status_label}",
        f"Diverifikasi oleh: {_actor_display(actor_name, actor_username)}",
    ]
    clean_note = (reviewer_note or "").strip()
    if clean_note:
        lines.append(f"Catatan: {clean_note}")
    time_label = _time_label()
    if time_label:
        lines.append(f"Waktu: {time_label}")
    return _broadcast_notification(text="\n".join(lines))


def _build_verification_keyboard(user_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Setujui", "callback_data": f"verify:approve:{user_id}"},
                {"text": "❌ Tolak", "callback_data": f"verify:reject:{user_id}"},
            ]
        ]
    }


def _build_guestbook_keyboard(
    transaction_id: int,
    photo_links: Optional[List[Dict[str, str]]] = None,
    photo_url: Optional[str] = None,
    previous_photo_url: Optional[str] = None,
    detail_url: Optional[str] = None,
    remove_transaction_photo: bool = False,
) -> Optional[dict]:
    photo_buttons = _normalize_guestbook_photo_links(
        photo_links=photo_links,
        photo_url=photo_url,
        previous_photo_url=previous_photo_url,
    )
    photo_buttons = _filter_guestbook_photo_buttons(
        photo_buttons,
        remove_transaction_photo=remove_transaction_photo,
        prefer_profile_over_previous=True,
    )
    keyboard: list[list[dict]] = []
    if transaction_id:
        keyboard.append(
            [
                {
                    "text": "✅ Setujui",
                    "callback_data": f"guestbook:approve:{transaction_id}",
                },
                {
                    "text": "❌ Tolak",
                    "callback_data": f"guestbook:reject:{transaction_id}",
                },
            ]
        )
        resolved_detail_url = (detail_url or "").strip() or _build_guestbook_detail_url(
            transaction_id,
            status="pending",
        )
        if not resolved_detail_url:
            resolved_detail_url = _infer_guestbook_detail_url_from_photo_links(
                transaction_id=transaction_id,
                photo_links=photo_buttons,
            )
        keyboard.extend(
            _build_detail_photo_rows(
                detail_url=resolved_detail_url,
                photo_buttons=photo_buttons,
            )
        )
    if not transaction_id:
        keyboard.extend(
            _build_detail_photo_rows(
                detail_url=(detail_url or "").strip(),
                photo_buttons=photo_buttons,
            )
        )
    if not keyboard:
        return None
    return {"inline_keyboard": keyboard}


def notify_pending_user(
    *,
    user_id: int,
    full_name: str,
    email: str,
    role: str,
    kecamatan_name: Optional[str] = None,
    whatsapp_number: Optional[str] = None,
) -> Dict[str, Any]:
    """Send Telegram notification for pending dashboard user verification."""
    token = _resolve_bot_token()
    if not token:
        return {"sent": 0, "skipped": "token_missing"}

    recipients = _list_admin_recipients()

    timestamp = to_jakarta(current_jakarta_time())
    time_label = timestamp.strftime("%d %b %Y, %H:%M") if timestamp else ""

    lines = [
        "Permintaan verifikasi akun baru",
        f"ID: {user_id}",
        f"Nama: {full_name}",
        f"Email: {email}",
        f"Role: {role}",
    ]
    if kecamatan_name:
        lines.append(f"Kecamatan: {kecamatan_name}")
    if whatsapp_number:
        lines.append(f"WhatsApp: {whatsapp_number}")
    if time_label:
        lines.append(f"Waktu: {time_label}")
    lines.append("")
    message = "\n".join(lines)
    reply_markup = _build_verification_keyboard(user_id)

    sent = 0
    missing: List[str] = []
    for recipient in recipients:
        telegram_user_id = recipient.get("telegram_user_id")
        if not telegram_user_id:
            missing.append(recipient.get("telegram_username") or "")
            continue
        try:
            if _send_telegram_message(
                token,
                int(telegram_user_id),
                message,
                reply_markup=reply_markup,
            ):
                sent += 1
        except Exception:
            continue

    group_sent = 0
    groups = list_telegram_notification_groups()
    for group in groups:
        chat_id = group.get("chat_id")
        if not chat_id:
            continue
        try:
            if _send_telegram_message(
                token,
                int(chat_id),
                message,
                reply_markup=reply_markup,
            ):
                group_sent += 1
        except Exception:
            continue

    return {
        "sent": sent,
        "group_sent": group_sent,
        "missing_usernames": [name for name in missing if name],
        "total_admins": len(recipients),
        "total_groups": len(groups),
    }


def send_test_notification(message: Optional[str] = None) -> Dict[str, Any]:
    """Send a test notification to all admins and registered groups."""
    token = _resolve_bot_token()
    if not token:
        return {"sent": 0, "group_sent": 0, "skipped": "token_missing"}

    recipients = _list_admin_recipients()
    groups = list_telegram_notification_groups()

    timestamp = to_jakarta(current_jakarta_time())
    time_label = timestamp.strftime("%d %b %Y, %H:%M") if timestamp else ""

    base_message = (message or "").strip()
    if not base_message:
        base_message = "Tes notifikasi Telegram dari Dashboard ASKA."
    if time_label:
        base_message = f"{base_message}\nWaktu: {time_label}"

    sent = 0
    missing: List[str] = []
    for recipient in recipients:
        telegram_user_id = recipient.get("telegram_user_id")
        if not telegram_user_id:
            missing.append(recipient.get("telegram_username") or "")
            continue
        try:
            if _send_telegram_message(token, int(telegram_user_id), base_message):
                sent += 1
        except Exception:
            continue

    group_sent = 0
    for group in groups:
        chat_id = group.get("chat_id")
        if not chat_id:
            continue
        try:
            if _send_telegram_message(token, int(chat_id), base_message):
                group_sent += 1
        except Exception:
            continue

    return {
        "sent": sent,
        "group_sent": group_sent,
        "missing_usernames": [name for name in missing if name],
        "total_admins": len(recipients),
        "total_groups": len(groups),
    }


def notify_guestbook_request(
    *,
    transaction_id: int,
    school_name: str,
    npsn: Optional[str] = None,
    visit_at=None,
    guest_summary: Optional[str] = None,
    guest_names: Optional[List[str]] = None,
    duplicate_repeat_count: Optional[int] = None,
    purpose: Optional[str] = None,
    notes: Optional[str] = None,
    photo_links: Optional[List[Dict[str, str]]] = None,
    photo_url: Optional[str] = None,
    previous_photo_url: Optional[str] = None,
    photo_file_path: Optional[str] = None,
    detail_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Send Telegram notification for pending guestbook transaction."""
    token = _resolve_bot_token()
    if not token:
        return {"sent": 0, "skipped": "token_missing"}

    recipients = _list_admin_recipients()
    groups = list_telegram_notification_groups()
    if not recipients and not groups:
        return {"sent": 0, "group_sent": 0, "skipped": "no_targets"}

    timestamp = to_jakarta(visit_at) if visit_at else None
    time_label = timestamp.strftime("%d %b %Y, %H:%M") if timestamp else ""
    guest_preview = _build_guest_preview(
        guest_summary=guest_summary,
        guest_names=guest_names,
    )

    lines = [
        "📘 Buku Tamu • Menunggu Verifikasi",
        f"#{transaction_id} • {_compact_text(school_name, 72)}",
    ]
    if guest_preview:
        lines.append(f"Tamu: {_compact_text(guest_preview, 72)}")
    try:
        repeat_count = int(duplicate_repeat_count or 0)
    except (TypeError, ValueError):
        repeat_count = 0
    if repeat_count >= 2:
        lines.append(f"Duplikat {repeat_count}X❗️")
    if purpose:
        lines.append(f"Keperluan: {_compact_text(purpose, 84)}")
    if notes:
        lines.append(f"Catatan: {_compact_note_text(notes, 55)}")
    if time_label:
        lines.append(f"🕒 {time_label}")
    message = "\n".join(lines)

    use_photo_message = bool(_resolve_local_upload_photo_path(photo_file_path))
    reply_markup = _build_guestbook_keyboard(
        transaction_id,
        photo_links=photo_links,
        photo_url=photo_url,
        previous_photo_url=previous_photo_url,
        detail_url=detail_url,
        remove_transaction_photo=use_photo_message,
    )

    sent = 0
    missing: List[str] = []
    for recipient in recipients:
        telegram_user_id = recipient.get("telegram_user_id")
        if not telegram_user_id:
            missing.append(recipient.get("telegram_username") or "")
            continue
        try:
            target_chat_id = int(telegram_user_id)
            delivered = False
            delivered_message_id: Optional[int] = None
            if use_photo_message and photo_file_path:
                delivered, delivered_message_id = _send_telegram_photo_with_meta(
                    token,
                    target_chat_id,
                    photo_file_path,
                    caption=message,
                    reply_markup=reply_markup,
                )
            if not delivered:
                delivered, delivered_message_id = _send_telegram_message_with_meta(
                    token,
                    target_chat_id,
                    message,
                    reply_markup=reply_markup,
                )
            if delivered:
                sent += 1
                if delivered_message_id:
                    upsert_guestbook_delivery_message(
                        transaction_id=int(transaction_id),
                        chat_id=target_chat_id,
                        message_id=int(delivered_message_id),
                    )
        except Exception:
            continue

    group_sent = 0
    for group in groups:
        chat_id = group.get("chat_id")
        if not chat_id:
            continue
        try:
            target_chat_id = int(chat_id)
            delivered = False
            delivered_message_id: Optional[int] = None
            if use_photo_message and photo_file_path:
                delivered, delivered_message_id = _send_telegram_photo_with_meta(
                    token,
                    target_chat_id,
                    photo_file_path,
                    caption=message,
                    reply_markup=reply_markup,
                )
            if not delivered:
                delivered, delivered_message_id = _send_telegram_message_with_meta(
                    token,
                    target_chat_id,
                    message,
                    reply_markup=reply_markup,
                )
            if delivered:
                group_sent += 1
                if delivered_message_id:
                    upsert_guestbook_delivery_message(
                        transaction_id=int(transaction_id),
                        chat_id=target_chat_id,
                        message_id=int(delivered_message_id),
                    )
        except Exception:
            continue

    return {
        "sent": sent,
        "group_sent": group_sent,
        "missing_usernames": [name for name in missing if name],
        "total_admins": len(recipients),
        "total_groups": len(groups),
    }
