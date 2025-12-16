"""Routes for portal assessment system (PANBERSS)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
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
)
from werkzeug.utils import secure_filename

from ..auth import current_user, role_required
from dashboard.db_access import get_cursor
from .queries import (
    list_portal_schools,
    list_portal_rooms,
    list_school_rooms,
    get_school_by_id,
    get_active_assessment,
    create_assessment,
    get_assessment_by_id,
    get_assessment_scores,
    save_assessment_score,
    save_assessment_photo,
    save_room_details,
    get_assessment_room_details,
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
    assign_assessment,
    fetch_random_photos,
    create_period,
    list_all_staff,
    get_period_by_id,
    delete_assessment,
    fetch_school_avg_scores,
    fetch_bottom_schools,
    delete_photo,
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
)


portal_bp = Blueprint(
    "portal",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/portal",
)

UPLOAD_FOLDER = Path(__file__).parent.parent.parent / "uploads" / "portal"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
COORDINATOR_CONTACTS = [
    {"area": "Cilincing", "name": "Neni", "phone": "+62 851-1085-1681"},
    {"area": "Kelapa Gading", "name": "Slamet", "phone": "+62 859-2123-2424"},
    {"area": "Koja", "name": "Rani", "phone": "+62 878-8032-8670"},
]


@portal_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    """Serve uploaded files."""
    safe_name = secure_filename(filename)
    return send_from_directory(UPLOAD_FOLDER, safe_name)


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _portal_access_required(view):
    """Decorator for portal access (staff, sekolah, or admin)."""
    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Silakan login terlebih dahulu.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        role = user.get("role")
        if role not in ("admin", "staff", "sekolah"):
            flash("Anda tidak memiliki akses ke portal.", "danger")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapper


def _sanitize_phone(phone: str) -> str:
    """Normalize phone string to digits only for wa.me/api.whatsapp links."""
    digits_only = "".join(ch for ch in phone if ch.isdigit())
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


def _compute_missing_profile_fields(school: dict | None) -> list[str]:
    """Check required fields for sekolah profile completeness."""
    if not school:
        return ["school"]
    meta = school.get("metadata") or {}
    required_keys = {
        "gmaps_url": "Link Google Maps",
        "student_count": "Jumlah siswa",
        "empty_seats": "Jumlah bangku kosong",
        "rombel_count": "Jumlah rombel",
        "school_phone": "Nomor telepon sekolah",
        "coordinator_phone": "Nomor operator sekolah",
        "cs_email": "Email sekolah untuk CS",
    }
    missing = []
    # alamat + kelurahan/kecamatan
    if not (school.get("alamat") and school.get("kelurahan_name") and school.get("kecamatan_name")):
        missing.append("Alamat dan wilayah")
    for key, label in required_keys.items():
        value = meta.get(key)
        if value in (None, "", 0, "0"):
            missing.append(label)
    return missing


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

    return {
        "alamat": (form_data.get("alamat") or "").strip(),
        "kelurahan_id": _clean_int(form_data.get("kelurahan_id")),
        "gmaps_url": (form_data.get("gmaps_url") or "").strip(),
        "student_count": _clean_int(form_data.get("student_count")),
        "empty_seats": _clean_int(form_data.get("empty_seats")),
        "rombel_count": _clean_int(form_data.get("rombel_count")),
        "teacher_count": _clean_int(form_data.get("teacher_count")),
        "staff_count": _clean_int(form_data.get("staff_count")),
        "school_phone": _clean_phone(form_data.get("school_phone")),
        "coordinator_phone": _clean_phone(form_data.get("coordinator_phone")),
        "cs_email": (form_data.get("cs_email") or "").strip(),
        "instagram": (form_data.get("instagram") or "").strip(),
        "tiktok": (form_data.get("tiktok") or "").strip(),
        "youtube": (form_data.get("youtube") or "").strip(),
        "wa_channel": (form_data.get("wa_channel") or "").strip(),
    }


def _validate_profile_data(payload: dict) -> list[str]:
    errors = []
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    if not payload.get("alamat"):
        errors.append("Alamat sekolah wajib diisi.")
    if not payload.get("kelurahan_id"):
        errors.append("Kelurahan wajib dipilih.")
    if not payload.get("gmaps_url"):
        errors.append("Link Google Maps wajib diisi.")
    if payload.get("student_count") is None:
        errors.append("Jumlah siswa wajib diisi.")
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
    """Persist profile data into portal_schools (address + metadata)."""
    meta_fields = {k: v for k, v in data.items() if k not in {"alamat", "kelurahan_id"}}
    with get_cursor(commit=True) as cur:
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
    return digits_only


def _build_coordinator_contacts(school: dict | None = None) -> list[dict]:
    """Return coordinator list with wa links, optionally personalized with school info."""
    contacts = []
    message = "Halo, kami ingin mengganti email akun portal sekolah."
    if school:
        message = (
            f"Halo, kami dari {school.get('name')} (NPSN {school.get('npsn')}) "
            "ingin mengganti email akun portal sekolah."
        )

    for c in COORDINATOR_CONTACTS:
        phone_for_link = _sanitize_phone(c["phone"])
        is_user_area = False
        if school:
            # Simple match: check if school.kecamatan_name contains area name
            kec_name = (school.get("kecamatan_name") or "").lower()
            is_user_area = c["area"].lower() in kec_name
        contacts.append(
            {
                **c,
                "wa_link": f"https://api.whatsapp.com/send?phone={phone_for_link}&text={quote_plus(message)}",
                "normalized_area": c["area"].lower(),
                "is_user_area": is_user_area,
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
    
    assessments = list_staff_assessments(user["id"])
    return render_template(
        "portal/staff_home.html",
        assessments=assessments,
        user=user,
    )


@portal_bp.route("/schools")
@_portal_access_required
def schools() -> Response:
    """List schools available for assessment."""
    user = current_user()
    if user.get("role") == "sekolah":
        return redirect(url_for("portal.sekolah_rooms"))
    
    search = request.args.get("q", "").strip()
    jenjang = request.args.get("jenjang", "").strip() or None
    page = request.args.get("page", 1, type=int)
    per_page = 20
    
    from .queries import get_portal_schools_paginated
    pagination = get_portal_schools_paginated(
        page=page, 
        per_page=per_page, 
        search=search or None, 
        jenjang=jenjang
    )
    
    return render_template(
        "portal/school_select.html",
        schools=pagination["items"],
        pagination=pagination,
        search=search,
        jenjang=jenjang,
    )


@portal_bp.route("/assess/<int:school_id>")
@_portal_access_required
def assess(school_id: int) -> Response:
    """Start or continue assessment for a school."""
    user = current_user()
    if user.get("role") not in ("admin", "staff"):
        flash("Hanya staff yang bisa melakukan penilaian.", "danger")
        return redirect(url_for("portal.home"))
    
    school = get_school_by_id(school_id)
    if not school:
        flash("Sekolah tidak ditemukan.", "danger")
        return redirect(url_for("portal.schools"))
    
    # Get active draft for THIS user
    assessment = get_active_assessment(school_id, staff_id=user["id"])
    if not assessment:
        # Create new assessment
        try:
            assessment = create_assessment(
                school_id,
                staff_id=user["id"],
                creator_email=user["email"],
            )
        except Exception as e:
            current_app.logger.exception("Error creating assessment")
            flash("Gagal membuat penilaian baru.", "danger")
            return redirect(url_for("portal.schools"))
            
    assessment_id = assessment["id"]
    
    # Get school rooms with aspects
    rooms = list_school_rooms(school_id)
    if not rooms:
        flash("Sekolah belum memiliki ruangan yang dikonfigurasi.", "warning")
        return redirect(url_for("portal.schools"))
    total_aspects = sum(len(r.get("aspects", [])) for r in rooms)
    
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
    
    # Get room notes
    room_notes = get_assessment_room_details(assessment_id)
    
    return render_template(
        "portal/assessment.html",
        school=school,
        assessment=assessment,
        rooms=rooms,
        scores_map=scores_map,
        photos_map=photos_map,
        room_notes=room_notes,
        total_aspects=total_aspects,
    )


@portal_bp.route("/assess/<int:school_id>/score", methods=["POST"])
@_portal_access_required
def save_score(school_id: int) -> Response:
    """API endpoint to save a single score."""
    user = current_user()
    if user.get("role") not in ("admin", "staff"):
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

        if assessment["staff_id"] != user["id"] and user["role"] != "admin":
            return jsonify({"success": False, "message": "Unauthorized access to this assessment"}), 403

        if not (0 <= score <= 3):
            return jsonify({"success": False, "message": "Invalid score"}), 400

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

    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
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

    if assessment["school_id"] != school_id:
        flash("Penilaian tidak sesuai sekolah.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))

    if assessment["staff_id"] != user["id"] and user["role"] != "admin":
        flash("Anda tidak memiliki akses untuk submit penilaian ini.", "danger")
        return redirect(url_for("portal.assess", school_id=school_id))
    
    try:
        success = submit_assessment(assessment_id_int)
        if success:
            flash("Penilaian berhasil disubmit!", "success")
        else:
            flash("Gagal submit penilaian.", "danger")
    except Exception as e:
        current_app.logger.exception("Error submitting assessment")
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.home"))


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
    
    return render_template(
        "portal/assessment_view.html",
        assessment=assessment,
        user=user,
        photos_by_room=photos_by_room,
        room_notes=room_notes,
        other_assessments=other_assessments,
        school_avg=school_avg,
        rooms_data=rooms_data,
        related_photos=related_photos,
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


@portal_bp.route("/assessment/<int:assessment_id>/delete", methods=["POST"])
@role_required("admin")
def delete_assessment_route(assessment_id: int) -> Response:
    """Admin deletes an assessment record."""
    if delete_assessment(assessment_id):
        flash("Penilaian dihapus.", "success")
    else:
        flash("Gagal menghapus penilaian.", "danger")
    return redirect(url_for("portal.admin_stats"))


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
    
    if request.method == "POST":
        school_id = request.form.get("school_id")
        room_ids = request.form.getlist("room_ids", type=int)
        
        # For sekolah role, only allow updating their own school
        if user.get("role") == "sekolah" and user_school:
            school_id = str(user_school["id"])
        
        if school_id:
            try:
                count = update_school_rooms(int(school_id), room_ids)
                flash(f"Berhasil menyimpan {count} ruangan.", "success")
            except Exception as e:
                flash(f"Error: {e}", "danger")
    
    all_rooms = list_portal_rooms()
    schools = [user_school] if user_school else list_portal_schools()
    
    # Get saved room IDs for current school
    saved_room_ids = set()
    current_school_id = None
    if user_school:
        current_school_id = user_school["id"]
    elif request.args.get("school_id"):
        current_school_id = int(request.args.get("school_id"))
    
    if current_school_id:
        from .queries import list_school_rooms
        saved_rooms = list_school_rooms(current_school_id)
        saved_room_ids = {r["room_id"] for r in saved_rooms}
    
    missing_fields = _compute_missing_profile_fields(user_school) if user_school else []
    show_profile_modal = bool(missing_fields)
    kecamatan_list = list_kecamatan()
    kelurahan_list = list_kelurahan()  # full list to allow sekolah update

    return render_template(
        "portal/sekolah_rooms.html",
        all_rooms=all_rooms,
        schools=schools,
        user_school=user_school,
        saved_room_ids=saved_room_ids,
        school_profile=user_school,
        missing_fields=missing_fields,
        show_profile_modal=show_profile_modal,
        coordinator_contacts=_build_coordinator_contacts(user_school),
        kecamatan_list=kecamatan_list,
        kelurahan_list=kelurahan_list,
    )


# ===== Admin Routes =====


@portal_bp.route("/admin/stats")
@role_required("admin")
def admin_stats() -> Response:
    """Admin view of portal statistics."""
    # Trigger reload
    period_id = request.args.get("period_id", type=int)
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
    
    stats = fetch_portal_stats(period_id)
    from .queries import fetch_score_distribution
    score_dist = fetch_score_distribution(period_id)
    recent_assessments = list_recent_assessments(
        period_id=period_id,
        jenjang=jenjang_filter,
        order=order,
    )
    top_schools = fetch_top_schools(period_id=period_id)
    bottom_schools = fetch_bottom_schools(period_id=period_id)
    photo_order = request.args.get("photo_order", "random")
    random_photos = fetch_random_photos(period_id=period_id, order=photo_order, limit=24)
    school_avg_map = fetch_school_avg_scores(period_id=period_id)
    periods = list_periods()
    all_schools = list_portal_schools()
    all_staff = list_all_staff()
    
    return render_template(
        "portal/admin_stats.html",
        stats=stats,
        score_dist=score_dist,
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
        all_schools=all_schools,
        all_staff=all_staff,
    )


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
    from .queries import fetch_map_data
    data = fetch_map_data(period_id)
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

    if request.method == "POST":
        payload = _build_profile_payload(request.form)
        errors = _validate_profile_data(payload)
        if errors:
            for err in errors:
                flash(err, "warning")
        else:
            _save_school_profile(school["id"], payload)
            flash("Profil sekolah berhasil diperbarui.", "success")
            return redirect(url_for("portal.sekolah_profile"))

    meta = {**(school.get("metadata") or {}), **(_build_profile_payload(request.form) if request.method == "POST" else {})}
    kecamatan_list = list_kecamatan()
    kelurahan_list = list_kelurahan()
    return render_template(
        "portal/school_profile.html",
        school=school,
        meta=meta,
        missing_fields=_compute_missing_profile_fields(school),
        kecamatan_list=kecamatan_list,
        kelurahan_list=kelurahan_list,
    )


@portal_bp.route("/admin/photos")
@role_required("admin")
def admin_photos_partial() -> Response:
    """Return gallery grid partial for photo order changes (AJAX)."""
    period_id = request.args.get("period_id", type=int)
    photo_order = request.args.get("photo_order", "random")
    photos = fetch_random_photos(period_id=period_id, order=photo_order, limit=24)
    return render_template("portal/_gallery_grid.html", random_photos=photos)


@portal_bp.route("/admin/related-photos")
@role_required("admin")
def admin_related_photos() -> Response:
    """Return related photos for the same school and room type (AJAX JSON)."""
    from .queries import fetch_related_photos
    school_id = request.args.get("school_id", type=int)
    room_id = request.args.get("room_id", type=int)
    
    if not school_id or not room_id:
        return jsonify([])
    
    photos = fetch_related_photos(school_id=school_id, room_id=room_id, limit=10)
    
    # Format photo URLs
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
    
    return jsonify(result)

@portal_bp.route("/admin/periods", methods=["POST"])
@role_required("admin")
def create_period_route() -> Response:
    """Create a new period."""
    name = request.form.get("name")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    is_active = request.form.get("is_active") == "on"
    
    if not all([name, start_date, end_date]):
        flash("Mohon lengkapi data periode.", "warning")
    else:
        try:
            create_period(name, start_date, end_date, is_active)
            flash("Periode berhasil dibuat.", "success")
        except Exception as e:
            flash(f"Error: {e}", "danger")
        
    return redirect(url_for("portal.admin_stats"))


@portal_bp.route("/admin/assign", methods=["POST"])
@role_required("admin")
def assign_assessment_route() -> Response:
    """Assign assessment to staff."""
    school_id = request.form.get("school_id")
    staff_id = request.form.get("staff_id")
    period_id = request.form.get("period_id")
    
    if not all([school_id, staff_id]):
        flash("Pilih sekolah dan staff.", "warning")
    else:
        try:
            pid = int(period_id) if period_id else None
            assign_assessment(int(school_id), int(staff_id), pid)
            flash("Draft penilaian berhasil dibuat untuk staff.", "success")
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
    return render_template(
        "portal/admin_setup.html",
        rooms=rooms,
        schools=schools,
        kecamatan_list=kecamatan_list,
        kelurahan_list=kelurahan_list,
    )


@portal_bp.route("/admin/setup/room", methods=["POST"])
@role_required("admin")
def add_room() -> Response:
    """Add a new room type."""
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    category = request.form.get("category", "umum").strip()
    sort_order = int(request.form.get("sort_order", 0))
    
    if not name:
        flash("Nama ruangan wajib diisi.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        create_room(name, description, category, sort_order)
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
    
    if not room_id or not name:
        flash("Room ID dan nama aspek wajib diisi.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        create_aspect(int(room_id), name, description, sort_order)
        flash(f"Aspek '{name}' berhasil ditambahkan.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/aspects/batch", methods=["POST"])
@role_required("admin")
def add_aspects_batch() -> Response:
    """Add multiple aspects at once (JSON API)."""
    data = request.get_json()
    aspects = data.get("aspects", [])
    
    if not aspects:
        return jsonify({"success": False, "error": "No aspects provided"})
    
    created_count = 0
    errors = []
    
    for item in aspects:
        room_id = item.get("roomId")
        name = item.get("name", "").strip()
        
        if not room_id or not name:
            errors.append(f"Missing room_id or name for aspect")
            continue
        
        try:
            create_aspect(int(room_id), name, None, 0)
            created_count += 1
        except Exception as e:
            errors.append(f"Error creating '{name}': {str(e)}")
    
    if created_count > 0:
        flash(f"{created_count} aspek berhasil ditambahkan.", "success")
    
    return jsonify({
        "success": created_count > 0,
        "created": created_count,
        "errors": errors
    })


@portal_bp.route("/admin/setup/room/<int:room_id>", methods=["POST"])
@role_required("admin")
def edit_room(room_id: int) -> Response:
    """Update an existing room."""
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    category = request.form.get("category", "umum").strip()
    sort_order = int(request.form.get("sort_order", 0))
    active = request.form.get("active") == "on"
    
    if not name:
        flash("Nama ruangan wajib diisi.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        result = update_room(room_id, name, description, category, sort_order, active)
        if result:
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
            new_status
        )
        if result:
            status_text = "diaktifkan" if new_status else "dinonaktifkan"
            flash(f"Ruangan '{room['name']}' berhasil {status_text}.", "success")
        else:
            flash("Gagal mengubah status ruangan.", "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup") + f"#room-{room_id}")


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
            new_status
        )
        if result:
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
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    sort_order = int(request.form.get("sort_order", 0))
    active = request.form.get("active") == "on"
    
    if not name:
        flash("Nama aspek wajib diisi.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        result = update_aspect(aspect_id, name, description, sort_order, active)
        if result:
            flash(f"Aspek '{name}' berhasil diperbarui.", "success")
        else:
            flash("Aspek tidak ditemukan.", "warning")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))


@portal_bp.route("/admin/setup/aspect/<int:aspect_id>/delete", methods=["POST"])
@role_required("admin")
def delete_aspect_route(aspect_id: int) -> Response:
    """Delete an aspect."""
    aspect = get_aspect_by_id(aspect_id)
    if not aspect:
        flash("Aspek tidak ditemukan.", "warning")
        return redirect(url_for("portal.admin_setup"))
    
    try:
        if delete_aspect(aspect_id):
            flash(f"Aspek '{aspect['name']}' berhasil dihapus.", "success")
        else:
            flash("Gagal menghapus aspek.", "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect(url_for("portal.admin_setup"))

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
        create_school(npsn, name, jenjang, alamat, kelurahan_id, status)
        flash(f"Sekolah '{name}' berhasil ditambahkan.", "success")
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
                    "portal/register_school.html",
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
            return render_template("portal/register_school.html", npsn=npsn, email=email)
        
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
            return render_template("portal/register_school.html", npsn=npsn, email=email)
    
    return render_template(
        "portal/register_school.html",
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
        "portal/sidak_planner.html",
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
