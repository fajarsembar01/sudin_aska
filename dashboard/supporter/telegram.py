from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Set

from dashboard.db_access import get_cursor
from dashboard.telegram_notifications import (
    _dashboard_base_url,
    _prefer_lan_base_url,
    _send_telegram_message_with_meta,
    _send_telegram_photo_with_meta,
)
from utils import current_jakarta_time, to_jakarta

from .queries import (
    ACTION_OPTIONS,
    PLATFORM_OPTIONS,
    SUPPORTER_TELEGRAM_SCOPE,
    get_submission_detail,
    get_supporter_setting,
    list_supporter_telegram_groups,
    upsert_supporter_delivery_message,
)


SUPPORTER_BOT_TOKEN_SETTING = "telegram_bot_token"


ACTION_LABELS = dict(ACTION_OPTIONS)
PLATFORM_LABELS = dict(PLATFORM_OPTIONS)
STATUS_LABELS = {
    "submitted": "Menunggu verifikasi",
    "under_review": "Sedang direview",
    "verified": "Terverifikasi",
    "rejected": "Ditolak",
    "needs_revision": "Perlu revisi",
    "cancelled": "Dibatalkan",
}


def resolve_supporter_bot_token() -> Optional[str]:
    # Prefer the token configured via the dashboard settings page, then
    # fall back to the environment variable for backward compatibility.
    try:
        stored = get_supporter_setting(SUPPORTER_BOT_TOKEN_SETTING)
    except Exception:
        stored = None
    if stored:
        return stored
    token = (os.getenv("TELEGRAM_SUPPORTER_BOT_TOKEN") or "").strip()
    return token or None


def test_supporter_bot_connection() -> Dict[str, Any]:
    """Call Telegram getMe to verify the configured bot token works."""
    token = resolve_supporter_bot_token()
    if not token:
        return {"ok": False, "error": "Token bot belum dikonfigurasi."}

    import json
    import urllib.error
    import urllib.request

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:  # nosec - external API call
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = json.loads(exc.read().decode("utf-8") or "{}")
            detail = body.get("description") or ""
        except Exception:
            detail = ""
        if exc.code in (401, 404):
            return {"ok": False, "error": detail or "Token bot tidak valid."}
        return {"ok": False, "error": detail or f"Gagal menghubungi Telegram (HTTP {exc.code})."}
    except Exception as exc:  # noqa: BLE001 - network/timeout errors
        return {"ok": False, "error": f"Gagal menghubungi Telegram: {exc}"}

    if not payload.get("ok"):
        return {"ok": False, "error": payload.get("description") or "Token bot tidak valid."}

    result = payload.get("result") or {}
    return {
        "ok": True,
        "username": result.get("username"),
        "name": result.get("first_name"),
        "bot_id": result.get("id"),
    }


def _list_supporter_admin_recipients() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                ta.telegram_username,
                tu.telegram_user_id
            FROM telegram_admin_accounts ta
            JOIN dashboard_users u ON u.id = ta.dashboard_user_id AND u.role IN ('admin', 'staff')
            LEFT JOIN telegram_users tu ON LOWER(tu.username) = LOWER(ta.telegram_username)
            WHERE ta.notification_scope = %s
            ORDER BY LOWER(ta.telegram_username) ASC
            """,
            (SUPPORTER_TELEGRAM_SCOPE,),
        )
        return [dict(row) for row in cur.fetchall()]


def _submission_admin_url(submission_id: int) -> Optional[str]:
    base = _dashboard_base_url()
    if not base:
        return None
    return f"{base}/supporter/admin/submissions?status=all&q={int(submission_id)}"


def _points_breakdown(detail: Dict[str, Any]) -> tuple[int, int, int]:
    """Return (points_per_action, total_points, action_count) for a submission."""
    action_count = int(detail.get("action_count") or len(detail.get("action_types") or []) or 1)
    action_count = max(1, action_count)
    total = int(detail.get("potential_points") or 0)
    per_action = round(total / action_count) if action_count else total
    return per_action, total, action_count


def _build_submission_text(detail: Dict[str, Any], *, status_update: bool = False) -> str:
    submitted_at = to_jakarta(detail.get("submitted_at"))
    reviewed_at = to_jakarta(detail.get("reviewed_at"))
    end_at = to_jakarta(detail.get("end_at"))
    per_action, total_points, action_count = _points_breakdown(detail)
    lines = [
        "Supporter submission" + (" diproses" if status_update else " baru"),
        f"ID: {detail.get('id')}",
        f"Staff: {detail.get('staff_name') or '-'}",
        f"Task: {detail.get('task_title') or '-'}",
        f"Platform: {PLATFORM_LABELS.get(detail.get('platform'), detail.get('platform') or '-')}",
        f"Aksi: {detail.get('action_summary') or ACTION_LABELS.get(detail.get('action_type'), detail.get('action_type') or '-')}",
        f"Status: {STATUS_LABELS.get(detail.get('status'), detail.get('status') or '-')}",
    ]
    if action_count > 1:
        lines.append(f"Poin per aksi: {per_action} (total {total_points} untuk {action_count} aksi)")
    else:
        lines.append(f"Poin: {total_points}")
    if detail.get("penalty_percent"):
        lines.append(f"Penalty: {detail.get('penalty_percent')}%")
    if submitted_at:
        lines.append(f"Dikirim: {submitted_at:%d %b %Y %H:%M} WIB")
    if end_at:
        lines.append(f"Berakhir: {end_at:%d %b %Y %H:%M} WIB")
    if reviewed_at:
        lines.append(f"Direview: {reviewed_at:%d %b %Y %H:%M} WIB")
    if detail.get("proof_url"):
        lines.append(f"Bukti: {detail.get('proof_url')}")
    if detail.get("social_username"):
        lines.append(f"Akun: {detail.get('social_username')}")
    if detail.get("reviewer_note"):
        lines.append(f"Catatan: {detail.get('reviewer_note')}")
    return "\n".join(lines)


def _decision_markup(submission_id: int) -> Dict[str, Any]:
    rows: list[list[dict]] = [
        [
            {"text": "Verifikasi", "callback_data": f"supporter:verify:{submission_id}"},
            {"text": "Revisi", "callback_data": f"supporter:revision:{submission_id}"},
            {"text": "Tolak", "callback_data": f"supporter:reject:{submission_id}"},
        ]
    ]
    detail_url = _submission_admin_url(submission_id)
    if detail_url:
        rows.append([{"text": "Buka dashboard", "url": _prefer_lan_base_url(detail_url)}])
    return {"inline_keyboard": rows}


def _action_decision_markup(submission_id: int, action_key: str) -> Dict[str, Any]:
    """Per-action verify/revise/reject buttons."""
    rows: list[list[dict]] = [
        [
            {"text": "✅ Verifikasi", "callback_data": f"supporter:verify:{submission_id}:{action_key}"},
            {"text": "✏️ Revisi", "callback_data": f"supporter:revision:{submission_id}:{action_key}"},
            {"text": "❌ Tolak", "callback_data": f"supporter:reject:{submission_id}:{action_key}"},
        ]
    ]
    detail_url = _submission_admin_url(submission_id)
    if detail_url:
        rows.append([{"text": "Buka dashboard", "url": _prefer_lan_base_url(detail_url)}])
    return {"inline_keyboard": rows}


def _photo_caption(text: str) -> str:
    # Telegram caption hard limit is 1024 chars.
    clean = text or ""
    return clean if len(clean) <= 1024 else clean[:1021] + "..."


def _deliver_one(
    token: str,
    chat_id: int,
    text: str,
    *,
    reply_markup: Optional[dict],
    photo_path: Optional[str],
) -> tuple[bool, Optional[int]]:
    """Send a photo with caption when available, otherwise a plain text message."""
    if photo_path:
        ok, message_id = _send_telegram_photo_with_meta(
            token,
            chat_id,
            photo_path,
            caption=_photo_caption(text),
            reply_markup=reply_markup,
        )
        if ok:
            return ok, message_id
    return _send_telegram_message_with_meta(token, chat_id, text, reply_markup=reply_markup)


def _broadcast_supporter_message(
    *,
    text: str,
    reply_markup: Optional[dict] = None,
    photo_path: Optional[str] = None,
    submission_id: Optional[int] = None,
    track_delivery: bool = True,
    exclude_chat_ids: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    token = resolve_supporter_bot_token()
    if not token:
        return {"sent": 0, "group_sent": 0, "skipped": "token_missing"}

    sent = 0
    group_sent = 0
    missing: list[str] = []

    for recipient in _list_supporter_admin_recipients():
        telegram_user_id = recipient.get("telegram_user_id")
        if not telegram_user_id:
            missing.append(recipient.get("telegram_username") or "")
            continue
        chat_id = int(telegram_user_id)
        if exclude_chat_ids and chat_id in exclude_chat_ids:
            continue
        try:
            ok, message_id = _deliver_one(
                token,
                chat_id,
                text,
                reply_markup=reply_markup,
                photo_path=photo_path,
            )
            if ok:
                sent += 1
                if track_delivery and submission_id and message_id:
                    upsert_supporter_delivery_message(
                        submission_id=submission_id,
                        chat_id=chat_id,
                        message_id=message_id,
                    )
        except Exception:
            continue

    for group in list_supporter_telegram_groups():
        chat_id = group.get("chat_id")
        if not chat_id:
            continue
        target_chat_id = int(chat_id)
        if exclude_chat_ids and target_chat_id in exclude_chat_ids:
            continue
        try:
            ok, message_id = _deliver_one(
                token,
                target_chat_id,
                text,
                reply_markup=reply_markup,
                photo_path=photo_path,
            )
            if ok:
                group_sent += 1
                if track_delivery and submission_id and message_id:
                    upsert_supporter_delivery_message(
                        submission_id=submission_id,
                        chat_id=target_chat_id,
                        message_id=message_id,
                    )
        except Exception:
            continue

    return {
        "sent": sent,
        "group_sent": group_sent,
        "missing_usernames": [name for name in missing if name],
    }


def send_supporter_test_broadcast() -> Dict[str, Any]:
    """Send a test message to all reachable supporter admins and groups."""
    token = resolve_supporter_bot_token()
    if not token:
        return {"ok": False, "error": "Token bot belum dikonfigurasi.", "sent": 0, "group_sent": 0}

    now = to_jakarta(current_jakarta_time())
    when = f" ({now:%d %b %Y %H:%M} WIB)" if now else ""
    text = (
        "Tes notifikasi Supporter ASKA" + when + "\n"
        "Jika kamu menerima pesan ini, notifikasi sudah aktif."
    )
    result = _broadcast_supporter_message(text=text)
    result["ok"] = True
    return result


def _supporter_photo_ref(rel_path: Optional[str]) -> Optional[str]:
    """Map a stored supporter proof path to a value resolvable by the photo sender."""
    raw = str(rel_path or "").strip()
    if not raw:
        return None
    normalized = raw.replace("\\", "/").lstrip("/")
    if normalized.startswith("uploads/"):
        return normalized
    if normalized.startswith("supporter/"):
        return f"uploads/{normalized}"
    return f"uploads/supporter/{normalized}"


def _collect_action_screenshots(detail: Dict[str, Any]) -> list[tuple[Optional[str], str]]:
    """Return ordered (action_key, photo_ref) pairs for a submission's screenshots."""
    metadata = detail.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            metadata = {}
    screenshots = (metadata or {}).get("screenshots") or {}

    pairs: list[tuple[Optional[str], str]] = []
    seen: Set[str] = set()
    if isinstance(screenshots, dict):
        # Preserve the task's action ordering first.
        for action_key in detail.get("action_types") or []:
            rel = screenshots.get(action_key)
            ref = _supporter_photo_ref(rel)
            if ref and ref not in seen:
                pairs.append((action_key, ref))
                seen.add(ref)
        # Include any extra screenshots not tied to a known action.
        for action_key, rel in screenshots.items():
            ref = _supporter_photo_ref(rel)
            if ref and ref not in seen:
                pairs.append((action_key, ref))
                seen.add(ref)

    if not pairs:
        ref = _supporter_photo_ref(detail.get("proof_file_path"))
        if ref:
            pairs.append((None, ref))
    return pairs


def _build_action_caption(
    detail: Dict[str, Any],
    action_key: Optional[str],
    index: int,
    total: int,
    *,
    with_decision: bool,
) -> str:
    submitted_at = to_jakarta(detail.get("submitted_at"))
    per_action, total_points, action_count = _points_breakdown(detail)
    lines = ["Supporter submission baru"]
    if total > 1:
        label = ACTION_LABELS.get(action_key, action_key or "-")
        lines.append(f"Aksi {index}/{total}: {label}")
    elif action_key:
        lines.append(f"Aksi: {ACTION_LABELS.get(action_key, action_key)}")
    lines.extend(
        [
            f"ID: {detail.get('id')}",
            f"Staff: {detail.get('staff_name') or '-'}",
            f"Task: {detail.get('task_title') or '-'}",
            f"Platform: {PLATFORM_LABELS.get(detail.get('platform'), detail.get('platform') or '-')}",
            f"Status: {STATUS_LABELS.get(detail.get('status'), detail.get('status') or '-')}",
            f"Poin aksi ini: {per_action}",
        ]
    )
    if detail.get("social_username"):
        lines.append(f"Akun: {detail.get('social_username')}")
    if detail.get("proof_url"):
        lines.append(f"Bukti: {detail.get('proof_url')}")
    if submitted_at:
        lines.append(f"Dikirim: {submitted_at:%d %b %Y %H:%M} WIB")
    if with_decision:
        lines.append("")
        lines.append("Verifikasi aksi ini dengan tombol di bawah.")
    return "\n".join(lines)


def notify_supporter_submission(*, submission_id: int) -> Dict[str, Any]:
    detail = get_submission_detail(submission_id)
    if not detail:
        return {"sent": 0, "group_sent": 0, "skipped": "submission_missing"}

    pairs = _collect_action_screenshots(detail)
    if not pairs:
        # No image proof: fall back to a single text notification (whole submission).
        return _broadcast_supporter_message(
            text=_build_submission_text(detail),
            reply_markup=_decision_markup(submission_id),
            submission_id=submission_id,
        )

    total = len(pairs)
    last_result: Dict[str, Any] = {"sent": 0, "group_sent": 0, "missing_usernames": []}
    for index, (action_key, photo_ref) in enumerate(pairs):
        is_last = index == total - 1
        # Per-action verification: each message gets its own buttons.
        markup = _action_decision_markup(submission_id, action_key) if action_key else _decision_markup(submission_id)
        caption = _build_action_caption(
            detail,
            action_key,
            index + 1,
            total,
            with_decision=True,
        )
        result = _broadcast_supporter_message(
            text=caption,
            reply_markup=markup,
            photo_path=photo_ref,
            submission_id=submission_id if is_last else None,
            track_delivery=is_last,
        )
        if is_last:
            last_result = result
    return last_result


def notify_supporter_status_update(
    *,
    submission_id: int,
    exclude_chat_ids: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    detail = get_submission_detail(submission_id)
    if not detail:
        return {"sent": 0, "group_sent": 0, "skipped": "submission_missing"}
    lines = [_build_submission_text(detail, status_update=True)]
    now = to_jakarta(current_jakarta_time())
    if now:
        lines.append(f"Waktu update: {now:%d %b %Y %H:%M} WIB")
    return _broadcast_supporter_message(
        text="\n".join(lines),
        submission_id=submission_id,
        exclude_chat_ids=exclude_chat_ids,
    )
