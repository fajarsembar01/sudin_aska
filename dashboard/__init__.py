from __future__ import annotations

import atexit
import os
from datetime import timedelta

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from .auth import auth_bp, current_user, init_oauth
from .routes import main_bp
from .portal.routes import portal_bp
from .adiwiyata import adiwiyata_api_bp, adiwiyata_bp
from .hospitality import hospitality_bp
from .supporter import supporter_bp
from .daftar_tamu.routes import daftar_tamu_bp
from .call_center import call_center_api_bp, call_center_bp
from .penugasan import penugasan_bp
from .cms.routes import cms_bp
from .laporan import laporan_bp
from .pengaturan import pengaturan_bp
from .db_access import shutdown_pool
from .queries import fetch_pending_bullying_count, fetch_pending_psych_count, fetch_pending_corruption_count
from .schema import ensure_dashboard_schema, ensure_laporan_schema, ensure_monev_bos_schema
from utils import to_jakarta

from .adiwiyata import adiwiyata_api_bp, adiwiyata_bp
from .auth import auth_bp, current_user, init_oauth
from .call_center import call_center_api_bp, call_center_bp
from .cms.routes import cms_bp
from .daftar_tamu.routes import daftar_tamu_bp
from .db_access import shutdown_pool
from .hospitality import hospitality_bp
from .laporan import laporan_bp
from .penugasan import penugasan_bp
from .portal.routes import portal_bp
from .queries import (
    fetch_pending_bullying_count,
    fetch_pending_corruption_count,
    fetch_pending_psych_count,
)
from .routes import main_bp
from .schema import ensure_dashboard_schema, ensure_laporan_schema
from .supporter import supporter_bp


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = os.getenv("DASHBOARD_SECRET_KEY", "change-me")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        days=int(os.getenv("DASHBOARD_SESSION_DAYS", "14"))
    )
    # Batas ukuran upload — default 50 MB, bisa di-override via env DASHBOARD_MAX_UPLOAD_MB
    _max_upload_mb = int(os.getenv("DASHBOARD_MAX_UPLOAD_MB", "50"))
    app.config["MAX_CONTENT_LENGTH"] = _max_upload_mb * 1024 * 1024

    csrf = CSRFProtect(app)
    from flask_cors import CORS

    CORS(
        app,
        supports_credentials=True,
        resources={
            r"/api/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000"]},
            r"/portal/api/*": {
                "origins": ["http://localhost:3000", "http://127.0.0.1:3000"]
            },
        },
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(adiwiyata_bp)
    app.register_blueprint(hospitality_bp)
    app.register_blueprint(supporter_bp)
    app.register_blueprint(daftar_tamu_bp)
    app.register_blueprint(penugasan_bp)
    app.register_blueprint(call_center_bp)
    csrf.exempt(call_center_api_bp)
    app.register_blueprint(call_center_api_bp)
    app.register_blueprint(adiwiyata_api_bp)
    app.register_blueprint(cms_bp)
    app.register_blueprint(laporan_bp)
    
    from .monev_bos.routes import monev_bos_bp
    app.register_blueprint(monev_bos_bp)
    app.register_blueprint(pengaturan_bp)
    
    # Exempt public API endpoints from CSRF
    from .adiwiyata.routes import api_adiwiyata_likes
    from .routes import api_spmb_evaluation_item, api_spmb_evaluations, api_spmb_queue

    csrf.exempt(api_adiwiyata_likes)
    csrf.exempt(api_spmb_evaluations)
    csrf.exempt(api_spmb_evaluation_item)
    csrf.exempt(api_spmb_queue)

    init_oauth(app)

    if os.getenv("ASKA_DASHBOARD_AUTO_INIT", "1").strip().lower() in {"1", "true", "yes"}:
        try:
            ensure_dashboard_schema()
        except Exception:
            pass
        try:
            ensure_laporan_schema()
        except Exception:
            pass
        try:
            ensure_monev_bos_schema()
        except Exception:
            pass

    @app.before_request
    def check_mandatory_whatsapp():
        from flask import request, redirect, url_for, flash, session
        user = current_user()
        if not user:
            return None

        wa_number = (user.get("whatsapp_number") or user.get("phone") or "").strip()
        role = (user.get("role") or "").strip().lower()

        if not wa_number:
            try:
                from .portal.queries import get_dashboard_user_profile
                db_profile = get_dashboard_user_profile(user["id"])
                if db_profile:
                    wa_number = (db_profile.get("whatsapp_number") or db_profile.get("phone") or "").strip()

                # For sekolah role, check Nomor Operator Sekolah (coordinator_phone) from portal_schools
                if not wa_number and role == "sekolah":
                    from .portal.routes import _fetch_user_school
                    school_info = _fetch_user_school(user["id"])
                    if school_info and school_info.get("metadata"):
                        meta = school_info.get("metadata") or {}
                        coord_phone = (meta.get("coordinator_phone") or meta.get("school_phone") or "").strip()
                        if coord_phone:
                            wa_number = coord_phone
                            from .db_access import get_cursor
                            with get_cursor(commit=True) as cur:
                                cur.execute(
                                    "UPDATE dashboard_users SET whatsapp_number = %s, phone = %s WHERE id = %s",
                                    (coord_phone, coord_phone, user["id"])
                                )

                if wa_number:
                    session_user = session.get("user", {})
                    session_user["whatsapp_number"] = wa_number
                    session_user["phone"] = wa_number
                    session["user"] = session_user
            except Exception:
                pass

        if wa_number:
            return None

        path = request.path or ""
        endpoint = request.endpoint or ""

        # Allow static files and resources
        if path.startswith("/static") or endpoint.startswith("static"):
            return None

        # Allow authentication endpoints
        if path.startswith("/auth") or endpoint.startswith("auth."):
            return None

        # Allow profile pages and profile APIs so user can fill in WhatsApp number
        allowed_endpoints = {
            "portal.profile",
            "portal.sekolah_profile",
            "portal.user_profile_settings",
            "portal.profile_photo",
            "portal.api_sekolah_profile",
            "portal.uploaded_file"
        }
        if endpoint in allowed_endpoints or "/profile" in path or "/sekolah/profile" in path:
            return None

        target_url = url_for("portal.sekolah_profile") if role == "sekolah" else url_for("portal.user_profile_settings")

        flash("Demi kelancaran sistem dan koordinasi, silakan isi Nomor Operator Sekolah pada profil sekolah terlebih dahulu.", "warning")
        return redirect(target_url)

    @app.context_processor
    def inject_globals() -> dict:
        user = current_user()
        pending_count = 0
        pending_psych = 0
        pending_corruption = 0
        user_school = None
        area_contacts = []

        if user:
            try:
                pending_count = fetch_pending_bullying_count()
            except Exception:
                pending_count = 0
            try:
                pending_psych = fetch_pending_psych_count()
            except Exception:
                pending_psych = 0
            try:
                pending_corruption = fetch_pending_corruption_count()
            except Exception:
                pending_corruption = 0

            try:
                from .portal.routes import (
                    _build_coordinator_contacts,
                    _fetch_user_kecamatan_name,
                    _fetch_user_school,
                )

                if user.get("role") == "sekolah":
                    user_school = _fetch_user_school(user.get("id"))
                    area_contacts = _build_coordinator_contacts(user_school)
                else:
                    user_area_name = _fetch_user_kecamatan_name(user.get("id"))
                    area_contacts = _build_coordinator_contacts(
                        None, area_name=user_area_name
                    )
            except Exception:
                area_contacts = []

        # Call Center unread badge
        cc_unread_count = 0
        admin_pending = None
        admin_notification_items = []
        if user and user.get("role") == "admin":
            try:
                from .call_center.queries import fetch_cc_unread_total

                cc_unread_count = fetch_cc_unread_total()
            except Exception:
                cc_unread_count = 0
            try:
                from flask import url_for

                from .portal.queries import fetch_admin_pending_summary

                admin_pending = fetch_admin_pending_summary()
                admin_notification_items = [
                    {"href": url_for("portal.manage_users"), "title": "User baru", "subtitle": "Menunggu verifikasi akun", "count": admin_pending.get("pending_users", 0), "item_id": "adminPendingUsersItem", "count_id": "adminPendingUsersCount", "badge_class": "bg-warning text-dark"},
                    {"href": url_for("portal.admin_manage_staff"), "title": "Permintaan penugasan", "subtitle": "Koordinator ajukan penugasan staff", "count": admin_pending.get("pending_assignment_requests", 0), "item_id": "adminPendingAssignmentItem", "count_id": "adminPendingAssignmentCount", "badge_class": "bg-info text-dark"},
                    {"href": url_for("portal.manage_monev_teams"), "title": "Permintaan anggota tim", "subtitle": "Persetujuan anggota monev", "count": admin_pending.get("pending_team_member_requests", 0), "item_id": "adminPendingTeamItem", "count_id": "adminPendingTeamCount", "badge_class": "bg-primary"},
                    {"href": url_for("portal.admin_reopen_requests"), "title": "Permintaan reopen", "subtitle": "Penilaian diajukan untuk dibuka", "count": admin_pending.get("pending_reopen_requests", 0), "item_id": "adminPendingReopenItem", "count_id": "adminPendingReopenCount", "badge_class": "bg-danger"},
                    {"href": url_for("daftar_tamu.admin_validation"), "title": "Verifikasi daftar tamu", "subtitle": "Transaksi buku tamu menunggu validasi", "count": admin_pending.get("pending_guestbook", 0), "item_id": "adminPendingGuestbookItem", "count_id": "adminPendingGuestbookCount", "badge_class": "bg-success"},
                    {"href": url_for("monev_bos.admin_edit_requests"), "title": "Pengajuan edit Monev BOS/BOP", "subtitle": "Permintaan ubah data kegiatan divalidasi", "count": admin_pending.get("pending_monev_edit_requests", 0), "item_id": "adminPendingMonevEditItem", "count_id": "adminPendingMonevEditCount", "badge_class": "bg-warning text-dark"},
                    {"href": url_for("call_center.inbox"), "title": "Call Center", "subtitle": "Pesan masuk belum dibaca", "count": admin_pending.get("pending_call_center", 0), "item_id": "adminPendingCCItem", "count_id": "adminPendingCCCount", "badge_class": "text-bg-danger"},
                ]
            except Exception:
                admin_pending = {"total": 0}
                admin_notification_items = []

        try:
            from .portal.permissions import get_permission_summary

            permissions = (
                get_permission_summary(user) if user else get_permission_summary({})
            )
        except Exception:
            permissions = {}

        return {
            "current_user": user,
            "pending_bullying_count": pending_count,
            "pending_psych_count": pending_psych,
            "pending_corruption_count": pending_corruption,
            "user_school": user_school,
            "area_contacts": area_contacts,
            "cc_unread_count": cc_unread_count,
            "admin_pending": admin_pending,
            "admin_notification_items": admin_notification_items,
            "permissions": permissions,
        }

    @app.template_filter("jakarta")
    def format_jakarta(value, fmt="%d %b %Y %H:%M"):
        if value is None:
            return ""
        dt = to_jakarta(value)
        try:
            return dt.strftime(fmt)
        except Exception:
            return ""

    @app.template_filter("mask_email")
    def mask_email(value, first=2, last=1):
        if value is None:
            return ""

        email = str(value)
        name, domain = email.split("@", 1)
        if not name:
            return "@" + domain

        # Logic jika nama email terlalu pendek, berlaku untuk first = 2 dan last = 1
        if len(name) <= first + last:
            if len(name) == 1:
                masked_name = name[0] + 7 * "*" + name[0]
            elif len(name) == 2:
                masked_name = name[0] + 7 * "*" + name[1]
            else:
                masked_name = name[:first] + 7 * "*" + name[-last:]
        else:
            masked_name = name[:first] + 7 * "*" + name[-last:]

        return masked_name + "@" + domain

    atexit.register(shutdown_pool)

    return app
