"""Routes for Daftar Tamu (guestbook) module."""

from __future__ import annotations

import csv
import json
import math
from datetime import date, datetime
from io import StringIO
from typing import Optional

from flask import Blueprint, Response, jsonify, render_template, request
from psycopg2.extras import Json
from urllib.parse import quote_plus

from dashboard.auth import current_user, role_required
from dashboard.db_access import get_cursor
from dashboard.portal.permissions import can_access_aska, get_permission_summary, is_superadmin
from dashboard.portal.queries import fetch_admin_pending_summary, list_portal_kontak
from utils import current_jakarta_time

from .media import stamp_guestbook_photo
from .queries import (
    DEFAULT_SORT,
    SORT_OPTIONS,
    ensure_daftar_tamu_seed_data,
    fetch_dashboard_summary,
    fetch_guest_history,
    fetch_map_data,
    fetch_recent_visits,
    fetch_school_rankings,
    fetch_unvisited_schools,
    get_transaction_detail,
    list_admin_transactions,
    list_guest_candidates,
    list_school_transactions,
    update_transaction_status,
)

DAFTAR_TAMU_URL_PREFIX = "/daftar-tamu"


daftar_tamu_bp = Blueprint(
    "daftar_tamu",
    __name__,
    url_prefix=DAFTAR_TAMU_URL_PREFIX,
    template_folder="templates",
    static_folder="static",
)


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_int(value: Optional[str], default: int) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _parse_guest_ids(raw: Optional[str]) -> list[int]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    ids: list[int] = []
    for item in payload:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for val in ids:
        if val in seen:
            continue
        seen.add(val)
        unique_ids.append(val)
    return unique_ids


def _fetch_school_for_user(user_id: int) -> Optional[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.id,
                   s.npsn,
                   s.name,
                   s.jenjang,
                   s.alamat,
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


def _sanitize_phone(phone: str) -> str:
    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if digits_only.startswith("0"):
        digits_only = "62" + digits_only[1:]
    return digits_only


def _build_area_contacts(school: Optional[dict]) -> list[dict]:
    if not school:
        return []
    area_name = (school.get("kecamatan_name") or "").strip()
    message = (
        f"Halo, kami dari {school.get('name')} (NPSN {school.get('npsn')}) "
        "baru mengisi buku tamu dan mohon bantuan percepatan verifikasi."
    )
    contacts: list[dict] = []
    for row in list_portal_kontak():
        area = (row.get("wilayah") or "").strip()
        if not area:
            continue
        is_user_area = bool(area_name) and area.lower() in area_name.lower()
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
            is_active = row.get(active_key)
            if is_active is None:
                is_active = True
            phone_for_link = _sanitize_phone(phone)
            if not phone_for_link:
                continue
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
    # Prioritize contacts in the same area
    has_match = any(c["is_user_area"] for c in contacts)
    if has_match:
        contacts = [c for c in contacts if c["is_user_area"]]
    contacts.sort(key=lambda c: (not c["is_user_area"], c["area"], c["contact_index"]))
    return contacts


@daftar_tamu_bp.context_processor
def inject_daftar_tamu_context() -> dict:
    """Inject shared portal-like context into daftar tamu templates."""
    user = current_user()
    if not user:
        return {}

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
            pass

    context = {
        "permissions": get_permission_summary(user),
        "is_superadmin": is_superadmin(user),
        "can_access_aska": can_access_aska(user),
        "admin_pending": admin_pending,
    }
    if user.get("role") == "sekolah":
        school = _fetch_school_for_user(user.get("id"))
        context["user_school"] = school
        context["area_contacts"] = _build_area_contacts(school)
    return context


# ===============================
# Admin Dashboard
# ===============================

@daftar_tamu_bp.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard() -> Response:
    """Render admin monitoring dashboard for school guest visits."""
    ensure_daftar_tamu_seed_data()

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    search_query = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or DEFAULT_SORT).strip().lower()
    if sort not in SORT_OPTIONS:
        sort = DEFAULT_SORT

    per_page = _to_int(request.args.get("per_page"), 10)
    per_page = max(5, min(per_page, 100))

    page = _to_int(request.args.get("page"), 1)
    page = max(1, page)

    summary = fetch_dashboard_summary(date_from=date_from, date_to=date_to)
    rankings, total_rows = fetch_school_rankings(
        page=page,
        per_page=per_page,
        sort_key=sort,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
    )

    total_pages = max(1, math.ceil(total_rows / per_page)) if total_rows else 1
    if page > total_pages:
        page = total_pages
        rankings, total_rows = fetch_school_rankings(
            page=page,
            per_page=per_page,
            sort_key=sort,
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
        )

    unvisited_schools = fetch_unvisited_schools(limit=10, date_from=date_from, date_to=date_to)
    recent_visits = fetch_recent_visits(limit=8, date_from=date_from, date_to=date_to)

    date_from_str = date_from.isoformat() if date_from else ""
    date_to_str = date_to.isoformat() if date_to else ""

    return render_template(
        "daftar_tamu/admin_dashboard.html",
        summary=summary,
        rankings=rankings,
        unvisited_schools=unvisited_schools,
        recent_visits=recent_visits,
        page=page,
        per_page=per_page,
        total_rows=total_rows,
        total_pages=total_pages,
        sort=sort,
        search_query=search_query,
        date_from_str=date_from_str,
        date_to_str=date_to_str,
        today_str=date.today().isoformat(),
    )


@daftar_tamu_bp.route("/admin/map-data")
@role_required("admin")
def admin_map_data() -> Response:
    """Return map dots for daftar tamu dashboard."""
    ensure_daftar_tamu_seed_data()
    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    return jsonify(fetch_map_data(date_from=date_from, date_to=date_to))


@daftar_tamu_bp.route("/admin/export")
@role_required("admin")
def export_rankings() -> Response:
    """Export rankings in CSV/Excel-friendly CSV."""
    ensure_daftar_tamu_seed_data()

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    search_query = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or DEFAULT_SORT).strip().lower()
    if sort not in SORT_OPTIONS:
        sort = DEFAULT_SORT

    rows, _ = fetch_school_rankings(
        page=1,
        per_page=10000,
        sort_key=sort,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
    )

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Peringkat",
            "NPSN",
            "Nama Sekolah",
            "Jenjang",
            "Kecamatan",
            "Kelurahan",
            "Jumlah Kunjungan",
            "Kunjungan Terakhir",
            "Tamu Terakhir",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.get("rank"),
                row.get("npsn"),
                row.get("school_name"),
                row.get("jenjang"),
                row.get("kecamatan"),
                row.get("kelurahan"),
                row.get("visit_count"),
                row.get("last_visit_date").isoformat() if row.get("last_visit_date") else "",
                row.get("last_guest_display") or "",
            ]
        )

    file_format = (request.args.get("format") or "csv").strip().lower()
    if file_format == "excel":
        filename = f"ranking_daftar_tamu_{date.today().isoformat()}.xls"
        mimetype = "application/vnd.ms-excel"
    else:
        filename = f"ranking_daftar_tamu_{date.today().isoformat()}.csv"
        mimetype = "text/csv"

    response = Response(buffer.getvalue(), mimetype=mimetype)
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


# ===============================
# Admin Validation
# ===============================

@daftar_tamu_bp.route("/admin/validasi")
@role_required("admin")
def admin_validation() -> Response:
    status = (request.args.get("status") or "pending").strip().lower()
    if status not in ("pending", "approved", "rejected"):
        status = "pending"

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    search_query = (request.args.get("q") or "").strip()

    per_page = _to_int(request.args.get("per_page"), 10)
    per_page = max(5, min(per_page, 100))

    page = _to_int(request.args.get("page"), 1)
    page = max(1, page)

    rows, total_rows = list_admin_transactions(
        status=status,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )

    total_pages = max(1, math.ceil(total_rows / per_page)) if total_rows else 1
    if page > total_pages:
        page = total_pages
        rows, total_rows = list_admin_transactions(
            status=status,
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            page=page,
            per_page=per_page,
        )

    date_from_str = date_from.isoformat() if date_from else ""
    date_to_str = date_to.isoformat() if date_to else ""

    return render_template(
        "daftar_tamu/admin_validation.html",
        rows=rows,
        status=status,
        search_query=search_query,
        page=page,
        per_page=per_page,
        total_rows=total_rows,
        total_pages=total_pages,
        date_from_str=date_from_str,
        date_to_str=date_to_str,
        today_str=date.today().isoformat(),
    )


@daftar_tamu_bp.route("/admin/transactions/<int:transaction_id>")
@role_required("admin")
def admin_transaction_detail(transaction_id: int) -> Response:
    detail = get_transaction_detail(transaction_id)
    if not detail:
        return jsonify({"success": False, "message": "Transaksi tidak ditemukan"}), 404

    return jsonify({"success": True, "transaction": detail})


@daftar_tamu_bp.route("/admin/transactions/<int:transaction_id>/approve", methods=["POST"])
@role_required("admin")
def admin_transaction_approve(transaction_id: int) -> Response:
    user = current_user()
    note = (request.form.get("reviewer_note") or "").strip()
    try:
        ok = update_transaction_status(
            transaction_id=transaction_id,
            status="approved",
            reviewer_id=user["id"],
            reviewer_notes=note or None,
        )
    except ValueError:
        ok = False
    if not ok:
        return jsonify({"success": False, "message": "Gagal memperbarui transaksi."}), 400
    return jsonify({"success": True})


@daftar_tamu_bp.route("/admin/transactions/<int:transaction_id>/reject", methods=["POST"])
@role_required("admin")
def admin_transaction_reject(transaction_id: int) -> Response:
    user = current_user()
    note = (request.form.get("reviewer_note") or "").strip()
    if not note:
        return jsonify({"success": False, "message": "Catatan penolakan wajib diisi."}), 400
    try:
        ok = update_transaction_status(
            transaction_id=transaction_id,
            status="rejected",
            reviewer_id=user["id"],
            reviewer_notes=note,
        )
    except ValueError:
        ok = False
    if not ok:
        return jsonify({"success": False, "message": "Gagal memperbarui transaksi."}), 400
    return jsonify({"success": True})


@daftar_tamu_bp.route("/admin/guests/<int:user_id>/history")
@role_required("admin")
def admin_guest_history(user_id: int) -> Response:
    limit = _to_int(request.args.get("limit"), 20)
    offset = _to_int(request.args.get("offset"), 0)
    rows = fetch_guest_history(user_id=user_id, limit=limit, offset=offset)
    return jsonify({"success": True, "history": rows})


# ===============================
# Sekolah Guestbook
# ===============================

@daftar_tamu_bp.route("/sekolah")
@role_required("sekolah")
def sekolah_guestbook() -> Response:
    user = current_user()
    school = _fetch_school_for_user(user["id"])
    if not school:
        return render_template(
            "daftar_tamu/sekolah_dashboard.html",
            school=None,
            rows=[],
            status="",
            search_query="",
            page=1,
            per_page=10,
            total_rows=0,
            total_pages=1,
            date_from_str="",
            date_to_str="",
            today_str=date.today().isoformat(),
            error_message="Akun sekolah belum terhubung dengan data sekolah. Hubungi admin.",
        )

    status = (request.args.get("status") or "").strip().lower()
    search_query = (request.args.get("q") or "").strip()
    per_page = _to_int(request.args.get("per_page"), 10)
    per_page = max(5, min(per_page, 100))
    page = _to_int(request.args.get("page"), 1)
    page = max(1, page)

    rows, total_rows = list_school_transactions(
        school_id=school["id"],
        status=status,
        page=page,
        per_page=per_page,
    )
    total_pages = max(1, math.ceil(total_rows / per_page)) if total_rows else 1
    if page > total_pages:
        page = total_pages
        rows, total_rows = list_school_transactions(
            school_id=school["id"],
            status=status,
            page=page,
            per_page=per_page,
        )

    return render_template(
        "daftar_tamu/sekolah_dashboard.html",
        school=school,
        user_school=school,
        area_contacts=_build_area_contacts(school),
        rows=rows,
        status=status,
        search_query=search_query,
        page=page,
        per_page=per_page,
        total_rows=total_rows,
        total_pages=total_pages,
        date_from_str="",
        date_to_str="",
        today_str=date.today().isoformat(),
        error_message=None,
    )


@daftar_tamu_bp.route("/sekolah/guest-search")
@role_required("sekolah")
def sekolah_guest_search() -> Response:
    query = (request.args.get("q") or "").strip()
    limit = _to_int(request.args.get("limit"), 20)
    results = list_guest_candidates(query, limit=limit)
    return jsonify({"success": True, "results": results})


@daftar_tamu_bp.route("/sekolah/area-contacts")
@role_required("sekolah")
def sekolah_area_contacts() -> Response:
    """Return area contacts for the current school (used by guestbook modal)."""
    user = current_user()
    school = _fetch_school_for_user(user.get("id"))
    if not school:
        return jsonify({"success": False, "message": "Akun sekolah belum terhubung."}), 400
    contacts = _build_area_contacts(school)
    return jsonify({"success": True, "contacts": contacts, "user_school": school})


@daftar_tamu_bp.route("/sekolah/transactions", methods=["POST"])
@role_required("sekolah")
def sekolah_create_transaction() -> Response:
    user = current_user()
    school = _fetch_school_for_user(user["id"])
    if not school:
        return jsonify({"success": False, "message": "Akun sekolah belum terhubung."}), 400

    guest_ids = _parse_guest_ids(request.form.get("guest_ids"))
    if not guest_ids:
        return jsonify({"success": False, "message": "Pilih minimal satu tamu."}), 400

    purpose = (request.form.get("purpose") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    latitude_raw = request.form.get("latitude")
    longitude_raw = request.form.get("longitude")
    accuracy_raw = request.form.get("accuracy")
    try:
        latitude = float(latitude_raw)
        longitude = float(longitude_raw)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Lokasi GPS tidak valid."}), 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"success": False, "message": "Lokasi GPS di luar jangkauan."}), 400

    if "photo" not in request.files:
        return jsonify({"success": False, "message": "Foto wajib diunggah."}), 400

    photo = request.files["photo"]
    if not photo or not photo.filename:
        return jsonify({"success": False, "message": "Foto wajib diunggah."}), 400

    visit_at = current_jakarta_time()

    try:
        stamp_result = stamp_guestbook_photo(
            file_storage=photo,
            latitude=latitude,
            longitude=longitude,
            captured_at=visit_at,
            school_label=school.get("name"),
        )
    except Exception as exc:
        return jsonify({"success": False, "message": f"Gagal memproses foto: {exc}"}), 500

    metadata = {
        "accuracy": float(accuracy_raw) if accuracy_raw else None,
        "user_agent": request.headers.get("User-Agent"),
        "map_provider": stamp_result.get("map_provider"),
        "map_error": stamp_result.get("map_error"),
    }

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO daftar_tamu_transactions (
                school_id,
                visit_at,
                purpose,
                notes,
                photo_path,
                photo_raw_path,
                latitude,
                longitude,
                status,
                reviewed_by,
                reviewed_at,
                reviewer_notes,
                created_by,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', NULL, NULL, NULL, %s, %s)
            RETURNING id
            """,
            (
                school["id"],
                visit_at,
                purpose or None,
                notes or None,
                stamp_result["stamped_path"],
                stamp_result.get("raw_path"),
                latitude,
                longitude,
                user["id"],
                Json(metadata),
            ),
        )
        tx_row = cur.fetchone()
        transaction_id = int(tx_row["id"]) if tx_row else None

        for guest_id in guest_ids:
            cur.execute(
                """
                INSERT INTO daftar_tamu_transaction_guests (transaction_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT (transaction_id, user_id) DO NOTHING
                """,
                (transaction_id, guest_id),
            )

    return jsonify({"success": True, "transaction_id": transaction_id})
