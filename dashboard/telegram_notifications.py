from __future__ import annotations

import os
import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .db_access import get_cursor
from .queries import fetch_telegram_notification_settings, list_telegram_notification_groups
from utils import current_jakarta_time, to_jakarta


def _resolve_bot_token() -> Optional[str]:
    settings = fetch_telegram_notification_settings() or {}
    token = (settings.get("bot_token") or "").strip()
    if not token:
        token = (os.getenv("TELEGRAM_NOTIF_BOT_TOKEN") or "").strip()
    return token or None


def _list_admin_recipients() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                ta.telegram_username,
                tu.telegram_user_id
            FROM telegram_admin_accounts ta
            JOIN dashboard_users u ON u.id = ta.dashboard_user_id AND u.role = 'admin'
            LEFT JOIN telegram_users tu ON LOWER(tu.username) = LOWER(ta.telegram_username)
            ORDER BY LOWER(ta.telegram_username) ASC
            """
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def _send_telegram_message(
    bot_token: str,
    chat_id: int,
    text: str,
    *,
    reply_markup: Optional[dict] = None,
) -> bool:
    if not bot_token or not chat_id or not text:
        return False
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    payload = urllib.parse.urlencode(data)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:  # nosec - external API call
        return 200 <= resp.status < 300


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
    photo_url: Optional[str],
) -> Optional[dict]:
    keyboard: list[list[dict]] = []
    if transaction_id:
        keyboard.append(
            [
                {"text": "✅ Setujui", "callback_data": f"guestbook:approve:{transaction_id}"},
                {"text": "❌ Tolak", "callback_data": f"guestbook:reject:{transaction_id}"},
            ]
        )
    if photo_url:
        keyboard.append([{"text": "🖼️ Lihat Foto", "url": photo_url}])
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
    npsn: Optional[str],
    visit_at,
    guest_summary: Optional[str],
    purpose: Optional[str],
    notes: Optional[str],
    photo_url: Optional[str],
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

    lines = [
        "Permintaan verifikasi buku tamu",
        f"ID: {transaction_id}",
        f"Sekolah: {school_name}",
    ]
    if npsn:
        lines.append(f"NPSN: {npsn}")
    if guest_summary:
        lines.append(f"Tamu: {guest_summary}")
    if purpose:
        lines.append(f"Keperluan: {purpose}")
    if notes:
        lines.append(f"Catatan: {notes}")
    if time_label:
        lines.append(f"Waktu: {time_label}")
    lines.append("")
    message = "\n".join(lines)

    reply_markup = _build_guestbook_keyboard(transaction_id, photo_url)

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
