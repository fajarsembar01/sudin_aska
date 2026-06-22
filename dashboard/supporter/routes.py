from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from dashboard.auth import current_user, role_required
from dashboard.portal.routes import inject_permissions as portal_inject_permissions
from dashboard.queries import (
    delete_telegram_admin_account,
    list_admin_users,
    list_telegram_admin_accounts,
    upsert_telegram_admin_accounts,
)
from utils import JAKARTA_TZ, current_jakarta_time, to_jakarta

from .queries import (
    ACTION_OPTIONS,
    PLATFORM_OPTIONS,
    SUPPORTER_TELEGRAM_SCOPE,
    TASK_STATUSES,
    calculate_points,
    cancel_submission,
    create_task,
    delete_supporter_telegram_group,
    ensure_supporter_schema,
    export_submissions,
    fetch_admin_stats,
    fetch_leaderboard,
    fetch_staff_stats,
    get_staff_submission_for_task,
    get_submission_detail,
    get_supporter_setting,
    get_task,
    list_activity_logs,
    list_staff_tasks,
    list_submissions,
    list_supporter_admin_delivery_status,
    list_supporter_telegram_groups,
    list_tasks,
    normalize_action_types,
    review_submission,
    review_submission_action,
    set_supporter_setting,
    submit_task,
    update_task,
    update_task_status,
)


supporter_bp = Blueprint(
    "supporter",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/supporter",
)

UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "supporter"
ALLOWED_PROOF_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "pdf"}
MAX_PROOF_IMAGE_BYTES = 100 * 1024  # auto-compress screenshots to <= 100 KB

ACTION_LABELS = dict(ACTION_OPTIONS)
PLATFORM_LABELS = dict(PLATFORM_OPTIONS)
TASK_STATUS_LABELS = {
    "draft": "Draft",
    "active": "Aktif",
    "paused": "Paused",
    "archived": "Arsip",
}
SUBMISSION_STATUS_LABELS = {
    "submitted": "Menunggu",
    "under_review": "Direview",
    "verified": "Terverifikasi",
    "rejected": "Ditolak",
    "needs_revision": "Revisi",
    "cancelled": "Dibatalkan",
}
SUBMISSION_STATUS_BADGES = {
    "submitted": "text-bg-warning",
    "under_review": "text-bg-info",
    "verified": "text-bg-success",
    "rejected": "text-bg-danger",
    "needs_revision": "text-bg-primary",
    "cancelled": "text-bg-secondary",
}


@supporter_bp.context_processor
def inject_supporter_context() -> Dict[str, Any]:
    context = portal_inject_permissions() or {}
    context.update(
        {
            "supporter_action_labels": ACTION_LABELS,
            "supporter_platform_labels": PLATFORM_LABELS,
            "supporter_task_status_labels": TASK_STATUS_LABELS,
            "supporter_submission_status_labels": SUBMISSION_STATUS_LABELS,
            "supporter_submission_status_badges": SUBMISSION_STATUS_BADGES,
        }
    )
    return context


@supporter_bp.before_request
def _ensure_schema_before_request() -> None:
    ensure_supporter_schema()


def _parse_datetime_local(value: Optional[str]) -> Optional[datetime]:
    clean = (value or "").strip()
    if not clean:
        return None
    try:
        parsed = datetime.strptime(clean, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    return parsed.replace(tzinfo=JAKARTA_TZ)


def _datetime_local_value(value: Optional[datetime]) -> str:
    if not value:
        return ""
    jakarta_value = to_jakarta(value)
    try:
        return jakarta_value.strftime("%Y-%m-%dT%H:%M")
    except Exception:
        return ""


def _clean_text(name: str, *, default: str = "") -> str:
    return (request.form.get(name) or default).strip()


def _task_form_data() -> Dict[str, Any]:
    platform_values = {key for key, _ in PLATFORM_OPTIONS}
    action_values = {key for key, _ in ACTION_OPTIONS}
    platform = _clean_text("platform", default="instagram")
    action_types = []
    for raw_action in request.form.getlist("action_types"):
        action = (raw_action or "").strip()
        if action in action_values and action not in action_types:
            action_types.append(action)
    if not action_types:
        legacy_action = _clean_text("action_type")
        if legacy_action in action_values:
            action_types.append(legacy_action)
    action_type = action_types[0] if action_types else "custom"
    status = _clean_text("status", default="draft")
    if platform not in platform_values:
        platform = "other"
    if status not in TASK_STATUSES:
        status = "draft"
    try:
        base_points = max(0, int(_clean_text("base_points", default="10")))
    except ValueError:
        base_points = 10
    try:
        penalty = float(_clean_text("late_penalty_percent", default="50"))
    except ValueError:
        penalty = 50.0
    penalty = max(0.0, min(100.0, penalty))
    return {
        "title": _clean_text("title"),
        "campaign_name": _clean_text("campaign_name") or None,
        "description": _clean_text("description") or None,
        "platform": platform,
        "action_type": action_type,
        "action_types": action_types,
        "target_url": _clean_text("target_url") or None,
        "target_account": _clean_text("target_account") or None,
        "instructions": _clean_text("instructions") or None,
        "base_points": base_points,
        "late_penalty_percent": penalty,
        "start_at": _parse_datetime_local(request.form.get("start_at")) or current_jakarta_time(),
        "deadline_at": _parse_datetime_local(request.form.get("deadline_at")),
        "end_at": _parse_datetime_local(request.form.get("end_at")),
        "allow_late_submission": request.form.get("allow_late_submission") == "on",
        "requires_proof_url": request.form.get("requires_proof_url") == "on",
        "requires_proof_text": request.form.get("requires_proof_text") == "on",
        "requires_screenshot": request.form.get("requires_screenshot") == "on",
        "verification_mode": _clean_text("verification_mode", default="manual_telegram") or "manual_telegram",
        "status": status,
    }


def _validate_task_timing(data: Dict[str, Any]) -> Optional[str]:
    start_at = data.get("start_at")
    deadline_at = data.get("deadline_at")
    end_at = data.get("end_at")
    if end_at and start_at and end_at < start_at:
        return "Waktu berakhir tidak boleh sebelum waktu mulai."
    if end_at and deadline_at and end_at < deadline_at:
        return "Waktu berakhir tidak boleh sebelum deadline."
    return None


def _task_form_context(task: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    selected_action_types = normalize_action_types(
        (task or {}).get("action_types"),
        fallback=(task or {}).get("action_type"),
    )
    default_start_at = current_jakarta_time()
    return {
        "task": task,
        "action_options": ACTION_OPTIONS,
        "platform_options": PLATFORM_OPTIONS,
        "task_statuses": TASK_STATUSES,
        "datetime_local_value": _datetime_local_value,
        "default_start_at": default_start_at,
        "selected_action_types": selected_action_types,
    }


def _compress_proof_image_to_jpeg(file, target_path: Path, max_bytes: int = MAX_PROOF_IMAGE_BYTES) -> bool:
    """Re-encode an uploaded image as JPEG capped at ~max_bytes. Returns True on success."""
    try:
        import io

        from PIL import Image, ImageOps

        file.stream.seek(0)
        with Image.open(file.stream) as opened:
            opened = ImageOps.exif_transpose(opened)
            image = opened.convert("RGB")

        max_dim = 1600
        if image.width > max_dim or image.height > max_dim:
            image.thumbnail((max_dim, max_dim), Image.LANCZOS)

        buf = io.BytesIO()
        for quality in (85, 75, 65, 55, 45, 35, 25, 15):
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= max_bytes:
                break

        # Still too large: progressively downscale until it fits (or give up).
        attempts = 0
        while buf.tell() > max_bytes and attempts < 6 and min(image.width, image.height) > 320:
            attempts += 1
            image.thumbnail((int(image.width * 0.8), int(image.height * 0.8)), Image.LANCZOS)
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=35, optimize=True)

        buf.seek(0)
        target_path.write_bytes(buf.getvalue())
        return True
    except Exception:
        return False


def _persist_proof_filestorage(file, *, error_label: str) -> Optional[str]:
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    if not filename:
        return None
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_PROOF_EXTENSIONS:
        raise ValueError(error_label)
    today = current_jakarta_time()
    rel_dir = Path(f"{today:%Y}") / f"{today:%m}"
    target_dir = UPLOAD_ROOT / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    if ext == "pdf":
        stored_name = f"{uuid.uuid4().hex}_{filename}"
        file.save(target_dir / stored_name)
        return (rel_dir / stored_name).as_posix()

    # Image proof: auto-compress to <= 100 KB and normalize to JPEG.
    stored_name = f"{uuid.uuid4().hex}.jpg"
    if _compress_proof_image_to_jpeg(file, target_dir / stored_name):
        return (rel_dir / stored_name).as_posix()

    # Fallback: store the original bytes if compression fails.
    fallback_name = f"{uuid.uuid4().hex}_{filename}"
    file.stream.seek(0)
    file.save(target_dir / fallback_name)
    return (rel_dir / fallback_name).as_posix()


def _save_proof_file() -> Optional[str]:
    return _persist_proof_filestorage(
        request.files.get("proof_file"),
        error_label="Format bukti hanya jpg, jpeg, png, webp, atau pdf.",
    )


def _save_proof_file_for_action(action_key: str) -> Optional[str]:
    return _persist_proof_filestorage(
        request.files.get(f"proof_file_{action_key}"),
        error_label=f"Format bukti untuk aksi {action_key} hanya jpg, jpeg, png, webp, atau pdf.",
    )


def _proof_path_is_safe(filename: str) -> Optional[Path]:
    raw = (filename or "").replace("\\", "/").strip()
    if not raw:
        return None
    rel = PurePosixPath(raw)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    candidate = (UPLOAD_ROOT / rel.as_posix()).resolve()
    try:
        candidate.relative_to(UPLOAD_ROOT.resolve())
    except ValueError:
        return None
    return candidate if candidate.exists() and candidate.is_file() else None


def _can_submit_task(task: Dict[str, Any], submission: Optional[Dict[str, Any]]) -> tuple[bool, str]:
    if (task.get("status") or "") != "active":
        return False, "Task belum aktif."
    now = current_jakarta_time()
    start_at = task.get("start_at")
    if start_at and to_jakarta(start_at) > now:
        return False, "Task belum dimulai."
    calc = calculate_points(task, submitted_at=now)
    if calc.get("is_expired"):
        if calc.get("is_ended"):
            return False, "Task sudah berakhir."
        return False, "Task sudah melewati batas waktu."
    if not submission:
        return True, ""
    if submission.get("status") in {"needs_revision", "rejected", "cancelled"}:
        return True, ""
    return False, "Submission untuk task ini sudah tercatat."


@supporter_bp.route("/")
def landing() -> Response:
    user = current_user()
    if not user:
        return redirect(url_for("auth.login", next=request.path))
    role = (user.get("role") or "").strip().lower()
    if role == "admin":
        return redirect(url_for("supporter.admin_dashboard"))
    if role == "staff":
        return redirect(url_for("supporter.staff_dashboard"))
    flash("Fitur Supporter hanya tersedia untuk admin dan staff.", "danger")
    return redirect(url_for("portal.home"))


@supporter_bp.route("/staff")
@role_required("staff")
def staff_dashboard() -> Response:
    user = current_user() or {}
    staff_id = int(user.get("id") or 0)
    tasks = list_staff_tasks(staff_id=staff_id, limit=100)
    submissions = list_submissions(staff_id=staff_id, limit=20)
    stats = fetch_staff_stats(staff_id)
    leaderboard = fetch_leaderboard(limit=5)
    return render_template(
        "supporter/staff/dashboard.html",
        page_title="Supporter",
        tasks=tasks,
        submissions=submissions,
        stats=stats,
        leaderboard=leaderboard,
    )


@supporter_bp.route("/tasks/<int:task_id>")
@role_required("staff")
def task_detail(task_id: int) -> Response:
    user = current_user() or {}
    staff_id = int(user.get("id") or 0)
    task = get_task(task_id)
    if not task:
        flash("Task tidak ditemukan.", "warning")
        return redirect(url_for("supporter.staff_dashboard"))
    submission = get_staff_submission_for_task(task_id=task_id, staff_id=staff_id)
    can_submit, submit_reason = _can_submit_task(task, submission)
    current_points = calculate_points(task)
    return render_template(
        "supporter/staff/task_detail.html",
        page_title=f"Supporter - {task.get('title')}",
        task=task,
        submission=submission,
        can_submit=can_submit,
        submit_reason=submit_reason,
        current_points=current_points,
    )


@supporter_bp.route("/tasks/<int:task_id>/submit", methods=["POST"])
@role_required("staff")
def submit_task_route(task_id: int) -> Response:
    user = current_user() or {}
    staff_id = int(user.get("id") or 0)
    task = get_task(task_id)
    if not task:
        flash("Task tidak ditemukan.", "warning")
        return redirect(url_for("supporter.staff_dashboard"))
    existing = get_staff_submission_for_task(task_id=task_id, staff_id=staff_id)
    can_submit, submit_reason = _can_submit_task(task, existing)
    if not can_submit:
        flash(submit_reason, "warning")
        return redirect(url_for("supporter.task_detail", task_id=task_id))

    proof_url = _clean_text("proof_url") or None
    proof_text = _clean_text("proof_text") or None
    social_username = _clean_text("social_username") or None
    if task.get("requires_proof_url") and not proof_url:
        flash("Link bukti wajib diisi.", "warning")
        return redirect(url_for("supporter.task_detail", task_id=task_id))
    if task.get("requires_proof_text") and not proof_text:
        flash("Catatan bukti wajib diisi.", "warning")
        return redirect(url_for("supporter.task_detail", task_id=task_id))

    proof_file_path = None
    screenshots = {}
    if task.get("requires_screenshot"):
        action_types = task.get("action_types") or []
        if action_types:
            for action_key in action_types:
                try:
                    path = _save_proof_file_for_action(action_key)
                    if path:
                        screenshots[action_key] = path
                        if not proof_file_path:
                            proof_file_path = path
                except ValueError as exc:
                    flash(str(exc), "warning")
                    return redirect(url_for("supporter.task_detail", task_id=task_id))
            
            # Check if all action screenshots are provided
            for action_key in action_types:
                if action_key not in screenshots:
                    flash("Semua screenshot aksi wajib diunggah.", "warning")
                    return redirect(url_for("supporter.task_detail", task_id=task_id))
        else:
            try:
                proof_file_path = _save_proof_file()
            except ValueError as exc:
                flash(str(exc), "warning")
                return redirect(url_for("supporter.task_detail", task_id=task_id))
            if not proof_file_path:
                flash("Screenshot/file bukti wajib diunggah.", "warning")
                return redirect(url_for("supporter.task_detail", task_id=task_id))

    # Auto-save social_username to staff profile settings if changed
    if social_username and social_username != user.get("social_username"):
        try:
            from dashboard.portal.queries import update_dashboard_user_profile
            update_dashboard_user_profile(user_id=staff_id, social_username=social_username)
            user["social_username"] = social_username
            session["user"] = user
        except Exception:
            pass

    submission = submit_task(
        task=task,
        staff_id=staff_id,
        social_username=social_username,
        proof_url=proof_url,
        proof_text=proof_text,
        proof_file_path=proof_file_path,
        metadata={"source": "web", "screenshots": screenshots},
    )
    try:
        from .telegram import notify_supporter_submission

        notify_supporter_submission(submission_id=int(submission["id"]))
    except Exception:
        # Notification failure must not block staff submission.
        pass
    flash("Submission dikirim dan menunggu verifikasi admin.", "success")
    return redirect(url_for("supporter.task_detail", task_id=task_id))


@supporter_bp.route("/submissions/<int:submission_id>/cancel", methods=["POST"])
@role_required("staff")
def cancel_submission_route(submission_id: int) -> Response:
    user = current_user() or {}
    ok = cancel_submission(submission_id=submission_id, staff_id=int(user.get("id") or 0))
    flash("Submission dibatalkan." if ok else "Submission tidak dapat dibatalkan.", "info" if ok else "warning")
    return redirect(url_for("supporter.staff_dashboard"))


@supporter_bp.route("/leaderboard")
@role_required("staff", "admin")
def leaderboard() -> Response:
    rows = fetch_leaderboard(limit=100)
    return render_template(
        "supporter/leaderboard.html",
        page_title="Supporter - Leaderboard",
        leaderboard=rows,
    )


@supporter_bp.route("/proof/<path:filename>")
@role_required("staff", "admin")
def proof_file(filename: str) -> Response:
    candidate = _proof_path_is_safe(filename)
    if not candidate:
        flash("File bukti tidak ditemukan.", "warning")
        return redirect(url_for("supporter.landing"))
    rel_parent = candidate.parent.relative_to(UPLOAD_ROOT.resolve()).as_posix()
    return send_from_directory(UPLOAD_ROOT / rel_parent, candidate.name)


@supporter_bp.route("/admin")
@role_required("admin")
def admin_dashboard() -> Response:
    stats = fetch_admin_stats()
    pending = list_submissions(status="pending", limit=10)
    tasks = list_tasks(limit=10)
    leaderboard_rows = fetch_leaderboard(limit=5)
    logs = list_activity_logs(limit=8)
    return render_template(
        "supporter/admin/dashboard.html",
        page_title="Supporter - Dashboard Admin",
        stats=stats,
        pending=pending,
        tasks=tasks,
        leaderboard=leaderboard_rows,
        logs=logs,
    )


@supporter_bp.route("/admin/tasks", methods=["GET", "POST"])
@role_required("admin")
def admin_tasks() -> Response:
    user = current_user() or {}
    if request.method == "POST":
        data = _task_form_data()
        timing_error = _validate_task_timing(data)
        if not data["title"]:
            flash("Judul task wajib diisi.", "warning")
        elif not data["action_types"]:
            flash("Pilih minimal satu aksi untuk task.", "warning")
        elif timing_error:
            flash(timing_error, "warning")
        else:
            task_id = create_task(data, created_by=int(user.get("id") or 0))
            flash("Task Supporter berhasil dibuat.", "success")
            return redirect(url_for("supporter.admin_edit_task", task_id=task_id))
    status = (request.args.get("status") or "").strip() or None
    q = (request.args.get("q") or "").strip() or None
    tasks = list_tasks(status=status, q=q, limit=300)
    return render_template(
        "supporter/admin/tasks.html",
        page_title="Supporter - Task",
        tasks=tasks,
        status_filter=status,
        q=q or "",
        **_task_form_context(),
    )


@supporter_bp.route("/admin/tasks/<int:task_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def admin_edit_task(task_id: int) -> Response:
    user = current_user() or {}
    task = get_task(task_id)
    if not task:
        flash("Task tidak ditemukan.", "warning")
        return redirect(url_for("supporter.admin_tasks"))
    if request.method == "POST":
        data = _task_form_data()
        timing_error = _validate_task_timing(data)
        if not data["title"]:
            flash("Judul task wajib diisi.", "warning")
        elif not data["action_types"]:
            flash("Pilih minimal satu aksi untuk task.", "warning")
        elif timing_error:
            flash(timing_error, "warning")
        elif update_task(task_id, data, actor_user_id=int(user.get("id") or 0)):
            flash("Task berhasil diperbarui.", "success")
            return redirect(url_for("supporter.admin_edit_task", task_id=task_id))
        else:
            flash("Task gagal diperbarui.", "danger")
    task = get_task(task_id)
    return render_template(
        "supporter/admin/task_form.html",
        page_title="Supporter - Edit Task",
        **_task_form_context(task),
    )


@supporter_bp.route("/admin/tasks/<int:task_id>/status", methods=["POST"])
@role_required("admin")
def admin_task_status(task_id: int) -> Response:
    user = current_user() or {}
    status = (request.form.get("status") or "").strip()
    ok = update_task_status(task_id, status, actor_user_id=int(user.get("id") or 0))
    flash("Status task diperbarui." if ok else "Status task tidak valid.", "success" if ok else "warning")
    return redirect(request.referrer or url_for("supporter.admin_tasks"))


@supporter_bp.route("/admin/submissions")
@role_required("admin")
def admin_submissions() -> Response:
    status = (request.args.get("status") or "pending").strip()
    q = (request.args.get("q") or "").strip() or None
    rows = list_submissions(status=status if status != "all" else None, q=q, limit=500)
    return render_template(
        "supporter/admin/submissions.html",
        page_title="Supporter - Verifikasi",
        submissions=rows,
        status_filter=status,
        q=q or "",
    )


@supporter_bp.route("/admin/submissions/<int:submission_id>/review-action", methods=["POST"])
@role_required("admin")
def admin_review_action(submission_id: int) -> Response:
    user = current_user() or {}
    action = (request.form.get("action") or "").strip()
    action_key = (request.form.get("action_key") or "").strip()
    status_map = {
        "verify": "verified",
        "reject": "rejected",
        "revision": "needs_revision",
    }
    status = status_map.get(action)
    note = _clean_text("reviewer_note") or None
    if not status or not action_key:
        flash("Aksi verifikasi tidak valid.", "warning")
        return redirect(request.referrer or url_for("supporter.admin_submissions"))
    updated = review_submission_action(
        submission_id=submission_id,
        action_key=action_key,
        status=status,
        reviewer_id=int(user.get("id") or 0),
        reviewer_note=note,
    )
    if updated:
        flash("Aksi berhasil diproses.", "success")
        try:
            from .telegram import notify_supporter_status_update

            notify_supporter_status_update(submission_id=submission_id)
        except Exception:
            pass
    else:
        flash("Aksi gagal diproses.", "danger")
    return redirect(request.referrer or url_for("supporter.admin_submissions"))


@supporter_bp.route("/admin/submissions/<int:submission_id>/review", methods=["POST"])
@role_required("admin")
def admin_review_submission(submission_id: int) -> Response:
    user = current_user() or {}
    action = (request.form.get("action") or "").strip()
    status_map = {
        "verify": "verified",
        "reject": "rejected",
        "revision": "needs_revision",
        "review": "under_review",
    }
    status = status_map.get(action)
    note = _clean_text("reviewer_note") or None
    if not status:
        flash("Aksi verifikasi tidak valid.", "warning")
        return redirect(request.referrer or url_for("supporter.admin_submissions"))
    updated = review_submission(
        submission_id=submission_id,
        status=status,
        reviewer_id=int(user.get("id") or 0),
        reviewer_note=note,
    )
    if updated:
        try:
            from .telegram import notify_supporter_status_update

            notify_supporter_status_update(submission_id=submission_id)
        except Exception:
            pass
        flash("Submission berhasil diproses.", "success")
    else:
        flash("Submission gagal diproses.", "danger")
    return redirect(request.referrer or url_for("supporter.admin_submissions"))


@supporter_bp.route("/admin/leaderboard")
@role_required("admin")
def admin_leaderboard() -> Response:
    return redirect(url_for("supporter.leaderboard"))


@supporter_bp.route("/admin/settings", methods=["GET", "POST"])
@role_required("admin")
def admin_settings() -> Response:
    user = current_user() or {}
    if request.method == "POST":
        form_action = _clean_text("form_action")
        if form_action == "bot_token":
            from .telegram import SUPPORTER_BOT_TOKEN_SETTING

            token = _clean_text("supporter_bot_token")
            set_supporter_setting(
                SUPPORTER_BOT_TOKEN_SETTING,
                token,
                updated_by=int(user.get("id") or 0) or None,
            )
            if token:
                flash("Token bot Telegram Supporter disimpan.", "success")
            else:
                flash("Token bot Telegram Supporter dihapus.", "info")
            return redirect(url_for("supporter.admin_settings"))

        username = _clean_text("telegram_username").lstrip("@").lower()
        dashboard_user_id = request.form.get("dashboard_user_id", type=int)
        if not username or not dashboard_user_id:
            flash("Pilih admin dan isi username Telegram.", "warning")
        else:
            upsert_telegram_admin_accounts(
                [
                    {
                        "dashboard_user_id": dashboard_user_id,
                        "telegram_username": username,
                    }
                ],
                created_by=int(user.get("id") or 0),
                scope=SUPPORTER_TELEGRAM_SCOPE,
            )
            flash("Admin Telegram Supporter disimpan.", "success")
        return redirect(url_for("supporter.admin_settings"))

    from .telegram import SUPPORTER_BOT_TOKEN_SETTING

    stored_bot_token = get_supporter_setting(SUPPORTER_BOT_TOKEN_SETTING)
    env_bot_token = bool((os.getenv("TELEGRAM_SUPPORTER_BOT_TOKEN") or "").strip())
    return render_template(
        "supporter/admin/settings.html",
        page_title="Supporter - Pengaturan",
        admin_users=list_admin_users(),
        telegram_admins=list_supporter_admin_delivery_status(),
        telegram_groups=list_supporter_telegram_groups(),
        supporter_bot_token_configured=bool(stored_bot_token) or env_bot_token,
        supporter_bot_token_from_db=bool(stored_bot_token),
        supporter_bot_token_from_env=env_bot_token,
    )


@supporter_bp.route("/admin/settings/test-bot", methods=["POST"])
@role_required("admin")
def admin_test_bot() -> Response:
    from .telegram import test_supporter_bot_connection

    result = test_supporter_bot_connection()
    if result.get("ok"):
        flash(
            "Koneksi bot berhasil. Terhubung sebagai @{username} (ID {bot_id}).".format(
                username=result.get("username") or "-",
                bot_id=result.get("bot_id") or "-",
            ),
            "success",
        )
    else:
        flash("Koneksi bot gagal: {0}".format(result.get("error") or "Tidak diketahui."), "danger")
    return redirect(url_for("supporter.admin_settings"))


@supporter_bp.route("/admin/settings/test-notification", methods=["POST"])
@role_required("admin")
def admin_test_notification() -> Response:
    from .telegram import send_supporter_test_broadcast

    result = send_supporter_test_broadcast()
    if not result.get("ok"):
        flash("Tes notifikasi gagal: {0}".format(result.get("error") or "Tidak diketahui."), "danger")
        return redirect(url_for("supporter.admin_settings"))

    sent = int(result.get("sent") or 0)
    group_sent = int(result.get("group_sent") or 0)
    missing = result.get("missing_usernames") or []
    if sent == 0 and group_sent == 0:
        msg = "Tidak ada penerima yang terjangkau. Pastikan admin sudah menekan /start di bot."
        if missing:
            msg += " Belum chat bot: " + ", ".join("@" + name for name in missing) + "."
        flash(msg, "warning")
    else:
        msg = "Tes notifikasi terkirim ke {0} admin dan {1} grup.".format(sent, group_sent)
        if missing:
            msg += " Belum terjangkau: " + ", ".join("@" + name for name in missing) + "."
        flash(msg, "success")
    return redirect(url_for("supporter.admin_settings"))


@supporter_bp.route("/admin/settings/telegram-admin/<int:mapping_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_telegram_admin(mapping_id: int) -> Response:
    ok = delete_telegram_admin_account(mapping_id)
    flash("Mapping admin Telegram dihapus." if ok else "Mapping tidak ditemukan.", "info" if ok else "warning")
    return redirect(url_for("supporter.admin_settings"))


@supporter_bp.route("/admin/settings/telegram-group/<int:group_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_telegram_group(group_id: int) -> Response:
    ok = delete_supporter_telegram_group(group_id)
    flash("Group Telegram dihapus." if ok else "Group tidak ditemukan.", "info" if ok else "warning")
    return redirect(url_for("supporter.admin_settings"))


@supporter_bp.route("/admin/export")
@role_required("admin")
def admin_export() -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "submission_id",
            "task_id",
            "task_title",
            "platform",
            "actions",
            "staff_name",
            "staff_email",
            "status",
            "base_points",
            "penalty_percent",
            "potential_points",
            "awarded_points",
            "submitted_at",
            "reviewed_at",
            "reviewer_name",
            "proof_url",
            "proof_file_path",
            "reviewer_note",
        ]
    )
    for row in export_submissions():
        writer.writerow(
            [
                row.get("id"),
                row.get("task_id"),
                row.get("task_title"),
                row.get("platform"),
                row.get("action_summary"),
                row.get("staff_name"),
                row.get("staff_email"),
                row.get("status"),
                row.get("base_points"),
                row.get("penalty_percent"),
                row.get("potential_points"),
                row.get("awarded_points"),
                to_jakarta(row.get("submitted_at")).isoformat() if row.get("submitted_at") else "",
                to_jakarta(row.get("reviewed_at")).isoformat() if row.get("reviewed_at") else "",
                row.get("reviewer_name"),
                row.get("proof_url"),
                row.get("proof_file_path"),
                row.get("reviewer_note"),
            ]
        )
    filename = f"supporter_submissions_{current_jakarta_time():%Y%m%d_%H%M%S}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
