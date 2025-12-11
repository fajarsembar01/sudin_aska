"""Routes for portal assessment system (PANBERSS)."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

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
        # reuse recent list but filtered by school
        other_assessments = list_recent_assessments(limit=50, period_id=None)
        other_assessments = [a for a in other_assessments if a["school_id"] == assessment["school_id"] and a["id"] != assessment_id]
        avg_map = fetch_school_avg_scores(period_id=None)
        school_avg = avg_map.get(assessment["school_id"])
    
    # Group scores by room
    rooms_scores = {}
    for s in scores:
        room_name = s["room_name"]
        if room_name not in rooms_scores:
            rooms_scores[room_name] = []
        rooms_scores[room_name].append(s)
    
    return render_template(
        "portal/assessment_view.html",
        assessment=assessment,
        rooms_scores=rooms_scores,
        user=user,
        photos_by_room=photos_by_room,
        room_notes=room_notes,
        other_assessments=other_assessments,
        school_avg=school_avg,
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
        from dashboard.db_access import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.npsn, s.name, s.jenjang, s.status,
                       l.name as kelurahan_name, k.name as kecamatan_name
                FROM dashboard_users u
                JOIN portal_schools s ON u.school_id = s.id
                LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
                LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
                WHERE u.id = %s
                """,
                (user["id"],),
            )
            row = cur.fetchone()
            if row:
                user_school = dict(row)
        
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
    
    return render_template(
        "portal/sekolah_rooms.html",
        all_rooms=all_rooms,
        schools=schools,
        user_school=user_school,
        saved_room_ids=saved_room_ids,
    )


# ===== Admin Routes =====


@portal_bp.route("/admin/stats")
@role_required("admin")
def admin_stats() -> Response:
    """Admin view of portal statistics."""
    # Trigger reload
    period_id = request.args.get("period_id", type=int)
    
    stats = fetch_portal_stats(period_id)
    from .queries import fetch_score_distribution
    score_dist = fetch_score_distribution(period_id)
    recent_assessments = list_recent_assessments(period_id=period_id)
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
    
    return render_template("portal/register_school.html")
