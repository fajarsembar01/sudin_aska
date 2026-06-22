from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import save_chat
from dashboard.queries import get_telegram_admin_by_username
from .queries import (
    SUPPORTER_TELEGRAM_SCOPE,
    delete_supporter_telegram_group_by_chat_id,
    get_submission_detail,
    list_submissions,
    review_submission,
    review_submission_action,
    upsert_supporter_telegram_group,
)
from .telegram import ACTION_LABELS, PLATFORM_LABELS, STATUS_LABELS, notify_supporter_status_update


def _normalize_username(username: Optional[str]) -> Optional[str]:
    if not username:
        return None
    cleaned = username.strip().lstrip("@").lower()
    return cleaned or None


def _authorize_admin(update: Update) -> Optional[dict]:
    user = update.effective_user
    if not user:
        return None
    username = _normalize_username(user.username)
    if not username:
        return None
    return get_telegram_admin_by_username(username, scope=SUPPORTER_TELEGRAM_SCOPE)


def _log_command(update: Update, text: str) -> None:
    user = update.effective_user
    if not user:
        return
    username = user.username or user.first_name or "supporter_admin"
    try:
        save_chat(user.id, username, text, role="user", topic="supporter_notif")
    except Exception:
        logging.getLogger("telegram.supporter").exception("Gagal menyimpan log command supporter.")


async def _reply(update: Update, text: str, *, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
    message = update.effective_message
    if message:
        await message.reply_text(text, reply_markup=reply_markup)


def _submission_markup(submission_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Verifikasi", callback_data=f"supporter:verify:{submission_id}"),
                InlineKeyboardButton("Revisi", callback_data=f"supporter:revision:{submission_id}"),
                InlineKeyboardButton("Tolak", callback_data=f"supporter:reject:{submission_id}"),
            ]
        ]
    )


def _submission_text(item: dict) -> str:
    return "\n".join(
        [
            f"Submission Supporter #{item.get('id')}",
            f"Staff: {item.get('staff_name') or '-'}",
            f"Task: {item.get('task_title') or '-'}",
            f"Platform: {PLATFORM_LABELS.get(item.get('platform'), item.get('platform') or '-')}",
            f"Aksi: {item.get('action_summary') or ACTION_LABELS.get(item.get('action_type'), item.get('action_type') or '-')}",
            f"Status: {STATUS_LABELS.get(item.get('status'), item.get('status') or '-')}",
            f"Potensi poin: {item.get('potential_points') or 0}",
            f"Bukti: {item.get('proof_url') or '-'}",
        ]
    )


async def supporter_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, "/start")
    admin = _authorize_admin(update)
    if not admin:
        await _reply(
            update,
            "Bot Supporter ASKA aktif. Akun Telegram ini belum terdaftar sebagai admin Supporter.",
        )
        return
    await _reply(
        update,
        "Bot Supporter ASKA aktif.\n"
        "Gunakan /pending untuk submission menunggu verifikasi.\n"
        "Gunakan /register_group di grup target notifikasi.",
    )


async def supporter_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.supporter")
    admin = _authorize_admin(update)
    if not admin:
        await _reply(update, "Akun ini belum terdaftar sebagai admin Telegram Supporter.")
        return
    _log_command(update, "/pending")
    try:
        rows = list_submissions(status="pending", limit=10)
    except Exception:
        logger.exception("Gagal mengambil pending submission Supporter.")
        await _reply(update, "Gagal mengambil daftar pending.")
        return
    if not rows:
        await _reply(update, "Tidak ada submission Supporter yang pending.")
        return
    await _reply(update, f"Submission pending: {len(rows)} item terbaru.")
    for item in rows:
        await _reply(update, _submission_text(item), reply_markup=_submission_markup(int(item["id"])))


async def supporter_register_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.supporter")
    admin = _authorize_admin(update)
    if not admin:
        await _reply(update, "Akun ini belum terdaftar sebagai admin Telegram Supporter.")
        return
    _log_command(update, "/register_group")
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await _reply(update, "Perintah ini harus dijalankan di dalam grup.")
        return
    try:
        upsert_supporter_telegram_group(
            chat_id=int(chat.id),
            title=chat.title or None,
            created_by=admin.get("dashboard_user_id"),
        )
    except Exception:
        logger.exception("Gagal mendaftarkan grup Supporter.")
        await _reply(update, "Gagal mendaftarkan grup Supporter.")
        return
    await _reply(update, "Grup ini berhasil didaftarkan untuk notifikasi Supporter.")


async def supporter_unregister_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.supporter")
    admin = _authorize_admin(update)
    if not admin:
        await _reply(update, "Akun ini belum terdaftar sebagai admin Telegram Supporter.")
        return
    _log_command(update, "/unregister_group")
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await _reply(update, "Perintah ini harus dijalankan di dalam grup.")
        return
    try:
        deleted = delete_supporter_telegram_group_by_chat_id(int(chat.id))
    except Exception:
        logger.exception("Gagal menghapus grup Supporter.")
        await _reply(update, "Gagal menghapus grup Supporter.")
        return
    await _reply(update, "Grup dihapus dari notifikasi Supporter." if deleted else "Grup ini belum terdaftar.")


async def handle_supporter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.supporter")
    query = update.callback_query
    if not query or not query.data:
        return
    admin = _authorize_admin(update)
    if not admin:
        await query.answer("Akun ini belum terdaftar sebagai admin Supporter.", show_alert=True)
        return

    # Acknowledge immediately so the Telegram button stops showing the spinner.
    try:
        await query.answer()
    except Exception:
        pass

    async def _notify(text: str) -> None:
        message = query.message
        if message:
            try:
                await message.reply_text(text)
            except Exception:
                logger.exception("Gagal mengirim umpan balik callback Supporter.")

    async def _clear_buttons() -> None:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as exc:
            # Benign when the keyboard was already removed (e.g. retried callback).
            if "not modified" not in str(exc).lower():
                logger.warning("Gagal membersihkan tombol callback Supporter: %s", exc)

    parts = query.data.split(":")
    if len(parts) < 3:
        await _notify("Callback tidak dikenal.")
        return
    action = parts[1]
    try:
        submission_id = int(parts[2])
    except (TypeError, ValueError):
        await _notify("ID submission tidak valid.")
        return
    action_key = parts[3] if len(parts) > 3 else None
    status_map = {
        "verify": "verified",
        "reject": "rejected",
        "revision": "needs_revision",
    }
    status = status_map.get(action)
    if not status:
        await _notify("Aksi tidak dikenal.")
        return
    detail = await asyncio.to_thread(get_submission_detail, submission_id)
    if not detail:
        await _notify("Submission tidak ditemukan.")
        return
    if detail.get("status") == "cancelled":
        await _notify("Submission sudah dibatalkan.")
        return

    status_word = {
        "verified": "diverifikasi",
        "rejected": "ditolak",
        "needs_revision": "diminta revisi",
    }[status]

    # Per-action verification (callback carries the action key).
    if action_key:
        note = {
            "verified": f"Aksi {action_key} diverifikasi via Telegram.",
            "rejected": f"Aksi {action_key} ditolak via Telegram.",
            "needs_revision": f"Aksi {action_key} diminta revisi via Telegram.",
        }[status]
        try:
            updated = await asyncio.to_thread(
                review_submission_action,
                submission_id=submission_id,
                action_key=action_key,
                status=status,
                reviewer_id=admin.get("dashboard_user_id"),
                reviewer_note=note,
            )
        except Exception:
            logger.exception("Gagal memproses callback aksi Supporter.")
            await _notify("Gagal memproses aksi.")
            return
        if not updated:
            await _notify("Aksi gagal diperbarui.")
            return
        action_label = ACTION_LABELS.get(action_key, action_key)
        await _clear_buttons()
        await _notify(f"Aksi {action_label} {status_word}.")
        return

    # Legacy whole-submission verification (no action key).
    if detail.get("status") in {"verified", "cancelled"}:
        await _notify("Submission sudah selesai.")
        return
    note = {
        "verified": "Diverifikasi via Telegram Supporter.",
        "rejected": "Ditolak via Telegram Supporter.",
        "needs_revision": "Diminta revisi via Telegram Supporter.",
    }[status]
    try:
        updated = await asyncio.to_thread(
            review_submission,
            submission_id=submission_id,
            status=status,
            reviewer_id=admin.get("dashboard_user_id"),
            reviewer_note=note,
        )
    except Exception:
        logger.exception("Gagal memproses callback Supporter.")
        await _notify("Gagal memproses submission.")
        return
    if not updated:
        await _notify("Submission gagal diperbarui.")
        return
    await _clear_buttons()
    final_text = _submission_text(updated)
    message = query.message
    if message:
        try:
            await message.reply_text(final_text)
        except Exception:
            logger.exception("Gagal mengirim teks final callback Supporter.")
    source_chat_id = getattr(message, "chat_id", None)
    try:
        await asyncio.to_thread(
            notify_supporter_status_update,
            submission_id=submission_id,
            exclude_chat_ids={int(source_chat_id)} if source_chat_id is not None else None,
        )
    except Exception:
        logger.exception("Gagal broadcast status Supporter.")
