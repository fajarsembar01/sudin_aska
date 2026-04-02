from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import secrets
import re
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash, send_from_directory, abort, make_response
from authlib.integrations.flask_client import OAuth

from .handlers import process_channel_request, process_web_request, web_sessions, reload_qa_chain
from .feedback_routes import feedback_bp
from db import (
    save_chat,
    get_or_create_web_user,
    get_chat_history,
    get_corruption_report,
    get_chat_quota_status,
    consume_chat_quota,
    get_web_user_status,
    DEFAULT_LIMITED_QUOTA,
    DEFAULT_LIMITED_REASON,
    get_whatsapp_user_status,
    get_portal_school_by_npsn,
    create_public_guestbook_transaction,
    get_public_guestbook_review_by_token,
    submit_public_guestbook_review,
    find_general_guest_by_phone,
    list_guestbook_purpose_keywords,
    list_guestbook_contact_priorities,
)
from account_status import BLOCKING_STATUSES, build_status_notice, ACCOUNT_STATUS_ACTIVE
from responses import detect_bullying_category, is_corruption_report_intent
from reporting_flags import reporting_enabled
from utils import normalize_input, replace_bot_mentions, to_jakarta

LIMIT_BLOCK_MESSAGE = (
    f"Ups! Kuota {DEFAULT_LIMITED_QUOTA} chat untuk akses Gmail sudah habis. "
    "Tunggu hitung mundur selesai atau login pakai akun belajar.id / Telegram biar bebas limit ya! 🚀"
)
GMAIL_ALLOWED_DOMAINS = {"gmail.com", "googlemail.com"}
WEB_BOT_USERNAME = "ASKA_WEB"


def _run_async(coro):
    """Safely run an async coroutine from a sync Flask/gunicorn context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside a running loop — offload to a new thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


def create_app() -> Flask:
    """Create and configure an instance of the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    # Secret key for session management
    app.config["SECRET_KEY"] = os.getenv("APP_SECRET_KEY", "a-very-secret-key-that-you-should-change")

    # Initialize OAuth
    oauth = OAuth(app)

    # Configure Google OAuth client
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    @app.template_filter("jakarta")
    def format_jakarta(value, fmt="%d %b %Y %H:%M"):
        if value is None:
            return ""
        dt = to_jakarta(value)
        try:
            return dt.strftime(fmt)
        except Exception:
            return ""

    def _add_no_cache_headers(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    def _serialize_quota_payload(quota_state: dict | None) -> dict:
        quota_state = quota_state or {}
        reset_at = quota_state.get("quota_reset_at")
        if hasattr(reset_at, "isoformat"):
            reset_at = reset_at.isoformat()
        access_tier = quota_state.get("access_tier") or "full"
        limited_reason = quota_state.get("limited_reason")
        if access_tier == "limited" and not limited_reason:
            limited_reason = DEFAULT_LIMITED_REASON
        return {
            "accessTier": access_tier,
            "quotaLimit": quota_state.get("quota_limit"),
            "quotaRemaining": quota_state.get("quota_remaining"),
            "quotaResetAt": reset_at,
            "limitedReason": limited_reason,
        }

    def _portal_register_url() -> str | None:
        raw = (
            os.getenv("PORTAL_REGISTER_URL")
            or os.getenv("PORTAL_BASE_URL")
            or os.getenv("DASHBOARD_BASE_URL")
        )
        if not raw:
            return None
        raw = raw.strip().rstrip("/")
        if raw.endswith("/portal/register"):
            return raw
        return f"{raw}/portal/register"

    def _normalize_url(value: str) -> str:
        clean = (value or "").strip()
        if not clean:
            return ""
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        return f"https://{clean}"

    def _normalize_instagram(value: str) -> str:
        clean = (value or "").strip()
        if not clean:
            return ""
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        if "instagram.com" in clean:
            return _normalize_url(clean)
        username = clean.lstrip("@")
        return f"https://instagram.com/{username}"

    def _normalize_wa_channel(value: str) -> str:
        clean = (value or "").strip()
        if not clean:
            return ""
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        if clean.startswith("whatsapp.com/") or clean.startswith("wa.me/"):
            return _normalize_url(clean)
        return f"https://whatsapp.com/channel/{clean}"

    def _normalize_phone(value: str) -> str:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if not digits:
            return ""
        if digits.startswith("0"):
            digits = "62" + digits[1:]
        return digits

    def _normalize_whatsapp_user_id(value: object) -> Optional[int]:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        if not digits:
            return None
        try:
            return int(digits)
        except (TypeError, ValueError):
            return None

    def _build_contact_buttons(school: dict | None) -> list[dict]:
        if not school:
            return []
        meta = school.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}

        contacts = {
            "website": _normalize_url(meta.get("website") or ""),
            "email": (meta.get("cs_email") or meta.get("email") or "").strip(),
            "phone": _normalize_phone(meta.get("school_phone") or meta.get("phone") or ""),
            "instagram": _normalize_instagram(meta.get("instagram") or ""),
            "wa_channel": _normalize_wa_channel(meta.get("wa_channel") or ""),
        }

        icon_map = {
            "website": {"icon": "bi-globe2", "label": "Website sekolah", "target": "_blank"},
            "email": {"icon": "bi-envelope", "label": "Email sekolah", "target": None},
            "phone": {"icon": "bi-telephone", "label": "Telepon sekolah", "target": None},
            "instagram": {"icon": "bi-instagram", "label": "Instagram sekolah", "target": "_blank"},
            "wa_channel": {"icon": "bi-whatsapp", "label": "WhatsApp Channel sekolah", "target": "_blank"},
        }

        ordered_keys = list_guestbook_contact_priorities(active_only=True)
        if not ordered_keys:
            ordered_keys = ["website", "email", "phone", "instagram", "wa_channel"]

        buttons = []
        for key in ordered_keys:
            value = contacts.get(key)
            if not value:
                continue
            if key == "email":
                href = f"mailto:{value}"
            elif key == "phone":
                href = f"tel:+{value}"
            else:
                href = value
            meta_info = icon_map.get(key, {})
            buttons.append(
                {
                    "key": key,
                    "href": href,
                    "icon": meta_info.get("icon", "bi-link-45deg"),
                    "label": meta_info.get("label", key.title()),
                    "target": meta_info.get("target"),
                }
            )
            if len(buttons) >= 4:
                break
        return buttons

    def _guestbook_grade_options(jenjang: str | None) -> list[str]:
        if not jenjang:
            return [str(i) for i in range(1, 13)]
        upper = jenjang.strip().upper()
        if upper in {"SD", "MI"}:
            return [str(i) for i in range(1, 7)]
        if upper in {"SMP", "MTS"}:
            return [str(i) for i in range(7, 10)]
        if upper in {"SMA", "SMK", "MA"}:
            return [str(i) for i in range(10, 13)]
        return [str(i) for i in range(1, 13)]

    def _guestbook_class_letters() -> list[str]:
        return [chr(code) for code in range(ord("A"), ord("Z") + 1)]

    def _guestbook_review_summary(review: dict | None, fallback_summary: dict | None = None) -> dict:
        if not review:
            return fallback_summary or {"names": [], "count": 0}
        names_raw = review.get("guest_names") or ""
        names = [name.strip() for name in str(names_raw).split(",") if name.strip()]
        try:
            count = int(review.get("guest_count") or len(names))
        except (TypeError, ValueError):
            count = len(names)
        if not count and names:
            count = len(names)
        return {
            "names": names,
            "count": count,
        }

    def _guestbook_review_primary_name(summary: dict | None) -> str:
        names = (summary or {}).get("names") or []
        if names:
            return names[0]
        return "Tamu Umum"

    def _activate_guest_chat_session(review: dict, summary: dict | None) -> None:
        transaction_id = review.get("transaction_id")
        session["guest_chat_tx_id"] = transaction_id
        session["guest_chat_remaining"] = 2
        session["guest_chat_npsn"] = review.get("npsn")
        session["guest_chat_summary"] = summary or {"names": [], "count": 0}
        session["guest_chat_name"] = _guestbook_review_primary_name(summary)
        session.pop("guest_review_tx_id", None)
        session.pop("guest_review_token", None)
        session.pop("guest_review_npsn", None)
        session.pop("guest_review_school_name", None)
        session.pop("guest_review_summary", None)
        session.pop("guest_chat_user_id", None)
        session.modified = True

    def _pending_guest_review_redirect(review_token: str | None) -> str | None:
        pending_tx = session.get("guest_review_tx_id")
        pending_token = (session.get("guest_review_token") or "").strip()
        if not pending_tx or not pending_token:
            return None
        if review_token and pending_token != review_token:
            return None
        pending_npsn = (session.get("guest_review_npsn") or "").strip()
        if not pending_npsn:
            return None
        return url_for("buku_tamu_review", npsn=pending_npsn, review_token=pending_token)

    def _sync_session_quota(quota_state: dict | None) -> None:
        if "user" not in session or not quota_state:
            return
        user_data = dict(session["user"])
        access_tier = quota_state.get("access_tier") or "full"
        user_data["access_tier"] = access_tier
        user_data["quota_limit"] = quota_state.get("quota_limit")
        user_data["quota_remaining"] = quota_state.get("quota_remaining")
        reset_at = quota_state.get("quota_reset_at")
        if hasattr(reset_at, "isoformat"):
            reset_at = reset_at.isoformat()
        user_data["quota_reset_at"] = reset_at
        user_data["limited_reason"] = quota_state.get("limited_reason")
        session["user"] = user_data
        session.modified = True

    def _sync_session_status(status_state: dict | None) -> None:
        if "user" not in session or not status_state:
            return
        user_data = dict(session["user"])
        status_value = status_state.get("status") or ACCOUNT_STATUS_ACTIVE
        user_data["status"] = status_value
        user_data["status_reason"] = status_state.get("status_reason")
        changed_at = status_state.get("status_changed_at")
        if hasattr(changed_at, "isoformat"):
            changed_at = changed_at.isoformat()
        user_data["status_changed_at"] = changed_at
        user_data["status_changed_by"] = status_state.get("status_changed_by")
        session["user"] = user_data
        session.modified = True

    def _prepare_status_notice(user_id: int):
        status_state = get_web_user_status(user_id)
        _sync_session_status(status_state)
        status_value = (status_state or {}).get("status")
        notice = None
        if status_value in BLOCKING_STATUSES:
            notice = build_status_notice(
                status_value,
                reason=(status_state or {}).get("status_reason"),
                channel="web",
            )
        return notice, status_state

    def _is_quota_exempt_message(user_id: int, message: str) -> bool:
        if not message:
            return False

        session_data = web_sessions.get(user_id) or {}

        if reporting_enabled("bullying"):
            bullying_sessions = session_data.get("bullying_sessions") or {}
            if bullying_sessions.get(user_id):
                return True

        if reporting_enabled("corruption"):
            corruption_sessions = session_data.get("corruption_sessions") or {}
            if corruption_sessions.get(user_id):
                return True

        cleaned = normalize_input(replace_bot_mentions(message, WEB_BOT_USERNAME))
        if reporting_enabled("bullying") and detect_bullying_category(cleaned):
            return True

        if reporting_enabled("corruption") and is_corruption_report_intent(cleaned):
            return True

        return False

    @app.route("/")
    def index():
        user = session.get("user")
        if not user:
            return redirect(url_for("login_page"))

        user_id = user.get("id")
        quota_status = get_chat_quota_status(user_id)
        _sync_session_quota(quota_status)
        status_notice, _ = _prepare_status_notice(user_id)
        initial_chats = get_chat_history(user_id, limit=10, offset=0)

        status_payload = status_notice.__dict__ if status_notice else None
        return render_template(
            "chat.html",
            user=session.get("user"),
            initial_chats=initial_chats,
            quota=_serialize_quota_payload(quota_status),
            status_notice=status_payload,
            server_time=datetime.now(timezone.utc).isoformat(),
        )

    @app.route("/auth/login")
    def login_page():
        if session.get("user"):
            return redirect(url_for("index"))
        response = make_response(render_template("login.html", portal_register_url=_portal_register_url()))
        return _add_no_cache_headers(response)

    @app.route('/login')
    def login_belajar():
        session['login_mode'] = 'belajar'
        redirect_uri = url_for('authorize', _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route('/login/gmail')
    def login_gmail():
        session['login_mode'] = 'gmail'
        redirect_uri = url_for('authorize', _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route('/authorize')
    def authorize():
        token = oauth.google.authorize_access_token()
        userinfo = oauth.google.parse_id_token(token, nonce=session.get('nonce'))

        # Validate email domain
        email = userinfo.get('email')
        if not email:
            flash("Gagal mendapatkan informasi email dari Google.", "error")
            return redirect(url_for('login_page'))

        login_mode = session.pop('login_mode', 'belajar')
        domain = email.split('@')[-1].lower()
        is_belajar_domain = domain == 'belajar.id' or domain.endswith('.belajar.id')
        is_gmail_domain = domain in GMAIL_ALLOWED_DOMAINS

        if login_mode != 'belajar' and is_belajar_domain:
            # User clicked Gmail but actually has belajar.id, promote to full access.
            login_mode = 'belajar'

        if login_mode == 'belajar':
            if not is_belajar_domain:
                flash(
                    "Login harus menggunakan email dengan domain @belajar.id atau subdomainnya.",
                    "error",
                )
                return redirect(url_for('login_page'))
            access_tier = 'full'
            quota_limit = None
            auth_provider = 'google_oauth_belajar'
            limited_reason = None
        else:
            if not is_gmail_domain:
                flash(
                    "Login Gmail hanya menerima alamat @gmail.com. "
                    "Kalau kamu punya akun belajar.id silakan pilih opsi itu biar tanpa limit ya!",
                    "error",
                )
                return redirect(url_for('login_page'))
            access_tier = 'limited'
            quota_limit = DEFAULT_LIMITED_QUOTA
            auth_provider = 'google_oauth_gmail'
            limited_reason = DEFAULT_LIMITED_REASON

        # Get or create user in the database, update photo URL and last login timestamp
        user = get_or_create_web_user(
            email=email,
            full_name=userinfo.get('name'),
            photo_url=userinfo.get('picture'),
            access_tier=access_tier,
            auth_provider=auth_provider,
            quota_limit=quota_limit,
            limited_reason=limited_reason,
        )

        user_dict = dict(user) if user else {}
        if user:
            # Ensure datetime is serializable in the session
            last_login = user_dict.get('last_login')
            if hasattr(last_login, 'isoformat'):
                user_dict['last_login'] = last_login.isoformat()
            reset_at = user_dict.get('quota_reset_at')
            if hasattr(reset_at, 'isoformat'):
                user_dict['quota_reset_at'] = reset_at.isoformat()
            # Maintain compatibility with templates expecting `user.picture`
            user_dict['picture'] = user_dict.get('photo_url') or userinfo.get('picture')
            status_changed_at = user_dict.get('status_changed_at')
            if hasattr(status_changed_at, 'isoformat'):
                user_dict['status_changed_at'] = status_changed_at.isoformat()

        # Save user in session
        session['user'] = user_dict
        quota_status = None
        if user_dict.get('id'):
            quota_status = get_chat_quota_status(user_dict['id'])
            _sync_session_quota(quota_status)

        return redirect(url_for('index'))

    @app.route('/logout')
    def logout():
        session.pop('user', None)
        flash("You have been logged out.", "info")
        return redirect(url_for('login_page'))

    @app.route("/portal/uploads/logos/<path:filename>")
    def portal_school_logo(filename: str):
        requested_path = Path(filename)
        if requested_path.is_absolute() or ".." in requested_path.parts:
            abort(404)

        logos_dir = Path(__file__).resolve().parent.parent / "uploads" / "portal" / "logos"
        return send_from_directory(logos_dir, str(requested_path))

    @app.route("/buku-tamu/<npsn>", methods=["GET", "POST"])
    def buku_tamu(npsn: str):
        school = get_portal_school_by_npsn(npsn)
        if not school or not school.get("active"):
            return render_template(
                "buku_tamu.html",
                school=None,
                error="Sekolah tidak ditemukan atau nonaktif.",
                purpose_keywords=[],
                contact_buttons=[],
                grade_options=[],
                class_letters=[],
            ), 404

        grade_options = _guestbook_grade_options(school.get("jenjang"))
        class_letters = _guestbook_class_letters()
        allowed_grades = set(grade_options)
        allowed_letters = {letter.upper() for letter in class_letters}
        error = None
        def _is_truthy(value: object) -> bool:
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

        def _is_valid_student_class(value: str) -> bool:
            return bool((value or "").strip())

        if request.method == "POST":
            guest_type = (request.form.get("guest_type") or "umum").strip().lower()
            if guest_type != "umum":
                error = "Pengisian tamu Sudin dilakukan oleh pihak sekolah."
            else:
                guest_payload_raw = (request.form.get("guests_payload") or "").strip()
                guests = []
                if guest_payload_raw:
                    try:
                        payload = json.loads(guest_payload_raw)
                        if isinstance(payload, list):
                            guests = payload
                    except json.JSONDecodeError:
                        guests = []
                else:
                    names = request.form.getlist("guest_name[]")
                    instansi_list = request.form.getlist("guest_instansi[]")
                    jabatan_list = request.form.getlist("guest_jabatan[]")
                    phone_list = request.form.getlist("guest_phone[]")
                    email_list = request.form.getlist("guest_email[]")

                    for idx, name in enumerate(names):
                        clean_name = (name or "").strip()
                        if not clean_name:
                            continue
                        guests.append(
                            {
                                "full_name": clean_name,
                                "instansi": instansi_list[idx] if idx < len(instansi_list) else "",
                                "jabatan": jabatan_list[idx] if idx < len(jabatan_list) else "",
                                "phone": phone_list[idx] if idx < len(phone_list) else "",
                                "email": email_list[idx] if idx < len(email_list) else "",
                            }
                        )

                seen_phones = set()
                duplicate_found = False
                cleaned_guests = []
                for guest in guests:
                    name = (guest.get("full_name") or "").strip()
                    phone = (guest.get("phone") or "").strip()
                    if not name:
                        continue
                    if not phone:
                        error = "Nomor telepon wajib diisi untuk tamu umum."
                        break
                    phone_key = "".join(ch for ch in phone if ch.isdigit())
                    if phone_key.startswith("0"):
                        phone_key = "62" + phone_key[1:]
                    if phone_key in seen_phones:
                        duplicate_found = True
                    seen_phones.add(phone_key)
                    is_parent = _is_truthy(guest.get("is_parent"))
                    instansi = (guest.get("instansi") or "").strip()
                    jabatan = (guest.get("jabatan") or "").strip()
                    student_class = (guest.get("student_class") or "").strip()
                    student_name = (guest.get("student_name") or "").strip()
                    if is_parent:
                        if not student_class or not _is_valid_student_class(student_class):
                            error = "Kelas siswa wajib diisi."
                            break
                        if not student_name:
                            error = "Nama siswa wajib diisi untuk wali murid."
                            break
                        instansi = ""
                        jabatan = ""
                    else:
                        student_class = ""
                        student_name = ""
                    cleaned_guests.append(
                        {
                            "full_name": name,
                            "instansi": instansi,
                            "jabatan": jabatan,
                            "phone": phone_key,
                            "email": (guest.get("email") or "").strip(),
                            "is_parent": is_parent,
                            "student_class": student_class,
                            "student_name": student_name,
                        }
                    )
                if error:
                    pass
                elif not cleaned_guests:
                    error = "Minimal isi satu tamu."
                elif duplicate_found:
                    error = "Ada nomor telepon yang sama. Mohon periksa kembali."
                else:
                    guests = cleaned_guests
                    purpose = (request.form.get("purpose") or "").strip()
                    notes = (request.form.get("notes") or "").strip()
                    metadata = {
                        "user_agent": request.headers.get("User-Agent"),
                        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
                        "source": "web_aska",
                    }
                    try:
                        transaction_result = create_public_guestbook_transaction(
                            school_id=school["id"],
                            purpose=purpose or None,
                            notes=notes or None,
                            guests=guests,
                            metadata=metadata,
                        )
                    except Exception as exc:
                        error = f"Gagal mengirim buku tamu: {exc}"
                    else:
                        guest_names = [g.get("full_name") for g in guests if g.get("full_name")]
                        transaction_id = transaction_result.get("transaction_id")
                        review_token = transaction_result.get("review_token")
                        session.pop("guest_chat_tx_id", None)
                        session.pop("guest_chat_remaining", None)
                        session.pop("guest_chat_npsn", None)
                        session.pop("guest_chat_summary", None)
                        session.pop("guest_chat_name", None)
                        session.pop("guest_chat_user_id", None)
                        session["guest_review_tx_id"] = transaction_id
                        session["guest_review_token"] = review_token
                        session["guest_review_npsn"] = school.get("npsn")
                        session["guest_review_school_name"] = school.get("name")
                        session["guest_review_summary"] = {
                            "names": guest_names,
                            "count": len(guest_names),
                        }
                        session.modified = True
                        return redirect(url_for("buku_tamu_review", npsn=school.get("npsn"), review_token=review_token))

        return render_template(
            "buku_tamu.html",
            school=school,
            error=error,
            purpose_keywords=list_guestbook_purpose_keywords(active_only=True),
            contact_buttons=_build_contact_buttons(school),
            grade_options=grade_options,
            class_letters=class_letters,
        )

    @app.route("/api/guestbook/lookup")
    def guestbook_lookup():
        phone = (request.args.get("phone") or "").strip()
        guest = find_general_guest_by_phone(phone)
        return jsonify({
            "success": True,
            "found": bool(guest),
            "guest": guest,
        })

    @app.route("/buku-tamu/<npsn>/review/<review_token>", methods=["GET", "POST"])
    def buku_tamu_review(npsn: str, review_token: str):
        school = get_portal_school_by_npsn(npsn)
        review = get_public_guestbook_review_by_token(review_token)
        error = None

        if not school or not school.get("active"):
            error = "Sekolah tidak ditemukan atau nonaktif."
        elif not review:
            error = "Link review tidak ditemukan atau sudah tidak valid."
        elif (review.get("npsn") or "").strip() != (school.get("npsn") or "").strip():
            error = "Link review tidak sesuai dengan sekolah yang dipilih."

        if error:
            return render_template(
                "buku_tamu_review.html",
                school=school,
                review=None,
                summary={"names": [], "count": 0},
                review_url=None,
                review_completed=False,
                can_chat=False,
                error=error,
            ), 404

        review_status = (review.get("review_status") or review.get("status") or "").strip().lower()
        summary = _guestbook_review_summary(review, session.get("guest_review_summary"))
        review_url = url_for("buku_tamu_review", npsn=npsn, review_token=review_token)
        chat_url = url_for("buku_tamu_selesai", npsn=npsn, tx=review.get("transaction_id"))
        can_chat = int(session.get("guest_chat_tx_id") or 0) == int(review.get("transaction_id") or 0)

        if request.method == "POST" and review_status != "completed":
            rating_raw = (request.form.get("rating") or "").strip()
            comment = (request.form.get("comment") or "").strip()
            try:
                rating = int(rating_raw)
            except (TypeError, ValueError):
                rating = 0
            if rating < 1 or rating > 5:
                error = "Pilih rating bintang 1 sampai 5 dulu."
            else:
                try:
                    submit_public_guestbook_review(
                        review_token=review_token,
                        rating=rating,
                        comment=comment or None,
                    )
                except Exception as exc:
                    error = f"Gagal menyimpan review: {exc}"
                else:
                    fresh_review = get_public_guestbook_review_by_token(review_token) or review
                    summary = _guestbook_review_summary(fresh_review, summary)
                    _activate_guest_chat_session(fresh_review, summary)
                    return redirect(chat_url)

        if review_status == "completed":
            if not can_chat:
                _activate_guest_chat_session(review, summary)
            return redirect(chat_url)

        completed = review_status == "completed"
        return render_template(
            "buku_tamu_review.html",
            school=school,
            review=review,
            summary=summary,
            review_url=review_url,
            review_completed=completed,
            can_chat=can_chat,
            chat_url=chat_url,
            error=error,
        )

    @app.route("/buku-tamu/<npsn>/selesai")
    def buku_tamu_selesai(npsn: str):
        school = get_portal_school_by_npsn(npsn)
        tx_id = request.args.get("tx")
        can_chat = False
        remaining = 0
        summary = session.get("guest_chat_summary") or {}
        review_redirect = _pending_guest_review_redirect(None)
        try:
            tx_id_int = int(tx_id) if tx_id else None
        except (TypeError, ValueError):
            tx_id_int = None
        if tx_id_int and session.get("guest_chat_tx_id") == tx_id_int:
            can_chat = True
            remaining = int(session.get("guest_chat_remaining") or 0)
        if not can_chat and review_redirect:
            return redirect(review_redirect)
        return render_template(
            "buku_tamu_selesai.html",
            school=school,
            can_chat=can_chat,
            remaining=remaining,
            summary=summary,
            review_pending=bool(session.get("guest_review_tx_id") and session.get("guest_review_token")),
            review_url=review_redirect,
        )

    @app.route("/api/guest-chat", methods=["POST"])
    def guest_chat():
        data = request.json or {}
        message = data.get("message")
        if not message:
            return jsonify({"error": "Message is required"}), 400

        tx_id = session.get("guest_chat_tx_id")
        remaining = int(session.get("guest_chat_remaining") or 0)
        if not tx_id:
            return jsonify({"error": "Session expired", "require_login": True}), 401
        if remaining <= 0:
            return jsonify({"error": "Limit reached", "require_login": True}), 401

        guest_user_id = session.get("guest_chat_user_id")
        if not guest_user_id:
            guest_user_id = -1 * (secrets.randbelow(1_000_000_000) + 1)
            session["guest_chat_user_id"] = guest_user_id

        guest_name = session.get("guest_chat_name") or "Tamu Umum"
        response, _ = _run_async(process_web_request(guest_user_id, message, username=guest_name))
        remaining -= 1
        session["guest_chat_remaining"] = remaining
        session.modified = True
        return jsonify({"response": response, "remaining": remaining})

    @app.route("/api/whatsapp/inbound", methods=["POST"])
    def whatsapp_inbound():
        token_expected = (os.getenv("ASKA_WHATSAPP_INTERNAL_TOKEN") or "").strip()
        if not token_expected:
            return jsonify({"error": "ASKA_WHATSAPP_INTERNAL_TOKEN belum dikonfigurasi"}), 501

        provided_token = (
            request.headers.get("X-ASKA-WHATSAPP-TOKEN")
            or request.args.get("token")
            or request.form.get("token")
        )
        if provided_token != token_expected:
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json(silent=True) or {}
        user_id = _normalize_whatsapp_user_id(data.get("user_id") or data.get("from"))
        if not user_id:
            return jsonify({"error": "Nomor WhatsApp tidak valid"}), 400

        username = (data.get("username") or data.get("name") or "WhatsApp User").strip()[:120]
        message_type = (data.get("message_type") or "text").strip().lower()
        message = (data.get("message") or "").strip()

        if message_type != "text":
            return jsonify(
                {
                    "response": "Saat ini ASKA via WhatsApp baru support pesan teks dulu ya 🙏",
                    "blocked": False,
                    "blockType": "unsupported_type",
                    "chat_log_id": None,
                }
            )
        if not message:
            return jsonify({"error": "Message is required"}), 400

        status_info = get_whatsapp_user_status(user_id)
        status_value = (status_info or {}).get("status")
        if status_value in BLOCKING_STATUSES:
            notice = build_status_notice(
                status_value,
                reason=(status_info or {}).get("status_reason"),
                channel="whatsapp",
            )
            save_chat(user_id, username, message, role="user", topic="whatsapp")
            response_text = notice.message if notice else "Akses WhatsApp kamu sedang dibatasi oleh sekolah."
            save_chat(user_id, "ASKA", response_text, role="aska", topic="whatsapp")
            return jsonify(
                {
                    "response": response_text,
                    "blocked": True,
                    "blockType": "status",
                    "chat_log_id": None,
                    "statusBlock": notice.__dict__ if notice else None,
                }
            )

        response, chat_log_id = _run_async(
            process_channel_request(
                user_id,
                message,
                username=username,
                topic="whatsapp",
            )
        )
        return jsonify(
            {
                "response": response,
                "blocked": False,
                "blockType": None,
                "chat_log_id": chat_log_id,
            }
        )

    @app.route("/api/callcenter/inbound", methods=["POST"])
    def callcenter_inbound():
        """Receive inbound messages from the Call Center WhatsApp bridge.

        Unlike the ASKA bot, this does NOT generate an AI reply.
        It stores the message and notifies admins via Telegram.
        """
        token_expected = (os.getenv("ASKA_CC_WHATSAPP_INTERNAL_TOKEN") or "").strip()
        if not token_expected:
            return jsonify({"error": "ASKA_CC_WHATSAPP_INTERNAL_TOKEN belum dikonfigurasi"}), 501

        provided_token = (
            request.headers.get("X-ASKA-CC-TOKEN")
            or request.args.get("token")
            or ""
        )
        if provided_token != token_expected:
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json(silent=True) or {}
        raw_user_id = str(data.get("user_id") or "").strip()
        if not raw_user_id:
            return jsonify({"error": "user_id required"}), 400

        username = (data.get("username") or raw_user_id).strip()[:120]
        message = (data.get("message") or "").strip()
        message_id = data.get("message_id") or None
        if not message:
            return jsonify({"error": "message required"}), 400

        try:
            from dashboard.call_center.queries import (
                upsert_cc_conversation,
                save_cc_message,
                send_cc_telegram_notification,
            )

            conv = upsert_cc_conversation(wa_user_id=raw_user_id, display_name=username)
            msg = save_cc_message(
                conversation_id=conv["id"],
                direction="inbound",
                message_text=message,
                wa_message_id=message_id,
            )

            # Fire-and-forget Telegram notification
            try:
                send_cc_telegram_notification(username, message)
            except Exception:
                pass

            return jsonify({"ok": True, "conversation_id": conv.get("id"), "message_id": msg.get("id")})
        except Exception as exc:
            current_app.logger.exception("callcenter_inbound error")
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/chat", methods=["POST"])
    def chat():
        if 'user' not in session:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.json
        user_id = session['user'].get("id")
        full_name = session['user'].get("full_name", "WebUser")
        message = data.get("message")

        if not message:
            return jsonify({"error": "Message is required"}), 400

        status_notice, status_state = _prepare_status_notice(user_id)
        status_payload = status_notice.__dict__ if status_notice else None
        if status_notice:
            quota_state = get_chat_quota_status(user_id)
            _sync_session_quota(quota_state)
            server_now = datetime.now(timezone.utc).isoformat()
            return jsonify({
                "response": status_notice.message,
                "blocked": True,
                "blockType": "status",
                "statusBlock": status_payload,
                "exempt": False,
                "quota": _serialize_quota_payload(quota_state),
                "serverTime": server_now,
            })

        is_exempt = _is_quota_exempt_message(user_id, message)
        if is_exempt:
            quota_state = get_chat_quota_status(user_id)
        else:
            quota_state = consume_chat_quota(user_id)

        _sync_session_quota(quota_state)

        if quota_state.get("error") == "user_not_found":
            session.pop('user', None)
            return jsonify({"error": "Unauthorized"}), 401

        quota_payload = _serialize_quota_payload(quota_state)
        if not is_exempt and not quota_state.get("allowed", False):
            server_now = datetime.now(timezone.utc).isoformat()
            return jsonify({
                "response": LIMIT_BLOCK_MESSAGE,
                "blocked": True,
                "blockType": "quota",
                "exempt": False,
                "quota": quota_payload,
                "statusBlock": None,
                "serverTime": server_now,
            })

        response, chat_log_id = _run_async(process_web_request(user_id, message, username=full_name))
        server_now = datetime.now(timezone.utc).isoformat()
        return jsonify({
            "response": response,
            "chat_log_id": chat_log_id,
            "blocked": False,
            "exempt": is_exempt,
            "blockType": None,
            "statusBlock": status_payload,
            "quota": quota_payload,
            "serverTime": server_now,
        })

    @app.route("/api/history")
    def chat_history():
        if 'user' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        
        user_id = session['user'].get('id')
        offset = request.args.get('offset', 0, type=int)
        
        history = get_chat_history(user_id, limit=10, offset=offset)
        
        # Convert datetime objects to string representation
        for item in history:
            if 'created_at' in item and hasattr(item['created_at'], 'isoformat'):
                item['created_at'] = item['created_at'].isoformat()

        return jsonify(history)

    @app.route("/api/quota")
    def quota_status_api():
        if 'user' not in session:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = session['user'].get('id')
        quota_status = get_chat_quota_status(user_id)
        _sync_session_quota(quota_status)
        return jsonify({
            "quota": _serialize_quota_payload(quota_status),
            "serverTime": datetime.now(timezone.utc).isoformat(),
        })

    @app.route("/api/admin/refresh-knowledge", methods=["POST"])
    def refresh_knowledge_api():
        token = (
            request.headers.get("X-ASKA-REFRESH-TOKEN")
            or request.args.get("token")
            or request.form.get("token")
        )
        expected = os.getenv("ASKA_REFRESH_TOKEN")
        if not expected:
            return jsonify({"error": "Refresh token not configured"}), 501
        if token != expected:
            return jsonify({"error": "Unauthorized"}), 403
        try:
            reload_qa_chain()
        except Exception as exc:
            current_app.logger.exception("Failed to reload QA chain")
            return jsonify({"error": f"Reload failed: {exc}"}), 500
        return jsonify({"status": "ok"})

    @app.route("/cek-laporan", methods=["GET"])
    def cek_laporan():
        if not reporting_enabled("corruption"):
            abort(404)

        ticket = request.args.get("ticket", "").strip()
        report = None
        error = None

        if ticket:
            report = get_corruption_report(ticket)
            if not report:
                error = "Nomor tiketnya belum ketemu nih. Coba pastiin lagi atau cek huruf kapitalnya ya!"

        return render_template("cek_laporan.html", ticket=ticket, report=report, error=error)

    @app.route("/cek-laporan/<ticket_id>")
    def cek_laporan_detail(ticket_id: str):
        if not reporting_enabled("corruption"):
            abort(404)
        return redirect(url_for("cek_laporan", ticket=ticket_id, _anchor="hasil"))

    # Register feedback blueprint
    app.register_blueprint(feedback_bp)

    return app
