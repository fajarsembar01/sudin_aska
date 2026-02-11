from __future__ import annotations

from typing import Optional
import logging

from telegram import Update
from telegram.ext import ContextTypes

from db import save_chat
from dashboard.queries import (
    fetch_dashboard_user_basic,
    fetch_pending_dashboard_users,
    get_telegram_admin_by_username,
    update_dashboard_user_verification,
    upsert_telegram_notification_group,
    delete_telegram_notification_group_by_chat_id,
)
from dashboard.daftar_tamu.queries import get_transaction_detail, update_transaction_status


def _normalize_username(username: Optional[str]) -> Optional[str]:
    if not username:
        return None
    cleaned = username.strip().lstrip("@").lower()
    return cleaned or None


def _log_command(update: Update, text: str) -> None:
    user = update.effective_user
    if not user:
        return
    username = user.username or user.first_name or "admin"
    save_chat(user.id, username, text, role="user", topic=None)


async def _reply(update: Update, text: str) -> None:
    message = update.effective_message
    if message:
        await message.reply_text(text)


async def _finalize_callback(
    query,
    status_label: str,
    actor_name: Optional[str],
    actor_username: Optional[str],
) -> None:
    logger = logging.getLogger("telegram.admin")
    message = query.message
    if actor_name and actor_username:
        suffix_actor = f" oleh {actor_name} (@{actor_username})"
    elif actor_name:
        suffix_actor = f" oleh {actor_name}"
    elif actor_username:
        suffix_actor = f" oleh @{actor_username}"
    else:
        suffix_actor = ""
    if message and message.text:
        suffix = f"\n\nStatus: {status_label}{suffix_actor}"
        if suffix not in message.text:
            new_text = message.text + suffix
            try:
                await query.edit_message_text(new_text)
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
        await message.reply_text(f"Status: {status_label}{suffix_actor}")


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

    if user.get("account_status") == "approved":
        await _reply(update, "User sudah disetujui sebelumnya.")
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

    if user.get("account_status") == "rejected":
        await _reply(update, "User sudah ditolak sebelumnya.")
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
        await query.answer(f"{status_label}!", show_alert=False)
        await _finalize_callback(query, status_label, actor_name, actor_username)
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

        current_status = (detail.get("status") or "").strip().lower()
        if current_status in {"approved", "rejected"}:
            label = "✅ Disetujui" if current_status == "approved" else "❌ Ditolak"
            await query.answer(f"Transaksi sudah {label}.", show_alert=True)
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
        await query.answer(f"{status_label}!", show_alert=False)
        await _finalize_callback(query, status_label, actor_name, actor_username)
    except Exception:
        logger.exception("Error tidak terduga pada guestbook callback.")
        try:
            await query.answer("Terjadi error saat memproses.", show_alert=True)
        except Exception:
            logger.exception("Gagal mengirim answer callback.")
