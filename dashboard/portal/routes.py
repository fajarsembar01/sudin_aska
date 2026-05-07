"""Routes for portal assessment system (PANBERSS)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path, PurePosixPath
from urllib.parse import quote_plus, urlparse
import subprocess
import sys
import math
import json
import uuid
import re
import os
import io
import urllib.request as urlrequest
from zoneinfo import ZoneInfo

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    current_app,
    send_file,
    send_from_directory,
    abort,
    session,
)
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import current_user, role_required
from dashboard.db_access import get_cursor
from .permissions import (
    is_superadmin,
    can_assign_staff,
    can_manage_periods,
    can_reopen_assessment,
    can_delete_assessment,
    can_access_aska,
)
from .queries import (
    list_portal_schools,
    list_portal_rooms,
    list_school_rooms,
    get_school_by_id,
    get_active_assessment,
    get_active_period,
    create_assessment,
    get_assessment_by_id,
    get_assessment_scores,
    delete_assessment_scores,
    save_assessment_score,
    save_assessment_photo,
    save_room_details,
    get_assessment_room_details,
    get_assessment_photos,
    submit_assessment,
    list_staff_assessments,
    fetch_portal_stats,
    list_recent_assessments,
    list_staff_latest_assessments,
    fetch_top_schools,
    create_room,
    create_aspect,
    create_school,
    update_school_rooms,
    list_periods,
    reopen_assessment,
    fetch_random_photos,
    fetch_gallery_photos,
    fetch_gallery_latest_date,
    create_period,
    list_all_staff,
    list_all_staff_assignments_overview,
    update_staff_assignment_notes,
    delete_staff_assignments_by_ids,
    get_period_by_id,
    delete_assessment,
    fetch_school_avg_scores,
    fetch_bottom_schools,
    delete_photo,
    ensure_classroom_rooms_for_school,
    list_kecamatan,
    list_kelurahan,
    search_schools_by_npsn,
    get_school_by_npsn,
    get_room_by_id,
    update_room,
    delete_room,
    get_aspect_by_id,
    update_aspect,
    delete_aspect,
    list_kelurahan_by_urgency,
    fetch_schools_for_sidak,
    get_portal_schools_paginated,
    # Staff school assignments
    assign_staff_to_school,
    get_staff_assigned_schools,
    get_schools_assigned_to_staff_ids,
    remove_staff_school_assignment,
    list_all_staff_with_assignments,
    get_latest_final_assessment_for_period,
    # Assignment requests
    create_assignment_request,
    list_assignment_requests,
    update_assignment_request_status,
    list_coordinator_requests,
    set_active_period,
    update_period,
    delete_period,
    get_dashboard_user_profile,
    update_dashboard_user_profile,
    update_dashboard_user_profile_photo,
    # Classroom configuration
    enable_all_classroom_room_aspects_for_school,
    list_school_classrooms,
    create_school_classroom,
    update_school_classroom,
    delete_school_classroom,
    save_school_classrooms_batch,
    create_reopen_request,
    get_latest_reopen_request,
    update_reopen_request_status,
    list_reopen_requests,
    fetch_admin_pending_summary,
    fetch_admin_pending_preview,
    fetch_portal_undo_window_seconds,
    list_preview_pins,
    is_preview_pin,
    add_preview_pin,
    remove_preview_pin,
    get_optional_rooms_for_schools,
    get_room_with_aspects,
    list_portal_kontak,
    create_portal_kontak,
    update_portal_kontak,
    update_portal_kontak_status,
    get_portal_kontak_by_wilayah,
    delete_portal_kontak,
    upsert_portal_undo_window_seconds,
    list_school_user_ids_for_follow_up_notifications,
    create_room_follow_up_ticket,
    list_room_follow_up_tickets_for_school,
    count_room_follow_up_nav_badge_for_school,
    count_room_follow_up_nav_badge_for_staff,
    list_room_follow_up_tickets_for_admin,
    list_room_follow_up_tickets_for_staff,
    get_room_follow_up_ticket,
    get_latest_submitted_assessment_for_school,
    list_room_follow_up_updates,
    admin_create_room_follow_up_ticket,
    admin_update_room_follow_up_ticket,
    admin_delete_room_follow_up_ticket,
    add_school_room_follow_up_update,
    verify_room_follow_up_by_staff,
    list_due_room_follow_up_reminders,
    list_due_room_follow_up_reminders_for_staff,
    mark_room_follow_up_reminders_sent,
    PORTAL_FOLLOW_UP_STATUS_NEW,
    PORTAL_FOLLOW_UP_STATUS_IN_PROGRESS,
    PORTAL_FOLLOW_UP_STATUS_SUBMITTED,
    PORTAL_FOLLOW_UP_STATUS_DONE,
    PORTAL_UNDO_WINDOW_DEFAULT_SECONDS,
    PORTAL_UNDO_WINDOW_MIN_SECONDS,
    PORTAL_UNDO_WINDOW_MAX_SECONDS,
)
from dashboard.queries import (
    create_team_member_request,
    list_team_member_requests,
    list_team_member_requests_for_team,
    update_team_member_request_status,
    get_team_member_request,
    get_available_staff,
    list_dashboard_users,
)
from .classroom_rules import (
    expected_grade_levels,
    get_classroom_levels,
    get_template_room_name,
    grade_label,
    grade_label_map,
    normalize_jenjang,
    parse_room_info,
    sanitize_submitted_classrooms,
)
from dashboard.photo_stamp import decode_data_url_image, stamp_live_photo
from dashboard.telegram_notifications import (
    notify_assignment_request,
    notify_assignment_request_status_update,
    notify_reopen_request,
    notify_reopen_status_update,
    notify_team_member_request,
    notify_team_member_request_status_update,
)
from dashboard.daftar_tamu.queries import (
    PANBERS_ASSIGNMENT_NOTIFICATION_CATEGORY,
    PANBERS_FOLLOW_UP_NOTIFICATION_CATEGORY,
    PANBERS_REOPEN_NOTIFICATION_CATEGORY,
    PANBERS_TEAM_MEMBER_NOTIFICATION_CATEGORY,
    USER_APP_NOTIFICATION_CATEGORIES,
    create_user_notifications,
    fetch_user_notification_summary,
    list_user_notifications,
    mark_user_notifications_read,
)


def _get_room_aspects(room_id: int) -> list[dict]:
    """Return aspects for a room."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, room_id, name, description, sort_order, active, is_required
            FROM portal_aspects
            WHERE room_id = %s
            ORDER BY sort_order, id
            """,
            (room_id,),
        )
        return [dict(row) for row in cur.fetchall()]


portal_bp = Blueprint(
    "portal",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/portal",
)

UPLOAD_FOLDER = Path(__file__).parent.parent.parent / "uploads" / "portal"
PHOTO_REQUIRED_PCT = 90.0
FOLLOW_UP_THRESHOLD_PCT = 60.0
try:
    JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    JAKARTA_TZ = timezone(timedelta(hours=7), name="WIB")
_PREVIEW_ALLOWED_ROLES = {"staff", "coordinator", "sekolah"}
_PREVIEW_ADMIN_SESSION_KEY = "preview_admin_user"
_PREVIEW_TARGET_SESSION_KEY = "preview_target_user"
_PREVIEW_APP_SESSION_KEY = "preview_selected_app"
_PREVIEW_RETURN_URL_SESSION_KEY = "preview_return_url"
_PREVIEW_READ_ONLY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_PREVIEW_READ_ONLY_EXEMPT_ENDPOINTS = {"portal.preview_start", "portal.preview_pin"}
_LEGACY_SCORE_SCALE_MAX = 3
_NEW_SCORE_SCALE_MAX = 5
FOLLOW_UP_STATUS_LABELS = {
    PORTAL_FOLLOW_UP_STATUS_NEW: "Baru",
    PORTAL_FOLLOW_UP_STATUS_IN_PROGRESS: "Diproses Sekolah",
    PORTAL_FOLLOW_UP_STATUS_SUBMITTED: "Menunggu Verifikasi Staff",
    PORTAL_FOLLOW_UP_STATUS_DONE: "Selesai",
}
FOLLOW_UP_EVENT_LABELS = {
    "created": "Tiket dibuat otomatis",
    "admin_create": "Tiket dibuat admin",
    "admin_update": "Update oleh admin",
    "school_update": "Update dari sekolah",
    "school_submit": "Sekolah mengajukan verifikasi",
    "staff_verify": "Staff memverifikasi selesai",
    "reminder": "Pengingat bulanan",
}


def _normalize_assessment_scale_max(scale_max: int | None) -> int:
    try:
        parsed = int(scale_max) if scale_max is not None else _LEGACY_SCORE_SCALE_MAX
    except (TypeError, ValueError):
        parsed = _LEGACY_SCORE_SCALE_MAX
    return _NEW_SCORE_SCALE_MAX if parsed == _NEW_SCORE_SCALE_MAX else _LEGACY_SCORE_SCALE_MAX


def _assessment_score_min(scale_max: int) -> int:
    return 1 if scale_max == _NEW_SCORE_SCALE_MAX else 0


def _assessment_submit_baseline(scale_max: int) -> int:
    return 1 if scale_max == _NEW_SCORE_SCALE_MAX else 0


def _score_pct_from_raw(score: float | int | None, scale_max: int) -> float:
    try:
        score_value = float(score or 0)
    except (TypeError, ValueError):
        return 0.0
    normalized_scale = _normalize_assessment_scale_max(scale_max)
    if normalized_scale <= 0:
        return 0.0
    return (score_value / normalized_scale) * 100.0


def _build_assessment_score_config(assessment: dict | None) -> dict:
    scale_max = _normalize_assessment_scale_max((assessment or {}).get("score_scale_max"))
    score_min = _assessment_score_min(scale_max)
    score_baseline = _assessment_submit_baseline(scale_max)
    options = list(range(score_min, scale_max + 1))
    if scale_max == _NEW_SCORE_SCALE_MAX:
        legend = [
            {"value": 1, "label": "sangat kurang"},
            {"value": 2, "label": "kurang"},
            {"value": 3, "label": "cukup"},
            {"value": 4, "label": "baik"},
            {"value": 5, "label": "sangat baik"},
        ]
    else:
        legend = [
            {"value": 0, "label": "rusak"},
            {"value": 1, "label": "kurang baik"},
            {"value": 2, "label": "baik"},
            {"value": 3, "label": "sangat baik"},
        ]
    default_label = next((item["label"] for item in legend if item["value"] == score_min), "")
    return {
        "min": score_min,
        "max": scale_max,
        "default": score_min,
        "default_label": default_label,
        "baseline": score_baseline,
        "options": options,
        "legend": legend,
    }


def _is_preview_read_only_session() -> bool:
    preview_admin = session.get(_PREVIEW_ADMIN_SESSION_KEY)
    preview_target = session.get(_PREVIEW_TARGET_SESSION_KEY)
    return (
        isinstance(preview_admin, dict)
        and preview_admin.get("role") == "admin"
        and isinstance(preview_target, dict)
        and bool(preview_target.get("id"))
    )


def _preview_read_only_block_response(*, fallback_url: str) -> Response:
    message = "Mode preview aktif. Aksi edit dinonaktifkan."
    accept_header = (request.headers.get("Accept") or "").lower()
    content_type = (request.content_type or "").lower()
    wants_json = (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in accept_header
        or "application/json" in content_type
    )
    if wants_json:
        return jsonify({"success": False, "message": message, "preview_read_only": True}), 403

    flash(message, "warning")
    target_url = (request.referrer or "").strip() or fallback_url
    return redirect(target_url, code=303)


@portal_bp.before_request
def _enforce_preview_read_only_mode() -> Response | None:
    if request.method not in _PREVIEW_READ_ONLY_METHODS:
        return None
    if request.endpoint in _PREVIEW_READ_ONLY_EXEMPT_ENDPOINTS:
        return None
    if not _is_preview_read_only_session():
        return None
    return _preview_read_only_block_response(fallback_url=url_for("portal.preview_accounts"))


def _get_low_score_rooms(
    assessment_id: int,
    school_id: int,
    *,
    threshold_pct: float,
    require_missing_photo: bool = False,
) -> list[dict]:
    """Return rooms with average score below threshold."""
    assessment = get_assessment_by_id(assessment_id) or {}
    score_config = _build_assessment_score_config(assessment)
    scale_max = score_config["max"]
    missing_default = score_config["default"]

    rooms = list_school_rooms(school_id)
    if not rooms:
        return []

    scores = get_assessment_scores(assessment_id)
    score_map = {
        (s.get("school_room_id"), s.get("aspect_id")): s.get("score")
        for s in scores
    }
    photos = get_assessment_photos(assessment_id)
    rooms_with_photos = {p.get("school_room_id") for p in photos if p.get("school_room_id") is not None}

    missing: list[dict] = []
    for room in rooms:
        aspects = room.get("aspects") or []
        if not aspects:
            continue

        total = 0.0
        count = 0
        room_id = room.get("school_room_id")
        for aspect in aspects:
            aspect_id = aspect.get("id")
            score_val = score_map.get((room_id, aspect_id))
            if score_val is None:
                score_val = missing_default
            try:
                total += float(score_val)
            except (TypeError, ValueError):
                total += float(missing_default)
            count += 1

        if count == 0:
            continue

        pct = _score_pct_from_raw(total / count, scale_max)
        if pct >= threshold_pct:
            continue
        if require_missing_photo and room_id in rooms_with_photos:
            continue
        if room_id is None:
            continue
        missing.append(
            {
                "school_room_id": int(room_id),
                "room_id": int(room.get("room_id") or 0),
                "room_name": room.get("room_name") or f"Ruang {room_id}",
                "room_pct": round(pct, 1),
            }
        )

    return missing


def _get_low_score_rooms_missing_photos(
    assessment_id: int,
    school_id: int,
    threshold_pct: float = PHOTO_REQUIRED_PCT,
) -> list[dict]:
    """Return rooms with score below threshold that don't have photos yet."""
    return _get_low_score_rooms(
        assessment_id,
        school_id,
        threshold_pct=threshold_pct,
        require_missing_photo=True,
    )


def _status_badge_class(status: str) -> str:
    value = (status or "").strip().lower()
    if value == PORTAL_FOLLOW_UP_STATUS_DONE:
        return "success"
    if value == PORTAL_FOLLOW_UP_STATUS_SUBMITTED:
        return "warning"
    if value in {PORTAL_FOLLOW_UP_STATUS_NEW, PORTAL_FOLLOW_UP_STATUS_IN_PROGRESS}:
        return "primary"
    return "secondary"


def _follow_up_status_label(status: str) -> str:
    return FOLLOW_UP_STATUS_LABELS.get((status or "").strip().lower(), "Tidak diketahui")


def _follow_up_event_label(event_type: str) -> str:
    return FOLLOW_UP_EVENT_LABELS.get((event_type or "").strip().lower(), "Update")


def _ensure_follow_up_tickets_after_submit(
    *,
    assessment: dict,
    low_rooms: list[dict],
    actor: dict,
) -> int:
    """Create follow-up tickets for low-score rooms and notify sekolah users."""
    if not assessment or not low_rooms:
        return 0

    school_id = int(assessment.get("school_id") or 0)
    assessment_id = int(assessment.get("id") or 0)
    staff_id = int(assessment.get("staff_id") or 0)
    school_name = (assessment.get("school_name") or "").strip() or "sekolah"
    if not school_id or not assessment_id or not staff_id:
        return 0

    recipient_ids = list_school_user_ids_for_follow_up_notifications(school_id)

    created_count = 0
    actor_name = (actor or {}).get("full_name") or (actor or {}).get("email") or "Staff"
    for room in low_rooms:
        school_room_id = int(room.get("school_room_id") or 0)
        room_id = int(room.get("room_id") or 0)
        room_name = (room.get("room_name") or "").strip() or f"Ruang {school_room_id}"
        room_pct = float(room.get("room_pct") or 0.0)
        if school_room_id <= 0 or room_id <= 0:
            continue
        ticket = create_room_follow_up_ticket(
            assessment_id=assessment_id,
            school_id=school_id,
            school_room_id=school_room_id,
            room_id=room_id,
            room_name=room_name,
            staff_id=staff_id,
            trigger_score_pct=room_pct,
            threshold_pct=FOLLOW_UP_THRESHOLD_PCT,
        )
        follow_up_id = int(ticket.get("id") or 0)
        if follow_up_id <= 0:
            continue
        if not ticket.get("_created"):
            continue
        created_count += 1
        notif_title = "Tindak Lanjut PANBERSS"
        notif_message = (
            f"{school_name}: {room_name} skor {room_pct:.1f} (di bawah {FOLLOW_UP_THRESHOLD_PCT:.0f}). "
            "Mohon lakukan tindak lanjut."
        )
        if recipient_ids:
            create_user_notifications(
                recipient_ids=recipient_ids,
                category=PANBERS_FOLLOW_UP_NOTIFICATION_CATEGORY,
                title=notif_title,
                message=notif_message,
                link=url_for("portal.follow_up_detail", follow_up_id=follow_up_id),
                reference_table="portal_room_follow_up_tickets",
                reference_id=follow_up_id,
                metadata={
                    "status": PORTAL_FOLLOW_UP_STATUS_NEW,
                    "feature": "panbers_follow_up",
                    "ticket_id": follow_up_id,
                    "ticket_code": ticket.get("ticket_code"),
                    "school_id": school_id,
                    "school_name": school_name,
                    "assessment_id": assessment_id,
                    "room_name": room_name,
                    "room_score_pct": room_pct,
                    "threshold_pct": FOLLOW_UP_THRESHOLD_PCT,
                    "actor_name": actor_name,
                },
            )
    return created_count
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
AREA_CONTACTS = [
    {"area": "Cilincing", "name": "Neni", "phone": "+62 851-1085-1681"},
    {"area": "Kelapa Gading", "name": "Slamet", "phone": "+62 859-2123-2424"},
    {"area": "Koja", "name": "Rani", "phone": "+62 878-8032-8670"},
]


@portal_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    """Serve uploaded files (supports nested paths)."""
    normalized = (filename or "").replace("\\", "/")
    requested_path = PurePosixPath(normalized)
    if requested_path.is_absolute() or ".." in requested_path.parts:
        abort(404)

    target_path = (UPLOAD_FOLDER / requested_path.as_posix()).resolve()
    try:
        target_path.relative_to(UPLOAD_FOLDER.resolve())
    except ValueError:
        abort(404)

    if target_path.is_file():
        return send_from_directory(UPLOAD_FOLDER, requested_path.as_posix())

    # Guestbook photos may be cleaned up while historical rows still reference them.
    # Fall back to a local placeholder so dashboard pages do not emit avoidable 404s.
    if requested_path.parts and requested_path.parts[0] == "daftar_tamu":
        placeholder = Path(__file__).resolve().parent.parent / "static" / "logo" / "logo.png"
        if placeholder.is_file():
            return send_file(placeholder)

    abort(404)


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _collect_orphan_photo_files() -> tuple[list[dict], dict]:
    if not UPLOAD_FOLDER.exists():
        return [], {"total_files": 0, "db_photos": 0, "orphan_count": 0}

    with get_cursor() as cur:
        cur.execute("SELECT photo_path FROM portal_assessment_photos")
        db_paths = {
            (row["photo_path"] or "").replace("\\", "/")
            for row in cur.fetchall()
            if row.get("photo_path")
        }

    orphans: list[dict] = []
    total_files = 0
    for path in UPLOAD_FOLDER.rglob("*"):
        if not path.is_file():
            continue
        if not _allowed_file(path.name):
            continue
        rel = path.relative_to(UPLOAD_FOLDER).as_posix()
        if rel.startswith("logos/"):
            continue
        total_files += 1
        db_key = f"uploads/portal/{rel}"
        if db_key in db_paths:
            continue
        stat = path.stat()
        updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone(JAKARTA_TZ)
        orphans.append(
            {
                "rel_path": rel,
                "filename": path.name,
                "size_bytes": stat.st_size,
                "size_label": _format_bytes(stat.st_size),
                "updated_at": updated_at,
                "updated_at_iso": updated_at.isoformat(timespec="seconds"),
                "updated_at_label": updated_at.strftime("%d %b %Y %H:%M WIB"),
            }
        )

    orphans.sort(key=lambda item: item.get("updated_at") or datetime.min, reverse=True)
    stats = {
        "total_files": total_files,
        "db_photos": len(db_paths),
        "orphan_count": len(orphans),
    }
    return orphans, stats


def _normalize_photo_rel_path(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.replace("\\", "/").strip()
    if normalized.startswith("uploads/portal/"):
        normalized = normalized[len("uploads/portal/") :]
    normalized = normalized.lstrip("/")
    rel = PurePosixPath(normalized)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    if rel.parts and rel.parts[0] == "logos":
        return None
    return rel.as_posix()


def _build_profile_photo_url(photo_path: str | None) -> str | None:
    rel = _normalize_photo_rel_path(photo_path)
    if not rel:
        return None
    return url_for("portal.uploaded_file", filename=rel)


def _build_portal_file_url(file_path: str | None) -> str | None:
    rel = _normalize_photo_rel_path(file_path)
    if not rel:
        return None
    return url_for("portal.uploaded_file", filename=rel)


def _format_follow_up_datetime(value: object) -> str:
    if not isinstance(value, datetime):
        return "-"
    local_dt = value
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=timezone.utc)
    local_dt = local_dt.astimezone(JAKARTA_TZ)
    return local_dt.strftime("%d %b %Y, %H:%M WIB")


def _serialize_follow_up_timeline(updates: list[dict]) -> list[dict]:
    serialized: list[dict] = []
    for item in updates or []:
        row = dict(item)
        event_type = (row.get("event_type") or "").strip().lower()
        status_after = (row.get("status_after") or "").strip().lower()
        row["event_label"] = _follow_up_event_label(event_type)
        row["status_after_label"] = _follow_up_status_label(status_after) if status_after else ""
        row["status_badge"] = _status_badge_class(status_after) if status_after else "secondary"
        row["created_label"] = _format_follow_up_datetime(row.get("created_at"))
        row["photo_url"] = _build_portal_file_url((row.get("photo_path") or "").strip() or None)
        serialized.append(row)
    return serialized


def _dispatch_due_follow_up_reminders_for_user(*, user: dict, school: dict | None) -> int:
    if not user or (user.get("role") or "").strip().lower() != "sekolah":
        return 0
    school_id = int((school or {}).get("id") or 0)
    user_id = int(user.get("id") or 0)
    if school_id <= 0 or user_id <= 0:
        return 0

    due_items = list_due_room_follow_up_reminders(school_id, limit=20)
    if not due_items:
        return 0

    notified_ids: list[int] = []
    school_name = (school or {}).get("name") or "sekolah"
    for item in due_items:
        follow_up_id = int(item.get("id") or 0)
        if follow_up_id <= 0:
            continue
        room_name = (item.get("room_name_snapshot") or "").strip() or f"Ruang {follow_up_id}"
        ticket_code = (item.get("ticket_code") or "").strip()
        score_pct = float(item.get("trigger_score_pct") or 0.0)
        notif_title = "Pengingat Tindak Lanjut PANBERSS"
        message = (
            f"{school_name}: {room_name} belum selesai ditindaklanjuti. "
            f"Skor terakhir {score_pct:.1f} (<{FOLLOW_UP_THRESHOLD_PCT:.0f})."
        )
        if ticket_code:
            message = f"[{ticket_code}] {message}"

        created = create_user_notifications(
            recipient_ids=[user_id],
            category=PANBERS_FOLLOW_UP_NOTIFICATION_CATEGORY,
            title=notif_title,
            message=message,
            link=url_for("portal.follow_up_detail", follow_up_id=follow_up_id),
            reference_table="portal_room_follow_up_tickets",
            reference_id=follow_up_id,
            metadata={
                "status": (item.get("status") or "").strip().lower() or PORTAL_FOLLOW_UP_STATUS_IN_PROGRESS,
                "feature": "panbers_follow_up",
                "ticket_id": follow_up_id,
                "ticket_code": ticket_code or None,
                "room_name": room_name,
                "room_score_pct": score_pct,
                "is_reminder": True,
                "school_id": school_id,
                "threshold_pct": FOLLOW_UP_THRESHOLD_PCT,
            },
        )
        if created > 0:
            notified_ids.append(follow_up_id)

    if not notified_ids:
        return 0
    mark_room_follow_up_reminders_sent(follow_up_ids=notified_ids, actor_user_id=user_id)
    return len(notified_ids)


def _dispatch_due_follow_up_reminders_for_staff_user(*, user: dict) -> int:
    if not user or (user.get("role") or "").strip().lower() != "staff":
        return 0
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        return 0

    due_items = list_due_room_follow_up_reminders_for_staff(user_id, limit=20)
    if not due_items:
        return 0

    notified_ids: list[int] = []
    for item in due_items:
        follow_up_id = int(item.get("id") or 0)
        if follow_up_id <= 0:
            continue
        school_name = (item.get("school_name") or "").strip() or "Sekolah"
        room_name = (item.get("room_name_snapshot") or "").strip() or f"Ruang {follow_up_id}"
        ticket_code = (item.get("ticket_code") or "").strip()
        score_pct = float(item.get("trigger_score_pct") or 0.0)
        notif_title = "Reminder Verifikasi Tindak Lanjut PANBERSS"
        message = (
            f"{school_name}: {room_name} menunggu verifikasi staff. "
            f"Skor terakhir {score_pct:.1f} (<{FOLLOW_UP_THRESHOLD_PCT:.0f})."
        )
        if ticket_code:
            message = f"[{ticket_code}] {message}"
        created = create_user_notifications(
            recipient_ids=[user_id],
            category=PANBERS_FOLLOW_UP_NOTIFICATION_CATEGORY,
            title=notif_title,
            message=message,
            link=url_for("portal.follow_up_detail", follow_up_id=follow_up_id),
            reference_table="portal_room_follow_up_tickets",
            reference_id=follow_up_id,
            metadata={
                "status": PORTAL_FOLLOW_UP_STATUS_SUBMITTED,
                "feature": "panbers_follow_up",
                "ticket_id": follow_up_id,
                "ticket_code": ticket_code or None,
                "room_name": room_name,
                "school_name": school_name,
                "room_score_pct": score_pct,
                "is_reminder": True,
            },
        )
        if created > 0:
            notified_ids.append(follow_up_id)

    if not notified_ids:
        return 0
    mark_room_follow_up_reminders_sent(follow_up_ids=notified_ids, actor_user_id=user_id)
    return len(notified_ids)


def _portal_access_required(view):
    """Decorator for portal access (staff, sekolah, coordinator, or admin)."""
    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Silakan login terlebih dahulu.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        role = user.get("role")
        if role not in ("admin", "coordinator", "staff", "sekolah"):
            flash("Anda tidak memiliki akses ke portal.", "danger")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapper


def _needs_profile_photo_completion(user: dict | None) -> bool:
    """Return True when staff/coordinator must complete profile photo first."""
    if not isinstance(user, dict):
        return False
    role_value = (user.get("role") or "").strip().lower()
    if role_value not in {"staff", "coordinator"}:
        return False
    if _is_preview_read_only_session():
        return False
    return not bool((user.get("profile_photo_path") or "").strip())


def _require_profile_photo_redirect(user: dict | None) -> Response | None:
    """Redirect to profile page when photo completion is mandatory."""
    if not _needs_profile_photo_completion(user):
        return None
    flash("Foto profil wajib diisi untuk melanjutkan akses ke Portal.", "warning")
    return redirect(url_for("portal.user_profile_settings"))


def _resolve_profile_upload_redirect(default_target: str) -> str:
    """Resolve safe redirect target for profile photo upload responses."""
    target = (request.form.get("redirect_to") or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    return default_target


def _sanitize_phone(phone: str) -> str:
    """Normalize phone string to digits only for wa.me/api.whatsapp links."""
    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if digits_only.startswith("0"):
        digits_only = "62" + digits_only[1:]
    return digits_only


def _fetch_user_school(user_id: int) -> dict | None:
    """Return the school linked to the given user_id with metadata."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.id,
                   s.npsn,
                   s.name,
                   s.jenjang,
                   s.status,
                   s.alamat,
                   s.logo_url,
                   s.metadata,
                   s.kelurahan_id,
                   l.name AS kelurahan_name,
                    k.name AS kecamatan_name
            FROM dashboard_users u
            JOIN portal_schools s ON u.school_id = s.id
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            WHERE u.id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _fetch_user_kecamatan_name(user_id: int) -> str | None:
    """Return the kecamatan name linked to the given user_id (requested_kecamatan)."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT k.name
            FROM dashboard_users u
            LEFT JOIN portal_kecamatan k ON u.requested_kecamatan = k.id
            WHERE u.id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row and row["name"]:
            return row["name"]
    return None


def _fetch_dashboard_user_summary(user_id: int) -> dict | None:
    """Return a minimal dashboard user record for logging context."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, full_name, email, role
            FROM dashboard_users
            WHERE id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _fetch_monev_team(team_id: int) -> dict | None:
    """Return a minimal monev team record for logging context."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT mt.id, mt.name, mt.team_type, mt.kecamatan_id, k.name AS kecamatan_name
            FROM monev_teams mt
            LEFT JOIN portal_kecamatan k ON mt.kecamatan_id = k.id
            WHERE mt.id = %s
            """,
            (team_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _fetch_monev_member(member_id: int) -> dict | None:
    """Return a minimal monev team member record for logging context."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, team_id, staff_id
            FROM monev_team_members
            WHERE id = %s
            """,
            (member_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _fetch_monev_member_by_pair(team_id: int, staff_id: int) -> dict | None:
    """Return a minimal monev team member record for a team/staff pair."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, team_id, staff_id
            FROM monev_team_members
            WHERE team_id = %s AND staff_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (team_id, staff_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _fetch_reopen_request(request_id: int) -> dict | None:
    """Return a minimal reopen request record for logging context."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, assessment_id, staff_id, reason, status, reviewer_note
            FROM portal_assessment_reopen_requests
            WHERE id = %s
            """,
            (request_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _truncate_notification_text(value: object, max_length: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _build_status_label(status: str) -> str:
    value = (status or "").strip().lower()
    if value == "approved":
        return "Disetujui"
    if value == "rejected":
        return "Ditolak"
    if value == "pending":
        return "Menunggu"
    return "Diperbarui"


def _notify_panbers_reopen_status_change(
    *,
    request_id: int,
    assessment_id: int,
    status: str,
    actor: Optional[dict],
    assessment: Optional[dict] = None,
    reopen_request: Optional[dict] = None,
    reviewer_note: Optional[str] = None,
) -> None:
    safe_status = (status or "").strip().lower()
    if safe_status not in {"approved", "rejected"}:
        return

    request_row = reopen_request or _fetch_reopen_request(request_id) or {}
    recipient_ids: list[int] = []
    if request_row.get("staff_id"):
        try:
            recipient_ids.append(int(request_row.get("staff_id")))
        except (TypeError, ValueError):
            pass
    if not recipient_ids:
        return

    school_name = (assessment or {}).get("school_name") or "sekolah"
    status_label = _build_status_label(safe_status)
    actor_name = (actor or {}).get("full_name") or (actor or {}).get("email") or "Admin"
    note_text = _truncate_notification_text(reviewer_note)

    message = f"Permintaan reopen penilaian {school_name} {status_label.lower()}."
    if note_text:
        message += f" Catatan: {note_text}"

    create_user_notifications(
        recipient_ids=recipient_ids,
        category=PANBERS_REOPEN_NOTIFICATION_CATEGORY,
        title=f"Reopen Penilaian {status_label}",
        message=message,
        link=url_for("portal.view_assessment", assessment_id=assessment_id),
        reference_table="portal_assessment_reopen_requests",
        reference_id=request_id,
        metadata={
            "status": safe_status,
            "actor_name": actor_name,
            "request_id": int(request_id),
            "assessment_id": int(assessment_id),
            "school_name": school_name,
            "reviewer_note": note_text or None,
            "feature": "panbers_reopen",
        },
    )


def _notify_panbers_assignment_status_change(
    *,
    request_row: dict,
    status: str,
    actor: Optional[dict],
    reviewer_note: Optional[str] = None,
    school_name: Optional[str] = None,
    staff_name: Optional[str] = None,
    coordinator_name: Optional[str] = None,
    period_name: Optional[str] = None,
) -> None:
    safe_status = (status or "").strip().lower()
    if safe_status not in {"approved", "rejected"}:
        return

    recipient_ids: list[int] = []
    for key in ("coordinator_id", "staff_id"):
        raw_id = request_row.get(key)
        try:
            parsed_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if parsed_id > 0:
            recipient_ids.append(parsed_id)
    if not recipient_ids:
        return

    status_label = _build_status_label(safe_status)
    actor_name = (actor or {}).get("full_name") or (actor or {}).get("email") or "Admin"
    school_label = (school_name or "").strip() or "sekolah"
    staff_label = (staff_name or "").strip() or "staf"
    coordinator_label = (coordinator_name or "").strip()
    period_label = (period_name or "").strip()
    note_text = _truncate_notification_text(reviewer_note)

    message_parts = [f"Pengajuan penugasan {staff_label} ke {school_label} {status_label.lower()}."]
    if period_label:
        message_parts.append(f"Periode: {period_label}.")
    if coordinator_label:
        message_parts.append(f"Diajukan oleh {coordinator_label}.")
    if note_text:
        message_parts.append(f"Catatan: {note_text}")

    request_id = int(request_row.get("id") or 0)
    create_user_notifications(
        recipient_ids=recipient_ids,
        category=PANBERS_ASSIGNMENT_NOTIFICATION_CATEGORY,
        title=f"Pengajuan Penugasan {status_label}",
        message=" ".join(message_parts).strip(),
        link=url_for("portal.home"),
        reference_table="staff_assignment_requests",
        reference_id=request_id if request_id > 0 else None,
        metadata={
            "status": safe_status,
            "actor_name": actor_name,
            "request_id": request_id if request_id > 0 else None,
            "school_name": school_label,
            "staff_name": staff_label,
            "coordinator_name": coordinator_label or None,
            "period_name": period_label or None,
            "reviewer_note": note_text or None,
            "feature": "panbers_assignment_request",
        },
    )


def _notify_panbers_team_member_request_status_change(
    *,
    request_row: dict,
    status: str,
    actor: Optional[dict],
    reviewer_note: Optional[str] = None,
) -> None:
    safe_status = (status or "").strip().lower()
    if safe_status not in {"approved", "rejected"}:
        return

    recipient_ids: list[int] = []
    for key in ("requested_by", "staff_id"):
        raw_id = request_row.get(key)
        try:
            parsed_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if parsed_id > 0:
            recipient_ids.append(parsed_id)
    if not recipient_ids:
        return

    status_label = _build_status_label(safe_status)
    actor_name = (actor or {}).get("full_name") or (actor or {}).get("email") or "Admin"
    team_name = (request_row.get("team_name") or "").strip() or "Tim Monev"
    staff_name = (request_row.get("staff_name") or "").strip() or "staf"
    requester_name = (request_row.get("requested_by_name") or "").strip()
    note_text = _truncate_notification_text(reviewer_note)

    message_parts = [f"Permintaan anggota tim untuk {staff_name} di {team_name} {status_label.lower()}."]
    if requester_name:
        message_parts.append(f"Pengaju: {requester_name}.")
    if note_text:
        message_parts.append(f"Catatan: {note_text}")

    request_id = int(request_row.get("id") or 0)
    create_user_notifications(
        recipient_ids=recipient_ids,
        category=PANBERS_TEAM_MEMBER_NOTIFICATION_CATEGORY,
        title=f"Permintaan Anggota Tim {status_label}",
        message=" ".join(message_parts).strip(),
        link=url_for("portal.view_my_team"),
        reference_table="monev_team_member_requests",
        reference_id=request_id if request_id > 0 else None,
        metadata={
            "status": safe_status,
            "actor_name": actor_name,
            "request_id": request_id if request_id > 0 else None,
            "team_name": team_name,
            "staff_name": staff_name,
            "requested_by_name": requester_name or None,
            "reviewer_note": note_text or None,
            "feature": "panbers_team_member_request",
        },
    )


def _normalize_metadata(meta: object | None) -> dict:
    """Coerce metadata to a dict, falling back to empty dict on bad data."""
    if not meta:
        return {}
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, list):
        merged: dict = {}
        for item in meta:
            if isinstance(item, dict):
                merged.update(item)
        return merged
    if isinstance(meta, str):
        try:
            parsed = json.loads(meta)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _compute_missing_profile_fields(school: dict | None) -> list[str]:
    """Check required fields for sekolah profile completeness."""
    if not school:
        return ["school"]
    meta = _normalize_metadata(school.get("metadata"))
    expected_grades = _expected_grade_levels(school.get("jenjang") if school else None)
    required_keys = {
        "gmaps_url": "Link Google Maps",
        "student_count": "Jumlah siswa",
        "inclusion_student_count": "Jumlah siswa inklusi",
        "rombel_count": "Jumlah rombel",
        "school_phone": "Nomor telepon sekolah",
        "coordinator_phone": "Nomor operator sekolah",
        "cs_email": "Email sekolah untuk CS",
        "rt": "RT",
        "rw": "RW",
        "postal_code": "Kode Pos",
    }
    missing = []
    # Logo is now required
    if not school.get("logo_url"):
        missing.append("Logo sekolah")
    # alamat + kelurahan/kecamatan
    if not (school.get("alamat") and school.get("kelurahan_name") and school.get("kecamatan_name")):
        missing.append("Alamat dan wilayah")
    for key, label in required_keys.items():
        value = meta.get(key)
        # Anggap 0 sebagai nilai valid; hanya kosong yang dianggap belum diisi
        if value is None or value == "":
            missing.append(label)
    # Bangku kosong per jenjang
    if expected_grades:
        empty_map = meta.get("empty_seats_by_grade") or {}
        for g in expected_grades:
            val = empty_map.get(str(g))
            if val is None or val == "":
                missing.append("Jumlah bangku kosong per kelas")
                break
    else:
        if meta.get("empty_seats") is None or meta.get("empty_seats") == "":
            missing.append("Jumlah bangku kosong")
    return missing


def _detect_suspicious_profile_data(school: dict | None) -> list[str]:
    """Return reasons when school profile data looks inconsistent."""
    if not school:
        return []
    meta = _normalize_metadata(school.get("metadata"))

    def _to_int(val):
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    reasons = []
    student_count = _to_int(meta.get("student_count"))
    inclusion_count = _to_int(meta.get("inclusion_student_count"))
    rombel_count = _to_int(meta.get("rombel_count"))
    teacher_count = _to_int(meta.get("teacher_count"))
    staff_count = _to_int(meta.get("staff_count"))
    empty_seats = _to_int(meta.get("empty_seats"))

    empty_by_grade = meta.get("empty_seats_by_grade") or {}
    if isinstance(empty_by_grade, str):
        try:
            empty_by_grade = json.loads(empty_by_grade)
        except Exception:
            empty_by_grade = {}
    empty_by_grade_sum = None
    if isinstance(empty_by_grade, dict) and empty_by_grade:
        total = 0
        for v in empty_by_grade.values():
            val = _to_int(v)
            if val is not None:
                total += val
        empty_by_grade_sum = total

    if student_count is not None and inclusion_count is not None and inclusion_count > student_count:
        reasons.append("Siswa inklusi > total siswa")
    if student_count is not None and rombel_count is not None and rombel_count > student_count:
        reasons.append("Rombel > total siswa")
    if student_count is not None and empty_seats is not None and empty_seats > student_count:
        reasons.append("Bangku kosong > total siswa")
    if student_count is not None and empty_by_grade_sum is not None and empty_by_grade_sum > student_count:
        reasons.append("Bangku kosong per kelas > total siswa")
    if student_count is not None and student_count > 0:
        if teacher_count == 0:
            reasons.append("Jumlah guru 0")
        if staff_count == 0:
            reasons.append("Jumlah tendik 0")

    return reasons


def _expected_grade_levels(jenjang: str | None) -> list[int]:
    """Return grade levels based on jenjang."""
    return expected_grade_levels(jenjang)


def _classroom_grade_from_name(name: str) -> int | None:
    """Extract grade number from classroom name (supports variants like 5A)."""
    parsed = parse_room_info(name)
    if parsed:
        try:
            return int(parsed.get("grade_level"))
        except (TypeError, ValueError):
            return None
    return None


def _is_classroom_variant(name: str) -> bool:
    """Return True for variant classroom names like 'Ruang Kelas 5A'."""
    return bool((parse_room_info(name) or {}).get("is_variant"))


def _classroom_band_for_grade(grade: int) -> list[int]:
    if grade == 1:
        return list(range(1, 7))
    if grade == 7:
        return list(range(7, 10))
    if grade == 10:
        return list(range(10, 13))
    if grade in (-1, 0):
        return [-1, 0]
    return [grade]


def _sync_classroom_required_from_template(room: dict | None, is_required: bool) -> int:
    if not room:
        return 0
    name = (room.get("name") or "").strip()
    if not name:
        return 0
    grade = _classroom_grade_from_name(name)
    if grade is None or _is_classroom_variant(name):
        return 0
    target_grades = set(_classroom_band_for_grade(grade))
    if not target_grades:
        return 0

    with get_cursor(commit=True) as cur:
        cur.execute("SELECT id, name FROM portal_rooms")
        rows = cur.fetchall()
        target_ids = []
        for row in rows:
            row_grade = _classroom_grade_from_name(row["name"] or "")
            if row_grade in target_grades:
                target_ids.append(row["id"])
        if not target_ids:
            return 0
        cur.execute(
            "UPDATE portal_rooms SET is_required = %s WHERE id = ANY(%s)",
            (is_required, target_ids),
        )
        return cur.rowcount


def _sync_classroom_aspect_required_from_template(
    room_name: str | None,
    aspect_name: str | None,
    is_required: bool,
) -> int:
    if not room_name or not aspect_name:
        return 0
    if _is_classroom_variant(room_name):
        return 0
    grade = _classroom_grade_from_name(room_name)
    if grade is None:
        return 0
    target_grades = set(_classroom_band_for_grade(grade))
    if not target_grades:
        return 0

    with get_cursor(commit=True) as cur:
        cur.execute("SELECT id, name FROM portal_rooms")
        rows = cur.fetchall()
        target_ids = []
        for row in rows:
            row_grade = _classroom_grade_from_name(row["name"] or "")
            if row_grade in target_grades:
                target_ids.append(row["id"])
        if not target_ids:
            return 0
        cur.execute(
            """
            UPDATE portal_aspects
            SET is_required = %s
            WHERE room_id = ANY(%s)
              AND lower(btrim(name)) = lower(btrim(%s))
            """,
            (is_required, target_ids, aspect_name),
        )
        return cur.rowcount


def _sync_classroom_aspects_from_template_room(room: dict | None) -> int:
    if not room:
        return 0
    room_id = room.get("id")
    room_name = (room.get("name") or "").strip()
    if not room_id or not room_name:
        return 0
    if _is_classroom_variant(room_name):
        return 0
    if _classroom_grade_from_name(room_name) is None:
        return 0
    room_detail = get_room_with_aspects(int(room_id))
    if not room_detail:
        return 0
    total = 0
    for asp in room_detail.get("aspects") or []:
        total += _sync_classroom_aspect_required_from_template(
            room_name,
            asp.get("name"),
            bool(asp.get("is_required")),
        )
    return total


def _build_profile_payload(form_data: dict) -> dict:
    """Extract and normalize profile fields from form data or json."""
    def _clean_int(val):
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    def _clean_phone(val):
        raw = (val or "").strip()
        digits_only = "".join(ch for ch in raw if ch.isdigit())
        return digits_only

    def _clean_padded(val, length=3):
        """Clean and zero-pad a numeric string (for RT/RW)."""
        raw = (val or "").strip()
        digits_only = "".join(ch for ch in raw if ch.isdigit())
        if not digits_only:
            return ""
        return digits_only.zfill(length)[:length]

    def _clean_empty_seats_by_grade(raw_val):
        """Parse empty seats per grade mapping."""
        if raw_val in (None, ""):
            return {}
        parsed = {}
        try:
            if isinstance(raw_val, str):
                raw_val = json.loads(raw_val)
            if isinstance(raw_val, dict):
                for g, v in raw_val.items():
                    try:
                        grade = int(g)
                        val_int = _clean_int(v)
                        if val_int is not None and val_int >= 0:
                            parsed[str(grade)] = val_int
                    except Exception:
                        continue
        except Exception:
            return {}
        return parsed

    empty_seats_by_grade_raw = form_data.get("empty_seats_by_grade")
    empty_seats_by_grade = _clean_empty_seats_by_grade(empty_seats_by_grade_raw)
    empty_seats_val = _clean_int(form_data.get("empty_seats"))
    if empty_seats_by_grade:
        empty_seats_val = sum(v for v in empty_seats_by_grade.values() if v is not None)

    return {
        "logo_data": (form_data.get("logo_data") or ""),
        "alamat": (form_data.get("alamat") or "").strip(),
        "kelurahan_id": _clean_int(form_data.get("kelurahan_id")),
        "gmaps_url": (form_data.get("gmaps_url") or "").strip(),
        "rt": _clean_padded(form_data.get("rt"), 3),
        "rw": _clean_padded(form_data.get("rw"), 3),
        "postal_code": _clean_phone(form_data.get("postal_code")),
        "student_count": _clean_int(form_data.get("student_count")),
        "inclusion_student_count": _clean_int(form_data.get("inclusion_student_count")),
        "empty_seats": empty_seats_val,
        "empty_seats_by_grade": empty_seats_by_grade,
        "rombel_count": _clean_int(form_data.get("rombel_count")),
        "teacher_count": _clean_int(form_data.get("teacher_count")),
        "staff_count": _clean_int(form_data.get("staff_count")),
        "school_phone": _clean_phone(form_data.get("school_phone")),
        "coordinator_phone": _clean_phone(form_data.get("coordinator_phone")),
        "fax": (form_data.get("fax") or "").strip(),
        "cs_email": (form_data.get("cs_email") or "").strip(),
        "website": (form_data.get("website") or "").strip(),
        "instagram": (form_data.get("instagram") or "").strip(),
        "tiktok": (form_data.get("tiktok") or "").strip(),
        "youtube": (form_data.get("youtube") or "").strip(),
        "wa_channel": (form_data.get("wa_channel") or "").strip(),
        "telegram": (form_data.get("telegram") or "").strip(),
    }


def _validate_profile_data(payload: dict, *, jenjang: str | None = None) -> list[str]:
    errors = []
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    if not payload.get("alamat"):
        errors.append("Alamat sekolah wajib diisi.")
    if not payload.get("kelurahan_id"):
        errors.append("Kelurahan wajib dipilih.")
    if not payload.get("gmaps_url"):
        errors.append("Link Google Maps wajib diisi.")
    # RT and RW must be 3 digits
    rt_val = payload.get("rt", "")
    if not rt_val or len(rt_val) != 3 or not rt_val.isdigit():
        errors.append("RT wajib diisi (3 angka, contoh: 001).")
    rw_val = payload.get("rw", "")
    if not rw_val or len(rw_val) != 3 or not rw_val.isdigit():
        errors.append("RW wajib diisi (3 angka, contoh: 001).")
    postal_code = payload.get("postal_code", "")
    if not postal_code or not postal_code.isdigit():
        errors.append("Kode Pos wajib diisi (angka).")
    if payload.get("student_count") is None:
        errors.append("Jumlah siswa wajib diisi.")
    if payload.get("inclusion_student_count") is None:
        errors.append("Jumlah siswa inklusi wajib diisi.")
    expected_grades = _expected_grade_levels(jenjang)
    if expected_grades:
        empty_map = payload.get("empty_seats_by_grade") or {}
        if not isinstance(empty_map, dict) or not empty_map:
            errors.append("Jumlah bangku kosong per kelas wajib diisi.")
        else:
            for g in expected_grades:
                val = empty_map.get(str(g))
                if val is None:
                    errors.append(f"Bangku kosong {grade_label(jenjang, g)} wajib diisi.")
                    break
                try:
                    int_val = int(val)
                    if int_val < 0:
                        errors.append(f"Bangku kosong {grade_label(jenjang, g)} harus >= 0.")
                        break
                except Exception:
                    errors.append(f"Bangku kosong {grade_label(jenjang, g)} harus angka.")
                    break
    else:
        if payload.get("empty_seats") is None:
            errors.append("Jumlah bangku kosong wajib diisi.")
    if payload.get("rombel_count") is None:
        errors.append("Jumlah rombel wajib diisi.")
    if payload.get("teacher_count") is None:
        errors.append("Jumlah guru wajib diisi.")
    if payload.get("staff_count") is None:
        errors.append("Jumlah tendik wajib diisi.")
    for phone_key, label in [
        ("school_phone", "Nomor telepon sekolah"),
        ("coordinator_phone", "Nomor operator sekolah"),
    ]:
        phone_val = payload.get(phone_key)
        if not phone_val:
            errors.append(f"{label} wajib diisi.")
        elif not phone_val.isdigit():
            errors.append(f"{label} hanya boleh berisi angka.")
    cs_email = payload.get("cs_email", "")
    if not cs_email:
        errors.append("Email sekolah (CS) wajib diisi.")
    elif not email_re.match(cs_email):
        errors.append("Format email sekolah (CS) tidak valid.")
    return errors


def _save_school_profile(school_id: int, data: dict) -> None:
    """Persist profile data into portal_schools (address + metadata + logo)."""
    import base64
    
    logo_data = data.get("logo_data", "")
    logo_url = None
    
    # Handle logo upload from base64
    if logo_data and logo_data.startswith("data:image"):
        try:
            # Remove data URL prefix
            header, encoded = logo_data.split(",", 1)
            img_bytes = base64.b64decode(encoded)
            
            # Create logos directory
            logos_dir = UPLOAD_FOLDER / "logos"
            logos_dir.mkdir(parents=True, exist_ok=True)
            
            # Save with school_id as filename
            filename = f"school_{school_id}.jpg"
            filepath = logos_dir / filename
            with open(filepath, "wb") as f:
                f.write(img_bytes)
            
            logo_url = url_for("portal.uploaded_file", filename=f"logos/{filename}")
        except Exception as e:
            current_app.logger.exception(f"Error saving logo: {e}")
    
    # Exclude non-metadata fields
    meta_fields = {k: v for k, v in data.items() if k not in {"alamat", "kelurahan_id", "logo_data"}}
    
    with get_cursor(commit=True) as cur:
        if logo_url:
            cur.execute(
                """
                UPDATE portal_schools
                SET alamat = %s,
                    kelurahan_id = %s,
                    logo_url = %s,
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (data.get("alamat"), data.get("kelurahan_id"), logo_url, json.dumps(meta_fields), school_id),
            )
        else:
            cur.execute(
                """
                UPDATE portal_schools
                SET alamat = %s,
                    kelurahan_id = %s,
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (data.get("alamat"), data.get("kelurahan_id"), json.dumps(meta_fields), school_id),
            )


def _sanitize_phone(phone: str) -> str:
    """Normalize phone string to digits only for wa.me/api.whatsapp links."""
    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if digits_only.startswith("0"):
        digits_only = "62" + digits_only[1:]
    return digits_only


def _build_coordinator_contacts(school: dict | None = None, *, area_name: str | None = None) -> list[dict]:
    """Return area contact list with wa links, optionally personalized with school or user area info."""
    contacts = []
    message = "Halo, kami ingin menghubungi admin wilayah."
    if school and school.get("name") and school.get("npsn"):
        message = (
            f"Halo, kami dari {school.get('name')} (NPSN {school.get('npsn')}) "
            "ingin menghubungi admin wilayah."
        )
    elif school and school.get("name"):
        message = f"Halo, kami dari {school.get('name')} ingin menghubungi admin wilayah."
    elif area_name:
        message = f"Halo, kami dari wilayah {area_name} ingin menghubungi admin wilayah."
    area_match_source = area_name
    if not area_match_source and school:
        area_match_source = school.get("kecamatan_name")

    for row in list_portal_kontak():
        area = (row.get("wilayah") or "").strip()
        if not area:
            continue
        is_user_area = False
        if area_match_source:
            # Simple match: check if area name contains the contact area keyword
            is_user_area = area.lower() in area_match_source.lower()
        for idx, (name_key, phone_key, active_key) in enumerate(
            (
                ("nama", "kontak", "kontak_1_active"),
                ("nama_2", "kontak_2", "kontak_2_active"),
            ),
            start=1,
        ):
            name = (row.get(name_key) or "").strip()
            phone = (row.get(phone_key) or "").strip()
            if not name and not phone:
                continue
            phone_for_link = _sanitize_phone(phone)
            if not phone_for_link:
                continue
            is_active = row.get(active_key)
            if is_active is None:
                is_active = True
            contacts.append(
                {
                    "area": area,
                    "name": name,
                    "phone": phone,
                    "wa_link": f"https://api.whatsapp.com/send?phone={phone_for_link}&text={quote_plus(message)}",
                    "normalized_area": area.lower(),
                    "is_user_area": is_user_area,
                    "is_active": bool(is_active),
                    "contact_index": idx,
                }
            )
    return contacts


# ===== Staff Portal Routes =====


@portal_bp.route("/")
@_portal_access_required
def home() -> Response:
    """Portal home by role."""
    user = current_user()
    role = user.get("role")
    display_name = (user.get("full_name") or user.get("email") or "").strip()
    header_title = "Selamat Datang"
    if display_name:
        header_title = f"Selamat Datang, {display_name}"
    photo_redirect = _require_profile_photo_redirect(user)
    if photo_redirect:
        return photo_redirect

    if role == "sekolah":
        return redirect(url_for("portal.sekolah_home"))

    if role == "admin":
        return redirect(url_for("portal.admin_stats"))

    if role == "staff":
        cards = [
            {
                "title": "PANBERSS",
                "description": "Akses tugas Monev dan proses penilaian PANBERSS.",
                "icon": "bi-building",
                "href": url_for("portal.staff_assignments"),
                "col_class": "col-md-6 col-12",
            },
            {
                "title": "Hospitality",
                "description": "Penilaian hospitality tanpa penugasan, terhubung buku tamu.",
                "icon": "bi-house-heart",
                "href": url_for("hospitality.staff_home"),
                "col_class": "col-md-6 col-12",
            },
            {
                "title": "Buku Tamu",
                "description": "Pantau dashboard buku tamu sesuai lokasi unit kerja Anda.",
                "icon": "bi-person-vcard",
                "href": url_for("daftar_tamu.admin_dashboard"),
                "col_class": "col-md-6 col-12",
            },
        ]
        return render_template(
            "role_selection.html",
            page_title="ASKA Portal - Pilih Layanan Staff ",
            page_description="Pilih layanan ASKA Portal untuk Staff",
            header_title=header_title,
            header_subtitle="Silakan pilih layanan ASKA Portal",
            cards=cards,
            default_col_class="col-md-6 col-12",
            enable_odd_center=True,
            show_logout=True,
        )
    if role == "coordinator":
        cards = [
            {
                "title": "PANBERSS",
                "description": "Akses statistik dan monitoring PANBERSS tim Anda.",
                "icon": "bi-building",
                "href": url_for("portal.coordinator_stats"),
                "col_class": "col-md-6 col-12",
            },
            {
                "title": "Hospitality",
                "description": "Lakukan penilaian hospitality seperti staff.",
                "icon": "bi-house-heart",
                "href": url_for("hospitality.staff_home"),
                "col_class": "col-md-6 col-12",
            },
            {
                "title": "Buku Tamu",
                "description": "Pantau dashboard buku tamu pribadi untuk sekolah negeri.",
                "icon": "bi-person-vcard",
                "href": url_for("daftar_tamu.coordinator_dashboard"),
                "col_class": "col-md-6 col-12",
            },
        ]
        return render_template(
            "role_selection.html",
            page_title="ASKA Portal - Pilih Layanan Koordinator",
            page_description="Pilih layanan ASKA Portal untuk Koordinator",
            header_title=header_title,
            header_subtitle="Silakan pilih layanan ASKA Portal",
            cards=cards,
            default_col_class="col-md-6 col-12",
            enable_odd_center=True,
            show_logout=True,
        )

    return redirect(url_for("portal.staff_oss_home"))


@portal_bp.route("/staff/oss")
@role_required("staff")
def staff_oss_home() -> Response:
    """Staff OSS home - list staff assessments."""
    user = current_user()
    assessments = list_staff_assessments(user["id"])
    return render_template(
        "portal/staff/home.html",
        assessments=assessments,
        user=user,
    )


@portal_bp.route("/schools")
@_portal_access_required
def schools() -> Response:
    """List schools available for assessment."""
    user = current_user()
    role = user.get("role")
    
    # Sekolah role redirect
    if role == "sekolah":
        return redirect(url_for("portal.sekolah_home"))
    
    # Staff can only see assigned schools - redirect to assignments page
    if role == "staff":
        return redirect(url_for("portal.staff_assignments"))
    
    search = request.args.get("q", "").strip()
    jenjang = request.args.get("jenjang", "").strip() or None
    page = request.args.get("page", 1, type=int)
    per_page = 20
    
    pagination = get_portal_schools_paginated(
        page=page, 
        per_page=per_page, 
        search=search or None, 
        jenjang=jenjang,
        kecamatan_ids=None
    )
    
    return render_template(
        "portal/assessments/school_select.html",
        schools=pagination["items"],
        pagination=pagination,
        search=search,
        jenjang=jenjang,
    )


# ===== Sekolah Landing =====

@portal_bp.route("/sekolah")
@role_required("sekolah")
def sekolah_home() -> Response:
    """Landing page for sekolah role (choose Buku Tamu or PANBERSS)."""
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung dengan sekolah. Hubungi admin.", "warning")
    subtitle = ""
    if school and school.get("name") and school.get("npsn"):
        subtitle = f"{school.get('name')} • NPSN {school.get('npsn')}"
    cards = [
         {
             "title": "PANBERSS",
             "description": "Konfigurasi ruangan untuk pemantauan kebersihan dan sarana sekolah.",
             "icon": "bi bi-building",
             "href": url_for("portal.sekolah_rooms"),
             "col_class": "col-md-6 col-12",
        },
        {
            "title": "Hospitality",
            "description": "Lihat hasil penilaian hospitality dan beri komentar.",
            "icon": "bi-house-heart",
            "href": url_for("hospitality.school_home"),
            "col_class": "col-md-6 col-12",
        },
        {
            "title": "Buku Tamu",
            "description": "Input kunjungan tamu dan pantau status verifikasi kunjungan.",
            "icon": "bi-person-vcard",
            "href": url_for("daftar_tamu.sekolah_guestbook"),
            "col_class": "col-md-6 col-12",
        },
    ]
    return render_template(
        "role_selection.html",
        page_title="ASKA Portal - Pilih Layanan Sekola",
        page_description="Pilih layanan ASKA Portal yang ingin Anda akses",
        header_title="Selamat Datang",
        header_subtitle=subtitle,
        cards=cards,
        default_col_class="col-md-6 col-12",
        enable_odd_center=True,
        show_logout=True,
    )


def _annotate_follow_up_ticket(ticket: dict) -> dict:
    row = dict(ticket or {})
    status_value = (row.get("status") or "").strip().lower()
    row["status_label"] = _follow_up_status_label(status_value)
    row["status_badge"] = _status_badge_class(status_value)
    row["created_label"] = _format_follow_up_datetime(row.get("created_at"))
    row["updated_label"] = _format_follow_up_datetime(row.get("updated_at"))
    row["submitted_label"] = _format_follow_up_datetime(row.get("submitted_at"))
    row["verified_label"] = _format_follow_up_datetime(row.get("verified_at"))
    row["last_event_label"] = _follow_up_event_label(row.get("last_event_type") or "")
    row["last_event_at_label"] = _format_follow_up_datetime(row.get("last_event_at"))
    return row


def _can_access_follow_up_ticket(user: dict, ticket: dict) -> bool:
    role_value = (user.get("role") or "").strip().lower()
    if role_value in {"admin", "coordinator"}:
        return True
    if role_value == "staff":
        return int(user.get("id") or 0) == int(ticket.get("staff_id") or 0)
    if role_value == "sekolah":
        school = _fetch_user_school(user.get("id"))
        return int((school or {}).get("id") or 0) == int(ticket.get("school_id") or 0)
    return False


def _parse_live_photo_payload() -> tuple[bytes | None, float | None, float | None, datetime | None]:
    photo_data = (request.form.get("photo_data") or "").strip()
    if not photo_data:
        return None, None, None, None

    source_bytes = decode_data_url_image(photo_data)
    lat_raw = request.form.get("photo_latitude")
    lon_raw = request.form.get("photo_longitude")
    try:
        latitude = float(lat_raw)
        longitude = float(lon_raw)
    except (TypeError, ValueError):
        raise ValueError("Lokasi GPS foto progress tidak valid.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Lokasi GPS foto progress di luar jangkauan.")

    captured_raw = (request.form.get("photo_captured_at") or "").strip()
    captured_at: datetime | None = None
    if captured_raw:
        try:
            captured_at = datetime.fromisoformat(captured_raw.replace("Z", "+00:00"))
        except ValueError:
            captured_at = None
    if captured_at is None:
        captured_at = datetime.now(JAKARTA_TZ)
    return source_bytes, latitude, longitude, captured_at


def _save_follow_up_photo(file_storage, *, follow_up_id: int, school_label: str | None) -> str | None:
    live_source_bytes, live_latitude, live_longitude, live_captured_at = _parse_live_photo_payload()
    if live_source_bytes:
        stamped = stamp_live_photo(
            source_bytes=live_source_bytes,
            latitude=float(live_latitude),
            longitude=float(live_longitude),
            captured_at=live_captured_at or datetime.now(JAKARTA_TZ),
            school_label=school_label,
            upload_root=UPLOAD_FOLDER / "followups",
            relative_root="uploads/portal/followups",
            file_prefix=f"followup_{int(follow_up_id)}",
        )
        return stamped.get("stamped_path")

    if not file_storage or not getattr(file_storage, "filename", ""):
        return None
    if not _allowed_file(file_storage.filename):
        raise ValueError("Format foto tidak didukung. Gunakan PNG, JPG, JPEG, atau WEBP.")
    file_storage.stream.seek(0)
    source_bytes = file_storage.stream.read()
    stamped = stamp_live_photo(
        source_bytes=source_bytes,
        latitude=0.0,
        longitude=0.0,
        captured_at=datetime.now(JAKARTA_TZ),
        school_label=school_label,
        upload_root=UPLOAD_FOLDER / "followups",
        relative_root="uploads/portal/followups",
        file_prefix=f"followup_{int(follow_up_id)}",
    )
    return stamped.get("stamped_path")


@portal_bp.route("/sekolah/tindak-lanjut")
@role_required("sekolah")
def sekolah_follow_ups() -> Response:
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung ke data sekolah.", "warning")
        return redirect(url_for("portal.sekolah_home"))

    tickets = [
        _annotate_follow_up_ticket(item)
        for item in list_room_follow_up_tickets_for_school(int(school.get("id")), include_done=True, limit=200)
    ]
    open_count = sum(1 for item in tickets if (item.get("status") or "").strip().lower() != PORTAL_FOLLOW_UP_STATUS_DONE)
    done_count = len(tickets) - open_count
    return render_template(
        "portal/sekolah/follow_ups.html",
        school=school,
        tickets=tickets,
        open_count=open_count,
        done_count=done_count,
    )


@portal_bp.route("/staff/tindak-lanjut")
@role_required("staff")
def staff_follow_ups() -> Response:
    user = current_user()
    tickets = [
        _annotate_follow_up_ticket(item)
        for item in list_room_follow_up_tickets_for_staff(int(user.get("id") or 0), include_done=True, limit=250)
    ]
    pending_verify_count = sum(
        1 for item in tickets if (item.get("status") or "").strip().lower() == PORTAL_FOLLOW_UP_STATUS_SUBMITTED
    )
    open_count = sum(1 for item in tickets if (item.get("status") or "").strip().lower() != PORTAL_FOLLOW_UP_STATUS_DONE)
    return render_template(
        "portal/staff/follow_ups.html",
        tickets=tickets,
        pending_verify_count=pending_verify_count,
        open_count=open_count,
    )


@portal_bp.route("/admin/tindak-lanjut")
@role_required("admin")
def admin_follow_ups() -> Response:
    query_text = (request.args.get("q") or "").strip()
    status_filter = (request.args.get("status") or "").strip().lower()
    school_filter = request.args.get("school_id", type=int)
    staff_filter = request.args.get("staff_id", type=int)
    create_school_id = request.args.get("create_school_id", type=int)

    tickets = [
        _annotate_follow_up_ticket(item)
        for item in list_room_follow_up_tickets_for_admin(
            status=status_filter or None,
            school_id=school_filter if school_filter and school_filter > 0 else None,
            staff_id=staff_filter if staff_filter and staff_filter > 0 else None,
            search=query_text or None,
            limit=500,
        )
    ]

    status_counts = {
        PORTAL_FOLLOW_UP_STATUS_NEW: 0,
        PORTAL_FOLLOW_UP_STATUS_IN_PROGRESS: 0,
        PORTAL_FOLLOW_UP_STATUS_SUBMITTED: 0,
        PORTAL_FOLLOW_UP_STATUS_DONE: 0,
    }
    for item in tickets:
        status_value = (item.get("status") or "").strip().lower()
        if status_value in status_counts:
            status_counts[status_value] += 1

    schools = list_portal_schools(active_only=False)
    staff_options = list_all_staff()
    create_school = get_school_by_id(create_school_id) if create_school_id else None
    create_school_rooms = list_school_rooms(int(create_school_id)) if create_school_id else []
    create_latest_assessment = (
        get_latest_submitted_assessment_for_school(int(create_school_id))
        if create_school_id
        else None
    )

    return render_template(
        "portal/admin/follow_ups.html",
        tickets=tickets,
        schools=schools,
        staff_options=staff_options,
        query_text=query_text,
        status_filter=status_filter,
        school_filter=school_filter or 0,
        staff_filter=staff_filter or 0,
        status_counts=status_counts,
        create_school_id=create_school_id or 0,
        create_school=create_school,
        create_school_rooms=create_school_rooms,
        create_latest_assessment=create_latest_assessment,
        follow_up_status_labels=FOLLOW_UP_STATUS_LABELS,
    )


@portal_bp.route("/admin/tindak-lanjut/create", methods=["POST"])
@role_required("admin")
def admin_follow_up_create() -> Response:
    user = current_user()
    school_id = request.form.get("school_id", type=int)
    school_room_id = request.form.get("school_room_id", type=int)
    staff_id = request.form.get("staff_id", type=int)
    assessment_id = request.form.get("assessment_id", type=int)
    status_value = (request.form.get("status") or "").strip().lower()
    note = (request.form.get("note") or "").strip()

    try:
        trigger_score_pct = float((request.form.get("trigger_score_pct") or "").strip() or "0")
    except (TypeError, ValueError):
        trigger_score_pct = -1.0
    try:
        threshold_pct = float((request.form.get("threshold_pct") or "").strip() or "60")
    except (TypeError, ValueError):
        threshold_pct = -1.0

    if status_value not in {
        PORTAL_FOLLOW_UP_STATUS_NEW,
        PORTAL_FOLLOW_UP_STATUS_IN_PROGRESS,
        PORTAL_FOLLOW_UP_STATUS_SUBMITTED,
        PORTAL_FOLLOW_UP_STATUS_DONE,
    }:
        status_value = PORTAL_FOLLOW_UP_STATUS_NEW

    if not school_id or school_id <= 0:
        flash("Pilih sekolah terlebih dahulu.", "warning")
        return redirect(url_for("portal.admin_follow_ups"))
    if not school_room_id or school_room_id <= 0:
        flash("Pilih ruangan sekolah terlebih dahulu.", "warning")
        return redirect(url_for("portal.admin_follow_ups", create_school_id=school_id))
    if not staff_id or staff_id <= 0:
        flash("Pilih staff penanggung jawab.", "warning")
        return redirect(url_for("portal.admin_follow_ups", create_school_id=school_id))
    if trigger_score_pct < 0 or trigger_score_pct > 100:
        flash("Skor trigger harus di antara 0 sampai 100.", "warning")
        return redirect(url_for("portal.admin_follow_ups", create_school_id=school_id))
    if threshold_pct <= 0 or threshold_pct > 100:
        flash("Threshold harus di antara 1 sampai 100.", "warning")
        return redirect(url_for("portal.admin_follow_ups", create_school_id=school_id))

    school = get_school_by_id(int(school_id))
    if not school:
        flash("Sekolah tidak ditemukan.", "warning")
        return redirect(url_for("portal.admin_follow_ups"))
    school_rooms = list_school_rooms(int(school_id))
    selected_room = next(
        (item for item in school_rooms if int(item.get("school_room_id") or 0) == int(school_room_id)),
        None,
    )
    if not selected_room:
        flash("Ruangan sekolah tidak ditemukan.", "warning")
        return redirect(url_for("portal.admin_follow_ups", create_school_id=school_id))

    if assessment_id and assessment_id > 0:
        assessment = get_assessment_by_id(int(assessment_id))
        if not assessment or int(assessment.get("school_id") or 0) != int(school_id):
            flash("Assessment tidak valid untuk sekolah ini.", "warning")
            return redirect(url_for("portal.admin_follow_ups", create_school_id=school_id))
        if (assessment.get("status") or "").strip().lower() not in {"submitted", "verified"}:
            flash("Assessment harus berstatus submitted/verified untuk membuat tiket.", "warning")
            return redirect(url_for("portal.admin_follow_ups", create_school_id=school_id))
    else:
        latest_assessment = get_latest_submitted_assessment_for_school(int(school_id))
        if not latest_assessment:
            flash("Belum ada assessment submitted/verified untuk sekolah ini.", "warning")
            return redirect(url_for("portal.admin_follow_ups", create_school_id=school_id))
        assessment_id = int(latest_assessment.get("id") or 0)

    created = admin_create_room_follow_up_ticket(
        assessment_id=int(assessment_id),
        school_id=int(school_id),
        school_room_id=int(school_room_id),
        room_id=int(selected_room.get("room_id") or 0),
        room_name=(selected_room.get("room_name") or "").strip(),
        staff_id=int(staff_id),
        trigger_score_pct=float(trigger_score_pct),
        threshold_pct=float(threshold_pct),
        status=status_value,
        actor_user_id=int(user.get("id") or 0),
        note=note,
    )
    follow_up_id = int(created.get("id") or 0)
    if follow_up_id <= 0:
        flash("Gagal membuat tiket tindak lanjut.", "danger")
        return redirect(url_for("portal.admin_follow_ups", create_school_id=school_id))

    if not created.get("_created"):
        flash("Tiket untuk assessment dan ruangan ini sudah ada.", "info")
    else:
        flash("Tiket tindak lanjut berhasil dibuat.", "success")

    return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))


@portal_bp.route("/admin/tindak-lanjut/<int:follow_up_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def admin_follow_up_edit(follow_up_id: int) -> Response:
    user = current_user()
    ticket = get_room_follow_up_ticket(follow_up_id)
    if not ticket:
        flash("Tiket tindak lanjut tidak ditemukan.", "warning")
        return redirect(url_for("portal.admin_follow_ups"))

    if request.method == "POST":
        staff_id = request.form.get("staff_id", type=int)
        status_value = (request.form.get("status") or "").strip().lower()
        note = (request.form.get("note") or "").strip()
        return_to = (request.form.get("return_to") or "").strip()
        try:
            trigger_score_pct = float((request.form.get("trigger_score_pct") or "").strip() or "0")
        except (TypeError, ValueError):
            trigger_score_pct = -1.0
        try:
            threshold_pct = float((request.form.get("threshold_pct") or "").strip() or "60")
        except (TypeError, ValueError):
            threshold_pct = -1.0

        if not staff_id or staff_id <= 0:
            flash("Staff penanggung jawab wajib dipilih.", "warning")
            return redirect(url_for("portal.admin_follow_up_edit", follow_up_id=follow_up_id))
        if trigger_score_pct < 0 or trigger_score_pct > 100:
            flash("Skor trigger harus di antara 0 sampai 100.", "warning")
            return redirect(url_for("portal.admin_follow_up_edit", follow_up_id=follow_up_id))
        if threshold_pct <= 0 or threshold_pct > 100:
            flash("Threshold harus di antara 1 sampai 100.", "warning")
            return redirect(url_for("portal.admin_follow_up_edit", follow_up_id=follow_up_id))

        updated = admin_update_room_follow_up_ticket(
            follow_up_id=follow_up_id,
            actor_user_id=int(user.get("id") or 0),
            staff_id=int(staff_id),
            status=status_value,
            trigger_score_pct=float(trigger_score_pct),
            threshold_pct=float(threshold_pct),
            note=note,
        )
        if not updated:
            flash("Gagal memperbarui tiket tindak lanjut.", "danger")
            return redirect(url_for("portal.admin_follow_up_edit", follow_up_id=follow_up_id))

        flash("Tiket tindak lanjut berhasil diperbarui.", "success")
        if return_to.startswith("/") and not return_to.startswith("//"):
            return redirect(return_to)
        return redirect(url_for("portal.admin_follow_up_edit", follow_up_id=follow_up_id))

    annotated = _annotate_follow_up_ticket(ticket)
    timeline = _serialize_follow_up_timeline(list_room_follow_up_updates(follow_up_id, limit=200))
    staff_options = list_all_staff()
    return render_template(
        "portal/admin/follow_up_edit.html",
        ticket=annotated,
        timeline=timeline,
        staff_options=staff_options,
        follow_up_status_labels=FOLLOW_UP_STATUS_LABELS,
    )


@portal_bp.route("/admin/tindak-lanjut/<int:follow_up_id>/delete", methods=["POST"])
@role_required("admin")
def admin_follow_up_delete(follow_up_id: int) -> Response:
    return_to = (request.form.get("return_to") or "").strip()
    deleted = admin_delete_room_follow_up_ticket(follow_up_id=follow_up_id)
    if not deleted:
        flash("Tiket tindak lanjut tidak ditemukan.", "warning")
    else:
        label = (deleted.get("ticket_code") or f"#{follow_up_id}").strip()
        flash(f"Tiket {label} berhasil dihapus.", "success")

    if return_to.startswith("/") and not return_to.startswith("//"):
        return redirect(return_to)
    return redirect(url_for("portal.admin_follow_ups"))


@portal_bp.route("/tindak-lanjut/<int:follow_up_id>")
@_portal_access_required
def follow_up_detail(follow_up_id: int) -> Response:
    user = current_user()
    ticket = get_room_follow_up_ticket(follow_up_id)
    if not ticket:
        flash("Tiket tindak lanjut tidak ditemukan.", "warning")
        return redirect(url_for("portal.home"))
    if not _can_access_follow_up_ticket(user, ticket):
        flash("Anda tidak memiliki akses ke tiket ini.", "danger")
        return redirect(url_for("portal.home"))

    annotated = _annotate_follow_up_ticket(ticket)
    raw_timeline = list_room_follow_up_updates(follow_up_id, limit=200)
    timeline = _serialize_follow_up_timeline(raw_timeline)
    assessment = get_assessment_by_id(int(annotated.get("assessment_id") or 0)) or {}
    score_scale = _build_assessment_score_config(assessment)
    school_room_id = int(annotated.get("school_room_id") or 0)
    score_rows = get_assessment_scores(int(annotated.get("assessment_id") or 0))
    aspect_scores = [
        row for row in score_rows
        if int(row.get("school_room_id") or 0) == school_room_id
    ]
    room_note_map = get_assessment_room_details(int(annotated.get("assessment_id") or 0))
    staff_room_note = (room_note_map.get(school_room_id) or "").strip()
    role_value = (user.get("role") or "").strip().lower()
    can_school_update = (
        role_value == "sekolah"
        and int(annotated.get("school_id") or 0) == int((_fetch_user_school(user.get("id")) or {}).get("id") or 0)
        and (annotated.get("status") or "").strip().lower() != PORTAL_FOLLOW_UP_STATUS_DONE
    )
    can_staff_verify = (
        role_value == "staff"
        and int(user.get("id") or 0) == int(annotated.get("staff_id") or 0)
        and (annotated.get("status") or "").strip().lower() in {
            PORTAL_FOLLOW_UP_STATUS_IN_PROGRESS,
            PORTAL_FOLLOW_UP_STATUS_SUBMITTED,
        }
    )
    status_value = (annotated.get("status") or "").strip().lower()
    is_waiting_staff_verification = status_value == PORTAL_FOLLOW_UP_STATUS_SUBMITTED
    has_school_progress = any((item.get("event_type") or "").strip().lower() == "school_update" for item in raw_timeline)
    can_submit_verification = can_school_update and has_school_progress and not is_waiting_staff_verification
    return render_template(
        "portal/follow_up/detail.html",
        ticket=annotated,
        score_scale=score_scale,
        aspect_scores=aspect_scores,
        staff_room_note=staff_room_note,
        timeline=timeline,
        can_school_update=can_school_update,
        can_submit_verification=can_submit_verification,
        is_waiting_staff_verification=is_waiting_staff_verification,
        can_staff_verify=can_staff_verify,
        follow_up_status_labels=FOLLOW_UP_STATUS_LABELS,
    )


@portal_bp.route("/tindak-lanjut/<int:follow_up_id>/update", methods=["POST"])
@role_required("sekolah")
def follow_up_update(follow_up_id: int) -> Response:
    user = current_user()
    ticket = get_room_follow_up_ticket(follow_up_id)
    if not ticket:
        flash("Tiket tindak lanjut tidak ditemukan.", "warning")
        return redirect(url_for("portal.sekolah_follow_ups"))
    if not _can_access_follow_up_ticket(user, ticket):
        flash("Anda tidak memiliki akses ke tiket ini.", "danger")
        return redirect(url_for("portal.sekolah_follow_ups"))
    status_value = (ticket.get("status") or "").strip().lower()
    if status_value == PORTAL_FOLLOW_UP_STATUS_DONE:
        flash("Tiket sudah selesai.", "info")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))
    if status_value == PORTAL_FOLLOW_UP_STATUS_SUBMITTED:
        flash("Tiket sudah diajukan dan sedang menunggu verifikasi staff.", "info")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))

    note = (request.form.get("note") or "").strip()
    uploaded_photo = request.files.get("photo")
    try:
        photo_path = _save_follow_up_photo(
            uploaded_photo,
            follow_up_id=follow_up_id,
            school_label=ticket.get("school_name"),
        )
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))
    except Exception:
        current_app.logger.exception("Gagal menyimpan foto tindak lanjut.")
        flash("Gagal menyimpan foto tindak lanjut.", "danger")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))

    if not note and not photo_path:
        flash("Isi catatan atau ambil foto progress sebelum menyimpan update.", "warning")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))

    updated = add_school_room_follow_up_update(
        follow_up_id=follow_up_id,
        actor_user_id=int(user.get("id") or 0),
        actor_role="sekolah",
        note=note,
        photo_path=photo_path,
        submit_for_verification=False,
    )
    if not updated:
        flash("Gagal menyimpan update tindak lanjut.", "danger")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))

    flash("Update tindak lanjut berhasil disimpan.", "success")
    return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))


@portal_bp.route("/tindak-lanjut/<int:follow_up_id>/ajukan", methods=["POST"])
@role_required("sekolah")
def follow_up_submit_for_verification(follow_up_id: int) -> Response:
    user = current_user()
    ticket = get_room_follow_up_ticket(follow_up_id)
    if not ticket:
        flash("Tiket tindak lanjut tidak ditemukan.", "warning")
        return redirect(url_for("portal.sekolah_follow_ups"))
    if not _can_access_follow_up_ticket(user, ticket):
        flash("Anda tidak memiliki akses ke tiket ini.", "danger")
        return redirect(url_for("portal.sekolah_follow_ups"))
    status_value = (ticket.get("status") or "").strip().lower()
    if status_value == PORTAL_FOLLOW_UP_STATUS_DONE:
        flash("Tiket sudah selesai.", "info")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))
    if status_value == PORTAL_FOLLOW_UP_STATUS_SUBMITTED:
        flash("Tiket sudah diajukan. Jika belum diverifikasi, sistem akan kirim pengingat bulanan ke staff.", "info")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))

    timeline = list_room_follow_up_updates(follow_up_id, limit=200)
    has_school_progress = any((item.get("event_type") or "").strip().lower() == "school_update" for item in timeline)
    if not has_school_progress:
        flash("Simpan update progress terlebih dahulu sebelum mengajukan verifikasi.", "warning")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))

    updated = add_school_room_follow_up_update(
        follow_up_id=follow_up_id,
        actor_user_id=int(user.get("id") or 0),
        actor_role="sekolah",
        note=None,
        photo_path=None,
        submit_for_verification=True,
    )
    if not updated:
        flash("Gagal mengajukan verifikasi tindak lanjut.", "danger")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))

    staff_id = int(updated.get("staff_id") or 0)
    if staff_id > 0:
        create_user_notifications(
            recipient_ids=[staff_id],
            category=PANBERS_FOLLOW_UP_NOTIFICATION_CATEGORY,
            title="Verifikasi Tindak Lanjut PANBERSS",
            message=(
                f"{updated.get('school_name')}: {updated.get('room_name')} diajukan untuk verifikasi."
            ),
            link=url_for("portal.follow_up_detail", follow_up_id=follow_up_id),
            reference_table="portal_room_follow_up_tickets",
            reference_id=follow_up_id,
            metadata={
                "status": PORTAL_FOLLOW_UP_STATUS_SUBMITTED,
                "feature": "panbers_follow_up",
                "ticket_id": follow_up_id,
                "ticket_code": updated.get("ticket_code"),
                "school_id": int(updated.get("school_id") or 0),
                "assessment_id": int(updated.get("assessment_id") or 0),
                "room_name": updated.get("room_name"),
                "actor_name": user.get("full_name") or user.get("email"),
            },
        )

    flash("Tindak lanjut diajukan ke staff untuk verifikasi.", "success")
    return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))


@portal_bp.route("/tindak-lanjut/<int:follow_up_id>/verifikasi", methods=["POST"])
@role_required("staff")
def follow_up_verify(follow_up_id: int) -> Response:
    user = current_user()
    ticket = get_room_follow_up_ticket(follow_up_id)
    if not ticket:
        flash("Tiket tindak lanjut tidak ditemukan.", "warning")
        return redirect(url_for("portal.staff_follow_ups"))
    if not _can_access_follow_up_ticket(user, ticket):
        flash("Anda tidak memiliki akses ke tiket ini.", "danger")
        return redirect(url_for("portal.staff_follow_ups"))
    status_value = (ticket.get("status") or "").strip().lower()
    if status_value == PORTAL_FOLLOW_UP_STATUS_DONE:
        flash("Tiket sudah selesai.", "info")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))
    if status_value not in {PORTAL_FOLLOW_UP_STATUS_IN_PROGRESS, PORTAL_FOLLOW_UP_STATUS_SUBMITTED}:
        flash("Sekolah belum mengajukan progres untuk diverifikasi.", "warning")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))

    note = (request.form.get("note") or "").strip()
    updated = verify_room_follow_up_by_staff(
        follow_up_id=follow_up_id,
        actor_user_id=int(user.get("id") or 0),
        actor_role="staff",
        note=note,
    )
    if not updated:
        flash("Gagal memverifikasi tindak lanjut.", "danger")
        return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))

    recipient_ids = list_school_user_ids_for_follow_up_notifications(int(updated.get("school_id") or 0))
    if recipient_ids:
        create_user_notifications(
            recipient_ids=recipient_ids,
            category=PANBERS_FOLLOW_UP_NOTIFICATION_CATEGORY,
            title="Tindak Lanjut PANBERSS Selesai",
            message=f"{updated.get('room_name')} telah diverifikasi selesai oleh staff.",
            link=url_for("portal.follow_up_detail", follow_up_id=follow_up_id),
            reference_table="portal_room_follow_up_tickets",
            reference_id=follow_up_id,
            metadata={
                "status": PORTAL_FOLLOW_UP_STATUS_DONE,
                "feature": "panbers_follow_up",
                "ticket_id": follow_up_id,
                "ticket_code": updated.get("ticket_code"),
                "school_id": int(updated.get("school_id") or 0),
                "assessment_id": int(updated.get("assessment_id") or 0),
                "room_name": updated.get("room_name"),
                "actor_name": user.get("full_name") or user.get("email"),
            },
        )

    flash("Tindak lanjut berhasil diverifikasi selesai.", "success")
    return redirect(url_for("portal.follow_up_detail", follow_up_id=follow_up_id))


def _filter_assessment_rooms(rooms: list[dict], jenjang: str | None = None) -> list[dict]:
    """Filter rooms to hide base kelas when variant rooms exist."""
    filtered_rooms: list[dict] = []
    rooms_by_key: dict[tuple[str | None, int], list[dict]] = {}

    for room in rooms:
        name = (room.get("room_name") or "").strip()
        parsed = parse_room_info(name, jenjang)
        if parsed:
            try:
                key = (parsed.get("bucket"), int(parsed.get("grade_level")))
            except (TypeError, ValueError):
                filtered_rooms.append(room)
                continue
            rooms_by_key.setdefault(key, []).append({"room": room, "parsed": parsed})
            continue
        if parse_room_info(name):
            continue
        filtered_rooms.append(room)

    for grouped_rooms in rooms_by_key.values():
        has_variant = any(bool(item["parsed"].get("is_variant")) for item in grouped_rooms)
        for item in grouped_rooms:
            if has_variant and not item["parsed"].get("is_variant"):
                continue
            filtered_rooms.append(dict(item["room"]))

    return filtered_rooms


def _sort_assessment_rooms(rooms: list[dict], jenjang: str | None = None) -> list[dict]:
    """Show classroom-like rooms before umum rooms on assessment pages."""
    bucket_order = {
        "paud": 0,
        "paket": 1,
        "slb": 2,
        "tk": 3,
        "sd": 4,
        "smp": 5,
        "sma": 6,
    }

    def _variant_key(value: str | None) -> tuple[int, str]:
        variant = (value or "").strip().upper()
        if not variant:
            return (0, "")
        if variant.isdigit():
            return (1, f"{int(variant):04d}")
        return (2, variant)

    decorated: list[tuple[tuple[Any, ...], dict]] = []
    for index, room in enumerate(rooms):
        name = (room.get("room_name") or "").strip()
        parsed = parse_room_info(name, jenjang)
        if parsed:
            sort_key = (
                0,
                bucket_order.get(parsed.get("bucket"), 99),
                int(parsed.get("grade_level") or 0),
                _variant_key(parsed.get("variant")),
                name.lower(),
                index,
            )
        else:
            sort_key = (1, 999, 999, (9, ""), name.lower(), index)
        decorated.append((sort_key, room))

    decorated.sort(key=lambda item: item[0])
    return [room for _, room in decorated]


def _augment_rooms_with_assessment_data(
    all_rooms: list[dict],
    rooms: list[dict],
    assessment_id: int,
    existing_scores: list[dict] | None = None,
    photos_list: list[dict] | None = None,
    room_notes: dict[int, str] | None = None,
) -> tuple[list[dict], list[dict], list[dict], dict[int, str]]:
    """Ensure rooms with existing assessment data are included in the room list."""
    if existing_scores is None:
        existing_scores = get_assessment_scores(assessment_id)
    if photos_list is None:
        photos_list = get_assessment_photos(assessment_id)
    if room_notes is None:
        room_notes = get_assessment_room_details(assessment_id)

    data_room_ids = set()
    data_room_ids.update(
        s.get("school_room_id") for s in existing_scores if s.get("school_room_id")
    )
    data_room_ids.update(
        p.get("school_room_id") for p in photos_list if p.get("school_room_id")
    )
    data_room_ids.update(room_notes.keys())

    if not data_room_ids:
        return rooms, existing_scores, photos_list, room_notes

    room_by_id = {r.get("school_room_id"): r for r in rooms if r.get("school_room_id")}
    all_by_id = {r.get("school_room_id"): r for r in all_rooms if r.get("school_room_id")}
    for room_id in data_room_ids:
        if room_id and room_id not in room_by_id and room_id in all_by_id:
            rooms.append(all_by_id[room_id])
            room_by_id[room_id] = all_by_id[room_id]

    return rooms, existing_scores, photos_list, room_notes




@portal_bp.route("/assess/<int:school_id>")
@_portal_access_required
def assess(school_id: int) -> Response:
    """Start or continue assessment for a school."""
    user = current_user()
    role = user.get("role")
    period_id_arg = request.args.get("period_id", type=int)
    assessment_id_arg = request.args.get("assessment_id", type=int)
    
    if role not in ("admin", "staff", "coordinator"):
        flash("Hanya staff atau koordinator yang bisa melakukan penilaian.", "danger")
        return redirect(url_for("portal.home"))
    
    # Staff access control - verify assignment
    if role in ("staff", "coordinator"):
        assigned_school_ids = get_schools_assigned_to_staff_ids(user["id"])
        if school_id not in assigned_school_ids and role != "admin":
            flash("Anda tidak memiliki akses ke sekolah ini. Hubungi admin untuk penugasan.", "danger")
            return redirect(url_for("portal.staff_assignments"))
    
    school = get_school_by_id(school_id)
    if not school:
        flash("Sekolah tidak ditemukan.", "danger")
        return redirect(url_for("portal.schools"))
    
    # Get draft by explicit assessment_id (keeps existing draft/photos)
    assessment = None
    if assessment_id_arg:
        assessment = get_assessment_by_id(assessment_id_arg)
        if not assessment:
            flash("Penilaian tidak ditemukan.", "danger")
            return redirect(url_for("portal.staff_assignments"))
        if assessment.get("status") != "draft":
            return redirect(url_for("portal.view_assessment", assessment_id=assessment_id_arg))
        if assessment.get("school_id") != school_id:
            flash("Penilaian tidak sesuai sekolah.", "danger")
            return redirect(url_for("portal.staff_assignments"))
        if assessment.get("staff_id") != user["id"] and role != "admin":
            flash("Anda tidak memiliki akses ke penilaian ini.", "danger")
            return redirect(url_for("portal.staff_assignments"))

    # Get active draft for THIS user
    if assessment is None:
        assessment = get_active_assessment(school_id, staff_id=user["id"], period_id=period_id_arg)
    if not assessment:
        # Prevent new draft if sudah ada penilaian selesai untuk periode yang sama
        target_period_id = period_id_arg
        if target_period_id is None:
            active_period = get_active_period()
            target_period_id = active_period["id"] if active_period else None

        existing_final = get_latest_final_assessment_for_period(
            school_id, user["id"], target_period_id
        )
        if existing_final:
            flash("Sekolah ini sudah disubmit untuk periode tersebut. Silakan buka penilaian yang ada.", "info")
            return redirect(url_for("portal.view_assessment", assessment_id=existing_final["id"]))

        # Create new assessment
        try:
            assessment = create_assessment(
                school_id,
                staff_id=user["id"],
                period_id=period_id_arg,
                creator_email=user["email"],
            )
            if assessment.get("_is_new"):
                try:
                    delete_assessment_scores(assessment["id"])
                except Exception:
                    current_app.logger.exception("Failed to clear auto-filled scores")
        except Exception as e:
            current_app.logger.exception("Error creating assessment")
            flash("Gagal membuat penilaian baru.", "danger")
            return redirect(url_for("portal.schools"))
            
    assessment_id = assessment["id"]
    score_scale = _build_assessment_score_config(assessment)

    
    # Ensure classroom variants are materialized as rooms for this school
    try:
        ensure_classroom_rooms_for_school(school_id)
    except Exception:
        current_app.logger.exception("Failed to sync classroom rooms")

    # Get school rooms with aspects
    all_rooms = list_school_rooms(school_id)
    if not all_rooms:
        flash("Sekolah belum memiliki ruangan yang dikonfigurasi.", "warning")
        return redirect(url_for("portal.schools"))

    rooms = _filter_assessment_rooms(all_rooms, school.get("jenjang"))
    
    # Periode penilaian untuk badge UI
    assessment_period = get_period_by_id(assessment.get("period_id")) if assessment.get("period_id") else get_active_period()

    # Get existing scores
    existing_scores = get_assessment_scores(assessment_id)
    photos_list = get_assessment_photos(assessment_id)
    room_notes = get_assessment_room_details(assessment_id)
    rooms, existing_scores, photos_list, room_notes = _augment_rooms_with_assessment_data(
        all_rooms,
        rooms,
        assessment_id,
        existing_scores=existing_scores,
        photos_list=photos_list,
        room_notes=room_notes,
    )
    rooms = _sort_assessment_rooms(rooms, school.get("jenjang"))
    total_aspects = sum(len(r.get("aspects", [])) for r in rooms)
    scores_map = {
        (s["school_room_id"], s["aspect_id"]): s["score"]
        for s in existing_scores
    }
    
    photos_map = {}
    for photo in photos_list:
        room_id = photo["school_room_id"]
        if room_id in photos_map:
            continue  # keep the most recent photo only
        filename = Path(photo["photo_path"]).name if photo.get("photo_path") else None
        photo["url"] = url_for("portal.uploaded_file", filename=filename) if filename else None
        photos_map[room_id] = photo

    room_ids = {r.get("school_room_id") for r in rooms if r.get("school_room_id")}
    photo_room_ids = sorted({p.get("school_room_id") for p in photos_list if p.get("school_room_id") in room_ids})
    photo_uploaded_count = len(photo_room_ids)
    photo_min_required = math.ceil(len(rooms) * 0.2) if rooms else 0
    photo_max_allowed = math.ceil(len(rooms) * 0.5) if rooms else 0
    
    # Get optional rooms for this school
    optional_rooms_data = get_optional_rooms_for_schools([school_id])
    
    return render_template(
        "portal/assessments/assessment.html",
        school=school,
        assessment=assessment,
        score_scale=score_scale,
        rooms=rooms,
        scores_map=scores_map,
        photos_map=photos_map,
        photo_room_ids=photo_room_ids,
        photo_uploaded_count=photo_uploaded_count,
        photo_min_required=photo_min_required,
        photo_max_allowed=photo_max_allowed,
        room_notes=room_notes,
        total_aspects=total_aspects,
        assessment_period=assessment_period,
        optional_rooms_data=optional_rooms_data,
        photo_required_threshold=PHOTO_REQUIRED_PCT,
    )


@portal_bp.route("/assess/<int:school_id>/score", methods=["POST"])
@_portal_access_required
def save_score(school_id: int) -> Response:
    """API endpoint to save a single score."""
    user = current_user()
    if user.get("role") not in ("admin", "staff", "coordinator"):
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    try:
        assessment_id = int(data.get("assessment_id"))
        school_room_id = int(data.get("school_room_id"))
        aspect_id = int(data.get("aspect_id"))
        score = int(data.get("score"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid data format"}), 400

    try:
        assessment = get_assessment_by_id(assessment_id)
        if not assessment:
            return jsonify({"success": False, "message": "Assessment not found"}), 404

        if assessment["school_id"] != school_id:
            return jsonify({"success": False, "message": "Assessment tidak sesuai sekolah"}), 400

        if assessment.get("status") != "draft":
            return jsonify({"success": False, "message": "Penilaian sudah dikirim/terverifikasi."}), 400

        if assessment["staff_id"] != user["id"] and user["role"] != "admin":
            return jsonify({"success": False, "message": "Unauthorized access to this assessment"}), 403

        with get_cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM portal_assessments asses
                JOIN portal_school_rooms sr
                  ON sr.id = %s
                 AND sr.school_id = asses.school_id
                JOIN portal_aspects asp
                  ON asp.id = %s
                 AND asp.room_id = sr.room_id
                 AND asp.active = TRUE
                WHERE asses.id = %s
                  AND (
                    asp.is_required = TRUE
                    OR EXISTS (
                        SELECT 1
                        FROM portal_school_room_aspects psra
                        WHERE psra.school_room_id = sr.id
                          AND psra.aspect_id = asp.id
                    )
                  )
                """,
                (school_room_id, aspect_id, assessment_id),
            )
            if not cur.fetchone():
                return jsonify({"success": False, "message": "Aspek tidak sesuai dengan ruangan yang dinilai"}), 400

        score_config = _build_assessment_score_config(assessment)
        min_score = score_config["min"]
        max_score = score_config["max"]
        if not (min_score <= score <= max_score):
            if max_score == _NEW_SCORE_SCALE_MAX:
                return jsonify({"success": False, "message": "Nilai harus dalam rentang 1-5"}), 400
            return jsonify({"success": False, "message": "Nilai harus dalam rentang 0-3"}), 400



        success = save_assessment_score(
            assessment_id,
            school_room_id,
            aspect_id,
            score,
        )

        if success:
            return jsonify({"success": True})

        return jsonify({"success": False, "message": "Failed to save"}), 500
    except Exception as e:
        current_app.logger.exception("Error saving score")
        return jsonify({"success": False, "message": str(e)}), 500


@portal_bp.route("/assess/<int:school_id>/note", methods=["POST"])
@_portal_access_required
def save_note(school_id: int) -> Response:
    """API endpoint to save room note."""
    user = current_user()
    if user.get("role") not in ("admin", "staff", "coordinator"):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    data = request.get_json(silent=True) or {}
    try:
        assessment_id = int(data.get("assessment_id"))
        school_room_id = int(data.get("school_room_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Data tidak valid"}), 400

    notes = (data.get("notes") or "").strip()
    assessment = get_assessment_by_id(assessment_id)
    if not assessment:
        return jsonify({"success": False, "message": "Assessment tidak ditemukan"}), 404

    if assessment["school_id"] != school_id:
        return jsonify({"success": False, "message": "Assessment tidak sesuai sekolah"}), 400

    if assessment.get("status") != "draft":
        return jsonify({"success": False, "message": "Penilaian sudah dikirim/terverifikasi."}), 400

    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    try:

        result = save_room_details(
            assessment_id=assessment_id,
            school_room_id=school_room_id,
            notes=notes,
        )
        return jsonify({"success": True, "details": result})
    except Exception as e:
        current_app.logger.exception("Error saving note")
        return jsonify({"success": False, "message": str(e)}), 500


@portal_bp.route("/assess/<int:school_id>/photo", methods=["POST"])
@_portal_access_required
def upload_photo(school_id: int) -> Response:
    """Upload a photo with GPS data."""
    user = current_user()
    if user.get("role") not in ("admin", "staff", "coordinator"):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    assessment_id = request.form.get("assessment_id", type=int)
    school_room_id = request.form.get("school_room_id", type=int)
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")

    if not assessment_id or not school_room_id:
        return jsonify({"success": False, "message": "Assessment atau ruangan tidak valid"}), 400

    assessment = get_assessment_by_id(assessment_id)
    if not assessment:
        return jsonify({"success": False, "message": "Assessment tidak ditemukan"}), 404

    if assessment["school_id"] != school_id:
        return jsonify({"success": False, "message": "Assessment tidak sesuai sekolah"}), 400

    if assessment.get("status") != "draft":
        return jsonify({"success": False, "message": "Penilaian sudah dikirim/terverifikasi."}), 400

    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    try:

        all_rooms = list_school_rooms(school_id)
        school = get_school_by_id(school_id)
        rooms = _filter_assessment_rooms(all_rooms, school.get("jenjang") if school else None)
        photos_list = get_assessment_photos(assessment_id)
        rooms, _, photos_list, _ = _augment_rooms_with_assessment_data(
            all_rooms,
            rooms,
            assessment_id,
            photos_list=photos_list,
            room_notes={},
        )
        total_rooms = len(rooms)
        max_photos = math.ceil(total_rooms * 0.5) if total_rooms else 0
        if max_photos:
            room_ids = {r.get("school_room_id") for r in rooms if r.get("school_room_id")}
            photo_room_ids = {
                p.get("school_room_id")
                for p in photos_list
                if p.get("school_room_id") in room_ids
            }
            if len(photo_room_ids) >= max_photos and school_room_id not in photo_room_ids:
                return jsonify(
                    {
                        "success": False,
                        "message": "Jumlah upload foto sudah mencapai maksimal. Jika ingin menambahkan foto lagi, tolong hapus yang lain terlebih dahulu.",
                    }
                ), 400
    except Exception:
        current_app.logger.exception("Error validating max photo requirement")
        return jsonify({"success": False, "message": "Gagal memvalidasi batas foto."}), 500
    
    if "photo" not in request.files:
        return jsonify({"success": False, "message": "No photo provided"}), 400
    
    file = request.files["photo"]
    if not file or not file.filename:
        return jsonify({"success": False, "message": "No file selected"}), 400
    
    if not _allowed_file(file.filename):
        return jsonify({"success": False, "message": "Invalid file type"}), 400
    
    # Ensure upload directory exists
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = UPLOAD_FOLDER / filename
    try:
        lat_val = float(latitude) if latitude else None
    except (TypeError, ValueError):
        lat_val = None
    try:
        lon_val = float(longitude) if longitude else None
    except (TypeError, ValueError):
        lon_val = None

    if lat_val is None and lon_val is None:
        return jsonify(
            {
                "success": False,
                "message": "Lokasi belum terbaca. Aktifkan izin lokasi lalu coba lagi.",
            }
        ), 400
    
    try:
        file.save(str(filepath))
        
        saved = save_assessment_photo(
            assessment_id=assessment_id,
            school_room_id=school_room_id,
            photo_path=f"uploads/portal/{filename}",
            latitude=lat_val,
            longitude=lon_val,
        )
        saved_filename = Path(saved.get("photo_path") or filename).name
        saved["url"] = url_for("portal.uploaded_file", filename=saved_filename)
        
        return jsonify({"success": True, "photo": saved})
    except Exception as e:
        current_app.logger.exception("Error saving photo")
        return jsonify({"success": False, "message": str(e)}), 500


@portal_bp.route("/assess/<int:school_id>/submit", methods=["POST"])
@_portal_access_required
def submit(school_id: int) -> Response:
    """Submit the assessment."""
    user = current_user()
    if user.get("role") not in ("admin", "staff", "coordinator"):
        flash("Unauthorized", "danger")
        return redirect(url_for("portal.home"))
    
    assessment_id = request.form.get("assessment_id")
    if not assessment_id:
        flash("Assessment ID tidak valid.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))

    try:
        assessment_id_int = int(assessment_id)
    except (TypeError, ValueError):
        flash("Data assessment tidak valid.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))

    assessment = get_assessment_by_id(assessment_id_int)
    if not assessment:
        flash("Penilaian tidak ditemukan.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))

    # Hanya draft yang boleh disimpan ulang, cegah status submitted/verified berubah jadi draft
    if assessment.get("status") != "draft":
        flash("Penilaian sudah dikirim/terverifikasi, tidak bisa disimpan ulang.", "warning")
        return redirect(url_for("portal.view_assessment", assessment_id=assessment_id_int))

    if assessment["school_id"] != school_id:
        flash("Penilaian tidak sesuai sekolah.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))

    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        flash("Anda tidak memiliki akses untuk submit penilaian ini.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))
    if user["role"] == "staff":
        assigned_school_ids = get_schools_assigned_to_staff_ids(user["id"])
        if assessment["school_id"] not in assigned_school_ids:
            flash("Penugasan ke sekolah ini sudah tidak aktif. Hubungi admin.", "danger")
            return redirect(url_for("portal.staff_assignments"))

    try:
        all_rooms = list_school_rooms(school_id)
        school = get_school_by_id(school_id)
        rooms = _filter_assessment_rooms(all_rooms, school.get("jenjang") if school else None)
        existing_scores = get_assessment_scores(assessment_id_int)
        photos_list = get_assessment_photos(assessment_id_int)
        rooms, existing_scores, photos_list, _ = _augment_rooms_with_assessment_data(
            all_rooms,
            rooms,
            assessment_id_int,
            existing_scores=existing_scores,
            photos_list=photos_list,
            room_notes={},
        )

        total_rooms = len(rooms)
        min_photos = math.ceil(total_rooms * 0.2) if total_rooms else 0
        missing_messages = []
        if min_photos:
            room_ids = {r.get("school_room_id") for r in rooms if r.get("school_room_id")}
            photo_room_count = len(
                {
                    p.get("school_room_id")
                    for p in photos_list
                    if p.get("school_room_id") in room_ids
                }
            )
            if photo_room_count < min_photos:
                missing_messages.append(
                    f"Minimal upload foto ruangan {min_photos} dari {total_rooms} ruangan (20%). "
                    f"Saat ini {photo_room_count}."
                )

        scores_map = {
            (s["school_room_id"], s["aspect_id"]): s.get("score")
            for s in existing_scores
        }
        for room in rooms:
            room_id = room.get("school_room_id")
            aspects = room.get("aspects") or []
            if not room_id or not aspects:
                continue
            for aspect in aspects:
                score_val = scores_map.get((room_id, aspect.get("id")))
                if score_val is None:
                    missing_messages.append("Terdapat aspek yang masih belum dinilai.")
                    break
            if missing_messages:
                break

        if missing_messages:
            flash(" ".join(missing_messages), "warning")
            return redirect(url_for("portal.assess", school_id=school_id))
    except Exception:
        current_app.logger.exception("Error validating submission requirements")
        flash("Gagal memvalidasi persyaratan submit. Coba lagi.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))
    
    try:

        success = submit_assessment(assessment_id_int)
        if success:
            try:
                low_rooms = _get_low_score_rooms(
                    assessment_id_int,
                    school_id,
                    threshold_pct=FOLLOW_UP_THRESHOLD_PCT,
                    require_missing_photo=False,
                )
                created_follow_ups = _ensure_follow_up_tickets_after_submit(
                    assessment=assessment,
                    low_rooms=low_rooms,
                    actor=user,
                )
                if created_follow_ups > 0:
                    flash(
                        f"Dibuat {created_follow_ups} tiket tindak lanjut ruangan di bawah {FOLLOW_UP_THRESHOLD_PCT:.0f}.",
                        "warning",
                    )
            except Exception:
                current_app.logger.exception("Gagal membuat tiket tindak lanjut PANBERSS.")
            flash("Penilaian berhasil disubmit!", "success")
        else:
            flash("Gagal submit penilaian.", "danger")
    except Exception as e:
        current_app.logger.exception("Error submitting assessment")
        flash(f"Error: {e}", "danger")

    period_id = assessment.get("period_id") if assessment else None
    if user.get("role") == "staff":
        if period_id:
            return redirect(url_for("portal.staff_assignments", period_id=period_id))
        return redirect(url_for("portal.staff_assignments"))
    if user.get("role") == "coordinator":
        if period_id:
            return redirect(url_for("portal.coordinator_assessments", period_id=period_id))
        return redirect(url_for("portal.coordinator_assessments"))
    return redirect(url_for("portal.home"))


@portal_bp.route("/assess/<int:school_id>/save-draft", methods=["POST"])
@_portal_access_required
def save_draft(school_id: int) -> Response:
    """Explicitly save assessment as draft (no submit)."""
    user = current_user()
    if user.get("role") not in ("admin", "staff", "coordinator"):
        flash("Unauthorized", "danger")
        return redirect(url_for("portal.home"))

    assessment_id = request.form.get("assessment_id")
    if not assessment_id:
        flash("Assessment ID tidak valid.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))

    try:
        assessment_id_int = int(assessment_id)
    except (TypeError, ValueError):
        flash("Data assessment tidak valid.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))

    assessment = get_assessment_by_id(assessment_id_int)
    if not assessment:
        flash("Penilaian tidak ditemukan.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))

    if assessment["school_id"] != school_id:
        flash("Penilaian tidak sesuai sekolah.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))

    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        flash("Anda tidak memiliki akses untuk menyimpan draft ini.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))
    if user["role"] == "staff":
        assigned_school_ids = get_schools_assigned_to_staff_ids(user["id"])
        if assessment["school_id"] not in assigned_school_ids:
            flash("Penugasan ke sekolah ini sudah tidak aktif. Hubungi admin.", "danger")
            return redirect(url_for("portal.staff_assignments"))

    try:

        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE portal_assessments
                SET status = 'draft', updated_at = NOW()
                WHERE id = %s
                """,
                (assessment_id_int,),
            )
        flash("Draft berhasil disimpan.", "success")
    except Exception as e:
        current_app.logger.exception("Error saving draft")
        flash(f"Gagal menyimpan draft: {e}", "danger")

    return redirect(url_for("portal.assess", school_id=school_id))


@portal_bp.route("/assessment/<int:assessment_id>/request-reopen", methods=["POST"])
@_portal_access_required
def request_reopen(assessment_id: int) -> Response:
    """Staff requests admin approval to reopen a submitted assessment."""
    user = current_user()
    from .queries import log_activity
    if user.get("role") not in ("admin", "staff", "coordinator"):
        flash("Unauthorized", "danger")
        return redirect(url_for("portal.home"))

    assessment = get_assessment_by_id(assessment_id)
    if not assessment:
        flash("Penilaian tidak ditemukan.", "danger")
        return redirect(url_for("portal.home"))

    if assessment.get("status") != "submitted":
        flash("Hanya penilaian yang sudah disubmit yang bisa diajukan reopen.", "warning")
        return redirect(url_for("portal.view_assessment", assessment_id=assessment_id))

    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        flash("Anda tidak memiliki akses untuk mengajukan reopen penilaian ini.", "danger")
        return redirect(url_for("portal.home"))

    # Pastikan staf masih ditugaskan
    if user["role"] == "staff":
        assigned_school_ids = get_schools_assigned_to_staff_ids(user["id"])
        if assessment["school_id"] not in assigned_school_ids:
            flash("Penugasan sudah tidak aktif. Hubungi admin.", "danger")
            return redirect(url_for("portal.staff_assignments"))

    latest_req = get_latest_reopen_request(assessment_id)
    if latest_req and latest_req.get("status") == "pending":
        flash("Permintaan reopen sebelumnya masih menunggu persetujuan admin.", "warning")
        return redirect(url_for("portal.view_assessment", assessment_id=assessment_id))

    reason = request.form.get("reason", "").strip() or None
    try:
        request_row = create_reopen_request(assessment_id, user["id"], reason)
        details = {
            "assessment_id": assessment_id,
            "status": "pending",
        }
        if assessment.get("school_name"):
            details["school_name"] = assessment.get("school_name")
        if assessment.get("npsn"):
            details["npsn"] = assessment.get("npsn")
        if assessment.get("assessor_name"):
            details["staff_name"] = assessment.get("assessor_name")
        if assessment.get("assessor_email"):
            details["staff_email"] = assessment.get("assessor_email")
        if assessment.get("period_id") is not None:
            details["period_id"] = assessment.get("period_id")
        if assessment.get("period_name"):
            details["period_name"] = assessment.get("period_name")
        if reason:
            details["reason"] = reason
        log_activity(
            user.get("id"),
            "CREATE",
            "REOPEN_REQUEST",
            request_row.get("id") if request_row else None,
            assessment.get("school_name") or f"Assessment {assessment_id}",
            details,
        )
        request_row_id = request_row.get("id") if request_row else None
        if request_row_id is not None:
            try:
                notify_reopen_request(
                    request_id=int(request_row_id),
                    assessment_id=assessment_id,
                    school_name=assessment.get("school_name"),
                    period_name=assessment.get("period_name"),
                    staff_name=assessment.get("assessor_name"),
                    requested_by_name=user.get("full_name") or user.get("email"),
                    reason=reason,
                )
            except Exception:
                current_app.logger.exception("Gagal mengirim notifikasi Telegram permintaan reopen.")
        flash("Permintaan reopen dikirim. Menunggu persetujuan admin.", "success")
    except Exception as e:
        current_app.logger.exception("Error creating reopen request")
        flash(f"Gagal mengajukan reopen: {e}", "danger")

    return redirect(url_for("portal.view_assessment", assessment_id=assessment_id))


@portal_bp.route("/assessment/<int:assessment_id>/approve-reopen", methods=["POST"])
@role_required("admin")
def approve_reopen(assessment_id: int) -> Response:
    """Admin approves reopen request and reopens assessment."""
    from .queries import log_activity
    request_id = request.form.get("request_id", type=int)
    note = request.form.get("reviewer_note", "").strip() or None
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not request_id:
        if wants_json:
            return jsonify({"success": False, "message": "Permintaan tidak valid."}), 400
        flash("Permintaan tidak valid.", "danger")
        return redirect(url_for("portal.view_assessment", assessment_id=assessment_id))

    try:
        ok = update_reopen_request_status(
            request_id=request_id,
            status="approved",
            reviewer_id=current_user()["id"],
            reviewer_note=note,
        )
        success = False
        if ok and reopen_assessment(assessment_id):
            assessment = get_assessment_by_id(assessment_id)
            req = _fetch_reopen_request(request_id)
            details = {
                "assessment_id": assessment_id,
                "status": "approved",
            }
            if assessment:
                details["school_name"] = assessment.get("school_name")
                details["npsn"] = assessment.get("npsn")
                details["staff_name"] = assessment.get("assessor_name")
                details["staff_email"] = assessment.get("assessor_email")
                if assessment.get("period_id") is not None:
                    details["period_id"] = assessment.get("period_id")
                if assessment.get("period_name"):
                    details["period_name"] = assessment.get("period_name")
            if req and req.get("reason"):
                details["reason"] = req.get("reason")
            if note:
                details["reviewer_note"] = note
            log_activity(
                current_user().get("id"),
                "UPDATE",
                "REOPEN_REQUEST",
                request_id,
                assessment.get("school_name") if assessment else f"Assessment {assessment_id}",
                details,
            )
            try:
                actor = current_user() or {}
                notify_reopen_status_update(
                    request_id=request_id,
                    assessment_id=assessment_id,
                    school_name=assessment.get("school_name") if assessment else None,
                    period_name=assessment.get("period_name") if assessment else None,
                    staff_name=assessment.get("assessor_name") if assessment else None,
                    status_label="✅ Disetujui",
                    actor_name=actor.get("full_name") or actor.get("email"),
                    actor_username=None,
                    reviewer_note=note,
                )
            except Exception:
                current_app.logger.exception("Gagal mengirim notifikasi Telegram status reopen.")
            try:
                _notify_panbers_reopen_status_change(
                    request_id=request_id,
                    assessment_id=assessment_id,
                    status="approved",
                    actor=current_user(),
                    assessment=assessment,
                    reopen_request=req,
                    reviewer_note=note,
                )
            except Exception:
                current_app.logger.exception("Gagal menyimpan notifikasi aplikasi status reopen.")
            flash("Reopen disetujui dan penilaian dibuka kembali.", "success")
            success = True
        else:
            flash("Gagal menyetujui reopen.", "danger")
        if wants_json:
            status_code = 200 if success else 400
            return jsonify(
                {
                    "success": success,
                    "request_id": request_id,
                    "assessment_id": assessment_id,
                    "status": "approved" if success else "failed",
                }
            ), status_code
    except Exception as e:
        current_app.logger.exception("Error approving reopen")
        if wants_json:
            return jsonify({"success": False, "message": str(e)}), 500
        flash(f"Gagal menyetujui reopen: {e}", "danger")
    return redirect(url_for("portal.view_assessment", assessment_id=assessment_id))


@portal_bp.route("/assessment/<int:assessment_id>/reject-reopen", methods=["POST"])
@role_required("admin")
def reject_reopen(assessment_id: int) -> Response:
    """Admin rejects reopen request."""
    from .queries import log_activity
    request_id = request.form.get("request_id", type=int)
    note = request.form.get("reviewer_note", "").strip() or None
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not request_id:
        if wants_json:
            return jsonify({"success": False, "message": "Permintaan tidak valid."}), 400
        flash("Permintaan tidak valid.", "danger")
        return redirect(url_for("portal.view_assessment", assessment_id=assessment_id))

    try:
        ok = update_reopen_request_status(
            request_id=request_id,
            status="rejected",
            reviewer_id=current_user()["id"],
            reviewer_note=note,
        )
        if ok:
            assessment = get_assessment_by_id(assessment_id)
            req = _fetch_reopen_request(request_id)
            details = {
                "assessment_id": assessment_id,
                "status": "rejected",
            }
            if assessment:
                details["school_name"] = assessment.get("school_name")
                details["npsn"] = assessment.get("npsn")
                details["staff_name"] = assessment.get("assessor_name")
                details["staff_email"] = assessment.get("assessor_email")
                if assessment.get("period_id") is not None:
                    details["period_id"] = assessment.get("period_id")
                if assessment.get("period_name"):
                    details["period_name"] = assessment.get("period_name")
            if req and req.get("reason"):
                details["reason"] = req.get("reason")
            if note:
                details["reviewer_note"] = note
            log_activity(
                current_user().get("id"),
                "UPDATE",
                "REOPEN_REQUEST",
                request_id,
                assessment.get("school_name") if assessment else f"Assessment {assessment_id}",
                details,
            )
            try:
                actor = current_user() or {}
                notify_reopen_status_update(
                    request_id=request_id,
                    assessment_id=assessment_id,
                    school_name=assessment.get("school_name") if assessment else None,
                    period_name=assessment.get("period_name") if assessment else None,
                    staff_name=assessment.get("assessor_name") if assessment else None,
                    status_label="❌ Ditolak",
                    actor_name=actor.get("full_name") or actor.get("email"),
                    actor_username=None,
                    reviewer_note=note,
                )
            except Exception:
                current_app.logger.exception("Gagal mengirim notifikasi Telegram status reopen.")
            try:
                _notify_panbers_reopen_status_change(
                    request_id=request_id,
                    assessment_id=assessment_id,
                    status="rejected",
                    actor=current_user(),
                    assessment=assessment,
                    reopen_request=req,
                    reviewer_note=note,
                )
            except Exception:
                current_app.logger.exception("Gagal menyimpan notifikasi aplikasi status reopen.")
            flash("Permintaan reopen ditolak.", "info")
        else:
            flash("Gagal menolak reopen.", "danger")
        if wants_json:
            status_code = 200 if ok else 400
            return jsonify(
                {
                    "success": bool(ok),
                    "request_id": request_id,
                    "assessment_id": assessment_id,
                    "status": "rejected" if ok else "failed",
                }
            ), status_code
    except Exception as e:
        current_app.logger.exception("Error rejecting reopen")
        if wants_json:
            return jsonify({"success": False, "message": str(e)}), 500
        flash(f"Gagal menolak reopen: {e}", "danger")
    return redirect(url_for("portal.view_assessment", assessment_id=assessment_id))


@portal_bp.route("/assessment/<int:assessment_id>")
@_portal_access_required
def view_assessment(assessment_id: int) -> Response:
    """View a completed assessment."""
    user = current_user()
    assessment = get_assessment_by_id(assessment_id)
    if not assessment:
        flash("Penilaian tidak ditemukan.", "danger")
        return redirect(url_for("portal.home"))
    
    # Security check: Only owner or admin can view
    if assessment["staff_id"] != user["id"] and user["role"] != "admin" and user["role"] != "coordinator":
        flash("Anda tidak memiliki akses untuk melihat penilaian ini.", "danger")
        return redirect(url_for("portal.home"))

    score_scale = _build_assessment_score_config(assessment)
    
    scores = get_assessment_scores(assessment_id)
    photos = get_assessment_photos(assessment_id)
    room_notes = get_assessment_room_details(assessment_id)
    photos_by_room = {}
    for p in photos:
        photos_by_room.setdefault(p["school_room_id"], []).append(p)
    # Other assessments same school for admin context
    other_assessments = []
    school_avg = None
    if user.get("role") == "admin":
        # fetch all submitted assessments for this school (including current)
        from dashboard.db_access import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT 
                    a.id, 
                    a.total_score,
                    a.score_scale_max,
                    CASE
                        WHEN a.total_score IS NULL THEN NULL
                        ELSE (a.total_score::DECIMAL / NULLIF(COALESCE(a.score_scale_max, 3), 0) * 100)
                    END AS score_pct,
                    a.submitted_at, 
                    a.staff_id, 
                    u.full_name as assessor_name,
                    u.email as assessor_email,
                    (a.id = %s) AS is_current
                FROM portal_assessments a
                LEFT JOIN dashboard_users u ON u.id = a.staff_id
                WHERE a.school_id = %s AND a.status IN ('submitted', 'verified')
                ORDER BY a.submitted_at DESC, a.id DESC
                """,
                (assessment_id, assessment["school_id"]),
            )
            other_assessments = [dict(row) for row in cur.fetchall()]
        avg_map = fetch_school_avg_scores(period_id=None)
        school_avg = avg_map.get(assessment["school_id"])
    
    # Group scores by room
    rooms_data = {}
    for s in scores:
        room_id = s["room_id"]
        if room_id not in rooms_data:
            rooms_data[room_id] = {
                "room_id": room_id,
                "room_name": s["room_name"],
                "scores": [],
                "school_room_id": s["school_room_id"],
            }
        rooms_data[room_id]["scores"].append(s)

    related_photos = {}
    for room_id in rooms_data.keys():
        try:
            related_photos[room_id] = fetch_related_photos(
                school_id=assessment["school_id"],
                room_id=room_id,
                limit=10,
            )
        except Exception:
            related_photos[room_id] = []

    latest_reopen_request = get_latest_reopen_request(assessment_id)
    
    return render_template(
        "portal/assessments/view.html",
        assessment=assessment,
        score_scale=score_scale,
        user=user,
        photos_by_room=photos_by_room,
        room_notes=room_notes,
        other_assessments=other_assessments,
        school_avg=school_avg,
        rooms_data=rooms_data,
        related_photos=related_photos,
        latest_reopen_request=latest_reopen_request,
    )


@portal_bp.route("/assess/<int:school_id>/photo/<int:photo_id>/delete", methods=["POST"])
@_portal_access_required
def delete_photo_route(school_id: int, photo_id: int) -> Response:
    """Delete a photo belonging to an assessment."""
    user = current_user()
    if user.get("role") not in ("admin", "staff", "coordinator"):
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    assessment_id = request.form.get("assessment_id", type=int)
    school_room_id = request.form.get("school_room_id", type=int)
    if not assessment_id or not school_room_id:
        return jsonify({"success": False, "message": "Data tidak valid"}), 400

    assessment = get_assessment_by_id(assessment_id)
    if not assessment:
        return jsonify({"success": False, "message": "Assessment tidak ditemukan"}), 404
    if assessment["school_id"] != school_id:
        return jsonify({"success": False, "message": "Assessment tidak sesuai sekolah"}), 400

    if assessment.get("status") != "draft":
        return jsonify({"success": False, "message": "Penilaian sudah dikirim/terverifikasi."}), 400

    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    try:
        success = delete_photo(photo_id, assessment_id, school_room_id)
        if success:
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Gagal menghapus foto"}), 400
    except Exception as e:
        current_app.logger.exception("Error deleting photo")
        return jsonify({"success": False, "message": str(e)}), 500


@portal_bp.route("/room/<int:room_id>/aspects")
@_portal_access_required
def get_room_aspects_api(room_id: int) -> Response:
    """Get room aspects for AJAX call."""
    room = get_room_with_aspects(room_id)
    if not room:
        return jsonify({"success": False, "message": "Room not found"}), 404
    
    return jsonify({
        "success": True,
        "aspects": room.get('aspects', [])
    })


@portal_bp.route("/assess/<int:school_id>/add-room", methods=["POST"])
@_portal_access_required
def add_room_to_school(school_id: int) -> Response:
    """Add an optional room to school during assessment."""
    user = current_user()
    if user.get("role") not in ("admin", "staff", "coordinator"):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    data = request.get_json()
    room_id = data.get("room_id")
    aspect_ids = data.get("aspect_ids", [])
    
    if not room_id:
        return jsonify({"success": False, "message": "room_id required"}), 400
    
    try:
        with get_cursor(commit=True) as cur:
            # Check if already exists
            cur.execute("""
                SELECT id FROM portal_school_rooms
                WHERE school_id = %s AND room_id = %s
            """, (school_id, room_id))
            
            existing = cur.fetchone()
            if existing:
                return jsonify({"success": False, "message": "Ruangan sudah ada di sekolah"}), 400
            
            # Insert school room
            cur.execute("""
                INSERT INTO portal_school_rooms (school_id, room_id)
                VALUES (%s, %s)
                RETURNING id
            """, (school_id, room_id))
            
            school_room_id = cur.fetchone()['id']
            
            # Insert selected aspects
            if aspect_ids:
                for aspect_id in aspect_ids:
                    cur.execute("""
                        INSERT INTO portal_school_room_aspects (school_room_id, aspect_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, (school_room_id, aspect_id))
        
        current_app.logger.info(
            f"[add_room_to_school] Added room {room_id} to school {school_id} with aspects {aspect_ids}"
        )
        
        return jsonify({"success": True, "message": "Ruangan berhasil ditambahkan"})
    
    except Exception as e:
        current_app.logger.exception("Error adding room to school")
        return jsonify({"success": False, "message": str(e)}), 500


@portal_bp.route("/assessment/<int:assessment_id>/delete", methods=["POST"])
@role_required("admin")
def delete_assessment_route(assessment_id: int) -> Response:
    """Admin deletes an assessment record."""
    if delete_assessment(assessment_id):
        flash("Penilaian dihapus.", "success")
    else:
        flash("Gagal menghapus penilaian.", "danger")
    return redirect(url_for("portal.admin_stats"))


@portal_bp.route("/assessment/<int:assessment_id>/delete-draft", methods=["POST"])
@_portal_access_required
def delete_draft_route(assessment_id: int) -> Response:
    """Staff deletes their own draft assessment."""
    user = current_user()
    if user.get("role") not in ("admin", "staff", "coordinator"):
        flash("Unauthorized", "danger")
        return redirect(url_for("portal.home"))

    assessment = get_assessment_by_id(assessment_id)
    if not assessment:
        flash("Penilaian tidak ditemukan.", "warning")
        return redirect(url_for("portal.home"))

    # Only drafts can be deleted by staff
    if assessment.get("status") != "draft":
        flash("Hanya draft yang dapat dihapus.", "warning")
        return redirect(url_for("portal.home"))

    # Only the owner (or admin) can delete
    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        flash("Anda tidak memiliki akses untuk menghapus draft ini.", "danger")
        return redirect(url_for("portal.home"))

    if delete_assessment(assessment_id):
        flash("Draft penilaian berhasil dihapus.", "success")
    else:
        flash("Gagal menghapus draft.", "danger")

    if user.get("role") == "coordinator":
        return redirect(url_for("portal.coordinator_assessments"))
    return redirect(url_for("portal.home"))


# ===== Staff Assignment Routes =====


@portal_bp.route("/staff/assignments")
@_portal_access_required
def staff_assignments() -> Response:
    """Staff view their assigned schools."""
    user = current_user()
    photo_redirect = _require_profile_photo_redirect(user)
    if photo_redirect:
        return photo_redirect
    
    if user.get("role") != "staff":
        flash("Halaman ini hanya untuk staf.", "warning")
        return redirect(url_for("portal.home"))
    
    periods = list_periods()
    active_period_id = next((p["id"] for p in periods if p.get("is_active")), None) or (periods[0]["id"] if periods else None)
    selected_period_id = request.args.get("period_id", type=int)
    if selected_period_id is None:
        selected_period_id = active_period_id

    assigned_schools = get_staff_assigned_schools(user["id"], period_id=selected_period_id)

    return render_template(
        "portal/staff/assignments.html",
        assigned_schools=assigned_schools,
        periods=periods,
        active_period_id=active_period_id,
        selected_period_id=selected_period_id,
        user=user,
    )


# ===== Sekolah Portal Routes =====


@portal_bp.route("/sekolah/rooms", methods=["GET", "POST"])
@_portal_access_required
def sekolah_rooms() -> Response:
    """School configures which rooms they have."""
    user = current_user()
    
    # Get user's school_id from database
    user_school = None
    if user.get("role") == "sekolah":
        user_school = _fetch_user_school(user["id"])
        
        if not user_school:
            flash("Akun Anda belum terhubung dengan sekolah. Hubungi admin.", "warning")
            return redirect(url_for("portal.home"))
    
    current_school_id = None

    if request.method == "POST":
        school_id = request.form.get("school_id")
        room_ids = request.form.getlist("room_ids", type=int)
        
        # For sekolah role, only allow updating their own school
        if user.get("role") == "sekolah" and user_school:
            school_id = str(user_school["id"])
        
        aspect_map: dict[int, list[int]] = {}
        for rid in room_ids:
            aspect_ids = request.form.getlist(f"aspects_{rid}[]", type=int)
            if not aspect_ids:
                # Fallback for older form names without [] suffix
                aspect_ids = request.form.getlist(f"aspects_{rid}", type=int)
            if aspect_ids:
                aspect_map[rid] = aspect_ids

        if school_id:
            current_school_id = int(school_id)
            # Debug log to trace submitted data vs persisted
            current_app.logger.info(
                "[sekolah_rooms] submit user=%s role=%s school_id=%s room_ids=%s aspect_map=%s form_keys=%s",
                user.get("id"),
                user.get("role"),
                current_school_id,
                room_ids,
                {rid: sorted(vals) for rid, vals in aspect_map.items()},
                [k for k in request.form.keys() if k.startswith("aspects_")],
            )
            try:
                # Pastikan paralel kelas sudah tersinkron sebelum simpan konfigurasi ruangan
                try:
                    ensure_classroom_rooms_for_school(current_school_id)
                except Exception:
                    current_app.logger.exception("Failed to sync classroom rooms before update_school_rooms")
                count = update_school_rooms(current_school_id, room_ids, aspect_map)
                try:
                    ensure_classroom_rooms_for_school(current_school_id)
                except Exception:
                    current_app.logger.exception("Failed to sync classroom rooms after update_school_rooms")
                # Log what is stored after save
                saved_after = list_school_rooms(current_school_id, include_all_aspects=True)
                saved_map = {
                    r["room_id"]: [
                        (a["id"], bool(a.get("is_required")), bool(a.get("is_selected")))
                        for a in r.get("aspects", [])
                    ]
                    for r in saved_after
                }
                current_app.logger.info(
                    "[sekolah_rooms] persisted rooms=%s aspects=%s",
                    [r["room_id"] for r in saved_after],
                    saved_map,
                )
                flash(f"Berhasil menyimpan {count} ruangan beserta konfigurasi aspek.", "success")
            except Exception as e:
                flash(f"Error: {e}", "danger")

    # Determine selected school early (needed for filtering variant rooms)
    schools = [user_school] if user_school else list_portal_schools()
    saved_room_ids: set[int] = set()
    if current_school_id is None:
        if user_school:
            current_school_id = user_school["id"]
        elif request.args.get("school_id"):
            current_school_id = int(request.args.get("school_id"))

    saved_rooms = []
    if current_school_id:
        try:
            ensure_classroom_rooms_for_school(current_school_id)
        except Exception:
            current_app.logger.exception("Failed to sync classroom rooms before rendering sekolah_rooms")
        saved_rooms = list_school_rooms(current_school_id, include_all_aspects=True)
        saved_room_ids = {r["room_id"] for r in saved_rooms}

    # Get classroom configurations for current school (used to hint variants per jenjang)
    classrooms = []
    if current_school_id:
        classrooms = list_school_classrooms(current_school_id)

    selected_school = user_school
    if not selected_school and current_school_id:
        selected_school = next((s for s in schools if s.get("id") == current_school_id), None)
    selected_jenjang = selected_school.get("jenjang") if selected_school else None
    selected_jenjang_upper = normalize_jenjang(selected_jenjang)
    template_room_name = (get_template_room_name(selected_jenjang) or "").strip().lower()
    classroom_levels = get_classroom_levels(selected_jenjang)
    classroom_level_labels = grade_label_map(selected_jenjang)
    profile_classroom_levels = get_classroom_levels(selected_jenjang, for_profile=True)
    profile_classroom_level_labels = grade_label_map(selected_jenjang, for_profile=True)
    
    # Build set of (grade, variant) pairs for exact matching
    # e.g., {(1, 'A'), (2, 'A'), (3, 'A')} means only show Kelas 1A, 2A, 3A
    classroom_variants: set[tuple[int, str]] = set()
    classroom_grades: set[int] = set()
    
    for cls in classrooms:
        try:
            g = int(cls.get("grade_level"))
            variant = (cls.get("variant") or "").strip().upper()
            if g in (-1, 0) and variant and not variant.isdigit():
                if len(variant) == 1 and variant.isalpha():
                    variant = str(ord(variant) - ord("A") + 1)
            if variant:  # Only add if there's a variant
                classroom_variants.add((g, variant))
            classroom_grades.add(g)
        except (TypeError, ValueError):
            continue

    all_rooms = list_portal_rooms()
    # Tag aspek yang sudah dipilih agar checkbox tercentang saat render
    if saved_rooms:
        saved_aspects_by_room = {
            r["room_id"]: {a["id"]: bool(a.get("is_required") or a.get("is_selected")) for a in (r.get("aspects") or [])}
            for r in saved_rooms
        }
        for r in all_rooms:
            aspects = r.get("aspects") or []
            selected_flags = saved_aspects_by_room.get(r["id"], {})
            r["aspects"] = [
                {
                    **a,
                    "is_selected": bool(a.get("is_required")) or bool(selected_flags.get(a.get("id"), False)),
                }
                for a in aspects
            ]

    def _room_grade(room: dict) -> int | None:
        name_val = room.get("name") or room.get("room_name") or ""
        parsed = parse_room_info(name_val, selected_jenjang)
        if not parsed:
            return None
        try:
            return int(parsed.get("grade_level"))
        except (TypeError, ValueError):
            return None

    def _is_variant_class(name: str) -> bool:
        return bool((parse_room_info(name or "", selected_jenjang) or {}).get("is_variant"))

    
    def _room_variant(room: dict) -> str | None:
        """Extract variant letter from room name (e.g., 'A' from 'Ruang Kelas 1A')."""
        name_val = room.get("name") or room.get("room_name") or ""
        parsed = parse_room_info(name_val, selected_jenjang)
        variant = (parsed or {}).get("variant")
        return str(variant).strip().upper() if variant else None

    def _room_bucket(room: dict) -> str | None:
        name_val = room.get("name") or room.get("room_name") or ""
        parsed = parse_room_info(name_val, selected_jenjang)
        return (parsed or {}).get("bucket")

    def _room_is_other_jenjang_classroom(room: dict) -> bool:
        if not selected_jenjang_upper:
            return False
        name_val = room.get("name") or room.get("room_name") or ""
        parsed_any = parse_room_info(name_val)
        if not parsed_any:
            return False
        parsed_selected = parse_room_info(name_val, selected_jenjang)
        return parsed_selected is None

    for r in all_rooms:
        aspects = r.get("aspects") or []
        has_optional_selected = any(
            (not a.get("is_required")) and a.get("is_selected") for a in aspects
        )
        r["default_select_all_aspects"] = bool(_room_grade(r) is not None and not has_optional_selected)

    # Identifikasi jenjang yang sudah punya kelas paralel untuk sekolah aktif saja.
    variant_grades: set[int] = set()
    for sr in saved_rooms:
        name_val = sr.get("room_name") or sr.get("name") or ""
        if _is_variant_class(name_val):
            g = _room_grade(sr)
            if g is not None:
                variant_grades.add(g)
    variant_grades.update(classroom_grades)

    # Debug logging to diagnose filtering issues
    current_app.logger.info(
        "[sekolah_rooms] Starting room filtering for school_id=%s, classroom_grades=%s, classroom_variants=%s, variant_grades=%s, saved_room_ids count=%d",
        current_school_id, classroom_grades, classroom_variants, variant_grades, len(saved_room_ids)
    )
    current_app.logger.info(
        "[sekolah_rooms] Total rooms before filtering: %d (SD candidates: %d)",
        len(all_rooms),
        len([r for r in all_rooms if _room_grade(r) in range(1, 7)])
    )

    filtered_rooms = []
    skipped_variant_rooms = []
    skipped_base_rooms = []
    hide_all_numeric_grade_rooms = selected_jenjang_upper in {"SD", "SMP", "SMA", "SMK"} and not classroom_grades
    
    for r in all_rooms:
        name_val = r.get("name") or ""
        g = _room_grade(r)
        is_saved = r.get("id") in saved_room_ids
        r["auto_select"] = False

        if hide_all_numeric_grade_rooms and g is not None:
            current_app.logger.info(
                "[sekolah_rooms] Skipping classroom room '%s' (grade=%s) because numeric classroom config is empty",
                name_val, g
            )
            skipped_base_rooms.append(name_val)
            continue

        if classrooms and g is not None and g not in classroom_grades and not is_saved:
            current_app.logger.info(
                "[sekolah_rooms] Skipping classroom room '%s' (grade=%s) because grade is not configured",
                name_val, g
            )
            skipped_base_rooms.append(name_val)
            continue

        # Only show variant classrooms if exact (grade, variant) match OR already saved
        if _is_variant_class(name_val):
            variant = _room_variant(r)
            
            # Check if this exact (grade, variant) pair is configured
            is_exact_match = (g, variant) in classroom_variants if (g is not None and variant) else False
            r["auto_select"] = bool(is_exact_match)
            should_skip = not is_exact_match and not is_saved
            
            # Log each variant room decision
            current_app.logger.info(
                "[sekolah_rooms] Variant room '%s': room_id=%s, grade=%s, variant='%s', exact_match=%s, is_saved=%s, SKIP=%s",
                name_val, r.get("id"), g, variant, is_exact_match, is_saved, should_skip
            )
            
            if should_skip:
                skipped_variant_rooms.append(name_val)
                continue
        elif g is not None and g in classroom_grades and not variant_grades:
            r["auto_select"] = True
        # Jika ada paralel untuk jenjang yang sama, sembunyikan base class (mis. "Ruang Kelas 1")
        if not _is_variant_class(name_val) and g is not None and g in variant_grades:
            current_app.logger.info(
                "[sekolah_rooms] Skipping base room '%s' (grade=%s) because variants exist",
                name_val, g
            )
            skipped_base_rooms.append(name_val)
            continue
        filtered_rooms.append(r)
    
    # Summary logging
    current_app.logger.info(
        "[sekolah_rooms] Filtering complete: kept %d rooms, skipped %d variant rooms, skipped %d base rooms",
        len(filtered_rooms), len(skipped_variant_rooms), len(skipped_base_rooms)
    )
    if skipped_variant_rooms:
        current_app.logger.info("[sekolah_rooms] Skipped variant rooms: %s", skipped_variant_rooms)
    if skipped_base_rooms:
        current_app.logger.info("[sekolah_rooms] Skipped base rooms: %s", skipped_base_rooms)
    sd_rooms = []
    smp_rooms = []
    sma_rooms = []
    paud_rooms = []
    tk_rooms = []
    paket_rooms = []
    slb_rooms = []
    umum_rooms = []
    for r in filtered_rooms:
        room_name = (r.get("name") or "").strip().lower()
        if _room_is_other_jenjang_classroom(r):
            continue
        if template_room_name and room_name == template_room_name and selected_jenjang_upper in {"SPS", "TPA", "KB", "SKB", "PKBM", "SLB"}:
            continue
        bucket = _room_bucket(r)
        grade = _room_grade(r)
        if bucket == "paud":
            paud_rooms.append(r)
        elif bucket == "tk":
            tk_rooms.append(r)
        elif bucket == "paket":
            paket_rooms.append(r)
        elif bucket == "slb":
            slb_rooms.append(r)
        elif 1 <= (grade or 0) <= 6:
            sd_rooms.append(r)
        elif 7 <= (grade or 0) <= 9:
            smp_rooms.append(r)
        elif 10 <= (grade or 0) <= 12:
            sma_rooms.append(r)
        else:
            umum_rooms.append(r)
    
    missing_fields = _compute_missing_profile_fields(user_school) if user_school else []
    show_profile_modal = bool(missing_fields)
    kecamatan_list = list_kecamatan()
    kelurahan_list = list_kelurahan()  # full list to allow sekolah update
    
    return render_template(
        "portal/sekolah/rooms.html",
        all_rooms=all_rooms,
        schools=schools,
        user_school=user_school,
        saved_room_ids=saved_room_ids,
        school_profile=user_school,
        missing_fields=missing_fields,
        show_profile_modal=show_profile_modal,
        coordinator_contacts=_build_coordinator_contacts(user_school),
        area_contacts=_build_coordinator_contacts(user_school),
        kecamatan_list=kecamatan_list,
        kelurahan_list=kelurahan_list,
        classrooms=classrooms,
        classroom_levels=classroom_levels,
        classroom_level_labels=classroom_level_labels,
        profile_classroom_levels=profile_classroom_levels,
        profile_classroom_level_labels=profile_classroom_level_labels,
        selected_jenjang_upper=selected_jenjang_upper,
        selected_school=selected_school,
        paud_rooms=paud_rooms,
        tk_rooms=tk_rooms,
        paket_rooms=paket_rooms,
        slb_rooms=slb_rooms,
        sd_rooms=sd_rooms,
        smp_rooms=smp_rooms,
        sma_rooms=sma_rooms,
        umum_rooms=umum_rooms,
    )


# ===== Coordinator helpers =====


def _get_coordinator_team_context(user_id: int):
    """Return (team, team_members, staff_ids) for a coordinator."""
    from dashboard.queries import get_monev_teams, get_team_members
    
    all_teams = get_monev_teams()
    team = next((t for t in all_teams if t.get("coordinator_id") == user_id), None)
    if not team:
        return None, [], []
    
    team_members = get_team_members(team["id"])
    staff_ids = [m["staff_id"] for m in team_members]
    if user_id not in staff_ids:
        staff_ids.append(user_id)
    
    return team, team_members, staff_ids


def _get_team_staff_ids(team_id: int):
    """Return (staff_ids, team) for a given team id (includes coordinator)."""
    from dashboard.queries import get_monev_teams, get_team_members
    
    teams = get_monev_teams()
    team = next((t for t in teams if t.get("id") == team_id), None)
    if not team:
        return [], None
    
    members = get_team_members(team_id)
    staff_ids = [m["staff_id"] for m in members]
    coordinator_id = team.get("coordinator_id")
    if coordinator_id and coordinator_id not in staff_ids:
        staff_ids.append(coordinator_id)
    
    return staff_ids, team


def _build_admin_stats_period_filter(
    periods: list[dict[str, object]],
    year: int | None,
    month: int | None,
    period_id: int | None = None,
) -> tuple[int | None, list[int] | None, list[int], int | None, int | None]:
    """Resolve admin stats period filters from year/month selections."""
    period_rows: list[tuple[int, int, int]] = []
    year_set: set[int] = set()
    for p in periods:
        pid = p.get("id")
        start_date = p.get("start_date")
        if not isinstance(pid, int) or start_date is None:
            continue
        y = getattr(start_date, "year", None)
        m = getattr(start_date, "month", None)
        if not isinstance(y, int) or not isinstance(m, int):
            continue
        year_set.add(y)
        period_rows.append((pid, y, m))

    selected_year = year if isinstance(year, int) and year in year_set else None
    selected_month = month if isinstance(month, int) and 1 <= month <= 12 else None
    if selected_year is None and selected_month is None and isinstance(period_id, int):
        chosen = next(((pid, y, m) for (pid, y, m) in period_rows if pid == period_id), None)
        if chosen:
            selected_year = chosen[1]
            selected_month = chosen[2]
    if selected_year is None:
        selected_month = None

    year_options = sorted(year_set, reverse=True)
    if selected_year is None:
        return None, None, year_options, None, None

    year_period_ids = [pid for (pid, y, _m) in period_rows if y == selected_year]
    if selected_month is None:
        return None, year_period_ids, year_options, selected_year, None

    matching = [pid for (pid, y, m) in period_rows if y == selected_year and m == selected_month]
    if not matching:
        return None, [], year_options, selected_year, selected_month
    selected_period_id = matching[0]
    return selected_period_id, [selected_period_id], year_options, selected_year, selected_month


def _serialize_related_photos(school_id: int | None, room_id: int | None, staff_ids: list[int] | None = None):
    """Serialize related photos response with optional staff filtering."""
    if not school_id or not room_id:
        return []
    
    from .queries import fetch_related_photos
    
    photos = fetch_related_photos(
        school_id=school_id,
        room_id=room_id,
        limit=10,
        staff_ids=staff_ids,
    )
    
    result = []
    for p in photos:
        filename = (p.get("photo_path") or "").split("/")[-1]
        if p.get("photo_path", "").startswith("http"):
            photo_url = p["photo_path"]
        else:
            photo_url = url_for("portal.uploaded_file", filename=filename) if filename else None
        
        raw_score_pct = p.get("room_score_pct")
        if raw_score_pct is None:
            score_base = float(p.get("room_score") or 0)
            score_scale_max = _normalize_assessment_scale_max(p.get("score_scale_max"))
            score_pct = _score_pct_from_raw(score_base, score_scale_max)
        else:
            score_pct = float(raw_score_pct)
        
        result.append({
            "photo_url": photo_url,
            "school_name": p.get("school_name"),
            "room_name": p.get("room_name"),
            "score": round(score_pct, 1),
            "score_pct": round(score_pct, 1),
            "captured_at": p["captured_at"].isoformat() if p.get("captured_at") else None,
            "latitude": float(p["latitude"]) if p.get("latitude") else None,
            "longitude": float(p["longitude"]) if p.get("longitude") else None,
        })
    return result


# ===== Admin Routes =====


@portal_bp.route("/coordinator/stats")
@role_required("coordinator")
def coordinator_stats() -> Response:
    """Coordinator view of team statistics - same as admin but filtered to team members only."""
    from .queries import (
        list_team_assessments,
        fetch_team_top_schools,
        fetch_team_bottom_schools,
        list_periods,
        fetch_portal_stats,
        fetch_score_distribution,
        fetch_random_photos,
        fetch_school_avg_scores,
        fetch_kecamatan_avg_scores,
    )
    
    user = current_user()
    photo_redirect = _require_profile_photo_redirect(user)
    if photo_redirect:
        return photo_redirect
    user_id = user.get("id")
    period_id = request.args.get("period_id", type=int)
    jenjang_filter = request.args.get("jenjang") or None
    order = request.args.get("order") or "recent"
    photo_order = request.args.get("photo_order", "random")
    
    my_team, team_members, staff_ids = _get_coordinator_team_context(user_id)
    
    if not my_team:
        flash("Anda belum ditugaskan sebagai koordinator tim manapun.", "warning")
        periods = list_periods()
        empty_stats = {
            "schools": {"total_schools": 0, "active_schools": 0},
            "assessments": {
                "total": 0,
                "drafts": 0,
                "submitted": 0,
                "avg_score": None,
            },
        }
        return render_template(
            "portal/coordinator/stats.html",
            team=None,
            team_members=[],
            stats=empty_stats,
            score_dist=[0] * 9,
            kecamatan_stats=[],
            recent_assessments=[],
            top_schools=[],
            bottom_schools=[],
            random_photos=[],
            school_avg_map={},
            periods=periods,
            current_period_id=period_id,
            jenjang_filter=jenjang_filter,
            order=order,
            photo_order=photo_order,
            selected_team_id=None,
        )
        
    stats = fetch_portal_stats(period_id=period_id, staff_ids=staff_ids)
    score_dist = fetch_score_distribution(period_id=period_id, staff_ids=staff_ids)
    
    # Get team-filtered assessments
    recent_assessments = list_team_assessments(staff_ids, limit=50, period_id=period_id)
    top_schools = fetch_team_top_schools(staff_ids, period_id=period_id, limit=10)
    bottom_schools = fetch_team_bottom_schools(staff_ids, period_id=period_id, limit=10)
    
    # Other data for display
    random_photos = fetch_random_photos(
        period_id=period_id,
        order=photo_order,
        limit=24,
        staff_ids=staff_ids,
        restrict_to_staff=True,
    )
    school_avg_map = fetch_school_avg_scores(period_id=period_id, staff_ids=staff_ids)
    periods = list_periods()
    kecamatan_stats = fetch_kecamatan_avg_scores(period_id=period_id, staff_ids=staff_ids)
    
    return render_template(
        "portal/coordinator/stats.html",
        team=my_team,
        team_members=team_members,
        stats=stats,
        score_dist=score_dist,
        kecamatan_stats=kecamatan_stats,
        recent_assessments=recent_assessments,
        top_schools=top_schools,
        bottom_schools=bottom_schools,
        random_photos=random_photos,
        school_avg_map=school_avg_map,
        periods=periods,
        current_period_id=period_id,
        jenjang_filter=jenjang_filter,
        order=order,
        photo_order=photo_order,
        selected_team_id=my_team.get("id"),
    )


@portal_bp.route("/admin/stats")
@role_required("admin")
def admin_stats() -> Response:
    """Admin view of portal statistics."""
    # Trigger reload
    from dashboard.queries import get_monev_teams
    from .queries import (
        fetch_team_top_schools,
        fetch_team_bottom_schools,
        fetch_negeri_assessment_frequency,
    )

    periods = list_periods()
    selected_year_arg = request.args.get("year", type=int)
    selected_month_arg = request.args.get("month", type=int)
    selected_period_arg = request.args.get("period_id", type=int)
    period_id, period_ids, period_year_options, selected_year, selected_month = _build_admin_stats_period_filter(
        periods,
        selected_year_arg,
        selected_month_arg,
        selected_period_arg,
    )
    team_id = request.args.get("team_id", type=int)
    jenjang_filter = request.args.get("jenjang") or None
    order = request.args.get("order") or "recent"
    allowed_orders = {
        "recent",
        "score_desc",
        "score_asc",
        "staff_desc",
        "staff_asc",
        "name_asc",
        "name_desc",
        "date_asc",
        "date_desc",
    }
    if order not in allowed_orders:
        order = "recent"
    
    staff_ids: list[int] | None = None
    selected_team = None
    if team_id:
        staff_ids, selected_team = _get_team_staff_ids(team_id)
        if selected_team is None:
            staff_ids = None
    
    stats = fetch_portal_stats(period_id=period_id, period_ids=period_ids, staff_ids=staff_ids)
    from .queries import fetch_score_distribution
    score_dist = fetch_score_distribution(period_id=period_id, period_ids=period_ids, staff_ids=staff_ids)
    recent_assessments = list_recent_assessments(
        period_id=period_id,
        period_ids=period_ids,
        jenjang=jenjang_filter,
        order=order,
        staff_ids=staff_ids,
    )
    staff_latest_assessments = list_staff_latest_assessments(
        period_id=period_id,
        period_ids=period_ids,
        staff_ids=staff_ids,
        limit=100,
    )
    if staff_ids:
        top_schools = fetch_team_top_schools(staff_ids, period_id=period_id, period_ids=period_ids, limit=10)
        bottom_schools = fetch_team_bottom_schools(staff_ids, period_id=period_id, period_ids=period_ids, limit=10)
    else:
        top_schools = fetch_top_schools(period_id=period_id, period_ids=period_ids, limit=10)
        bottom_schools = fetch_bottom_schools(period_id=period_id, period_ids=period_ids, limit=10)
    photo_order = request.args.get("photo_order", "random")
    random_photos = fetch_random_photos(
        period_id=period_id,
        period_ids=period_ids,
        order=photo_order,
        limit=24,
        staff_ids=staff_ids,
    )
    school_avg_map = fetch_school_avg_scores(period_id=period_id, period_ids=period_ids, staff_ids=staff_ids)
    all_schools = list_portal_schools()
    all_staff = list_all_staff()
    monev_teams = get_monev_teams()
    
    from .queries import fetch_kecamatan_avg_scores
    kecamatan_stats = fetch_kecamatan_avg_scores(period_id=period_id, period_ids=period_ids, staff_ids=staff_ids)
    negeri_assessment_frequency = fetch_negeri_assessment_frequency(
        period_id=period_id,
        period_ids=period_ids,
        staff_ids=staff_ids,
    )
    
    return render_template(
        "portal/admin/stats.html",
        stats=stats,
        score_dist=score_dist,
        kecamatan_stats=kecamatan_stats,
        recent_assessments=recent_assessments,
        top_schools=top_schools,
        bottom_schools=bottom_schools,
        random_photos=random_photos,
        school_avg_map=school_avg_map,
        periods=periods,
        current_period_id=period_id,
        current_period_year=selected_year,
        current_period_month=selected_month,
        period_year_options=period_year_options,
        selected_team_id=team_id,
        selected_team=selected_team,
        jenjang_filter=jenjang_filter,
        order=order,
        photo_order=photo_order,
        all_schools=all_schools,
        all_staff=all_staff,
        monev_teams=monev_teams,
        staff_latest_assessments=staff_latest_assessments,
        negeri_assessment_frequency=negeri_assessment_frequency,
    )


@portal_bp.route("/admin/stats/negeri-frequency")
@role_required("admin")
def admin_stats_negeri_frequency() -> Response:
    """Detail negeri school names grouped by assessment frequency."""
    from dashboard.queries import get_monev_teams
    from .queries import fetch_negeri_assessment_frequency

    periods = list_periods()
    selected_year_arg = request.args.get("year", type=int)
    selected_month_arg = request.args.get("month", type=int)
    selected_period_arg = request.args.get("period_id", type=int)
    period_id, period_ids, period_year_options, selected_year, selected_month = _build_admin_stats_period_filter(
        periods,
        selected_year_arg,
        selected_month_arg,
        selected_period_arg,
    )
    team_id = request.args.get("team_id", type=int)
    selected_count = request.args.get("count", type=int)

    staff_ids: list[int] | None = None
    selected_team = None
    if team_id:
        staff_ids, selected_team = _get_team_staff_ids(team_id)
        if selected_team is None:
            staff_ids = None

    grouped = fetch_negeri_assessment_frequency(
        period_id=period_id,
        period_ids=period_ids,
        staff_ids=staff_ids,
    )
    available_counts = [int(row.get("count_times") or 0) for row in grouped]
    if selected_count is None and available_counts:
        selected_count = available_counts[0]
    selected_group = next(
        (row for row in grouped if int(row.get("count_times") or 0) == int(selected_count))
        if selected_count is not None
        else None,
        None,
    )

    return render_template(
        "portal/admin/stats_negeri_frequency.html",
        grouped=grouped,
        selected_group=selected_group,
        available_counts=available_counts,
        periods=periods,
        current_period_id=period_id,
        current_period_year=selected_year,
        current_period_month=selected_month,
        period_year_options=period_year_options,
        selected_team_id=team_id,
        selected_team=selected_team,
        monev_teams=get_monev_teams(),
        selected_count=selected_count,
    )


@portal_bp.route("/admin/gallery")
@role_required("admin")
def admin_gallery() -> Response:
    """Admin gallery view grouped by school."""
    from dashboard.queries import get_monev_teams

    period_id = request.args.get("period_id", type=int)
    team_id = request.args.get("team_id", type=int)
    order = request.args.get("order", "default")

    staff_ids: list[int] | None = None
    selected_team = None
    if team_id:
        staff_ids, selected_team = _get_team_staff_ids(team_id)
        if selected_team is None:
            staff_ids = None

    photos = fetch_gallery_photos(period_id=period_id, staff_ids=staff_ids)
    latest_at = fetch_gallery_latest_date(staff_ids=staff_ids)
    albums: list[dict] = []
    album_map: dict[int, dict] = {}
    for p in photos:
        school_id = p.get("school_id")
        if not school_id:
            continue
        album = album_map.get(school_id)
        if not album:
            album = {
                "school_id": school_id,
                "school_name": p.get("school_name") or "Sekolah",
                "school_jenjang": p.get("school_jenjang"),
                "photos": [],
            }
            album_map[school_id] = album
            albums.append(album)
        album["photos"].append(p)

    total_photos = sum(len(a.get("photos") or []) for a in albums)

    import random
    if order == "lowest":
        for album in albums:
            total_score = sum(
                float(
                    p.get("room_score_pct")
                    if p.get("room_score_pct") is not None
                    else _score_pct_from_raw(
                        float(p.get("room_score") or 0),
                        _normalize_assessment_scale_max(p.get("score_scale_max")),
                    )
                )
                for p in album["photos"]
            )
            count = len(album["photos"])
            album["_sort_score"] = (total_score / count) if count > 0 else 0
        albums.sort(key=lambda a: a["_sort_score"])
    elif order == "newest":
        for album in albums:
            max_dt = None
            for p in album["photos"]:
                dt = p.get("captured_at")
                if dt:
                    if not max_dt or dt > max_dt:
                        max_dt = dt
            album["_sort_date"] = max_dt
        albums.sort(key=lambda a: a["_sort_date"] if a["_sort_date"] else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    elif order == "random":
        random.shuffle(albums)

    periods = list_periods()
    if latest_at:
        latest_date = latest_at.date() if hasattr(latest_at, "date") else latest_at
    else:
        latest_date = datetime.now().date()
    periods = [
        p
        for p in periods
        if p.get("start_date") and p.get("start_date") <= latest_date
    ]
    monev_teams = get_monev_teams()

    return render_template(
        "portal/admin/gallery.html",
        albums=albums,
        total_photos=total_photos,
        total_schools=len(albums),
        periods=periods,
        current_period_id=period_id,
        selected_team_id=team_id,
        selected_team=selected_team,
        monev_teams=monev_teams,
        order=order,
    )


@portal_bp.route("/coordinator/gallery")
@role_required("coordinator")
def coordinator_gallery() -> Response:
    """Coordinator gallery view grouped by school."""
    user = current_user()
    period_id = request.args.get("period_id", type=int)
    order = request.args.get("order", "default")
    my_team, _, staff_ids = _get_coordinator_team_context(user.get("id"))

    if not my_team or not staff_ids:
        flash("Anda belum ditugaskan sebagai koordinator tim manapun.", "warning")
        periods = list_periods()
        return render_template(
            "portal/coordinator/gallery.html",
            albums=[],
            total_photos=0,
            total_schools=0,
            periods=periods,
            current_period_id=period_id,
            selected_team_id=None,
            selected_team=my_team,
            order=order,
        )

    photos = fetch_gallery_photos(
        period_id=period_id,
        staff_ids=staff_ids,
        restrict_to_staff=True,
    )
    latest_at = fetch_gallery_latest_date(
        period_id=period_id,
        staff_ids=staff_ids,
        restrict_to_staff=True,
    )
    albums: list[dict] = []
    album_map: dict[int, dict] = {}
    for p in photos:
        school_id = p.get("school_id")
        if not school_id:
            continue
        album = album_map.get(school_id)
        if not album:
            album = {
                "school_id": school_id,
                "school_name": p.get("school_name") or "Sekolah",
                "school_jenjang": p.get("school_jenjang"),
                "photos": [],
            }
            album_map[school_id] = album
            albums.append(album)
        album["photos"].append(p)

    total_photos = sum(len(a.get("photos") or []) for a in albums)

    import random
    if order == "lowest":
        for album in albums:
            total_score = sum(
                float(
                    p.get("room_score_pct")
                    if p.get("room_score_pct") is not None
                    else _score_pct_from_raw(
                        float(p.get("room_score") or 0),
                        _normalize_assessment_scale_max(p.get("score_scale_max")),
                    )
                )
                for p in album["photos"]
            )
            count = len(album["photos"])
            album["_sort_score"] = (total_score / count) if count > 0 else 0
        albums.sort(key=lambda a: a["_sort_score"])
    elif order == "newest":
        for album in albums:
            max_dt = None
            for p in album["photos"]:
                dt = p.get("captured_at")
                if dt:
                    if not max_dt or dt > max_dt:
                        max_dt = dt
            album["_sort_date"] = max_dt
        albums.sort(key=lambda a: a["_sort_date"] if a["_sort_date"] else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    elif order == "random":
        random.shuffle(albums)

    periods = list_periods()
    if latest_at:
        latest_date = latest_at.date() if hasattr(latest_at, "date") else latest_at
    else:
        latest_date = datetime.now().date()
    periods = [
        p
        for p in periods
        if p.get("start_date") and p.get("start_date") <= latest_date
    ]

    return render_template(
        "portal/coordinator/gallery.html",
        albums=albums,
        total_photos=total_photos,
        total_schools=len(albums),
        periods=periods,
        current_period_id=period_id,
        selected_team_id=my_team.get("id"),
        selected_team=my_team,
        order=order,
    )


@portal_bp.route("/api/rankings")
@role_required("admin")
def api_rankings() -> Response:
    """API endpoint for fetching additional rankings."""
    from .queries import fetch_team_top_schools, fetch_team_bottom_schools
    
    type_ = request.args.get("type", "best")
    limit = request.args.get("limit", 10, type=int)
    offset = request.args.get("offset", 0, type=int)
    periods = list_periods()
    selected_year_arg = request.args.get("year", type=int)
    selected_month_arg = request.args.get("month", type=int)
    selected_period_arg = request.args.get("period_id", type=int)
    period_id, period_ids, _year_options, _selected_year, _selected_month = _build_admin_stats_period_filter(
        periods,
        selected_year_arg,
        selected_month_arg,
        selected_period_arg,
    )
    team_id = request.args.get("team_id", type=int)
    
    staff_ids = None
    if team_id:
        staff_ids, team = _get_team_staff_ids(team_id)
        if team is None:
            staff_ids = None
    
    if type_ == "best":
        if staff_ids:
            data = fetch_team_top_schools(staff_ids, period_id=period_id, period_ids=period_ids, limit=limit, offset=offset)
        else:
            data = fetch_top_schools(limit=limit, offset=offset, period_id=period_id, period_ids=period_ids)
    else:
        if staff_ids:
            data = fetch_team_bottom_schools(staff_ids, period_id=period_id, period_ids=period_ids, limit=limit, offset=offset)
        else:
            data = fetch_bottom_schools(limit=limit, offset=offset, period_id=period_id, period_ids=period_ids)
        
    return jsonify(data)


@portal_bp.route("/coordinator/api/rankings")
@role_required("coordinator")
def coordinator_api_rankings() -> Response:
    """API endpoint for coordinator rankings limited to their team."""
    from .queries import fetch_team_top_schools, fetch_team_bottom_schools
    
    type_ = request.args.get("type", "best")
    limit = request.args.get("limit", 10, type=int)
    offset = request.args.get("offset", 0, type=int)
    period_id = request.args.get("period_id", type=int) or None
    
    user = current_user()
    _, _, staff_ids = _get_coordinator_team_context(user.get("id"))
    if not staff_ids:
        return jsonify([])
    
    if type_ == "best":
        data = fetch_team_top_schools(staff_ids, period_id=period_id, limit=limit, offset=offset)
    else:
        data = fetch_team_bottom_schools(staff_ids, period_id=period_id, limit=limit, offset=offset)
        
    return jsonify(data)


@portal_bp.route("/admin/export/excel")
@role_required("admin")
def export_excel() -> Response:
    """Export assessment data to Excel."""
    try:
        import pandas as pd
        import io
        from flask import send_file
    except ImportError:
        flash("Library pandas/openpyxl belum terinstall.", "danger")
        return redirect(url_for("portal.admin_stats"))

    period_id = request.args.get("period_id", type=int)
    
    from .queries import fetch_export_data
    data = fetch_export_data(period_id)
    
    if not data:
        flash("Tidak ada data untuk diexport.", "warning")
        return redirect(url_for("portal.admin_stats"))
        
    df = pd.DataFrame(data)
    
    # Rename columns for nicer headers if needed (already renamed in query SQL)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data Penilaian')
        
    output.seek(0)
    
    filename = f"Laporan_Penilaian_{datetime.now(JAKARTA_TZ).strftime('%Y%m%d')}.xlsx"
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@portal_bp.route("/admin/map-data")
@role_required("admin")
def admin_map_data() -> Response:
    """Return JSON data for school locations map."""
    periods = list_periods()
    selected_year_arg = request.args.get("year", type=int)
    selected_month_arg = request.args.get("month", type=int)
    selected_period_arg = request.args.get("period_id", type=int)
    period_id, period_ids, _year_options, _selected_year, _selected_month = _build_admin_stats_period_filter(
        periods,
        selected_year_arg,
        selected_month_arg,
        selected_period_arg,
    )
    team_id = request.args.get("team_id", type=int)
    from .queries import fetch_map_data
    
    staff_ids = None
    if team_id:
        staff_ids, team = _get_team_staff_ids(team_id)
        if team is None:
            staff_ids = None
    
    data = fetch_map_data(period_id=period_id, period_ids=period_ids, staff_ids=staff_ids)
    return jsonify(data)


@portal_bp.route("/coordinator/map-data")
@role_required("coordinator")
def coordinator_map_data() -> Response:
    """Return JSON data for school locations map - for coordinator role."""
    period_id = request.args.get("period_id", type=int)
    from .queries import fetch_map_data
    
    user = current_user()
    _, _, staff_ids = _get_coordinator_team_context(user.get("id"))
    data = fetch_map_data(period_id, staff_ids=staff_ids)
    return jsonify(data)


@portal_bp.route("/sekolah/profile", methods=["GET", "POST"])
@_portal_access_required
def sekolah_profile() -> Response:
    """View/update school profile data for sekolah role."""
    user = current_user()
    if user.get("role") != "sekolah":
        flash("Hanya akun sekolah yang dapat memperbarui profil sekolah.", "danger")
        return redirect(url_for("portal.home"))

    school = _fetch_user_school(user["id"])
    if not school:
        flash("Akun belum terhubung dengan sekolah. Hubungi admin.", "warning")
        return redirect(url_for("portal.home"))

    form_errors = []
    if request.method == "POST":
        payload = _build_profile_payload(request.form)
        form_errors = _validate_profile_data(payload, jenjang=school.get("jenjang"))
        if form_errors:
            flash("Data belum tersimpan. Periksa detail di bawah.", "warning")
        else:
            _save_school_profile(school["id"], payload)
            flash("Profil sekolah berhasil diperbarui.", "success")
            return redirect(url_for("portal.sekolah_profile"))

    meta = {
        **_normalize_metadata(school.get("metadata")),
        **(_build_profile_payload(request.form) if request.method == "POST" else {}),
    }
    kecamatan_list = list_kecamatan()
    kelurahan_list = list_kelurahan()
    return render_template(
        "portal/sekolah/profile.html",
        school=school,
        meta=meta,
        missing_fields=_compute_missing_profile_fields(school),
        form_errors=form_errors,
        kecamatan_list=kecamatan_list,
        kelurahan_list=kelurahan_list,
    )


@portal_bp.route("/sekolah/password", methods=["GET", "POST"])
@_portal_access_required
def sekolah_change_password() -> Response:
    """Allow sekolah users to change their password."""
    user = current_user()
    if user.get("role") != "sekolah":
        flash("Hanya akun sekolah yang dapat mengubah password.", "danger")
        return redirect(url_for("portal.home"))

    profile = get_dashboard_user_profile(user["id"])
    if not profile:
        flash("Profil tidak ditemukan.", "danger")
        return redirect(url_for("portal.sekolah_home"))

    if request.method == "POST":
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        errors = []
        if not new_password:
            errors.append("Password baru wajib diisi.")
        if not confirm_password:
            errors.append("Konfirmasi password baru wajib diisi.")
        if new_password and confirm_password and new_password != confirm_password:
            errors.append("Password baru dan konfirmasi tidak sama.")
        if new_password and len(new_password) < 8:
            errors.append("Password baru minimal 8 karakter.")

        if errors:
            for msg in errors:
                flash(msg, "danger")
        else:
            pw_hash = generate_password_hash(new_password, method="pbkdf2:sha256", salt_length=12)
            update_dashboard_user_profile(
                user_id=user["id"],
                full_name=profile.get("full_name") or None,
                email=profile.get("email") or None,
                whatsapp_number=profile.get("whatsapp_number"),
                nip=profile.get("nip"),
                nrk=profile.get("nrk"),
                jabatan=profile.get("jabatan"),
                password_hash=pw_hash,
            )
            flash("Password berhasil diperbarui.", "success")
            return redirect(url_for("portal.sekolah_change_password"))

    return render_template("portal/sekolah/change_password.html")


@portal_bp.route("/admin/photos")
@role_required("admin")
def admin_photos_partial() -> Response:
    """Return gallery grid partial for photo order changes (AJAX)."""
    periods = list_periods()
    selected_year_arg = request.args.get("year", type=int)
    selected_month_arg = request.args.get("month", type=int)
    selected_period_arg = request.args.get("period_id", type=int)
    period_id, period_ids, _year_options, _selected_year, _selected_month = _build_admin_stats_period_filter(
        periods,
        selected_year_arg,
        selected_month_arg,
        selected_period_arg,
    )
    photo_order = request.args.get("photo_order", "random")
    team_id = request.args.get("team_id", type=int)
    
    staff_ids = None
    if team_id:
        staff_ids, team = _get_team_staff_ids(team_id)
        if not team:
            return render_template("portal/shared/_gallery_grid.html", random_photos=[])
        if not staff_ids:
            return render_template("portal/shared/_gallery_grid.html", random_photos=[])

    photos = fetch_random_photos(
        period_id=period_id,
        period_ids=period_ids,
        order=photo_order,
        limit=24,
        staff_ids=staff_ids,
        restrict_to_staff=True,
    )
    return render_template("portal/shared/_gallery_grid.html", random_photos=photos)


@portal_bp.route("/coordinator/photos")
@role_required("coordinator")
def coordinator_photos_partial() -> Response:
    """Return gallery grid partial filtered to coordinator team."""
    period_id = request.args.get("period_id", type=int)
    photo_order = request.args.get("photo_order", "random")
    user = current_user()

    # Always scope to the coordinator's own team; optional team_id must match
    team_id = request.args.get("team_id", type=int)
    my_team, _, staff_ids = _get_coordinator_team_context(user.get("id"))
    if not my_team or not staff_ids:
        return render_template("portal/shared/_gallery_grid.html", random_photos=[])
    if team_id and team_id != my_team.get("id"):
        return render_template("portal/shared/_gallery_grid.html", random_photos=[])

    photos = fetch_random_photos(
        period_id=period_id,
        order=photo_order,
        limit=24,
        staff_ids=staff_ids,
    )
    return render_template("portal/shared/_gallery_grid.html", random_photos=photos)


@portal_bp.route("/admin/related-photos")
@role_required("admin")
def admin_related_photos() -> Response:
    """Return related photos for the same school and room type (AJAX JSON)."""
    school_id = request.args.get("school_id", type=int)
    room_id = request.args.get("room_id", type=int)
    team_id = request.args.get("team_id", type=int)
    
    staff_ids = None
    if team_id:
        staff_ids, team = _get_team_staff_ids(team_id)
        if team is None:
            staff_ids = None
    
    result = _serialize_related_photos(school_id, room_id, staff_ids=staff_ids)
    return jsonify(result)


@portal_bp.route("/admin/photo-recovery")
@role_required("admin")
def admin_photo_recovery() -> Response:
    """Admin page to recover orphaned photos into draft assessments."""
    orphan_files, stats = _collect_orphan_photo_files()
    schools = list_portal_schools(active_only=False)
    return render_template(
        "portal/admin/photo_recovery.html",
        orphan_files=orphan_files,
        stats=stats,
        schools=schools,
    )


@portal_bp.route("/admin/photo-recovery/school/<int:school_id>")
@role_required("admin")
def admin_photo_recovery_school_data(school_id: int) -> Response:
    """Return draft assessments and rooms for a school (AJAX JSON)."""
    school = get_school_by_id(school_id)
    if not school:
        return jsonify({"success": False, "message": "Sekolah tidak ditemukan"}), 404

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 
                a.id,
                a.created_at,
                a.staff_id,
                u.full_name AS staff_name,
                p.name AS period_name
            FROM portal_assessments a
            LEFT JOIN dashboard_users u ON u.id = a.staff_id
            LEFT JOIN portal_assessment_periods p ON p.id = a.period_id
            WHERE a.school_id = %s AND a.status = 'draft'
            ORDER BY a.created_at DESC
            """,
            (school_id,),
        )
        drafts = []
        for row in cur.fetchall():
            item = dict(row)
            created_at = item.get("created_at")
            if isinstance(created_at, datetime):
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                created_at = created_at.astimezone(JAKARTA_TZ)
                item["created_at"] = created_at.isoformat(timespec="seconds")
                item["created_at_label"] = created_at.strftime("%d %b %Y %H:%M WIB")
            drafts.append(item)

    rooms_raw = list_school_rooms(school_id)
    rooms = [
        {
            "school_room_id": room.get("school_room_id"),
            "room_name": room.get("room_name"),
        }
        for room in rooms_raw
    ]

    return jsonify({"success": True, "drafts": drafts, "rooms": rooms})


@portal_bp.route("/admin/photo-recovery/merge", methods=["POST"])
@role_required("admin")
def admin_photo_recovery_merge() -> Response:
    """Attach an orphaned photo file to a draft assessment room."""
    payload = request.get_json(silent=True) or {}
    if not payload:
        payload = request.form.to_dict()

    file_path = (payload.get("file_path") or "").strip()
    action = (payload.get("action") or "skip").strip().lower()

    try:
        assessment_id = int(payload.get("assessment_id"))
        school_room_id = int(payload.get("school_room_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Data penilaian tidak valid."}), 400

    rel_path = _normalize_photo_rel_path(file_path)
    if not rel_path:
        return jsonify({"success": False, "message": "Path foto tidak valid."}), 400

    candidate = (UPLOAD_FOLDER / rel_path).resolve()
    try:
        candidate.relative_to(UPLOAD_FOLDER.resolve())
    except ValueError:
        return jsonify({"success": False, "message": "Path foto tidak valid."}), 400

    if not candidate.exists() or not candidate.is_file():
        return jsonify({"success": False, "message": "File foto tidak ditemukan."}), 404

    if not _allowed_file(candidate.name):
        return jsonify({"success": False, "message": "Tipe file tidak didukung."}), 400

    assessment = get_assessment_by_id(assessment_id)
    if not assessment:
        return jsonify({"success": False, "message": "Assessment tidak ditemukan."}), 404

    if assessment.get("status") != "draft":
        return jsonify({"success": False, "message": "Assessment bukan draft."}), 400

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, school_id FROM portal_school_rooms WHERE id = %s",
            (school_room_id,),
        )
        room_row = cur.fetchone()

    if not room_row:
        return jsonify({"success": False, "message": "Ruangan tidak ditemukan."}), 404

    if room_row["school_id"] != assessment.get("school_id"):
        return jsonify({"success": False, "message": "Ruangan tidak sesuai sekolah draft."}), 400

    if action not in ("skip", "replace"):
        action = "skip"

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id FROM portal_assessment_photos
            WHERE assessment_id = %s AND school_room_id = %s
            """,
            (assessment_id, school_room_id),
        )
        existing = cur.fetchone()

    if existing and action == "skip":
        return jsonify(
            {
                "success": True,
                "status": "skipped",
                "message": "Sudah ada foto pada ruangan ini. Tidak diganti.",
            }
        )

    photo_path = f"uploads/portal/{rel_path}"
    captured_at = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc).astimezone(JAKARTA_TZ)

    try:
        saved = save_assessment_photo(
            assessment_id=assessment_id,
            school_room_id=school_room_id,
            photo_path=photo_path,
            latitude=None,
            longitude=None,
            captured_at=captured_at,
        )
    except Exception as exc:
        current_app.logger.exception("Error merging orphan photo")
        return jsonify({"success": False, "message": str(exc)}), 500

    return jsonify(
        {
            "success": True,
            "status": "saved",
            "photo": saved,
        }
    )


@portal_bp.route("/coordinator/related-photos")
@role_required("coordinator")
def coordinator_related_photos() -> Response:
    """Related photos restricted to coordinator's team assessments."""
    school_id = request.args.get("school_id", type=int)
    room_id = request.args.get("room_id", type=int)
    user = current_user()
    _, _, staff_ids = _get_coordinator_team_context(user.get("id"))
    
    result = _serialize_related_photos(school_id, room_id, staff_ids=staff_ids)
    return jsonify(result)

@portal_bp.route("/admin/periods/create", methods=["POST"])
@role_required("admin")
def create_period_route() -> Response:
    """Create a new period."""
    user = current_user()
    from .queries import log_activity
    if not can_manage_periods(user):
        flash("Anda tidak memiliki izin mengelola periode.", "warning")
        return redirect(url_for("portal.admin_stats"))
    name = request.form.get("name")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    is_active = request.form.get("is_active") == "on"
    
    if not all([name, start_date, end_date]):
        flash("Mohon lengkapi data periode.", "warning")
    else:
        try:
            period = create_period(name, start_date, end_date, is_active)
            log_activity(
                user.get("id"),
                "CREATE",
                "PERIOD",
                period.get("id"),
                period.get("name") or name,
                {
                    "start_date": start_date,
                    "end_date": end_date,
                    "active": bool(is_active),
                },
            )
            flash("Periode berhasil dibuat.", "success")
        except Exception as e:
            flash(f"Error: {e}", "danger")
        
    return redirect(url_for("portal.admin_stats"))


@portal_bp.route("/admin/reopen-requests")
@role_required("admin")
def admin_reopen_requests() -> Response:
    """Admin page to view reopen requests."""
    status = request.args.get("status") or None
    from .queries import fetch_activity_logs
    requests = list_reopen_requests(status=status)
    activity_logs = fetch_activity_logs(limit=50, target_types=("REOPEN_REQUEST",))
    return render_template(
        "portal/admin/reopen_requests.html",
        requests=requests,
        status_filter=status,
        activity_logs=activity_logs,
    )


@portal_bp.route("/admin/pending-summary")
@role_required("admin")
def admin_pending_summary() -> Response:
    """Return pending confirmation counts for admin notification polling."""
    try:
        return jsonify(fetch_admin_pending_summary())
    except Exception:
        current_app.logger.exception("Failed to fetch admin pending summary")
        return jsonify(
            {
                "pending_users": 0,
                "pending_assignment_requests": 0,
                "pending_team_member_requests": 0,
                "pending_reopen_requests": 0,
                "pending_guestbook": 0,
                "pending_call_center": 0,
                "total": 0,
            }
        )


@portal_bp.route("/admin/pending-preview")
@role_required("admin")
def admin_pending_preview() -> Response:
    """Return pending preview data for admin quick actions."""
    limit = request.args.get("limit", type=int) or 3
    limit = max(1, min(limit, 10))
    try:
        return jsonify(fetch_admin_pending_preview(limit_per_type=limit))
    except Exception:
        current_app.logger.exception("Failed to fetch admin pending preview")
        return jsonify(
            {
                "summary": {
                    "pending_users": 0,
                    "pending_assignment_requests": 0,
                    "pending_team_member_requests": 0,
                    "pending_reopen_requests": 0,
                    "pending_guestbook": 0,
                    "pending_call_center": 0,
                    "total": 0,
                },
                "users": [],
                "assignment_requests": [],
                "team_member_requests": [],
                "reopen_requests": [],
            }
        )


def _format_user_notification_created_label(value: object) -> str:
    if not isinstance(value, datetime):
        return ""
    local_dt = value
    if value.tzinfo is None:
        local_dt = value.replace(tzinfo=timezone.utc)
    local_dt = local_dt.astimezone(JAKARTA_TZ)
    now_dt = datetime.now(JAKARTA_TZ)
    delta_seconds = int((now_dt - local_dt).total_seconds())
    if delta_seconds < 60:
        return "Baru saja"
    if delta_seconds < 3600:
        return f"{max(1, delta_seconds // 60)} menit lalu"
    if delta_seconds < 86400:
        return f"{max(1, delta_seconds // 3600)} jam lalu"
    return local_dt.strftime("%d %b %Y, %H:%M WIB")


def _serialize_user_app_notification(row: dict, fallback_link: str) -> dict:
    notification_id = int(row.get("id") or 0)
    category = (row.get("category") or "").strip()
    status_value = (row.get("status") or "").strip().lower() or "unread"

    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    status_key = str(metadata.get("status") or "").strip().lower()

    icon = "bi-bell-fill"
    if category == PANBERS_REOPEN_NOTIFICATION_CATEGORY:
        icon = "bi-arrow-counterclockwise"
    elif category == PANBERS_ASSIGNMENT_NOTIFICATION_CATEGORY:
        icon = "bi-diagram-3-fill"
    elif category == PANBERS_TEAM_MEMBER_NOTIFICATION_CATEGORY:
        icon = "bi-people-fill"
    elif category == PANBERS_FOLLOW_UP_NOTIFICATION_CATEGORY:
        icon = "bi-tools"
    elif category == "daftar_tamu_status":
        icon = "bi-journal-check"

    tone = "secondary"
    if status_key == "approved":
        tone = "success"
    elif status_key == "rejected":
        tone = "danger"
    elif status_key == "pending":
        tone = "warning"
    elif status_key == PORTAL_FOLLOW_UP_STATUS_DONE:
        tone = "success"
    elif status_key in {
        PORTAL_FOLLOW_UP_STATUS_NEW,
        PORTAL_FOLLOW_UP_STATUS_IN_PROGRESS,
        PORTAL_FOLLOW_UP_STATUS_SUBMITTED,
    }:
        tone = "warning"

    created_at = row.get("created_at")
    created_at_iso = created_at.isoformat(timespec="seconds") if isinstance(created_at, datetime) else ""

    return {
        "id": notification_id,
        "category": category,
        "title": (row.get("title") or "").strip() or "Notifikasi",
        "message": (row.get("message") or "").strip(),
        "status": status_value,
        "is_unread": status_value == "unread",
        "link": (row.get("link") or "").strip() or fallback_link,
        "icon": icon,
        "tone": tone,
        "created_at": created_at_iso,
        "created_label": _format_user_notification_created_label(created_at),
        "reference_id": int(row.get("reference_id") or 0),
    }


@portal_bp.route("/saya/notifikasi")
@role_required("staff", "coordinator", "sekolah")
def user_app_notifications() -> Response:
    user = current_user()
    user_id = int(user.get("id"))
    limit = max(1, min(request.args.get("limit", type=int) or 8, 30))
    if user.get("role") == "sekolah":
        fallback_link = url_for("daftar_tamu.sekolah_riwayat")
    else:
        fallback_link = url_for("portal.home")
    categories = list(USER_APP_NOTIFICATION_CATEGORIES)

    try:
        summary = fetch_user_notification_summary(user_id=user_id, categories=categories)
        rows = list_user_notifications(user_id=user_id, limit=limit, categories=categories)
    except Exception:
        current_app.logger.exception("Gagal mengambil notifikasi aplikasi pengguna.")
        return jsonify(
            {
                "success": False,
                "items": [],
                "unread_count": 0,
                "total_count": 0,
                "generated_at": datetime.now(JAKARTA_TZ).isoformat(timespec="seconds"),
            }
        )

    return jsonify(
        {
            "success": True,
            "items": [_serialize_user_app_notification(row, fallback_link) for row in rows],
            "unread_count": int(summary.get("unread_count") or 0),
            "total_count": int(summary.get("total_count") or 0),
            "generated_at": datetime.now(JAKARTA_TZ).isoformat(timespec="seconds"),
        }
    )


@portal_bp.route("/saya/notifikasi/tandai-dibaca", methods=["POST"])
@role_required("staff", "coordinator", "sekolah")
def user_app_notifications_mark_read() -> Response:
    user = current_user()
    user_id = int(user.get("id"))
    payload = request.get_json(silent=True) if request.is_json else {}
    if not isinstance(payload, dict):
        payload = {}

    mark_all_raw = payload.get("all", request.form.get("all"))
    mark_all = str(mark_all_raw or "").strip().lower() in {"1", "true", "yes", "on"}

    raw_ids = payload.get("ids")
    if not isinstance(raw_ids, list):
        raw_ids = request.form.getlist("ids") or request.form.getlist("notification_ids")
    if not raw_ids and request.form.get("id"):
        raw_ids = [request.form.get("id")]

    safe_ids: list[int] = []
    for raw_id in raw_ids or []:
        try:
            safe_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    categories = list(USER_APP_NOTIFICATION_CATEGORIES)
    try:
        updated_count = mark_user_notifications_read(
            user_id=user_id,
            notification_ids=safe_ids,
            mark_all=mark_all,
            categories=categories,
        )
        summary = fetch_user_notification_summary(user_id=user_id, categories=categories)
    except Exception:
        current_app.logger.exception("Gagal memperbarui status baca notifikasi aplikasi pengguna.")
        return jsonify({"success": False, "message": "Gagal memperbarui notifikasi."}), 500

    return jsonify(
        {
            "success": True,
            "updated_count": int(updated_count or 0),
            "unread_count": int(summary.get("unread_count") or 0),
            "total_count": int(summary.get("total_count") or 0),
        }
    )


@portal_bp.route("/admin/periods", methods=["GET", "POST"])
@role_required("admin")
def admin_periods() -> Response:
    """Admin page to manage assessment periods."""
    user = current_user()
    from .queries import log_activity, fetch_activity_logs
    if not can_manage_periods(user):
        flash("Anda tidak memiliki izin mengelola periode.", "warning")
        return redirect(url_for("portal.admin_stats"))

    if request.method == "POST":
        name = request.form.get("name")
        start_date = request.form.get("start_date")
        end_date = request.form.get("end_date")
        is_active = request.form.get("is_active") == "on"
        if not all([name, start_date, end_date]):
            flash("Nama, tanggal mulai, dan selesai wajib diisi.", "warning")
        else:
            try:
                period = create_period(name, start_date, end_date, is_active)
                log_activity(
                    user.get("id"),
                    "CREATE",
                    "PERIOD",
                    period.get("id"),
                    period.get("name") or name,
                    {
                        "start_date": start_date,
                        "end_date": end_date,
                        "active": bool(is_active),
                    },
                )
                flash("Periode baru berhasil dibuat.", "success")
            except Exception as exc:
                flash(f"Gagal membuat periode: {exc}", "danger")
        return redirect(url_for("portal.admin_periods"))

    periods = list_periods()
    has_active = any(p.get("is_active") for p in periods)
    activity_logs = fetch_activity_logs(limit=50, target_types=("PERIOD",))
    return render_template(
        "portal/admin/periods.html",
        periods=periods,
        user=user,
        has_active=has_active,
        activity_logs=activity_logs,
    )


@portal_bp.route("/admin/periods/<int:period_id>/activate", methods=["POST"])
@role_required("admin")
def admin_activate_period(period_id: int) -> Response:
    """Set a period as the active period."""
    user = current_user()
    from .queries import log_activity
    if not can_manage_periods(user):
        flash("Anda tidak memiliki izin mengelola periode.", "warning")
        return redirect(url_for("portal.admin_stats"))

    if set_active_period(period_id):
        period = get_period_by_id(period_id)
        log_activity(
            user.get("id"),
            "UPDATE",
            "PERIOD",
            period_id,
            period.get("name") if period else f"Period {period_id}",
            {"active": True},
        )
        flash("Periode berhasil diaktifkan.", "success")
    else:
        flash("Periode tidak ditemukan.", "danger")
    return redirect(url_for("portal.admin_periods"))


@portal_bp.route("/admin/periods/<int:period_id>/edit", methods=["POST"])
@role_required("admin")
def admin_edit_period(period_id: int) -> Response:
    """Edit an existing period."""
    user = current_user()
    from .queries import log_activity
    if not can_manage_periods(user):
        flash("Anda tidak memiliki izin mengelola periode.", "warning")
        return redirect(url_for("portal.admin_stats"))

    name = request.form.get("name")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    is_active = request.form.get("is_active") == "on"
    if not all([name, start_date, end_date]):
        flash("Nama dan tanggal wajib diisi.", "warning")
    else:
        try:
            ok = update_period(period_id, name, start_date, end_date, is_active)
            if ok:
                log_activity(
                    user.get("id"),
                    "UPDATE",
                    "PERIOD",
                    period_id,
                    name or f"Period {period_id}",
                    {
                        "start_date": start_date,
                        "end_date": end_date,
                        "active": bool(is_active),
                    },
                )
                flash("Periode berhasil diperbarui.", "success")
            else:
                flash("Periode tidak ditemukan.", "danger")
        except Exception as exc:
            current_app.logger.exception("Error updating period")
            flash(f"Gagal memperbarui periode: {exc}", "danger")
    return redirect(url_for("portal.admin_periods"))


@portal_bp.route("/admin/periods/<int:period_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_period(period_id: int) -> Response:
    """Delete a non-active period."""
    user = current_user()
    from .queries import log_activity
    if not can_manage_periods(user):
        flash("Anda tidak memiliki izin mengelola periode.", "warning")
        return redirect(url_for("portal.admin_stats"))

    try:
        period = get_period_by_id(period_id)
        ok = delete_period(period_id)
        if ok:
            details = None
            if period:
                details = {
                    "start_date": str(period.get("start_date")) if period.get("start_date") else None,
                    "end_date": str(period.get("end_date")) if period.get("end_date") else None,
                    "active": bool(period.get("is_active")),
                }
            log_activity(
                user.get("id"),
                "DELETE",
                "PERIOD",
                period_id,
                period.get("name") if period else f"Period {period_id}",
                details,
            )
            flash("Periode berhasil dihapus.", "success")
        else:
            flash("Tidak bisa menghapus periode aktif atau tidak ditemukan.", "warning")
    except Exception as exc:
        current_app.logger.exception("Error deleting period")
        flash(f"Gagal menghapus periode: {exc}", "danger")
    return redirect(url_for("portal.admin_periods"))


@portal_bp.route("/admin/assign", methods=["POST"])
@role_required("admin")
def assign_assessment_route() -> Response:
    """Assign school to staff (without creating draft)."""
    school_id = request.form.get("school_id")
    staff_id = request.form.get("staff_id")
    
    if not all([school_id, staff_id]):
        flash("Pilih sekolah dan staff.", "warning")
    else:
        try:
            assign_staff_to_school(int(staff_id), int(school_id), current_user().get("id"))
            flash("Sekolah berhasil ditugaskan ke staff.", "success")
        except Exception as e:
            flash(f"Error: {e}", "danger")
        
    return redirect(url_for("portal.admin_stats"))


@portal_bp.route("/assessment/<int:assessment_id>/reopen", methods=["POST"])
@role_required("admin")
def reopen_route(assessment_id: int) -> Response:
    """Reopen a submitted assessment."""
    if reopen_assessment(assessment_id):
        flash("Penilaian berhasil dibuka kembali (Reopened).", "success")
    else:
        flash("Gagal membuka kembali.", "danger")
    return redirect(url_for("portal.view_assessment", assessment_id=assessment_id))


@portal_bp.route("/admin/setup")
@role_required("admin")
def admin_setup() -> Response:
    """Admin setup for rooms and aspects."""
    rooms = list_portal_rooms(active_only=False)
    schools = list_portal_schools(active_only=False)
    kecamatan_list = list_kecamatan()
    kelurahan_list = list_kelurahan()
    school_monitor_items = []
    school_monitor_attention_count = 0

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                s.id,
                s.npsn,
                s.name,
                s.jenjang,
                s.alamat,
                s.status,
                s.kelurahan_id,
                s.user_id,
                s.logo_url,
                s.metadata,
                s.active,
                s.created_at,
                l.name as kelurahan_name,
                k.name as kecamatan_name,
                COALESCE(uc.user_count, 0) as school_user_count,
                COALESCE(rc.room_count, 0) as room_count
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            LEFT JOIN (
                SELECT school_id, COUNT(*) as user_count
                FROM dashboard_users
                WHERE school_id IS NOT NULL AND role = 'sekolah'
                GROUP BY school_id
            ) uc ON uc.school_id = s.id
            LEFT JOIN (
                SELECT school_id, COUNT(*) as room_count
                FROM portal_school_rooms
                GROUP BY school_id
            ) rc ON rc.school_id = s.id
            ORDER BY s.name
            """
        )
        monitor_rows = cur.fetchall()

    for row in monitor_rows:
        school = dict(row)
        meta = _normalize_metadata(school.get("metadata"))
        school["metadata"] = meta

        missing_fields = _compute_missing_profile_fields(school)
        suspicious_reasons = _detect_suspicious_profile_data(school)
        is_claimed = (school.get("school_user_count") or 0) > 0
        has_rooms = (school.get("room_count") or 0) > 0

        # Check for rooms selected without any aspects
        rooms_without_aspects = []
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT r.name
                FROM portal_school_rooms sr
                JOIN portal_rooms r ON r.id = sr.room_id
                WHERE sr.school_id = %s
                AND NOT EXISTS (
                    SELECT 1 FROM portal_school_room_aspects psra
                    WHERE psra.school_room_id = sr.id
                )
                ORDER BY r.name
                """,
                (school.get("id"),)
            )
            rooms_without_aspects = [row["name"] for row in cur.fetchall()]

        operator_phone_raw = meta.get("coordinator_phone") or meta.get("school_phone") or ""
        operator_phone_display = str(operator_phone_raw).strip()
        operator_phone = _sanitize_phone(operator_phone_display)
        wa_link = None
        if operator_phone:
            msg = (
                f"Halo, kami dari admin ingin menindaklanjuti data sekolah "
                f"{school.get('name')} (NPSN {school.get('npsn')})."
            )
            wa_link = f"https://api.whatsapp.com/send?phone={operator_phone}&text={quote_plus(msg)}"

        missing_preview = ""
        if missing_fields:
            preview_items = missing_fields[:3]
            missing_preview = ", ".join(preview_items)
            if len(missing_fields) > 3:
                missing_preview = f"{missing_preview} +{len(missing_fields) - 3} lainnya"

        suspicious_preview = ""
        if suspicious_reasons:
            preview_items = suspicious_reasons[:2]
            suspicious_preview = ", ".join(preview_items)
            if len(suspicious_reasons) > 2:
                suspicious_preview = f"{suspicious_preview} +{len(suspicious_reasons) - 2} lainnya"

        rooms_no_aspects_preview = ""
        if rooms_without_aspects:
            preview_items = rooms_without_aspects[:2]
            rooms_no_aspects_preview = ", ".join(preview_items)
            if len(rooms_without_aspects) > 2:
                rooms_no_aspects_preview = f"{rooms_no_aspects_preview} +{len(rooms_without_aspects) - 2} lainnya"

        needs_attention = (not is_claimed) or (not has_rooms) or bool(missing_fields) or bool(suspicious_reasons) or bool(rooms_without_aspects)
        if needs_attention:
            school_monitor_attention_count += 1

        school_monitor_items.append(
            {
                "id": school.get("id"),
                "npsn": school.get("npsn"),
                "name": school.get("name"),
                "jenjang": school.get("jenjang"),
                "status": school.get("status"),
                "alamat": school.get("alamat"),
                "kelurahan_name": school.get("kelurahan_name"),
                "kecamatan_name": school.get("kecamatan_name"),
                "logo_url": school.get("logo_url"),
                "school_user_count": school.get("school_user_count", 0),
                "room_count": school.get("room_count", 0),
                "meta": meta,
                "is_claimed": is_claimed,
                "has_rooms": has_rooms,
                "is_incomplete": bool(missing_fields),
                "is_suspicious": bool(suspicious_reasons),
                "has_rooms_without_aspects": bool(rooms_without_aspects),
                "missing_preview": missing_preview,
                "missing_fields": missing_fields,
                "suspicious_preview": suspicious_preview,
                "suspicious_reasons": suspicious_reasons,
                "rooms_without_aspects": rooms_without_aspects,
                "rooms_no_aspects_preview": rooms_no_aspects_preview,
                "operator_phone": operator_phone_display,
                "operator_wa": wa_link,
            }
        )

    def _room_grade(name: str) -> int | None:
        parsed = parse_room_info(name)
        if not parsed:
            return None
        try:
            return int(parsed.get("grade_level"))
        except (TypeError, ValueError):
            return None

    def _is_variant_class(name: str) -> bool:
        parsed = parse_room_info(name)
        return bool((parsed or {}).get("is_variant"))

    # Build base rooms: keep non-class rooms and only one representative per jenjang band (SD=1, SMP=7, SMA=10)
    base_rooms = []
    seen_names = set()
    explicit_template_names = {
        "ruang kelas -1",
        "ruang kelas paud",
        "ruang kelas paket",
        "ruang kelas slb",
    }
    for r in rooms:
        name = r.get("name") or ""
        name_lower = name.strip().lower()
        grade = _room_grade(name)
        is_variant = _is_variant_class(name)
        templ = None
        is_tk_base = bool(re.search(r"^\\s*(?:Ruang\\s+)?Kelas\\s+-1\\s*$", name or "", flags=re.IGNORECASE))
        if grade is not None:
            if grade <= 6:
                templ = 1
            elif grade <= 9:
                templ = 7
            elif grade <= 12:
                templ = 10

        should_keep = False
        if name_lower in explicit_template_names:
            should_keep = True
        elif grade is None:
            should_keep = True  # non-class room
        elif is_tk_base:
            should_keep = True
        elif templ in (1, 7, 10) and grade == templ and not is_variant:
            should_keep = True  # representative per band

        if should_keep and name not in seen_names:
            base_rooms.append(r)
            seen_names.add(name)
    
    from .queries import fetch_activity_logs
    activity_logs = fetch_activity_logs(limit=50, target_types=("ROOM", "ASPECT", "SCHOOL"))
    
    return render_template(
        "portal/admin/setup.html",
        rooms=rooms,
        base_rooms=base_rooms,
        schools=schools,
        school_monitor_items=school_monitor_items,
        school_monitor_attention_count=school_monitor_attention_count,
        kecamatan_list=kecamatan_list,
        kelurahan_list=kelurahan_list,
        activity_logs=activity_logs,
    )


@portal_bp.route("/admin/setup/undo-window", methods=["POST"])
@role_required("admin")
def admin_update_undo_window() -> Response:
    """Persist global undo waiting window setting."""
    fallback_url = url_for("portal.admin_setup") + "#undo-settings"
    raw_value = (request.form.get("undo_window_seconds") or "").strip()
    try:
        requested_seconds = int(raw_value)
    except (TypeError, ValueError):
        flash("Durasi undo harus berupa angka.", "danger")
        return redirect(fallback_url)

    if requested_seconds < PORTAL_UNDO_WINDOW_MIN_SECONDS or requested_seconds > PORTAL_UNDO_WINDOW_MAX_SECONDS:
        flash(
            f"Durasi undo harus di antara {PORTAL_UNDO_WINDOW_MIN_SECONDS} sampai "
            f"{PORTAL_UNDO_WINDOW_MAX_SECONDS} detik.",
            "danger",
        )
        return redirect(fallback_url)

    actor = current_user() or {}
    try:
        actor_id = int(actor.get("id")) if actor.get("id") is not None else None
    except (TypeError, ValueError):
        actor_id = None
    try:
        saved_seconds = upsert_portal_undo_window_seconds(requested_seconds, actor_id)
    except Exception:
        current_app.logger.exception("Failed to save portal undo window settings")
        flash("Gagal menyimpan pengaturan undo.", "danger")
        return redirect(fallback_url)

    flash(f"Durasi undo diperbarui menjadi {saved_seconds} detik.", "success")
    return redirect(fallback_url)


@portal_bp.route("/admin/knowledge/refresh", methods=["POST"])
@role_required("admin")
def admin_refresh_knowledge() -> Response:
    """Regenerate Detail_Sekolah.md for ASKA knowledge base."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "generate_detail_sekolah_md.py"
    if not script_path.exists():
        flash("Script pembaruan Detail_Sekolah.md tidak ditemukan.", "danger")
        return redirect(url_for("portal.admin_setup"))

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        current_app.logger.exception("Gagal menjalankan generator Detail_Sekolah.md")
        flash("Gagal memperbarui Detail_Sekolah.md. Cek log server.", "danger")
        return redirect(url_for("portal.admin_setup"))

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        detail = detail.splitlines()[-1] if detail else ""
        if detail:
            flash(f"Gagal memperbarui Detail_Sekolah.md: {detail}", "danger")
        else:
            flash("Gagal memperbarui Detail_Sekolah.md. Cek log server.", "danger")
        return redirect(url_for("portal.admin_setup"))

    refresh_targets = []
    refresh_url = (os.getenv("ASKA_REFRESH_URL") or "").strip()
    refresh_token = (os.getenv("ASKA_REFRESH_TOKEN") or "").strip()
    if refresh_url and refresh_token:
        refresh_targets.append(("web", refresh_url, refresh_token))

    telegram_url = (os.getenv("ASKA_TELEGRAM_REFRESH_URL") or "").strip()
    telegram_token = (os.getenv("ASKA_TELEGRAM_REFRESH_TOKEN") or refresh_token or "").strip()
    if telegram_url and telegram_token:
        refresh_targets.append(("telegram", telegram_url, telegram_token))

    if refresh_targets:
        failed = []
        for name, url, token in refresh_targets:
            try:
                req = urlrequest.Request(
                    url,
                    method="POST",
                    headers={"X-ASKA-REFRESH-TOKEN": token},
                )
                with urlrequest.urlopen(req, timeout=10) as resp:
                    if resp.status >= 400:
                        raise RuntimeError(f"Status {resp.status}")
            except Exception:
                current_app.logger.exception("Gagal memanggil refresh %s", name)
                failed.append(name)

        if failed:
            if len(failed) == len(refresh_targets):
                flash(
                    "Detail_Sekolah.md diperbarui, tapi reload ASKA gagal. Restart manual jika diperlukan.",
                    "warning",
                )
            else:
                labels = ", ".join(failed)
                flash(
                    f"Detail_Sekolah.md diperbarui. Reload gagal untuk: {labels}.",
                    "warning",
                )
        else:
            flash("Detail_Sekolah.md diperbarui dan ASKA berhasil reload.", "success")
    else:
        flash(
            "Detail_Sekolah.md berhasil diperbarui. Restart layanan ASKA agar pengetahuan terbaru aktif.",
            "success",
        )
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/activity-logs")
@role_required("admin")
def admin_activity_logs() -> Response:
    """Admin view for consolidated activity logs."""
    from .queries import fetch_activity_logs

    limit = request.args.get("limit", type=int) or 200
    limit = max(1, min(limit, 500))
    activity_logs = fetch_activity_logs(limit=limit)

    return render_template(
        "portal/admin/activity_logs.html",
        activity_logs=activity_logs,
        limit=limit,
    )


@portal_bp.route("/admin/activity-logs/rows")
@role_required("admin")
def admin_activity_log_rows() -> Response:
    """Return activity log rows for incremental refresh."""
    from .queries import fetch_activity_logs

    limit = request.args.get("limit", type=int) or 50
    limit = max(1, min(limit, 500))
    target_types = request.args.getlist("target_type")
    if not target_types:
        target_types_raw = request.args.get("target_types", "")
        if target_types_raw:
            target_types = [item.strip() for item in target_types_raw.split(",") if item.strip()]

    activity_logs = fetch_activity_logs(limit=limit, target_types=target_types or None)

    return render_template(
        "portal/admin/_activity_log_rows.html",
        activity_logs=activity_logs,
    )


@portal_bp.route("/admin/setup/room", methods=["POST"])
@role_required("admin")
def add_room() -> Response:
    """Add a new room type."""
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    category = request.form.get("category", "umum").strip()
    sort_order = int(request.form.get("sort_order", 0))
    is_required = request.form.get("is_required", "on") == "on"
    
    if not name:
        flash("Nama ruangan wajib diisi.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        create_room(name, description, category, sort_order, is_required)
        
        from .queries import log_activity
        log_activity(current_user().get("id"), "CREATE", "ROOM", None, name, {"category": category, "is_required": is_required})
        
        flash(f"Ruangan '{name}' berhasil ditambahkan.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/aspect", methods=["POST"])
@role_required("admin")
def add_aspect() -> Response:
    """Add a new aspect to a room."""
    room_id = request.form.get("room_id")
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    sort_order = int(request.form.get("sort_order", 0))
    is_required = request.form.get("is_required", "on") == "on"
    
    if not room_id or not name:
        flash("Room ID dan nama aspek wajib diisi.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        room = get_room_by_id(int(room_id))
        create_aspect(int(room_id), name, description, sort_order, is_required)
        
        from .queries import log_activity
        log_activity(
            current_user().get("id"),
            "CREATE",
            "ASPECT",
            None,
            name,
            {"room_id": room_id, "room_name": room.get("name") if room else None},
        )
        
        if request.is_json:
            return jsonify({
                "success": True,
                "room_id": int(room_id),
                "aspects": _get_room_aspects(int(room_id)),
            })
        flash(f"Aspek '{name}' berhasil ditambahkan.", "success")
    except Exception as e:
        if request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/aspects/batch", methods=["POST"])
@role_required("admin")
def add_aspects_batch() -> Response:
    """Add multiple aspects at once (JSON API)."""
    data = request.get_json()
    aspects = data.get("aspects", [])
    is_required_default = bool(data.get("is_required", True))
    
    if not aspects:
        return jsonify({"success": False, "error": "No aspects provided"})
    
    created_count = 0
    errors = []
    touched_rooms: set[int] = set()
    
    for item in aspects:
        room_id = item.get("roomId")
        name = item.get("name", "").strip()
        is_required = bool(item.get("is_required", is_required_default))
        
        if not room_id or not name:
            errors.append(f"Missing room_id or name for aspect")
            continue
        
        try:
            rid = int(room_id)
            room = get_room_by_id(rid)
            create_aspect(rid, name, None, 0, is_required)
            
            from .queries import log_activity
            log_activity(
                current_user().get("id"),
                "CREATE",
                "ASPECT",
                None,
                name,
                {"room_id": rid, "room_name": room.get("name") if room else None, "batch": True},
            )
            
            created_count += 1
            touched_rooms.add(rid)
        except Exception as e:
            errors.append(f"Error creating '{name}': {str(e)}")
    
    room_aspects = {rid: _get_room_aspects(rid) for rid in touched_rooms}
    
    if request.is_json:
        return jsonify({
            "success": created_count > 0,
            "created": created_count,
            "errors": errors,
            "room_aspects": room_aspects,
        })
    if created_count > 0:
        flash(f"{created_count} aspek berhasil ditambahkan.", "success")
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/room/<int:room_id>", methods=["POST"])
@role_required("admin")
def edit_room(room_id: int) -> Response:
    """Update an existing room."""
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    category = request.form.get("category", "umum").strip()
    sort_order = int(request.form.get("sort_order", 0))
    active = request.form.get("active") == "on"
    is_required = request.form.get("is_required") == "on"
    
    if not name:
        flash("Nama ruangan wajib diisi.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        result = update_room(room_id, name, description, category, sort_order, active, is_required)
        if result:
            _sync_classroom_required_from_template(result, is_required)
            _sync_classroom_aspects_from_template_room(result)
            from .queries import log_activity
            log_activity(current_user().get("id"), "UPDATE", "ROOM", room_id, name, {"active": active})
            
            flash(f"Ruangan '{name}' berhasil diperbarui.", "success")
        else:
            flash("Ruangan tidak ditemukan.", "warning")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/room/<int:room_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_room_status(room_id: int) -> Response:
    """Toggle room active status."""
    room = get_room_by_id(room_id)
    if not room:
        flash("Ruangan tidak ditemukan.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        new_status = not room.get("active", True)
        result = update_room(
            room_id, 
            room["name"], 
            room.get("description"), 
            room.get("category", "umum"), 
            room.get("sort_order", 0), 
            new_status,
            room.get("is_required", False)
        )
        if result:
            from .queries import log_activity
            log_activity(current_user().get("id"), "UPDATE", "ROOM", room_id, room["name"], {"status": "active" if new_status else "inactive"})
            
            status_text = "diaktifkan" if new_status else "dinonaktifkan"
            flash(f"Ruangan '{room['name']}' berhasil {status_text}.", "success")
        else:
            flash("Gagal mengubah status ruangan.", "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup") + f"#room-{room_id}")


@portal_bp.route("/admin/setup/room/<int:room_id>/toggle-required", methods=["POST"])
@role_required("admin")
def toggle_room_required(room_id: int) -> Response:
    """Toggle room required flag."""
    room = get_room_by_id(room_id)
    if not room:
        flash("Ruangan tidak ditemukan.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        new_required = not room.get("is_required", True)
        result = update_room(
            room_id,
            room["name"],
            room.get("description"),
            room.get("category", "umum"),
            room.get("sort_order", 0),
            room.get("active", True),
            new_required,
        )
        if result:
            _sync_classroom_required_from_template(room, new_required)
            _sync_classroom_aspects_from_template_room(room)
            from .queries import log_activity
            log_activity(
                current_user().get("id"),
                "UPDATE",
                "ROOM",
                room_id,
                room["name"],
                {"required": new_required},
            )
            flash(f"Ruangan '{room['name']}' kini {'wajib' if new_required else 'opsional'}.", "success")
        else:
            flash("Gagal mengubah status wajib ruangan.", "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup") + f"#room-{room_id}")


@portal_bp.route("/admin/setup/rooms/reorder", methods=["POST"])
@role_required("admin")
def reorder_rooms() -> Response:
    """Persist new room order based on a drag-and-drop list."""
    data = request.get_json(silent=True) or {}
    room_ids_raw = data.get("room_ids") or []

    try:
        room_ids = [int(rid) for rid in room_ids_raw if rid is not None]
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Data ruangan tidak valid"}), 400

    if not room_ids:
        return jsonify({"success": False, "message": "Tidak ada ruangan untuk diurutkan"}), 400

    try:
        with get_cursor(commit=True) as cur:
            for idx, rid in enumerate(room_ids):
                cur.execute(
                    "UPDATE portal_rooms SET sort_order = %s WHERE id = %s",
                    (idx, rid),
                )

        from .queries import log_activity

        log_activity(
            current_user().get("id"),
            "UPDATE",
            "ROOM",
            None,
            "Reorder Rooms",
            {"count": len(room_ids)},
        )
        return jsonify({"success": True, "room_ids": room_ids})
    except Exception as exc:  # pragma: no cover - defensive
        current_app.logger.exception("Failed to reorder rooms")
        return jsonify({"success": False, "message": str(exc)}), 500


@portal_bp.route("/admin/setup/room/<int:room_id>/toggle-api", methods=["POST"])
@role_required("admin")
def toggle_room_status_api(room_id: int) -> Response:
    """Toggle room active status via AJAX - returns JSON."""
    room = get_room_by_id(room_id)
    if not room:
        return jsonify({"success": False, "error": "Ruangan tidak ditemukan"})
    
    try:
        new_status = not room.get("active", True)
        result = update_room(
            room_id, 
            room["name"], 
            room.get("description"), 
            room.get("category", "umum"), 
            room.get("sort_order", 0), 
            new_status,
            room.get("is_required", False)
        )
        if result:
            from .queries import log_activity
            log_activity(current_user().get("id"), "UPDATE", "ROOM", room_id, room["name"], {"status": "active" if new_status else "inactive"})
            
            return jsonify({"success": True, "active": new_status, "room_id": room_id})
        else:
            return jsonify({"success": False, "error": "Gagal mengubah status"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@portal_bp.route("/admin/setup/room/<int:room_id>/delete", methods=["POST"])
@role_required("admin")
def delete_room_route(room_id: int) -> Response:
    """Delete a room."""
    room = get_room_by_id(room_id)
    if not room:
        flash("Ruangan tidak ditemukan.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        if delete_room(room_id):
            from .queries import log_activity
            log_activity(current_user().get("id"), "DELETE", "ROOM", room_id, room["name"])
            
            flash(f"Ruangan '{room['name']}' berhasil dihapus.", "success")
        else:
            flash("Gagal menghapus ruangan.", "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/aspect/<int:aspect_id>", methods=["POST"])
@role_required("admin")
def edit_aspect(aspect_id: int) -> Response:
    """Update an existing aspect."""
    payload = {}
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        description = (payload.get("description") or "").strip() or None
        sort_order = int(payload.get("sort_order") or 0)
        active = bool(payload.get("active", True))
        is_required = bool(payload.get("is_required", True))
    else:
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        sort_order = int(request.form.get("sort_order", 0))
        active = request.form.get("active") == "on"
        is_required = request.form.get("is_required", "on") == "on"
    
    if not name:
        if request.is_json:
            return jsonify({"success": False, "message": "Nama aspek wajib diisi."}), 400
        flash("Nama aspek wajib diisi.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        aspect_before = get_aspect_by_id(aspect_id)
        result = update_aspect(aspect_id, name, description, sort_order, active, is_required)
        if result:
            if aspect_before:
                _sync_classroom_aspect_required_from_template(
                    aspect_before.get("room_name"),
                    aspect_before.get("name"),
                    is_required,
                )
            from .queries import log_activity
            log_activity(
                current_user().get("id"),
                "UPDATE",
                "ASPECT",
                aspect_id,
                name,
                {"room_id": aspect_before.get("room_id") if aspect_before else None, "room_name": aspect_before.get("room_name") if aspect_before else None},
            )
            if request.is_json:
                room_id = aspect_before.get("room_id") if aspect_before else None
                return jsonify({
                    "success": True,
                    "room_id": room_id,
                    "aspects": _get_room_aspects(room_id) if room_id else [],
                })
            flash(f"Aspek '{name}' berhasil diperbarui.", "success")
        else:
            if request.is_json:
                return jsonify({"success": False, "message": "Aspek tidak ditemukan"}), 404
            flash("Aspek tidak ditemukan.", "warning")
    except Exception as e:
        if request.is_json:
            return jsonify({"success": False, "message": str(e)}), 500
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/aspect/<int:aspect_id>/delete", methods=["POST"])
@role_required("admin")
def delete_aspect_route(aspect_id: int) -> Response:
    """Delete an aspect."""
    aspect = get_aspect_by_id(aspect_id)
    if not aspect:
        if request.is_json:
            return jsonify({"success": True, "room_id": None, "aspects": []})
        flash("Aspek sudah dihapus atau tidak ditemukan.", "info")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        if delete_aspect(aspect_id):
            from .queries import log_activity
            log_activity(
                current_user().get("id"),
                "DELETE",
                "ASPECT",
                aspect_id,
                aspect["name"],
                {"room_id": aspect.get("room_id"), "room_name": aspect.get("room_name")},
            )
            if request.is_json:
                return jsonify({
                    "success": True,
                    "room_id": aspect.get("room_id"),
                    "aspects": _get_room_aspects(aspect.get("room_id")),
                })
            flash(f"Aspek '{aspect['name']}' berhasil dihapus.", "success")
        else:
            if request.is_json:
                return jsonify({"success": False, "message": "Gagal menghapus aspek"}), 400
            flash("Gagal menghapus aspek.", "danger")
    except Exception as e:
        if request.is_json:
            return jsonify({"success": False, "message": str(e)}), 500
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/aspect/<int:aspect_id>/toggle-required", methods=["POST"])
@role_required("admin")
def toggle_aspect_required(aspect_id: int) -> Response:
    """Toggle required flag for an aspect."""
    aspect = get_aspect_by_id(aspect_id)
    if not aspect:
        return jsonify({"success": False, "message": "Aspek tidak ditemukan"}), 404
    try:
        new_required = not aspect.get("is_required", True)
        updated = update_aspect(
            aspect_id,
            aspect.get("name") or "",
            aspect.get("description"),
            aspect.get("sort_order") or 0,
            aspect.get("active", True),
            new_required,
        )
        if updated:
            _sync_classroom_aspect_required_from_template(
                aspect.get("room_name"),
                aspect.get("name"),
                new_required,
            )
            from .queries import log_activity
            log_activity(
                current_user().get("id"),
                "UPDATE",
                "ASPECT",
                aspect_id,
                aspect.get("name"),
                {"is_required": new_required},
            )
            room_id = aspect.get("room_id")
            return jsonify({
                "success": True,
                "room_id": room_id,
                "is_required": new_required,
                "aspects": _get_room_aspects(room_id) if room_id else [],
            })
        return jsonify({"success": False, "message": "Gagal mengubah status wajib"}), 500
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500

@portal_bp.route("/admin/setup/school", methods=["POST"])
@role_required("admin")
def add_school() -> Response:
    """Add or update a school."""
    npsn = request.form.get("npsn", "").strip()
    name = request.form.get("name", "").strip()
    jenjang = request.form.get("jenjang", "SD").strip()
    alamat = request.form.get("alamat", "").strip() or None
    kelurahan_id = request.form.get("kelurahan_id", type=int)
    status = request.form.get("status", "NEGERI").strip()
    
    if not npsn or not name:
        flash("NPSN dan nama sekolah wajib diisi.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    if not kelurahan_id:
        flash("Kelurahan wajib dipilih.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        from .queries import get_school_by_npsn, log_activity
        
        # Check if school exists to determine log action
        existing_school = get_school_by_npsn(npsn)
        action = "UPDATE" if existing_school else "CREATE"
        school_id = existing_school.get("id") if existing_school else None
        
        create_school(npsn, name, jenjang, alamat, kelurahan_id, status)
        
        log_activity(current_user().get("id"), action, "SCHOOL", school_id, name, {"npsn": npsn})
        
        flash(f"Sekolah '{name}' berhasil {'diperbarui' if action == 'UPDATE' else 'ditambahkan'}.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/school/<int:school_id>/delete", methods=["POST"])
@role_required("admin")
def delete_school_route(school_id: int) -> Response:
    """Delete a school."""
    from .queries import get_school_by_id, delete_school, log_activity
    
    school = get_school_by_id(school_id)
    if not school:
        flash("Sekolah tidak ditemukan.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        if delete_school(school_id):
            log_activity(current_user().get("id"), "DELETE", "SCHOOL", school_id, school["name"])
            flash(f"Sekolah '{school['name']}' berhasil dihapus.", "success")
        else:
            flash("Gagal menghapus sekolah.", "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


# ===== School Registration =====

@portal_bp.route("/api/schools/search")
def search_schools_api() -> Response:
    """API endpoint for NPSN autocomplete search."""
    q = request.args.get("q", "").strip()
    if len(q) < 3:
        return jsonify([])
    
    schools = search_schools_by_npsn(q, limit=10)
    return jsonify([
        {
            "id": s["id"],
            "npsn": s["npsn"],
            "name": s["name"],
            "jenjang": s["jenjang"],
            "kecamatan": s.get("kecamatan_name") or "",
        }
        for s in schools
    ])


@portal_bp.route("/register", methods=["GET", "POST"])
def register_school() -> Response:
    """School account registration page."""
    from werkzeug.security import generate_password_hash
    from dashboard.queries import get_user_by_email
    from dashboard.db_access import get_cursor
    
    # If user is logged in, redirect to home
    if current_user():
        return redirect(url_for("portal.home"))
    
    if request.method == "POST":
        npsn = request.form.get("npsn", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        # Validate inputs
        errors = []
        if not npsn:
            errors.append("NPSN sekolah wajib dipilih.")
        if not email:
            errors.append("Email wajib diisi.")
        if not password:
            errors.append("Password wajib diisi.")
        if password != confirm_password:
            errors.append("Password dan konfirmasi tidak cocok.")
        if len(password) < 6:
            errors.append("Password minimal 6 karakter.")
        
        # Check if school exists
        school = get_school_by_npsn(npsn) if npsn else None
        if npsn and not school:
            errors.append(f"Sekolah dengan NPSN {npsn} tidak ditemukan.")
        
        existing_school_user = None
        if school:
            with get_cursor() as cur:
                cur.execute(
                    "SELECT email FROM dashboard_users WHERE school_id = %s LIMIT 1",
                    (school["id"],),
                )
                existing_school_user = cur.fetchone()
            if existing_school_user:
                coordinator_contacts = _build_coordinator_contacts(school)
                flash("Sekolah ini sudah memiliki akun terdaftar.", "warning")
                return render_template(
                    "portal/registration/register_school.html",
                    npsn=npsn,
                    email=email,
                    school=school,
                    existing_school_email=existing_school_user["email"],
                    coordinator_contacts=coordinator_contacts,
                    show_registered_modal=True,
                )
        
        # Check if email already registered
        if email and get_user_by_email(email):
            errors.append("Email sudah terdaftar. Silakan login.")
        
        if errors:
            for err in errors:
                flash(err, "warning")
            return render_template("portal/registration/register_school.html", npsn=npsn, email=email)
        
        # Create user account with role "sekolah"
        try:
            password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=12)
            from dashboard.db_access import get_cursor
            
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    INSERT INTO dashboard_users (email, full_name, password_hash, role, school_id)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (email, school["name"], password_hash, "sekolah", school["id"]),
                )
            
            flash(f"Pendaftaran berhasil! Silakan login dengan email {email}.", "success")
            return redirect(url_for("auth.login"))
        
        except Exception as e:
            flash(f"Gagal membuat akun: {e}", "danger")
            return render_template("portal/registration/register_school.html", npsn=npsn, email=email)
    
    return render_template(
        "portal/registration/register_school.html",
        coordinator_contacts=_build_coordinator_contacts(),
    )


# ===== AI Sidak Route Planner =====


@portal_bp.route("/admin/sidak-planner")
@role_required("admin")
def sidak_planner() -> Response:
    """Admin page for AI-powered sidak route planning."""
    period_id = request.args.get("period_id", type=int)
    periods = list_periods()
    
    # Get kelurahan sorted by urgency (lowest score first)
    kelurahan_list = list_kelurahan_by_urgency(period_id)
    
    # Get all kelurahan for Tab 2
    all_kelurahan_list = list_kelurahan()
    
    return render_template(
        "portal/admin/sidak_planner.html",
        kelurahan_list=kelurahan_list,
        all_kelurahan_list=all_kelurahan_list,
        periods=periods,
        current_period_id=period_id,
    )


@portal_bp.route("/admin/sidak-route", methods=["POST"])
@role_required("admin")
def generate_sidak_route() -> Response:
    """API endpoint to generate optimized sidak route for a kelurahan."""
    data = request.get_json(silent=True) or {}
    kelurahan_id = data.get("kelurahan_id")
    period_id = data.get("period_id")
    max_schools = data.get("max_schools", 10)
    
    if not kelurahan_id:
        return jsonify({"success": False, "message": "Kelurahan harus dipilih"}), 400
    
    try:
        kelurahan_id = int(kelurahan_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Kelurahan ID tidak valid"}), 400
    
    # Get schools for sidak
    schools = fetch_schools_for_sidak(
        kelurahan_id=kelurahan_id,
        max_score_pct=60,
        period_id=period_id,
    )
    
    if not schools:
        return jsonify({"success": False, "message": "Tidak ada sekolah dengan data penilaian di kelurahan ini"}), 404
    
    # Filter schools with GPS
    schools_with_gps = [s for s in schools if s.get("latitude") and s.get("longitude")]
    
    if not schools_with_gps:
        return jsonify({
            "success": False, 
            "message": "Tidak ada sekolah dengan data GPS di kelurahan ini. Perlu foto dengan lokasi.",
            "schools": schools[:max_schools],
        }), 200
    
    # Limit schools
    schools_to_optimize = schools_with_gps[:max_schools]
    
    # Optimize route using nearest neighbor algorithm
    from .ai_route_planner import (
        optimize_route,
        generate_gmaps_deeplink,
        calculate_route_stats,
        DEFAULT_START_LOCATION,
    )
    
    optimized = optimize_route(
        schools_to_optimize,
        start_lat=DEFAULT_START_LOCATION["latitude"],
        start_lon=DEFAULT_START_LOCATION["longitude"],
    )
    
    # Generate Google Maps link
    gmaps_link = generate_gmaps_deeplink(
        optimized,
        start_lat=DEFAULT_START_LOCATION["latitude"],
        start_lon=DEFAULT_START_LOCATION["longitude"],
    )
    
    # Calculate stats
    stats = calculate_route_stats(
        optimized,
        start_lat=DEFAULT_START_LOCATION["latitude"],
        start_lon=DEFAULT_START_LOCATION["longitude"],
    )
    
    return jsonify({
        "success": True,
        "start_location": DEFAULT_START_LOCATION,
        "schools": optimized,
        "all_schools": schools,
        "gmaps_link": gmaps_link,
        "stats": stats,
    })


@portal_bp.route("/admin/school-rooms/<int:school_id>")
@_portal_access_required
def get_school_room_details(school_id: int) -> Response:
    """Get room details with scores, photos, and notes grouped by staff."""
    from .queries import get_cursor
    
    query = """
        SELECT 
            r.id as room_id,
            r.name as room_name,
            sr.id as school_room_id,
            a.id as assessment_id,
            u.full_name as staff_name,
            u.id as staff_id,
            -- Average score for this room in raw and normalized scale-aware percentage
            COALESCE(AVG(sc.score), 0)::DECIMAL(5,2) as avg_score_raw,
            ROUND(
                COALESCE(
                    AVG(
                        sc.score::DECIMAL / NULLIF(COALESCE(a.score_scale_max, 3), 0) * 100
                    ),
                    0
                ),
                1
            ) as avg_score_pct,
            -- Photo path
            (SELECT p.photo_path FROM portal_assessment_photos p 
             WHERE p.assessment_id = a.id AND p.school_room_id = sr.id 
             ORDER BY p.captured_at DESC NULLS LAST LIMIT 1) as photo_path,
            -- Notes
            (SELECT d.notes FROM portal_assessment_room_details d
             WHERE d.assessment_id = a.id AND d.school_room_id = sr.id
             LIMIT 1) as notes
        FROM portal_school_rooms sr
        JOIN portal_rooms r ON sr.room_id = r.id
        JOIN portal_assessments a ON a.school_id = sr.school_id
        JOIN dashboard_users u ON a.staff_id = u.id
        LEFT JOIN portal_assessment_scores sc 
            ON sc.assessment_id = a.id AND sc.school_room_id = sr.id
        WHERE sr.school_id = %s
          AND a.status IN ('submitted', 'verified')
        GROUP BY r.id, r.name, sr.id, a.id, u.full_name, u.id
        HAVING AVG(sc.score) IS NOT NULL
        ORDER BY avg_score_pct ASC, r.name, u.full_name
    """
    
    with get_cursor() as cur:
        cur.execute(query, (school_id,))
        rows = [dict(row) for row in cur.fetchall()]
    
    # Group by room, then by staff
    rooms = {}
    for row in rows:
        room_id = row["room_id"]
        if room_id not in rooms:
            rooms[room_id] = {
                "room_id": room_id,
                "room_name": row["room_name"],
                "staff_assessments": []
            }
        
        photo_url = None
        if row.get("photo_path"):
            from pathlib import Path
            filename = Path(row["photo_path"]).name
            photo_url = url_for("portal.uploaded_file", filename=filename)
        
        rooms[room_id]["staff_assessments"].append({
            "staff_id": row["staff_id"],
            "staff_name": row["staff_name"],
            "score_pct": float(row["avg_score_pct"]) if row.get("avg_score_pct") else 0,
            "photo_url": photo_url,
            "notes": row.get("notes") or "",
        })
    
    # Sort rooms by lowest score first
    result = sorted(rooms.values(), key=lambda r: min(
        [s["score_pct"] for s in r["staff_assessments"]] or [100]
    ))
    
    return jsonify({
        "success": True,
        "school_id": school_id,
        "rooms": result,
    })


@portal_bp.route("/sekolah/classrooms", methods=["POST"])
@_portal_access_required
def save_classrooms() -> Response:
    """Save classroom configurations for a school."""
    user = current_user()
    
    if user.get("role") != "sekolah":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    user_school = _fetch_user_school(user["id"])
    if not user_school:
        return jsonify({"success": False, "message": "Sekolah tidak ditemukan"}), 404
    
    data = request.get_json(silent=True) or {}
    classrooms = sanitize_submitted_classrooms(user_school.get("jenjang"), data.get("classrooms", []))
    
    try:
        save_school_classrooms_batch(user_school["id"], classrooms)
        ensure_classroom_rooms_for_school(user_school["id"])
        enable_all_classroom_room_aspects_for_school(user_school["id"])
        return jsonify({"success": True, "message": "Konfigurasi kelas berhasil disimpan"})
    except Exception as e:
        current_app.logger.exception("Error saving classrooms")
        return jsonify({"success": False, "message": str(e)}), 500


@portal_bp.route("/sekolah/classrooms/<int:classroom_id>/delete", methods=["POST"])
@_portal_access_required
def delete_classroom_route(classroom_id: int) -> Response:
    """Delete a classroom configuration."""
    user = current_user()
    
    if user.get("role") != "sekolah":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        if delete_school_classroom(classroom_id):
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Gagal menghapus kelas"}), 400
    except Exception as e:
        current_app.logger.exception("Error deleting classroom")
        return jsonify({"success": False, "message": str(e)}), 500


# ===== Admin Staff Management Routes =====


@portal_bp.route("/admin/manage-staff")
@role_required("admin")
def admin_manage_staff() -> Response:
    """Admin interface to manage staff-school assignments."""
    user = current_user()
    from .queries import fetch_activity_logs
    
    # Admin only
    if not can_assign_staff(user):
        flash("Anda tidak memiliki izin untuk mengelola staff. Hubungi admin utama.", "warning")
        return redirect(url_for("portal.admin_stats"))
    
    # Get all staff with their assignments
    all_staff = list_all_staff_with_assignments()
    assignments_overview = list_all_staff_assignments_overview()
    
    # Admin dapat melihat semua sekolah
    available_schools = list_portal_schools()
    pending_requests = list_assignment_requests(status="pending")
    periods = list_periods()
    active_period_id = next((p["id"] for p in periods if p.get("is_active")), None) or (periods[0]["id"] if periods else None)
    activity_logs = fetch_activity_logs(
        limit=50,
        target_types=("STAFF_ASSIGNMENT", "ASSIGNMENT_REQUEST"),
    )
    
    return render_template(
        "portal/admin/manage_staff.html",
        staff_list=all_staff,
        assignments_overview=assignments_overview,
        available_schools=available_schools,
        pending_requests=pending_requests,
        periods=periods,
        active_period_id=active_period_id,
        user=user,
        activity_logs=activity_logs,
    )


@portal_bp.route("/coordinator/manage-staff")
@role_required("coordinator")
def coordinator_manage_staff() -> Response:
    """Coordinator interface to submit staff-school assignment requests."""
    user = current_user()
    team, team_members, _ = _get_coordinator_team_context(user.get("id"))
    if not team:
        flash("Anda belum memiliki tim.", "warning")
        return redirect(url_for("portal.view_my_team"))

    staff_list = []
    team_member_ids = []
    for member in team_members:
        staff_id = member.get("staff_id")
        if not staff_id:
            continue
        team_member_ids.append(staff_id)
        assigned_count = len(get_staff_assigned_schools(staff_id))
        staff_list.append(
            {
                "id": staff_id,
                "email": member.get("email"),
                "full_name": member.get("full_name"),
                "nip": member.get("nip"),
                "role": member.get("role"),
                "assigned_schools_count": assigned_count,
            }
        )

    if user.get("id") not in team_member_ids:
        assigned_count = len(get_staff_assigned_schools(user.get("id")))
        staff_list.append(
            {
                "id": user.get("id"),
                "email": user.get("email"),
                "full_name": user.get("full_name") or "Koordinator",
                "nip": user.get("nip"),
                "role": user.get("role"),
                "assigned_schools_count": assigned_count,
            }
        )

    staff_list.sort(key=lambda row: (row.get("full_name") or "").lower())

    available_schools = list_portal_schools()
    periods = list_periods()
    active_period_id = next((p["id"] for p in periods if p.get("is_active")), None) or (
        periods[0]["id"] if periods else None
    )

    return render_template(
        "portal/admin/manage_staff.html",
        staff_list=staff_list,
        assignments_overview=[],
        available_schools=available_schools,
        pending_requests=[],
        periods=periods,
        active_period_id=active_period_id,
        user=user,
        activity_logs=[],
    )


@portal_bp.route("/admin/assign-school", methods=["POST"])
@role_required("admin")
def admin_assign_school() -> Response:
    """Admin assigns a school to a staff member."""
    user = current_user()
    from .queries import log_activity, fetch_activity_logs
    
    # Admin only
    if not can_assign_staff(user):
        return jsonify({"success": False, "message": "Tidak memiliki izin"}), 403
    
    staff_id = request.form.get("staff_id", type=int)
    school_id = request.form.get("school_id", type=int)
    period_id = request.form.get("period_id", type=int)
    notes = request.form.get("notes", "").strip()
    
    if not staff_id or not school_id:
        return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    
    try:
        assignment = assign_staff_to_school(staff_id, school_id, user["id"], notes)
        staff_info = _fetch_dashboard_user_summary(staff_id)
        school = get_school_by_id(school_id)
        details = {
            "staff_id": staff_id,
            "school_id": school_id,
        }
        if period_id:
            details["period_id"] = period_id
        if notes:
            details["notes"] = notes
        if staff_info:
            details["staff_name"] = staff_info.get("full_name")
            details["staff_email"] = staff_info.get("email")
        if school:
            details["school_name"] = school.get("name")
            details["npsn"] = school.get("npsn")
        log_activity(
            user.get("id"),
            "CREATE",
            "STAFF_ASSIGNMENT",
            assignment.get("id") if assignment else None,
            school.get("name") if school else f"School {school_id}",
            details,
        )
        flash(f"Sekolah berhasil ditugaskan ke staf.", "success")
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.exception("Error assigning school")
        return jsonify({"success": False, "message": str(e)}), 500


@portal_bp.route("/admin/assign-schools-batch", methods=["POST"])
@role_required("admin")
def admin_assign_school_batch() -> Response:
    """Admin assigns multiple schools to a staff member in one request."""
    user = current_user()
    from .queries import log_activity
    if not can_assign_staff(user):
        return jsonify({"success": False, "message": "Tidak memiliki izin"}), 403

    data = request.get_json(silent=True) or {}
    staff_id = data.get("staff_id")
    school_ids = data.get("school_ids") or []
    period_id_raw = data.get("period_id")
    notes = (data.get("notes") or "").strip() or None

    if not staff_id or not school_ids:
        return jsonify({"success": False, "message": "Staff dan daftar sekolah wajib diisi"}), 400

    try:
        staff_id_int = int(staff_id)
        school_ids_int = {int(sid) for sid in school_ids if sid}
        period_id_int = int(period_id_raw) if period_id_raw not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Format data tidak valid"}), 400

    assigned = 0
    errors: list[str] = []
    for sid in school_ids_int:
        try:
            assign_staff_to_school(staff_id_int, sid, user["id"], notes)
            assigned += 1
        except Exception as exc:
            current_app.logger.exception("Error assigning school %s", sid)
            errors.append(f"{sid}: {exc}")

    try:
        total_assignments = len(get_staff_assigned_schools(staff_id_int))
    except Exception:
        total_assignments = None
    
    if assigned > 0:
        staff_info = _fetch_dashboard_user_summary(staff_id_int)
        details = {
            "staff_id": staff_id_int,
            "school_ids": sorted(str(sid) for sid in school_ids_int),
            "count": assigned,
        }
        if period_id_int is not None:
            details["period_id"] = period_id_int
        if notes:
            details["notes"] = notes
        if staff_info:
            details["staff_name"] = staff_info.get("full_name")
            details["staff_email"] = staff_info.get("email")
        if errors:
            details["errors"] = errors
        log_activity(
            user.get("id"),
            "CREATE",
            "STAFF_ASSIGNMENT",
            None,
            staff_info.get("full_name") if staff_info else f"Staff {staff_id_int}",
            details,
        )

    return jsonify({
        "success": assigned > 0,
        "assigned": assigned,
        "errors": errors,
        "total_assignments": total_assignments,
    })


@portal_bp.route("/admin/assignment/<int:assignment_id>/update", methods=["POST"])
@role_required("admin")
def admin_update_assignment_notes(assignment_id: int) -> Response:
    """Admin updates notes for a staff-school assignment."""
    user = current_user()
    from .queries import log_activity

    if not can_assign_staff(user):
        return jsonify({"success": False, "message": "Tidak memiliki izin"}), 403

    notes = (request.form.get("notes") or "").strip() or None

    try:
        updated = update_staff_assignment_notes(assignment_id, notes, user.get("id"))
        if not updated:
            return jsonify({"success": False, "message": "Penugasan tidak ditemukan"}), 404

        staff_info = _fetch_dashboard_user_summary(updated.get("staff_id"))
        school = get_school_by_id(updated.get("school_id")) if updated.get("school_id") else None
        details = {
            "assignment_id": assignment_id,
            "staff_id": updated.get("staff_id"),
            "school_id": updated.get("school_id"),
            "notes": notes,
        }
        if staff_info:
            details["staff_name"] = staff_info.get("full_name")
            details["staff_email"] = staff_info.get("email")
        if school:
            details["school_name"] = school.get("name")
            details["npsn"] = school.get("npsn")

        log_activity(
            user.get("id"),
            "UPDATE",
            "STAFF_ASSIGNMENT",
            assignment_id,
            school.get("name") if school else f"Assignment {assignment_id}",
            details,
        )

        return jsonify({"success": True, "notes": notes})
    except Exception as e:
        current_app.logger.exception("Error updating assignment notes")
        return jsonify({"success": False, "message": str(e)}), 500


@portal_bp.route("/admin/assignments/delete-batch", methods=["POST"])
@role_required("admin")
def admin_delete_assignments_batch() -> Response:
    """Admin deletes multiple staff-school assignments."""
    user = current_user()
    from .queries import log_activity

    if not can_assign_staff(user):
        return jsonify({"success": False, "message": "Tidak memiliki izin"}), 403

    data = request.get_json(silent=True) or {}
    ids_raw = data.get("assignment_ids") or []
    try:
        assignment_ids = [int(x) for x in ids_raw if x is not None]
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Format data tidak valid"}), 400

    if not assignment_ids:
        return jsonify({"success": False, "message": "Tidak ada penugasan dipilih"}), 400

    try:
        deleted_count = delete_staff_assignments_by_ids(assignment_ids)
        log_activity(
            user.get("id"),
            "DELETE",
            "STAFF_ASSIGNMENT",
            None,
            "Bulk delete assignments",
            {"count": deleted_count, "assignment_ids": assignment_ids},
        )
        return jsonify({"success": True, "deleted": deleted_count})
    except Exception as e:
        current_app.logger.exception("Error deleting assignments in batch")
        return jsonify({"success": False, "message": str(e)}), 500


@portal_bp.route("/admin/assignment-requests/<int:request_id>/approve", methods=["POST"])
@role_required("admin")
def admin_approve_assignment_request(request_id: int) -> Response:
    """Admin approves a coordinator-submitted assignment request."""
    user = current_user()
    from .queries import log_activity
    reviewer_note = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        reviewer_note = payload.get("reviewer_note")
    else:
        reviewer_note = request.form.get("reviewer_note")
    reviewer_note = reviewer_note.strip() if isinstance(reviewer_note, str) and reviewer_note.strip() else None

    req = update_assignment_request_status(
        request_id,
        "approved",
        reviewer_id=user["id"],
        reviewer_note=reviewer_note,
    )
    if not req:
        return jsonify({"success": False, "message": "Request tidak ditemukan"}), 404
    coordinator_info = _fetch_dashboard_user_summary(req["coordinator_id"]) if req.get("coordinator_id") else None
    period_info = get_period_by_id(req.get("period_id")) if req.get("period_id") else None
    try:
        assignment = assign_staff_to_school(req["staff_id"], req["school_id"], user["id"], req.get("note"))
        staff_info = _fetch_dashboard_user_summary(req["staff_id"])
        school = get_school_by_id(req["school_id"])
        request_details = {
            "status": "approved",
            "staff_id": req.get("staff_id"),
            "school_id": req.get("school_id"),
            "period_id": req.get("period_id"),
        }
        if reviewer_note:
            request_details["reviewer_note"] = reviewer_note
        if staff_info:
            request_details["staff_name"] = staff_info.get("full_name")
            request_details["staff_email"] = staff_info.get("email")
        if school:
            request_details["school_name"] = school.get("name")
            request_details["npsn"] = school.get("npsn")
        log_activity(
            user.get("id"),
            "UPDATE",
            "ASSIGNMENT_REQUEST",
            request_id,
            staff_info.get("full_name") if staff_info else f"Request {request_id}",
            request_details,
        )
        assignment_details = {
            "staff_id": req.get("staff_id"),
            "school_id": req.get("school_id"),
            "period_id": req.get("period_id"),
            "request_id": request_id,
        }
        if staff_info:
            assignment_details["staff_name"] = staff_info.get("full_name")
            assignment_details["staff_email"] = staff_info.get("email")
        if school:
            assignment_details["school_name"] = school.get("name")
            assignment_details["npsn"] = school.get("npsn")
        if req.get("note"):
            assignment_details["notes"] = req.get("note")
        log_activity(
            user.get("id"),
            "CREATE",
            "STAFF_ASSIGNMENT",
            assignment.get("id") if assignment else None,
            school.get("name") if school else f"School {req.get('school_id')}",
            assignment_details,
        )
        try:
            notify_assignment_request_status_update(
                request_id=request_id,
                coordinator_name=coordinator_info.get("full_name") if coordinator_info else None,
                staff_name=staff_info.get("full_name") if staff_info else None,
                school_name=school.get("name") if school else None,
                period_name=period_info.get("name") if period_info else None,
                status_label="✅ Disetujui",
                actor_name=user.get("full_name") or user.get("email"),
                actor_username=None,
                reviewer_note=reviewer_note,
            )
        except Exception:
            current_app.logger.exception("Gagal mengirim notifikasi Telegram status assignment request.")
        try:
            _notify_panbers_assignment_status_change(
                request_row=req,
                status="approved",
                actor=user,
                reviewer_note=reviewer_note,
                school_name=school.get("name") if school else None,
                staff_name=staff_info.get("full_name") if staff_info else None,
                coordinator_name=coordinator_info.get("full_name") if coordinator_info else None,
                period_name=period_info.get("name") if period_info else None,
            )
        except Exception:
            current_app.logger.exception("Gagal menyimpan notifikasi aplikasi status assignment request.")
    except Exception as exc:
        current_app.logger.exception("Error assigning after approval")
        return jsonify({"success": False, "message": str(exc)}), 500
    return jsonify({"success": True, "request": req})


@portal_bp.route("/admin/assignment-requests/<int:request_id>/reject", methods=["POST"])
@role_required("admin")
def admin_reject_assignment_request(request_id: int) -> Response:
    """Admin rejects a coordinator-submitted assignment request."""
    user = current_user()
    from .queries import log_activity
    reviewer_note = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        reviewer_note = payload.get("reviewer_note")
    else:
        reviewer_note = request.form.get("reviewer_note")
    reviewer_note = reviewer_note.strip() if isinstance(reviewer_note, str) and reviewer_note.strip() else None

    req = update_assignment_request_status(
        request_id,
        "rejected",
        reviewer_id=user["id"],
        reviewer_note=reviewer_note,
    )
    if not req:
        return jsonify({"success": False, "message": "Request tidak ditemukan"}), 404
    staff_info = _fetch_dashboard_user_summary(req["staff_id"])
    coordinator_info = _fetch_dashboard_user_summary(req["coordinator_id"]) if req.get("coordinator_id") else None
    period_info = get_period_by_id(req.get("period_id")) if req.get("period_id") else None
    school = get_school_by_id(req["school_id"])
    details = {
        "status": "rejected",
        "staff_id": req.get("staff_id"),
        "school_id": req.get("school_id"),
        "period_id": req.get("period_id"),
    }
    if reviewer_note:
        details["reviewer_note"] = reviewer_note
    if staff_info:
        details["staff_name"] = staff_info.get("full_name")
        details["staff_email"] = staff_info.get("email")
    if school:
        details["school_name"] = school.get("name")
        details["npsn"] = school.get("npsn")
    if req.get("note"):
        details["notes"] = req.get("note")
    log_activity(
        user.get("id"),
        "UPDATE",
        "ASSIGNMENT_REQUEST",
        request_id,
        staff_info.get("full_name") if staff_info else f"Request {request_id}",
        details,
    )
    try:
        notify_assignment_request_status_update(
            request_id=request_id,
            coordinator_name=coordinator_info.get("full_name") if coordinator_info else None,
            staff_name=staff_info.get("full_name") if staff_info else None,
            school_name=school.get("name") if school else None,
            period_name=period_info.get("name") if period_info else None,
            status_label="❌ Ditolak",
            actor_name=user.get("full_name") or user.get("email"),
            actor_username=None,
            reviewer_note=reviewer_note,
        )
    except Exception:
        current_app.logger.exception("Gagal mengirim notifikasi Telegram status assignment request.")
    try:
        _notify_panbers_assignment_status_change(
            request_row=req,
            status="rejected",
            actor=user,
            reviewer_note=reviewer_note,
            school_name=school.get("name") if school else None,
            staff_name=staff_info.get("full_name") if staff_info else None,
            coordinator_name=coordinator_info.get("full_name") if coordinator_info else None,
            period_name=period_info.get("name") if period_info else None,
        )
    except Exception:
        current_app.logger.exception("Gagal menyimpan notifikasi aplikasi status assignment request.")
    return jsonify({"success": True, "request": req})


@portal_bp.route("/admin/remove-assignment", methods=["POST"])
@role_required("admin")
def admin_remove_assignment() -> Response:
    """Admin removes a school assignment from a staff member."""
    user = current_user()
    from .queries import log_activity
    
    # Superadmin only
    if not can_assign_staff(user):
        return jsonify({"success": False, "message": "Tidak memiliki izin"}), 403
    
    staff_id = request.form.get("staff_id", type=int)
    school_id = request.form.get("school_id", type=int)
    
    if not staff_id or not school_id:
        return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    
    try:
        if remove_staff_school_assignment(staff_id, school_id):
            staff_info = _fetch_dashboard_user_summary(staff_id)
            school = get_school_by_id(school_id)
            details = {
                "staff_id": staff_id,
                "school_id": school_id,
            }
            if staff_info:
                details["staff_name"] = staff_info.get("full_name")
                details["staff_email"] = staff_info.get("email")
            if school:
                details["school_name"] = school.get("name")
                details["npsn"] = school.get("npsn")
            log_activity(
                user.get("id"),
                "DELETE",
                "STAFF_ASSIGNMENT",
                None,
                school.get("name") if school else f"School {school_id}",
                details,
            )
            flash("Penugasan berhasil dihapus.", "success")
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Gagal menghapus penugasan"}), 400
    except Exception as e:
        current_app.logger.exception("Error removing assignment")
        return jsonify({"success": False, "message": str(e)}), 500



@portal_bp.route("/admin/staff/<int:staff_id>/assigned-schools")
@role_required("admin")
def admin_staff_assigned_schools(staff_id: int) -> Response:
    """Admin page to view all schools assigned to a specific staff member."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, full_name, email, role, jabatan
            FROM dashboard_users
            WHERE id = %s AND role IN ('staff', 'coordinator')
            """,
            (staff_id,),
        )
        row = cur.fetchone()
    if not row:
        abort(404)

    staff = dict(row)
    assignments = get_staff_assigned_schools(staff_id)
    return render_template(
        "portal/admin/staff_assigned_schools.html",
        staff=staff,
        assignments=assignments,
    )


@portal_bp.route("/admin/staff/<int:staff_id>/assignments")
@role_required("admin")
def get_staff_assignments_api(staff_id: int) -> Response:
    """API endpoint to get assignments for a specific staff member."""
    try:
        assignments = get_staff_assigned_schools(staff_id)
        return jsonify({
            "success": True,
            "assignments": assignments
        })
    except Exception as e:
        current_app.logger.exception("Error fetching staff assignments")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@portal_bp.route("/coordinator/staff/<int:staff_id>/assignments")
@role_required("coordinator")
def coordinator_staff_assignments_api(staff_id: int) -> Response:
    """API endpoint for coordinators to view assignments within their team."""
    user = current_user()
    team, _, staff_ids = _get_coordinator_team_context(user.get("id"))
    if not team or staff_id not in staff_ids:
        return jsonify({"success": False, "message": "Tidak diizinkan"}), 403

    try:
        assignments = get_staff_assigned_schools(staff_id)
        return jsonify({
            "success": True,
            "assignments": assignments
        })
    except Exception as e:
        current_app.logger.exception("Error fetching coordinator staff assignments")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500



# Add permissions to template context globally
@portal_bp.context_processor
def inject_permissions():
    """Inject permission checks into all portal templates."""
    user = current_user()
    if not user:
        return {}

    # Keep session photo state in sync with DB so modal rules reflect latest admin changes.
    session_photo_path = user.get("profile_photo_path")
    latest_photo_path = session_photo_path
    try:
        latest_profile = get_dashboard_user_profile(int(user.get("id"))) or {}
        latest_photo_path = latest_profile.get("profile_photo_path")
    except Exception:
        current_app.logger.exception("Failed to sync profile photo state from DB")
    if latest_photo_path != session_photo_path:
        computed_photo_url = _build_profile_photo_url(latest_photo_path)
        user["profile_photo_path"] = latest_photo_path
        user["profile_photo_url"] = computed_photo_url
        session_user = session.get("user") or {}
        session_user["profile_photo_path"] = latest_photo_path
        session_user["profile_photo_url"] = computed_photo_url
        session["user"] = session_user
    elif session_photo_path and not user.get("profile_photo_url"):
        computed_photo_url = _build_profile_photo_url(session_photo_path)
        if computed_photo_url:
            user["profile_photo_url"] = computed_photo_url
            session_user = session.get("user") or {}
            session_user["profile_photo_url"] = computed_photo_url
            session["user"] = session_user
    
    from .permissions import get_permission_summary
    user_school = None
    user_area_name = None
    if user.get("role") == "sekolah":
        user_school = _fetch_user_school(user.get("id"))
    else:
        user_area_name = _fetch_user_kecamatan_name(user.get("id"))

    if user.get("role") == "sekolah":
        try:
            _dispatch_due_follow_up_reminders_for_user(user=user, school=user_school)
        except Exception:
            current_app.logger.exception("Gagal mengirim reminder tindak lanjut PANBERSS.")
    elif user.get("role") == "staff":
        try:
            _dispatch_due_follow_up_reminders_for_staff_user(user=user)
        except Exception:
            current_app.logger.exception("Gagal mengirim reminder verifikasi tindak lanjut PANBERSS.")

    area_contacts = _build_coordinator_contacts(user_school, area_name=user_area_name)
    admin_pending = {
        "pending_users": 0,
        "pending_assignment_requests": 0,
        "pending_team_member_requests": 0,
        "pending_reopen_requests": 0,
        "pending_guestbook": 0,
        "total": 0,
    }
    user_app_notifications = {
        "unread_count": 0,
        "total_count": 0,
    }
    follow_up_nav_badge_count = 0
    undo_window_seconds = PORTAL_UNDO_WINDOW_DEFAULT_SECONDS
    if user.get("role") == "admin":
        try:
            admin_pending = fetch_admin_pending_summary()
        except Exception:
            current_app.logger.exception("Failed to load admin pending summary")
    elif user.get("role") in {"staff", "coordinator", "sekolah"}:
        try:
            user_app_notifications = fetch_user_notification_summary(
                user_id=int(user.get("id")),
                categories=list(USER_APP_NOTIFICATION_CATEGORIES),
            )
        except Exception:
            user_app_notifications = {"unread_count": 0, "total_count": 0}
    if user.get("role") == "sekolah" and user_school:
        try:
            follow_up_nav_badge_count = count_room_follow_up_nav_badge_for_school(int(user_school.get("id") or 0))
        except Exception:
            current_app.logger.exception("Failed to load follow-up nav badge count")
            follow_up_nav_badge_count = 0
    elif user.get("role") == "staff":
        try:
            follow_up_nav_badge_count = count_room_follow_up_nav_badge_for_staff(int(user.get("id") or 0))
        except Exception:
            current_app.logger.exception("Failed to load staff follow-up nav badge count")
            follow_up_nav_badge_count = 0
    try:
        undo_window_seconds = fetch_portal_undo_window_seconds()
    except Exception:
        current_app.logger.exception("Failed to load portal undo window settings")
        undo_window_seconds = PORTAL_UNDO_WINDOW_DEFAULT_SECONDS

    require_profile_photo_upload = _needs_profile_photo_completion(user)

    admin_notification_items = []
    if user.get("role") == "admin" and admin_pending:
        from flask import url_for
        admin_notification_items = [
            {
                "href": url_for("portal.manage_users"),
                "title": "User baru",
                "subtitle": "Menunggu verifikasi akun",
                "count": admin_pending.get("pending_users", 0),
                "item_id": "adminPendingUsersItem",
                "count_id": "adminPendingUsersCount",
                "badge_class": "bg-warning text-dark",
            },
            {
                "href": url_for("portal.admin_manage_staff"),
                "title": "Permintaan penugasan",
                "subtitle": "Koordinator ajukan penugasan staff",
                "count": admin_pending.get("pending_assignment_requests", 0),
                "item_id": "adminPendingAssignmentItem",
                "count_id": "adminPendingAssignmentCount",
                "badge_class": "bg-info text-dark",
            },
            {
                "href": url_for("portal.manage_monev_teams"),
                "title": "Permintaan anggota tim",
                "subtitle": "Persetujuan anggota monev",
                "count": admin_pending.get("pending_team_member_requests", 0),
                "item_id": "adminPendingTeamItem",
                "count_id": "adminPendingTeamCount",
                "badge_class": "bg-primary",
            },
            {
                "href": url_for("portal.admin_reopen_requests"),
                "title": "Permintaan reopen",
                "subtitle": "Penilaian diajukan untuk dibuka",
                "count": admin_pending.get("pending_reopen_requests", 0),
                "item_id": "adminPendingReopenItem",
                "count_id": "adminPendingReopenCount",
                "badge_class": "bg-danger",
            },
            {
                "href": url_for("daftar_tamu.admin_validation"),
                "title": "Verifikasi daftar tamu",
                "subtitle": "Transaksi buku tamu menunggu validasi",
                "count": admin_pending.get("pending_guestbook", 0),
                "item_id": "adminPendingGuestbookItem",
                "count_id": "adminPendingGuestbookCount",
                "badge_class": "bg-success",
            },
            {
                "href": url_for("call_center.inbox"),
                "title": "Call Center",
                "subtitle": "Pesan masuk belum dibaca",
                "count": admin_pending.get("pending_call_center", 0),
                "item_id": "adminPendingCCItem",
                "count_id": "adminPendingCCCount",
                "badge_class": "text-bg-danger",
            },
        ]

    return {
        'permissions': get_permission_summary(user),
        'is_superadmin': is_superadmin(user),
        'can_access_aska': can_access_aska(user),
        'user_school': user_school,
        'area_contacts': area_contacts,
        'admin_pending': admin_pending,
        'admin_notification_items': admin_notification_items,
        'user_app_notifications': user_app_notifications,
        'follow_up_nav_badge_count': follow_up_nav_badge_count,
        'undo_window_seconds': undo_window_seconds,
        'undo_window_min_seconds': PORTAL_UNDO_WINDOW_MIN_SECONDS,
        'undo_window_max_seconds': PORTAL_UNDO_WINDOW_MAX_SECONDS,
        'require_profile_photo_upload': require_profile_photo_upload,
    }



# ===== Coordinator Dashboard Routes =====

@portal_bp.route("/coordinator/dashboard")
@role_required("coordinator")
def coordinator_dashboard() -> Response:
    """Coordinator dashboard - view team progress."""
    from dashboard.queries import get_monev_teams, get_team_members
    
    user = current_user()
    user_id = user.get("id")
    
    # Find the team where current user is coordinator
    all_teams = get_monev_teams()
    my_team = None
    
    for team in all_teams:
        if team.get('coordinator_id') == user_id:
            my_team = team
            break
    
    if not my_team:
        # Show empty dashboard instead of redirecting to avoid loop
        return render_template(
            "portal/coordinator/dashboard.html",
            section={"name": "Belum Ditugaskan", "description": "Anda belum menjadi koordinator tim manapun."},
            team_members=[],
            stats={"total_staff": 0, "total_assessments": 0, "completed_assessments": 0, "schools_assessed": 0},
            user=user,
        )
    
    # Get team members
    team_members_data = get_team_members(my_team['id'])
    
    # Build team stats (basic)
    stats = {
        "total_staff": len(team_members_data),
        "total_assessments": 0,
        "completed_assessments": 0,
        "schools_assessed": 0,
    }
    
    # Create a section-like object for template compatibility
    team_as_section = {
        "name": my_team.get('name') or my_team.get('kecamatan_name') or f"Tim ID {my_team['id']}",
        "description": f"Tim Monev ({my_team.get('team_type', 'kecamatan')})",
    }
    
    return render_template(
        "portal/coordinator/dashboard.html",
        section=team_as_section,
        team_members=team_members_data,
        stats=stats,
        user=user,
    )


@portal_bp.route("/coordinator/team")
@role_required("coordinator")
def coordinator_team() -> Response:
    """Redirect legacy Kelola Tim to Tim Saya (single page experience)."""
    return redirect(url_for("portal.view_my_team"))


@portal_bp.route("/coordinator/team/request-member", methods=["POST"])
@role_required("coordinator")
def coordinator_request_member() -> Response:
    """Coordinator submits a member addition request for admin approval."""
    from dashboard.queries import get_monev_teams

    user = current_user()
    user_id = user.get("id")
    team_id = request.form.get("team_id", type=int)
    staff_id = request.form.get("staff_id", type=int)
    note = (request.form.get("note") or "").strip()

    coordinator_teams = [
        team for team in get_monev_teams()
        if team.get("coordinator_id") == user_id
    ]
    if team_id is not None:
        my_team = next((team for team in coordinator_teams if team.get("id") == team_id), None)
    else:
        my_team = coordinator_teams[0] if coordinator_teams else None

    if not my_team:
        flash("Anda belum memiliki tim.", "warning")
        return redirect(url_for("portal.view_my_team"))

    if not staff_id:
        flash("Pilih staff yang ingin diajukan.", "warning")
        return redirect(url_for("portal.view_my_team", _anchor=f"team-{my_team['id']}"))

    result = create_team_member_request(
        team_id=my_team["id"],
        staff_id=staff_id,
        requested_by=user_id,
        note=note or None,
    )
    
    status = result.get("status")
    if status == "already_member":
        flash("Staff sudah menjadi anggota tim.", "info")
    elif status == "pending":
        flash("Permintaan serupa masih menunggu persetujuan admin.", "info")
    elif status == "created":
        created_request = result.get("request") or {}
        created_request_id = created_request.get("id")
        if created_request_id is not None:
            try:
                staff_info = _fetch_dashboard_user_summary(staff_id)
                notify_team_member_request(
                    request_id=int(created_request_id),
                    team_name=my_team.get("name") or my_team.get("kecamatan_name"),
                    staff_name=staff_info.get("full_name") if staff_info else None,
                    requested_by_name=user.get("full_name") or user.get("email"),
                    note=note,
                )
            except Exception:
                current_app.logger.exception("Gagal mengirim notifikasi Telegram permintaan anggota tim.")
        flash("Permintaan tambah anggota dikirim ke admin untuk verifikasi.", "success")
    else:
        flash("Gagal mengirim permintaan.", "danger")

    return redirect(url_for("portal.view_my_team", _anchor=f"team-{my_team['id']}"))


# =====================================================
# User Profile (admin/coordinator/staff)
# =====================================================

@portal_bp.route("/profile/photo", methods=["POST"])
@role_required("staff", "coordinator")
def upload_profile_photo() -> Response:
    """Upload/update profile photo for staff and coordinator users."""
    user = current_user()
    if not user:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )
    file_storage = request.files.get("photo")
    if not file_storage or not file_storage.filename:
        message = "Pilih foto profil terlebih dahulu."
        if wants_json:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "warning")
        return redirect(url_for("portal.user_profile_settings"))

    if not _allowed_file(file_storage.filename):
        message = "Format foto tidak didukung. Gunakan JPG, JPEG, PNG, atau WEBP."
        if wants_json:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "warning")
        return redirect(url_for("portal.user_profile_settings"))

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    upload_dir = UPLOAD_FOLDER / "profile"
    upload_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(JAKARTA_TZ).strftime("%Y%m%d%H%M%S")
    generated_name = f"user_{int(user['id'])}_{timestamp}_{uuid.uuid4().hex[:8]}.{ext}"
    abs_path = upload_dir / generated_name
    rel_path = f"profile/{generated_name}"
    db_photo_path = f"uploads/portal/{rel_path}"

    previous_profile = get_dashboard_user_profile(int(user["id"])) or {}
    previous_rel = _normalize_photo_rel_path(previous_profile.get("profile_photo_path"))

    try:
        file_storage.save(abs_path)
        updated = update_dashboard_user_profile_photo(
            user_id=int(user["id"]),
            photo_path=db_photo_path,
        )
        if not updated:
            raise RuntimeError("Gagal menyimpan foto profil ke database.")

        if previous_rel and previous_rel.startswith("profile/") and previous_rel != rel_path:
            old_abs_path = UPLOAD_FOLDER / previous_rel
            if old_abs_path.exists() and old_abs_path.is_file():
                try:
                    old_abs_path.unlink()
                except OSError:
                    current_app.logger.warning(
                        "Gagal menghapus foto profil lama: %s",
                        old_abs_path.as_posix(),
                    )

        session_user = session.get("user") or {}
        session_user["profile_photo_path"] = db_photo_path
        session_user["profile_photo_url"] = url_for("portal.uploaded_file", filename=rel_path)
        session["user"] = session_user
    except Exception as exc:
        if abs_path.exists():
            try:
                abs_path.unlink()
            except OSError:
                pass
        current_app.logger.exception("Gagal mengunggah foto profil pengguna.")
        message = f"Gagal mengunggah foto profil: {exc}"
        if wants_json:
            return jsonify({"success": False, "message": message}), 500
        flash(message, "danger")
        return redirect(url_for("portal.user_profile_settings"))

    success_message = "Foto profil berhasil diperbarui."
    success_redirect_url = _resolve_profile_upload_redirect(url_for("portal.home"))
    if wants_json:
        return jsonify(
            {
                "success": True,
                "message": success_message,
                "photo_url": url_for("portal.uploaded_file", filename=rel_path),
                "redirect_url": success_redirect_url,
            }
        )
    flash(success_message, "success")
    return redirect(success_redirect_url)


_HOSPITALITY_DATE_MODE_KEY = "hospitality_date_mode"


@portal_bp.route("/settings/hospitality-date-mode", methods=["POST"])
@role_required("admin")
def set_hospitality_date_mode() -> Response:
    """Toggle the hospitality date display mode (original vs edit) stored in session (admin only)."""
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
    )
    raw_mode = (request.get_json(silent=True) or {}).get("mode") if request.is_json else request.form.get("mode")
    mode = str(raw_mode or "edit").strip().lower()
    if mode not in {"original", "edit"}:
        mode = "edit"
    session[_HOSPITALITY_DATE_MODE_KEY] = mode
    if wants_json:
        return jsonify({"success": True, "mode": mode})
    flash(
        "Mode tanggal Hospitality: " + ("Tanggal Edit" if mode == "edit" else "Tanggal Original"),
        "success",
    )
    return redirect(url_for("portal.user_profile_settings"))


@portal_bp.route("/profile", methods=["GET", "POST"])
@role_required("admin", "coordinator", "staff")
def user_profile_settings() -> Response:
    """Allow dashboard users to edit basic profile info and change password."""
    user = current_user()
    profile = get_dashboard_user_profile(user["id"])
    if not profile:
        flash("Profil tidak ditemukan.", "danger")
        return redirect(url_for("portal.home"))
    profile_view = {k: v for k, v in profile.items() if k != "password_hash"}
    profile_view["profile_photo_url"] = _build_profile_photo_url(profile.get("profile_photo_path"))

    if request.method == "POST":
        form_type = (request.form.get("form_type") or "profile").strip().lower()
        # Default to existing profile data so password-only form doesn't blank fields.
        full_name = (request.form.get("full_name") or profile.get("full_name") or "").strip()
        email = (request.form.get("email") or profile.get("email") or "").strip().lower()
        whatsapp = (request.form.get("whatsapp_number") or profile.get("whatsapp_number") or "").strip() or None
        nip = (request.form.get("nip") or profile.get("nip") or "").strip() or None
        nrk = (request.form.get("nrk") or profile.get("nrk") or "").strip() or None
        jabatan = (request.form.get("jabatan") or profile.get("jabatan") or "").strip() or None

        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        errors = []
        if form_type == "profile":
            if not full_name:
                errors.append("Nama wajib diisi.")
            if not email:
                errors.append("Email wajib diisi.")
        else:
            # Still ensure existing essential data is present
            if not full_name:
                errors.append("Profil tidak valid: nama kosong.")
            if not email:
                errors.append("Profil tidak valid: email kosong.")

        # Password validation only when changing password
        if form_type == "password" or new_password or confirm_password or current_password:
            if not profile.get("password_hash"):
                errors.append("Akun ini belum memiliki password, hubungi admin.")
            elif not current_password:
                errors.append("Masukkan password saat ini.")
            elif not check_password_hash(profile["password_hash"], current_password):
                errors.append("Password saat ini salah.")
            if not new_password:
                errors.append("Password baru wajib diisi.")
            if not confirm_password:
                errors.append("Konfirmasi password baru wajib diisi.")
            if new_password and confirm_password and new_password != confirm_password:
                errors.append("Password baru dan konfirmasi tidak sama.")
            if new_password and len(new_password) < 8:
                errors.append("Password baru minimal 8 karakter.")

        if errors:
            for msg in errors:
                flash(msg, "danger")
        else:
            pw_hash = (
                generate_password_hash(new_password, method="pbkdf2:sha256", salt_length=12)
                if new_password
                else None
            )
            try:
                update_dashboard_user_profile(
                    user_id=user["id"],
                    full_name=full_name,
                    email=email,
                    whatsapp_number=whatsapp,
                    nip=nip,
                    nrk=nrk,
                    jabatan=jabatan,
                    password_hash=pw_hash,
                )
                # Refresh session data
                session_user = session.get("user", {})
                session_user["full_name"] = full_name
                session_user["email"] = email
                session["user"] = session_user
                flash("Profil berhasil diperbarui.", "success")
                profile = get_dashboard_user_profile(user["id"])
                profile_view = {k: v for k, v in profile.items() if k != "password_hash"}
                profile_view["profile_photo_url"] = _build_profile_photo_url(profile.get("profile_photo_path"))
            except Exception as exc:
                current_app.logger.error(f"Gagal memperbarui profil: {exc}")
                flash("Gagal memperbarui profil.", "danger")

    hospitality_date_mode = session.get(_HOSPITALITY_DATE_MODE_KEY, "edit")
    return render_template(
        "portal/profile.html",
        profile=profile_view,
        hospitality_date_mode=hospitality_date_mode,
    )


# =====================================================
# User Management & Monev Teams (Portal Integration)
# =====================================================

def _preview_admin_actor() -> dict | None:
    """Return admin actor from active session or preview session."""
    preview_admin = session.get(_PREVIEW_ADMIN_SESSION_KEY)
    if isinstance(preview_admin, dict) and preview_admin.get("role") == "admin":
        return preview_admin
    user = current_user()
    if isinstance(user, dict) and user.get("role") == "admin":
        return user
    return None


def _preview_access_required(view):
    """Allow access for logged-in admin and active preview-admin sessions."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        actor = _preview_admin_actor()
        if actor:
            return view(*args, **kwargs)
        if not current_user():
            flash("Silakan login terlebih dahulu.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        flash("Halaman ini hanya untuk admin.", "danger")
        return redirect(url_for("portal.home"))
    return wrapper


def _normalize_preview_app(raw: str | None) -> str:
    app = (raw or "").strip().lower()
    if app in {"guestbook", "daftar_tamu", "daftar-tamu"}:
        return "daftar_tamu"
    return "portal"


def _preview_home_fallback_url() -> str:
    return url_for("main.admin_select_role")


def _sanitize_preview_return_url(raw_url: str | None) -> str | None:
    if raw_url is None:
        return None
    value = str(raw_url).strip()
    if not value:
        return None

    parsed = urlparse(value)
    # Allow relative URLs and same-origin absolute URLs only.
    if parsed.netloc:
        host = urlparse(request.host_url).netloc
        if parsed.netloc != host:
            return None
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            return None

    path = (parsed.path or "").strip()
    if not path.startswith("/") or path.startswith("//"):
        return None

    # Prevent redirect loop back into preview workspace/stop endpoint.
    if path == url_for("portal.preview_accounts") or path.startswith("/portal/preview/"):
        return None

    return f"{path}?{parsed.query}" if parsed.query else path


def _build_preview_entry_url(*, role: str, app: str) -> str:
    role_value = (role or "").strip().lower()
    app_value = _normalize_preview_app(app)
    if app_value == "daftar_tamu":
        if role_value == "sekolah":
            return url_for("daftar_tamu.sekolah_guestbook")
        if role_value == "coordinator":
            return url_for("daftar_tamu.coordinator_dashboard")
        return url_for("daftar_tamu.user_guestbook_history")
    if role_value == "sekolah":
        return url_for("portal.sekolah_home")
    return url_for("portal.home")


def _build_session_user_payload(row: dict) -> dict:
    raw_assigned_class = row.get("assigned_class_id")
    assigned_class_id = None
    if raw_assigned_class is not None:
        try:
            assigned_class_id = int(raw_assigned_class)
        except (TypeError, ValueError):
            assigned_class_id = None
    profile_photo_path = row.get("profile_photo_path")
    profile_photo_url = _build_profile_photo_url(profile_photo_path)
    return {
        "id": row.get("id"),
        "email": (row.get("email") or "").strip().lower(),
        "full_name": row.get("full_name"),
        "role": row.get("role"),
        "profile_photo_path": profile_photo_path,
        "profile_photo_url": profile_photo_url,
        "no_tester_enabled": bool(row.get("no_tester_enabled")),
        "assigned_class_id": assigned_class_id,
    }


def _serialize_preview_target(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "full_name": row.get("full_name"),
        "role": row.get("role"),
        "account_status": row.get("account_status"),
    }


def _list_preview_accounts(pinned_ids: list[int] | None = None) -> list[dict]:
    pinned_ids = pinned_ids or []
    pinned_set = set()
    for value in pinned_ids:
        try:
            pinned_set.add(int(value))
        except (TypeError, ValueError):
            continue
    rows = []
    for index, user in enumerate(list_dashboard_users()):
        role = (user.get("role") or "").strip().lower()
        if role not in _PREVIEW_ALLOWED_ROLES:
            continue
        account_status = (user.get("account_status") or "").strip().lower()
        if account_status != "approved":
            continue
        if user.get("merged_to"):
            continue
        row = dict(user)
        row["profile_photo_url"] = _build_profile_photo_url(row.get("profile_photo_path"))
        row["preview_index"] = index
        try:
            row_id = int(row.get("id") or 0)
        except (TypeError, ValueError):
            row_id = 0
        row["is_pinned"] = row_id in pinned_set
        rows.append(row)
    if not pinned_set:
        return rows
    pinned_rows = [row for row in rows if row.get("is_pinned")]
    unpinned_rows = [row for row in rows if not row.get("is_pinned")]
    return pinned_rows + unpinned_rows


def _find_preview_target(user_id: int) -> dict | None:
    for row in _list_preview_accounts():
        if int(row.get("id") or 0) == int(user_id):
            return row
    return None


@portal_bp.route("/settings/users", methods=["GET", "POST"])
@_preview_access_required
def manage_users() -> Response:
    """Manage dashboard users from Portal app."""
    from dashboard.user_management import handle_manage_users

    return handle_manage_users(
        actor=_preview_admin_actor(),
        base_template="portal/base_portal.html",
        read_only=_is_preview_read_only_session(),
    )


@portal_bp.route("/settings/preview-akun", methods=["GET"])
@_preview_access_required
def preview_accounts() -> Response:
    """Admin preview workspace for target accounts."""
    actor = _preview_admin_actor()
    pinned_ids: list[int] = []
    if actor and actor.get("id"):
        try:
            pinned_ids = list_preview_pins(int(actor["id"]))
        except (TypeError, ValueError):
            pinned_ids = []
    preview_users = _list_preview_accounts(pinned_ids)
    selected_target = session.get(_PREVIEW_TARGET_SESSION_KEY)
    selected_app = _normalize_preview_app(session.get(_PREVIEW_APP_SESSION_KEY))
    preview_url = None
    if isinstance(selected_target, dict):
        selected_id = int(selected_target.get("id") or 0)
        still_exists = any(int(user.get("id") or 0) == selected_id for user in preview_users)
        if still_exists:
            preview_url = _build_preview_entry_url(
                role=(selected_target.get("role") or ""),
                app=selected_app,
            )
        else:
            session.pop(_PREVIEW_TARGET_SESSION_KEY, None)
            session.pop(_PREVIEW_APP_SESSION_KEY, None)
            selected_target = None

    # Keep return destination so "Keluar Preview" can go back to previous page.
    referrer_return_url = _sanitize_preview_return_url(request.referrer)
    stored_return_url = _sanitize_preview_return_url(session.get(_PREVIEW_RETURN_URL_SESSION_KEY))
    preview_return_url = referrer_return_url or stored_return_url or _preview_home_fallback_url()
    session[_PREVIEW_RETURN_URL_SESSION_KEY] = preview_return_url

    return render_template(
        "portal/admin/preview_workspace.html",
        preview_users=preview_users,
        preview_pinned_ids=pinned_ids,
        preview_target=selected_target,
        preview_selected_app=selected_app,
        preview_url=preview_url,
        preview_return_url=preview_return_url,
    )


@portal_bp.route("/preview/start/<int:user_id>", methods=["POST"])
@_preview_access_required
def preview_start(user_id: int) -> Response:
    """Activate preview mode as selected target user."""
    target = _find_preview_target(user_id)
    if not target:
        return jsonify({"success": False, "message": "Akun target tidak ditemukan."}), 404

    role = (target.get("role") or "").strip().lower()
    if role not in _PREVIEW_ALLOWED_ROLES:
        return jsonify({"success": False, "message": "Role akun tidak didukung untuk preview."}), 400

    actor = _preview_admin_actor()
    if not actor:
        return jsonify({"success": False, "message": "Hanya admin yang dapat memulai preview."}), 403

    session[_PREVIEW_ADMIN_SESSION_KEY] = actor
    session["user"] = _build_session_user_payload(target)
    session[_PREVIEW_TARGET_SESSION_KEY] = _serialize_preview_target(target)

    app_name = _normalize_preview_app(request.form.get("app") or request.args.get("app"))
    session[_PREVIEW_APP_SESSION_KEY] = app_name
    preview_url = _build_preview_entry_url(role=role, app=app_name)

    return jsonify(
        {
            "success": True,
            "preview_url": preview_url,
            "target": session.get(_PREVIEW_TARGET_SESSION_KEY),
            "app": app_name,
        }
    )


@portal_bp.route("/settings/preview-akun/pin/<int:user_id>", methods=["POST"])
@_preview_access_required
def preview_pin(user_id: int) -> Response:
    """Pin/unpin preview target accounts per admin."""
    actor = _preview_admin_actor()
    if not actor or not actor.get("id"):
        return jsonify({"success": False, "message": "Hanya admin yang dapat menyematkan akun."}), 403

    target = _find_preview_target(user_id)
    if not target:
        return jsonify({"success": False, "message": "Akun target tidak ditemukan."}), 404

    try:
        admin_id = int(actor["id"])
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Admin tidak valid."}), 400

    action = (request.form.get("action") or "").strip().lower()
    pinned = False
    if action == "pin":
        add_preview_pin(admin_id, user_id)
        pinned = True
    elif action == "unpin":
        remove_preview_pin(admin_id, user_id)
        pinned = False
    else:
        if is_preview_pin(admin_id, user_id):
            remove_preview_pin(admin_id, user_id)
            pinned = False
        else:
            add_preview_pin(admin_id, user_id)
            pinned = True

    return jsonify({"success": True, "user_id": user_id, "pinned": pinned})


@portal_bp.route("/preview/stop")
@_preview_access_required
def preview_stop() -> Response:
    """Stop preview mode and restore original admin session."""
    stored_return_url = _sanitize_preview_return_url(session.get(_PREVIEW_RETURN_URL_SESSION_KEY))
    admin_session_user = session.get(_PREVIEW_ADMIN_SESSION_KEY)
    if isinstance(admin_session_user, dict) and admin_session_user.get("role") == "admin":
        session["user"] = admin_session_user
        flash("Mode preview dihentikan. Anda kembali ke akun admin.", "info")

    session.pop(_PREVIEW_ADMIN_SESSION_KEY, None)
    session.pop(_PREVIEW_TARGET_SESSION_KEY, None)
    session.pop(_PREVIEW_APP_SESSION_KEY, None)
    session.pop(_PREVIEW_RETURN_URL_SESSION_KEY, None)

    next_url = (
        _sanitize_preview_return_url(request.args.get("next"))
        or stored_return_url
        or _preview_home_fallback_url()
    )
    return redirect(next_url)


@portal_bp.route("/settings/monev-teams", methods=["GET", "POST"])
@role_required("admin")
def manage_monev_teams() -> Response:
    """Manage monev teams from Portal app."""
    from dashboard.queries import (
        get_monev_teams,
        get_team_members,
        update_team_coordinator,
        add_team_member,
        remove_team_member,
        get_available_staff,
        create_monev_team,
        delete_monev_team,
        list_team_member_requests,
        update_team_member_request_status,
        get_team_member_request,
    )
    from dashboard.portal.queries import list_kecamatan
    from .queries import log_activity, fetch_activity_logs
    
    if request.method == "POST":
        action = request.form.get("action")
        actor_id = current_user().get("id") if current_user() else None
        wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        
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
                        team_info = _fetch_monev_team(team_id)
                        details = {"team_type": team_type}
                        if kecamatan_id is not None:
                            details["kecamatan_id"] = kecamatan_id
                        if team_info and team_info.get("kecamatan_name"):
                            details["kecamatan_name"] = team_info.get("kecamatan_name")
                        log_activity(
                            actor_id,
                            "CREATE",
                            "MONEV_TEAM",
                            team_id,
                            team_info.get("name") if team_info else name,
                            details,
                        )
                        flash(f"Tim '{name}' berhasil dibuat.", "success")
                    else:
                        flash("Gagal membuat tim.", "danger")
                        
            elif action == "delete_team":
                team_id = int(request.form.get("team_id"))
                team_name = request.form.get("team_name", "")
                team_info = _fetch_monev_team(team_id)
                
                if delete_monev_team(team_id):
                    details = {}
                    if team_info:
                        if team_info.get("team_type"):
                            details["team_type"] = team_info.get("team_type")
                        if team_info.get("kecamatan_name"):
                            details["kecamatan_name"] = team_info.get("kecamatan_name")
                    log_activity(
                        actor_id,
                        "DELETE",
                        "MONEV_TEAM",
                        team_id,
                        team_info.get("name") if team_info else team_name,
                        details or None,
                    )
                    flash(f"Tim '{team_name}' berhasil dihapus.", "success")
                else:
                    flash("Gagal menghapus tim.", "danger")
                    
            elif action == "update_coordinator":
                team_id = int(request.form.get("team_id"))
                coordinator_id = request.form.get("coordinator_id")
                coordinator_id = int(coordinator_id) if coordinator_id else None
                
                if update_team_coordinator(team_id, coordinator_id):
                    team_info = _fetch_monev_team(team_id)
                    coord_info = (
                        _fetch_dashboard_user_summary(coordinator_id) if coordinator_id else None
                    )
                    details = {}
                    if coordinator_id is not None:
                        details["coordinator_id"] = coordinator_id
                    if coord_info:
                        details["coordinator_name"] = coord_info.get("full_name")
                        details["coordinator_email"] = coord_info.get("email")
                    if team_info:
                        details["team_type"] = team_info.get("team_type")
                        if team_info.get("kecamatan_name"):
                            details["kecamatan_name"] = team_info.get("kecamatan_name")
                    log_activity(
                        actor_id,
                        "UPDATE",
                        "MONEV_TEAM",
                        team_id,
                        team_info.get("name") if team_info else f"Team {team_id}",
                        details or None,
                    )
                    flash("Koordinator berhasil diperbarui.", "success")
                else:
                    flash("Gagal memperbarui koordinator.", "danger")
                    
            elif action == "add_member":
                team_id = int(request.form.get("team_id"))
                staff_id = int(request.form.get("staff_id"))
                admin_id = current_user().get("id") if current_user() else None
                
                if add_team_member(team_id, staff_id, admin_id):
                    team_info = _fetch_monev_team(team_id)
                    staff_info = _fetch_dashboard_user_summary(staff_id)
                    member_info = _fetch_monev_member_by_pair(team_id, staff_id)
                    member_id = member_info.get("id") if member_info else None
                    details = {"team_id": team_id, "staff_id": staff_id}
                    if member_id is not None:
                        details["member_id"] = member_id
                    if team_info and team_info.get("name"):
                        details["team_name"] = team_info.get("name")
                    if staff_info:
                        details["staff_name"] = staff_info.get("full_name")
                        details["staff_email"] = staff_info.get("email")
                    log_activity(
                        actor_id,
                        "CREATE",
                        "MONEV_TEAM_MEMBER",
                        member_id,
                        staff_info.get("full_name") if staff_info else f"Staff {staff_id}",
                        details,
                    )
                    flash("Anggota berhasil ditambahkan.", "success")
                else:
                    flash("Anggota sudah ada dalam tim atau gagal ditambahkan.", "warning")
                    
            elif action == "remove_member":
                member_id = int(request.form.get("member_id"))
                member_info = _fetch_monev_member(member_id)
                team_info = _fetch_monev_team(member_info["team_id"]) if member_info else None
                staff_info = (
                    _fetch_dashboard_user_summary(member_info["staff_id"]) if member_info else None
                )
                
                if remove_team_member(member_id):
                    details = {}
                    details["member_id"] = member_id
                    if member_info:
                        details["team_id"] = member_info.get("team_id")
                        details["staff_id"] = member_info.get("staff_id")
                    if team_info and team_info.get("name"):
                        details["team_name"] = team_info.get("name")
                    if staff_info:
                        details["staff_name"] = staff_info.get("full_name")
                        details["staff_email"] = staff_info.get("email")
                    log_activity(
                        actor_id,
                        "DELETE",
                        "MONEV_TEAM_MEMBER",
                        member_id,
                        staff_info.get("full_name") if staff_info else f"Member {member_id}",
                        details or None,
                    )
                    flash("Anggota berhasil dihapus dari tim.", "success")
                else:
                    flash("Gagal menghapus anggota.", "danger")
            
            elif action == "approve_request":
                request_id = int(request.form.get("request_id"))
                reviewer_note = (request.form.get("reviewer_note") or "").strip() or None
                admin_id = current_user().get("id") if current_user() else None
                req = get_team_member_request(request_id)
                if not req:
                    if wants_json:
                        return jsonify({"success": False, "message": "Permintaan tidak ditemukan."}), 404
                    flash("Permintaan tidak ditemukan.", "danger")
                else:
                    updated_req = update_team_member_request_status(
                        request_id,
                        "approved",
                        admin_id,
                        reviewer_note=reviewer_note,
                    )
                    if updated_req:
                        details = {
                            "status": "approved",
                            "team_id": req.get("team_id"),
                            "team_name": req.get("team_name"),
                            "staff_id": req.get("staff_id"),
                            "staff_name": req.get("staff_name"),
                            "requested_by": req.get("requested_by_name"),
                        }
                        if reviewer_note:
                            details["reviewer_note"] = reviewer_note
                        log_activity(
                            actor_id,
                            "UPDATE",
                            "MONEV_MEMBER_REQUEST",
                            request_id,
                            req.get("staff_name") or req.get("team_name"),
                            details,
                        )
                        try:
                            actor = current_user() or {}
                            notify_team_member_request_status_update(
                                request_id=request_id,
                                team_name=req.get("team_name"),
                                staff_name=req.get("staff_name"),
                                requested_by_name=req.get("requested_by_name"),
                                status_label="✅ Disetujui",
                                actor_name=actor.get("full_name") or actor.get("email"),
                                actor_username=None,
                                reviewer_note=reviewer_note,
                            )
                        except Exception:
                            current_app.logger.exception(
                                "Gagal mengirim notifikasi Telegram status permintaan anggota tim."
                            )
                        try:
                            _notify_panbers_team_member_request_status_change(
                                request_row=req,
                                status="approved",
                                actor=current_user(),
                                reviewer_note=reviewer_note,
                            )
                        except Exception:
                            current_app.logger.exception(
                                "Gagal menyimpan notifikasi aplikasi status permintaan anggota tim."
                            )
                    added = add_team_member(req["team_id"], req["staff_id"], admin_id)
                    if added:
                        member_info = _fetch_monev_member_by_pair(req["team_id"], req["staff_id"])
                        member_id = member_info.get("id") if member_info else None
                        log_activity(
                            actor_id,
                            "CREATE",
                            "MONEV_TEAM_MEMBER",
                            member_id,
                            req.get("staff_name"),
                            {
                                "team_id": req.get("team_id"),
                                "team_name": req.get("team_name"),
                                "staff_id": req.get("staff_id"),
                                "staff_name": req.get("staff_name"),
                                "member_id": member_id,
                            },
                        )
                    if wants_json:
                        status_code = 200 if updated_req else 400
                        return jsonify(
                            {
                                "success": bool(updated_req),
                                "request_id": request_id,
                                "status": "approved",
                            }
                        ), status_code
                    flash(f"Permintaan anggota untuk {req.get('staff_name') or 'staff'} disetujui.", "success")
            
            elif action == "reject_request":
                request_id = int(request.form.get("request_id"))
                reviewer_note = (request.form.get("reviewer_note") or "").strip() or None
                admin_id = current_user().get("id") if current_user() else None
                req = get_team_member_request(request_id)
                if not req:
                    if wants_json:
                        return jsonify({"success": False, "message": "Permintaan tidak ditemukan."}), 404
                    flash("Permintaan tidak ditemukan.", "danger")
                else:
                    updated_req = update_team_member_request_status(
                        request_id,
                        "rejected",
                        admin_id,
                        reviewer_note=reviewer_note,
                    )
                    if updated_req:
                        details = {
                            "status": "rejected",
                            "team_id": req.get("team_id"),
                            "team_name": req.get("team_name"),
                            "staff_id": req.get("staff_id"),
                            "staff_name": req.get("staff_name"),
                            "requested_by": req.get("requested_by_name"),
                        }
                        if reviewer_note:
                            details["reviewer_note"] = reviewer_note
                        log_activity(
                            actor_id,
                            "UPDATE",
                            "MONEV_MEMBER_REQUEST",
                            request_id,
                            req.get("staff_name") or req.get("team_name"),
                            details,
                        )
                        try:
                            actor = current_user() or {}
                            notify_team_member_request_status_update(
                                request_id=request_id,
                                team_name=req.get("team_name"),
                                staff_name=req.get("staff_name"),
                                requested_by_name=req.get("requested_by_name"),
                                status_label="❌ Ditolak",
                                actor_name=actor.get("full_name") or actor.get("email"),
                                actor_username=None,
                                reviewer_note=reviewer_note,
                            )
                        except Exception:
                            current_app.logger.exception(
                                "Gagal mengirim notifikasi Telegram status permintaan anggota tim."
                            )
                        try:
                            _notify_panbers_team_member_request_status_change(
                                request_row=req,
                                status="rejected",
                                actor=current_user(),
                                reviewer_note=reviewer_note,
                            )
                        except Exception:
                            current_app.logger.exception(
                                "Gagal menyimpan notifikasi aplikasi status permintaan anggota tim."
                            )
                    if wants_json:
                        status_code = 200 if updated_req else 400
                        return jsonify(
                            {
                                "success": bool(updated_req),
                                "request_id": request_id,
                                "status": "rejected",
                            }
                        ), status_code
                    flash(f"Permintaan anggota untuk {req.get('staff_name') or 'staff'} ditolak.", "info")
                    
        except Exception as exc:
            current_app.logger.error(f"Error managing monev team: {exc}")
            if wants_json:
                return jsonify({"success": False, "message": str(exc)}), 500
            flash(f"Terjadi kesalahan: {exc}", "danger")
    
    # GET: Fetch teams by type and enrich with members
    kasi_teams = get_monev_teams(team_type='kasi')
    for team in kasi_teams:
        team['members'] = get_team_members(team['id'])
    
    kecamatan_teams = get_monev_teams(team_type='kecamatan')
    for team in kecamatan_teams:
        team['members'] = get_team_members(team['id'])
    
    custom_teams = get_monev_teams(team_type='custom')
    for team in custom_teams:
        team['members'] = get_team_members(team['id'])

    # Hitung anggota + koordinator per tim
    def _with_counts(teams: list[dict]) -> list[dict]:
        for t in teams:
            member_count = len(t.get("members") or [])
            t["member_count_with_coord"] = member_count + (1 if t.get("coordinator_id") else 0)
        return teams

    kasi_teams = _with_counts(kasi_teams)
    kecamatan_teams = _with_counts(kecamatan_teams)
    custom_teams = _with_counts(custom_teams)

    # Dedup Kasi teams by (slugged name + coordinator), keep the one with most members (fallback to highest id)
    def _slug(name: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())

    deduped_kasi: dict[tuple[str, int | None], dict] = {}
    for team in kasi_teams:
        slug = _slug(team.get("name"))
        key = (slug, team.get("coordinator_id"))
        current = deduped_kasi.get(key)
        if not current:
            deduped_kasi[key] = team
            continue
        curr_count = current.get("member_count_with_coord", 0)
        new_count = team.get("member_count_with_coord", 0)
        if new_count > curr_count or (new_count == curr_count and team.get("id", 0) > current.get("id", 0)):
            deduped_kasi[key] = team
    kasi_teams = list(deduped_kasi.values())

    available_staff = get_available_staff()
    pending_requests = list_team_member_requests(status="pending")
    kecamatan_list = list_kecamatan()

    activity_logs = fetch_activity_logs(
        limit=50,
        target_types=("MONEV_TEAM", "MONEV_TEAM_MEMBER", "MONEV_MEMBER_REQUEST"),
    )

    return render_template(
        "portal/admin/monev_teams.html",
        kasi_teams=kasi_teams,
        kecamatan_teams=kecamatan_teams,
        custom_teams=custom_teams,
        available_staff=available_staff,
        pending_requests=pending_requests,
        kecamatan_list=kecamatan_list,
        activity_logs=activity_logs,
    )


@portal_bp.route("/kontak", methods=["GET", "POST"])
@role_required("admin")
def portal_kontak_wilayah() -> Response:
    """Admin page to manage kontak per wilayah."""
    kecamatan_list = list_kecamatan()
    allowed_wilayah = {
        (kec.get("name") or "").strip()
        for kec in kecamatan_list
        if (kec.get("name") or "").strip()
    }
    if request.method == "POST":
        action = (request.form.get("action") or "create").strip().lower()
        kontak_id = request.form.get("kontak_id")
        wilayah = (request.form.get("wilayah") or "").strip()

        try:
            if action == "set_status":
                if not kontak_id:
                    flash("ID kontak tidak valid.", "danger")
                else:
                    contact_index_raw = request.form.get("contact_index")
                    is_active_raw = request.form.get("is_active")
                    try:
                        contact_index = int(contact_index_raw)
                    except (TypeError, ValueError):
                        contact_index = 0
                    is_active = str(is_active_raw or "").strip().lower() in ("1", "true", "on", "yes")
                    updated = update_portal_kontak_status(
                        kontak_id=int(kontak_id),
                        contact_index=contact_index,
                        is_active=is_active,
                    )
                    if updated:
                        flash("Status kontak berhasil diperbarui.", "success")
                    else:
                        flash("Kontak tidak ditemukan atau status gagal diperbarui.", "warning")

            elif action in {"create", "update"}:
                nama_1 = (request.form.get("nama_1") or "").strip()
                kontak_1 = (request.form.get("kontak_1") or "").strip()
                nama_2 = (request.form.get("nama_2") or "").strip()
                kontak_2 = (request.form.get("kontak_2") or "").strip()
                kontak_1_active = (request.form.get("kontak_1_active") or "1") == "1"
                kontak_2_active = (request.form.get("kontak_2_active") or "1") == "1"

                if not wilayah or (allowed_wilayah and wilayah not in allowed_wilayah):
                    flash("Wilayah wajib dipilih dari daftar.", "warning")
                elif not all([nama_1, kontak_1, nama_2, kontak_2]):
                    flash("Nama dan kontak untuk dua nomor wajib diisi.", "warning")
                elif action == "create":
                    existing = get_portal_kontak_by_wilayah(wilayah)
                    if existing:
                        updated = update_portal_kontak(
                            kontak_id=int(existing["id"]),
                            wilayah=wilayah,
                            nama_1=nama_1,
                            kontak_1=kontak_1,
                            nama_2=nama_2,
                            kontak_2=kontak_2,
                            kontak_1_active=kontak_1_active,
                            kontak_2_active=kontak_2_active,
                        )
                        if updated:
                            flash("Kontak wilayah berhasil diperbarui.", "success")
                        else:
                            flash("Kontak tidak ditemukan atau tidak ada perubahan.", "info")
                    else:
                        create_portal_kontak(
                            wilayah=wilayah,
                            nama_1=nama_1,
                            kontak_1=kontak_1,
                            nama_2=nama_2,
                            kontak_2=kontak_2,
                            kontak_1_active=kontak_1_active,
                            kontak_2_active=kontak_2_active,
                        )
                        flash("Kontak wilayah berhasil ditambahkan.", "success")
                else:
                    if not kontak_id:
                        flash("ID kontak tidak valid.", "danger")
                    else:
                        updated = update_portal_kontak(
                            kontak_id=int(kontak_id),
                            wilayah=wilayah,
                            nama_1=nama_1,
                            kontak_1=kontak_1,
                            nama_2=nama_2,
                            kontak_2=kontak_2,
                            kontak_1_active=kontak_1_active,
                            kontak_2_active=kontak_2_active,
                        )
                        if updated:
                            flash("Kontak wilayah berhasil diperbarui.", "success")
                        else:
                            flash("Kontak tidak ditemukan atau tidak ada perubahan.", "info")

            elif action == "delete":
                if not kontak_id:
                    flash("ID kontak tidak valid.", "danger")
                else:
                    deleted = delete_portal_kontak(int(kontak_id))
                    if deleted:
                        flash("Kontak wilayah berhasil dihapus.", "success")
                    else:
                        flash("Kontak tidak ditemukan.", "warning")
            else:
                flash("Aksi tidak dikenal.", "warning")

        except Exception as exc:
            current_app.logger.error(f"Error managing portal kontak wilayah: {exc}")
            flash(f"Gagal memproses data: {exc}", "danger")

    contacts = list_portal_kontak()
    return render_template(
        "portal/admin/kontak.html",
        contacts=contacts,
        kecamatan_list=kecamatan_list,
    )


@portal_bp.route("/my-team")
@role_required("coordinator", "staff")
def view_my_team() -> Response:
    """View all monev teams for coordinator or staff member (Portal)."""
    from dashboard.queries import get_monev_teams, get_team_members

    user = current_user()
    user_id = user.get("id")

    all_teams = get_monev_teams()
    my_teams = []
    all_available_staff = get_available_staff()

    for team in all_teams:
        team_role = None
        if team.get('coordinator_id') == user_id:
            team_role = 'coordinator'

        members = get_team_members(team['id'])

        if team_role is None and any(m.get('staff_id') == user_id for m in members):
            team_role = 'member'

        if team_role is None:
            continue

        team_data = dict(team)
        team_data["team_role"] = team_role
        team_data["members"] = members
        if team_role == "coordinator":
            existing_member_ids = {m["staff_id"] for m in members}
            team_data["available_staff"] = [
                staff for staff in all_available_staff
                if staff["id"] not in existing_member_ids
            ]
            team_data["member_requests"] = list_team_member_requests_for_team(team["id"])
        else:
            team_data["available_staff"] = []
            team_data["member_requests"] = []
        my_teams.append(team_data)

    my_teams.sort(
        key=lambda row: (
            0 if row.get("team_role") == "coordinator" else 1,
            (row.get("team_type") or "").lower(),
            (row.get("name") or row.get("kecamatan_name") or "").lower(),
            row.get("id") or 0,
        )
    )

    return render_template(
        "portal/teams/my_team.html",
        my_teams=my_teams,
    )


@portal_bp.route("/coordinator/assignment-requests", methods=["GET", "POST"])
@role_required("coordinator")
def coordinator_assignment_requests() -> Response:
    """Coordinator submits and views assignment requests for their team."""
    user = current_user()
    my_team, team_members, staff_ids = _get_coordinator_team_context(user.get("id"))
    if not my_team:
        flash("Anda belum memiliki tim.", "warning")
        return redirect(url_for("portal.view_my_team"))

    # Build staff options (team members + coordinator themself)
    staff_options = list(team_members)
    team_staff_ids = {member.get("staff_id") for member in staff_options}
    if user.get("id") not in team_staff_ids:
        staff_options.append({
            "staff_id": user.get("id"),
            "full_name": user.get("full_name") or my_team.get("coordinator_name") or "Saya (Koordinator)",
            "role": user.get("role") or my_team.get("coordinator_role") or "coordinator",
        })
    schools = list_portal_schools()
    periods = list_periods()
    active_period_id = next((p["id"] for p in periods if p.get("is_active")), None) or (periods[0]["id"] if periods else None)
    staff_name_map = {}
    for member in staff_options:
        staff_value = member.get("staff_id")
        if staff_value is None:
            continue
        try:
            staff_key = int(staff_value)
        except (TypeError, ValueError):
            continue
        staff_name_map[staff_key] = member.get("full_name")
    school_name_map = {}
    for school in schools:
        school_value = school.get("id")
        if school_value is None:
            continue
        try:
            school_key = int(school_value)
        except (TypeError, ValueError):
            continue
        school_name_map[school_key] = school.get("name")
    period_name_map = {}
    for period in periods:
        period_value = period.get("id")
        if period_value is None:
            continue
        try:
            period_key = int(period_value)
        except (TypeError, ValueError):
            continue
        period_name_map[period_key] = period.get("name")

    if request.method == "POST":
        if request.is_json:
            data = request.get_json(silent=True) or {}
            staff_id = data.get("staff_id", None)
            school_ids = data.get("school_ids") or []
            note = (data.get("note") or "").strip() or None
            period_id_raw = data.get("period_id")
            if not staff_id or not school_ids:
                return jsonify(success=False, message="Pilih staff dan minimal satu sekolah."), 400
            if staff_id not in staff_ids and staff_id != user.get("id"):
                return jsonify(success=False, message="Staff tidak ada di tim Anda."), 403
            try:
                period_id = int(period_id_raw) if period_id_raw not in (None, "") else None
            except (TypeError, ValueError):
                return jsonify(success=False, message="Periode tidak valid."), 400

            created = 0
            errors = []
            for sid in school_ids:
                try:
                    created_row = create_assignment_request(user["id"], int(staff_id), int(sid), note, period_id)
                    created += 1
                    created_row_id = created_row.get("id") if created_row else None
                    if created_row_id is not None:
                        try:
                            staff_key = int(staff_id)
                        except (TypeError, ValueError):
                            staff_key = None
                        try:
                            school_key = int(sid)
                        except (TypeError, ValueError):
                            school_key = None
                        try:
                            notify_assignment_request(
                                request_id=int(created_row_id),
                                coordinator_name=user.get("full_name") or user.get("email"),
                                staff_name=staff_name_map.get(staff_key or -1),
                                school_name=school_name_map.get(school_key or -1),
                                period_name=period_name_map.get(period_id) if period_id is not None else None,
                                note=note,
                            )
                        except Exception:
                            current_app.logger.exception(
                                "Gagal mengirim notifikasi Telegram permintaan assignment."
                            )
                except Exception as exc:
                    errors.append(str(exc))
            return jsonify(success=created > 0, created=created, errors=errors)

        # Fallback: single submission via form
        staff_id = request.form.get("staff_id", type=int)
        school_id = request.form.get("school_id", type=int)
        period_id = request.form.get("period_id", type=int)
        note = (request.form.get("note") or "").strip() or None
        if not staff_id or not school_id:
            flash("Pilih staff dan sekolah.", "warning")
        elif staff_id not in staff_ids and staff_id != user.get("id"):
            flash("Staff tidak ada di tim Anda.", "danger")
        else:
            try:
                created_row = create_assignment_request(user["id"], staff_id, school_id, note, period_id)
                created_row_id = created_row.get("id") if created_row else None
                if created_row_id is not None:
                    try:
                        notify_assignment_request(
                            request_id=int(created_row_id),
                            coordinator_name=user.get("full_name") or user.get("email"),
                            staff_name=staff_name_map.get(staff_id),
                            school_name=school_name_map.get(school_id),
                            period_name=period_name_map.get(period_id) if period_id is not None else None,
                            note=note,
                        )
                    except Exception:
                        current_app.logger.exception("Gagal mengirim notifikasi Telegram permintaan assignment.")
                flash("Permintaan penugasan dikirim ke admin.", "success")
            except Exception as exc:
                flash(f"Gagal mengirim permintaan: {exc}", "danger")

    requests_list = list_coordinator_requests(user["id"])
    return render_template(
        "portal/coordinator/assignment_requests.html",
        team=my_team,
        staff_options=staff_options,
        schools=schools,
        requests_list=requests_list,
        periods=periods,
        active_period_id=active_period_id,
    )


@portal_bp.route("/coordinator/assessments")
@role_required("coordinator")
def coordinator_assessments() -> Response:
    """Coordinator can start/continue their own assessments."""
    user = current_user()
    periods = list_periods()
    active_period_id = next((p["id"] for p in periods if p.get("is_active")), None) or (periods[0]["id"] if periods else None)
    
    selected_period_id = request.args.get("period_id", type=int)
    if selected_period_id is None:
        selected_period_id = active_period_id

    assigned_schools = get_staff_assigned_schools(user["id"], period_id=selected_period_id)

    return render_template(
        "portal/coordinator/assessments.html",
        assigned_schools=assigned_schools,
        periods=periods,
        active_period_id=active_period_id,
        selected_period_id=selected_period_id,
        user=user,
    )
