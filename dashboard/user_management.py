from __future__ import annotations

import re
from typing import Optional
from uuid import uuid4
import secrets

from flask import Response, current_app, flash, jsonify, render_template, request
from werkzeug.security import generate_password_hash

from dashboard.queries import (
    create_dashboard_user,
    list_dashboard_users,
    merge_dashboard_users,
    update_dashboard_user,
)
from dashboard.portal.queries import fetch_activity_logs, get_school_by_id, list_kecamatan, log_activity


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", ".", (value or "").strip().lower())
    cleaned = cleaned.strip(".")
    return cleaned or "user"


def _build_unregistered_email(full_name: str) -> str:
    token = uuid4().hex[:8]
    return f"unregistered+{_slugify(full_name)}-{token}@aska.local"


def handle_manage_users(*, actor: Optional[dict], base_template: str) -> Response:
    """Shared handler for dashboard user management across apps."""
    actor_id = actor.get("id") if actor else None

    if request.method == "POST":
        action = request.form.get("action", "create")
        user_id = request.form.get("user_id")
        wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        email = (request.form.get("email") or "").strip().lower()
        full_name = (request.form.get("full_name") or "").strip()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "viewer").strip()
        account_status = (request.form.get("account_status") or "").strip() or None
        reviewer_note = (request.form.get("reviewer_note") or "").strip() or None
        jabatan = (request.form.get("jabatan") or "").strip() or None

        is_unregistered = request.form.get("is_unregistered") in {"1", "true", "on", "yes"}
        if is_unregistered:
            account_status = "not_registered"

        school_id_raw = (request.form.get("school_id") or "").strip()
        school_id = int(school_id_raw) if school_id_raw.isdigit() else None
        if role != "sekolah":
            school_id = None

        requested_kecamatan_raw = (request.form.get("requested_kecamatan") or "").strip()
        requested_kecamatan = int(requested_kecamatan_raw) if requested_kecamatan_raw.isdigit() else None

        try:
            if action == "create":
                if is_unregistered:
                    if not full_name or not jabatan or requested_kecamatan is None:
                        flash("Nama, jabatan, dan kecamatan wajib diisi untuk akun belum register.", "warning")
                    else:
                        placeholder_email = _build_unregistered_email(full_name)
                        secret = secrets.token_urlsafe(18)
                        password_hash = generate_password_hash(secret, method="pbkdf2:sha256", salt_length=12)
                        new_user_id = create_dashboard_user(
                            email=placeholder_email,
                            full_name=full_name,
                            password_hash=password_hash,
                            role=role,
                            school_id=school_id,
                            requested_kecamatan=requested_kecamatan,
                            jabatan=jabatan,
                            account_status=account_status,
                        )
                        details = {
                            "email": placeholder_email,
                            "role": role,
                            "account_status": account_status,
                        }
                        if jabatan:
                            details["jabatan"] = jabatan
                        if requested_kecamatan is not None:
                            details["kecamatan_id"] = requested_kecamatan
                        if school_id is not None:
                            details["school_id"] = school_id
                            school = get_school_by_id(school_id)
                            if school:
                                details["school_name"] = school.get("name")
                                details["npsn"] = school.get("npsn")
                        log_activity(actor_id, "CREATE", "USER", new_user_id, full_name or placeholder_email, details)
                        flash(f"User {full_name} berhasil dibuat (belum register).", "success")
                else:
                    if not all([email, full_name, password]):
                        flash("Semua field wajib diisi.", "warning")
                    else:
                        password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=12)
                        new_user_id = create_dashboard_user(
                            email=email,
                            full_name=full_name,
                            password_hash=password_hash,
                            role=role,
                            school_id=school_id,
                            requested_kecamatan=requested_kecamatan,
                            jabatan=jabatan,
                            account_status=account_status,
                        )
                        details = {
                            "email": email,
                            "role": role,
                        }
                        if account_status:
                            details["account_status"] = account_status
                        if jabatan:
                            details["jabatan"] = jabatan
                        if requested_kecamatan is not None:
                            details["kecamatan_id"] = requested_kecamatan
                        if school_id is not None:
                            details["school_id"] = school_id
                            school = get_school_by_id(school_id)
                            if school:
                                details["school_name"] = school.get("name")
                                details["npsn"] = school.get("npsn")
                        log_activity(actor_id, "CREATE", "USER", new_user_id, full_name or email, details)
                        flash(f"User {full_name} berhasil dibuat.", "success")

            elif action == "update":
                if not user_id:
                    flash("ID User tidak valid.", "danger")
                else:
                    pw_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=12) if password else None
                    updated = update_dashboard_user(
                        user_id=int(user_id),
                        full_name=full_name,
                        role=role,
                        email=email,
                        password_hash=pw_hash,
                        account_status=account_status,
                        school_id=school_id,
                        requested_kecamatan=requested_kecamatan,
                        jabatan=jabatan,
                    )
                    if updated:
                        details = {
                            "email": email,
                            "role": role,
                        }
                        if account_status:
                            details["account_status"] = account_status
                        if jabatan is not None:
                            details["jabatan"] = jabatan
                        if requested_kecamatan is not None:
                            details["kecamatan_id"] = requested_kecamatan
                        if school_id is not None:
                            details["school_id"] = school_id
                            school = get_school_by_id(school_id)
                            if school:
                                details["school_name"] = school.get("name")
                                details["npsn"] = school.get("npsn")
                        log_activity(actor_id, "UPDATE", "USER", int(user_id), full_name or email, details)
                    flash(f"Data user {full_name} berhasil diperbarui.", "success")

            elif action == "verify":
                if not user_id or not account_status:
                    message = "Data tidak lengkap."
                    if wants_json:
                        return jsonify({"success": False, "message": message}), 400
                    flash(message, "warning")
                else:
                    updated = update_dashboard_user(
                        user_id=int(user_id),
                        full_name=full_name,
                        role=role,
                        account_status=account_status,
                    )
                    if updated:
                        details = {"account_status": account_status, "info": "verify"}
                        if reviewer_note:
                            details["reviewer_note"] = reviewer_note
                        log_activity(actor_id, "UPDATE", "USER", int(user_id), full_name or email, details)
                    if wants_json:
                        status_code = 200 if updated else 400
                        return jsonify(
                            {"success": bool(updated), "user_id": int(user_id), "account_status": account_status}
                        ), status_code
                    flash(f"Status user berhasil diubah menjadi {account_status}.", "success")

            elif action == "merge":
                old_user_id = request.form.get("old_user_id")
                new_user_id = request.form.get("new_user_id")
                if not old_user_id or not new_user_id:
                    flash("Pilih akun lama dan akun baru untuk merge.", "warning")
                else:
                    result = merge_dashboard_users(int(old_user_id), int(new_user_id), merged_by=actor_id)
                    details = {
                        "old_user_id": int(old_user_id),
                        "new_user_id": int(new_user_id),
                        "old_email": (result.get("old_user") or {}).get("email"),
                        "new_email": (result.get("new_user") or {}).get("email"),
                    }
                    log_activity(actor_id, "MERGE", "USER", int(new_user_id), full_name or "Merge User", details)
                    flash("Akun berhasil di-merge. Akun lama dinonaktifkan.", "success")

        except Exception as exc:
            current_app.logger.error(f"Error managing user: {exc}")
            if wants_json:
                return jsonify({"success": False, "message": str(exc)}), 500
            flash(f"Gagal memproses data: {exc}", "danger")

    users = list_dashboard_users()
    kecamatan_list = list_kecamatan()
    activity_logs = fetch_activity_logs(limit=50, target_types=("USER",))

    return render_template(
        "portal/admin/manage_users.html",
        users=users,
        kecamatan_list=kecamatan_list,
        activity_logs=activity_logs,
        base_template=base_template,
    )
