"""Routes for Daftar Tamu (guestbook) module."""

from __future__ import annotations

import base64
import csv
import json
import math
import os
from io import BytesIO, StringIO
import requests
from pathlib import Path
from datetime import date, datetime
from typing import Optional

from flask import Blueprint, Response, jsonify, render_template, request, url_for, send_file, redirect, flash, current_app
from psycopg2.extras import Json
from urllib.parse import quote_plus
from PIL import Image, ImageDraw, ImageFont
import qrcode

from dashboard.auth import current_user, role_required
from dashboard.db_access import get_cursor
from dashboard.portal.permissions import can_access_aska, get_permission_summary, is_superadmin
from dashboard.portal.queries import (
    fetch_admin_pending_summary,
    get_staff_assigned_schools,
    get_user_kecamatan_details,
    get_user_kecamatan_ids,
    list_portal_kontak,
    list_schools_by_kecamatan,
)
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
    fetch_school_visit_history,
    fetch_user_rankings,
    fetch_user_visit_history,
    fetch_unvisited_schools,
    fetch_school_pending_counts,
    get_transaction_detail,
    list_admin_public_school_summary,
    list_admin_public_transactions,
    list_admin_transactions,
    list_guest_candidates,
    list_general_guest_candidates,
    list_general_guests_admin,
    list_user_transactions,
    list_user_visited_school_ids,
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


def _parse_guest_scope(value: Optional[str], default: str = "sudin") -> str:
    scope = (value or "").strip().lower()
    if scope == "semua":
        scope = "all"
    if scope not in {"sudin", "umum", "all"}:
        scope = default
    return scope


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
        or "https://aska.sudindikju2.com"
    )
    base = (base or "").strip()
    if base and not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base.rstrip("/")


def _get_guestbook_qr_payload(school_id: int) -> Optional[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT metadata->'guestbook_qr' AS guestbook_qr
            FROM portal_schools
            WHERE id = %s
            """,
            (school_id,),
        )
        row = cur.fetchone()
    payload = dict(row).get("guestbook_qr") if row else None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = None
    return payload if isinstance(payload, dict) else None


def _store_guestbook_qr_payload(school_id: int, payload: dict) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_schools
            SET metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{guestbook_qr}', %s::jsonb, true),
                updated_at = NOW()
            WHERE id = %s
            """,
            (Json(payload), school_id),
        )


def _build_guestbook_qr(target_url: str, size: int = 1024, logo_path: Optional[Path] = None) -> Image.Image:
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
    logo_candidates = []
    if logo_path:
        logo_candidates.append(logo_path)
    logo_candidates.extend([
        base_dir / "web_aska" / "static" / "favicon.ico",
        base_dir / "web_aska" / "static" / "logo.png",
    ])
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


def _load_school_logo(school: dict) -> Optional[Image.Image]:
    logo_url = (school or {}).get("logo_url")
    if not logo_url:
        return None
    try:
        if str(logo_url).startswith(("http://", "https://")):
            resp = requests.get(logo_url, timeout=5)
            resp.raise_for_status()
            return Image.open(BytesIO(resp.content))
            
        # Clean path: remove leading slash to prevent absolute path issues
        clean_path = str(logo_url).lstrip("/")
        
        # Define base root directory
        root_dir = Path(__file__).resolve().parent.parent.parent
        
        # Logic to try multiple potential paths
        candidates = []
        
        # 1. Try as is (relative to root)
        candidates.append(root_dir / clean_path)
        
        # 2. Handle known mismatch: DB 'portal/uploads' -> FS 'uploads/portal'
        if clean_path.startswith("portal/uploads/"):
            swapped_path = clean_path.replace("portal/uploads/", "uploads/portal/", 1)
            candidates.append(root_dir / swapped_path)
            
        # 3. Try forcing 'uploads/portal/' + filename
        filename = Path(clean_path).name
        candidates.append(root_dir / "uploads" / "portal" / "logos" / filename)
        
        # 4. Try just 'uploads/' + clean_path (if portal prefix is extra)
        if clean_path.startswith("portal/"):
             candidates.append(root_dir / "uploads" / clean_path[7:]) # remove 'portal/'
             
        for candidate in candidates:
            if candidate.exists():
                return Image.open(candidate)
                
        return None
    except Exception:
        return None



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
                   s.metadata,
                   s.logo_url,
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


def _fetch_school_profile(school_id: int) -> Optional[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.id,
                   s.npsn,
                   s.name,
                   s.jenjang,
                   k.name AS kecamatan_name
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            WHERE s.id = %s
            """,
            (school_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _fetch_dashboard_user(user_id: int) -> Optional[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                u.id,
                u.full_name,
                u.email,
                u.role,
                u.jabatan,
                u.requested_kecamatan,
                k.name AS requested_kecamatan_name
            FROM dashboard_users u
            LEFT JOIN portal_kecamatan k ON u.requested_kecamatan = k.id
            WHERE u.id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _list_unvisited_schools_for_user(
    *,
    user_id: int,
    date_from: Optional[date],
    date_to: Optional[date],
    guest_scope: str,
    assigned_schools: Optional[list[dict]] = None,
    kecamatan_ids: Optional[list[int]] = None,
) -> list[dict]:
    assigned_schools = assigned_schools or []
    candidates: list[dict] = []

    if assigned_schools:
        for school in assigned_schools:
            candidates.append(
                {
                    "school_id": school.get("school_id"),
                    "school_name": school.get("school_name"),
                    "npsn": school.get("npsn"),
                    "kecamatan": school.get("kecamatan_name"),
                }
            )
    else:
        if kecamatan_ids is None:
            kecamatan_ids = get_user_kecamatan_ids(user_id)
        if not kecamatan_ids:
            return []
        schools = list_schools_by_kecamatan(kecamatan_ids, active_only=True)
        for school in schools:
            candidates.append(
                {
                    "school_id": school.get("id"),
                    "school_name": school.get("name"),
                    "npsn": school.get("npsn"),
                    "kecamatan": school.get("kecamatan_name"),
                }
            )

    visited_ids = set(
        list_user_visited_school_ids(
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            guest_scope=guest_scope,
        )
    )
    return [school for school in candidates if school.get("school_id") not in visited_ids]


def _sanitize_phone(phone: str) -> str:
    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if digits_only.startswith("0"):
        digits_only = "62" + digits_only[1:]
    return digits_only


def _build_photo_url(photo_path: Optional[str], *, external: bool = False) -> Optional[str]:
    if not photo_path:
        return None
    normalized = (photo_path or "").replace("\\", "/")
    if "uploads/portal/" in normalized:
        filename = normalized.split("uploads/portal/")[-1]
    else:
        filename = normalized.split("/")[-1]
    filename = (filename or "").lstrip("/")
    if not filename:
        return None
    return url_for("portal.uploaded_file", filename=filename, _external=external)


def _format_date_dmy(value: Optional[datetime | date]) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d/%m/%Y")


def _build_csv_response(headers: list[str], rows: list[list[object]], filename: str) -> Response:
    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    response = Response(buffer.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


def _build_xlsx_response(headers: list[str], rows: list[list[object]], filename: str) -> Response:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        return Response("Library openpyxl belum terinstall.", status=500)

    output = BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


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
        context["school_pending"] = {"pending_sudin": 0, "pending_public": 0}
        if school:
            try:
                context["school_pending"] = fetch_school_pending_counts(school_id=school.get("id"))
            except Exception:
                context["school_pending"] = {"pending_sudin": 0, "pending_public": 0}
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

    guest_scope = _parse_guest_scope(request.args.get("guest_scope"))
    summary = fetch_dashboard_summary(date_from=date_from, date_to=date_to, guest_scope=guest_scope)
    rankings, total_rows = fetch_school_rankings(
        page=page,
        per_page=per_page,
        sort_key=sort,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
        guest_scope=guest_scope,
    )
    user_search_query = (request.args.get("user_q") or "").strip()
    user_sort = (request.args.get("user_sort") or "").strip().lower() or "visits_desc"
    user_per_page = _to_int(request.args.get("user_per_page"), 10)
    user_per_page = max(5, min(user_per_page, 100))
    user_page = _to_int(request.args.get("user_page"), 1)
    user_page = max(1, user_page)

    user_rankings, user_total_rows = fetch_user_rankings(
        page=user_page,
        per_page=user_per_page,
        sort_key=user_sort,
        search_query=user_search_query,
        date_from=None,
        date_to=None,
        guest_scope=guest_scope,
    )
    user_total_pages = max(1, math.ceil(user_total_rows / user_per_page)) if user_total_rows else 1
    if user_page > user_total_pages:
        user_page = user_total_pages
        user_rankings, user_total_rows = fetch_user_rankings(
            page=user_page,
            per_page=user_per_page,
            sort_key=user_sort,
            search_query=user_search_query,
            date_from=None,
            date_to=None,
            guest_scope=guest_scope,
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
            guest_scope=guest_scope,
        )

    unvisited_schools = fetch_unvisited_schools(
        limit=10,
        date_from=date_from,
        date_to=date_to,
        guest_scope=guest_scope,
    )
    recent_visits = fetch_recent_visits(
        limit=8,
        date_from=date_from,
        date_to=date_to,
        guest_scope=guest_scope,
    )

    date_from_str = date_from.isoformat() if date_from else ""
    date_to_str = date_to.isoformat() if date_to else ""

    return render_template(
        "daftar_tamu/admin_dashboard.html",
        summary=summary,
        rankings=rankings,
        user_rankings=user_rankings,
        user_total_rows=user_total_rows,
        user_total_pages=user_total_pages,
        user_page=user_page,
        user_per_page=user_per_page,
        user_search_query=user_search_query,
        user_sort=user_sort,
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
        guest_scope=guest_scope,
    )


@daftar_tamu_bp.route("/admin/user/<int:user_id>/riwayat")
@role_required("admin")
def admin_user_history(user_id: int) -> Response:
    user_profile = _fetch_dashboard_user(user_id)
    if not user_profile:
        return render_template(
            "daftar_tamu/admin_user_history.html",
            user_profile=None,
            rows=[],
            total_rows=0,
            total_pages=1,
            page=1,
            per_page=10,
            date_from_str="",
            date_to_str="",
            guest_scope="all",
            today_str=date.today().isoformat(),
            assigned_schools=[],
            assigned_kecamatan=[],
            unvisited_schools=[],
            error_message="User tidak ditemukan.",
        ), 404

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    guest_scope = _parse_guest_scope(request.args.get("guest_scope"))

    per_page = _to_int(request.args.get("per_page"), 10)
    per_page = max(5, min(per_page, 100))

    page = _to_int(request.args.get("page"), 1)
    page = max(1, page)

    rows, total_rows = list_user_transactions(
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        guest_scope=guest_scope,
        page=page,
        per_page=per_page,
    )

    total_pages = max(1, math.ceil(total_rows / per_page)) if total_rows else 1
    if page > total_pages:
        page = total_pages
        rows, total_rows = list_user_transactions(
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            guest_scope=guest_scope,
            page=page,
            per_page=per_page,
        )

    hide_assignments = True
    assigned_schools = []
    assigned_kecamatan = []
    unvisited_schools = []

    return render_template(
        "daftar_tamu/admin_user_history.html",
        user_profile=user_profile,
        rows=rows,
        total_rows=total_rows,
        total_pages=total_pages,
        page=page,
        per_page=per_page,
        date_from_str=date_from.isoformat() if date_from else "",
        date_to_str=date_to.isoformat() if date_to else "",
        guest_scope=guest_scope,
        today_str=date.today().isoformat(),
        assigned_schools=assigned_schools,
        assigned_kecamatan=assigned_kecamatan,
        unvisited_schools=unvisited_schools,
        hide_assignments=hide_assignments,
        error_message=None,
    )


@daftar_tamu_bp.route("/admin/user/<int:user_id>/visits")
@role_required("admin")
def admin_user_visits(user_id: int) -> Response:
    """Return visit history rows for modal on admin dashboard."""
    user_profile = _fetch_dashboard_user(user_id)
    if not user_profile:
        return jsonify({"success": False, "message": "User tidak ditemukan."}), 404

    page = _to_int(request.args.get("page"), 1)
    page = max(1, page)
    per_page = _to_int(request.args.get("per_page"), 10)
    per_page = max(5, min(per_page, 100))
    sort = (request.args.get("sort") or "").strip().lower() or "date_desc"
    search_query = (request.args.get("q") or "").strip()
    guest_scope = _parse_guest_scope(request.args.get("guest_scope"))
    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    rows, total_rows = fetch_user_visit_history(
        user_id=user_id,
        page=page,
        per_page=per_page,
        sort_key=sort,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
        guest_scope=guest_scope,
    )

    total_pages = max(1, math.ceil(total_rows / per_page)) if total_rows else 1
    if page > total_pages:
        page = total_pages
        rows, total_rows = fetch_user_visit_history(
            user_id=user_id,
            page=page,
            per_page=per_page,
            sort_key=sort,
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            guest_scope=guest_scope,
        )

    for row in rows:
        visit_at = row.get("visit_at")
        row["visit_at"] = visit_at.isoformat() if visit_at else None
        row["photo_url"] = _build_photo_url(row.get("photo_path"))

    return jsonify(
        {
            "success": True,
            "rows": rows,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "page": page,
            "per_page": per_page,
            "sort": sort,
        }
    )


@daftar_tamu_bp.route("/admin/sekolah/<int:school_id>/visits")
@role_required("admin")
def admin_school_visits(school_id: int) -> Response:
    """Return visit history rows for school modal on admin dashboard."""
    school = _fetch_school_profile(school_id)
    if not school:
        return jsonify({"success": False, "message": "Sekolah tidak ditemukan."}), 404

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    page = _to_int(request.args.get("page"), 1)
    page = max(1, page)
    per_page = _to_int(request.args.get("per_page"), 10)
    per_page = max(5, min(per_page, 100))
    sort = (request.args.get("sort") or "").strip().lower() or "date_desc"
    if sort not in {"date_desc", "date_asc"}:
        sort = "date_desc"
    search_query = (request.args.get("q") or "").strip()
    guest_scope = _parse_guest_scope(request.args.get("guest_scope"))

    rows, total_rows = fetch_school_visit_history(
        school_id=school_id,
        page=page,
        per_page=per_page,
        sort_key=sort,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
        guest_scope=guest_scope,
    )

    total_pages = max(1, math.ceil(total_rows / per_page)) if total_rows else 1
    if page > total_pages:
        page = total_pages
        rows, total_rows = fetch_school_visit_history(
            school_id=school_id,
            page=page,
            per_page=per_page,
            sort_key=sort,
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            guest_scope=guest_scope,
        )

    for row in rows:
        visit_at = row.get("visit_at")
        row["visit_at"] = visit_at.isoformat() if visit_at else None
        row["photo_url"] = _build_photo_url(row.get("photo_path"))

    return jsonify(
        {
            "success": True,
            "rows": rows,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "page": page,
            "per_page": per_page,
            "sort": sort,
        }
    )


@daftar_tamu_bp.route("/admin/user/<int:user_id>/visits/export")
@role_required("admin")
def admin_user_visits_export(user_id: int) -> Response:
    """Export user visit history (Excel-friendly CSV)."""
    user_profile = _fetch_dashboard_user(user_id)
    if not user_profile:
        return Response("User tidak ditemukan.", status=404)

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    search_query = (request.args.get("q") or "").strip()
    guest_scope = _parse_guest_scope(request.args.get("guest_scope"))
    sort = (request.args.get("sort") or "").strip().lower() or "date_desc"
    if sort not in {"date_desc", "date_asc"}:
        sort = "date_desc"

    per_page = 100
    rows, total_rows = fetch_user_visit_history(
        user_id=user_id,
        page=1,
        per_page=per_page,
        sort_key=sort,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
        guest_scope=guest_scope,
    )
    total_pages = max(1, math.ceil(total_rows / per_page)) if total_rows else 1
    if total_pages > 1:
        for page in range(2, total_pages + 1):
            page_rows, _ = fetch_user_visit_history(
                user_id=user_id,
                page=page,
                per_page=per_page,
                sort_key=sort,
                search_query=search_query,
                date_from=date_from,
                date_to=date_to,
                guest_scope=guest_scope,
            )
            rows.extend(page_rows)

    headers = [
        "Nama Sekolah",
        "Tanggal Kunjungan",
        "Tujuan",
        "Foto",
    ]
    data_rows: list[list[object]] = []
    for row in rows:
        photo_flag = "Ada" if row.get("photo_path") else "-"
        data_rows.append(
            [
                row.get("school_name") or "",
                _format_date_dmy(row.get("visit_at")),
                row.get("purpose") or "",
                photo_flag,
            ]
        )

    file_format = (request.args.get("format") or "excel").strip().lower()
    if file_format in {"excel", "xlsx"}:
        filename = f"riwayat_kunjungan_user_{user_id}_{date.today().isoformat()}.xlsx"
        return _build_xlsx_response(headers, data_rows, filename)

    filename = f"riwayat_kunjungan_user_{user_id}_{date.today().isoformat()}.csv"
    return _build_csv_response(headers, data_rows, filename)


@daftar_tamu_bp.route("/admin/sekolah/<int:school_id>/visits/export")
@role_required("admin")
def admin_school_visits_export(school_id: int) -> Response:
    """Export school visit history (Excel-friendly CSV)."""
    school = _fetch_school_profile(school_id)
    if not school:
        return Response("Sekolah tidak ditemukan.", status=404)

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    search_query = (request.args.get("q") or "").strip()
    guest_scope = _parse_guest_scope(request.args.get("guest_scope"))
    sort = (request.args.get("sort") or "").strip().lower() or "date_desc"
    if sort not in {"date_desc", "date_asc"}:
        sort = "date_desc"

    per_page = 100
    rows, total_rows = fetch_school_visit_history(
        school_id=school_id,
        page=1,
        per_page=per_page,
        sort_key=sort,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
        guest_scope=guest_scope,
    )
    total_pages = max(1, math.ceil(total_rows / per_page)) if total_rows else 1
    if total_pages > 1:
        for page in range(2, total_pages + 1):
            page_rows, _ = fetch_school_visit_history(
                school_id=school_id,
                page=page,
                per_page=per_page,
                sort_key=sort,
                search_query=search_query,
                date_from=date_from,
                date_to=date_to,
                guest_scope=guest_scope,
            )
            rows.extend(page_rows)

    headers = [
        "Nama Tamu Terakhir",
        "Tanggal Kunjungan",
        "Tujuan",
        "Foto",
    ]
    data_rows: list[list[object]] = []
    for row in rows:
        photo_flag = "Ada" if row.get("photo_path") else "-"
        data_rows.append(
            [
                row.get("guest_display") or row.get("guest_names") or "",
                _format_date_dmy(row.get("visit_at")),
                row.get("purpose") or "",
                photo_flag,
            ]
        )

    file_format = (request.args.get("format") or "excel").strip().lower()
    if file_format in {"excel", "xlsx"}:
        filename = f"riwayat_kunjungan_sekolah_{school_id}_{date.today().isoformat()}.xlsx"
        return _build_xlsx_response(headers, data_rows, filename)

    filename = f"riwayat_kunjungan_sekolah_{school_id}_{date.today().isoformat()}.csv"
    return _build_csv_response(headers, data_rows, filename)


@daftar_tamu_bp.route("/settings/users", methods=["GET", "POST"])
@role_required("admin")
def manage_users() -> Response:
    """Manage dashboard users from Daftar Tamu app."""
    from dashboard.user_management import handle_manage_users

    return handle_manage_users(actor=current_user(), base_template="daftar_tamu/base_daftar_tamu.html")


@daftar_tamu_bp.route("/admin/map-data")
@role_required("admin")
def admin_map_data() -> Response:
    """Return map dots for daftar tamu dashboard."""
    ensure_daftar_tamu_seed_data()
    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    guest_scope = _parse_guest_scope(request.args.get("guest_scope"))
    return jsonify(fetch_map_data(date_from=date_from, date_to=date_to, guest_scope=guest_scope))


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

    guest_scope = _parse_guest_scope(request.args.get("guest_scope"))

    rows, _ = fetch_school_rankings(
        page=1,
        per_page=10000,
        sort_key=sort,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
        guest_scope=guest_scope,
    )

    headers = [
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
    data_rows: list[list[object]] = []
    for row in rows:
        data_rows.append(
            [
                row.get("rank"),
                row.get("npsn"),
                row.get("school_name"),
                row.get("jenjang"),
                row.get("kecamatan"),
                row.get("kelurahan"),
                row.get("visit_count"),
                _format_date_dmy(row.get("last_visit_date")),
                row.get("last_guest_display") or "",
            ]
        )

    file_format = (request.args.get("format") or "csv").strip().lower()
    if file_format in {"excel", "xlsx"}:
        filename = f"ranking_daftar_tamu_{date.today().isoformat()}.xlsx"
        return _build_xlsx_response(headers, data_rows, filename)

    filename = f"ranking_daftar_tamu_{date.today().isoformat()}.csv"
    return _build_csv_response(headers, data_rows, filename)


# ===============================
# Admin Validation
# ===============================

@daftar_tamu_bp.route("/admin/validasi")
@role_required("admin")
def admin_validation() -> Response:
    status = (request.args.get("status") or "pending").strip().lower()
    if status not in ("pending", "approved", "rejected", "history"):
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


@daftar_tamu_bp.route("/admin/transactions/<int:transaction_id>/pending", methods=["POST"])
@role_required("admin")
def admin_transaction_pending(transaction_id: int) -> Response:
    user = current_user()
    note = (request.form.get("reviewer_note") or "").strip()
    try:
        ok = update_transaction_status(
            transaction_id=transaction_id,
            status="pending",
            reviewer_id=user["id"],
            reviewer_notes=note or None,
        )
    except ValueError:
        ok = False
    if not ok:
        return jsonify({"success": False, "message": "Gagal memperbarui transaksi."}), 400
    return jsonify({"success": True})


@daftar_tamu_bp.route("/admin/transactions/bulk-approve", methods=["POST"])
@role_required("admin")
def admin_bulk_approve_transactions() -> Response:
    user = current_user()
    raw_ids = request.form.getlist("transaction_ids")
    ids: list[int] = []
    for raw in raw_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        flash("Pilih transaksi yang ingin disetujui.", "warning")
        return redirect(_build_admin_validation_redirect(request.form))

    note = (request.form.get("reviewer_note") or "").strip()
    success_count = 0
    for tx_id in ids:
        try:
            ok = update_transaction_status(
                transaction_id=tx_id,
                status="approved",
                reviewer_id=user["id"],
                reviewer_notes=note or None,
            )
        except Exception:
            ok = False
        if ok:
            success_count += 1

    if success_count:
        flash(f"{success_count} transaksi berhasil disetujui.", "success")
    else:
        flash("Tidak ada transaksi yang berhasil disetujui.", "warning")

    return redirect(_build_admin_validation_redirect(request.form))


@daftar_tamu_bp.route("/admin/transactions/bulk-reject", methods=["POST"])
@role_required("admin")
def admin_bulk_reject_transactions() -> Response:
    user = current_user()
    raw_ids = request.form.getlist("transaction_ids")
    ids: list[int] = []
    for raw in raw_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        flash("Pilih transaksi yang ingin ditolak.", "warning")
        return redirect(_build_admin_validation_redirect(request.form))

    note = (request.form.get("reviewer_note") or "").strip()
    if not note:
        flash("Catatan penolakan wajib diisi.", "warning")
        return redirect(_build_admin_validation_redirect(request.form))

    success_count = 0
    for tx_id in ids:
        try:
            ok = update_transaction_status(
                transaction_id=tx_id,
                status="rejected",
                reviewer_id=user["id"],
                reviewer_notes=note,
            )
        except Exception:
            ok = False
        if ok:
            success_count += 1

    if success_count:
        flash(f"{success_count} transaksi berhasil ditolak.", "success")
    else:
        flash("Tidak ada transaksi yang berhasil ditolak.", "warning")

    return redirect(_build_admin_validation_redirect(request.form))


@daftar_tamu_bp.route("/admin/transactions/bulk-pending", methods=["POST"])
@role_required("admin")
def admin_bulk_pending_transactions() -> Response:
    user = current_user()
    raw_ids = request.form.getlist("transaction_ids")
    ids: list[int] = []
    for raw in raw_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        flash("Pilih transaksi yang ingin dikembalikan ke pending.", "warning")
        return redirect(_build_admin_validation_redirect(request.form))

    note = (request.form.get("reviewer_note") or "").strip()
    success_count = 0
    for tx_id in ids:
        try:
            ok = update_transaction_status(
                transaction_id=tx_id,
                status="pending",
                reviewer_id=user["id"],
                reviewer_notes=note or None,
            )
        except Exception:
            ok = False
        if ok:
            success_count += 1

    if success_count:
        flash(f"{success_count} transaksi berhasil dikembalikan ke pending.", "success")
    else:
        flash("Tidak ada transaksi yang berhasil dikembalikan ke pending.", "warning")

    return redirect(_build_admin_validation_redirect(request.form))


def _build_admin_validation_redirect(form) -> str:
    status = (form.get("status") or "").strip() or "pending"
    search = (form.get("q") or "").strip()
    date_from = (form.get("date_from") or "").strip()
    date_to = (form.get("date_to") or "").strip()
    per_page_raw = (form.get("per_page") or "").strip()
    page_raw = (form.get("page") or "").strip()
    try:
        per_page = int(per_page_raw) if per_page_raw else None
    except (TypeError, ValueError):
        per_page = None
    try:
        page = int(page_raw) if page_raw else None
    except (TypeError, ValueError):
        page = None
    return url_for(
        "daftar_tamu.admin_validation",
        status=status,
        q=search,
        date_from=date_from,
        date_to=date_to,
        per_page=per_page,
        page=page,
    )


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


@daftar_tamu_bp.route("/admin/umum/search")
@role_required("admin")
def admin_general_guest_search() -> Response:
    query = (request.args.get("q") or "").strip()
    limit = _to_int(request.args.get("limit"), 15)
    results = list_general_guest_candidates(query, limit=limit)
    return jsonify({"success": True, "results": results})


@daftar_tamu_bp.route("/admin/umum-rekap")
@role_required("admin")
def admin_public_summary() -> Response:
    status = (request.args.get("status") or "").strip().lower()
    search_query = (request.args.get("q") or "").strip()
    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    per_page = _to_int(request.args.get("per_page"), 10)
    per_page = max(5, min(per_page, 200))
    page = _to_int(request.args.get("page"), 1)
    page = max(1, page)

    rows, total_rows = list_admin_public_school_summary(
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
        rows, total_rows = list_admin_public_school_summary(
            status=status,
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            page=page,
            per_page=per_page,
        )

    return render_template(
        "daftar_tamu/admin_public_summary.html",
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
            error_message="Akun sekolah belum terhubung dengan data sekolah. Hubungi admin.",
        )

    return render_template(
        "daftar_tamu/sekolah_dashboard.html",
        school=school,
        user_school=school,
        area_contacts=_build_area_contacts(school),
        purpose_keywords=list_purpose_keywords(active_only=True),
        error_message=None,
    )


@daftar_tamu_bp.route("/sekolah/umum-web")
@role_required("sekolah")
def sekolah_public_web() -> Response:
    user = current_user()
    school = _fetch_school_for_user(user["id"])
    if not school:
        return render_template(
            "daftar_tamu/sekolah_umum_web.html",
            school=None,
            error_message="Akun sekolah belum terhubung dengan data sekolah. Hubungi admin.",
        )

    public_status = (request.args.get("public_status") or "").strip().lower()
    public_per_page = _to_int(request.args.get("public_per_page"), 5)
    public_per_page = max(3, min(public_per_page, 100))
    public_page = _to_int(request.args.get("public_page"), 1)
    public_page = max(1, public_page)

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

    guestbook_public_url = f"{_web_aska_base_url()}/buku-tamu/{school.get('npsn')}"
    qr_payload = _get_guestbook_qr_payload(school["id"])
    qr_ready = bool(
        qr_payload
        and qr_payload.get("png_base64")
        and qr_payload.get("url") == guestbook_public_url
    )

    return render_template(
        "daftar_tamu/sekolah_umum_web.html",
        school=school,
        user_school=school,
        guestbook_public_url=guestbook_public_url,
        guestbook_qr_ready=qr_ready,
        public_rows=public_rows,
        public_status=public_status,
        public_page=public_page,
        public_per_page=public_per_page,
        public_total_rows=public_total_rows,
        public_total_pages=public_total_pages,
        error_message=None,
    )


@daftar_tamu_bp.route("/sekolah/riwayat")
@role_required("sekolah")
def sekolah_riwayat() -> Response:
    user = current_user()
    school = _fetch_school_for_user(user["id"])
    if not school:
        return render_template(
            "daftar_tamu/sekolah_riwayat.html",
            school=None,
            error_message="Akun sekolah belum terhubung dengan data sekolah. Hubungi admin.",
        )

    status = (request.args.get("status") or "").strip().lower()
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
        "daftar_tamu/sekolah_riwayat.html",
        school=school,
        user_school=school,
        rows=rows,
        status=status,
        page=page,
        per_page=per_page,
        total_rows=total_rows,
        total_pages=total_pages,
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
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip()
    instansi = (request.form.get("instansi") or "").strip()
    jabatan = (request.form.get("jabatan") or "").strip()
    auto_verify = user.get("role") == "admin"
    if not full_name:
        return jsonify({"success": False, "message": "Nama tamu wajib diisi."}), 400
    if phone:
        phone = _sanitize_phone(phone)

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO daftar_tamu_general_guests (
                full_name, email, phone, instansi, jabatan, created_by,
                is_verified, verified_by, verified_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s THEN NOW() ELSE NULL END)
            RETURNING id, full_name, email, phone, instansi, jabatan, is_verified
            """,
            (
                full_name,
                email or None,
                phone or None,
                instansi or None,
                jabatan or None,
                user.get("id"),
                auto_verify,
                user.get("id") if auto_verify else None,
                auto_verify,
            ),
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


@daftar_tamu_bp.route("/admin/umum/<int:guest_id>/update", methods=["POST"])
@role_required("admin")
def admin_update_general_guest(guest_id: int) -> Response:
    full_name = (request.form.get("full_name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    instansi = (request.form.get("instansi") or "").strip()
    jabatan = (request.form.get("jabatan") or "").strip()
    email = (request.form.get("email") or "").strip().lower()

    if not full_name:
        return jsonify({"success": False, "message": "Nama tamu wajib diisi."}), 400
    if phone:
        phone = _sanitize_phone(phone)

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE daftar_tamu_general_guests
            SET full_name = %s,
                phone = %s,
                instansi = %s,
                jabatan = %s,
                email = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                full_name,
                phone or None,
                instansi or None,
                jabatan or None,
                email or None,
                guest_id,
            ),
        )
        if cur.rowcount == 0:
            return jsonify({"success": False, "message": "Tamu umum tidak ditemukan."}), 404
    return jsonify({"success": True})


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
    return redirect(url_for("daftar_tamu.sekolah_public_web", _anchor="publicGuestbook"))


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
    return redirect(url_for("daftar_tamu.sekolah_public_web", _anchor="publicGuestbook"))


@daftar_tamu_bp.route("/sekolah/umum-transactions/bulk-approve", methods=["POST"])
@role_required("sekolah")
def sekolah_bulk_approve_public_transactions() -> Response:
    user = current_user()
    school = _fetch_school_for_user(user.get("id"))
    if not school:
        flash("Akun sekolah belum terhubung dengan data sekolah.", "warning")
        return redirect(url_for("daftar_tamu.sekolah_public_web"))

    raw_ids = request.form.getlist("transaction_ids")
    ids: list[int] = []
    for raw in raw_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        flash("Pilih transaksi yang ingin disetujui.", "warning")
        return redirect(url_for("daftar_tamu.sekolah_public_web"))

    reviewer_notes = (request.form.get("reviewer_notes") or "").strip()
    success_count = 0
    for tx_id in ids:
        try:
            ok = update_public_transaction_status(
                transaction_id=tx_id,
                status="approved",
                reviewer_id=user.get("id"),
                reviewer_notes=reviewer_notes or None,
                school_id=school.get("id"),
            )
        except Exception:
            ok = False
        if ok:
            success_count += 1

    if success_count:
        flash(f"{success_count} pengajuan berhasil disetujui.", "success")
    else:
        flash("Tidak ada pengajuan yang berhasil disetujui.", "warning")

    return redirect(url_for("daftar_tamu.sekolah_public_web"))


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
    qr_payload = _get_guestbook_qr_payload(school.get("id"))
    qr_base64 = None
    if qr_payload and qr_payload.get("png_base64") and qr_payload.get("url") == target_url:
        qr_base64 = qr_payload.get("png_base64")
    if not qr_base64:
        return jsonify({"success": False, "message": "QR belum dibuat. Silakan generate terlebih dahulu."}), 400
    try:
        qr_bytes = base64.b64decode(qr_base64)
        qr_img = Image.open(BytesIO(qr_bytes)).convert("RGBA")
    except Exception as exc:
        return jsonify({"success": False, "message": f"QR tersimpan tidak valid: {exc}"}), 500

    if fmt == "pdf":
        template_path = Path(__file__).resolve().parent.parent / "static" / "qr" / "new_template.png"
        if not template_path.exists():
            return jsonify({"success": False, "message": "Template QR tidak ditemukan."}), 500

        canvas = Image.open(template_path).convert("RGBA")
        base_w, base_h = 4419, 6250  # target high resolution
        
        # Upscale template if it's smaller than target base resolution
        # This ensures text, logos, and QR are rendered at high definition
        if canvas.width < base_w:
             canvas = canvas.resize((base_w, base_h), Image.LANCZOS)
             
        scale = canvas.width / base_w

        # Posisi & ukuran elemen (berdasarkan contoh.svg, diskalakan)
        qr_box_bbox = (1054, 2092, 3364, 4427)  # extracted from template.png
        qr_box_w = qr_box_bbox[2] - qr_box_bbox[0]
        qr_box_h = qr_box_bbox[3] - qr_box_bbox[1]
        qr_size_base = int(min(qr_box_w, qr_box_h) * 0.78)  # keep margin
        qr_center_x_base = (qr_box_bbox[0] + qr_box_bbox[2]) / 2
        qr_center_y_base = (qr_box_bbox[1] + qr_box_bbox[3]) / 2
        name_y_base = 4720
        web_label_y_base = 5440
        web_value_y_base = 5535
        ig_label_y_base = 5440
        ig_value_y_base = 5535
        web_x_base = 1480
        ig_x_base = 2920
        logo_center_base = (3800, 500)
        logo_diameter_base = 510

        qr_size = int(qr_size_base * scale)
        qr_x = int((qr_center_x_base - qr_size_base / 2) * scale)
        qr_y = int((qr_center_y_base - qr_size_base / 2) * scale)
        qr_resized = qr_img.resize((qr_size, qr_size), Image.LANCZOS).convert("RGBA")
        canvas.alpha_composite(qr_resized, (qr_x, qr_y))

        draw = ImageDraw.Draw(canvas)
        def _font(path: str, size: int):
            # Try finding bundled font first for server compatibility
            root_dir = Path(__file__).resolve().parent.parent.parent
            bundled_font = root_dir / "dashboard" / "static" / "fonts" / "Roboto-Bold.ttf"
            
            # List of potential font paths to try
            font_candidates = [
                bundled_font,
                path,
                f"/System/Library/Fonts/Supplemental/{path}",
                f"/System/Library/Fonts/{path}",
                f"/Library/Fonts/{path}",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", # Linux typical
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" # Linux typical
            ]
            
            for font_path in font_candidates:
                try:
                    if os.path.exists(str(font_path)):
                        return ImageFont.truetype(str(font_path), int(size * scale))
                except Exception:
                    continue
            
            # Fallback if nothing works
            print("WARNING: All font paths failed, using default font (tiny)")
            return ImageFont.load_default()

        # Use generic name, but function will pick Roboto-Bold.ttf if available
        font_name = _font("Arial Bold.ttf", 220)
        font_small_value = _font("Arial Bold.ttf", 80)

        cx = canvas.width // 2
        draw.text((cx, int(name_y_base * scale)), (school.get("name") or "Nama Sekolah").upper(),
                  fill=(60, 70, 180, 255), font=font_name, anchor="mm")

        meta = school.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        def _shorten(text: str, max_len: int = 40) -> str:
            text = text or "-"
            return text if len(text) <= max_len else text[: max_len - 3] + "..."

        website_text = _shorten(meta.get("website") or "-")
        # Remove protocol and www
        for prefix in ["https://", "http://", "www."]:
             if website_text.lower().startswith(prefix):
                 website_text = website_text[len(prefix):]
        # Remove trailing slash
        website_text = website_text.rstrip("/")

        instagram_text = _shorten(meta.get("instagram") or meta.get("ig") or "-")
        if instagram_text != "-" and not instagram_text.startswith("@"):
             instagram_text = f"@{instagram_text}"

        web_value_y_base = 5190
        ig_value_y_base = 5190

        # Adjust X for left alignment (lm anchor)
        # web_x_base was 1150 (left), changing to 1200 (slightly right)
        # ig_x_base was 2600 (left)
        web_x_base = 1200
        ig_x_base = 2600

        draw.text((int(web_x_base * scale), int(web_value_y_base * scale)), website_text,
                  fill=(0, 0, 0, 255), font=font_small_value, anchor="lm")
        draw.text((int(ig_x_base * scale), int(ig_value_y_base * scale)), instagram_text,
                  fill=(0, 0, 0, 255), font=font_small_value, anchor="lm")

        logo_img = _load_school_logo(school)
        if logo_img:
            # Logo dimensions
            logo_size = int(logo_diameter_base * scale)
            
            # Process logo
            logo_img = logo_img.convert("RGBA")
            
            # Create ultra high quality circular mask
            # Render at 4x size then downscale for maximum anti-aliasing
            mask_scale_factor = 4
            mask_size = logo_size * mask_scale_factor
            
            mask = Image.new("L", (mask_size, mask_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, mask_size, mask_size), fill=255)
            
            # Downscale mask perfectly
            mask = mask.resize((logo_size, logo_size), Image.LANCZOS)
            
            # Resize logo to fit
            # First resize to mask_size (upscale if needed) then downscale with LANCZOS
            logo_img = logo_img.resize((mask_size, mask_size), Image.LANCZOS)
            logo_img = logo_img.resize((logo_size, logo_size), Image.LANCZOS)
            
            # Enhance sharpness slightly after downscaling to prevent blur
            from PIL import ImageFilter
            logo_img = logo_img.filter(ImageFilter.SHARPEN)
            
            # Calculate position to center in the circle
            logo_pos = (
                int(logo_center_base[0] * scale - logo_size / 2),
                int(logo_center_base[1] * scale - logo_size / 2)
            )
            
            # Paste logo with mask
            canvas.paste(logo_img, logo_pos, mask)

        buf = BytesIO()
        canvas.convert("RGB").save(buf, format="PDF")
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


@daftar_tamu_bp.route("/sekolah/qr/generate", methods=["POST"])
@role_required("sekolah")
def sekolah_generate_guestbook_qr() -> Response:
    user = current_user()
    school = _fetch_school_for_user(user.get("id"))
    if not school:
        flash("Akun sekolah belum terhubung.", "danger")
        return redirect(url_for("daftar_tamu.sekolah_public_web"))

    target_url = f"{_web_aska_base_url()}/buku-tamu/{school.get('npsn')}"
    
    # Resolve logo path
    logo_path = None
    logo_url = school.get("logo_url")
    if logo_url and "/portal/uploads/" in logo_url:
        # Resolve URL to local path
        # URL format: /portal/uploads/<filename>
        # Local upload dir: base_dir/uploads/portal
        try:
            filename = logo_url.split("/portal/uploads/")[-1]
            base_dir = Path(__file__).resolve().parents[2]
            upload_folder = base_dir / "uploads" / "portal"
            candidate_path = upload_folder / filename
            if candidate_path.exists():
                logo_path = candidate_path
        except Exception:
            pass

    qr_img = _build_guestbook_qr(target_url, size=1024, logo_path=logo_path)
    buf = BytesIO()
    qr_img.convert("RGB").save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode("ascii")

    payload = {
        "url": target_url,
        "png_base64": qr_base64,
        "generated_at": current_jakarta_time().isoformat(),
    }
    _store_guestbook_qr_payload(school.get("id"), payload)
    flash("QR Buku Tamu berhasil dibuat.", "success")
    return redirect(url_for("daftar_tamu.sekolah_public_web"))


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

    auto_approve = user.get("role") == "sekolah" and not sudin_ids and bool(umum_ids)
    status_value = "approved" if auto_approve else "pending"
    reviewed_by = user.get("id") if auto_approve else None
    reviewed_at = visit_at if auto_approve else None
    reviewer_notes = "Auto konfirmasi sekolah" if auto_approve else None

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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                status_value,
                reviewed_by,
                reviewed_at,
                reviewer_notes,
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

    if status_value == "pending" and transaction_id:
        try:
            from dashboard.telegram_notifications import notify_guestbook_request

            detail = get_transaction_detail(transaction_id)
            photo_url = None
            guest_summary = None

            if detail:
                photo_path = detail.get("photo_path")
                if photo_path:
                    photo_name = photo_path.split("uploads/portal/")[-1]
                    photo_url = url_for(
                        "portal.uploaded_file",
                        filename=photo_name,
                        _external=True,
                    )

                guests = detail.get("guests") or []
                guest_names = [
                    (g.get("full_name") or "").strip()
                    for g in guests
                    if (g.get("full_name") or "").strip()
                ]
                if guest_names:
                    if len(guest_names) > 3:
                        guest_summary = f"{', '.join(guest_names[:3])} +{len(guest_names) - 3}"
                    else:
                        guest_summary = ", ".join(guest_names)

            notify_guestbook_request(
                transaction_id=transaction_id,
                school_name=school.get("name") or "Sekolah",
                npsn=school.get("npsn"),
                visit_at=visit_at,
                guest_summary=guest_summary,
                purpose=purpose or None,
                notes=notes or None,
                photo_url=photo_url,
            )
        except Exception:
            current_app.logger.exception("Gagal mengirim notifikasi buku tamu.")

    return jsonify({"success": True, "transaction_id": transaction_id})
