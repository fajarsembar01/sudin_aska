from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash, send_from_directory, abort
from authlib.integrations.flask_client import OAuth

from .handlers import process_web_request, web_sessions, reload_qa_chain
from .feedback_routes import feedback_bp
from db import (
    get_or_create_web_user,
    get_chat_history,
    get_corruption_report,
    get_chat_quota_status,
    consume_chat_quota,
    get_web_user_status,
    DEFAULT_LIMITED_QUOTA,
    DEFAULT_LIMITED_REASON,
    get_portal_school_by_npsn,
    create_public_guestbook_transaction,
    find_general_guest_by_phone,
    list_guestbook_purpose_keywords,
    list_guestbook_contact_priorities,
    list_school_classroom_options,
)
from account_status import BLOCKING_STATUSES, build_status_notice, ACCOUNT_STATUS_ACTIVE
from responses import detect_bullying_category, is_corruption_report_intent
from utils import normalize_input, replace_bot_mentions

LIMIT_BLOCK_MESSAGE = (
    f"Ups! Kuota {DEFAULT_LIMITED_QUOTA} chat untuk akses Gmail sudah habis. "
    "Tunggu hitung mundur selesai atau login pakai akun belajar.id / Telegram biar bebas limit ya! 🚀"
)
GMAIL_ALLOWED_DOMAINS = {"gmail.com", "googlemail.com"}
WEB_BOT_USERNAME = "ASKA_WEB"


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

        bullying_sessions = session_data.get("bullying_sessions") or {}
        if bullying_sessions.get(user_id):
            return True

        corruption_sessions = session_data.get("corruption_sessions") or {}
        if corruption_sessions.get(user_id):
            return True

        cleaned = normalize_input(replace_bot_mentions(message, WEB_BOT_USERNAME))
        if detect_bullying_category(cleaned):
            return True

        if is_corruption_report_intent(cleaned):
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
        return render_template("login.html", portal_register_url=_portal_register_url())

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
                class_options=[],
            ), 404

        class_options = list_school_classroom_options(school.get("id"))
        error = None
        def _is_truthy(value: object) -> bool:
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

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
                        instansi = "Wali Murid"
                        jabatan = "Wali Murid"
                        if class_options:
                            if not student_class or student_class not in class_options:
                                error = "Kelas siswa wajib dipilih dari daftar yang tersedia."
                                break
                        if not student_name:
                            error = "Nama siswa wajib diisi untuk wali murid."
                            break
                    cleaned_guests.append(
                        {
                            "full_name": name,
                            "instansi": instansi,
                            "jabatan": jabatan,
                            "phone": phone_key,
                            "email": (guest.get("email") or "").strip(),
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
                        transaction_id = create_public_guestbook_transaction(
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
                        guest_user_id = session.get("guest_chat_user_id")
                        if not guest_user_id:
                            guest_user_id = -1 * (secrets.randbelow(1_000_000_000) + 1)
                            session["guest_chat_user_id"] = guest_user_id
                        session["guest_chat_remaining"] = 2
                        session["guest_chat_tx_id"] = transaction_id
                        session["guest_chat_npsn"] = school.get("npsn")
                        session["guest_chat_summary"] = {
                            "names": guest_names,
                            "count": len(guest_names),
                        }
                        session["guest_chat_name"] = guest_names[0] if guest_names else "Tamu Umum"
                        session.modified = True
                        return redirect(url_for("buku_tamu_selesai", npsn=school.get("npsn"), tx=transaction_id))

        return render_template(
            "buku_tamu.html",
            school=school,
            error=error,
            purpose_keywords=list_guestbook_purpose_keywords(active_only=True),
            contact_buttons=_build_contact_buttons(school),
            class_options=class_options,
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

    @app.route("/buku-tamu/<npsn>/selesai")
    def buku_tamu_selesai(npsn: str):
        school = get_portal_school_by_npsn(npsn)
        tx_id = request.args.get("tx")
        can_chat = False
        remaining = 0
        summary = session.get("guest_chat_summary") or {}
        try:
            tx_id_int = int(tx_id) if tx_id else None
        except (TypeError, ValueError):
            tx_id_int = None
        if tx_id_int and session.get("guest_chat_tx_id") == tx_id_int:
            can_chat = True
            remaining = int(session.get("guest_chat_remaining") or 0)
        return render_template(
            "buku_tamu_selesai.html",
            school=school,
            can_chat=can_chat,
            remaining=remaining,
            summary=summary,
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

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        guest_name = session.get("guest_chat_name") or "Tamu Umum"
        response, _ = loop.run_until_complete(process_web_request(guest_user_id, message, username=guest_name))
        remaining -= 1
        session["guest_chat_remaining"] = remaining
        session.modified = True
        return jsonify({"response": response, "remaining": remaining})

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

        # Run the async function in a managed event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # 'get_running_loop' fails if no loop is running
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        response, chat_log_id = loop.run_until_complete(process_web_request(user_id, message, username=full_name))
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
        return redirect(url_for("cek_laporan", ticket=ticket_id, _anchor="hasil"))

    # Register feedback blueprint
    app.register_blueprint(feedback_bp)

    return app
