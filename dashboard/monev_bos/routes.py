from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from dashboard.auth import role_required, current_user
from . import monev_bos_bp, queries

@monev_bos_bp.route("/")
@role_required("admin", "staff", "sekolah")
def index():
    user = current_user()
    if user.get("role") == "admin":
        return redirect(url_for("monev_bos.admin_dashboard"))
    elif user.get("role") == "sekolah":
        return redirect(url_for("monev_bos.sekolah_dashboard"))
    else:
        return redirect(url_for("monev_bos.staff_dashboard"))

@monev_bos_bp.context_processor
def inject_monev_bos_context() -> dict:
    user = current_user()
    user_app_notifications = {"unread_count": 0, "total_count": 0}
    if user and user.get("role") in ["staff", "coordinator", "sekolah"]:
        try:
            from dashboard.daftar_tamu.queries import fetch_user_notification_summary, USER_APP_NOTIFICATION_CATEGORIES
            user_app_notifications = fetch_user_notification_summary(
                user_id=int(user["id"]),
                categories=list(USER_APP_NOTIFICATION_CATEGORIES)
            )
        except Exception:
            pass

    admin_pending = {
        "pending_users": 0,
        "pending_assignment_requests": 0,
        "pending_team_member_requests": 0,
        "pending_reopen_requests": 0,
        "pending_guestbook": 0,
        "pending_monev_edit_requests": 0,
        "pending_call_center": 0,
        "total": 0,
    }
    if user and user.get("role") == "admin":
        try:
            from dashboard.portal.queries import fetch_admin_pending_summary
            admin_pending = fetch_admin_pending_summary()
        except Exception:
            pass

    submitted_reports_count = 0
    if user and user.get("role") in ["admin", "staff"]:
        try:
            submitted_reports_count = queries.get_submitted_reports_count()
        except Exception:
            pass

    return {
        "app_title": "MONEV BOS/BOP",
        "admin_pending": admin_pending,
        "user_app_notifications": user_app_notifications,
        "submitted_reports_count": submitted_reports_count,
        "undo_window_seconds": 7,
    }

from datetime import datetime

@monev_bos_bp.route("/admin")
@role_required("admin")
def admin_dashboard():
    active_period = queries.get_active_period()
    return render_template("monev_bos/admin/dashboard.html", active_period=active_period)

@monev_bos_bp.route("/admin/periods", methods=["GET", "POST"])
@role_required("admin")
def admin_periods():
    current_year = datetime.now().year
    
    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate_year":
            year = int(request.form.get("year"))
            queries.ensure_periods_for_year(year)
            flash(f"Periode TW 1-4 Tahun {year} berhasil disiapkan.", "success")
        elif action == "set_active":
            period_id = int(request.form.get("period_id"))
            queries.set_active_period(period_id)
            flash("Periode berhasil diaktifkan.", "success")
        elif action == "deactivate":
            period_id = int(request.form.get("period_id"))
            queries.deactivate_period(period_id)
            flash("Periode berhasil dinonaktifkan.", "success")
        elif action == "set_deadline":
            period_id = int(request.form.get("period_id"))
            deadline = datetime.strptime(request.form.get("deadline"), "%Y-%m-%d").date()
            queries.update_period_deadline(period_id, deadline)
            flash("Deadline berhasil diperbarui.", "success")
        return redirect(url_for("monev_bos.admin_periods"))
    
    # Auto-generate current year if empty
    available_years = queries.get_available_years()
    if not available_years:
        queries.ensure_periods_for_year(current_year)
        available_years = [current_year]
    
    selected_year = request.args.get("year", available_years[0] if available_years else current_year, type=int)
    
    # Always ensure all 4 TW exist for selected year (fixes missing or wrong dates)
    queries.ensure_periods_for_year(selected_year)
    periods = queries.list_periods_by_year(selected_year)
    available_years = queries.get_available_years()
    
    return render_template("monev_bos/admin/periods.html", 
                           periods=periods, 
                           available_years=available_years,
                           selected_year=selected_year,
                           current_year=current_year)

@monev_bos_bp.route("/admin/checklists", methods=["GET", "POST"])
@role_required("admin")
def admin_checklists():
    if request.method == "POST":
        action = request.form.get("action")
        expense_type_ids = [int(x) for x in request.form.getlist("expense_type_ids") if x.isdigit()]
        if action == "create":
            name = request.form.get("name")
            description = request.form.get("description")
            sort_order = int(request.form.get("sort_order", 0))
            queries.create_checklist(name, description, sort_order, expense_type_ids=expense_type_ids)
            flash("Checklist berhasil ditambahkan", "success")
        elif action == "update":
            checklist_id = int(request.form.get("checklist_id"))
            name = request.form.get("name")
            description = request.form.get("description")
            sort_order = int(request.form.get("sort_order", 0))
            is_active = request.form.get("is_active") == "on"
            queries.update_checklist(checklist_id, name, description, sort_order, is_active, expense_type_ids=expense_type_ids)
            flash("Checklist berhasil diupdate", "success")
        elif action == "delete":
            checklist_id = int(request.form.get("checklist_id"))
            queries.delete_checklist(checklist_id)
            flash("Checklist berhasil dihapus", "success")
        return redirect(url_for("monev_bos.admin_checklists"))

    checklists = queries.list_checklists(include_inactive=True)
    expense_types = queries.list_expense_types(include_inactive=False)
    return render_template("monev_bos/admin/checklists.html", checklists=checklists, expense_types=expense_types)

@monev_bos_bp.route("/admin/master-activities", methods=["GET", "POST"])
@role_required("admin")
def admin_master_activities():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            name = request.form.get("name")
            code_prefix = request.form.get("code_prefix")
            fund_source = request.form.get("fund_source", "ALL")
            if name:
                queries.create_master_activity(name, code_prefix, fund_source)
                flash("Master Nama Kegiatan berhasil ditambahkan", "success")
            else:
                flash("Nama kegiatan wajib diisi.", "warning")
        elif action == "update":
            master_id = int(request.form.get("master_id"))
            name = request.form.get("name")
            code_prefix = request.form.get("code_prefix")
            fund_source = request.form.get("fund_source", "ALL")
            is_active = request.form.get("is_active") == "on"
            if name:
                queries.update_master_activity(master_id, name, code_prefix, fund_source, is_active)
                flash("Master Nama Kegiatan berhasil diperbarui", "success")
            else:
                flash("Nama kegiatan wajib diisi.", "warning")
        elif action == "delete":
            master_id = int(request.form.get("master_id"))
            queries.delete_master_activity(master_id)
            flash("Master Nama Kegiatan berhasil dihapus", "success")
        return redirect(url_for("monev_bos.admin_master_activities"))

    master_activities = queries.list_master_activities(include_inactive=True)
    return render_template("monev_bos/admin/master_activities.html", master_activities=master_activities)


@monev_bos_bp.route("/admin/expense-types", methods=["GET", "POST"])
@role_required("admin")
def admin_expense_types():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            name = (request.form.get("name") or "").strip()
            code = (request.form.get("code") or "").strip()
            description = (request.form.get("description") or "").strip()
            sort_order = int(request.form.get("sort_order", 0) or 0)
            if name:
                queries.create_expense_type(name, code, description, sort_order)
                flash("Jenis Belanja berhasil ditambahkan.", "success")
            else:
                flash("Nama Jenis Belanja wajib diisi.", "warning")
        elif action == "update":
            expense_type_id = int(request.form.get("expense_type_id"))
            name = (request.form.get("name") or "").strip()
            code = (request.form.get("code") or "").strip()
            description = (request.form.get("description") or "").strip()
            sort_order = int(request.form.get("sort_order", 0) or 0)
            is_active = request.form.get("is_active") == "on"
            if name and expense_type_id:
                queries.update_expense_type(expense_type_id, name, code, description, sort_order, is_active)
                flash("Jenis Belanja berhasil diperbarui.", "success")
        elif action == "delete":
            expense_type_id = int(request.form.get("expense_type_id"))
            if expense_type_id:
                queries.delete_expense_type(expense_type_id)
                flash("Jenis Belanja berhasil dihapus.", "success")
        return redirect(url_for("monev_bos.admin_expense_types"))

    expense_types = queries.list_expense_types(include_inactive=True)
    return render_template("monev_bos/admin/expense_types.html", expense_types=expense_types)

@monev_bos_bp.route("/admin/edit-requests", methods=["GET", "POST"])
@role_required("admin")
def admin_edit_requests():
    user = current_user()
    if request.method == "POST":
        action = request.form.get("action")
        request_id = int(request.form.get("request_id"))
        review_notes = request.form.get("review_notes", "").strip()

        if action == "approve":
            queries.approve_edit_request(request_id, user["id"], review_notes or None)
            flash("Pengajuan edit telah disetujui dan data kegiatan berhasil diperbarui.", "success")
        elif action == "reject":
            queries.reject_edit_request(request_id, user["id"], review_notes or None)
            flash("Pengajuan edit ditolak.", "info")

        return redirect(url_for("monev_bos.admin_edit_requests"))

    status_filter = request.args.get("status", "pending")
    edit_requests = queries.list_edit_requests(status=status_filter if status_filter != "all" else None)
    return render_template("monev_bos/admin/edit_requests.html",
                           edit_requests=edit_requests,
                           status_filter=status_filter)



@monev_bos_bp.route("/admin/teams", methods=["GET", "POST"])
@role_required("admin")
def admin_teams():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            name = request.form.get("name")
            leader_id = request.form.get("leader_id")
            leader_id = int(leader_id) if leader_id else None
            queries.create_team(name, leader_id)
            flash("Tim berhasil dibuat", "success")
        elif action == "update_leader":
            team_id = int(request.form.get("team_id"))
            leader_id = request.form.get("leader_id")
            leader_id = int(leader_id) if leader_id else None
            queries.update_team_leader(team_id, leader_id)
            flash("Ketua tim berhasil diupdate", "success")
        elif action == "delete":
            team_id = int(request.form.get("team_id"))
            queries.delete_team(team_id)
            flash("Tim berhasil dihapus", "success")
        elif action == "assign":
            team_id = int(request.form.get("team_id"))
            school_id = int(request.form.get("school_id"))
            period_id = int(request.form.get("period_id"))
            queries.assign_team_to_school(team_id, school_id, period_id)
            flash("Sekolah berhasil ditugaskan ke tim", "success")
        elif action == "unassign":
            assignment_id = int(request.form.get("assignment_id"))
            queries.unassign_school(assignment_id)
            flash("Tugas sekolah berhasil dilepas", "success")
        return redirect(url_for("monev_bos.admin_teams"))

    teams = queries.list_teams()
    staff_users = queries.get_staff_users()
    sekolah_users = queries.get_sekolah_users()
    active_period = queries.get_active_period()
    assignments = queries.list_assignments(active_period["id"]) if active_period else []

    return render_template(
        "monev_bos/admin/teams.html", 
        teams=teams, 
        staff_users=staff_users,
        sekolah_users=sekolah_users,
        active_period=active_period,
        assignments=assignments
    )

@monev_bos_bp.route("/sekolah")
@role_required("sekolah")
def sekolah_dashboard():
    user = current_user()
    school_info = queries.get_school_kecamatan_and_admin_wa(user["id"])
    
    # Available years filter
    available_years = queries.get_available_years()
    current_year = datetime.now().year
    if current_year not in available_years:
        available_years.insert(0, current_year)
    if not available_years:
        available_years = [2026, 2025]
    
    selected_year = request.args.get("year", type=int)
    if not selected_year or selected_year not in available_years:
        selected_year = available_years[0]
        
    existing_periods = queries.list_periods_by_year(selected_year)
    period_map = {p["tw"]: p for p in existing_periods}

    tw_cards = []
    tw_names = {1: "TW I", 2: "TW II", 3: "TW III", 4: "TW IV"}
    tw_months = {1: "Januari - Maret", 2: "April - Juni", 3: "Juli - September", 4: "Oktober - Desember"}

    for tw in range(1, 5):
        period = period_map.get(tw)
        if period:
            period_id = period["id"]
            is_active = period["is_active"]
            report = queries.get_school_report(user["id"], period_id)
        else:
            period_id = None
            is_active = False
            report = None

        bosp_receipt = float(report["bosp_receipt_amount"]) if report and report.get("bosp_receipt_amount") else 0.0
        bop_receipt = float(report["bop_receipt_amount"]) if report and report.get("bop_receipt_amount") else 0.0
        total_receipt = bosp_receipt + bop_receipt

        activities = queries.list_activities(report["id"]) if report else []
        bos_realized = float(sum(a["realized_amount"] for a in activities if a["fund_source"] == "BOS"))
        bop_realized = float(sum(a["realized_amount"] for a in activities if a["fund_source"] == "BOP"))
        total_realized = float(sum(a["realized_amount"] for a in activities))
        remaining_balance = total_receipt - total_realized

        valid_count = sum(1 for a in activities if a["status"] == "valid")
        invalid_count = sum(1 for a in activities if a["status"] == "invalid")
        in_review_count = sum(1 for a in activities if a["status"] == "in_review")
        pending_count = sum(1 for a in activities if a["status"] == "pending")

        status_key = "closed"
        if is_active:
            if not report:
                status_key = "unfilled"
            else:
                status_key = report["status"]

        card = {
            "tw": tw,
            "tw_label": tw_names[tw],
            "tw_months": tw_months[tw],
            "period": period,
            "period_id": period_id,
            "is_active": is_active,
            "report": report,
            "status_key": status_key,
            "bosp_receipt": bosp_receipt,
            "bop_receipt": bop_receipt,
            "total_receipt": total_receipt,
            "bos_realized": bos_realized,
            "bop_realized": bop_realized,
            "total_realized": total_realized,
            "remaining_balance": remaining_balance,
            "total_activities": len(activities),
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "in_review_count": in_review_count,
            "pending_count": pending_count,
        }
        tw_cards.append(card)

    year_stats = {
        "total_bosp_receipt": sum(c["bosp_receipt"] for c in tw_cards),
        "total_bop_receipt": sum(c["bop_receipt"] for c in tw_cards),
        "total_receipt": sum(c["total_receipt"] for c in tw_cards),
        "total_realized": sum(c["total_realized"] for c in tw_cards),
        "total_remaining": sum(c["remaining_balance"] for c in tw_cards),
        "filled_tw_count": sum(1 for c in tw_cards if c["report"]),
        "completed_tw_count": sum(1 for c in tw_cards if c["report"] and c["report"]["status"] in ["completed", "completed_with_notes"]),
        "revision_tw_count": sum(1 for c in tw_cards if c["report"] and c["report"]["status"] == "needs_revision"),
    }

    return render_template(
        "monev_bos/sekolah/dashboard.html",
        selected_year=selected_year,
        available_years=available_years,
        tw_cards=tw_cards,
        year_stats=year_stats,
        school_info=school_info
    )

def _parse_float(val) -> float:
    if not val:
        return 0.0
    val_str = str(val).replace(".", "").replace(",", ".")
    try:
        return float(val_str)
    except ValueError:
        return 0.0

@monev_bos_bp.route("/sekolah/report", methods=["GET", "POST"])
@role_required("sekolah")
def sekolah_report_form():
    user = current_user()
    period_id = request.args.get("period_id", type=int)
    if not period_id:
        flash("Pilih triwulan terlebih dahulu.", "warning")
        return redirect(url_for("monev_bos.sekolah_dashboard"))
    
    active_periods = queries.get_active_periods()
    active_period = next((p for p in active_periods if p["id"] == period_id), None)
    if not active_period:
        flash("Periode tidak ditemukan atau belum dibuka.", "warning")
        return redirect(url_for("monev_bos.sekolah_dashboard"))

    report = queries.get_school_report(user["id"], active_period["id"])
    
    if request.method == "POST":
        if report and report["status"] not in ["draft", "needs_revision"]:
            flash("Laporan sudah tidak bisa diubah.", "warning")
            return redirect(url_for("monev_bos.sekolah_dashboard"))
            
        bosp = _parse_float(request.form.get("bosp_amount"))
        bop = _parse_float(request.form.get("bop_amount"))
        queries.save_school_report_receipts(user["id"], active_period["id"], bosp, bop)
        flash("Data penerimaan dana berhasil disimpan.", "success")
        return redirect(url_for("monev_bos.sekolah_funds", period_id=period_id))

    return render_template("monev_bos/sekolah/form.html", active_period=active_period, report=report)

@monev_bos_bp.route("/sekolah/funds")
@role_required("sekolah")
def sekolah_funds():
    user = current_user()
    period_id = request.args.get("period_id", type=int)
    if not period_id:
        flash("Pilih triwulan terlebih dahulu.", "warning")
        return redirect(url_for("monev_bos.sekolah_dashboard"))
    
    active_periods = queries.get_active_periods()
    active_period = next((p for p in active_periods if p["id"] == period_id), None)
    if not active_period:
        flash("Periode tidak ditemukan atau belum dibuka.", "warning")
        return redirect(url_for("monev_bos.sekolah_dashboard"))

    report = queries.get_school_report(user["id"], active_period["id"])
    if not report:
        flash("Silakan isi data penerimaan dana terlebih dahulu.", "warning")
        return redirect(url_for("monev_bos.sekolah_report_form", period_id=period_id))

    all_activities = queries.list_activities(report["id"])
    
    bos_activities = [a for a in all_activities if a["fund_source"] == "BOS"]
    bop_activities = [a for a in all_activities if a["fund_source"] == "BOP"]
    
    bos_realized = sum(a["realized_amount"] for a in bos_activities)
    bop_realized = sum(a["realized_amount"] for a in bop_activities)

    return render_template("monev_bos/sekolah/funds.html", 
                           active_period=active_period, 
                           report=report,
                           bos_count=len(bos_activities),
                           bop_count=len(bop_activities),
                           bos_realized=bos_realized,
                           bop_realized=bop_realized)

import os
import io
from PIL import Image
from werkzeug.utils import secure_filename

def _compress_image_file(file_storage, target_kb=100) -> bytes:
    """Auto-compress image to <= target_kb (100KB) automatically."""
    target_bytes = target_kb * 1024
    
    file_storage.seek(0)
    img = Image.open(file_storage)
    
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        
    quality = 80
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=quality, optimize=True)
    
    while output.tell() > target_bytes and quality > 20:
        quality -= 15
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=quality, optimize=True)
        
    width, height = img.size
    while output.tell() > target_bytes and width > 300 and height > 300:
        width = int(width * 0.75)
        height = int(height * 0.75)
        resized_img = img.resize((width, height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        resized_img.save(output, format="JPEG", quality=45, optimize=True)
        
    return output.getvalue()

def _save_uploaded_file(file, base_dir, sub_path, max_size_bytes=100 * 1024):
    if not file or file.filename == '':
        return None, "File tidak ada"
    
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
        return None, "Dokumen hanya menerima file gambar (JPG, PNG, WEBP, atau BMP)."
    
    upload_dir = os.path.join(base_dir, sub_path)
    os.makedirs(upload_dir, exist_ok=True)
    
    try:
        compressed_bytes = _compress_image_file(file, target_kb=max_size_bytes // 1024)
        save_name = os.path.splitext(filename)[0] + ".jpg"
        file_path = os.path.join(upload_dir, save_name)
        with open(file_path, "wb") as f:
            f.write(compressed_bytes)
        return f"static/uploads/{sub_path}/{save_name}", None
    except Exception:
        return None, "File gambar gagal diproses. Pastikan file tidak rusak."

def _save_camera_photo(data_url, base_dir, sub_path):
    if not data_url:
        return None, "Foto kegiatan wajib diambil langsung dari kamera."
    if "," not in data_url:
        return None, "Format foto kamera tidak valid."

    try:
        header, encoded = data_url.split(",", 1)
        if not header.startswith("data:image/"):
            return None, "Format foto kamera harus berupa gambar."
        image_bytes = base64.b64decode(encoded)
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        upload_dir = os.path.join(base_dir, sub_path)
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"camera_{uuid.uuid4().hex[:10]}.jpg"
        file_path = os.path.join(upload_dir, filename)
        img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        img.save(file_path, format="JPEG", quality=75, optimize=True)
        return f"static/uploads/{sub_path}/{filename}", None
    except Exception:
        return None, "Foto kamera gagal diproses. Silakan ambil ulang foto."

@monev_bos_bp.route("/sekolah/activities", methods=["GET", "POST"])
@role_required("sekolah")
def sekolah_activities():
    user = current_user()
    period_id = request.args.get("period_id", type=int) or (request.form.get("period_id", type=int) if request.method == "POST" else None)
    fund_source = request.args.get("fund_source", "BOS") or (request.form.get("fund_source", "BOS") if request.method == "POST" else "BOS")
    if fund_source not in ["BOS", "BOP"]:
        fund_source = "BOS"

    if not period_id:
        flash("Pilih triwulan terlebih dahulu.", "warning")
        return redirect(url_for("monev_bos.sekolah_dashboard"))
    
    active_periods = queries.get_active_periods()
    active_period = next((p for p in active_periods if p["id"] == period_id), None)
    if not active_period:
        flash("Periode tidak ditemukan atau belum dibuka.", "warning")
        return redirect(url_for("monev_bos.sekolah_dashboard"))

    report = queries.get_school_report(user["id"], active_period["id"])
    if not report:
        flash("Silakan isi data penerimaan dana terlebih dahulu.", "warning")
        return redirect(url_for("monev_bos.sekolah_report_form", period_id=period_id))

    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_receipts":
            if report and report["status"] not in ["draft", "needs_revision"]:
                flash("Laporan sudah tidak bisa diubah.", "warning")
                return redirect(url_for("monev_bos.sekolah_activities", period_id=period_id, fund_source=fund_source))
            
            bosp = _parse_float(request.form.get("bosp_amount"))
            bop = _parse_float(request.form.get("bop_amount"))
            queries.save_school_report_receipts(user["id"], active_period["id"], bosp, bop)
            flash(f"Total Penerimaan Dana {fund_source} berhasil diperbarui.", "success")
            return redirect(url_for("monev_bos.sekolah_activities", period_id=period_id, fund_source=fund_source))

        if action == "add_activity":
            target_fund_source = request.form.get("fund_source", fund_source)
            vendor_id_raw = request.form.get("vendor_id")
            vendor_id = int(vendor_id_raw) if vendor_id_raw and vendor_id_raw.isdigit() else None
            vendor_name = request.form.get("vendor_name")
            if vendor_id and not vendor_name:
                v_obj = queries.get_vendor_by_id(vendor_id)
                if v_obj:
                    vendor_name = v_obj["name"]

            expense_type_id_raw = request.form.get("expense_type_id")
            expense_type_id = int(expense_type_id_raw) if expense_type_id_raw and expense_type_id_raw.isdigit() else None

            data = {
                "activity_code": request.form.get("activity_code") or request.form.get("bku_number") or "-",
                "activity_name": request.form.get("activity_name"),
                "account_code": request.form.get("account_code"),
                "expense_type_id": expense_type_id,
                "realized_amount": _parse_float(request.form.get("realized_amount")),
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "bku_number": request.form.get("bku_number"),
                "item_name": request.form.get("item_name"),
                "item_specs": request.form.get("item_specs"),
                "item_quantity": int(request.form.get("item_quantity", 0) or 0)
            }
            activity_id = queries.create_activity(report["id"], target_fund_source, data)
            
            # Handle mandatory document uploads (Faktur/Kwitansi & Bukti Transfer)
            base_dir = os.path.join(monev_bos_bp.root_path, "..", "static", "uploads")
            doc_inv_file = request.files.get("doc_invoice")
            doc_tf_file = request.files.get("doc_transfer")

            if not doc_inv_file or not doc_inv_file.filename:
                queries.delete_activity(activity_id)
                flash("Dokumen Faktur & Kwitansi wajib diunggah.", "danger")
                return redirect(url_for("monev_bos.sekolah_activities", period_id=period_id, fund_source=fund_source))

            if not doc_tf_file or not doc_tf_file.filename:
                queries.delete_activity(activity_id)
                flash("Dokumen Bukti Transfer wajib diunggah.", "danger")
                return redirect(url_for("monev_bos.sekolah_activities", period_id=period_id, fund_source=fund_source))

            # Handle optional camera photo or file upload (Foto Kegiatan / Barang)
            field_photo_file = request.files.get("doc_field_photo") or request.files.get("field_photo")
            if field_photo_file and field_photo_file.filename != '':
                sub_path = f"monev_bos/{report['id']}/{activity_id}/field_photo"
                saved_path, err_msg = _save_uploaded_file(field_photo_file, base_dir, sub_path, max_size_bytes=100 * 1024)
                if saved_path:
                    queries.add_activity_doc(activity_id, "field_photo", saved_path, field_photo_file.content_length or 0, user["id"])
            else:
                field_photo_data = request.form.get("field_photo_data")
                if field_photo_data:
                    saved_path, err_msg = _save_camera_photo(field_photo_data, base_dir, f"monev_bos/{report['id']}/{activity_id}/field_photo")
                    if err_msg:
                        queries.delete_activity(activity_id)
                        flash(err_msg, "danger")
                        return redirect(url_for("monev_bos.sekolah_activities", period_id=period_id, fund_source=fund_source))
                    queries.add_activity_doc(activity_id, "field_photo", saved_path, 0, user["id"])

            # Handle mandatory document file uploads
            has_error = False
            for doc_type in ["invoice", "transfer"]:
                file = request.files.get(f"doc_{doc_type}")
                if file and file.filename != '':
                    sub_path = f"monev_bos/{report['id']}/{activity_id}/{doc_type}"
                    saved_path, err_msg = _save_uploaded_file(file, base_dir, sub_path, max_size_bytes=100 * 1024)
                    if err_msg:
                        flash(err_msg, "danger")
                        has_error = True
                    elif saved_path:
                        queries.add_activity_doc(activity_id, doc_type, saved_path, file.content_length or 0, user["id"])

            if not has_error:
                flash("Kegiatan berhasil ditambahkan.", "success")
            
        elif action == "delete_activity":
            activity_id = int(request.form.get("activity_id"))
            queries.delete_activity(activity_id)
            flash("Kegiatan berhasil dihapus.", "success")

        elif action == "request_edit":
            # Pengajuan reopen edit untuk kegiatan yang berstatus Sesuai (valid)
            activity_id = int(request.form.get("activity_id"))
            reason = request.form.get("reason", "").strip()
            act = queries.get_activity_by_id(activity_id)
            if not act:
                flash("Kegiatan tidak ditemukan.", "danger")
            elif not reason:
                flash("Alasan pengajuan reopen wajib diisi.", "warning")
            else:
                # Cancel any previous pending request
                queries.cancel_edit_request(activity_id)
                queries.create_edit_request(activity_id, user["id"], reason)
                
                # Fetch admin/coordinator info for school's kecamatan
                admin_info = queries.get_school_kecamatan_and_admin_wa(user["id"])
                if admin_info.get("admin_phone"):
                    import urllib.parse
                    wa_msg = (
                        f"Yth. Bapak/Ibu {admin_info['admin_name']} (Admin Wilayah Kecamatan {admin_info['kecamatan_name']}),\n\n"
                        f"Saya dari {admin_info['school_name']} mengajukan *Reopen Edit Kegiatan Monev BOS/BOP*:\n"
                        f"• Kode Kegiatan: {act['activity_code']}\n"
                        f"• Uraian: {act['activity_name']}\n"
                        f"• Nominal Realisasi: Rp {act.get('realized_amount', 0):,.0f}\n"
                        f"• Alasan Reopen: \"{reason}\"\n\n"
                        f"Mohon kesediaannya untuk meninjau dan membuka kunci edit kegiatan tersebut. Terima kasih."
                    )
                    wa_url = f"https://wa.me/{admin_info['admin_phone']}?text={urllib.parse.quote(wa_msg)}"
                    session["wa_reopen_prompt"] = {
                        "wa_url": wa_url,
                        "admin_name": admin_info["admin_name"],
                        "kecamatan_name": admin_info["kecamatan_name"],
                        "activity_code": act["activity_code"]
                    }
                
                flash("Pengajuan reopen edit berhasil dikirim ke admin. Silakan konfirmasi ke Admin Wilayah via WhatsApp.", "success")

        elif action == "edit_activity":
            activity_id = int(request.form.get("activity_id"))
            act = queries.get_activity_by_id(activity_id)

            # Jika sudah sesuai (valid), harus minta persetujuan admin
            if act and act.get("status") == "valid":
                flash("Kegiatan ini sudah divalidasi sebagai Sesuai. Edit harus melalui pengajuan perubahan ke admin.", "warning")
                return redirect(url_for("monev_bos.sekolah_activities", period_id=period_id, fund_source=fund_source))

            was_invalid = act and act.get("status") == "invalid"
            # Jika status revisi (invalid), simpan snapshot data lama dulu sebagai history
            if was_invalid:
                queries.save_activity_history(activity_id, user["id"], reason="Perbaikan data oleh sekolah saat status Revisi")

            vendor_id_raw = request.form.get("vendor_id")
            vendor_id = int(vendor_id_raw) if vendor_id_raw and vendor_id_raw.isdigit() else None
            vendor_name = request.form.get("vendor_name")
            if vendor_id and not vendor_name:
                v_obj = queries.get_vendor_by_id(vendor_id)
                if v_obj:
                    vendor_name = v_obj["name"]

            expense_type_id_raw = request.form.get("expense_type_id")
            expense_type_id = int(expense_type_id_raw) if expense_type_id_raw and expense_type_id_raw.isdigit() else None

            data = {
                "activity_code": request.form.get("activity_code") or (act and act.get("activity_code")) or request.form.get("bku_number") or "-",
                "activity_name": request.form.get("activity_name"),
                "account_code": request.form.get("account_code"),
                "expense_type_id": expense_type_id,
                "realized_amount": _parse_float(request.form.get("realized_amount")),
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "bku_number": request.form.get("bku_number"),
                "item_name": request.form.get("item_name"),
                "item_specs": request.form.get("item_specs"),
                "item_quantity": int(request.form.get("item_quantity", 0) or 0)
            }
            queries.update_activity(activity_id, data)
            
            # Kembalikan status kegiatan dari 'invalid' ke 'pending' (Menunggu Validasi Ulang Tim Audit)
            queries.update_activity_audit(activity_id, "pending", act.get("audit_notes") or "")

            # Kirim notifikasi in-app & siapkan WA prompt ke Staff Auditor jika sebelumnya berstatus revisi
            if was_invalid:
                queries.send_revised_activity_notification_to_staff(activity_id)
                staff_wa_info = queries.get_auditor_staff_wa_for_report(report["id"], report["school_id"], period_id, activity_id=activity_id)
                if staff_wa_info.get("staff_phone"):
                    import urllib.parse
                    wa_msg = (
                        f"Yth. Bapak/Ibu {staff_wa_info['staff_name']} (Tim Audit Monev BOS/BOP),\n\n"
                        f"Saya dari {report.get('school_name', 'Sekolah')} telah memperbarui/merevisi data kegiatan:\n"
                        f"• Kode Kegiatan: {act['activity_code']}\n"
                        f"• Uraian: {data['activity_name']}\n"
                        f"• Nominal Realisasi: Rp {data['realized_amount']:,.0f}\n\n"
                        f"Mohon kesediaannya untuk melakukan validasi ulang. Terima kasih."
                    )
                    wa_url = f"https://wa.me/{staff_wa_info['staff_phone']}?text={urllib.parse.quote(wa_msg)}"
                    session["wa_revision_prompt"] = {
                        "wa_url": wa_url,
                        "staff_name": staff_wa_info["staff_name"],
                        "activity_code": act["activity_code"]
                    }
            
            # Handle optional field photo (file upload or camera)
            field_photo_file = request.files.get("doc_field_photo") or request.files.get("field_photo")
            if field_photo_file and field_photo_file.filename != '':
                base_dir = os.path.join(monev_bos_bp.root_path, "..", "static", "uploads")
                sub_path = f"monev_bos/{report['id']}/{activity_id}/field_photo"
                saved_path, err_msg = _save_uploaded_file(field_photo_file, base_dir, sub_path, max_size_bytes=100 * 1024)
                if err_msg:
                    flash(err_msg, "danger")
                elif saved_path:
                    queries.add_activity_doc(activity_id, "field_photo", saved_path, field_photo_file.content_length or 0, user["id"])
            else:
                field_photo_data = request.form.get("field_photo_data")
                if field_photo_data:
                    base_dir = os.path.join(monev_bos_bp.root_path, "..", "static", "uploads")
                    saved_path, err_msg = _save_camera_photo(field_photo_data, base_dir, f"monev_bos/{report['id']}/{activity_id}/field_photo")
                    if err_msg:
                        flash(err_msg, "danger")
                        return redirect(url_for("monev_bos.sekolah_activities", period_id=period_id, fund_source=fund_source))
                    queries.add_activity_doc(activity_id, "field_photo", saved_path, 0, user["id"])

            # Handle optional file re-uploads
            for doc_type in ["transfer", "invoice"]:
                file = request.files.get(f"doc_{doc_type}")
                if file and file.filename != '':
                    sub_path = f"monev_bos/{report['id']}/{activity_id}/{doc_type}"
                    saved_path, err_msg = _save_uploaded_file(file, base_dir, sub_path, max_size_bytes=100 * 1024)
                    
                    if err_msg:
                        flash(err_msg, "danger")
                    elif saved_path:
                        queries.add_activity_doc(activity_id, doc_type, saved_path, file.content_length or 0, user["id"])
            
            flash("Perubahan kegiatan berhasil disimpan. Status kegiatan kini kembali Pending dan notifikasi telah dikirim ke Staff Audit.", "success")
            
        elif action == "submit_report":
            queries.submit_school_report(report["id"])
            flash("Laporan berhasil disubmit ke tim monev.", "success")
            return redirect(url_for("monev_bos.sekolah_dashboard"))

        return redirect(url_for("monev_bos.sekolah_activities", period_id=period_id, fund_source=fund_source))

    all_activities = queries.list_activities(report["id"])
    activities = [a for a in all_activities if a["fund_source"] == fund_source]
    
    total_receipt = report["bosp_receipt_amount"] if fund_source == "BOS" else report["bop_receipt_amount"]
    total_realized = sum(a["realized_amount"] for a in activities)
    remaining_balance = total_receipt - total_realized
    
    wa_prompt = session.pop("wa_reopen_prompt", None)
    wa_revision_prompt = session.pop("wa_revision_prompt", None)
    admin_info = queries.get_school_kecamatan_and_admin_wa(user["id"])
    staff_wa_info = queries.get_auditor_staff_wa_for_report(report["id"], report["school_id"], period_id)

    for act in activities:
        docs = queries.get_activity_docs(act["id"])
        act["docs"] = {doc["doc_type"]: doc for doc in docs}
        act["history"] = queries.get_activity_history(act["id"])
        act["pending_edit_request"] = queries.get_edit_request_by_activity(act["id"])
        if act["pending_edit_request"] and admin_info.get("admin_phone"):
            import urllib.parse
            req_reason = act["pending_edit_request"].get("reason") or "-"
            wa_msg = (
                f"Yth. Bapak/Ibu {admin_info['admin_name']} (Admin Wilayah Kecamatan {admin_info['kecamatan_name']}),\n\n"
                f"Saya dari {admin_info['school_name']} mengajukan *Reopen Edit Kegiatan Monev BOS/BOP*:\n"
                f"• Kode Kegiatan: {act['activity_code']}\n"
                f"• Uraian: {act['activity_name']}\n"
                f"• Nominal Realisasi: Rp {act.get('realized_amount', 0):,.0f}\n"
                f"• Alasan Reopen: \"{req_reason}\"\n\n"
                f"Mohon kesediaannya untuk meninjau dan membuka kunci edit kegiatan tersebut. Terima kasih."
            )
            act["wa_url"] = f"https://wa.me/{admin_info['admin_phone']}?text={urllib.parse.quote(wa_msg)}"

        # If activity is pending after revision and staff phone exists
        act_staff_wa = queries.get_auditor_staff_wa_for_report(report["id"], report["school_id"], period_id, activity_id=act["id"])
        if act["status"] == "pending" and act.get("history") and act_staff_wa.get("staff_phone"):
            import urllib.parse
            wa_msg_staff = (
                f"Yth. Bapak/Ibu {act_staff_wa['staff_name']} (Tim Audit Monev BOS/BOP),\n\n"
                f"Saya dari {report.get('school_name', 'Sekolah')} telah memperbarui/merevisi data kegiatan:\n"
                f"• Kode Kegiatan: {act['activity_code']}\n"
                f"• Uraian: {act['activity_name']}\n"
                f"• Nominal Realisasi: Rp {act.get('realized_amount', 0):,.0f}\n\n"
                f"Mohon kesediaannya untuk melakukan validasi ulang. Terima kasih."
            )
            act["staff_wa_url"] = f"https://wa.me/{act_staff_wa['staff_phone']}?text={urllib.parse.quote(wa_msg_staff)}"

    master_activities = queries.list_master_activities(include_inactive=False, fund_source=fund_source)
    expense_types = queries.list_expense_types(include_inactive=False)
    verified_vendors = queries.get_verified_vendors_for_school(report["school_id"])

    return render_template("monev_bos/sekolah/activities.html", 
                           active_period=active_period, 
                           report=report, 
                           activities=activities,
                           master_activities=master_activities,
                           expense_types=expense_types,
                           verified_vendors=verified_vendors,
                           fund_source=fund_source,
                           total_receipt=total_receipt,
                           total_realized=total_realized,
                           remaining_balance=remaining_balance,
                           wa_prompt=wa_prompt,
                           wa_revision_prompt=wa_revision_prompt,
                           admin_info=admin_info,
                           staff_wa_info=staff_wa_info)

@monev_bos_bp.route("/staff")
@role_required("staff", "admin")
def staff_dashboard():
    user = current_user()
    active_period = queries.get_active_period()
    teams = queries.get_teams_for_staff(user["id"])
    
    assigned_schools = []
    if active_period and teams:
        # Untuk simple MVP, ambil sekolah dari tim pertama
        # Idealnya bisa pilih tim jika staff ikut banyak tim
        team_id = teams[0]["id"] 
        assigned_schools = queries.get_schools_for_team(team_id, active_period["id"])
        
    return render_template("monev_bos/staff/dashboard.html", 
                           active_period=active_period, 
                           teams=teams, 
                           assigned_schools=assigned_schools)

@monev_bos_bp.route("/staff/my-team", methods=["GET", "POST"])
@role_required("staff", "admin")
def staff_my_team():
    user = current_user()
    teams = queries.get_teams_for_staff(user["id"])
    
    if not teams:
        flash("Anda belum dimasukkan ke tim manapun.", "warning")
        return redirect(url_for("monev_bos.staff_dashboard"))
        
    team = teams[0] # Ambil tim pertama
    
    if request.method == "POST":
        if not team["is_leader"]:
            flash("Hanya ketua tim yang bisa mengelola anggota.", "danger")
            return redirect(url_for("monev_bos.staff_my_team"))
            
        action = request.form.get("action")
        staff_id = int(request.form.get("staff_id"))
        
        if action == "add_member":
            queries.add_team_member(team["id"], staff_id)
            flash("Anggota berhasil ditambahkan.", "success")
        elif action == "remove_member":
            queries.remove_team_member(team["id"], staff_id)
            flash("Anggota berhasil dihapus.", "success")
            
        return redirect(url_for("monev_bos.staff_my_team"))

    members = queries.get_team_members(team["id"])
    all_staff = queries.get_staff_users() if team["is_leader"] else []
    
    # Filter out existing members
    member_ids = [m["id"] for m in members]
    available_staff = [s for s in all_staff if s["id"] not in member_ids]
    
    return render_template("monev_bos/staff/my_team.html", team=team, members=members, available_staff=available_staff)

@monev_bos_bp.route("/staff/audit/<int:report_id>", methods=["GET", "POST"])
@role_required("staff", "admin")
def staff_audit_report(report_id):
    user = current_user()
    report = queries.get_report_by_id(report_id)
    
    if not report:
        flash("Laporan tidak ditemukan.", "danger")
        return redirect(url_for("monev_bos.staff_dashboard"))
        
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_report_status":
            status = request.form.get("status")
            with queries.get_cursor(commit=True) as cur:
                cur.execute(
                    "UPDATE monev_bos_reports SET status = %s WHERE id = %s", 
                    (status, report_id)
                )
            queries.add_audit_log(report_id, None, user["id"], "UPDATE_STATUS", f"Mengubah status laporan menjadi {status}")
            flash(f"Status laporan diubah menjadi {status}", "success")
            return redirect(url_for("monev_bos.staff_audit_report", report_id=report_id))
    # Reset any stale in_review activity statuses back to pending when loading page
    with queries.get_cursor(commit=True) as cur:
        cur.execute("UPDATE monev_bos_activities SET status = 'pending' WHERE report_id = %s AND status = 'in_review'", (report_id,))

    fund_source = request.args.get("fund_source", "BOS").upper()
    if fund_source not in ["BOS", "BOP"]:
        fund_source = "BOS"

    checklists = queries.list_checklists(include_inactive=False)
    all_activities = queries.list_activities(report_id)
    activities = [act for act in all_activities if (act.get("fund_source") or "BOS").upper() == fund_source]
    for act in activities:
        docs = queries.get_activity_docs(act["id"])
        act["docs"] = {doc["doc_type"]: doc for doc in docs}
        # get live photos & school field photos list
        act["live_photos"] = [doc for doc in docs if doc["doc_type"] in ["live_photo", "field_photo"]]
        # get checklist results for this activity
        act["checklist_results"] = queries.get_activity_checklist_results(act["id"])
        act["checklists"] = queries.get_checklists_for_activity(act.get("expense_type_id"))

    activity_groups_by_name = {}
    for act in activities:
        name = (act.get("activity_name") or "Tanpa nama kegiatan").strip()
        group = activity_groups_by_name.setdefault(name, {
            "name": name,
            "total": 0,
            "pending": 0,
            "in_review": 0,
            "valid": 0,
            "invalid": 0,
            "ready_review": 0,
            "ready_submit": 0,
        })
        group["total"] += 1
        status = act.get("status") or "pending"
        if status in group:
            group[status] += 1

    activity_groups = list(activity_groups_by_name.values())
        
    audit_logs = queries.get_audit_logs(report_id)
    
    total_receipt = float(report.get("bosp_receipt_amount") or 0) if fund_source == "BOS" else float(report.get("bop_receipt_amount") or 0)
    total_realized = sum(float(act.get("realized_amount") or 0) for act in activities)
    remaining_balance = total_receipt - total_realized
    percent_spent = (total_realized / total_receipt * 100) if total_receipt > 0 else 0
    
    return render_template(
        "monev_bos/staff/audit_report.html",
        report=report,
        fund_source=fund_source,
        activities=activities,
        activity_groups=activity_groups,
        audit_logs=audit_logs,
        checklists=checklists,
        total_receipt=total_receipt,
        total_realized=total_realized,
        remaining_balance=remaining_balance,
        percent_spent=percent_spent,
    )

import base64
import uuid

@monev_bos_bp.route("/staff/audit/activity/<int:activity_id>", methods=["POST"])
@role_required("staff", "admin")
def staff_audit_activity(activity_id):
    user = current_user()
    act = queries.get_activity_by_id(activity_id)
    
    if not act:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
            return jsonify({"success": False, "message": "Kegiatan tidak ditemukan."}), 404
        flash("Kegiatan tidak ditemukan.", "danger")
        return redirect(url_for("monev_bos.staff_dashboard"))

    report_id_raw = request.form.get("report_id")
    if report_id_raw:
        try:
            report_id = int(report_id_raw)
        except (ValueError, TypeError):
            report_id = act.get("report_id") or 1
    else:
        report_id = act.get("report_id") or 1
    
    action = request.form.get("action")
    
    try:
        if action == "validate":
            status = request.form.get("status")
            if not status or status not in ["valid", "invalid", "in_review", "pending"]:
                if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
                    return jsonify({"success": False, "message": "Pilih status validasi yang sesuai."}), 400
                flash("Pilih status validasi yang valid (Sesuai atau Perlu Revisi).", "warning")
                return redirect(url_for("monev_bos.staff_audit_report", report_id=report_id))

            notes = request.form.get("audit_notes") or ""
            queries.update_activity_audit(activity_id, status, notes)
            
            # Save checklist (filtered by activity's expense_type_id)
            checklists = queries.get_checklists_for_activity(act.get("expense_type_id"))
            for cl in checklists:
                cl_status = request.form.get(f"checklist_{cl['id']}")
                cl_notes = request.form.get(f"checklist_notes_{cl['id']}") or ""
                if cl_status and cl_status in ["yes", "no", "na"]:
                    queries.save_checklist_result(activity_id, cl['id'], cl_status, cl_notes, user["id"])
                    
            status_label = "Sesuai" if status == "valid" else ("Tidak Sesuai (Revisi)" if status == "invalid" else ("Proses Audit" if status == "in_review" else "Pending"))
            queries.add_audit_log(report_id, activity_id, user["id"], "VALIDATE", f"Memvalidasi kegiatan status '{status_label}'" + (f": {notes}" if notes else ""))
            
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
                return jsonify({
                    "success": True,
                    "status": status,
                    "status_label": status_label,
                    "activity_id": activity_id,
                    "auditor_name": user.get("full_name") or user.get("email") or "Staff",
                    "message": f"Hasil validasi kegiatan berhasil disimpan ({status_label})."
                })

            flash("Hasil validasi kegiatan berhasil disimpan.", "success")
            return redirect(url_for("monev_bos.staff_audit_report", report_id=report_id))

        elif action == "start_audit":
            if act and act.get("status") in ["pending", "invalid"]:
                queries.update_activity_audit(activity_id, "in_review", act.get("audit_notes") or "")
                staff_name = user.get("full_name") or user.get("email") or "Staff"
                return jsonify({"success": True, "status": "in_review", "original_status": act.get("status"), "message": f"Status kegiatan diubah ke Proses Audit oleh {staff_name}"})
            return jsonify({"success": True, "status": act.get("status") if act else "pending"})

        elif action == "cancel_audit":
            target_status = request.form.get("original_status") or "pending"
            if target_status not in ["pending", "invalid"]:
                target_status = "pending"
            if act and act.get("status") == "in_review":
                queries.update_activity_audit(activity_id, target_status, act.get("audit_notes") or "")
                return jsonify({"success": True, "status": target_status, "message": f"Status dikembalikan ke {target_status}"})
            return jsonify({"success": True, "status": act.get("status") if act else target_status})
            
        elif action == "upload_photo":
            image_data = request.form.get("live_photo_data")
            if image_data:
                header, encoded = image_data.split(",", 1)
                data = base64.b64decode(encoded)
                
                filename = f"live_{uuid.uuid4().hex[:8]}.jpg"
                upload_dir = os.path.join(monev_bos_bp.root_path, "..", "static", "uploads", "monev_bos", str(report_id), str(activity_id), "live_photo")
                os.makedirs(upload_dir, exist_ok=True)
                
                file_path = os.path.join(upload_dir, filename)
                with open(file_path, "wb") as f:
                    f.write(data)
                    
                db_path = f"static/uploads/monev_bos/{report_id}/{activity_id}/live_photo/{filename}"
                queries.add_activity_doc(activity_id, "live_photo", db_path, len(data), user["id"])
                queries.add_audit_log(report_id, activity_id, user["id"], "UPLOAD_PHOTO", "Mengambil foto live lapangan")
                flash("Foto live berhasil disimpan.", "success")

    except Exception as e:
        import logging
        logging.error(f"Error processing staff audit activity {activity_id}: {e}", exc_info=True)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("Accept") == "application/json":
            return jsonify({"success": False, "message": f"Terjadi kesalahan pada server saat memproses validasi: {str(e)}"}), 500
        flash("Terjadi kesalahan pada server saat memproses validasi kegiatan.", "danger")

    return redirect(url_for("monev_bos.staff_audit_report", report_id=report_id))


# --- VENDOR MANAGEMENT ROUTES ---

@monev_bos_bp.route("/sekolah/vendors", methods=["GET", "POST"])
@role_required("sekolah")
def sekolah_vendors():
    user = current_user()
    school_id = user["id"]

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create_vendor":
            name = (request.form.get("name") or "").strip()
            npwp = (request.form.get("npwp") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            address = (request.form.get("address") or "").strip()
            owner_name = (request.form.get("owner_name") or "").strip()
            bank_name = (request.form.get("bank_name") or "").strip()
            bank_account = (request.form.get("bank_account") or "").strip()

            if not name:
                flash("Nama toko / vendor wajib diisi.", "warning")
            else:
                data = {
                    "name": name,
                    "npwp": npwp,
                    "phone": phone,
                    "address": address,
                    "owner_name": owner_name,
                    "bank_name": bank_name,
                    "bank_account": bank_account,
                }
                new_id = queries.create_vendor(school_id, data)
                if new_id:
                    flash(f"Vendor '{name}' berhasil didaftarkan dan menunggu verifikasi admin/staff.", "success")
                else:
                    flash("Gagal mendaftarkan vendor.", "danger")
            return redirect(url_for("monev_bos.sekolah_vendors"))

        elif action == "delete_vendor":
            vendor_id = request.form.get("vendor_id", type=int)
            if vendor_id and queries.delete_vendor(vendor_id, school_id):
                flash("Pendaftaran vendor berhasil dihapus.", "success")
            else:
                flash("Gagal menghapus vendor.", "danger")
            return redirect(url_for("monev_bos.sekolah_vendors"))

    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "")
    vendors = queries.list_school_vendors(school_id, status_filter if status_filter in ["pending", "verified", "rejected"] else None, search_query=search_query)
    master_banks = queries.get_master_banks()
    return render_template("monev_bos/sekolah/vendors.html", vendors=vendors, status_filter=status_filter, search_query=search_query, master_banks=master_banks)


@monev_bos_bp.route("/admin/vendors", methods=["GET", "POST"])
@role_required("admin", "staff")
def admin_vendors():
    user = current_user()

    if request.method == "POST":
        action = request.form.get("action", "")
        vendor_id = request.form.get("vendor_id", type=int)

        if action == "verify_vendor" and vendor_id:
            if queries.update_vendor_status(vendor_id, "verified", user["id"]):
                v_obj = queries.get_vendor_by_id(vendor_id)
                v_name = v_obj["name"] if v_obj else "Vendor"
                flash(f"Vendor '{v_name}' berhasil diverifikasi dan disetujui.", "success")
            else:
                flash("Gagal memverifikasi vendor.", "danger")
            return redirect(url_for("monev_bos.admin_vendors", status=request.args.get("status", ""), q=request.args.get("q", "")))

        elif action == "reject_vendor" and vendor_id:
            reason = (request.form.get("rejection_reason") or "").strip()
            if not reason:
                flash("Alasan penolakan vendor wajib diisi.", "warning")
            else:
                if queries.update_vendor_status(vendor_id, "rejected", user["id"], rejection_reason=reason):
                    flash("Vendor berhasil ditolak.", "info")
                else:
                    flash("Gagal menolak vendor.", "danger")
            return redirect(url_for("monev_bos.admin_vendors", status=request.args.get("status", ""), q=request.args.get("q", "")))

        elif action == "update_master_banks":
            if user.get("role") != "admin":
                flash("Hanya Admin yang berhak mengubah daftar pilihan bank.", "danger")
                return redirect(url_for("monev_bos.admin_vendors", status=request.args.get("status", ""), q=request.args.get("q", "")))

            bank_lines = request.form.get("bank_list", "").splitlines()
            bank_list = [b.strip() for b in bank_lines if b.strip()]
            if queries.save_master_banks(bank_list, user["id"]):
                flash("Daftar master pilihan bank berhasil diperbarui.", "success")
            else:
                flash("Gagal memperbarui daftar bank.", "danger")
            return redirect(url_for("monev_bos.admin_vendors", status=request.args.get("status", ""), q=request.args.get("q", "")))

    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "")
    vendors = queries.list_all_vendors_for_admin(status_filter if status_filter in ["pending", "verified", "rejected"] else None, search_query=search_query)
    master_banks = queries.get_master_banks()
    return render_template("monev_bos/admin/admin_vendors.html", vendors=vendors, status_filter=status_filter, search_query=search_query, master_banks=master_banks)

