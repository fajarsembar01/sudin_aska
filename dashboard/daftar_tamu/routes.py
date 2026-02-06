"""Routes for Daftar Tamu (guestbook) module."""

from __future__ import annotations

import csv
import json
import math
import os
from io import BytesIO, StringIO
from pathlib import Path
from datetime import date, datetime
from typing import Optional

from flask import Blueprint, Response, jsonify, render_template, request, url_for, send_file, redirect, flash
from psycopg2.extras import Json
from urllib.parse import quote_plus
from PIL import Image, ImageDraw, ImageFont
import qrcode

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
    list_admin_public_transactions,
    list_admin_transactions,
    list_guest_candidates,
    list_general_guest_candidates,
    list_general_guests_admin,
    list_purpose_keyword_rows,
    list_purpose_keywords,
    list_contact_priority_rows,
    list_school_public_transactions,
    list_school_transactions,
    update_contact_priority,
    set_purpose_keyword_active,
    upsert_purpose_keyword,
    update_public_transaction_status,
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


def _parse_guest_payload(raw: Optional[str]) -> tuple[list[int], list[int]]:
    """Parse guest payload list into (sudin_ids, umum_ids)."""
    if not raw:
        return [], []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return [], []
    if not isinstance(payload, list):
        return [], []
    sudin_ids: list[int] = []
    umum_ids: list[int] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        guest_type = (item.get("type") or "").strip().lower()
        guest_id = item.get("id")
        try:
            guest_id = int(guest_id)
        except (TypeError, ValueError):
            continue
        if guest_type == "umum":
            umum_ids.append(guest_id)
        else:
            sudin_ids.append(guest_id)
    # Deduplicate while preserving order
    def _dedupe(values: list[int]) -> list[int]:
        seen = set()
        output = []
        for val in values:
            if val in seen:
                continue
            seen.add(val)
            output.append(val)
        return output

    return _dedupe(sudin_ids), _dedupe(umum_ids)


def _web_aska_base_url() -> str:
    base = (
        os.getenv("WEB_ASKA_BASE_URL")
        or os.getenv("WEB_ASKA_PUBLIC_URL")
        or os.getenv("ASKA_PUBLIC_BASE_URL")
        or "https://web_aska.app"
    )
    base = (base or "").strip()
    if base and not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base.rstrip("/")


def _build_guestbook_qr(target_url: str, size: int = 1024) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    qr_img = qr_img.resize((size, size), Image.LANCZOS)

    base_dir = Path(__file__).resolve().parents[2]
    logo_candidates = [
        base_dir / "web_aska" / "static" / "favicon.ico",
        base_dir / "web_aska" / "static" / "logo.png",
    ]
    logo = None
    for logo_path in logo_candidates:
        if not logo_path.exists():
            continue
        try:
            logo = Image.open(logo_path)
            if getattr(logo, "is_animated", False):
                logo.seek(0)
            logo = logo.convert("RGBA")
            break
        except Exception:
            logo = None
            continue

    if logo is not None:
        # Keep logo small to preserve QR readability (<= ~18% of width).
        logo_size = int(size * 0.16)
        logo.thumbnail((logo_size, logo_size), Image.LANCZOS)
        pos = ((size - logo.width) // 2, (size - logo.height) // 2)
        padding = int(logo_size * 0.08)
        bg_box = Image.new(
            "RGBA",
            (logo.width + padding * 2, logo.height + padding * 2),
            (255, 255, 255, 235),
        )
        bg_pos = (pos[0] - padding, pos[1] - padding)
        qr_img.paste(bg_box, bg_pos, bg_box)
        qr_img.paste(logo, pos, logo)
    return qr_img


def _measure_multiline(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, spacing: int = 4) -> tuple[int, int]:
    if hasattr(draw, "multiline_textbbox"):
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    if hasattr(draw, "multiline_textsize"):
        return draw.multiline_textsize(text, font=font, spacing=spacing)
    # Fallback
    lines = text.splitlines() or [text]
    widths = [draw.textlength(line, font=font) if hasattr(draw, "textlength") else len(line) * 6 for line in lines]
    return int(max(widths) if widths else 0), int(len(lines) * 12)


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


def _build_area_contacts(school: Optional[dict], message: Optional[str] = None) -> list[dict]:
    if not school:
        return []
    area_name = (school.get("kecamatan_name") or "").strip()
    if not message:
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


@daftar_tamu_bp.route("/admin/umum")
@role_required("admin")
def admin_general_guests() -> Response:
    search_query = (request.args.get("q") or "").strip()
    verified_raw = (request.args.get("verified") or "").strip().lower()
    deleted_raw = (request.args.get("deleted") or "").strip().lower()
    verified = None
    if verified_raw == "true":
        verified = True
    elif verified_raw == "false":
        verified = False
    deleted = None
    if deleted_raw == "true":
        deleted = True
    elif deleted_raw == "false":
        deleted = False
    page = _to_int(request.args.get("page"), 1)
    per_page = _to_int(request.args.get("per_page"), 20)
    per_page = max(10, min(per_page, 100))
    rows, total_rows = list_general_guests_admin(
        search_query=search_query,
        verified=verified,
        deleted=deleted,
        page=page,
        per_page=per_page,
    )
    total_pages = max(1, math.ceil(total_rows / per_page)) if total_rows else 1
    if page > total_pages:
        page = total_pages
        rows, total_rows = list_general_guests_admin(
            search_query=search_query,
            verified=verified,
            deleted=deleted,
            page=page,
            per_page=per_page,
        )

    return render_template(
        "daftar_tamu/admin_general_guests.html",
        rows=rows,
        total_rows=total_rows,
        total_pages=total_pages,
        page=page,
        per_page=per_page,
        search_query=search_query,
        verified_filter=verified_raw,
        deleted_filter=deleted_raw,
    )


@daftar_tamu_bp.route("/admin/umum-transactions")
@role_required("admin")
def admin_public_transactions() -> Response:
    status = (request.args.get("status") or "").strip().lower()
    search_query = (request.args.get("q") or "").strip()
    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    per_page = _to_int(request.args.get("per_page"), 10)
    per_page = max(5, min(per_page, 100))
    page = _to_int(request.args.get("page"), 1)
    page = max(1, page)

    rows, total_rows = list_admin_public_transactions(
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
        rows, total_rows = list_admin_public_transactions(
            status=status,
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            page=page,
            per_page=per_page,
        )

    return render_template(
        "daftar_tamu/admin_public_transactions.html",
        rows=rows,
        status=status,
        search_query=search_query,
        page=page,
        per_page=per_page,
        total_rows=total_rows,
        total_pages=total_pages,
        date_from_str=date_from.isoformat() if date_from else "",
        date_to_str=date_to.isoformat() if date_to else "",
    )


@daftar_tamu_bp.route("/admin/tujuan-kunjungan", methods=["GET", "POST"])
@role_required("admin")
def admin_purpose_keywords() -> Response:
    user = current_user()
    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower()
        if action == "add":
            keyword = (request.form.get("keyword") or "").strip()
            try:
                upsert_purpose_keyword(keyword=keyword, created_by=user.get("id"))
            except ValueError as exc:
                flash(str(exc), "danger")
            else:
                flash("Kata kunci tujuan disimpan.", "success")
        elif action == "toggle":
            keyword_id = _to_int(request.form.get("keyword_id"), 0)
            active_raw = (request.form.get("active") or "true").strip().lower()
            active = active_raw in ("1", "true", "yes", "on")
            if keyword_id <= 0:
                flash("Data kata kunci tidak valid.", "danger")
            else:
                ok = set_purpose_keyword_active(keyword_id=keyword_id, active=active)
                if ok:
                    flash("Status kata kunci diperbarui.", "success")
                else:
                    flash("Kata kunci tidak ditemukan.", "danger")
        else:
            flash("Aksi tidak dikenali.", "warning")
        return redirect(url_for("daftar_tamu.admin_purpose_keywords"))

    rows = list_purpose_keyword_rows(limit=400)
    return render_template(
        "daftar_tamu/admin_purpose_keywords.html",
        rows=rows,
    )


@daftar_tamu_bp.route("/admin/kontak-prioritas", methods=["GET", "POST"])
@role_required("admin")
def admin_contact_priority() -> Response:
    if request.method == "POST":
        keyword_id = _to_int(request.form.get("keyword_id"), 0)
        sort_order = _to_int(request.form.get("sort_order"), 0)
        active = (request.form.get("active") or "").strip().lower() == "true"
        if keyword_id <= 0 or sort_order <= 0:
            flash("Data prioritas tidak valid.", "danger")
        else:
            ok = update_contact_priority(keyword_id=keyword_id, sort_order=sort_order, active=active)
            if ok:
                flash("Prioritas kontak diperbarui.", "success")
            else:
                flash("Prioritas kontak tidak ditemukan.", "danger")
        return redirect(url_for("daftar_tamu.admin_contact_priority"))

    rows = list_contact_priority_rows(limit=50)
    return render_template(
        "daftar_tamu/admin_contact_priority.html",
        rows=rows,
    )


@daftar_tamu_bp.route("/admin/umum-transactions/<int:transaction_id>/approve", methods=["POST"])
@role_required("admin")
def admin_public_transaction_approve(transaction_id: int) -> Response:
    user = current_user()
    note = (request.form.get("reviewer_note") or "").strip()
    try:
        ok = update_public_transaction_status(
            transaction_id=transaction_id,
            status="approved",
            reviewer_id=user["id"],
            reviewer_notes=note or None,
        )
    except ValueError:
        ok = False
    if not ok:
        return jsonify({"success": False, "message": "Gagal memperbarui transaksi."}), 400
    return redirect(url_for("daftar_tamu.admin_public_transactions"))


@daftar_tamu_bp.route("/admin/umum-transactions/<int:transaction_id>/reject", methods=["POST"])
@role_required("admin")
def admin_public_transaction_reject(transaction_id: int) -> Response:
    user = current_user()
    note = (request.form.get("reviewer_note") or "").strip()
    if not note:
        return jsonify({"success": False, "message": "Catatan penolakan wajib diisi."}), 400
    try:
        ok = update_public_transaction_status(
            transaction_id=transaction_id,
            status="rejected",
            reviewer_id=user["id"],
            reviewer_notes=note,
        )
    except ValueError:
        ok = False
    if not ok:
        return jsonify({"success": False, "message": "Gagal memperbarui transaksi."}), 400
    return redirect(url_for("daftar_tamu.admin_public_transactions"))


@daftar_tamu_bp.route("/admin/umum/<int:guest_id>/verify", methods=["POST"])
@role_required("admin")
def admin_verify_general_guest(guest_id: int) -> Response:
    user = current_user()
    is_verified_raw = (request.form.get("is_verified") or "true").strip().lower()
    is_verified = is_verified_raw in ("1", "true", "yes", "on")
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE daftar_tamu_general_guests
            SET is_verified = %s,
                verified_by = %s,
                verified_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                updated_at = NOW()
            WHERE id = %s
              AND is_deleted = FALSE
            """,
            (is_verified, user.get("id"), is_verified, guest_id),
        )
        if cur.rowcount == 0:
            return jsonify({"success": False, "message": "Tamu umum tidak ditemukan atau sudah dihapus."}), 404
    return jsonify({"success": True, "is_verified": is_verified})


@daftar_tamu_bp.route("/admin/umum/<int:guest_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_general_guest(guest_id: int) -> Response:
    user = current_user()
    is_deleted_raw = (request.form.get("is_deleted") or "true").strip().lower()
    is_deleted = is_deleted_raw in ("1", "true", "yes", "on")
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE daftar_tamu_general_guests
            SET is_deleted = %s,
                deleted_by = CASE WHEN %s THEN %s ELSE NULL END,
                deleted_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                updated_at = NOW()
            WHERE id = %s
            """,
            (is_deleted, is_deleted, user.get("id"), is_deleted, guest_id),
        )
        if cur.rowcount == 0:
            return jsonify({"success": False, "message": "Tamu umum tidak ditemukan."}), 404
    return jsonify({"success": True, "is_deleted": is_deleted})


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

    public_status = (request.args.get("public_status") or "").strip().lower()
    public_per_page = _to_int(request.args.get("public_per_page"), 5)
    public_per_page = max(3, min(public_per_page, 50))
    public_page = _to_int(request.args.get("public_page"), 1)
    public_page = max(1, public_page)

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

    public_rows, public_total_rows = list_school_public_transactions(
        school_id=school["id"],
        status=public_status,
        page=public_page,
        per_page=public_per_page,
    )
    public_total_pages = max(1, math.ceil(public_total_rows / public_per_page)) if public_total_rows else 1
    if public_page > public_total_pages:
        public_page = public_total_pages
        public_rows, public_total_rows = list_school_public_transactions(
            school_id=school["id"],
            status=public_status,
            page=public_page,
            per_page=public_per_page,
        )

    return render_template(
        "daftar_tamu/sekolah_dashboard.html",
        school=school,
        user_school=school,
        guestbook_public_url=f"{_web_aska_base_url()}/buku-tamu/{school.get('npsn')}",
        area_contacts=_build_area_contacts(school),
        purpose_keywords=list_purpose_keywords(active_only=True),
        rows=rows,
        public_rows=public_rows,
        public_status=public_status,
        public_page=public_page,
        public_per_page=public_per_page,
        public_total_rows=public_total_rows,
        public_total_pages=public_total_pages,
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


@daftar_tamu_bp.route("/sekolah/guest-search-umum")
@role_required("sekolah")
def sekolah_general_guest_search() -> Response:
    query = (request.args.get("q") or "").strip()
    limit = _to_int(request.args.get("limit"), 20)
    results = list_general_guest_candidates(query, limit=limit)
    return jsonify({"success": True, "results": results})


@daftar_tamu_bp.route("/umum", methods=["POST"])
@role_required("sekolah", "admin")
def create_general_guest() -> Response:
    user = current_user()
    full_name = (request.form.get("full_name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    instansi = (request.form.get("instansi") or "").strip()
    jabatan = (request.form.get("jabatan") or "").strip()
    if not full_name:
        return jsonify({"success": False, "message": "Nama tamu wajib diisi."}), 400
    if phone:
        phone = _sanitize_phone(phone)

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO daftar_tamu_general_guests (full_name, phone, instansi, jabatan, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, full_name, phone, instansi, jabatan, is_verified
            """,
            (full_name, phone or None, instansi or None, jabatan or None, user.get("id")),
        )
        row = cur.fetchone()
        guest = dict(row) if row else {}

        cur.execute(
            """
            SELECT COUNT(*) AS name_count,
                   MAX(CASE WHEN is_verified THEN 1 ELSE 0 END) AS has_verified
            FROM daftar_tamu_general_guests
            WHERE lower(full_name) = lower(%s)
            """,
            (full_name,),
        )
        stats = dict(cur.fetchone() or {})

    guest["has_duplicate"] = int(stats.get("name_count") or 0) > 1
    guest["has_verified"] = bool(stats.get("has_verified"))
    return jsonify({"success": True, "guest": guest})


@daftar_tamu_bp.route("/sekolah/area-contacts")
@role_required("sekolah")
def sekolah_area_contacts() -> Response:
    """Return area contacts for the current school (used by guestbook modal)."""
    user = current_user()
    school = _fetch_school_for_user(user.get("id"))
    if not school:
        return jsonify({"success": False, "message": "Akun sekolah belum terhubung."}), 400
    message = None
    transaction_id_raw = request.args.get("transaction_id")
    if transaction_id_raw:
        try:
            transaction_id = int(transaction_id_raw)
        except (TypeError, ValueError):
            transaction_id = None
        if transaction_id:
            detail = get_transaction_detail(transaction_id)
            if detail and detail.get("school_id") == school.get("id"):
                guest_names = [
                    (g.get("full_name") or g.get("email") or "").strip()
                    for g in (detail.get("guests") or [])
                ]
                guest_names = [name for name in guest_names if name]
                guest_text = ", ".join(guest_names) if guest_names else "-"
                photo_url = None
                photo_path = detail.get("photo_path")
                if photo_path:
                    photo_name = photo_path.split("uploads/portal/")[-1]
                    photo_url = url_for("portal.uploaded_file", filename=photo_name, _external=True)
                message_lines = [
                    f"Halo, kami dari {school.get('name')} (NPSN {school.get('npsn')}) baru mengisi buku tamu.",
                    f"Tamu: {guest_text}",
                ]
                if photo_url:
                    message_lines.append(f"Foto: {photo_url}")
                message_lines.append("Mohon bantuan percepatan verifikasi.")
                message = "\n".join(message_lines)
    contacts = _build_area_contacts(school, message=message)
    return jsonify({"success": True, "contacts": contacts, "user_school": school})


@daftar_tamu_bp.route("/sekolah/umum-transactions/<int:transaction_id>/approve", methods=["POST"])
@role_required("sekolah")
def sekolah_approve_public_transaction(transaction_id: int) -> Response:
    user = current_user()
    school = _fetch_school_for_user(user.get("id"))
    if not school:
        return jsonify({"success": False, "message": "Akun sekolah belum terhubung."}), 400
    reviewer_notes = (request.form.get("reviewer_notes") or "").strip()
    success = update_public_transaction_status(
        transaction_id=transaction_id,
        status="approved",
        reviewer_id=user.get("id"),
        reviewer_notes=reviewer_notes or None,
        school_id=school.get("id"),
    )
    if not success:
        return jsonify({"success": False, "message": "Transaksi tidak ditemukan."}), 404
    return redirect(url_for("daftar_tamu.sekolah_guestbook", _anchor="publicGuestbook"))


@daftar_tamu_bp.route("/sekolah/umum-transactions/<int:transaction_id>/reject", methods=["POST"])
@role_required("sekolah")
def sekolah_reject_public_transaction(transaction_id: int) -> Response:
    user = current_user()
    school = _fetch_school_for_user(user.get("id"))
    if not school:
        return jsonify({"success": False, "message": "Akun sekolah belum terhubung."}), 400
    reviewer_notes = (request.form.get("reviewer_notes") or "").strip()
    success = update_public_transaction_status(
        transaction_id=transaction_id,
        status="rejected",
        reviewer_id=user.get("id"),
        reviewer_notes=reviewer_notes or None,
        school_id=school.get("id"),
    )
    if not success:
        return jsonify({"success": False, "message": "Transaksi tidak ditemukan."}), 404
    return redirect(url_for("daftar_tamu.sekolah_guestbook", _anchor="publicGuestbook"))


@daftar_tamu_bp.route("/sekolah/qr")
@role_required("sekolah")
def sekolah_guestbook_qr() -> Response:
    user = current_user()
    school = _fetch_school_for_user(user.get("id"))
    if not school:
        return jsonify({"success": False, "message": "Akun sekolah belum terhubung."}), 400

    fmt = (request.args.get("format") or "png").strip().lower()
    paper = (request.args.get("paper") or "a4").strip().lower()
    if fmt not in {"png", "pdf"}:
        fmt = "png"
    if paper not in {"a4", "a5"}:
        paper = "a4"

    target_url = f"{_web_aska_base_url()}/buku-tamu/{school.get('npsn')}"
    qr_img = _build_guestbook_qr(target_url, size=1024)

    if fmt == "pdf":
        page_sizes = {
            "a4": (2480, 3508),
            "a5": (1748, 2480),
        }
        width, height = page_sizes[paper]
        canvas = Image.new("RGB", (width, height), "white")
        qr_size = int(min(width, height) * 0.55)
        qr_resized = qr_img.resize((qr_size, qr_size), Image.LANCZOS).convert("RGB")
        qr_x = (width - qr_size) // 2
        qr_y = int(height * 0.18)
        canvas.paste(qr_resized, (qr_x, qr_y))

        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()
        text_lines = [
            school.get("name") or "Sekolah",
            f"NPSN {school.get('npsn')}",
            "Scan untuk buku tamu web_aska",
        ]
        text = "\n".join(text_lines)
        text_w, text_h = _measure_multiline(draw, text, font, spacing=4)
        text_x = (width - text_w) // 2
        text_y = qr_y + qr_size + 40
        draw.multiline_text((text_x, text_y), text, fill=(20, 20, 20), font=font, spacing=4, align="center")

        buf = BytesIO()
        canvas.save(buf, format="PDF")
        buf.seek(0)
        filename = f"qr_buku_tamu_{school.get('npsn')}_{paper}.pdf"
        return send_file(
            buf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    buf = BytesIO()
    qr_img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    filename = f"qr_buku_tamu_{school.get('npsn')}.png"
    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name=filename,
    )


@daftar_tamu_bp.route("/sekolah/transactions", methods=["POST"])
@role_required("sekolah")
def sekolah_create_transaction() -> Response:
    user = current_user()
    school = _fetch_school_for_user(user["id"])
    if not school:
        return jsonify({"success": False, "message": "Akun sekolah belum terhubung."}), 400

    sudin_ids, umum_ids = _parse_guest_payload(request.form.get("guest_payload"))
    if not sudin_ids and not umum_ids:
        sudin_ids = _parse_guest_ids(request.form.get("guest_ids"))
    if not sudin_ids and not umum_ids:
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

        for guest_id in sudin_ids:
            cur.execute(
                """
                INSERT INTO daftar_tamu_transaction_guests (transaction_id, guest_type, user_id)
                VALUES (%s, 'sudin', %s)
                ON CONFLICT (transaction_id, user_id) DO NOTHING
                """,
                (transaction_id, guest_id),
            )
        for guest_id in umum_ids:
            cur.execute(
                """
                INSERT INTO daftar_tamu_transaction_guests (transaction_id, guest_type, general_guest_id)
                VALUES (%s, 'umum', %s)
                ON CONFLICT (transaction_id, general_guest_id) DO NOTHING
                """,
                (transaction_id, guest_id),
            )

    return jsonify({"success": True, "transaction_id": transaction_id})
