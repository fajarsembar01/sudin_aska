"""Routes for portal assessment system (PANBERSS)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
import math
import json
import uuid
import re

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
    get_assessment_room_score_pct,
    get_assessment_photos,
    submit_assessment,
    list_staff_assessments,
    fetch_portal_stats,
    list_recent_assessments,
    fetch_top_schools,
    create_room,
    create_aspect,
    create_school,
    update_school_rooms,
    list_periods,
    reopen_assessment,
    fetch_random_photos,
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
    # Classroom configuration
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
    get_optional_rooms_for_schools,
    get_room_with_aspects,
    list_portal_kontak,
    create_portal_kontak,
    update_portal_kontak,
    update_portal_kontak_status,
    get_portal_kontak_by_wilayah,
    delete_portal_kontak,
)
from dashboard.queries import (
    create_team_member_request,
    list_team_member_requests,
    list_team_member_requests_for_team,
    update_team_member_request_status,
    get_team_member_request,
    get_available_staff,
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
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
AREA_CONTACTS = [
    {"area": "Cilincing", "name": "Neni", "phone": "+62 851-1085-1681"},
    {"area": "Kelapa Gading", "name": "Slamet", "phone": "+62 859-2123-2424"},
    {"area": "Koja", "name": "Rani", "phone": "+62 878-8032-8670"},
]


@portal_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    """Serve uploaded files (supports nested paths)."""
    requested_path = Path(filename)
    if requested_path.is_absolute() or ".." in requested_path.parts:
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, str(requested_path))


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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


def _normalize_metadata(meta: object | None) -> dict:
    """Coerce metadata to a dict, falling back to empty dict on bad data."""
    if not meta:
        return {}
    if isinstance(meta, dict):
        return meta
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
    if not jenjang:
        return []
    upper = jenjang.upper()
    if upper == "SD":
        return list(range(1, 7))
    if upper == "SMP":
        return list(range(7, 10))
    if upper in {"SMA", "SMK"}:
        return list(range(10, 13))
    if upper == "TK":
        return [-1, 0]  # TK A, TK B
    if upper == "PAUD":
        return [-2, -1, 0]  # KB, Kelompok A, Kelompok B
    return []


def _classroom_grade_from_name(name: str) -> int | None:
    """Extract grade number from classroom name (supports variants like 5A)."""
    match = re.search(r"\bKelas\s+(-?\d+)", name or "", flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _is_classroom_variant(name: str) -> bool:
    """Return True for variant classroom names like 'Ruang Kelas 5A'."""
    return bool(
        re.match(
            r"^\s*(?:Ruang\s+)?Kelas\s+-?\d+\s*[A-Za-z]+\s*$",
            name or "",
            flags=re.IGNORECASE,
        )
    )


def _classroom_band_for_grade(grade: int) -> list[int]:
    if grade == 1:
        return list(range(1, 7))
    if grade == 7:
        return list(range(7, 10))
    if grade == 10:
        return list(range(10, 13))
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
                    errors.append(f"Bangku kosong kelas {g} wajib diisi.")
                    break
                try:
                    int_val = int(val)
                    if int_val < 0:
                        errors.append(f"Bangku kosong kelas {g} harus >= 0.")
                        break
                except Exception:
                    errors.append(f"Bangku kosong kelas {g} harus angka.")
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
    """Staff portal home - list assessments."""
    user = current_user()
    role = user.get("role")
    
    if role == "sekolah":
        return redirect(url_for("portal.sekolah_rooms"))
    
    if role == "admin":
        return redirect(url_for("portal.admin_stats"))
    
    if role == "coordinator":
        return redirect(url_for("portal.coordinator_dashboard"))
    
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
        return redirect(url_for("portal.sekolah_rooms"))
    
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


def _filter_assessment_rooms(rooms: list[dict]) -> list[dict]:
    """Filter rooms to hide base kelas when variant rooms exist."""
    def _grade_and_variant(name: str) -> tuple[int | None, str | None]:
        match = re.search(r"\bKelas\s+(\d+)(\s*[A-Za-z]+)?$", name or "", flags=re.IGNORECASE)
        if not match:
            return None, None
        try:
            grade = int(match.group(1))
        except (TypeError, ValueError):
            return None, None
        variant = (match.group(2) or "").strip().upper() or None
        return grade, variant

    rooms_by_grade: dict[int, list[dict]] = {}
    for room in rooms:
        grade, variant = _grade_and_variant(room.get("room_name") or "")
        if grade is None:
            continue
        rooms_by_grade.setdefault(grade, []).append({"room": room, "variant": variant})

    filtered_rooms: list[dict] = []
    for rlist in rooms_by_grade.values():
        has_variant = any(item.get("variant") for item in rlist)
        for item in rlist:
            if has_variant and not item.get("variant"):
                continue
            filtered_rooms.append(dict(item["room"]))

    # Include non-classroom rooms (no grade match)
    for room in rooms:
        grade, _ = _grade_and_variant(room.get("room_name") or "")
        if grade is None:
            filtered_rooms.append(room)

    return filtered_rooms


def _sync_assessment_period_to_active(assessment: dict) -> None:
    """Force draft period to match the currently active period."""
    if not assessment or assessment.get("status") != "draft":
        return
    active_period = get_active_period()
    if not active_period:
        return
    period_id = active_period.get("id")
    if not period_id:
        return
    if assessment.get("period_id") == period_id:
        return
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_assessments
            SET period_id = %s,
                updated_at = NOW()
            WHERE id = %s AND status = 'draft'
            """,
            (period_id, assessment.get("id")),
        )
    assessment["period_id"] = period_id


@portal_bp.route("/assess/<int:school_id>")
@_portal_access_required
def assess(school_id: int) -> Response:
    """Start or continue assessment for a school."""
    user = current_user()
    role = user.get("role")
    period_id_arg = request.args.get("period_id", type=int)
    
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
    
    # Get active draft for THIS user
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
    _sync_assessment_period_to_active(assessment)
    
    # Ensure classroom variants are materialized as rooms for this school
    try:
        ensure_classroom_rooms_for_school(school_id)
    except Exception:
        current_app.logger.exception("Failed to sync classroom rooms")

    # Get school rooms with aspects
    rooms = list_school_rooms(school_id)
    if not rooms:
        flash("Sekolah belum memiliki ruangan yang dikonfigurasi.", "warning")
        return redirect(url_for("portal.schools"))

    rooms = _filter_assessment_rooms(rooms)
    total_aspects = sum(len(r.get("aspects", [])) for r in rooms)
    
    # Periode penilaian untuk badge UI
    assessment_period = get_period_by_id(assessment.get("period_id")) if assessment.get("period_id") else get_active_period()

    # Get existing scores
    existing_scores = get_assessment_scores(assessment_id)
    scores_map = {
        (s["school_room_id"], s["aspect_id"]): s["score"]
        for s in existing_scores
    }
    
    photos_list = get_assessment_photos(assessment_id)
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
    
    # Get room notes
    room_notes = get_assessment_room_details(assessment_id)
    
    # Get optional rooms for this school
    optional_rooms_data = get_optional_rooms_for_schools([school_id])
    
    return render_template(
        "portal/assessments/assessment.html",
        school=school,
        assessment=assessment,
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

        if not (0 <= score <= 3):
            return jsonify({"success": False, "message": "Invalid score"}), 400

        _sync_assessment_period_to_active(assessment)

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
    if user.get("role") not in ("admin", "staff"):
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
        _sync_assessment_period_to_active(assessment)
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
    if user.get("role") not in ("admin", "staff"):
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
        _sync_assessment_period_to_active(assessment)
        score_pct = get_assessment_room_score_pct(assessment_id, school_room_id)
        if score_pct > 90:
            return jsonify(
                {
                    "success": False,
                    "message": "Foto hanya boleh untuk ruangan dengan skor 90 atau kurang.",
                }
            ), 400
        rooms = list_school_rooms(school_id)
        rooms = _filter_assessment_rooms(rooms)
        total_rooms = len(rooms)
        max_photos = math.ceil(total_rooms * 0.5) if total_rooms else 0
        if max_photos:
            room_ids = {r.get("school_room_id") for r in rooms if r.get("school_room_id")}
            photos_list = get_assessment_photos(assessment_id)
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
    if user.get("role") not in ("admin", "staff"):
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
        rooms = list_school_rooms(school_id)
        rooms = _filter_assessment_rooms(rooms)
        total_rooms = len(rooms)
        min_photos = math.ceil(total_rooms * 0.2) if total_rooms else 0
        missing_messages = []
        if min_photos:
            room_ids = {r.get("school_room_id") for r in rooms if r.get("school_room_id")}
            photos_list = get_assessment_photos(assessment_id_int)
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

        existing_scores = get_assessment_scores(assessment_id_int)
        scores_map = {
            (s["school_room_id"], s["aspect_id"]): s.get("score")
            for s in existing_scores
        }
        for room in rooms:
            room_id = room.get("school_room_id")
            aspects = room.get("aspects") or []
            if not room_id or not aspects:
                continue
            has_non_zero = False
            for aspect in aspects:
                score_val = scores_map.get((room_id, aspect.get("id"))) or 0
                if score_val > 0:
                    has_non_zero = True
                    break
            if not has_non_zero:
                missing_messages.append("Terdapat ruangan yang masih belum dinilai.")
                break

        if missing_messages:
            flash(" ".join(missing_messages), "warning")
            return redirect(url_for("portal.assess", school_id=school_id))
    except Exception:
        current_app.logger.exception("Error validating submission requirements")
        flash("Gagal memvalidasi persyaratan submit. Coba lagi.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))
    
    try:
        _sync_assessment_period_to_active(assessment)
        success = submit_assessment(assessment_id_int)
        if success:
            flash("Penilaian berhasil disubmit!", "success")
        else:
            flash("Gagal submit penilaian.", "danger")
    except Exception as e:
        current_app.logger.exception("Error submitting assessment")
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.home"))


@portal_bp.route("/assess/<int:school_id>/save-draft", methods=["POST"])
@_portal_access_required
def save_draft(school_id: int) -> Response:
    """Explicitly save assessment as draft (no submit)."""
    user = current_user()
    if user.get("role") not in ("admin", "staff"):
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
        _sync_assessment_period_to_active(assessment)
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
    if user.get("role") not in ("admin", "staff"):
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
    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        flash("Anda tidak memiliki akses untuk melihat penilaian ini.", "danger")
        return redirect(url_for("portal.home"))
    
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
                    a.submitted_at, 
                    a.staff_id, 
                    u.full_name as assessor_name,
                    u.email as assessor_email,
                    (a.id = %s) AS is_current
                FROM portal_assessments a
                LEFT JOIN dashboard_users u ON u.id = a.staff_id
                WHERE a.school_id = %s AND a.status = 'submitted'
                ORDER BY a.submitted_at DESC
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
    if user.get("role") not in ("admin", "staff"):
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
    if user.get("role") not in ("admin", "staff"):
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

    return redirect(url_for("portal.home"))


# ===== Staff Assignment Routes =====


@portal_bp.route("/staff/assignments")
@_portal_access_required
def staff_assignments() -> Response:
    """Staff view their assigned schools."""
    user = current_user()
    
    if user.get("role") != "staff":
        flash("Halaman ini hanya untuk staf.", "warning")
        return redirect(url_for("portal.home"))
    
    assigned_schools = get_staff_assigned_schools(user["id"])
    periods = list_periods()
    active_period_id = next((p["id"] for p in periods if p.get("is_active")), None) or (periods[0]["id"] if periods else None)
    
    return render_template(
        "portal/staff/assignments.html",
        assigned_schools=assigned_schools,
        periods=periods,
        active_period_id=active_period_id,
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
    
    # Build set of (grade, variant) pairs for exact matching
    # e.g., {(1, 'A'), (2, 'A'), (3, 'A')} means only show Kelas 1A, 2A, 3A
    classroom_variants: set[tuple[int, str]] = set()
    classroom_grades: set[int] = set()
    
    for cls in classrooms:
        try:
            g = int(cls.get("grade_level"))
            variant = (cls.get("variant") or "").strip().upper()
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

    # Categorize rooms by grade number (so SD tab doesn't show kelas 10-12)
    # Regex patterns to match classroom names (support negative grades for PAUD/TK)
    variant_pattern = re.compile(r"^\s*(?:Ruang\s+)?Kelas\s+(-?\d+)\s*([A-Za-z]+)\s*$", re.IGNORECASE)
    base_pattern = re.compile(r"\bKelas\s+(-?\d+)\b", re.IGNORECASE)

    def _room_grade(room: dict) -> int | None:
        name_val = room.get("name") or ""
        m = variant_pattern.match(name_val) or base_pattern.search(name_val)
        if not m:
            return None
        try:
            return int(m.group(1))
        except (TypeError, ValueError):
            return None

    def _is_variant_class(name: str) -> bool:
        return bool(variant_pattern.match(name or ""))
    
    def _room_variant(room: dict) -> str | None:
        """Extract variant letter from room name (e.g., 'A' from 'Ruang Kelas 1A')."""
        name_val = room.get("name") or ""
        m = variant_pattern.match(name_val)
        if not m or not m.group(2):
            return None
        return m.group(2).strip().upper()

    for r in all_rooms:
        aspects = r.get("aspects") or []
        has_optional_selected = any(
            (not a.get("is_required")) and a.get("is_selected") for a in aspects
        )
        r["default_select_all_aspects"] = bool(_room_grade(r) is not None and not has_optional_selected)

    # Identifikasi jenjang yang sudah punya kelas paralel (mis. 1A, 1B) untuk menyembunyikan base "Ruang Kelas 1"
    variant_grades: set[int] = set()
    for r in all_rooms:
        name_val = r.get("name") or ""
        if _is_variant_class(name_val):
            g = _room_grade(r)
            if g is not None:
                variant_grades.add(g)
    # Tambahkan paralel yang sudah disimpan oleh sekolah (jika ada)
    for sr in saved_rooms:
        name_val = sr.get("room_name") or sr.get("name") or ""
        if _is_variant_class(name_val):
            g = _room_grade(sr)
            if g is not None:
                variant_grades.add(g)
    # Include classroom config grades so base kelas disembunyikan ketika paralel sudah diatur
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
    
    for r in all_rooms:
        name_val = r.get("name") or ""
        # Only show variant classrooms if exact (grade, variant) match OR already saved
        if _is_variant_class(name_val):
            g = _room_grade(r)
            variant = _room_variant(r)
            
            # Check if this exact (grade, variant) pair is configured
            is_exact_match = (g, variant) in classroom_variants if (g and variant) else False
            is_saved = r.get("id") in saved_room_ids
            should_skip = not is_exact_match and not is_saved
            
            # Log each variant room decision
            current_app.logger.info(
                "[sekolah_rooms] Variant room '%s': room_id=%s, grade=%s, variant='%s', exact_match=%s, is_saved=%s, SKIP=%s",
                name_val, r.get("id"), g, variant, is_exact_match, is_saved, should_skip
            )
            
            if should_skip:
                skipped_variant_rooms.append(name_val)
                continue
        # Jika ada paralel untuk jenjang yang sama, sembunyikan base class (mis. "Ruang Kelas 1")
        g = _room_grade(r)
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
    umum_rooms = []
    for r in filtered_rooms:
        grade = _room_grade(r)
        if grade is None:
            umum_rooms.append(r)
        elif -2 <= grade <= 0:  # PAUD/TK levels
            # Add to both, template will show correct tab based on jenjang
            paud_rooms.append(r)
            tk_rooms.append(r)
        elif 1 <= grade <= 6:
            sd_rooms.append(r)
        elif 7 <= grade <= 9:
            smp_rooms.append(r)
        elif 10 <= grade <= 12:
            sma_rooms.append(r)
        else:
            umum_rooms.append(r)
    
    missing_fields = _compute_missing_profile_fields(user_school) if user_school else []
    show_profile_modal = bool(missing_fields)
    kecamatan_list = list_kecamatan()
    kelurahan_list = list_kelurahan()  # full list to allow sekolah update
    
    # Determine selected school for jenjang-aware UI
    selected_school = user_school
    if not selected_school and current_school_id:
        selected_school = next((s for s in schools if s.get("id") == current_school_id), None)

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
        selected_school=selected_school,
        paud_rooms=paud_rooms,
        tk_rooms=tk_rooms,
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
        
        score_base = float(p.get("room_score") or 0)
        score_pct = (score_base / 3 * 100) if score_base else 0
        
        result.append({
            "photo_url": photo_url,
            "school_name": p.get("school_name"),
            "room_name": p.get("room_name"),
            "score": round(score_pct, 1),
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
    user_id = user.get("id")
    period_id = request.args.get("period_id", type=int)
    jenjang_filter = request.args.get("jenjang") or None
    order = request.args.get("order") or "recent"
    photo_order = request.args.get("photo_order", "random")
    
    my_team, team_members, staff_ids = _get_coordinator_team_context(user_id)
    
    if not my_team:
        flash("Anda belum ditugaskan sebagai koordinator tim manapun.", "warning")
        return redirect(url_for("portal.home"))
        
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
    from .queries import fetch_team_top_schools, fetch_team_bottom_schools

    period_id = request.args.get("period_id", type=int)
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
    
    stats = fetch_portal_stats(period_id, staff_ids=staff_ids)
    from .queries import fetch_score_distribution
    score_dist = fetch_score_distribution(period_id, staff_ids=staff_ids)
    recent_assessments = list_recent_assessments(
        period_id=period_id,
        jenjang=jenjang_filter,
        order=order,
        staff_ids=staff_ids,
    )
    if staff_ids:
        top_schools = fetch_team_top_schools(staff_ids, period_id=period_id, limit=10)
        bottom_schools = fetch_team_bottom_schools(staff_ids, period_id=period_id, limit=10)
    else:
        top_schools = fetch_top_schools(period_id=period_id, limit=10)
        bottom_schools = fetch_bottom_schools(period_id=period_id, limit=10)
    photo_order = request.args.get("photo_order", "random")
    random_photos = fetch_random_photos(
        period_id=period_id,
        order=photo_order,
        limit=24,
        staff_ids=staff_ids,
    )
    school_avg_map = fetch_school_avg_scores(period_id=period_id, staff_ids=staff_ids)
    periods = list_periods()
    all_schools = list_portal_schools()
    all_staff = list_all_staff()
    monev_teams = get_monev_teams()
    
    from .queries import fetch_kecamatan_avg_scores
    kecamatan_stats = fetch_kecamatan_avg_scores(period_id, staff_ids=staff_ids)
    
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
        selected_team_id=team_id,
        selected_team=selected_team,
        jenjang_filter=jenjang_filter,
        order=order,
        photo_order=photo_order,
        all_schools=all_schools,
        all_staff=all_staff,
        monev_teams=monev_teams,
    )


@portal_bp.route("/api/rankings")
@role_required("admin")
def api_rankings() -> Response:
    """API endpoint for fetching additional rankings."""
    from .queries import fetch_team_top_schools, fetch_team_bottom_schools
    
    type_ = request.args.get("type", "best")
    limit = request.args.get("limit", 10, type=int)
    offset = request.args.get("offset", 0, type=int)
    period_id = request.args.get("period_id", type=int) or None
    team_id = request.args.get("team_id", type=int)
    
    staff_ids = None
    if team_id:
        staff_ids, team = _get_team_staff_ids(team_id)
        if team is None:
            staff_ids = None
    
    if type_ == "best":
        if staff_ids:
            data = fetch_team_top_schools(staff_ids, period_id=period_id, limit=limit, offset=offset)
        else:
            data = fetch_top_schools(limit=limit, offset=offset, period_id=period_id)
    else:
        if staff_ids:
            data = fetch_team_bottom_schools(staff_ids, period_id=period_id, limit=limit, offset=offset)
        else:
            data = fetch_bottom_schools(limit=limit, offset=offset, period_id=period_id)
        
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
    
    filename = f"Laporan_Penilaian_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
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
    period_id = request.args.get("period_id", type=int)
    team_id = request.args.get("team_id", type=int)
    from .queries import fetch_map_data
    
    staff_ids = None
    if team_id:
        staff_ids, team = _get_team_staff_ids(team_id)
        if team is None:
            staff_ids = None
    
    data = fetch_map_data(period_id, staff_ids=staff_ids)
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


@portal_bp.route("/admin/photos")
@role_required("admin")
def admin_photos_partial() -> Response:
    """Return gallery grid partial for photo order changes (AJAX)."""
    period_id = request.args.get("period_id", type=int)
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
                    "total": 0,
                },
                "users": [],
                "assignment_requests": [],
                "team_member_requests": [],
                "reopen_requests": [],
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

        needs_attention = (not is_claimed) or (not has_rooms) or bool(missing_fields) or bool(suspicious_reasons)
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
                "missing_preview": missing_preview,
                "missing_fields": missing_fields,
                "suspicious_preview": suspicious_preview,
                "suspicious_reasons": suspicious_reasons,
                "operator_phone": operator_phone_display,
                "operator_wa": wa_link,
            }
        )

    def _room_grade(name: str) -> int | None:
        m = re.search(r"\bKelas\s+(\d+)", name or "", flags=re.IGNORECASE)
        if not m:
            return None
        try:
            return int(m.group(1))
        except (TypeError, ValueError):
            return None

    def _is_variant_class(name: str) -> bool:
        # Detect names like "Ruang Kelas 1A" "Ruang Kelas 1B" etc.
        return bool(re.search(r"^Ruang\\s+Kelas\\s+\\d+\\s*[A-Za-z]+$", name or "", flags=re.IGNORECASE))

    # Build base rooms: keep non-class rooms and only one representative per jenjang band (SD=1, SMP=7, SMA=10)
    base_rooms = []
    seen_names = set()
    for r in rooms:
        name = r.get("name") or ""
        grade = _room_grade(name)
        is_variant = _is_variant_class(name)
        templ = None
        if grade is not None:
            if grade <= 6:
                templ = 1
            elif grade <= 9:
                templ = 7
            elif grade <= 12:
                templ = 10

        should_keep = False
        if grade is None:
            should_keep = True  # non-class room
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
        max_score_pct=100,  # Get all schools, we'll filter in frontend
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
            -- Average score for this room (0-3 scale, convert to 0-100)
            COALESCE(AVG(sc.score), 0)::DECIMAL(5,2) as avg_score_raw,
            ROUND(COALESCE(AVG(sc.score), 0) / 3 * 100, 1) as avg_score_pct,
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
          AND a.status = 'submitted'
        GROUP BY r.id, r.name, sr.id, a.id, u.full_name, u.id
        HAVING AVG(sc.score) IS NOT NULL
        ORDER BY AVG(sc.score) ASC, r.name, u.full_name
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
    classrooms = data.get("classrooms", [])
    
    try:
        save_school_classrooms_batch(user_school["id"], classrooms)
        try:
            ensure_classroom_rooms_for_school(user_school["id"])
        except Exception:
            current_app.logger.exception("Failed to sync classroom rooms after save")
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



# Add permissions to template context globally
@portal_bp.context_processor
def inject_permissions():
    """Inject permission checks into all portal templates."""
    user = current_user()
    if not user:
        return {}
    
    from .permissions import get_permission_summary
    user_school = None
    user_area_name = None
    if user.get("role") == "sekolah":
        user_school = _fetch_user_school(user.get("id"))
    else:
        user_area_name = _fetch_user_kecamatan_name(user.get("id"))
    area_contacts = _build_coordinator_contacts(user_school, area_name=user_area_name)
    admin_pending = {
        "pending_users": 0,
        "pending_assignment_requests": 0,
        "pending_team_member_requests": 0,
        "pending_reopen_requests": 0,
        "pending_guestbook": 0,
        "total": 0,
    }
    if user.get("role") == "admin":
        try:
            admin_pending = fetch_admin_pending_summary()
        except Exception:
            current_app.logger.exception("Failed to load admin pending summary")

    return {
        'permissions': get_permission_summary(user),
        'is_superadmin': is_superadmin(user),
        'can_access_aska': can_access_aska(user),
        'user_school': user_school,
        'area_contacts': area_contacts,
        'admin_pending': admin_pending,
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
    user = current_user()
    user_id = user.get("id")
    staff_id = request.form.get("staff_id", type=int)
    note = (request.form.get("note") or "").strip()
    
    my_team, _, _ = _get_coordinator_team_context(user_id)
    if not my_team:
        flash("Anda belum memiliki tim.", "warning")
        return redirect(url_for("portal.view_my_team"))
    
    if not staff_id:
        flash("Pilih staff yang ingin diajukan.", "warning")
        return redirect(url_for("portal.coordinator_team"))
    
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
        flash("Permintaan tambah anggota dikirim ke admin untuk verifikasi.", "success")
    else:
        flash("Gagal mengirim permintaan.", "danger")
    
    return redirect(url_for("portal.coordinator_team"))


# =====================================================
# User Profile (admin/coordinator/staff)
# =====================================================

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
            except Exception as exc:
                current_app.logger.error(f"Gagal memperbarui profil: {exc}")
                flash("Gagal memperbarui profil.", "danger")

    return render_template("portal/profile.html", profile=profile_view)


# =====================================================
# User Management & Monev Teams (Portal Integration)
# =====================================================

@portal_bp.route("/settings/users", methods=["GET", "POST"])
@role_required("admin")
def manage_users() -> Response:
    """Manage dashboard users from Portal app."""
    from dashboard.queries import list_dashboard_users, create_dashboard_user, update_dashboard_user
    from dashboard.portal.queries import list_kecamatan
    from werkzeug.security import generate_password_hash
    from .queries import log_activity, fetch_activity_logs
    
    if request.method == "POST":
        action = request.form.get("action", "create")
        user_id = request.form.get("user_id")
        wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        
        email = (request.form.get("email") or "").strip().lower()
        full_name = (request.form.get("full_name") or "").strip()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "viewer").strip()
        account_status = request.form.get("account_status")
        reviewer_note = (request.form.get("reviewer_note") or "").strip() or None
        school_id_raw = (request.form.get("school_id") or "").strip()
        school_id = int(school_id_raw) if school_id_raw.isdigit() else None
        if role != "sekolah":
            school_id = None
        requested_kecamatan_raw = (request.form.get("requested_kecamatan") or "").strip()
        requested_kecamatan = int(requested_kecamatan_raw) if requested_kecamatan_raw.isdigit() else None

        try:
            if action == "create":
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
                    )
                    details = {
                        "email": email,
                        "role": role,
                    }
                    if requested_kecamatan is not None:
                        details["kecamatan_id"] = requested_kecamatan
                    if school_id is not None:
                        details["school_id"] = school_id
                        school = get_school_by_id(school_id)
                        if school:
                            details["school_name"] = school.get("name")
                            details["npsn"] = school.get("npsn")
                    log_activity(
                        current_user().get("id") if current_user() else None,
                        "CREATE",
                        "USER",
                        new_user_id,
                        full_name or email,
                        details,
                    )
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
                    )
                    if updated:
                        details = {
                            "email": email,
                            "role": role,
                        }
                        if account_status:
                            details["account_status"] = account_status
                        if requested_kecamatan is not None:
                            details["kecamatan_id"] = requested_kecamatan
                        if school_id is not None:
                            details["school_id"] = school_id
                            school = get_school_by_id(school_id)
                            if school:
                                details["school_name"] = school.get("name")
                                details["npsn"] = school.get("npsn")
                        log_activity(
                            current_user().get("id") if current_user() else None,
                            "UPDATE",
                            "USER",
                            int(user_id),
                            full_name or email,
                            details,
                        )
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
                        log_activity(
                            current_user().get("id") if current_user() else None,
                            "UPDATE",
                            "USER",
                            int(user_id),
                            full_name or email,
                            details,
                        )
                    if wants_json:
                        status_code = 200 if updated else 400
                        return jsonify(
                            {
                                "success": bool(updated),
                                "user_id": int(user_id),
                                "account_status": account_status,
                            }
                        ), status_code
                    flash(f"Status user berhasil diubah menjadi {account_status}.", "success")

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
    )


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
    """View monev team for coordinator or staff member (Portal)."""
    from dashboard.queries import get_monev_teams, get_team_members
    
    user = current_user()
    user_id = user.get("id")
    
    all_teams = get_monev_teams()
    
    my_team = None
    my_team_role = None
    
    for team in all_teams:
        if team.get('coordinator_id') == user_id:
            my_team = team
            my_team_role = 'coordinator'
            break
        
        members = get_team_members(team['id'])
        if any(m.get('staff_id') == user_id for m in members):
            my_team = team
            my_team_role = 'member'
            break
    
    if my_team:
        my_team['members'] = get_team_members(my_team['id'])
        if my_team_role == "coordinator":
            existing_member_ids = {m["staff_id"] for m in my_team["members"]}
            available_staff = [
                s for s in get_available_staff()
                if s["id"] not in existing_member_ids
            ]
            member_requests = list_team_member_requests_for_team(my_team["id"])
        else:
            available_staff = []
            member_requests = []
    else:
        available_staff = []
        member_requests = []
    
    return render_template(
        "portal/teams/my_team.html",
        team=my_team,
        team_role=my_team_role,
        available_staff=available_staff,
        member_requests=member_requests,
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
                    create_assignment_request(user["id"], int(staff_id), int(sid), note, period_id)
                    created += 1
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
                create_assignment_request(user["id"], staff_id, school_id, note, period_id)
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
    assigned_schools = get_staff_assigned_schools(user["id"])
    periods = list_periods()
    active_period_id = next((p["id"] for p in periods if p.get("is_active")), None) or (periods[0]["id"] if periods else None)
    
    return render_template(
        "portal/coordinator/assessments.html",
        assigned_schools=assigned_schools,
        periods=periods,
        active_period_id=active_period_id,
        user=user,
    )
