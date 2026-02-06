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

_GUEST_NAMES_SUBQUERY = """
    SELECT STRING_AGG(guest_name, ', ' ORDER BY guest_name)
    FROM (
        SELECT u.full_name AS guest_name
        FROM daftar_tamu_transaction_guests g
        JOIN dashboard_users u ON u.id = g.user_id
        WHERE g.transaction_id = {tx_ref}
          AND (g.guest_type = 'sudin' OR g.guest_type IS NULL)
        UNION ALL
        SELECT gg.full_name AS guest_name
        FROM daftar_tamu_transaction_guests g
        JOIN daftar_tamu_general_guests gg ON gg.id = g.general_guest_id
        WHERE g.transaction_id = {tx_ref}
          AND g.guest_type = 'umum'
    ) names
"""

_GUEST_COUNT_SUBQUERY = """
    SELECT COUNT(*)
    FROM daftar_tamu_transaction_guests g
    WHERE g.transaction_id = {tx_ref}
      AND (g.user_id IS NOT NULL OR g.general_guest_id IS NOT NULL)
"""

_PUBLIC_GUEST_NAMES_SUBQUERY = """
    SELECT STRING_AGG(g.full_name, ', ' ORDER BY g.full_name)
    FROM daftar_tamu_general_transaction_guests g
    WHERE g.transaction_id = {tx_ref}
"""

_PUBLIC_GUEST_COUNT_SUBQUERY = """
    SELECT COUNT(*)
    FROM daftar_tamu_general_transaction_guests g
    WHERE g.transaction_id = {tx_ref}
"""

_ROLLUP_CTE = (
    """
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
            {guest_names}
        ) AS guest_names,
        (
            {guest_count}
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
).format(
    guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="t2.id"),
    guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="t2.id"),
)


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
            {guest_names}
        ) AS guest_names,
        (
            {guest_count}
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
    """.format(
        guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id"),
        guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="t.id"),
    )
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


def list_general_guest_candidates(search_query: Optional[str], limit: int = 20) -> List[Dict[str, Any]]:
    query_text, like_query = _build_search(search_query)
    safe_limit = max(1, min(limit, 50))
    query = """
        SELECT
            g.id,
            g.full_name,
            g.email,
            g.phone,
            g.instansi,
            g.jabatan,
            g.is_verified,
            COUNT(*) OVER (PARTITION BY lower(g.full_name)) AS name_count,
            MAX(CASE WHEN g.is_verified THEN 1 ELSE 0 END) OVER (PARTITION BY lower(g.full_name)) AS has_verified
        FROM daftar_tamu_general_guests g
        WHERE g.is_deleted = FALSE
          AND (%s = ''
          OR g.full_name ILIKE %s
          OR COALESCE(g.email, '') ILIKE %s
          OR COALESCE(g.phone, '') ILIKE %s
          OR COALESCE(g.instansi, '') ILIKE %s
          OR COALESCE(g.jabatan, '') ILIKE %s)
        ORDER BY g.is_verified DESC, g.full_name ASC
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(
            query,
            [query_text, like_query, like_query, like_query, like_query, like_query, safe_limit],
        )
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["has_duplicate"] = int(row.get("name_count") or 0) > 1
        row["has_verified"] = bool(row.get("has_verified"))
        row.pop("name_count", None)
        row.pop("has_verified", None)
    return rows


def list_general_guests_admin(
    *,
    search_query: Optional[str] = None,
    verified: Optional[bool] = None,
    deleted: Optional[bool] = None,
    page: int = 1,
    per_page: int = 20,
) -> Tuple[List[Dict[str, Any]], int]:
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page
    query_text, like_query = _build_search(search_query)

    filter_verified = None
    if verified is True:
        filter_verified = True
    elif verified is False:
        filter_verified = False

    filter_deleted = None
    if deleted is True:
        filter_deleted = True
    elif deleted is False:
        filter_deleted = False

    count_query = """
        SELECT COUNT(*) AS total
        FROM daftar_tamu_general_guests g
        WHERE (%s = '' OR g.full_name ILIKE %s OR COALESCE(g.email, '') ILIKE %s OR COALESCE(g.phone, '') ILIKE %s OR COALESCE(g.instansi, '') ILIKE %s)
          AND (%s::boolean IS NULL OR g.is_verified = %s::boolean)
          AND (%s::boolean IS NULL OR g.is_deleted = %s::boolean)
    """
    data_query = """
        SELECT
            g.id,
            g.full_name,
            g.email,
            g.phone,
            g.instansi,
            g.jabatan,
            g.is_verified,
            g.is_deleted,
            g.deleted_at,
            g.created_at,
            g.verified_at,
            creator.full_name AS created_by_name,
            verifier.full_name AS verified_by_name,
            deleter.full_name AS deleted_by_name,
            COUNT(*) OVER (PARTITION BY lower(g.full_name)) AS name_count
        FROM daftar_tamu_general_guests g
        LEFT JOIN dashboard_users creator ON creator.id = g.created_by
        LEFT JOIN dashboard_users verifier ON verifier.id = g.verified_by
        LEFT JOIN dashboard_users deleter ON deleter.id = g.deleted_by
        WHERE (%s = '' OR g.full_name ILIKE %s OR COALESCE(g.email, '') ILIKE %s OR COALESCE(g.phone, '') ILIKE %s OR COALESCE(g.instansi, '') ILIKE %s)
          AND (%s::boolean IS NULL OR g.is_verified = %s::boolean)
          AND (%s::boolean IS NULL OR g.is_deleted = %s::boolean)
        ORDER BY g.is_verified DESC, g.full_name ASC, g.id DESC
        LIMIT %s OFFSET %s
    """

    params = [
        query_text,
        like_query,
        like_query,
        like_query,
        like_query,
        filter_verified,
        filter_verified,
        filter_deleted,
        filter_deleted,
    ]
    with get_cursor() as cur:
        cur.execute(count_query, params)
        total_rows = int((cur.fetchone() or {}).get("total") or 0)
        cur.execute(data_query, params + [safe_per_page, offset])
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["has_duplicate"] = int(row.get("name_count") or 0) > 1
        row.pop("name_count", None)
    return rows, total_rows


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
                {guest_names}
            ) AS guest_names,
            (
                {guest_count}
            ) AS guest_count
        FROM daftar_tamu_transactions t
        LEFT JOIN dashboard_users reviewer ON reviewer.id = t.reviewed_by
        LEFT JOIN dashboard_users creator ON creator.id = t.created_by
        WHERE t.school_id = %s
          AND (%s = '' OR t.status = %s)
        ORDER BY t.visit_at DESC, t.id DESC
        LIMIT %s OFFSET %s
    """.format(
        guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id"),
        guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="t.id"),
    )

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


def list_school_public_transactions(
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
        FROM daftar_tamu_general_transactions t
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
            t.created_at,
            t.reviewer_notes,
            t.reviewed_at,
            reviewer.full_name AS reviewer_name,
            (
                {guest_names}
            ) AS guest_names,
            (
                {guest_count}
            ) AS guest_count
        FROM daftar_tamu_general_transactions t
        LEFT JOIN dashboard_users reviewer ON reviewer.id = t.reviewed_by
        WHERE t.school_id = %s
          AND (%s = '' OR t.status = %s)
        ORDER BY t.visit_at DESC, t.id DESC
        LIMIT %s OFFSET %s
    """.format(
        guest_names=_PUBLIC_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id"),
        guest_count=_PUBLIC_GUEST_COUNT_SUBQUERY.format(tx_ref="t.id"),
    )

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
                LEFT JOIN daftar_tamu_general_guests gg ON gg.id = g.general_guest_id
                WHERE g.transaction_id = t.id
                  AND (
                    u.full_name ILIKE %s
                    OR u.email ILIKE %s
                    OR COALESCE(u.nip, '') ILIKE %s
                    OR COALESCE(u.nrk, '') ILIKE %s
                    OR COALESCE(u.role, '') ILIKE %s
                    OR gg.full_name ILIKE %s
                    OR COALESCE(gg.phone, '') ILIKE %s
                    OR COALESCE(gg.instansi, '') ILIKE %s
                    OR COALESCE(gg.jabatan, '') ILIKE %s
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
                {guest_names}
            ) AS guest_names,
            (
                {guest_count}
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
                LEFT JOIN daftar_tamu_general_guests gg ON gg.id = g.general_guest_id
                WHERE g.transaction_id = t.id
                  AND (
                    u.full_name ILIKE %s
                    OR u.email ILIKE %s
                    OR COALESCE(u.nip, '') ILIKE %s
                    OR COALESCE(u.nrk, '') ILIKE %s
                    OR COALESCE(u.role, '') ILIKE %s
                    OR gg.full_name ILIKE %s
                    OR COALESCE(gg.phone, '') ILIKE %s
                    OR COALESCE(gg.instansi, '') ILIKE %s
                    OR COALESCE(gg.jabatan, '') ILIKE %s
                  )
            )
          )
        ORDER BY t.visit_at DESC, t.id DESC
        LIMIT %s OFFSET %s
    """.format(
        guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id"),
        guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="t.id"),
    )

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


def list_admin_public_transactions(
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
        FROM daftar_tamu_general_transactions t
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
                FROM daftar_tamu_general_transaction_guests g
                WHERE g.transaction_id = t.id
                  AND (
                    g.full_name ILIKE %s
                    OR COALESCE(g.email, '') ILIKE %s
                    OR COALESCE(g.phone, '') ILIKE %s
                    OR COALESCE(g.instansi, '') ILIKE %s
                    OR COALESCE(g.jabatan, '') ILIKE %s
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
            (
                {guest_names}
            ) AS guest_names,
            (
                {guest_count}
            ) AS guest_count
        FROM daftar_tamu_general_transactions t
        JOIN portal_schools s ON s.id = t.school_id
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        LEFT JOIN dashboard_users reviewer ON reviewer.id = t.reviewed_by
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
                FROM daftar_tamu_general_transaction_guests g
                WHERE g.transaction_id = t.id
                  AND (
                    g.full_name ILIKE %s
                    OR COALESCE(g.email, '') ILIKE %s
                    OR COALESCE(g.phone, '') ILIKE %s
                    OR COALESCE(g.instansi, '') ILIKE %s
                    OR COALESCE(g.jabatan, '') ILIKE %s
                  )
            )
          )
        ORDER BY t.visit_at DESC, t.id DESC
        LIMIT %s OFFSET %s
    """.format(
        guest_names=_PUBLIC_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id"),
        guest_count=_PUBLIC_GUEST_COUNT_SUBQUERY.format(tx_ref="t.id"),
    )

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
                u.id AS id,
                'sudin' AS guest_type,
                u.full_name,
                u.email,
                u.role,
                u.nrk,
                u.jabatan,
                u.degree_prefix,
                u.degree_suffix,
                NULL::TEXT AS instansi,
                NULL::TEXT AS phone,
                NULL::BOOLEAN AS is_verified
            FROM daftar_tamu_transaction_guests g
            JOIN dashboard_users u ON u.id = g.user_id
            WHERE g.transaction_id = %s
              AND (g.guest_type = 'sudin' OR g.guest_type IS NULL)
            UNION ALL
            SELECT
                NULL::INTEGER AS id,
                'umum' AS guest_type,
                gg.full_name,
                NULL::TEXT AS email,
                NULL::TEXT AS role,
                NULL::TEXT AS nrk,
                gg.jabatan,
                NULL::TEXT AS degree_prefix,
                NULL::TEXT AS degree_suffix,
                gg.instansi,
                gg.phone,
                gg.is_verified
            FROM daftar_tamu_transaction_guests g
            JOIN daftar_tamu_general_guests gg ON gg.id = g.general_guest_id
            WHERE g.transaction_id = %s
              AND g.guest_type = 'umum'
            ORDER BY full_name
            """,
            (transaction_id, transaction_id),
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


def update_public_transaction_status(
    *,
    transaction_id: int,
    status: str,
    reviewer_id: int,
    reviewer_notes: Optional[str] = None,
    school_id: Optional[int] = None,
) -> bool:
    safe_status = (status or "").strip().lower()
    if safe_status not in TRANSACTION_STATUSES:
        raise ValueError("Invalid status")

    query = """
        UPDATE daftar_tamu_general_transactions
        SET status = %s,
            reviewed_by = %s,
            reviewed_at = NOW(),
            reviewer_notes = %s,
            updated_at = NOW()
        WHERE id = %s
    """
    params = [safe_status, reviewer_id, reviewer_notes, transaction_id]
    if school_id is not None:
        query += " AND school_id = %s"
        params.append(school_id)

    with get_cursor(commit=True) as cur:
        cur.execute(query, params)
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


def list_purpose_keywords(*, active_only: bool = True, limit: int = 50) -> List[str]:
    safe_limit = max(1, min(int(limit or 50), 500))
    where_sql = "WHERE active = TRUE" if active_only else ""

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT keyword
            FROM daftar_tamu_purpose_keywords
            {where_sql}
            ORDER BY lower(keyword) ASC
            LIMIT %s
            """,
            [safe_limit],
        )
        rows = [dict(row) for row in cur.fetchall()]

    keywords: List[str] = []
    seen: set[str] = set()
    for row in rows:
        kw = (row.get("keyword") or "").strip()
        if not kw:
            continue
        key = kw.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(kw)
    return keywords


def list_purpose_keyword_rows(*, limit: int = 200) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 200), 1000))
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                pk.id,
                pk.keyword,
                pk.active,
                pk.created_at,
                pk.updated_at,
                u.full_name AS created_by_name
            FROM daftar_tamu_purpose_keywords pk
            LEFT JOIN dashboard_users u ON u.id = pk.created_by
            ORDER BY lower(pk.keyword) ASC, pk.id DESC
            LIMIT %s
            """,
            [safe_limit],
        )
        return [dict(row) for row in cur.fetchall()]


def upsert_purpose_keyword(*, keyword: str, created_by: Optional[int] = None) -> Dict[str, Any]:
    clean = " ".join((keyword or "").split()).strip()
    if not clean:
        raise ValueError("Keyword kosong.")
    if len(clean) > 80:
        raise ValueError("Keyword terlalu panjang (maks 80 karakter).")

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO daftar_tamu_purpose_keywords (keyword, active, created_by)
            VALUES (%s, TRUE, %s)
            ON CONFLICT (keyword) DO UPDATE
            SET active = TRUE,
                updated_at = NOW()
            RETURNING id, keyword, active
            """,
            [clean, created_by],
        )
        row = cur.fetchone()
    return dict(row) if row else {"keyword": clean, "active": True}


def set_purpose_keyword_active(*, keyword_id: int, active: bool) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE daftar_tamu_purpose_keywords
            SET active = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            [bool(active), int(keyword_id)],
        )
        return cur.rowcount > 0


_CONTACT_PRIORITY_DEFAULTS = [
    ("website", 1),
    ("email", 2),
    ("phone", 3),
    ("instagram", 4),
    ("wa_channel", 5),
]


def _ensure_contact_priority_defaults() -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT COUNT(*) AS total FROM daftar_tamu_contact_priority")
        total = int((cur.fetchone() or {}).get("total") or 0)
        if total == 0:
            for key, order in _CONTACT_PRIORITY_DEFAULTS:
                cur.execute(
                    """
                    INSERT INTO daftar_tamu_contact_priority (contact_key, sort_order, active)
                    VALUES (%s, %s, TRUE)
                    ON CONFLICT (contact_key) DO NOTHING
                    """,
                    [key, order],
                )


def list_contact_priority_rows(*, limit: int = 50) -> List[Dict[str, Any]]:
    _ensure_contact_priority_defaults()
    safe_limit = max(1, min(int(limit or 50), 200))
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, contact_key, sort_order, active, created_at, updated_at
            FROM daftar_tamu_contact_priority
            ORDER BY sort_order ASC, id ASC
            LIMIT %s
            """,
            [safe_limit],
        )
        return [dict(row) for row in cur.fetchall()]


def update_contact_priority(*, keyword_id: int, sort_order: int, active: bool) -> bool:
    safe_order = max(1, min(int(sort_order), 99))
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE daftar_tamu_contact_priority
            SET sort_order = %s,
                active = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            [safe_order, bool(active), int(keyword_id)],
        )
        return cur.rowcount > 0
