"""Routes for Daftar Tamu admin dashboard."""

from __future__ import annotations

import csv
import math
from datetime import date, datetime
from io import StringIO
from typing import Optional

from flask import Blueprint, Response, jsonify, render_template, request

from dashboard.auth import current_user, role_required
from dashboard.portal.permissions import can_access_aska, get_permission_summary, is_superadmin
from dashboard.portal.queries import fetch_admin_pending_summary

from .queries import (
    DEFAULT_SORT,
    SORT_OPTIONS,
    ensure_daftar_tamu_seed_data,
    fetch_dashboard_summary,
    fetch_map_data,
    fetch_recent_visits,
    fetch_school_rankings,
    fetch_unvisited_schools,
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
        "total": 0,
    }
    if user.get("role") == "admin":
        try:
            admin_pending = fetch_admin_pending_summary()
        except Exception:
            pass

    return {
        "permissions": get_permission_summary(user),
        "is_superadmin": is_superadmin(user),
        "can_access_aska": can_access_aska(user),
        "admin_pending": admin_pending,
    }


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
            "Instansi Terakhir",
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
                row.get("last_guest_name") or "",
                row.get("last_guest_institution") or "",
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
