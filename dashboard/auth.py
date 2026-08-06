from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
from functools import wraps
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from authlib.integrations.flask_client import OAuth
from dotenv import dotenv_values
from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from account_status import (
    ACCOUNT_STATUS_BADGES,
    ACCOUNT_STATUS_CHOICES,
    ACCOUNT_STATUS_LABELS,
)
from dashboard.telegram_notifications import send_test_notification

from .queries import (
    create_dashboard_user,
    delete_telegram_admin_account,
    delete_telegram_notification_group,
    fetch_aska_users,
    fetch_telegram_notification_settings,
    fetch_whatsapp_link_settings,
    get_user_by_email,
    list_admin_users,
    list_dashboard_users,
    list_telegram_admin_accounts,
    list_telegram_notification_groups,
    summarize_aska_users,
    update_last_login,
    update_telegram_user_status,
    update_web_user_status,
    update_whatsapp_user_status,
    upsert_telegram_admin_accounts,
    upsert_telegram_notification_settings,
    upsert_whatsapp_link_settings,
)

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()

GMAIL_ALLOWED_DOMAINS = {"gmail.com", "googlemail.com"}
_OAUTH_REGISTERED = False
_WA_ME_PATTERN = re.compile(r"^https?://(www\.)?wa\.me/\d+/?$", re.IGNORECASE)


def _normalize_profile_photo_path(photo_path: Optional[str]) -> Optional[str]:
    if not photo_path:
        return None
    normalized = str(photo_path).replace("\\", "/").strip()
    if normalized.startswith("uploads/portal/"):
        normalized = normalized[len("uploads/portal/") :]
    normalized = normalized.lstrip("/")
    rel = PurePosixPath(normalized)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    return rel.as_posix() if rel.as_posix() else None


def _build_profile_photo_url(photo_path: Optional[str]) -> Optional[str]:
    rel_path = _normalize_profile_photo_path(photo_path)
    if not rel_path:
        return None
    return url_for("portal.uploaded_file", filename=rel_path)


def _normalize_whatsapp_link(raw_value: Optional[str]) -> str:
    clean = (raw_value or "").strip()
    if not clean:
        return "https://wa.me/6282143646463"
    if _WA_ME_PATTERN.match(clean):
        return clean.rstrip("/")
    digits = "".join(ch for ch in clean if ch.isdigit())
    if not digits:
        return "https://wa.me/6282143646463"
    if digits.startswith("0"):
        digits = f"62{digits[1:]}"
    return f"https://wa.me/{digits}"


def _load_whatsapp_bridge_status() -> dict:
    status_path = Path(
        os.getenv("ASKA_WHATSAPP_STATUS_PATH", "runtime/whatsapp_bridge_status.json")
    )
    if not status_path.is_absolute():
        status_path = (Path(__file__).resolve().parent.parent / status_path).resolve()

    if not status_path.exists():
        return {
            "state": "offline",
            "message": "Status file belum ada. Jalankan worker: npm run wa:start",
            "qrText": "",
            "statusPath": str(status_path),
        }
    try:
        raw = json.loads(status_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {}
    except Exception:
        raw = {}
    raw.setdefault("state", "unknown")
    raw.setdefault("message", "Status WhatsApp bridge belum tersedia.")
    raw.setdefault("qrText", "")
    raw["statusPath"] = str(status_path)
    return raw


def _resolve_whatsapp_runtime_paths() -> dict:
    root_dir = Path(__file__).resolve().parent.parent
    session_path = Path(os.getenv("ASKA_WHATSAPP_SESSION_PATH", ".wa_session"))
    if not session_path.is_absolute():
        session_path = (root_dir / session_path).resolve()
    status_path = Path(
        os.getenv("ASKA_WHATSAPP_STATUS_PATH", "runtime/whatsapp_bridge_status.json")
    )
    if not status_path.is_absolute():
        status_path = (root_dir / status_path).resolve()
    log_path = (root_dir / "runtime" / "whatsapp_bridge.log").resolve()
    pid_path = (root_dir / "runtime" / "whatsapp_bridge.pid").resolve()
    return {
        "root": root_dir,
        "session": session_path,
        "status": status_path,
        "log": log_path,
        "pid": pid_path,
    }


def _read_pid(pid_path: Path) -> Optional[int]:
    try:
        raw = pid_path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        return int(raw)
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _stop_existing_bridge(pid_path: Path) -> None:
    pid = _read_pid(pid_path)
    if not pid or not _pid_alive(pid):
        pass
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    # Safety net: kill stale WA worker/chrome processes tied to this session.
    try:
        subprocess.run(
            [
                "pkill",
                "-f",
                "node scripts/whatsapp_bridge.js|npm run wa:start|session-aska-main|Google Chrome for Testing.*wa_session",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    try:
        pid_path.unlink(missing_ok=True)
    except Exception:
        pass


def _restart_whatsapp_bridge(reset_session: bool = True) -> dict:
    paths = _resolve_whatsapp_runtime_paths()
    root_dir = paths["root"]
    session_path = paths["session"]
    pid_path = paths["pid"]
    log_path = paths["log"]

    _stop_existing_bridge(pid_path)
    # Remove stale Chromium lock files before boot.
    try:
        session_client_dir = session_path / "session-aska-main"
        for lock_name in (
            "SingletonLock",
            "SingletonCookie",
            "SingletonSocket",
            "lockfile",
        ):
            for lock_path in session_client_dir.rglob(lock_name):
                try:
                    lock_path.unlink()
                except Exception:
                    pass
    except Exception:
        pass
    if reset_session and session_path.exists():
        shutil.rmtree(session_path, ignore_errors=True)

    log_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env_file = root_dir / ".env"
    if env_file.exists():
        loaded = dotenv_values(env_file)
        for key, value in loaded.items():
            if key and value is not None and key not in env:
                env[key] = str(value)

    if not (env.get("ASKA_WHATSAPP_INTERNAL_TOKEN") or "").strip():
        raise RuntimeError(
            "ASKA_WHATSAPP_INTERNAL_TOKEN belum diset di environment/.env"
        )

    if "ASKA_WHATSAPP_STATUS_PATH" not in env:
        env["ASKA_WHATSAPP_STATUS_PATH"] = str(paths["status"])

    with log_path.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            ["npm", "run", "wa:start"],
            cwd=str(root_dir),
            env=env,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )

    pid_path.write_text(str(process.pid), encoding="utf-8")
    return {
        "pid": process.pid,
        "log_path": str(log_path),
        "status_path": str(paths["status"]),
    }


def init_oauth(app) -> None:
    """Initialize Google OAuth for the dashboard app."""
    global _OAUTH_REGISTERED
    oauth.init_app(app)
    if _OAUTH_REGISTERED:
        return

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return

    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    _OAUTH_REGISTERED = True


def current_user() -> Optional[dict]:
    return session.get("user")


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Silakan login terlebih dahulu.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapper


def role_required(*roles: str) -> Callable:
    """Check if user has required role. Simplified version without admin_level/access_scope."""

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                # flash("Silakan login terlebih dahulu.", "warning")
                return redirect(url_for("auth.login", next=request.path))

            role = user.get("role")
            if role not in roles:
                flash("Anda tidak memiliki akses ke fitur ini.", "danger")
                # Simple role-based redirect
                if role == "admin":
                    return redirect(url_for("main.admin_select_role"))
                elif role == "coordinator":
                    return redirect(url_for("portal.home"))
                elif role == "staff":
                    return redirect(url_for("portal.home"))
                elif role == "sekolah":
                    return redirect(url_for("portal.sekolah_home"))
                else:
                    return redirect(url_for("auth.logout"))

            return view(*args, **kwargs)

        return wrapper

    return decorator


def _establish_session(
    user: dict, *, remember: bool = False, email_override: Optional[str] = None
) -> None:
    """Populate the Flask session with the logged-in dashboard user."""
    raw_assigned_class = user.get("assigned_class_id")
    assigned_class_id = None
    if raw_assigned_class is not None:
        try:
            assigned_class_id = int(raw_assigned_class)
        except (TypeError, ValueError):
            assigned_class_id = None

    email_value = (email_override or user.get("email") or "").strip().lower()
    profile_photo_path = user.get("profile_photo_path")
    profile_photo_url = _build_profile_photo_url(profile_photo_path)

    session["user"] = {
        "id": user["id"],
        "email": email_value,
        "full_name": user.get("full_name"),
        "role": user.get("role"),
        "profile_photo_path": profile_photo_path,
        "profile_photo_url": profile_photo_url,
        "no_tester_enabled": bool(user.get("no_tester_enabled")),
        "assigned_class_id": assigned_class_id,
        "social_username": user.get("social_username"),
    }
    session.permanent = remember
    update_last_login(user["id"])


def _redirect_after_login(user: dict, fallback: Optional[str] = None) -> str:
    """Determine the appropriate redirect destination after login. Simplified."""
    if fallback and fallback != "/":
        return fallback

    role = user.get("role", "")

    # For admin, root is an acceptable redirection (it redirects to select-role)
    if fallback == "/" and role == "admin":
        return fallback

    # Simple role-based redirect
    if role == "admin":
        return url_for("main.admin_select_role")
    elif role == "coordinator":
        return url_for("portal.home")
    elif role == "staff":
        return url_for("portal.home")
    elif role == "sekolah":
        return url_for("portal.sekolah_home")
    else:
        return url_for("auth.login")


def _get_login_block_feedback(user: dict) -> Optional[tuple[str, str]]:
    """Return flash message/category when user status is not allowed to login."""
    status = (user.get("account_status") or "approved").strip().lower()
    if status == "approved":
        return None
    if status == "pending":
        return (
            "Akun Anda masih menunggu verifikasi admin. Silakan hubungi admin wilayah.",
            "warning",
        )
    if status == "rejected":
        return (
            "Akun Anda belum dapat digunakan karena pengajuan ditolak. Silakan hubungi admin wilayah.",
            "danger",
        )
    if status in {"suspended", "disabled"}:
        return (
            "Akun Anda sedang dinonaktifkan. Silakan hubungi admin wilayah.",
            "danger",
        )
    return (
        "Akun Anda belum dapat digunakan saat ini. Silakan hubungi admin wilayah.",
        "danger",
    )


def _render_login_page(**context) -> Response:
    response = make_response(render_template("login.html", **context))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@auth_bp.route("/register", methods=["GET", "POST"])
def register() -> Response:
    """Handle new staff account registration."""
    if current_user():
        return redirect(url_for("portal.home"))

    if request.method == "POST":
        try:
            full_name = request.form.get("full_name")
            email = request.form.get("email")
            password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")
            kecamatan_id = request.form.get("kecamatan_id")
            whatsapp = request.form.get("whatsapp_number")
            nip = request.form.get("nip")
            nrk = (request.form.get("nrk") or "").strip() or None
            jabatan = request.form.get("jabatan")

            # Basic validation
            if not all([full_name, email, password, whatsapp, nip]):
                flash("Mohon lengkapi semua data wajib.", "warning")
                # Fallback list if DB fails or query not ready
                kecamatan_list = []
                try:
                    from dashboard.db_access import get_cursor

                    with get_cursor() as cur:
                        cur.execute(
                            "SELECT id, name FROM portal_kecamatan ORDER BY name"
                        )
                        kecamatan_list = [dict(row) for row in cur.fetchall()]
                except Exception:
                    pass
                coordinator_contacts = _build_login_contact_list()
                return render_template(
                    "register.html",
                    kecamatan_list=kecamatan_list,
                    coordinator_contacts=coordinator_contacts,
                )

            if password != confirm_password:
                flash("Password tidak cocok.", "warning")
                kecamatan_list = []
                try:
                    from dashboard.db_access import get_cursor

                    with get_cursor() as cur:
                        cur.execute(
                            "SELECT id, name FROM portal_kecamatan ORDER BY name"
                        )
                        kecamatan_list = [dict(row) for row in cur.fetchall()]
                except Exception:
                    pass
                coordinator_contacts = _build_login_contact_list()
                return render_template(
                    "register.html",
                    kecamatan_list=kecamatan_list,
                    coordinator_contacts=coordinator_contacts,
                )

            # Check existing user
            from dashboard.queries import get_user_by_email

            if get_user_by_email(email):
                flash("Email sudah terdaftar. Silakan login.", "warning")
                return redirect(url_for("auth.login"))

            # Create user
            from werkzeug.security import generate_password_hash

            from dashboard.auth_queries import create_pending_user

            user_id = create_pending_user(
                email=email,
                full_name=full_name,
                password_hash=generate_password_hash(password, method="pbkdf2:sha256"),
                role="staff",
                whatsapp=whatsapp,
                nip=nip,
                nrk=nrk,
                jabatan=jabatan,
                kecamatan_id=int(kecamatan_id) if kecamatan_id else None,
            )

            try:
                from dashboard.db_access import get_cursor
                from dashboard.telegram_notifications import notify_pending_user

                kecamatan_name = None
                if kecamatan_id:
                    with get_cursor() as cur:
                        cur.execute(
                            "SELECT name FROM portal_kecamatan WHERE id = %s",
                            (int(kecamatan_id),),
                        )
                        row = cur.fetchone()
                        if row:
                            kecamatan_name = row.get("name")

                notify_pending_user(
                    user_id=user_id,
                    full_name=full_name,
                    email=email,
                    role="staff",
                    kecamatan_name=kecamatan_name,
                    whatsapp_number=whatsapp,
                )
            except Exception:
                current_app.logger.exception(
                    "Gagal mengirim notifikasi Telegram untuk verifikasi akun."
                )

            flash(
                "Pendaftaran berhasil! Akun Anda sedang diverifikasi oleh admin.",
                "success",
            )
            return redirect(url_for("auth.registration_status", user_id=user_id))

        except Exception as e:
            print(f"Registration error: {e}")
            flash("Terjadi kesalahan saat mendaftar. Silakan coba lagi.", "danger")

    # GET request
    from dashboard.db_access import get_cursor

    kecamatan_list = []
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id, name FROM portal_kecamatan ORDER BY name")
            kecamatan_list = [dict(row) for row in cur.fetchall()]
    except Exception:
        pass

    coordinator_contacts = _build_login_contact_list()

    return render_template(
        "register.html",
        kecamatan_list=kecamatan_list,
        coordinator_contacts=coordinator_contacts,
    )


@auth_bp.route("/registration-status/<int:user_id>")
def registration_status(user_id: int) -> Response:
    """Show registration status for a new user."""
    from dashboard.db_access import get_cursor

    with get_cursor() as cur:
        # Fetch user details + kecamatan name
        query = """
            SELECT u.*, k.name as kecamatan_name
            FROM dashboard_users u
            LEFT JOIN portal_kecamatan k ON u.requested_kecamatan = k.id
            WHERE u.id = %s
        """
        cur.execute(query, (user_id,))
        user = cur.fetchone()

    if not user:
        flash("Data pendaftaran tidak ditemukan.", "danger")
        return redirect(url_for("auth.register"))

    user_dict = dict(user)
    if (
        user_dict.get("full_name")
        and user_dict.get("email")
        and user_dict.get("kecamatan_name")
    ):
        message_template = (
            "Halo {contact_name}, saya "
            f"{user_dict.get('full_name')} baru mendaftar akun Portal ASKA "
            f"untuk kecamatan {user_dict.get('kecamatan_name')}."
            f"\n\nEmail: {user_dict.get('email')}\n\n"
            "Ditunggu verifikasi akun saya, terima kasih."
        )
    elif user_dict.get("full_name"):
        message_template = (
            "Halo {contact_name}, saya "
            f"{user_dict.get('full_name')} ingin menanyakan status pendaftaran Portal ASKA."
        )
    else:
        message_template = (
            "Halo {contact_name}, saya ingin bertanya tentang pendaftaran Portal ASKA."
        )
    coordinator_contacts = _build_login_contact_list(
        message_template=message_template,
        area_name=user_dict.get("kecamatan_name"),
    )

    return render_template(
        "registration_status.html",
        user=user_dict,
        coordinator_contacts=coordinator_contacts,
    )


def _build_login_contact_list(
    message: str | None = None,
    *,
    area_name: str | None = None,
    message_template: str | None = None,
) -> list[dict]:
    from urllib.parse import quote_plus

    from dashboard.portal.queries import list_portal_kontak

    contacts = []
    default_message = "Halo, saya butuh bantuan untuk akses portal ASKA."
    message_to_use = (message or default_message).strip() or default_message
    try:
        rows = list_portal_kontak()
    except Exception:
        return contacts

    for row in rows:
        area = (row.get("wilayah") or "").strip()
        if not area:
            continue
        for name_key, phone_key, active_key in (
            ("nama", "kontak", "kontak_1_active"),
            ("nama_2", "kontak_2", "kontak_2_active"),
        ):
            name = (row.get(name_key) or "").strip()
            phone = (row.get(phone_key) or "").strip()
            if not name or not phone:
                continue
            digits = "".join(ch for ch in phone if ch.isdigit())
            if digits.startswith("0"):
                digits = "62" + digits[1:]
            if not digits:
                continue
            is_active = row.get(active_key)
            if is_active is None:
                is_active = True
            contact_message = message_to_use
            if message_template:
                try:
                    contact_message = message_template.format(contact_name=name)
                except Exception:
                    contact_message = message_to_use
            is_user_area = False
            if area_name:
                is_user_area = area.lower() in area_name.lower()
            contacts.append(
                {
                    "area": area,
                    "name": name,
                    "phone": phone,
                    "wa_link": f"https://api.whatsapp.com/send?phone={digits}&text={quote_plus(contact_message)}",
                    "is_user_area": is_user_area,
                    "is_active": bool(is_active),
                }
            )
    return contacts


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> Response:
    existing = current_user()
    if existing:
        return redirect(_redirect_after_login(existing))

    coordinator_contacts = _build_login_contact_list()

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = request.form.get("remember") == "on"

        user = get_user_by_email(email)
        if not user:
            flash("Email belum terdaftar. Hubungi admin untuk membuat akun.", "danger")
            return _render_login_page(
                email=email, coordinator_contacts=coordinator_contacts
            )

        login_block = _get_login_block_feedback(user)
        if login_block:
            message, category = login_block
            flash(message, category)
            return _render_login_page(
                email=email, coordinator_contacts=coordinator_contacts
            )

        if not check_password_hash(user["password_hash"], password):
            flash("Salah password, hubungi admin untuk reset akses.", "danger")
            return _render_login_page(
                email=email, coordinator_contacts=coordinator_contacts
            )

        _establish_session(user, remember=remember, email_override=email)
        flash("Selamat datang kembali!", "success")
        return redirect(_redirect_after_login(user, request.args.get("next")))

    return _render_login_page(coordinator_contacts=coordinator_contacts)


@auth_bp.route("/logout")
@login_required
def logout() -> Response:
    session.clear()
    flash("Anda telah logout.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/clear-session")
def clear_session() -> Response:
    """Force clear all session data - emergency escape from loops."""
    session.clear()
    return render_template("clear_session.html")


@auth_bp.route("/login/google/<provider>")
def google_login(provider: str) -> Response:
    normalized_provider = (provider or "belajar").strip().lower()
    if normalized_provider not in {"belajar", "gmail"}:
        normalized_provider = "belajar"

    oauth_client = oauth.create_client("google")
    if not oauth_client:
        flash("Login Google belum dikonfigurasi oleh admin.", "danger")
        return redirect(url_for("auth.login"))

    session.pop("post_login_redirect", None)
    next_url = request.args.get("next")
    if next_url:
        session["post_login_redirect"] = next_url
    session["dashboard_oauth_provider"] = normalized_provider
    nonce = secrets.token_urlsafe(24)
    session["dashboard_oauth_nonce"] = nonce
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth_client.authorize_redirect(
        redirect_uri, prompt="select_account", nonce=nonce
    )


@auth_bp.route("/login/google/callback")
def google_callback() -> Response:
    oauth_client = oauth.create_client("google")
    if not oauth_client:
        flash("Login Google belum dikonfigurasi oleh admin.", "danger")
        return redirect(url_for("auth.login"))

    try:
        token = oauth_client.authorize_access_token()
        nonce = session.get("dashboard_oauth_nonce")
        userinfo = oauth_client.parse_id_token(token, nonce=nonce)
    except Exception:
        current_app.logger.exception("Google OAuth callback gagal diproses.")
        flash("Gagal memproses respons Google. Silakan coba lagi.", "danger")
        return redirect(url_for("auth.login"))
    finally:
        session.pop("dashboard_oauth_nonce", None)

    email = (userinfo or {}).get("email")
    if not email:
        flash("Google tidak mengirimkan email pengguna.", "danger")
        return redirect(url_for("auth.login"))

    email = email.strip().lower()
    provider = session.pop("dashboard_oauth_provider", "belajar")
    domain = email.split("@")[-1].lower()

    if provider == "belajar":
        valid_domain = domain == "belajar.id" or domain.endswith(".belajar.id")
        error_message = "Login belajar.id memerlukan email dengan domain @belajar.id."
    else:
        valid_domain = domain in GMAIL_ALLOWED_DOMAINS
        error_message = "Login Gmail hanya menerima alamat @gmail.com."

    if not valid_domain:
        flash(error_message, "danger")
        return redirect(url_for("auth.login"))

    user = get_user_by_email(email)
    if not user:
        flash(
            "Email tersebut belum terdaftar pada dashboard. Hubungi admin untuk mendapatkan akses.",
            "danger",
        )
        return redirect(url_for("auth.login"))

    login_block = _get_login_block_feedback(user)
    if login_block:
        message, category = login_block
        flash(message, category)
        return redirect(url_for("auth.login"))

    _establish_session(user, remember=True, email_override=email)
    flash("Autentikasi Google berhasil.", "success")
    next_url = session.pop("post_login_redirect", None)
    return redirect(_redirect_after_login(user, next_url))


@auth_bp.route("/settings/users", methods=["GET", "POST"])
@role_required("admin")
def manage_users() -> Response:
    from dashboard.user_management import handle_manage_users

    return handle_manage_users(
        actor=current_user(), base_template="base.html", read_only=True
    )


@auth_bp.route("/settings/monev-teams", methods=["GET", "POST"])
@role_required("admin")
def manage_monev_teams() -> Response:
    """Manage monev teams configuration."""
    from dashboard.portal.queries import list_kecamatan
    from dashboard.queries import (
        add_team_member,
        create_monev_team,
        delete_monev_team,
        get_available_staff,
        get_monev_teams,
        get_team_members,
        remove_team_member,
        update_team_coordinator,
    )

    if request.method == "POST":
        action = request.form.get("action")

        try:
            if action == "create_team":
                name = request.form.get("team_name", "").strip()
                team_type = request.form.get("team_type", "custom")
                kecamatan_id = request.form.get("kecamatan_id")
                kecamatan_id = int(kecamatan_id) if kecamatan_id else None

                if not name:
                    flash("Nama tim tidak boleh kosong.", "warning")
                else:
                    team_id = create_monev_team(name, team_type, kecamatan_id)
                    if team_id:
                        flash(f"Tim '{name}' berhasil dibuat.", "success")
                    else:
                        flash("Gagal membuat tim.", "danger")

            elif action == "delete_team":
                team_id = int(request.form.get("team_id"))
                team_name = request.form.get("team_name", "")

                if delete_monev_team(team_id):
                    flash(f"Tim '{team_name}' berhasil dihapus.", "success")
                else:
                    flash("Gagal menghapus tim.", "danger")

            elif action == "update_coordinator":
                team_id = int(request.form.get("team_id"))
                coordinator_id = request.form.get("coordinator_id")
                coordinator_id = int(coordinator_id) if coordinator_id else None

                if update_team_coordinator(team_id, coordinator_id):
                    flash("Koordinator berhasil diperbarui.", "success")
                else:
                    flash("Gagal memperbarui koordinator.", "danger")

            elif action == "add_member":
                team_id = int(request.form.get("team_id"))
                staff_id = int(request.form.get("staff_id"))
                admin_id = current_user().get("id") if current_user() else None

                if add_team_member(team_id, staff_id, admin_id):
                    flash("Anggota berhasil ditambahkan.", "success")
                else:
                    flash(
                        "Anggota sudah ada dalam tim atau gagal ditambahkan.", "warning"
                    )

            elif action == "remove_member":
                member_id = int(request.form.get("member_id"))

                if remove_team_member(member_id):
                    flash("Anggota berhasil dihapus dari tim.", "success")
                else:
                    flash("Gagal menghapus anggota.", "danger")

        except Exception as exc:
            current_app.logger.error(f"Error managing monev team: {exc}")
            flash(f"Terjadi kesalahan: {exc}", "danger")

    # GET: Fetch teams by type and enrich with members
    kasi_teams = get_monev_teams(team_type="kasi")
    for team in kasi_teams:
        team["members"] = get_team_members(team["id"])

    kecamatan_teams = get_monev_teams(team_type="kecamatan")
    for team in kecamatan_teams:
        team["members"] = get_team_members(team["id"])

    custom_teams = get_monev_teams(team_type="custom")
    for team in custom_teams:
        team["members"] = get_team_members(team["id"])

    available_staff = get_available_staff()
    kecamatan_list = list_kecamatan()

    return render_template(
        "monev_teams.html",
        kasi_teams=kasi_teams,
        kecamatan_teams=kecamatan_teams,
        custom_teams=custom_teams,
        available_staff=available_staff,
        kecamatan_list=kecamatan_list,
    )


@auth_bp.route("/settings/telegram-notifications", methods=["GET", "POST"])
@role_required("admin")
def telegram_notifications() -> Response:
    """Configure Telegram notification bot token and admin approvals."""
    return redirect(url_for("pengaturan.admin_settings", tab="notification"))


@auth_bp.route("/settings/whatsapp-link", methods=["GET", "POST"])
@role_required("admin")
def whatsapp_link_settings() -> Response:
    """Configure WhatsApp entry link shown in ASKA Insight dashboard."""
    actor = current_user() or {}

    if request.method == "POST":
        raw_value = request.form.get("wa_link") or ""
        normalized_link = _normalize_whatsapp_link(raw_value)
        upsert_whatsapp_link_settings(normalized_link, actor.get("id"))
        flash("Link WhatsApp berhasil disimpan.", "success")

    settings = fetch_whatsapp_link_settings()
    current_link = _normalize_whatsapp_link(
        settings.get("wa_link") or os.getenv("ASKA_WHATSAPP_URL", "082143646463")
    )

    return render_template(
        "whatsapp_link_settings.html",
        settings=settings,
        current_link=current_link,
    )


@auth_bp.route("/settings/whatsapp-bridge")
@role_required("admin")
def whatsapp_bridge_settings() -> Response:
    """Show WhatsApp bridge/QR connection guide."""
    status = _load_whatsapp_bridge_status()
    return render_template("whatsapp_bridge_settings.html", status=status)


@auth_bp.route("/settings/whatsapp-bridge/status")
@role_required("admin")
def whatsapp_bridge_status() -> Response:
    """Return current WhatsApp bridge status payload for polling."""
    return jsonify({"success": True, "status": _load_whatsapp_bridge_status()})


@auth_bp.route("/settings/whatsapp-bridge/generate-qr", methods=["POST"])
@role_required("admin")
def whatsapp_bridge_generate_qr() -> Response:
    """Force restart WA bridge and regenerate a fresh QR login."""
    try:
        runtime = _restart_whatsapp_bridge(reset_session=True)
        message = "Worker WhatsApp direstart. Tunggu 5-15 detik sampai QR muncul."
        if (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            return jsonify({"success": True, "message": message, "runtime": runtime})
        flash(message, "success")
        return redirect(url_for("auth.whatsapp_bridge_settings"))
    except Exception as exc:
        message = f"Gagal generate QR: {exc}"
        if (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            return jsonify({"success": False, "message": message}), 500
        flash(message, "danger")
        return redirect(url_for("auth.whatsapp_bridge_settings"))


@auth_bp.route("/my-team")
@role_required("coordinator", "staff")
def view_my_team() -> Response:
    """View monev team for coordinator or staff member."""
    from dashboard.queries import get_monev_teams, get_team_members

    user = current_user()
    user_id = user.get("id")
    user_role = user.get("role")

    # Get all teams
    all_teams = get_monev_teams()

    # Find team where user is coordinator or member
    my_team = None
    my_team_role = None  # 'coordinator' or 'member'

    for team in all_teams:
        # Check if coordinator
        if team.get("coordinator_id") == user_id:
            my_team = team
            my_team_role = "coordinator"
            break

        # Check if member
        members = get_team_members(team["id"])
        if any(m.get("staff_id") == user_id for m in members):
            my_team = team
            my_team_role = "member"
            break

    if my_team:
        my_team["members"] = get_team_members(my_team["id"])

    return render_template("my_team.html", team=my_team, team_role=my_team_role)


@auth_bp.route("/settings/aska-users")
@role_required("admin")
def manage_aska_users() -> Response:
    source = (request.args.get("source") or "all").strip().lower()
    if source not in {"web", "telegram", "whatsapp", "all"}:
        source = "all"
    status_filter = (request.args.get("status") or "all").strip().lower()
    normalized_status = (
        status_filter if status_filter in ACCOUNT_STATUS_CHOICES else None
    )
    search = (request.args.get("q") or "").strip()

    users = fetch_aska_users(source, normalized_status, search or None)
    stats = summarize_aska_users()

    return render_template(
        "aska_users.html",
        users=users,
        filter_source=source,
        status_filter=status_filter,
        search_query=search,
        status_choices=ACCOUNT_STATUS_CHOICES,
        status_labels=ACCOUNT_STATUS_LABELS,
        status_badges=ACCOUNT_STATUS_BADGES,
        stats=stats,
    )


@auth_bp.route("/settings/aska-users/status", methods=["POST"])
@role_required("admin")
def update_aska_user_status() -> Response:
    payload = request.get_json(silent=True) or {}
    channel = (payload.get("channel") or "").strip().lower()
    status = (payload.get("status") or "").strip().lower()
    user_id = payload.get("userId")
    if user_id is None:
        return jsonify({"success": False, "message": "ID user wajib diisi."}), 400
    reason = payload.get("reason")
    normalized_status = status if status in ACCOUNT_STATUS_CHOICES else None
    if not normalized_status:
        return jsonify({"success": False, "message": "Status tidak dikenal."}), 400
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "ID user tidak valid."}), 400

    admin = current_user() or {}
    actor = admin.get("email") or admin.get("full_name") or "dashboard"
    try:
        if channel == "web":
            updated = update_web_user_status(
                user_id_int, normalized_status, reason, changed_by=actor
            )
        elif channel == "telegram":
            updated = update_telegram_user_status(
                user_id_int, normalized_status, reason, changed_by=actor
            )
        elif channel == "whatsapp":
            updated = update_whatsapp_user_status(
                user_id_int, normalized_status, reason, changed_by=actor
            )
        else:
            return jsonify({"success": False, "message": "Channel tidak dikenal."}), 400
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    if not updated:
        return jsonify({"success": False, "message": "User tidak ditemukan."}), 404
    return jsonify({"success": True})
