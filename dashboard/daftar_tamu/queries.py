"""Query helpers for Daftar Tamu dashboard."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from dashboard.db_access import get_cursor


SORT_OPTIONS = {
    "visits_desc": "visit_count DESC, last_visit_date DESC NULLS LAST, school_name ASC",
    "visits_asc": "visit_count ASC, last_visit_date DESC NULLS LAST, school_name ASC",
    "last_visit_desc": "last_visit_date DESC NULLS LAST, visit_count DESC, school_name ASC",
    "last_visit_asc": "last_visit_date ASC NULLS FIRST, visit_count DESC, school_name ASC",
    "name_asc": "school_name ASC",
    "name_desc": "school_name DESC",
}

DEFAULT_SORT = "visits_desc"
TRANSACTION_STATUSES = {"pending", "approved", "rejected"}

_ROLLUP_CTE = """
WITH filtered_transactions AS (
    SELECT t.*
    FROM daftar_tamu_transactions t
    WHERE t.status = 'approved'
      AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
      AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
),
school_rollup AS (
    SELECT
        s.id AS school_id,
        s.npsn,
        s.name AS school_name,
        s.jenjang,
        k.name AS kecamatan,
        l.name AS kelurahan,
        s.alamat,
        COUNT(ft.id) AS visit_count,
        MAX(ft.visit_at) AS last_visit_date,
        latest.guest_names AS last_guest_names,
        latest.guest_count AS last_guest_count,
        latest.photo_path AS last_photo_path,
        latest.latitude AS latitude,
        latest.longitude AS longitude
    FROM portal_schools s
    LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
    LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
    LEFT JOIN filtered_transactions ft ON ft.school_id = s.id
    LEFT JOIN LATERAL (
        SELECT
            t2.photo_path,
            t2.latitude,
            t2.longitude,
            (
                SELECT STRING_AGG(u.full_name, ', ' ORDER BY u.full_name)
                FROM daftar_tamu_transaction_guests g
                LEFT JOIN dashboard_users u ON u.id = g.user_id
                WHERE g.transaction_id = t2.id
            ) AS guest_names,
            (
                SELECT COUNT(*)
                FROM daftar_tamu_transaction_guests g
                WHERE g.transaction_id = t2.id
            ) AS guest_count
        FROM filtered_transactions t2
        WHERE t2.school_id = s.id
        ORDER BY t2.visit_at DESC, t2.id DESC
        LIMIT 1
    ) latest ON TRUE
    WHERE s.active = TRUE
    GROUP BY
        s.id,
        s.npsn,
        s.name,
        s.jenjang,
        k.name,
        l.name,
        s.alamat,
        latest.guest_names,
        latest.guest_count,
        latest.photo_path,
        latest.latitude,
        latest.longitude
)
"""


def _build_search(search_query: Optional[str]) -> tuple[str, str]:
    query = (search_query or "").strip()
    return query, f"%{query}%"


def ensure_daftar_tamu_seed_data() -> None:
    """No-op: daftar tamu now uses portal_schools and real transactions."""
    return


def fetch_dashboard_summary(date_from: Optional[date] = None, date_to: Optional[date] = None) -> Dict[str, Any]:
    """Fetch top-level summary stats for admin dashboard."""
    cutoff = date.today() - timedelta(days=30)
    params: List[Any] = [
        date_from,
        date_from,
        date_to,
        date_to,
        cutoff,
        date_from,
        date_from,
        date_to,
        date_to,
        date_from,
        date_from,
        date_to,
        date_to,
    ]
    query = (
        _ROLLUP_CTE
        + """
    SELECT
        (SELECT COUNT(*) FROM portal_schools WHERE active = TRUE) AS total_schools,
        (SELECT COALESCE(SUM(visit_count), 0) FROM school_rollup) AS total_visits,
        (SELECT COUNT(*) FROM school_rollup WHERE visit_count > 0) AS visited_schools,
        (SELECT COUNT(*) FROM school_rollup WHERE visit_count = 0) AS unvisited_schools,
        (SELECT COUNT(*) FROM school_rollup WHERE visit_count = 0 OR last_visit_date < %s::date) AS attention_schools,
        (SELECT MAX(last_visit_date) FROM school_rollup) AS latest_visit_date,
        (SELECT COUNT(*) FROM filtered_transactions
            WHERE visit_at >= date_trunc('month', CURRENT_DATE)) AS visits_this_month,
        (SELECT COUNT(*) FROM daftar_tamu_transactions t
            WHERE t.status = 'pending'
              AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
              AND (%s::date IS NULL OR t.visit_at::date <= %s::date)) AS pending_visits,
        (SELECT COUNT(*) FROM daftar_tamu_transactions t
            WHERE t.status = 'rejected'
              AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
              AND (%s::date IS NULL OR t.visit_at::date <= %s::date)) AS rejected_visits
    """
    )

    with get_cursor() as cur:
        cur.execute(query, params)
        row = dict(cur.fetchone() or {})

    return {
        "total_schools": int(row.get("total_schools") or 0),
        "total_visits": int(row.get("total_visits") or 0),
        "visited_schools": int(row.get("visited_schools") or 0),
        "unvisited_schools": int(row.get("unvisited_schools") or 0),
        "attention_schools": int(row.get("attention_schools") or 0),
        "latest_visit_date": row.get("latest_visit_date"),
        "visits_this_month": int(row.get("visits_this_month") or 0),
        "pending_visits": int(row.get("pending_visits") or 0),
        "rejected_visits": int(row.get("rejected_visits") or 0),
    }


def fetch_school_rankings(
    *,
    page: int = 1,
    per_page: int = 10,
    sort_key: str = DEFAULT_SORT,
    search_query: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch school rankings with search, sorting, and pagination."""
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 500))
    offset = (safe_page - 1) * safe_per_page

    safe_sort = sort_key if sort_key in SORT_OPTIONS else DEFAULT_SORT
    order_sql = SORT_OPTIONS[safe_sort]
    query_text, like_query = _build_search(search_query)

    base_params: List[Any] = [date_from, date_from, date_to, date_to]
    search_params: List[Any] = [query_text, like_query, like_query, like_query, like_query]

    count_query = (
        _ROLLUP_CTE
        + """
    SELECT COUNT(*) AS total
    FROM school_rollup
    WHERE (
        %s = ''
        OR school_name ILIKE %s
        OR npsn ILIKE %s
        OR COALESCE(kecamatan, '') ILIKE %s
        OR COALESCE(kelurahan, '') ILIKE %s
    )
    """
    )

    data_query = (
        _ROLLUP_CTE
        + f"""
    SELECT
        school_id,
        npsn,
        school_name,
        jenjang,
        kecamatan,
        kelurahan,
        alamat,
        latitude,
        longitude,
        visit_count,
        last_visit_date,
        last_guest_names,
        last_guest_count,
        last_photo_path
    FROM school_rollup
    WHERE (
        %s = ''
        OR school_name ILIKE %s
        OR npsn ILIKE %s
        OR COALESCE(kecamatan, '') ILIKE %s
        OR COALESCE(kelurahan, '') ILIKE %s
    )
    ORDER BY {order_sql}
    LIMIT %s OFFSET %s
    """
    )

    with get_cursor() as cur:
        cur.execute(count_query, base_params + search_params)
        count_row = cur.fetchone()
        total_rows = int(dict(count_row).get("total") or 0) if count_row else 0

        cur.execute(data_query, base_params + search_params + [safe_per_page, offset])
        rows = [dict(row) for row in cur.fetchall()]

    today = date.today()
    for index, row in enumerate(rows, start=offset + 1):
        row["rank"] = index
        row["visit_count"] = int(row.get("visit_count") or 0)
        if row.get("latitude") is not None:
            row["latitude"] = float(row["latitude"])
        if row.get("longitude") is not None:
            row["longitude"] = float(row["longitude"])
        last_visit = row.get("last_visit_date")
        row["days_since_visit"] = (today - last_visit.date()).days if last_visit else None

        names_raw = row.get("last_guest_names") or ""
        names = [n.strip() for n in names_raw.split(",") if n.strip()]
        guest_count = int(row.get("last_guest_count") or 0)
        if not guest_count:
            guest_count = len(names)
        if names:
            if len(names) > 2:
                display = f"{names[0]} +{len(names) - 1}"
            elif len(names) == 2:
                display = f"{names[0]} & {names[1]}"
            else:
                display = names[0]
        else:
            display = None
        row["last_guest_display"] = display
        row["last_guest_count"] = guest_count

    return rows, total_rows


def fetch_map_data(
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Fetch map points for visit distribution."""
    query = (
        _ROLLUP_CTE
        + f"""
    SELECT
        school_id,
        npsn,
        school_name,
        jenjang,
        kecamatan,
        kelurahan,
        latitude,
        longitude,
        visit_count,
        last_visit_date,
        last_guest_names,
        last_guest_count
    FROM school_rollup
    ORDER BY {SORT_OPTIONS[DEFAULT_SORT]}
    """
    )

    with get_cursor() as cur:
        cur.execute(query, [date_from, date_from, date_to, date_to])
        rows = [dict(row) for row in cur.fetchall()]

    cutoff = date.today() - timedelta(days=30)
    payload: List[Dict[str, Any]] = []
    for row in rows:
        lat = row.get("latitude")
        lng = row.get("longitude")
        if lat is None or lng is None:
            continue

        visit_count = int(row.get("visit_count") or 0)
        last_visit = row.get("last_visit_date")
        if visit_count == 0:
            level = "unvisited"
        elif last_visit and last_visit.date() >= cutoff:
            level = "recent"
        else:
            level = "stale"

        payload.append(
            {
                "school_id": row.get("school_id"),
                "school_name": row.get("school_name"),
                "npsn": row.get("npsn"),
                "jenjang": row.get("jenjang"),
                "kecamatan": row.get("kecamatan"),
                "kelurahan": row.get("kelurahan"),
                "latitude": float(lat),
                "longitude": float(lng),
                "visit_count": visit_count,
                "last_visit_date": last_visit.isoformat() if last_visit else None,
                "last_guest_name": row.get("last_guest_names"),
                "last_guest_count": int(row.get("last_guest_count") or 0),
                "level": level,
            }
        )
    return payload


def fetch_unvisited_schools(
    *,
    limit: int = 8,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Fetch schools with zero approved visits in the selected period."""
    safe_limit = max(1, min(limit, 100))
    query = (
        _ROLLUP_CTE
        + """
    SELECT
        school_id,
        npsn,
        school_name,
        jenjang,
        kecamatan,
        kelurahan
    FROM school_rollup
    WHERE visit_count = 0
    ORDER BY school_name ASC
    LIMIT %s
    """
    )
    with get_cursor() as cur:
        cur.execute(query, [date_from, date_from, date_to, date_to, safe_limit])
        return [dict(row) for row in cur.fetchall()]


def fetch_recent_visits(
    *,
    limit: int = 10,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Fetch latest approved visit records for side panel."""
    safe_limit = max(1, min(limit, 100))
    query = """
    SELECT
        t.id,
        t.visit_at,
        t.purpose,
        t.photo_path,
        s.id AS school_id,
        s.name AS school_name,
        s.npsn,
        s.jenjang,
        k.name AS kecamatan,
        (
            SELECT STRING_AGG(u.full_name, ', ' ORDER BY u.full_name)
            FROM daftar_tamu_transaction_guests g
            LEFT JOIN dashboard_users u ON u.id = g.user_id
            WHERE g.transaction_id = t.id
        ) AS guest_names,
        (
            SELECT COUNT(*)
            FROM daftar_tamu_transaction_guests g
            WHERE g.transaction_id = t.id
        ) AS guest_count
    FROM daftar_tamu_transactions t
    JOIN portal_schools s ON s.id = t.school_id
    LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
    LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
    WHERE s.active = TRUE
      AND t.status = 'approved'
      AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
      AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
    ORDER BY t.visit_at DESC, t.id DESC
    LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(query, [date_from, date_from, date_to, date_to, safe_limit])
        return [dict(row) for row in cur.fetchall()]


def list_guest_candidates(search_query: Optional[str], limit: int = 20) -> List[Dict[str, Any]]:
    query_text, like_query = _build_search(search_query)
    safe_limit = max(1, min(limit, 50))
    query = """
        SELECT
            id,
            full_name,
            email,
            role,
            nrk,
            jabatan,
            degree_prefix,
            degree_suffix
        FROM dashboard_users
        WHERE account_status = 'approved'
          AND (
            %s = ''
            OR full_name ILIKE %s
            OR email ILIKE %s
            OR COALESCE(nip, '') ILIKE %s
            OR COALESCE(nrk, '') ILIKE %s
            OR COALESCE(role, '') ILIKE %s
        )
        ORDER BY full_name ASC
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(
            query,
            [query_text, like_query, like_query, like_query, like_query, like_query, safe_limit],
        )
        return [dict(row) for row in cur.fetchall()]


def list_school_transactions(
    *,
    school_id: int,
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[Dict[str, Any]], int]:
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page
    status_value = (status or "").strip().lower()
    if status_value and status_value not in TRANSACTION_STATUSES:
        status_value = ""

    count_query = """
        SELECT COUNT(*) AS total
        FROM daftar_tamu_transactions t
        WHERE t.school_id = %s
          AND (%s = '' OR t.status = %s)
    """
    data_query = """
        SELECT
            t.id,
            t.visit_at,
            t.status,
            t.purpose,
            t.notes,
            t.photo_path,
            t.photo_raw_path,
            t.latitude,
            t.longitude,
            t.created_at,
            t.reviewer_notes,
            t.reviewed_at,
            reviewer.full_name AS reviewer_name,
            creator.full_name AS created_by_name,
            (
                SELECT STRING_AGG(u.full_name, ', ' ORDER BY u.full_name)
                FROM daftar_tamu_transaction_guests g
                LEFT JOIN dashboard_users u ON u.id = g.user_id
                WHERE g.transaction_id = t.id
            ) AS guest_names,
            (
                SELECT COUNT(*)
                FROM daftar_tamu_transaction_guests g
                WHERE g.transaction_id = t.id
            ) AS guest_count
        FROM daftar_tamu_transactions t
        LEFT JOIN dashboard_users reviewer ON reviewer.id = t.reviewed_by
        LEFT JOIN dashboard_users creator ON creator.id = t.created_by
        WHERE t.school_id = %s
          AND (%s = '' OR t.status = %s)
        ORDER BY t.visit_at DESC, t.id DESC
        LIMIT %s OFFSET %s
    """

    with get_cursor() as cur:
        cur.execute(count_query, [school_id, status_value, status_value])
        total_rows = int((cur.fetchone() or {}).get("total") or 0)

        cur.execute(
            data_query,
            [school_id, status_value, status_value, safe_per_page, offset],
        )
        rows = [dict(row) for row in cur.fetchall()]

    for row in rows:
        names_raw = row.get("guest_names") or ""
        names = [n.strip() for n in names_raw.split(",") if n.strip()]
        guest_count = int(row.get("guest_count") or 0)
        if not guest_count:
            guest_count = len(names)
        if names:
            if len(names) > 2:
                display = f"{names[0]} +{len(names) - 1}"
            elif len(names) == 2:
                display = f"{names[0]} & {names[1]}"
            else:
                display = names[0]
        else:
            display = None
        row["guest_display"] = display
        row["guest_count"] = guest_count

    return rows, total_rows


def list_admin_transactions(
    *,
    status: Optional[str] = None,
    search_query: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[Dict[str, Any]], int]:
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page

    status_value = (status or "").strip().lower()
    if status_value and status_value not in TRANSACTION_STATUSES:
        status_value = ""

    query_text, like_query = _build_search(search_query)

    count_query = """
        SELECT COUNT(*) AS total
        FROM daftar_tamu_transactions t
        JOIN portal_schools s ON s.id = t.school_id
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        WHERE (%s = '' OR t.status = %s)
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
          AND (
            %s = ''
            OR s.name ILIKE %s
            OR s.npsn ILIKE %s
            OR COALESCE(k.name, '') ILIKE %s
            OR COALESCE(l.name, '') ILIKE %s
            OR EXISTS (
                SELECT 1
                FROM daftar_tamu_transaction_guests g
                LEFT JOIN dashboard_users u ON u.id = g.user_id
                WHERE g.transaction_id = t.id
                  AND (
                    u.full_name ILIKE %s
                    OR u.email ILIKE %s
                    OR COALESCE(u.nip, '') ILIKE %s
                    OR COALESCE(u.nrk, '') ILIKE %s
                    OR COALESCE(u.role, '') ILIKE %s
                  )
            )
          )
    """
    data_query = """
        SELECT
            t.id,
            t.visit_at,
            t.status,
            t.purpose,
            t.notes,
            t.photo_path,
            t.photo_raw_path,
            t.latitude,
            t.longitude,
            t.created_at,
            t.reviewer_notes,
            t.reviewed_at,
            s.id AS school_id,
            s.name AS school_name,
            s.npsn,
            s.jenjang,
            k.name AS kecamatan,
            l.name AS kelurahan,
            reviewer.full_name AS reviewer_name,
            creator.full_name AS created_by_name,
            (
                SELECT STRING_AGG(u.full_name, ', ' ORDER BY u.full_name)
                FROM daftar_tamu_transaction_guests g
                LEFT JOIN dashboard_users u ON u.id = g.user_id
                WHERE g.transaction_id = t.id
            ) AS guest_names,
            (
                SELECT COUNT(*)
                FROM daftar_tamu_transaction_guests g
                WHERE g.transaction_id = t.id
            ) AS guest_count
        FROM daftar_tamu_transactions t
        JOIN portal_schools s ON s.id = t.school_id
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        LEFT JOIN dashboard_users reviewer ON reviewer.id = t.reviewed_by
        LEFT JOIN dashboard_users creator ON creator.id = t.created_by
        WHERE (%s = '' OR t.status = %s)
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
          AND (
            %s = ''
            OR s.name ILIKE %s
            OR s.npsn ILIKE %s
            OR COALESCE(k.name, '') ILIKE %s
            OR COALESCE(l.name, '') ILIKE %s
            OR EXISTS (
                SELECT 1
                FROM daftar_tamu_transaction_guests g
                LEFT JOIN dashboard_users u ON u.id = g.user_id
                WHERE g.transaction_id = t.id
                  AND (
                    u.full_name ILIKE %s
                    OR u.email ILIKE %s
                    OR COALESCE(u.nip, '') ILIKE %s
                    OR COALESCE(u.nrk, '') ILIKE %s
                    OR COALESCE(u.role, '') ILIKE %s
                  )
            )
          )
        ORDER BY t.visit_at DESC, t.id DESC
        LIMIT %s OFFSET %s
    """

    params_common = [
        status_value,
        status_value,
        date_from,
        date_from,
        date_to,
        date_to,
        query_text,
        like_query,
        like_query,
        like_query,
        like_query,
        like_query,
        like_query,
        like_query,
        like_query,
        like_query,
    ]

    with get_cursor() as cur:
        cur.execute(count_query, params_common)
        total_rows = int((cur.fetchone() or {}).get("total") or 0)

        cur.execute(data_query, params_common + [safe_per_page, offset])
        rows = [dict(row) for row in cur.fetchall()]

    for row in rows:
        names_raw = row.get("guest_names") or ""
        names = [n.strip() for n in names_raw.split(",") if n.strip()]
        guest_count = int(row.get("guest_count") or 0)
        if not guest_count:
            guest_count = len(names)
        if names:
            if len(names) > 2:
                display = f"{names[0]} +{len(names) - 1}"
            elif len(names) == 2:
                display = f"{names[0]} & {names[1]}"
            else:
                display = names[0]
        else:
            display = None
        row["guest_display"] = display
        row["guest_count"] = guest_count

    return rows, total_rows


def get_transaction_detail(transaction_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                t.id,
                t.visit_at,
                t.status,
                t.purpose,
                t.notes,
                t.photo_path,
                t.photo_raw_path,
                t.latitude,
                t.longitude,
                t.created_at,
                t.reviewer_notes,
                t.reviewed_at,
                s.id AS school_id,
                s.name AS school_name,
                s.npsn,
                s.jenjang,
                k.name AS kecamatan,
                l.name AS kelurahan,
                reviewer.full_name AS reviewer_name,
                creator.full_name AS created_by_name
            FROM daftar_tamu_transactions t
            JOIN portal_schools s ON s.id = t.school_id
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            LEFT JOIN dashboard_users reviewer ON reviewer.id = t.reviewed_by
            LEFT JOIN dashboard_users creator ON creator.id = t.created_by
            WHERE t.id = %s
            """,
            (transaction_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        detail = dict(row)

        cur.execute(
            """
            SELECT
                u.id,
                u.full_name,
                u.email,
                u.role,
                u.nrk,
                u.jabatan,
                u.degree_prefix,
                u.degree_suffix
            FROM daftar_tamu_transaction_guests g
            LEFT JOIN dashboard_users u ON u.id = g.user_id
            WHERE g.transaction_id = %s
            ORDER BY u.full_name
            """,
            (transaction_id,),
        )
        detail["guests"] = [dict(row) for row in cur.fetchall()]

    return detail


def update_transaction_status(
    *,
    transaction_id: int,
    status: str,
    reviewer_id: int,
    reviewer_notes: Optional[str] = None,
) -> bool:
    safe_status = (status or "").strip().lower()
    if safe_status not in TRANSACTION_STATUSES:
        raise ValueError("Invalid status")

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE daftar_tamu_transactions
            SET status = %s,
                reviewed_by = %s,
                reviewed_at = NOW(),
                reviewer_notes = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (safe_status, reviewer_id, reviewer_notes, transaction_id),
        )
        return cur.rowcount > 0


def fetch_guest_history(
    *,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(limit, 50))
    safe_offset = max(0, offset)
    query = """
        SELECT
            t.id,
            t.visit_at,
            t.status,
            s.name AS school_name,
            s.npsn,
            s.jenjang,
            k.name AS kecamatan,
            l.name AS kelurahan
        FROM daftar_tamu_transaction_guests g
        JOIN daftar_tamu_transactions t ON t.id = g.transaction_id
        JOIN portal_schools s ON s.id = t.school_id
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        WHERE g.user_id = %s
        ORDER BY t.visit_at DESC, t.id DESC
        LIMIT %s OFFSET %s
    """
    with get_cursor() as cur:
        cur.execute(query, [user_id, safe_limit, safe_offset])
        return [dict(row) for row in cur.fetchall()]
