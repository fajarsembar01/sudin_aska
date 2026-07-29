from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from dashboard.auth import current_user, role_required
from dashboard.queries import (
    list_admin_users,
    fetch_telegram_notification_settings,
    upsert_telegram_notification_settings,
    list_telegram_admin_accounts,
    upsert_telegram_admin_accounts,
    delete_telegram_admin_account,
    list_telegram_notification_groups,
    delete_telegram_notification_group,
)
from dashboard.telegram_notifications import send_test_notification
from .queries import (
    get_all_system_settings,
    get_system_setting,
    update_system_settings,
    get_system_diagnostic_info,
    list_public_api_keys,
    create_public_api_key,
    toggle_public_api_key_status,
    delete_public_api_key,
    verify_public_api_key,
    fetch_public_schools_api_data,
)

pengaturan_bp = Blueprint("pengaturan", __name__, url_prefix="/pengaturan", template_folder="templates")


@pengaturan_bp.route("/", methods=["GET", "POST"])
@pengaturan_bp.route("/admin", methods=["GET", "POST"])
@role_required("admin")
def admin_settings() -> Response | str:
    user = current_user() or {}
    if not user:
        flash("Silakan login terlebih dahulu.", "warning")
        return redirect(url_for("auth.login"))

    user_id = user.get("id")

    if request.method == "POST":
        action = (request.form.get("action") or "save_settings").strip()
        active_tab = request.form.get("active_tab", "general")

        if action == "save_settings":
            settings_payload = {
                # General Settings
                "app_name": request.form.get("app_name", "").strip(),
                "app_subtitle": request.form.get("app_subtitle", "").strip(),
                "organization_name": request.form.get("organization_name", "").strip(),
                "support_email": request.form.get("support_email", "").strip(),
                "support_phone": request.form.get("support_phone", "").strip(),
                "maintenance_mode": "true" if request.form.get("maintenance_mode") == "on" else "false",
                "maintenance_message": request.form.get("maintenance_message", "").strip(),
                "session_timeout_minutes": request.form.get("session_timeout_minutes", "120").strip(),
                "allow_user_registration": "true" if request.form.get("allow_user_registration") == "on" else "false",

                # Notification Settings
                "telegram_notifications_enabled": "true" if request.form.get("telegram_notifications_enabled") == "on" else "false",
                "telegram_bot_token": request.form.get("telegram_bot_token", "").strip(),
                "telegram_chat_id": request.form.get("telegram_chat_id", "").strip(),
                "whatsapp_notifications_enabled": "true" if request.form.get("whatsapp_notifications_enabled") == "on" else "false",
                "email_notifications_enabled": "true" if request.form.get("email_notifications_enabled") == "on" else "false",
                "notify_on_new_login": "true" if request.form.get("notify_on_new_login") == "on" else "false",
                "notify_on_system_error": "true" if request.form.get("notify_on_system_error") == "on" else "false",
                "notify_daily_summary": "true" if request.form.get("notify_daily_summary") == "on" else "false",

                # API Settings
                "whatsapp_api_endpoint": request.form.get("whatsapp_api_endpoint", "").strip(),
                "whatsapp_api_key": request.form.get("whatsapp_api_key", "").strip(),
                "telegram_webhook_url": request.form.get("telegram_webhook_url", "").strip(),
                "api_rate_limit_per_min": request.form.get("api_rate_limit_per_min", "60").strip(),
                "api_access_enabled": "true" if request.form.get("api_access_enabled") == "on" else "false",
            }

            success = update_system_settings(settings_payload, user_id=user_id)
            if success:
                flash("Pengaturan aplikasi berhasil diperbarui!", "success")
            else:
                flash("Gagal memperbarui pengaturan aplikasi.", "danger")
            return redirect(url_for("pengaturan.admin_settings", tab=active_tab))

        elif action == "save_token":
            raw_token = (request.form.get("bot_token") or "").strip()
            upsert_telegram_notification_settings(raw_token, user_id)
            update_system_settings({"telegram_bot_token": raw_token}, user_id=user_id)
            flash("Token bot Telegram berhasil disimpan.", "success")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

        elif action == "add_admins":
            admin_users = list_admin_users()
            admin_ids = {str(u.get("id")) for u in admin_users if u.get("id") is not None}
            raw_usernames = request.form.getlist("telegram_username[]")
            raw_admin_ids = request.form.getlist("dashboard_user_id[]")
            errors = []
            entries_map = {}

            for idx, (raw_username, raw_admin_id) in enumerate(zip(raw_usernames, raw_admin_ids), start=1):
                username = (raw_username or "").strip()
                admin_id = (raw_admin_id or "").strip()
                if not username and not admin_id:
                    continue

                normalized = username.lstrip("@").strip().lower()
                if not normalized:
                    errors.append(f"Username Telegram di baris {idx} kosong.")
                    continue
                if admin_id not in admin_ids:
                    errors.append(f"Admin dashboard belum dipilih untuk @{normalized}.")
                    continue

                entries_map[normalized] = int(admin_id)

            if entries_map:
                payload = [
                    {"telegram_username": username, "dashboard_user_id": admin_id}
                    for username, admin_id in entries_map.items()
                ]
                saved = upsert_telegram_admin_accounts(payload, created_by=user_id)
                flash(f"{saved} admin Telegram berhasil disimpan.", "success")
            else:
                if not errors:
                    flash("Tidak ada admin Telegram baru yang disimpan.", "warning")

            for error in errors:
                flash(error, "warning")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

        elif action == "delete_admin":
            mapping_id = request.form.get("mapping_id") or ""
            if mapping_id.isdigit():
                deleted = delete_telegram_admin_account(int(mapping_id))
                if deleted:
                    flash("Admin Telegram berhasil dihapus.", "success")
                else:
                    flash("Admin Telegram tidak ditemukan.", "warning")
            else:
                flash("ID admin tidak valid.", "danger")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

        elif action == "delete_group":
            group_id = request.form.get("group_id") or ""
            if group_id.isdigit():
                deleted = delete_telegram_notification_group(int(group_id))
                if deleted:
                    flash("Grup Telegram berhasil dihapus.", "success")
                else:
                    flash("Grup Telegram tidak ditemukan.", "warning")
            else:
                flash("ID grup tidak valid.", "danger")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

        elif action in ["test_notification", "test_telegram"]:
            raw_message = request.form.get("test_message") or ""
            result = send_test_notification(raw_message)
            if result.get("skipped") == "token_missing":
                flash("Token bot Telegram belum diisi.", "warning")
            else:
                sent = int(result.get("sent") or 0)
                group_sent = int(result.get("group_sent") or 0)
                missing = result.get("missing_usernames") or []
                if sent == 0 and group_sent == 0:
                    flash("Tes notifikasi belum terkirim. Pastikan admin sudah chat bot atau grup terdaftar.", "warning")
                else:
                    flash(f"Tes notifikasi terkirim ke {sent} admin dan {group_sent} grup.", "success")
                if missing:
                    flash(f"{len(missing)} admin belum pernah chat bot.", "warning")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

    raw_settings = get_all_system_settings()
    settings_dict = {k: v["setting_value"] for k, v in raw_settings.items()}
    telegram_settings = fetch_telegram_notification_settings() or {}
    admin_users = list_admin_users()
    telegram_admins = list_telegram_admin_accounts()
    telegram_groups = list_telegram_notification_groups()
    system_info = get_system_diagnostic_info()
    active_tab = request.args.get("tab", "general")

    return render_template(
        "pengaturan/admin_settings.html",
        settings=settings_dict,
        settings_raw=raw_settings,
        telegram_settings=telegram_settings,
        admin_users=admin_users,
        telegram_admins=telegram_admins,
        telegram_groups=telegram_groups,
        system_info=system_info,
        active_tab=active_tab,
        page_title="Pengaturan Aplikasi Dashboard",
    )


@pengaturan_bp.route("/public-api", methods=["GET", "POST"])
@role_required("admin")
def public_api_settings() -> Response | str:
    user = current_user() or {}
    if not user:
        flash("Silakan login terlebih dahulu.", "warning")
        return redirect(url_for("auth.login"))

    user_id = user.get("id")

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        if action == "create_key":
            client_name = (request.form.get("client_name") or "").strip()
            contact_email = (request.form.get("contact_email") or "").strip()
            notes = (request.form.get("notes") or "").strip()
            scopes = request.form.getlist("scopes[]") or ["schools:read"]

            if not client_name:
                flash("Nama instansi / client wajib diisi.", "warning")
            else:
                created = create_public_api_key(
                    client_name=client_name,
                    contact_email=contact_email,
                    scopes=scopes,
                    notes=notes,
                    created_by=user_id,
                )
                if created:
                    flash(f"Public API Key untuk '{client_name}' berhasil dibuat!", "success")
                else:
                    flash("Gagal membuat Public API Key.", "danger")
            return redirect(url_for("pengaturan.public_api_settings"))

        elif action == "toggle_status":
            key_id = request.form.get("key_id") or ""
            if key_id.isdigit():
                toggled = toggle_public_api_key_status(int(key_id))
                if toggled:
                    flash("Status Public API Key berhasil diperbarui.", "success")
                else:
                    flash("API Key tidak ditemukan.", "warning")
            return redirect(url_for("pengaturan.public_api_settings"))

        elif action == "delete_key":
            key_id = request.form.get("key_id") or ""
            if key_id.isdigit():
                deleted = delete_public_api_key(int(key_id))
                if deleted:
                    flash("Public API Key berhasil dihapus.", "success")
                else:
                    flash("API Key tidak ditemukan.", "warning")
            return redirect(url_for("pengaturan.public_api_settings"))

    api_keys = list_public_api_keys()
    return render_template(
        "pengaturan/public_api.html",
        api_keys=api_keys,
        page_title="API Publik Instansi",
    )


@pengaturan_bp.route("/api/v1/public/schools", methods=["GET"])
def public_api_schools() -> Response:
    """Public JSON API Endpoint to fetch school data for authorized external clients."""
    # Read API Key from HTTP Header 'X-API-Key' or URL parameter 'api_key'
    api_key = request.headers.get("X-API-Key") or request.args.get("api_key") or ""

    verified = verify_public_api_key(api_key, required_scope="schools:read")
    if not verified:
        return jsonify({
            "status": "error",
            "message": "Autentikasi gagal. API Key tidak valid, nonaktif, atau tidak memiliki izin akses (schools:read).",
            "code": 401,
        }), 401

    schools = fetch_public_schools_api_data()
    return jsonify({
        "status": "success",
        "client": verified.get("client_name"),
        "total": len(schools),
        "data": schools,
    })
