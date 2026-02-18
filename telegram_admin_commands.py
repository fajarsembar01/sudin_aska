from __future__ import annotations

from typing import Iterable, Optional
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import save_chat
from utils import current_jakarta_time, to_jakarta
from dashboard.queries import (
    fetch_dashboard_user_basic,
    fetch_pending_dashboard_users,
    get_telegram_admin_by_username,
    update_dashboard_user_verification,
    upsert_telegram_notification_group,
    delete_telegram_notification_group_by_chat_id,
)
from dashboard.daftar_tamu.queries import get_transaction_detail, update_transaction_status
from dashboard.telegram_notifications import (
    _build_guestbook_detail_url,
    notify_guestbook_status_update,
    notify_verification_status_update,
)


def _normalize_username(username: Optional[str]) -> Optional[str]:
    if not username:
        return None
    cleaned = username.strip().lstrip("@").lower()
    return cleaned or None


def _status_label(status: Optional[str]) -> str:
    normalized = (status or "").strip().lower()
    if normalized == "approved":
        return "✅ Disetujui"
    if normalized == "rejected":
        return "❌ Ditolak"
    if normalized == "pending":
        return "⏳ Menunggu"
    return normalized or "-"


def _compact_text(value: Optional[str], limit: int = 96) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 1)].rstrip()}…"


def _compact_note_text(value: Optional[str], limit: int = 55) -> str:
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
    if any(keyword in lowered for keyword in ("disetujui", "terverifikasi", "verified", "approved", "acc")):
        return "✅ Terverifikasi"
    if any(keyword in lowered for keyword in ("ditolak", "tolak", "rejected", "invalid")):
        return "❌ Ditolak"
    if any(keyword in lowered for keyword in ("pending", "menunggu", "review")):
        return "⏳ Menunggu Verifikasi"
    return label


def _build_guest_preview(guest_names: Optional[list[str]]) -> str:
    cleaned_names: list[str] = []
    seen_names: set[str] = set()
    for raw_name in guest_names or []:
        name = str(raw_name or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        cleaned_names.append(name)
    if not cleaned_names:
        return ""
    if len(cleaned_names) == 1:
        return cleaned_names[0]
    return f"{cleaned_names[0]}, ..."


def _log_command(update: Update, text: str) -> None:
    user = update.effective_user
    if not user:
        return
    username = user.username or user.first_name or "admin"
    save_chat(user.id, username, text, role="user", topic=None)


def _log_bot_message(user_id: Optional[int], username: Optional[str], text: Optional[str]) -> None:
    if user_id is None:
        return
    message_text = (text or "").strip()
    if not message_text:
        return
    safe_username = (username or "").strip() or "admin"
    logger = logging.getLogger("telegram.admin")
    try:
        save_chat(user_id, safe_username, message_text, role="aska", topic=None)
    except Exception:
        logger.exception("Gagal menyimpan log balasan bot.")


def _log_verification_activity(
    *,
    admin_user_id: Optional[int],
    user_id: int,
    full_name: Optional[str],
    status: str,
    reviewer_note: Optional[str] = None,
) -> None:
    logger = logging.getLogger("telegram.admin")
    details = {
        "account_status": status,
        "info": "verify",
        "verification_source": "telegram_bot",
    }
    clean_note = (reviewer_note or "").strip()
    if clean_note:
        details["reviewer_note"] = clean_note
    try:
        from dashboard.portal.queries import log_activity

        log_activity(
            admin_user_id,
            "UPDATE",
            "USER",
            user_id,
            full_name or str(user_id),
            details,
        )
    except Exception:
        logger.exception("Gagal mencatat activity log verifikasi Telegram.")


async def _reply(update: Update, text: str) -> None:
    message = update.effective_message
    if message:
        await message.reply_text(text)
    user = update.effective_user
    if user:
        username = user.username or user.first_name or "admin"
        _log_bot_message(user.id, username, text)


async def _finalize_callback(
    query,
    status_label: str,
    actor_name: Optional[str],
    actor_username: Optional[str],
    *,
    summary_text: Optional[str] = None,
    detail_lines: Optional[Iterable[str]] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    include_status_line: bool = True,
) -> None:
    logger = logging.getLogger("telegram.admin")
    message = query.message
    callback_user = getattr(query, "from_user", None)
    callback_user_id = getattr(callback_user, "id", None)
    callback_username = (
        getattr(callback_user, "username", None)
        or getattr(callback_user, "first_name", None)
        or "admin"
    )
    if actor_name and actor_username:
        suffix_actor = f" oleh {actor_name} (@{actor_username})"
    elif actor_name:
        suffix_actor = f" oleh {actor_name}"
    elif actor_username:
        suffix_actor = f" oleh @{actor_username}"
    else:
        suffix_actor = ""

    lines = []
    if summary_text:
        lines.append(summary_text.strip())
    if include_status_line:
        lines.append(f"Status: {status_label}{suffix_actor}")
    for raw in detail_lines or []:
        clean = (raw or "").strip()
        if clean:
            lines.append(clean)
    default_text = f"Status: {status_label}{suffix_actor}" if include_status_line else "Status diperbarui."
    final_text = "\n".join(lines).strip() or default_text

    if message:
        try:
            await message.reply_text(final_text, reply_markup=reply_markup)
            _log_bot_message(callback_user_id, callback_username, final_text)
            try:
                await message.delete()
            except Exception:
                logger.exception("Gagal menghapus pesan callback lama.")
            return
        except Exception:
            logger.exception("Gagal mengirim pesan status baru callback.")
            pass

    if message and message.text:
        try:
            await query.edit_message_text(final_text, reply_markup=reply_markup)
            _log_bot_message(callback_user_id, callback_username, final_text)
            return
        except Exception:
            logger.exception("Gagal edit pesan callback.")
            pass

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("Gagal menghapus reply markup.")
        pass
    if message:
        await message.reply_text(final_text, reply_markup=reply_markup)
        _log_bot_message(callback_user_id, callback_username, final_text)


def _extract_guestbook_photo_links(
    existing_markup: Optional[InlineKeyboardMarkup],
) -> list[dict]:
    if not existing_markup:
        return []
    links: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in existing_markup.inline_keyboard or []:
        for button in row:
            text = (getattr(button, "text", None) or "").strip()
            url = (getattr(button, "url", None) or "").strip()
            if not text or not url:
                continue
            lowered = text.lower()
            if "foto" not in lowered and "photo" not in lowered:
                continue
            key = (text, url)
            if key in seen:
                continue
            seen.add(key)
            links.append({"text": text, "url": url})
    return links


def _extract_guestbook_detail_url(existing_markup: Optional[InlineKeyboardMarkup]) -> Optional[str]:
    if not existing_markup:
        return None
    for row in existing_markup.inline_keyboard or []:
        for button in row:
            text = (getattr(button, "text", None) or "").strip().lower()
            url = (getattr(button, "url", None) or "").strip()
            if not url:
                continue
            if "detail" in text:
                return url
    return None


def _button_label_with_icon(text: Optional[str], *, default_label: str) -> str:
    label = str(text or "").strip() or default_label
    if label.startswith(("📄", "🖼️", "✅", "❌", "⏳")):
        return label
    lowered = label.lower()
    if "detail" in lowered:
        return f"📄 {label}"
    if "foto" in lowered or "photo" in lowered:
        return f"🖼️ {label}"
    return label


def _build_guestbook_followup_markup(
    *,
    transaction_id: Optional[int] = None,
    existing_markup: Optional[InlineKeyboardMarkup],
) -> Optional[InlineKeyboardMarkup]:
    detail_url = _extract_guestbook_detail_url(existing_markup)
    if not detail_url and transaction_id:
        detail_url = _build_guestbook_detail_url(int(transaction_id), status="history")
    photo_links = _extract_guestbook_photo_links(existing_markup)

    has_profile = any(
        "foto profil" in str((item or {}).get("text") or "").strip().lower()
        for item in photo_links
    )

    photo_buttons: list[InlineKeyboardButton] = []
    seen_keys: set[tuple[str, str]] = set()
    for item in photo_links:
        url = str((item or {}).get("url") or "").strip()
        if not url:
            continue
        label = str((item or {}).get("text") or "").strip()
        lowered = label.lower()
        if "foto transaksi" in lowered:
            continue
        if has_profile and "foto sebelumnya" in lowered:
            continue
        safe_label = _button_label_with_icon(label, default_label="🖼️ Foto")
        if len(safe_label) > 64:
            safe_label = f"{safe_label[:61]}..."
        key = (safe_label, url)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        photo_buttons.append(InlineKeyboardButton(text=safe_label, url=url))

    rows: list[list[InlineKeyboardButton]] = []
    detail_button = None
    if detail_url:
        detail_button = InlineKeyboardButton(
            text=_button_label_with_icon("Detail", default_label="📄 Detail"),
            url=detail_url,
        )

    if detail_button and photo_buttons:
        rows.append([detail_button, photo_buttons.pop(0)])
    elif detail_button:
        rows.append([detail_button])

    for button in photo_buttons:
        rows.append([button])

    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


def _build_guestbook_callback_message(
    *,
    transaction_id: int,
    detail: dict,
    status_label: str,
    actor_name: Optional[str],
) -> str:
    guests = (detail or {}).get("guests") or []
    guest_names: list[str] = []
    seen_guest_names: set[str] = set()
    for row in guests:
        guest_name = str((row or {}).get("full_name") or "").strip()
        if not guest_name:
            continue
        key = guest_name.casefold()
        if key in seen_guest_names:
            continue
        seen_guest_names.add(key)
        guest_names.append(guest_name)

    guest_preview = _build_guest_preview(guest_names)
    reviewer_name = str(actor_name or "").strip() or str(detail.get("reviewer_name") or "").strip() or "-"
    lines = [
        f"📘 Buku Tamu • {_status_label_with_icon(status_label)}",
        f"#{transaction_id} • {_compact_text(detail.get('school_name') or '-', 72)}",
        f"Verifikator: {_compact_text(reviewer_name, 64)}",
    ]
    if guest_preview:
        lines.append(f"Tamu: {_compact_text(guest_preview, 72)}")

    purpose = str(detail.get("purpose") or "").strip()
    if purpose:
        lines.append(f"Keperluan: {_compact_text(purpose, 84)}")

    notes = str(detail.get("notes") or "").strip()
    if notes:
        lines.append(f"Catatan: {_compact_note_text(notes, 55)}")

    reviewed_at = detail.get("reviewed_at")
    timestamp = to_jakarta(reviewed_at) if reviewed_at else to_jakarta(current_jakarta_time())
    if timestamp:
        lines.append(f"🕒 {timestamp.strftime('%d %b %Y, %H:%M')}")
    return "\n".join(lines)


def _authorize_admin(update: Update) -> Optional[dict]:
    user = update.effective_user
    username = _normalize_username(getattr(user, "username", None)) if user else None
    if not username:
        return None
    return get_telegram_admin_by_username(username)


async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.admin")
    admin = _authorize_admin(update)
    if not admin:
        await _reply(
            update,
            "Akun ini belum terdaftar sebagai admin Telegram. "
            "Pastikan username Telegram kamu sudah didaftarkan di dashboard.",
        )
        return

    _log_command(update, "/pending")
    logger.info("Admin %s meminta daftar pending.", admin.get("admin_email"))

    pending = fetch_pending_dashboard_users(limit=10)
    if not pending:
        await _reply(update, "Tidak ada akun yang menunggu verifikasi.")
        return

    lines = ["Daftar akun pending (maks 10):"]
    for user in pending:
        name = user.get("full_name") or "-"
        role = user.get("role") or "-"
        kecamatan = user.get("kecamatan_name") or "-"
        lines.append(f"{user.get('id')} - {name} ({role}) | {kecamatan}")
    lines.append("")
    lines.append("Gunakan /approve ID atau /reject ID alasan.")
    await _reply(update, "\n".join(lines))


async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.admin")
    admin = _authorize_admin(update)
    if not admin:
        await _reply(update, "Akun ini belum terdaftar sebagai admin Telegram.")
        return

    _log_command(update, "/approve " + " ".join(context.args or []))
    logger.info("Admin %s menjalankan /approve.", admin.get("admin_email"))

    if not context.args:
        await _reply(update, "Format: /approve <ID> (contoh: /approve 123)")
        return

    try:
        user_id = int(context.args[0])
    except (TypeError, ValueError):
        await _reply(update, "ID tidak valid. Gunakan angka.")
        return

    note = " ".join(context.args[1:]).strip() or None
    user = fetch_dashboard_user_basic(user_id)
    if not user:
        await _reply(update, "User tidak ditemukan.")
        return

    current_status = (user.get("account_status") or "").strip().lower()
    if current_status in {"approved", "rejected"}:
        await _reply(update, f"User sudah diproses sebelumnya ({_status_label(current_status)}).")
        return
    if current_status and current_status != "pending":
        await _reply(update, f"Status user saat ini {_status_label(current_status)}.")
        return

    try:
        updated = update_dashboard_user_verification(
            user_id=user_id,
            status="approved",
            verified_by=admin.get("dashboard_user_id"),
            note=note,
        )
    except Exception:
        logger.exception("Gagal update approve via command.")
        await _reply(update, "Gagal memperbarui status user.")
        return

    if updated:
        actor_username = _normalize_username(getattr(update.effective_user, "username", None))
        actor_name = admin.get("admin_name") or admin.get("admin_email")
        source_chat = update.effective_chat
        exclude_chat_ids = (
            {int(source_chat.id)}
            if source_chat and getattr(source_chat, "id", None) is not None
            else None
        )
        try:
            notify_verification_status_update(
                user_id=user_id,
                full_name=user.get("full_name"),
                status_label="✅ Disetujui",
                actor_name=actor_name,
                actor_username=actor_username,
                exclude_chat_ids=exclude_chat_ids,
            )
        except Exception:
            logger.exception("Gagal mengirim broadcast approve via command.")
        _log_verification_activity(
            admin_user_id=admin.get("dashboard_user_id"),
            user_id=user_id,
            full_name=user.get("full_name"),
            status="approved",
            reviewer_note=note,
        )
        await _reply(update, f"✅ User {user.get('full_name') or user_id} telah disetujui.")
    else:
        await _reply(update, "Status user tidak berubah.")


async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.admin")
    admin = _authorize_admin(update)
    if not admin:
        await _reply(update, "Akun ini belum terdaftar sebagai admin Telegram.")
        return

    _log_command(update, "/reject " + " ".join(context.args or []))
    logger.info("Admin %s menjalankan /reject.", admin.get("admin_email"))

    if not context.args:
        await _reply(update, "Format: /reject <ID> <alasan>")
        return

    try:
        user_id = int(context.args[0])
    except (TypeError, ValueError):
        await _reply(update, "ID tidak valid. Gunakan angka.")
        return

    note = " ".join(context.args[1:]).strip() or None
    user = fetch_dashboard_user_basic(user_id)
    if not user:
        await _reply(update, "User tidak ditemukan.")
        return

    current_status = (user.get("account_status") or "").strip().lower()
    if current_status in {"approved", "rejected"}:
        await _reply(update, f"User sudah diproses sebelumnya ({_status_label(current_status)}).")
        return
    if current_status and current_status != "pending":
        await _reply(update, f"Status user saat ini {_status_label(current_status)}.")
        return

    try:
        updated = update_dashboard_user_verification(
            user_id=user_id,
            status="rejected",
            verified_by=admin.get("dashboard_user_id"),
            note=note,
        )
    except Exception:
        logger.exception("Gagal update reject via command.")
        await _reply(update, "Gagal memperbarui status user.")
        return

    if updated:
        actor_username = _normalize_username(getattr(update.effective_user, "username", None))
        actor_name = admin.get("admin_name") or admin.get("admin_email")
        source_chat = update.effective_chat
        exclude_chat_ids = (
            {int(source_chat.id)}
            if source_chat and getattr(source_chat, "id", None) is not None
            else None
        )
        try:
            notify_verification_status_update(
                user_id=user_id,
                full_name=user.get("full_name"),
                status_label="❌ Ditolak",
                actor_name=actor_name,
                actor_username=actor_username,
                exclude_chat_ids=exclude_chat_ids,
            )
        except Exception:
            logger.exception("Gagal mengirim broadcast reject via command.")
        _log_verification_activity(
            admin_user_id=admin.get("dashboard_user_id"),
            user_id=user_id,
            full_name=user.get("full_name"),
            status="rejected",
            reviewer_note=note,
        )
        await _reply(update, f"❌ User {user.get('full_name') or user_id} telah ditolak.")
    else:
        await _reply(update, "Status user tidak berubah.")


async def admin_register_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.admin")
    admin = _authorize_admin(update)
    if not admin:
        await _reply(update, "Akun ini belum terdaftar sebagai admin Telegram.")
        return

    _log_command(update, "/register_group")
    logger.info("Admin %s mencoba register grup.", admin.get("admin_email"))

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await _reply(update, "Perintah ini harus dijalankan di dalam grup.")
        return

    try:
        upsert_telegram_notification_group(
            chat_id=int(chat.id),
            title=chat.title or None,
            created_by=admin.get("dashboard_user_id"),
        )
    except Exception:
        logger.exception("Gagal menyimpan grup notifikasi.")
        await _reply(update, "Gagal mendaftarkan grup notifikasi.")
        return

    await _reply(update, "Grup ini berhasil didaftarkan untuk notifikasi.")


async def admin_unregister_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.admin")
    admin = _authorize_admin(update)
    if not admin:
        await _reply(update, "Akun ini belum terdaftar sebagai admin Telegram.")
        return

    _log_command(update, "/unregister_group")
    logger.info("Admin %s mencoba unregister grup.", admin.get("admin_email"))

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await _reply(update, "Perintah ini harus dijalankan di dalam grup.")
        return

    try:
        deleted = delete_telegram_notification_group_by_chat_id(int(chat.id))
    except Exception:
        logger.exception("Gagal menghapus grup notifikasi.")
        await _reply(update, "Gagal menghapus grup notifikasi.")
        return

    if deleted:
        await _reply(update, "Grup ini telah dihapus dari notifikasi.")
    else:
        await _reply(update, "Grup ini belum terdaftar.")


async def handle_verification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.admin")
    query = update.callback_query
    if not query or not query.data:
        return
    try:
        logger.info(
            "Callback diterima: data=%s user=%s chat_id=%s",
            query.data,
            getattr(query.from_user, "username", None),
            getattr(query.message, "chat_id", None),
        )

        admin = _authorize_admin(update)
        if not admin:
            await query.answer("Akun ini belum terdaftar sebagai admin.", show_alert=True)
            return

        parts = query.data.split(":")
        if len(parts) < 3:
            await query.answer("Perintah tidak dikenal.", show_alert=True)
            return

        action = parts[1]
        try:
            user_id = int(parts[2])
        except (TypeError, ValueError):
            await query.answer("ID user tidak valid.", show_alert=True)
            return

        note = None
        if action == "reject":
            note = "Ditolak via Telegram."

        user = fetch_dashboard_user_basic(user_id)
        if not user:
            await query.answer("User tidak ditemukan.", show_alert=True)
            return

        current_status = (user.get("account_status") or "").strip().lower()
        if current_status in {"approved", "rejected"}:
            label = _status_label(current_status)
            await query.answer(f"User sudah {label}.", show_alert=True)
            await _finalize_callback(
                query,
                label,
                None,
                None,
                summary_text=f"Permintaan verifikasi akun ID {user_id} sudah diproses sebelumnya.",
                detail_lines=[f"Nama: {user.get('full_name') or '-'}"],
            )
            return
        if current_status and current_status != "pending":
            label = _status_label(current_status)
            await query.answer("User tidak dalam status pending.", show_alert=True)
            await _finalize_callback(
                query,
                label,
                None,
                None,
                summary_text=f"Permintaan verifikasi akun ID {user_id} tidak bisa diproses.",
                detail_lines=[f"Nama: {user.get('full_name') or '-'}"],
            )
            return

        try:
            if action == "approve":
                updated = update_dashboard_user_verification(
                    user_id=user_id,
                    status="approved",
                    verified_by=admin.get("dashboard_user_id"),
                    note=note,
                )
                status_label = "✅ Disetujui"
            elif action == "reject":
                updated = update_dashboard_user_verification(
                    user_id=user_id,
                    status="rejected",
                    verified_by=admin.get("dashboard_user_id"),
                    note=note,
                )
                status_label = "❌ Ditolak"
            else:
                await query.answer("Aksi tidak dikenal.", show_alert=True)
                return
        except Exception:
            logger.exception("Gagal memperbarui status via callback.")
            await query.answer("Gagal memperbarui status.", show_alert=True)
            return

        if not updated:
            await query.answer("Status user tidak berubah.", show_alert=True)
            return

        actor_username = _normalize_username(getattr(query.from_user, "username", None))
        actor_name = admin.get("admin_name") or admin.get("admin_email")
        source_chat_id = getattr(query.message, "chat_id", None)
        verification_status = "approved" if action == "approve" else "rejected"
        _log_verification_activity(
            admin_user_id=admin.get("dashboard_user_id"),
            user_id=user_id,
            full_name=user.get("full_name"),
            status=verification_status,
            reviewer_note=note,
        )
        await query.answer(f"{status_label}!", show_alert=False)
        try:
            notify_verification_status_update(
                user_id=user_id,
                full_name=user.get("full_name"),
                status_label=status_label,
                actor_name=actor_name,
                actor_username=actor_username,
                exclude_chat_ids={int(source_chat_id)} if source_chat_id is not None else None,
            )
        except Exception:
            logger.exception("Gagal mengirim broadcast update verifikasi akun.")
        await _finalize_callback(
            query,
            status_label,
            actor_name,
            actor_username,
            summary_text=f"Permintaan verifikasi akun ID {user_id} telah diproses.",
            detail_lines=[f"Nama: {user.get('full_name') or '-'}"],
        )
    except Exception:
        logger.exception("Error tidak terduga pada callback.")
        try:
            await query.answer("Terjadi error saat memproses.", show_alert=True)
        except Exception:
            logger.exception("Gagal mengirim answer callback.")


async def handle_guestbook_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("telegram.admin")
    query = update.callback_query
    if not query or not query.data:
        return

    try:
        logger.info(
            "Guestbook callback: data=%s user=%s chat_id=%s",
            query.data,
            getattr(query.from_user, "username", None),
            getattr(query.message, "chat_id", None),
        )

        admin = _authorize_admin(update)
        if not admin:
            await query.answer("Akun ini belum terdaftar sebagai admin.", show_alert=True)
            return

        parts = query.data.split(":")
        if len(parts) < 3:
            await query.answer("Perintah tidak dikenal.", show_alert=True)
            return

        action = parts[1]
        try:
            tx_id = int(parts[2])
        except (TypeError, ValueError):
            await query.answer("ID transaksi tidak valid.", show_alert=True)
            return

        detail = get_transaction_detail(tx_id)
        if not detail:
            await query.answer("Transaksi tidak ditemukan.", show_alert=True)
            return

        existing_markup = getattr(query.message, "reply_markup", None)
        followup_markup = _build_guestbook_followup_markup(
            transaction_id=tx_id,
            existing_markup=existing_markup,
        )
        current_status = (detail.get("status") or "").strip().lower()
        if current_status in {"approved", "rejected"}:
            label = "✅ Disetujui" if current_status == "approved" else "❌ Ditolak"
            await query.answer(f"Transaksi sudah {label}.", show_alert=True)
            final_text = _build_guestbook_callback_message(
                transaction_id=tx_id,
                detail=detail,
                status_label=label,
                actor_name=detail.get("reviewer_name"),
            )
            await _finalize_callback(
                query,
                label,
                None,
                None,
                summary_text=final_text,
                reply_markup=followup_markup,
                include_status_line=False,
            )
            return

        note = None
        if action == "reject":
            note = "Ditolak via Telegram."

        try:
            if action == "approve":
                updated = update_transaction_status(
                    transaction_id=tx_id,
                    status="approved",
                    reviewer_id=admin.get("dashboard_user_id"),
                    reviewer_notes=note,
                )
                status_label = "✅ Disetujui"
            elif action == "reject":
                updated = update_transaction_status(
                    transaction_id=tx_id,
                    status="rejected",
                    reviewer_id=admin.get("dashboard_user_id"),
                    reviewer_notes=note,
                )
                status_label = "❌ Ditolak"
            else:
                await query.answer("Aksi tidak dikenal.", show_alert=True)
                return
        except Exception:
            logger.exception("Gagal memperbarui transaksi buku tamu.")
            await query.answer("Gagal memperbarui transaksi.", show_alert=True)
            return

        if not updated:
            await query.answer("Status transaksi tidak berubah.", show_alert=True)
            return

        actor_username = _normalize_username(getattr(query.from_user, "username", None))
        actor_name = admin.get("admin_name") or admin.get("admin_email")
        source_chat_id = getattr(query.message, "chat_id", None)
        photo_links = _extract_guestbook_photo_links(existing_markup)
        guest_names: list[str] = []
        seen_guest_names: set[str] = set()
        for row in (detail or {}).get("guests") or []:
            guest_name = str((row or {}).get("full_name") or "").strip()
            if not guest_name:
                continue
            guest_key = guest_name.casefold()
            if guest_key in seen_guest_names:
                continue
            seen_guest_names.add(guest_key)
            guest_names.append(guest_name)
        await query.answer(f"{status_label}!", show_alert=False)
        try:
            notify_guestbook_status_update(
                transaction_id=tx_id,
                school_name=detail.get("school_name"),
                status_label=status_label,
                actor_name=actor_name,
                actor_username=actor_username,
                guest_names=guest_names,
                photo_links=photo_links,
                exclude_chat_ids={int(source_chat_id)} if source_chat_id is not None else None,
            )
        except Exception:
            logger.exception("Gagal mengirim broadcast update buku tamu.")
        final_text = _build_guestbook_callback_message(
            transaction_id=tx_id,
            detail=detail,
            status_label=status_label,
            actor_name=actor_name,
        )
        await _finalize_callback(
            query,
            status_label,
            None,
            None,
            summary_text=final_text,
            reply_markup=followup_markup,
            include_status_line=False,
        )
    except Exception:
        logger.exception("Error tidak terduga pada guestbook callback.")
        try:
            await query.answer("Terjadi error saat memproses.", show_alert=True)
        except Exception:
            logger.exception("Gagal mengirim answer callback.")
