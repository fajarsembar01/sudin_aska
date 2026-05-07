"""Query helpers for Daftar Tamu dashboard."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from dashboard.db_access import get_cursor

try:
    from zoneinfo import ZoneInfo
except (ImportError, ModuleNotFoundError):
    ZoneInfo = None

if ZoneInfo is not None:
    try:
        _JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
    except Exception:
        _JAKARTA_TZ = timezone(timedelta(hours=7), name="WIB")
else:
    _JAKARTA_TZ = timezone(timedelta(hours=7), name="WIB")


def _today_jakarta() -> date:
    return datetime.now(_JAKARTA_TZ).date()


SORT_OPTIONS = {
    "visits_desc": "people_count DESC, visit_day_count DESC, last_visit_date DESC NULLS LAST, school_name ASC",
    "visits_asc": "people_count ASC, visit_day_count ASC, last_visit_date DESC NULLS LAST, school_name ASC",
    "days_desc": "visit_day_count DESC, people_count DESC, last_visit_date DESC NULLS LAST, school_name ASC",
    "days_asc": "visit_day_count ASC, people_count ASC, last_visit_date DESC NULLS LAST, school_name ASC",
    "last_visit_desc": "last_visit_date DESC NULLS LAST, people_count DESC, school_name ASC",
    "last_visit_asc": "last_visit_date ASC NULLS FIRST, people_count DESC, school_name ASC",
    "name_asc": "school_name ASC",
    "name_desc": "school_name DESC",
}

DEFAULT_SORT = "days_desc"
TRANSACTION_STATUSES = {"pending", "approved", "rejected"}

USER_SORT_OPTIONS = {
    "visits_desc": "visit_count DESC, last_visit_date DESC NULLS LAST, full_name ASC",
    "visits_asc": "visit_count ASC, last_visit_date DESC NULLS LAST, full_name ASC",
    "last_visit_desc": "last_visit_date DESC NULLS LAST, visit_count DESC, full_name ASC",
    "last_visit_asc": "last_visit_date ASC NULLS FIRST, visit_count DESC, full_name ASC",
}
DEFAULT_USER_SORT = "visits_desc"
USER_VISIT_SORT_OPTIONS = {
    "date_desc": "ft.visit_at DESC, ft.id DESC",
    "date_asc": "ft.visit_at ASC, ft.id ASC",
}
DEFAULT_USER_VISIT_SORT = "date_desc"
SCHOOL_VISIT_SORT_OPTIONS = {
    "date_desc": "t.visit_at DESC, t.id DESC",
    "date_asc": "t.visit_at ASC, t.id ASC",
}
DEFAULT_SCHOOL_VISIT_SORT = "date_desc"
STAFF_NOTE_LEVELS = {"tidak_perlu", "pantau", "tindak_lanjut", "mendesak"}
STAFF_NOTE_LEVEL_RANK = {
    "mendesak": 0,
    "tindak_lanjut": 1,
    "pantau": 2,
    "tidak_perlu": 3,
}
GUESTBOOK_NOTIFICATION_CATEGORY = "daftar_tamu_status"
PANBERS_REOPEN_NOTIFICATION_CATEGORY = "panbers_reopen_status"
PANBERS_ASSIGNMENT_NOTIFICATION_CATEGORY = "panbers_assignment_status"
PANBERS_TEAM_MEMBER_NOTIFICATION_CATEGORY = "panbers_team_member_status"
PANBERS_FOLLOW_UP_NOTIFICATION_CATEGORY = "panbers_follow_up_status"
HOSPITALITY_NOTIFICATION_CATEGORY = "hospitality_status"
USER_APP_NOTIFICATION_CATEGORIES = (
    GUESTBOOK_NOTIFICATION_CATEGORY,
    PANBERS_REOPEN_NOTIFICATION_CATEGORY,
    PANBERS_ASSIGNMENT_NOTIFICATION_CATEGORY,
    PANBERS_TEAM_MEMBER_NOTIFICATION_CATEGORY,
    PANBERS_FOLLOW_UP_NOTIFICATION_CATEGORY,
    HOSPITALITY_NOTIFICATION_CATEGORY,
)
_NOTIFICATION_SCHEMA_READY = False
_HAS_DASHBOARD_USER_PROFILE_PHOTO_PATH: Optional[bool] = None

_GUEST_SCOPE_WHERE = """
      AND (
        %s = 'all'
        OR (%s = 'sudin' AND EXISTS (
            SELECT 1
            FROM daftar_tamu_transaction_guests g
            WHERE g.transaction_id = {tx_ref}
              AND (g.guest_type = 'sudin' OR g.guest_type IS NULL)
        ))
        OR (%s = 'umum' AND EXISTS (
            SELECT 1
            FROM daftar_tamu_transaction_guests g
            WHERE g.transaction_id = {tx_ref}
              AND g.guest_type = 'umum'
        ))
      )
"""

_TRANSACTION_USER_SCOPE_WHERE = """
      AND (
        %s::int IS NULL
        OR {tx_alias}.created_by = %s::int
        OR EXISTS (
            SELECT 1
            FROM daftar_tamu_transaction_guests g_owner
            WHERE g_owner.transaction_id = {tx_ref}
              AND g_owner.user_id = %s::int
        )
      )
"""

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

_PUBLIC_GUEST_CONTEXT_SUBQUERY = """
    SELECT STRING_AGG(
        CASE
            WHEN NULLIF(TRIM(COALESCE(g.student_name, '')), '') IS NOT NULL
                 OR NULLIF(TRIM(COALESCE(g.student_class, '')), '') IS NOT NULL
            THEN
                'Wali murid '
                || COALESCE(NULLIF(TRIM(g.student_name), ''), '-')
                || CASE
                    WHEN NULLIF(TRIM(COALESCE(g.student_class, '')), '') IS NOT NULL
                    THEN ' (Kelas ' || TRIM(g.student_class) || ')'
                    ELSE ''
                END
            WHEN NULLIF(TRIM(COALESCE(g.instansi, '')), '') IS NOT NULL
            THEN 'instansi : ' || TRIM(g.instansi)
            ELSE '-'
        END,
        ' | ' ORDER BY g.full_name
    )
    FROM daftar_tamu_general_transaction_guests g
    WHERE g.transaction_id = {tx_ref}
"""


def _has_dashboard_user_profile_photo_path() -> bool:
    """Return True if dashboard_users.profile_photo_path exists in active schemas."""
    global _HAS_DASHBOARD_USER_PROFILE_PHOTO_PATH
    if _HAS_DASHBOARD_USER_PROFILE_PHOTO_PATH is not None:
        return _HAS_DASHBOARD_USER_PROFILE_PHOTO_PATH

    exists = False
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = ANY (current_schemas(TRUE))
                      AND table_name = 'dashboard_users'
                      AND column_name = 'profile_photo_path'
                ) AS exists
                """
            )
            row = cur.fetchone() or {}
            exists = bool(row.get("exists"))
    except Exception:
        exists = False

    _HAS_DASHBOARD_USER_PROFILE_PHOTO_PATH = exists
    return exists

_ROLLUP_CTE = (
    """
WITH filtered_transactions AS (
    SELECT t.*
    FROM daftar_tamu_transactions t
    WHERE t.status = 'approved'
      AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
      AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
"""
    + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
    + _TRANSACTION_USER_SCOPE_WHERE.format(tx_alias="t", tx_ref="t.id")
    + """
),
school_rollup AS (
    SELECT
        s.id AS school_id,
        s.npsn,
        s.name AS school_name,
        s.jenjang,
        s.status,
        l.kecamatan_id AS kecamatan_id,
        k.name AS kecamatan,
        l.name AS kelurahan,
        s.alamat,
        COUNT(ft.id) AS visit_count,
        COALESCE(SUM((
            {_guest_count}
        )), 0) AS people_count,
        COUNT(DISTINCT ft.visit_at::date) AS visit_day_count,
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
      AND (%s::int[] IS NULL OR l.kecamatan_id = ANY(%s::int[]))
    GROUP BY
        s.id,
        s.npsn,
        s.name,
        s.jenjang,
        s.status,
        l.kecamatan_id,
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
    _guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="ft.id"),
    guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="t2.id"),
    guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="t2.id"),
)


def _build_search(search_query: Optional[str]) -> tuple[str, str]:
    query = (search_query or "").strip()
    return query, f"%{query}%"


def _normalize_staff_note_level(level: Optional[str]) -> str:
    value = (level or "").strip().lower()
    if value in {"mendesak", "urgent", "critical", "sangat_mendesak", "sangat mendesak"}:
        return "mendesak"
    if value in {"tindak_lanjut", "tindak lanjut", "normal", "follow_up", "perlu_tindakan"}:
        return "tindak_lanjut"
    if value in {"pantau", "monitor", "other", "lainnya", "lainnya/pantau"}:
        return "pantau"
    if value in {"tidak_perlu", "tidak perlu", "info", "informasi", "arsip", "no_action"}:
        return "tidak_perlu"
    if value in STAFF_NOTE_LEVELS:
        return value
    return ""


def _summarize_staff_notes(metadata_value: Any) -> Dict[str, Any]:
    metadata = metadata_value
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    if not isinstance(metadata, dict):
        return {
            "staff_note_text": "",
            "staff_note_level": "",
            "staff_note_updated_at": "",
            "staff_note_count": 0,
        }

    staff_notes = metadata.get("staff_notes")
    if not isinstance(staff_notes, dict):
        return {
            "staff_note_text": "",
            "staff_note_level": "",
            "staff_note_updated_at": "",
            "staff_note_count": 0,
        }

    best_note = ""
    best_level = ""
    best_updated_at = ""
    best_rank = 99
    note_count = 0

    for raw_entry in staff_notes.values():
        note_text = ""
        note_level = "tindak_lanjut"
        note_updated_at = ""

        if isinstance(raw_entry, dict):
            note_text = (raw_entry.get("note") or "").strip()
            note_level = _normalize_staff_note_level(raw_entry.get("level")) or "tindak_lanjut"
            note_updated_at = (raw_entry.get("updated_at") or "").strip()
        elif isinstance(raw_entry, str):
            note_text = raw_entry.strip()
            note_level = "tindak_lanjut"

        if not note_text:
            continue

        note_count += 1
        rank = STAFF_NOTE_LEVEL_RANK.get(note_level, 9)
        if rank < best_rank:
            best_rank = rank
            best_note = note_text
            best_level = note_level
            best_updated_at = note_updated_at
        elif rank == best_rank and note_updated_at:
            try:
                current_dt = datetime.fromisoformat(best_updated_at.replace("Z", "+00:00")) if best_updated_at else None
            except ValueError:
                current_dt = None
            try:
                incoming_dt = datetime.fromisoformat(note_updated_at.replace("Z", "+00:00"))
            except ValueError:
                incoming_dt = None
            if incoming_dt and (not current_dt or incoming_dt > current_dt):
                best_note = note_text
                best_level = note_level
                best_updated_at = note_updated_at

    return {
        "staff_note_text": best_note,
        "staff_note_level": best_level,
        "staff_note_updated_at": best_updated_at,
        "staff_note_count": note_count,
    }


def _ensure_guestbook_notification_schema() -> None:
    global _NOTIFICATION_SCHEMA_READY
    if _NOTIFICATION_SCHEMA_READY:
        return

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            ALTER TABLE notifications
            ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES dashboard_users(id) ON DELETE CASCADE
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notifications_user_status_created_at
            ON notifications (user_id, status, created_at DESC)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notifications_user_category_created_at
            ON notifications (user_id, category, created_at DESC)
            """
        )

    _NOTIFICATION_SCHEMA_READY = True


def _normalize_guest_scope(scope: Optional[str]) -> str:
    value = (scope or "").strip().lower()
    if value == "semua":
        value = "all"
    if value not in {"sudin", "umum", "all"}:
        value = "all"
    return value


def _normalize_school_status(status: Optional[str]) -> str:
    value = (status or "").strip().lower()
    if value in {"", "all", "semua"}:
        return ""
    if value in {"negeri", "state"}:
        return "NEGERI"
    if value in {"swasta", "private"}:
        return "SWASTA"
    return ""


def _normalize_kecamatan_ids(kecamatan_ids: Optional[List[int]]) -> Optional[List[int]]:
    if not kecamatan_ids:
        return None
    normalized: List[int] = []
    seen: set[int] = set()
    for raw_id in kecamatan_ids:
        try:
            kec_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if kec_id <= 0 or kec_id in seen:
            continue
        seen.add(kec_id)
        normalized.append(kec_id)
    return normalized or None


def _normalize_owner_user_id(owner_user_id: Optional[int]) -> Optional[int]:
    if owner_user_id is None:
        return None
    try:
        parsed = int(owner_user_id)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def ensure_daftar_tamu_seed_data() -> None:
    """No-op: daftar tamu now uses portal_schools and real transactions."""
    return


def fetch_dashboard_summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
    kecamatan_ids: Optional[List[int]] = None,
    owner_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch top-level summary stats for admin dashboard."""
    scope = _normalize_guest_scope(guest_scope)
    status_filter = _normalize_school_status(school_status)
    area_filter = _normalize_kecamatan_ids(kecamatan_ids)
    owner_filter = _normalize_owner_user_id(owner_user_id)
    cutoff = _today_jakarta() - timedelta(days=30)
    params: List[Any] = [
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
        owner_filter,
        owner_filter,
        owner_filter,
        area_filter,
        area_filter,
        status_filter,
        status_filter,
        status_filter,
        status_filter,
        status_filter,
        status_filter,
        status_filter,
        status_filter,
        cutoff,
        status_filter,
        status_filter,
        status_filter,
        status_filter,
        status_filter,
        status_filter,
        date_from,
        date_from,
        date_to,
        date_to,
        status_filter,
        status_filter,
        scope,
        scope,
        scope,
        owner_filter,
        owner_filter,
        owner_filter,
        date_from,
        date_from,
        date_to,
        date_to,
        status_filter,
        status_filter,
        scope,
        scope,
        scope,
        owner_filter,
        owner_filter,
        owner_filter,
    ]
    query = (
        _ROLLUP_CTE
        + """
    SELECT
        (SELECT COUNT(*)
            FROM school_rollup
            WHERE (%s = '' OR status = %s)) AS total_schools,
        (SELECT COALESCE(SUM(visit_count), 0)
            FROM school_rollup
            WHERE (%s = '' OR status = %s)) AS total_visits,
        (SELECT COUNT(*)
            FROM school_rollup
            WHERE visit_count > 0
              AND (%s = '' OR status = %s)) AS visited_schools,
        (SELECT COUNT(*)
            FROM school_rollup
            WHERE visit_count = 0
              AND (%s = '' OR status = %s)) AS unvisited_schools,
        (SELECT COUNT(*)
            FROM school_rollup
            WHERE (visit_count = 0 OR last_visit_date < %s::date)
              AND (%s = '' OR status = %s)) AS attention_schools,
        (SELECT MAX(last_visit_date)
            FROM school_rollup
            WHERE (%s = '' OR status = %s)) AS latest_visit_date,
        (SELECT COUNT(*)
            FROM filtered_transactions ft
            JOIN school_rollup sr ON sr.school_id = ft.school_id
            WHERE ft.visit_at >= date_trunc('month', CURRENT_DATE)
              AND (%s = '' OR sr.status = %s)) AS visits_this_month,
        (SELECT COUNT(*) FROM daftar_tamu_transactions t
            JOIN school_rollup sr ON sr.school_id = t.school_id
            WHERE t.status = 'pending'
              AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
              AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
              AND (%s = '' OR sr.status = %s)
              """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
        + _TRANSACTION_USER_SCOPE_WHERE.format(tx_alias="t", tx_ref="t.id")
        + """) AS pending_visits,
        (SELECT COUNT(*) FROM daftar_tamu_transactions t
            JOIN school_rollup sr ON sr.school_id = t.school_id
            WHERE t.status = 'rejected'
              AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
              AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
              AND (%s = '' OR sr.status = %s)
              """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
        + _TRANSACTION_USER_SCOPE_WHERE.format(tx_alias="t", tx_ref="t.id")
        + """) AS rejected_visits
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
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
    kecamatan_ids: Optional[List[int]] = None,
    owner_user_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch school rankings with search, sorting, and pagination."""
    scope = _normalize_guest_scope(guest_scope)
    status_filter = _normalize_school_status(school_status)
    area_filter = _normalize_kecamatan_ids(kecamatan_ids)
    owner_filter = _normalize_owner_user_id(owner_user_id)
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 500))
    offset = (safe_page - 1) * safe_per_page

    safe_sort = sort_key if sort_key in SORT_OPTIONS else DEFAULT_SORT
    order_sql = SORT_OPTIONS[safe_sort]
    query_text, like_query = _build_search(search_query)

    base_params: List[Any] = [
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
        owner_filter,
        owner_filter,
        owner_filter,
        area_filter,
        area_filter,
    ]
    search_params: List[Any] = [query_text, like_query, like_query, like_query, like_query]
    status_params: List[Any] = [status_filter, status_filter]

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
      AND (%s = '' OR status = %s)
      AND jenjang NOT IN ('MI', 'MTS', 'MA')
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
        people_count,
        visit_day_count,
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
      AND (%s = '' OR status = %s)
      AND jenjang NOT IN ('MI', 'MTS', 'MA')
    ORDER BY {order_sql}
    LIMIT %s OFFSET %s
    """
    )

    with get_cursor() as cur:
        cur.execute(count_query, base_params + search_params + status_params)
        count_row = cur.fetchone()
        total_rows = int(dict(count_row).get("total") or 0) if count_row else 0

        cur.execute(data_query, base_params + search_params + status_params + [safe_per_page, offset])
        rows = [dict(row) for row in cur.fetchall()]

    today = _today_jakarta()
    for index, row in enumerate(rows, start=offset + 1):
        row["rank"] = index
        row["visit_count"] = int(row.get("visit_count") or 0)
        row["people_count"] = int(row.get("people_count") or 0)
        row["visit_day_count"] = int(row.get("visit_day_count") or 0)
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


def fetch_school_visit_histogram(
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
    kecamatan_ids: Optional[List[int]] = None,
    owner_user_id: Optional[int] = None,
) -> Dict[int, int]:
    """Return histogram of school visit counts for filtered schools."""
    scope = _normalize_guest_scope(guest_scope)
    status_filter = _normalize_school_status(school_status)
    area_filter = _normalize_kecamatan_ids(kecamatan_ids)
    owner_filter = _normalize_owner_user_id(owner_user_id)
    query = (
        _ROLLUP_CTE
        + """
    SELECT
        visit_count::int AS visit_count,
        COUNT(*)::int AS school_count
    FROM school_rollup
    WHERE (%s = '' OR status = %s)
      AND jenjang NOT IN ('MI', 'MTS', 'MA')
    GROUP BY visit_count
    ORDER BY visit_count ASC
    """
    )
    params: List[Any] = [
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
        owner_filter,
        owner_filter,
        owner_filter,
        area_filter,
        area_filter,
        status_filter,
        status_filter,
    ]

    histogram: Dict[int, int] = {}
    with get_cursor() as cur:
        cur.execute(query, params)
        for row in cur.fetchall():
            visit_count = int(row.get("visit_count") or 0)
            school_count = int(row.get("school_count") or 0)
            histogram[visit_count] = school_count
    return histogram


def fetch_school_visit_bucket_rows(
    *,
    min_visits: int,
    max_visits: Optional[int] = None,
    page: int = 1,
    per_page: int = 20,
    sort_key: str = "visits_desc",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
    kecamatan_ids: Optional[List[int]] = None,
    owner_user_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch schools within a visit-count bucket for dashboard drill-down."""
    scope = _normalize_guest_scope(guest_scope)
    status_filter = _normalize_school_status(school_status)
    area_filter = _normalize_kecamatan_ids(kecamatan_ids)
    owner_filter = _normalize_owner_user_id(owner_user_id)
    safe_page = max(1, page)
    safe_per_page = max(5, min(per_page, 200))
    offset = (safe_page - 1) * safe_per_page

    safe_min_visits = max(0, int(min_visits))
    safe_max_visits: Optional[int] = None
    if max_visits is not None:
        try:
            parsed_max = int(max_visits)
            if parsed_max >= safe_min_visits:
                safe_max_visits = parsed_max
        except (TypeError, ValueError):
            safe_max_visits = None

    bucket_sort_options = {
        "visits_desc": "visit_count DESC, school_name ASC",
        "visits_asc": "visit_count ASC, school_name ASC",
        "days_desc": "visit_day_count DESC, school_name ASC",
        "days_asc": "visit_day_count ASC, school_name ASC",
        "name_asc": "school_name ASC",
        "name_desc": "school_name DESC",
        "last_visit_desc": "last_visit_date DESC NULLS LAST, school_name ASC",
        "last_visit_asc": "last_visit_date ASC NULLS FIRST, school_name ASC",
    }
    safe_sort = sort_key if sort_key in bucket_sort_options else "visits_desc"
    order_sql = bucket_sort_options[safe_sort]

    bucket_clause = "visit_count >= %s"
    bucket_params: List[Any] = [safe_min_visits]
    if safe_max_visits is not None:
        bucket_clause += " AND visit_count <= %s"
        bucket_params.append(safe_max_visits)

    count_query = (
        _ROLLUP_CTE
        + f"""
    SELECT COUNT(*) AS total
    FROM school_rollup
    WHERE (%s = '' OR status = %s)
      AND jenjang NOT IN ('MI', 'MTS', 'MA')
      AND {bucket_clause}
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
        visit_count,
        visit_day_count,
        last_visit_date,
        last_guest_names,
        last_guest_count
    FROM school_rollup
    WHERE (%s = '' OR status = %s)
      AND jenjang NOT IN ('MI', 'MTS', 'MA')
      AND {bucket_clause}
    ORDER BY {order_sql}
    LIMIT %s OFFSET %s
    """
    )

    base_params: List[Any] = [
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
        owner_filter,
        owner_filter,
        owner_filter,
        area_filter,
        area_filter,
        status_filter,
        status_filter,
    ]

    with get_cursor() as cur:
        cur.execute(count_query, base_params + bucket_params)
        count_row = cur.fetchone()
        total_rows = int(dict(count_row).get("total") or 0) if count_row else 0

        cur.execute(data_query, base_params + bucket_params + [safe_per_page, offset])
        rows = [dict(row) for row in cur.fetchall()]

    today = _today_jakarta()
    for index, row in enumerate(rows, start=offset + 1):
        row["rank"] = index
        row["visit_count"] = int(row.get("visit_count") or 0)
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


def fetch_user_rankings(
    *,
    page: int = 1,
    per_page: int = 10,
    sort_key: str = DEFAULT_USER_SORT,
    search_query: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch user rankings for approved users based on visit history."""
    scope = _normalize_guest_scope(guest_scope)
    status_filter = _normalize_school_status(school_status)
    safe_page = max(1, page)
    safe_per_page = max(5, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page

    safe_sort = sort_key if sort_key in USER_SORT_OPTIONS else DEFAULT_USER_SORT
    order_sql = USER_SORT_OPTIONS[safe_sort]
    query_text, like_query = _build_search(search_query)

    base_cte = (
        """
    WITH filtered_transactions AS (
        SELECT t.*
        FROM daftar_tamu_transactions t
        JOIN portal_schools s ON s.id = t.school_id
        WHERE t.status = 'approved'
          AND (%s = '' OR s.status = %s)
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
        """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
        + """
    ),
    user_transactions AS (
        SELECT ft.id AS transaction_id, ft.created_by AS user_id
        FROM filtered_transactions ft
        WHERE ft.created_by IS NOT NULL
        UNION
        SELECT ft.id AS transaction_id, g.user_id AS user_id
        FROM filtered_transactions ft
        JOIN daftar_tamu_transaction_guests g ON g.transaction_id = ft.id
        WHERE g.user_id IS NOT NULL
    ),
    user_rollup AS (
        SELECT
            u.id AS user_id,
            u.full_name,
            u.email,
            u.role,
            COUNT(ut.transaction_id) AS visit_count,
            MAX(ft.visit_at) AS last_visit_date,
            CASE
                WHEN u.role = 'coordinator' THEN 1
                WHEN u.role = 'staff' THEN 2
                ELSE 3
            END AS role_rank
        FROM dashboard_users u
        LEFT JOIN user_transactions ut ON ut.user_id = u.id
        LEFT JOIN filtered_transactions ft ON ft.id = ut.transaction_id
        WHERE u.account_status = 'approved'
          AND (u.role IS NULL OR u.role <> 'sekolah')
        GROUP BY u.id, u.full_name, u.email, u.role
    )
    """
    )

    search_clause = """
    WHERE (
        %s = ''
        OR r.full_name ILIKE %s
        OR r.email ILIKE %s
        OR COALESCE(r.role, '') ILIKE %s
        OR COALESCE(latest.school_name, '') ILIKE %s
        OR COALESCE(latest.school_kecamatan, '') ILIKE %s
    )
    """

    count_query = (
        base_cte
        + """
    SELECT COUNT(*) AS total
    FROM user_rollup r
    LEFT JOIN LATERAL (
        SELECT
            s.name AS school_name,
            k.name AS school_kecamatan,
            ft.visit_at
        FROM user_transactions ut
        JOIN filtered_transactions ft ON ft.id = ut.transaction_id
        JOIN portal_schools s ON s.id = ft.school_id
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        WHERE ut.user_id = r.user_id
        ORDER BY ft.visit_at DESC, ft.id DESC
        LIMIT 1
    ) latest ON TRUE
    """
        + search_clause
    )

    data_query = (
        base_cte
        + f"""
    SELECT
        r.user_id,
        r.full_name,
        r.email,
        r.role,
        r.visit_count,
        r.last_visit_date,
        latest.school_name AS last_school_name,
        latest.school_npsn,
        latest.school_kecamatan,
        history.visit_history_text
    FROM user_rollup r
    LEFT JOIN LATERAL (
        SELECT
            s.name AS school_name,
            s.npsn AS school_npsn,
            k.name AS school_kecamatan,
            ft.visit_at
        FROM user_transactions ut
        JOIN filtered_transactions ft ON ft.id = ut.transaction_id
        JOIN portal_schools s ON s.id = ft.school_id
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        WHERE ut.user_id = r.user_id
        ORDER BY ft.visit_at DESC, ft.id DESC
        LIMIT 1
    ) latest ON TRUE
    LEFT JOIN LATERAL (
        SELECT STRING_AGG(hist.label, E'\n' ORDER BY hist.visit_seq) AS visit_history_text
        FROM (
            SELECT
                visit_seq,
                CONCAT(
                    'Kunjungan ke-',
                    visit_seq,
                    ': ',
                    school_name,
                    ' (',
                    visit_date_label,
                    ')'
                ) AS label
            FROM (
                SELECT
                    ROW_NUMBER() OVER (ORDER BY ft.visit_at ASC, ft.id ASC) AS visit_seq,
                    s.name AS school_name,
                    TO_CHAR(ft.visit_at, 'DD Mon YYYY') AS visit_date_label
                FROM user_transactions ut
                JOIN filtered_transactions ft ON ft.id = ut.transaction_id
                JOIN portal_schools s ON s.id = ft.school_id
                WHERE ut.user_id = r.user_id
            ) numbered
        ) hist
    ) history ON TRUE
    """
        + search_clause
        + f"""
    ORDER BY
        r.role_rank ASC,
        {order_sql}
    LIMIT %s OFFSET %s
    """
    )

    params_common: List[Any] = [
        status_filter,
        status_filter,
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
        query_text,
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

    today = _today_jakarta()
    for idx, row in enumerate(rows, start=offset + 1):
        row["rank"] = idx
        row["visit_count"] = int(row.get("visit_count") or 0)
        last_visit = row.get("last_visit_date")
        row["days_since_visit"] = (today - last_visit.date()).days if last_visit else None

    return rows, total_rows


def list_user_transactions(
    *,
    user_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[Dict[str, Any]], int]:
    """List approved transactions linked to a specific user."""
    scope = _normalize_guest_scope(guest_scope)
    status_filter = _normalize_school_status(school_status)
    safe_page = max(1, page)
    safe_per_page = max(5, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page

    count_query = (
        """
        SELECT COUNT(*) AS total
        FROM daftar_tamu_transactions t
        JOIN portal_schools s ON s.id = t.school_id
        WHERE t.status = 'approved'
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
          AND (%s = '' OR s.status = %s)
          AND (
              t.created_by = %s
              OR EXISTS (
                  SELECT 1
                  FROM daftar_tamu_transaction_guests g
                  WHERE g.transaction_id = t.id
                    AND g.user_id = %s
              )
          )
        """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
    )

    data_query = (
        """
        SELECT
            t.id,
            t.visit_at,
            t.purpose,
            t.notes,
            t.photo_path,
            t.photo_raw_path,
            t.latitude,
            t.longitude,
            s.id AS school_id,
            s.name AS school_name,
            s.npsn,
            s.jenjang,
            k.name AS kecamatan,
            l.name AS kelurahan,
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
        WHERE t.status = 'approved'
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
          AND (%s = '' OR s.status = %s)
          AND (
              t.created_by = %s
              OR EXISTS (
                  SELECT 1
                  FROM daftar_tamu_transaction_guests g
                  WHERE g.transaction_id = t.id
                    AND g.user_id = %s
              )
          )
        """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
        + """
        ORDER BY t.visit_at DESC, t.id DESC
        LIMIT %s OFFSET %s
        """
    ).format(
        guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id"),
        guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="t.id"),
    )

    params = [
        date_from,
        date_from,
        date_to,
        date_to,
        status_filter,
        status_filter,
        user_id,
        user_id,
        scope,
        scope,
        scope,
    ]

    with get_cursor() as cur:
        cur.execute(count_query, params)
        total_rows = int((cur.fetchone() or {}).get("total") or 0)

        cur.execute(data_query, params + [safe_per_page, offset])
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


def fetch_user_visit_history(
    *,
    user_id: int,
    page: int = 1,
    per_page: int = 10,
    sort_key: str = DEFAULT_USER_VISIT_SORT,
    search_query: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch visit history rows for a user (creator or guest)."""
    scope = _normalize_guest_scope(guest_scope)
    status_filter = _normalize_school_status(school_status)
    safe_page = max(1, page)
    safe_per_page = max(5, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page

    safe_sort = sort_key if sort_key in USER_VISIT_SORT_OPTIONS else DEFAULT_USER_VISIT_SORT
    order_sql = USER_VISIT_SORT_OPTIONS[safe_sort]
    query_text, like_query = _build_search(search_query)

    base_cte = (
        """
    WITH filtered_transactions AS (
        SELECT t.*
        FROM daftar_tamu_transactions t
        JOIN portal_schools s ON s.id = t.school_id
        WHERE t.status = 'approved'
          AND (%s = '' OR s.status = %s)
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
        """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
        + """
    ),
    user_transactions AS (
        SELECT ft.id AS transaction_id, ft.created_by AS user_id
        FROM filtered_transactions ft
        WHERE ft.created_by IS NOT NULL
        UNION
        SELECT ft.id AS transaction_id, g.user_id AS user_id
        FROM filtered_transactions ft
        JOIN daftar_tamu_transaction_guests g ON g.transaction_id = ft.id
        WHERE g.user_id IS NOT NULL
    )
    """
    )

    search_clause = """
    AND (
        %s = ''
        OR s.name ILIKE %s
        OR COALESCE(ft.purpose, '') ILIKE %s
        OR to_char(ft.visit_at::date, 'YYYY-MM-DD') ILIKE %s
        OR to_char(ft.visit_at::date, 'DD Mon YYYY') ILIKE %s
    )
    """

    count_query = (
        base_cte
        + """
    SELECT COUNT(*) AS total
    FROM user_transactions ut
    JOIN filtered_transactions ft ON ft.id = ut.transaction_id
    JOIN portal_schools s ON s.id = ft.school_id
    WHERE ut.user_id = %s
    """
        + search_clause
    )

    data_query = (
        base_cte
        + f"""
    SELECT
        ft.id AS transaction_id,
        ft.visit_at,
        ft.purpose,
        ft.notes,
        ft.metadata,
        ft.photo_path,
        s.name AS school_name,
        s.npsn AS school_npsn,
        k.name AS school_kecamatan
    FROM user_transactions ut
    JOIN filtered_transactions ft ON ft.id = ut.transaction_id
    JOIN portal_schools s ON s.id = ft.school_id
    LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
    LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
    WHERE ut.user_id = %s
    """
        + search_clause
        + f"""
    ORDER BY {order_sql}
    LIMIT %s OFFSET %s
    """
    )

    params_common: List[Any] = [
        status_filter,
        status_filter,
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
        user_id,
        query_text,
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
        row.update(_summarize_staff_notes(row.get("metadata")))

    return rows, total_rows


def fetch_user_guestbook_history(
    *,
    user_id: int,
    page: int = 1,
    per_page: int = 10,
    sort_key: str = DEFAULT_USER_VISIT_SORT,
    status: Optional[str] = None,
    search_query: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch user guestbook history across all statuses by default."""
    scope = _normalize_guest_scope(guest_scope)
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page

    safe_sort = sort_key if sort_key in USER_VISIT_SORT_OPTIONS else DEFAULT_USER_VISIT_SORT
    order_sql = USER_VISIT_SORT_OPTIONS[safe_sort]
    query_text, like_query = _build_search(search_query)

    status_value = (status or "").strip().lower()
    if status_value in {"all", "semua"}:
        status_value = ""
    if status_value and status_value not in TRANSACTION_STATUSES:
        status_value = ""

    base_cte = (
        """
    WITH filtered_transactions AS (
        SELECT t.*
        FROM daftar_tamu_transactions t
        WHERE (%s = '' OR t.status = %s)
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
        """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
        + """
    ),
    user_transactions AS (
        SELECT ft.id AS transaction_id, ft.created_by AS user_id
        FROM filtered_transactions ft
        WHERE ft.created_by IS NOT NULL
        UNION
        SELECT ft.id AS transaction_id, g.user_id AS user_id
        FROM filtered_transactions ft
        JOIN daftar_tamu_transaction_guests g ON g.transaction_id = ft.id
        WHERE g.user_id IS NOT NULL
    )
    """
    )

    search_clause = """
    AND (
        %s = ''
        OR s.name ILIKE %s
        OR COALESCE(ft.purpose, '') ILIKE %s
        OR to_char(ft.visit_at::date, 'YYYY-MM-DD') ILIKE %s
        OR to_char(ft.visit_at::date, 'DD Mon YYYY') ILIKE %s
    )
    """

    count_query = (
        base_cte
        + """
    SELECT COUNT(*) AS total
    FROM user_transactions ut
    JOIN filtered_transactions ft ON ft.id = ut.transaction_id
    JOIN portal_schools s ON s.id = ft.school_id
    WHERE ut.user_id = %s
    """
        + search_clause
    )

    data_query = (
        base_cte
        + """
    SELECT
        ft.id AS transaction_id,
        ft.visit_at,
        ft.status,
        ft.purpose,
        ft.photo_path,
        ft.reviewer_notes,
        ft.reviewed_at,
        ft.metadata,
        s.name AS school_name,
        s.npsn AS school_npsn,
        reviewer.full_name AS reviewer_name,
        (
            {guest_names}
        ) AS guest_names,
        (
            {guest_count}
        ) AS guest_count
    FROM user_transactions ut
    JOIN filtered_transactions ft ON ft.id = ut.transaction_id
    JOIN portal_schools s ON s.id = ft.school_id
    LEFT JOIN dashboard_users reviewer ON reviewer.id = ft.reviewed_by
    WHERE ut.user_id = %s
    """.format(
            guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="ft.id"),
            guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="ft.id"),
        )
        + search_clause
        + f"""
    ORDER BY {order_sql}
    LIMIT %s OFFSET %s
    """
    )

    params_common: List[Any] = [
        status_value,
        status_value,
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
        user_id,
        query_text,
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


def fetch_school_visit_history(
    *,
    school_id: int,
    page: int = 1,
    per_page: int = 10,
    sort_key: str = DEFAULT_SCHOOL_VISIT_SORT,
    search_query: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    owner_user_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch visit history rows for a school."""
    scope = _normalize_guest_scope(guest_scope)
    owner_filter = _normalize_owner_user_id(owner_user_id)
    safe_page = max(1, page)
    safe_per_page = max(5, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page

    safe_sort = sort_key if sort_key in SCHOOL_VISIT_SORT_OPTIONS else DEFAULT_SCHOOL_VISIT_SORT
    order_sql = SCHOOL_VISIT_SORT_OPTIONS[safe_sort]
    query_text, like_query = _build_search(search_query)

    base_cte = (
        """
    WITH filtered_transactions AS (
        SELECT t.*
        FROM daftar_tamu_transactions t
        WHERE t.status = 'approved'
          AND t.school_id = %s
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
        """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
        + _TRANSACTION_USER_SCOPE_WHERE.format(tx_alias="t", tx_ref="t.id")
        + """
    )
    """
    )

    search_clause = """
    WHERE (
        %s = ''
        OR COALESCE(guests.guest_names, '') ILIKE %s
        OR COALESCE(t.purpose, '') ILIKE %s
        OR to_char(t.visit_at::date, 'YYYY-MM-DD') ILIKE %s
        OR to_char(t.visit_at::date, 'DD Mon YYYY') ILIKE %s
    )
    """

    guest_names_sql = _GUEST_NAMES_SUBQUERY.format(tx_ref="t.id")
    guest_count_sql = _GUEST_COUNT_SUBQUERY.format(tx_ref="t.id")

    count_query = (
        base_cte
        + """
    SELECT COUNT(*) AS total
    FROM filtered_transactions t
    LEFT JOIN LATERAL (
        SELECT
            ({guest_names}) AS guest_names,
            ({guest_count}) AS guest_count
    ) guests ON TRUE
    """.format(
            guest_names=guest_names_sql,
            guest_count=guest_count_sql,
        )
        + search_clause
    )

    data_query = (
        base_cte
        + """
    SELECT
        t.id AS transaction_id,
        t.visit_at,
        t.purpose,
        t.notes,
        t.metadata,
        t.photo_path,
        guests.guest_names,
        guests.guest_count
    FROM filtered_transactions t
    LEFT JOIN LATERAL (
        SELECT
            ({guest_names}) AS guest_names,
            ({guest_count}) AS guest_count
    ) guests ON TRUE
    """.format(
            guest_names=guest_names_sql,
            guest_count=guest_count_sql,
        )
        + search_clause
        + f"""
    ORDER BY {order_sql}
    LIMIT %s OFFSET %s
    """
    )

    params_common: List[Any] = [
        school_id,
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
        owner_filter,
        owner_filter,
        owner_filter,
        query_text,
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
        row.update(_summarize_staff_notes(row.get("metadata")))
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


def fetch_school_visit_days(
    *,
    school_id: int,
    page: int = 1,
    per_page: int = 10,
    search_query: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    owner_user_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch distinct visit dates for a school, optionally filtered by guest name."""
    scope = _normalize_guest_scope(guest_scope)
    owner_filter = _normalize_owner_user_id(owner_user_id)
    safe_page = max(1, page)
    safe_per_page = max(5, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page
    query_text, like_query = _build_search(search_query)

    base_cte = (
        """
    WITH filtered_transactions AS (
        SELECT t.*
        FROM daftar_tamu_transactions t
        WHERE t.status = 'approved'
          AND t.school_id = %s
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
        """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
        + _TRANSACTION_USER_SCOPE_WHERE.format(tx_alias="t", tx_ref="t.id")
        + """
    ),
    visit_days AS (
        SELECT
            ft.visit_at::date AS visit_date,
            COUNT(DISTINCT ft.id)::int AS visit_count,
            COUNT(guests.guest_name)::int AS people_count,
            (ARRAY_AGG(guests.guest_name ORDER BY ft.visit_at DESC, ft.id DESC, guests.guest_name ASC)
                FILTER (WHERE guests.guest_name IS NOT NULL))[1] AS last_guest_name
        FROM filtered_transactions ft
        LEFT JOIN LATERAL (
            SELECT u.full_name AS guest_name
            FROM daftar_tamu_transaction_guests g
            JOIN dashboard_users u ON u.id = g.user_id
            WHERE g.transaction_id = ft.id
              AND (g.guest_type = 'sudin' OR g.guest_type IS NULL)
              AND (%s IN ('all', 'sudin'))
            UNION ALL
            SELECT gg.full_name AS guest_name
            FROM daftar_tamu_transaction_guests g
            JOIN daftar_tamu_general_guests gg ON gg.id = g.general_guest_id
            WHERE g.transaction_id = ft.id
              AND g.guest_type = 'umum'
              AND (%s IN ('all', 'umum'))
        ) guests ON TRUE
        WHERE (
            %s = ''
            OR COALESCE(guests.guest_name, '') ILIKE %s
            OR to_char(ft.visit_at::date, 'YYYY-MM-DD') ILIKE %s
            OR to_char(ft.visit_at::date, 'DD Mon YYYY') ILIKE %s
        )
        GROUP BY ft.visit_at::date
    )
    """
    )

    params: List[Any] = [
        school_id,
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
        owner_filter,
        owner_filter,
        owner_filter,
        scope,
        scope,
        query_text,
        like_query,
        like_query,
        like_query,
    ]

    count_query = base_cte + "SELECT COUNT(*) AS total FROM visit_days"
    data_query = (
        base_cte
        + """
    SELECT visit_date, visit_count, people_count, last_guest_name
    FROM visit_days
    ORDER BY visit_date DESC
    LIMIT %s OFFSET %s
    """
    )

    with get_cursor() as cur:
        cur.execute(count_query, params)
        total_rows = int((cur.fetchone() or {}).get("total") or 0)
        cur.execute(data_query, params + [safe_per_page, offset])
        rows = [dict(row) for row in cur.fetchall()]

    for row in rows:
        row["visit_count"] = int(row.get("visit_count") or 0)
        row["people_count"] = int(row.get("people_count") or 0)
    return rows, total_rows


def fetch_school_visit_day_guests(
    *,
    school_id: int,
    visit_date: date,
    page: int = 1,
    per_page: int = 10,
    search_query: Optional[str] = None,
    guest_scope: Optional[str] = None,
    owner_user_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch guest names for one school's selected visit date."""
    scope = _normalize_guest_scope(guest_scope)
    owner_filter = _normalize_owner_user_id(owner_user_id)
    safe_page = max(1, page)
    safe_per_page = max(5, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page
    query_text, like_query = _build_search(search_query)

    base_cte = """
    WITH day_guests AS (
        SELECT
            t.id AS transaction_id,
            t.visit_at,
            t.purpose,
            u.full_name AS guest_name,
            'Sudindik JU 2'::TEXT AS instansi,
            COALESCE(g.guest_type, 'sudin') AS guest_type
        FROM daftar_tamu_transactions t
        JOIN daftar_tamu_transaction_guests g ON g.transaction_id = t.id
        JOIN dashboard_users u ON u.id = g.user_id
        WHERE t.status = 'approved'
          AND t.school_id = %s
          AND t.visit_at::date = %s::date
          AND (%s::int IS NULL OR t.created_by = %s::int OR EXISTS (
                SELECT 1
                FROM daftar_tamu_transaction_guests g_owner
                WHERE g_owner.transaction_id = t.id
                  AND g_owner.user_id = %s::int
          ))
          AND (g.guest_type = 'sudin' OR g.guest_type IS NULL)
          AND (%s IN ('all', 'sudin'))
        UNION ALL
        SELECT
            t.id AS transaction_id,
            t.visit_at,
            t.purpose,
            gg.full_name AS guest_name,
            gg.instansi AS instansi,
            'umum' AS guest_type
        FROM daftar_tamu_transactions t
        JOIN daftar_tamu_transaction_guests g ON g.transaction_id = t.id
        JOIN daftar_tamu_general_guests gg ON gg.id = g.general_guest_id
        WHERE t.status = 'approved'
          AND t.school_id = %s
          AND t.visit_at::date = %s::date
          AND (%s::int IS NULL OR t.created_by = %s::int OR EXISTS (
                SELECT 1
                FROM daftar_tamu_transaction_guests g_owner
                WHERE g_owner.transaction_id = t.id
                  AND g_owner.user_id = %s::int
          ))
          AND g.guest_type = 'umum'
          AND (%s IN ('all', 'umum'))
    )
    """
    search_clause = """
    WHERE (
        %s = ''
        OR COALESCE(guest_name, '') ILIKE %s
        OR COALESCE(instansi, '') ILIKE %s
        OR COALESCE(purpose, '') ILIKE %s
    )
    """
    params: List[Any] = [
        school_id,
        visit_date,
        owner_filter,
        owner_filter,
        owner_filter,
        scope,
        school_id,
        visit_date,
        owner_filter,
        owner_filter,
        owner_filter,
        scope,
        query_text,
        like_query,
        like_query,
        like_query,
    ]

    count_query = base_cte + "SELECT COUNT(*) AS total FROM day_guests " + search_clause
    data_query = (
        base_cte
        + """
    SELECT transaction_id, visit_at, purpose, guest_name, instansi, guest_type
    FROM day_guests
    """
        + search_clause
        + """
    ORDER BY visit_at ASC, transaction_id ASC, guest_name ASC
    LIMIT %s OFFSET %s
    """
    )

    with get_cursor() as cur:
        cur.execute(count_query, params)
        total_rows = int((cur.fetchone() or {}).get("total") or 0)
        cur.execute(data_query, params + [safe_per_page, offset])
        rows = [dict(row) for row in cur.fetchall()]
    return rows, total_rows


def list_user_visited_school_ids(
    *,
    user_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
) -> List[int]:
    """Return distinct school IDs visited by the user in the selected period."""
    scope = _normalize_guest_scope(guest_scope)
    query = (
        """
        SELECT DISTINCT t.school_id
        FROM daftar_tamu_transactions t
        WHERE t.created_by = %s
          AND t.status = 'approved'
          AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
          AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
        """
        + _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
    )
    params = [
        user_id,
        date_from,
        date_from,
        date_to,
        date_to,
        scope,
        scope,
        scope,
    ]
    with get_cursor() as cur:
        cur.execute(query, params)
        return [int(row["school_id"]) for row in cur.fetchall() if row.get("school_id") is not None]

def fetch_map_data(
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
    kecamatan_ids: Optional[List[int]] = None,
    owner_user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch map points for visit distribution."""
    scope = _normalize_guest_scope(guest_scope)
    owner_filter = _normalize_owner_user_id(owner_user_id)
    status_filter = _normalize_school_status(school_status)
    area_filter = _normalize_kecamatan_ids(kecamatan_ids)
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
    WHERE (%s = '' OR status = %s)
    ORDER BY {SORT_OPTIONS[DEFAULT_SORT]}
    """
    )

    with get_cursor() as cur:
        cur.execute(
            query,
            [
                date_from,
                date_from,
                date_to,
                date_to,
                scope,
                scope,
                scope,
                owner_filter,
                owner_filter,
                owner_filter,
                area_filter,
                area_filter,
                status_filter,
                status_filter,
            ],
        )
        rows = [dict(row) for row in cur.fetchall()]

    cutoff = _today_jakarta() - timedelta(days=30)
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
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
    kecamatan_ids: Optional[List[int]] = None,
    owner_user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch schools with zero approved visits in the selected period."""
    scope = _normalize_guest_scope(guest_scope)
    status_filter = _normalize_school_status(school_status)
    area_filter = _normalize_kecamatan_ids(kecamatan_ids)
    owner_filter = _normalize_owner_user_id(owner_user_id)
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
      AND (%s = '' OR status = %s)
    ORDER BY school_name ASC
    LIMIT %s
    """
    )
    with get_cursor() as cur:
        cur.execute(
            query,
            [
                date_from,
                date_from,
                date_to,
                date_to,
                scope,
                scope,
                scope,
                owner_filter,
                owner_filter,
                owner_filter,
                area_filter,
                area_filter,
                status_filter,
                status_filter,
                safe_limit,
            ],
        )
        return [dict(row) for row in cur.fetchall()]


def fetch_recent_visits(
    *,
    limit: int = 10,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    guest_scope: Optional[str] = None,
    school_status: Optional[str] = None,
    kecamatan_ids: Optional[List[int]] = None,
    owner_user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch latest approved visit records for side panel."""
    scope = _normalize_guest_scope(guest_scope)
    status_filter = _normalize_school_status(school_status)
    area_filter = _normalize_kecamatan_ids(kecamatan_ids)
    owner_filter = _normalize_owner_user_id(owner_user_id)
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
      AND (%s = '' OR s.status = %s)
      AND (%s::int[] IS NULL OR l.kecamatan_id = ANY(%s::int[]))
      AND t.status = 'approved'
      AND (%s::date IS NULL OR t.visit_at::date >= %s::date)
      AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
        """
    query = query.format(
        guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id"),
        guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="t.id"),
    )
    query += _GUEST_SCOPE_WHERE.format(tx_ref="t.id")
    query += _TRANSACTION_USER_SCOPE_WHERE.format(tx_alias="t", tx_ref="t.id")
    query += """
    ORDER BY t.visit_at DESC, t.id DESC
    LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(
            query,
            [
                status_filter,
                status_filter,
                area_filter,
                area_filter,
                date_from,
                date_from,
                date_to,
                date_to,
                scope,
                scope,
                scope,
                owner_filter,
                owner_filter,
                owner_filter,
                safe_limit,
            ],
        )
        return [dict(row) for row in cur.fetchall()]


def list_guest_candidates(search_query: Optional[str], limit: int = 20) -> List[Dict[str, Any]]:
    query_text, like_query = _build_search(search_query)
    safe_limit = max(1, min(limit, 50))
    profile_photo_select = (
        "profile_photo_path"
        if _has_dashboard_user_profile_photo_path()
        else "NULL::TEXT AS profile_photo_path"
    )
    query = """
        SELECT
            id,
            full_name,
            email,
            role,
            nrk,
            jabatan,
            account_status,
            {profile_photo_select},
            degree_prefix,
            degree_suffix
        FROM dashboard_users
        WHERE account_status IN ('approved', 'not_registered')
          AND LOWER(COALESCE(role, '')) IN ('staff', 'coordinator', 'admin')
          AND (
            %s = ''
            OR full_name ILIKE %s
            OR email ILIKE %s
            OR COALESCE(nip, '') ILIKE %s
            OR COALESCE(nrk, '') ILIKE %s
        )
        ORDER BY (account_status = 'approved') DESC, full_name ASC
        LIMIT %s
    """.format(profile_photo_select=profile_photo_select)
    with get_cursor() as cur:
        cur.execute(
            query,
            [query_text, like_query, like_query, like_query, like_query, safe_limit],
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
            g.is_parent,
            g.student_class,
            g.student_name,
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
            g.is_parent,
            g.student_class,
            g.student_name,
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
    guest_scope: Optional[str] = None,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[Dict[str, Any]], int]:
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 100))
    offset = (safe_page - 1) * safe_per_page
    status_value = (status or "").strip().lower()
    if status_value and status_value not in TRANSACTION_STATUSES:
        status_value = ""
    scope = _normalize_guest_scope(guest_scope)

    split_rows_cte = """
        WITH base AS (
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
                creator.full_name AS created_by_name
            FROM daftar_tamu_transactions t
            LEFT JOIN dashboard_users reviewer ON reviewer.id = t.reviewed_by
            LEFT JOIN dashboard_users creator ON creator.id = t.created_by
            WHERE t.school_id = %s
              AND (%s = '' OR t.status = %s)
        ),
        split_rows AS (
            SELECT
                b.*,
                'sudin'::TEXT AS guest_type,
                u.full_name AS guest_names,
                (
                    SELECT COUNT(*)
                    FROM daftar_tamu_transaction_guests g_count
                    WHERE g_count.transaction_id = b.id
                      AND (g_count.user_id IS NOT NULL OR g_count.general_guest_id IS NOT NULL)
                ) AS guest_count
            FROM base b
            JOIN daftar_tamu_transaction_guests g
              ON g.transaction_id = b.id
             AND g.user_id IS NOT NULL
             AND (g.guest_type = 'sudin' OR g.guest_type IS NULL)
            JOIN dashboard_users u ON u.id = g.user_id
            WHERE (%s = 'all' OR %s = 'sudin')
            UNION ALL
            SELECT
                b.*,
                'umum'::TEXT AS guest_type,
                gg.full_name AS guest_names,
                (
                    SELECT COUNT(*)
                    FROM daftar_tamu_transaction_guests g_count
                    WHERE g_count.transaction_id = b.id
                      AND (g_count.user_id IS NOT NULL OR g_count.general_guest_id IS NOT NULL)
                ) AS guest_count
            FROM base b
            JOIN daftar_tamu_transaction_guests g
              ON g.transaction_id = b.id
             AND g.general_guest_id IS NOT NULL
             AND g.guest_type = 'umum'
            JOIN daftar_tamu_general_guests gg ON gg.id = g.general_guest_id
            WHERE (%s = 'all' OR %s = 'umum')
        )
    """

    count_query = split_rows_cte + """
        SELECT COUNT(*) AS total
        FROM split_rows
    """
    data_query = split_rows_cte + """
        SELECT
            id,
            visit_at,
            status,
            purpose,
            notes,
            photo_path,
            photo_raw_path,
            latitude,
            longitude,
            created_at,
            reviewer_notes,
            reviewed_at,
            reviewer_name,
            created_by_name,
            guest_type,
            guest_names,
            guest_count
        FROM split_rows
        ORDER BY visit_at DESC, id DESC, CASE WHEN guest_type = 'sudin' THEN 0 ELSE 1 END, guest_names ASC
        LIMIT %s OFFSET %s
    """
    common_params: List[Any] = [
        school_id,
        status_value,
        status_value,
        scope,
        scope,
        scope,
        scope,
    ]

    with get_cursor() as cur:
        cur.execute(count_query, common_params)
        total_rows = int((cur.fetchone() or {}).get("total") or 0)

        cur.execute(
            data_query,
            common_params + [safe_per_page, offset],
        )
        rows = [dict(row) for row in cur.fetchall()]

    for row in rows:
        guest_name = (row.get("guest_names") or "").strip()
        row["guest_display"] = guest_name or None
        row["guest_count"] = int(row.get("guest_count") or (1 if guest_name else 0))
        row["guest_type"] = (row.get("guest_type") or "").strip().lower() or "sudin"
        row["guest_type_label"] = (
            "Sudindik JU 2" if row["guest_type"] == "sudin" else "Instansi Pemerintah Lainnya"
        )

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
            ) AS guest_count,
            (
                {guest_context}
            ) AS guest_context
        FROM daftar_tamu_general_transactions t
        LEFT JOIN dashboard_users reviewer ON reviewer.id = t.reviewed_by
        WHERE t.school_id = %s
          AND (%s = '' OR t.status = %s)
        ORDER BY t.visit_at DESC, t.id DESC
        LIMIT %s OFFSET %s
    """.format(
        guest_names=_PUBLIC_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id"),
        guest_count=_PUBLIC_GUEST_COUNT_SUBQUERY.format(tx_ref="t.id"),
        guest_context=_PUBLIC_GUEST_CONTEXT_SUBQUERY.format(tx_ref="t.id"),
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
        row["guest_context"] = (row.get("guest_context") or "").strip()

    return rows, total_rows


def fetch_school_pending_counts(*, school_id: int) -> Dict[str, int]:
    """Return pending counts for school: sudin transactions + public (web) submissions."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                (SELECT COUNT(*)
                 FROM daftar_tamu_transactions t
                 WHERE t.school_id = %s
                   AND t.status = 'pending'
                   AND EXISTS (
                       SELECT 1
                       FROM daftar_tamu_transaction_guests g
                       WHERE g.transaction_id = t.id
                         AND g.guest_type = 'sudin'
                   )) AS pending_sudin,
                (SELECT COUNT(*)
                 FROM daftar_tamu_general_transactions t
                 WHERE t.school_id = %s
                   AND t.status = 'pending') AS pending_public
            """,
            (school_id, school_id),
        )
        row = dict(cur.fetchone() or {})
    return {
        "pending_sudin": int(row.get("pending_sudin") or 0),
        "pending_public": int(row.get("pending_public") or 0),
    }


def list_admin_transactions(
    *,
    status: Optional[str] = None,
    staff_note_level: Optional[str] = None,
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
    if status_value and status_value not in TRANSACTION_STATUSES and status_value != "history":
        status_value = ""
    staff_note_level_value = _normalize_staff_note_level(staff_note_level)

    status_filter = """
        (
            %s = ''
            OR (%s = 'history' AND t.status IN ('approved', 'rejected'))
            OR t.status = %s
        )
    """
    staff_note_filter = """
        (
            %s = ''
            OR COALESCE(
                (
                    SELECT MIN(
                        CASE lower(COALESCE(sn.note_obj->>'level', 'tindak_lanjut'))
                            WHEN 'mendesak' THEN 1
                            WHEN 'critical' THEN 1
                            WHEN 'urgent' THEN 1
                            WHEN 'tindak_lanjut' THEN 2
                            WHEN 'normal' THEN 2
                            WHEN 'follow_up' THEN 2
                            WHEN 'pantau' THEN 3
                            WHEN 'monitor' THEN 3
                            WHEN 'other' THEN 3
                            WHEN 'tidak_perlu' THEN 4
                            WHEN 'info' THEN 4
                            WHEN 'informasi' THEN 4
                            WHEN 'arsip' THEN 4
                            ELSE 3
                        END
                    )
                    FROM jsonb_each(COALESCE(t.metadata->'staff_notes', '{}'::jsonb)) sn(user_key, note_obj)
                    WHERE NULLIF(TRIM(COALESCE(sn.note_obj->>'note', '')), '') IS NOT NULL
                ),
                0
            ) = CASE %s
                    WHEN 'mendesak' THEN 1
                    WHEN 'tindak_lanjut' THEN 2
                    WHEN 'pantau' THEN 3
                    WHEN 'tidak_perlu' THEN 4
                    ELSE 0
                END
            OR (
                %s = 'tindak_lanjut'
                AND EXISTS (
                    SELECT 1
                    FROM jsonb_each(COALESCE(t.metadata->'staff_notes', '{}'::jsonb)) sn(user_key, note_obj)
                    WHERE jsonb_typeof(sn.note_obj) = 'string'
                      AND NULLIF(TRIM(COALESCE(sn.note_obj #>> '{}', '')), '') IS NOT NULL
                )
            )
        )
    """

    query_text, like_query = _build_search(search_query)

    count_query = """
        SELECT COUNT(*) AS total
        FROM daftar_tamu_transactions t
        JOIN portal_schools s ON s.id = t.school_id
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        WHERE {status_filter}
          AND {staff_note_filter}
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
    """.format(status_filter=status_filter, staff_note_filter=staff_note_filter)
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
            t.metadata,
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
        WHERE {status_filter}
          AND {staff_note_filter}
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
        status_filter=status_filter,
        staff_note_filter=staff_note_filter,
        guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id"),
        guest_count=_GUEST_COUNT_SUBQUERY.format(tx_ref="t.id"),
    )

    params_common = [
        status_value,
        status_value,
        status_value,
        staff_note_level_value,
        staff_note_level_value,
        staff_note_level_value,
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
        row.update(_summarize_staff_notes(row.get("metadata")))
        row.pop("metadata", None)

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


def list_admin_public_school_summary(
    *,
    status: Optional[str] = None,
    search_query: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[Dict[str, Any]], int]:
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 200))
    offset = (safe_page - 1) * safe_per_page

    status_value = (status or "").strip().lower()
    if status_value and status_value not in TRANSACTION_STATUSES:
        status_value = ""

    query_text, like_query = _build_search(search_query)

    rollup_cte = """
        WITH filtered_transactions AS (
            SELECT t.*
            FROM daftar_tamu_general_transactions t
            WHERE (%s::date IS NULL OR t.visit_at::date >= %s::date)
              AND (%s::date IS NULL OR t.visit_at::date <= %s::date)
              AND (%s = '' OR t.status = %s)
        ),
        school_rollup AS (
            SELECT
                s.id AS school_id,
                s.npsn,
                s.name AS school_name,
                s.jenjang,
                k.name AS kecamatan,
                l.name AS kelurahan,
                COUNT(ft.id) AS total_visits,
                COUNT(*) FILTER (WHERE ft.status = 'pending') AS pending_visits,
                COUNT(*) FILTER (WHERE ft.status = 'approved') AS approved_visits,
                COUNT(*) FILTER (WHERE ft.status = 'rejected') AS rejected_visits,
                MAX(ft.visit_at) AS last_visit_at,
                latest.guest_names AS last_guest_names,
                latest.guest_count AS last_guest_count
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            LEFT JOIN filtered_transactions ft ON ft.school_id = s.id
            LEFT JOIN LATERAL (
                SELECT
                    ({guest_names}) AS guest_names,
                    ({guest_count}) AS guest_count
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
                latest.guest_names,
                latest.guest_count
        )
    """.format(
        guest_names=_PUBLIC_GUEST_NAMES_SUBQUERY.format(tx_ref="t2.id"),
        guest_count=_PUBLIC_GUEST_COUNT_SUBQUERY.format(tx_ref="t2.id"),
    )

    count_query = (
        rollup_cte
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
        rollup_cte
        + """
        SELECT
            school_id,
            npsn,
            school_name,
            jenjang,
            kecamatan,
            kelurahan,
            total_visits,
            pending_visits,
            approved_visits,
            rejected_visits,
            last_visit_at,
            last_guest_names,
            last_guest_count
        FROM school_rollup
        WHERE (
            %s = ''
            OR school_name ILIKE %s
            OR npsn ILIKE %s
            OR COALESCE(kecamatan, '') ILIKE %s
            OR COALESCE(kelurahan, '') ILIKE %s
        )
        ORDER BY total_visits DESC, last_visit_at DESC NULLS LAST, school_name ASC
        LIMIT %s OFFSET %s
        """
    )

    params_common = [
        date_from,
        date_from,
        date_to,
        date_to,
        status_value,
        status_value,
    ]
    search_params = [query_text, like_query, like_query, like_query, like_query]

    with get_cursor() as cur:
        cur.execute(count_query, params_common + search_params)
        total_rows = int((cur.fetchone() or {}).get("total") or 0)

        cur.execute(
            data_query,
            params_common + search_params + [safe_per_page, offset],
        )
        rows = [dict(row) for row in cur.fetchall()]

    for row in rows:
        row["total_visits"] = int(row.get("total_visits") or 0)
        row["pending_visits"] = int(row.get("pending_visits") or 0)
        row["approved_visits"] = int(row.get("approved_visits") or 0)
        row["rejected_visits"] = int(row.get("rejected_visits") or 0)

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

    return rows, total_rows


def get_transaction_detail(transaction_id: int) -> Optional[Dict[str, Any]]:
    profile_photo_select = (
        "u.profile_photo_path AS profile_photo_path"
        if _has_dashboard_user_profile_photo_path()
        else "NULL::TEXT AS profile_photo_path"
    )
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
                reviewer_tg.telegram_username AS reviewer_telegram_username,
                reviewer_tg.telegram_user_id AS reviewer_telegram_user_id,
                creator.full_name AS created_by_name
            FROM daftar_tamu_transactions t
            JOIN portal_schools s ON s.id = t.school_id
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            LEFT JOIN dashboard_users reviewer ON reviewer.id = t.reviewed_by
            LEFT JOIN LATERAL (
                SELECT
                    ta.telegram_username,
                    tu.telegram_user_id
                FROM telegram_admin_accounts ta
                LEFT JOIN telegram_users tu ON LOWER(tu.username) = LOWER(ta.telegram_username)
                WHERE ta.dashboard_user_id = reviewer.id
                ORDER BY ta.id DESC
                LIMIT 1
            ) reviewer_tg ON TRUE
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
            f"""
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
                {profile_photo_select},
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
                NULL::TEXT AS profile_photo_path,
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


def list_transaction_previous_single_guest_photos(transaction_id: int) -> List[Dict[str, Any]]:
    """List previous photo path per current guest, only from single-guest transactions."""
    profile_photo_select = (
        "u.profile_photo_path AS profile_photo_path"
        if _has_dashboard_user_profile_photo_path()
        else "NULL::TEXT AS profile_photo_path"
    )
    with get_cursor() as cur:
        cur.execute(
            f"""
            WITH current_guests AS (
                SELECT
                    g.user_id,
                    g.general_guest_id,
                    MIN(g.id) AS guest_order
                FROM daftar_tamu_transaction_guests g
                WHERE g.transaction_id = %s
                  AND (g.user_id IS NOT NULL OR g.general_guest_id IS NOT NULL)
                GROUP BY g.user_id, g.general_guest_id
            )
            SELECT
                cg.user_id,
                cg.general_guest_id,
                cg.guest_order,
                COALESCE(u.full_name, gg.full_name, 'Tamu') AS guest_name,
                {profile_photo_select},
                prev.photo_path AS previous_photo_path
            FROM current_guests cg
            LEFT JOIN dashboard_users u ON u.id = cg.user_id
            LEFT JOIN daftar_tamu_general_guests gg ON gg.id = cg.general_guest_id
            LEFT JOIN LATERAL (
                SELECT t.photo_path
                FROM daftar_tamu_transactions t
                JOIN daftar_tamu_transaction_guests g_prev ON g_prev.transaction_id = t.id
                WHERE t.id <> %s
                  AND t.photo_path IS NOT NULL
                  AND (
                        (cg.user_id IS NOT NULL AND g_prev.user_id = cg.user_id)
                        OR (
                            cg.general_guest_id IS NOT NULL
                            AND g_prev.general_guest_id = cg.general_guest_id
                        )
                  )
                  AND (
                        SELECT COUNT(*)
                        FROM daftar_tamu_transaction_guests g_count
                        WHERE g_count.transaction_id = t.id
                          AND (g_count.user_id IS NOT NULL OR g_count.general_guest_id IS NOT NULL)
                  ) = 1
                ORDER BY t.visit_at DESC, t.id DESC
                LIMIT 1
            ) prev ON TRUE
            ORDER BY cg.guest_order ASC, cg.user_id, cg.general_guest_id
            """,
            (transaction_id, transaction_id),
        )
        rows = [dict(row) for row in cur.fetchall()]
    return rows


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


def _build_guestbook_status_notification_text(status: str) -> tuple[str, str]:
    safe_status = (status or "").strip().lower()
    if safe_status == "approved":
        return "Buku tamu disetujui", "Disetujui"
    if safe_status == "rejected":
        return "Buku tamu ditolak", "Ditolak"
    return "Status buku tamu diperbarui", "Menunggu Verifikasi"


def _normalize_notification_categories(categories: Optional[List[str]] = None) -> tuple[str, ...]:
    source = categories if categories else list(USER_APP_NOTIFICATION_CATEGORIES)
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in source:
        value = (raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


def create_user_notifications(
    *,
    recipient_ids: List[int],
    category: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
    reference_table: Optional[str] = None,
    reference_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    _ensure_guestbook_notification_schema()

    safe_recipient_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in recipient_ids or []:
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if user_id <= 0 or user_id in seen:
            continue
        seen.add(user_id)
        safe_recipient_ids.append(user_id)
    if not safe_recipient_ids:
        return 0

    safe_category = (category or "").strip()
    safe_title = (title or "").strip()
    if not safe_category or not safe_title:
        return 0

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM dashboard_users
            WHERE id = ANY(%s::int[])
              AND role IN ('staff', 'coordinator', 'sekolah')
            """,
            [safe_recipient_ids],
        )
        eligible_ids = [int(row["id"]) for row in cur.fetchall() if row.get("id")]

    if not eligible_ids:
        return 0

    payload = json.dumps(metadata or {})
    insert_rows = [
        (
            user_id,
            safe_category,
            safe_title,
            (message or "").strip() or None,
            (link or "").strip() or None,
            (reference_table or "").strip() or None,
            int(reference_id) if reference_id else None,
            payload,
        )
        for user_id in eligible_ids
    ]
    with get_cursor(commit=True) as cur:
        cur.executemany(
            """
            INSERT INTO notifications (
                user_id,
                category,
                title,
                message,
                status,
                link,
                reference_table,
                reference_id,
                metadata
            )
            VALUES (%s, %s, %s, %s, 'unread', %s, %s, %s, %s::jsonb)
            """,
            insert_rows,
        )
    return len(insert_rows)


def fetch_user_notification_summary(
    *,
    user_id: int,
    categories: Optional[List[str]] = None,
) -> Dict[str, int]:
    _ensure_guestbook_notification_schema()
    safe_categories = _normalize_notification_categories(categories)
    if not safe_categories:
        return {"unread_count": 0, "total_count": 0}

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE n.status = 'unread') AS unread_count,
                COUNT(*) AS total_count
            FROM notifications n
            WHERE n.user_id = %s
              AND n.status <> 'archived'
              AND n.category = ANY(%s::text[])
            """,
            [int(user_id), list(safe_categories)],
        )
        row = dict(cur.fetchone() or {})
    return {
        "unread_count": int(row.get("unread_count") or 0),
        "total_count": int(row.get("total_count") or 0),
    }


def list_user_notifications(
    *,
    user_id: int,
    limit: int = 8,
    categories: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 8), 50))
    _ensure_guestbook_notification_schema()
    safe_categories = _normalize_notification_categories(categories)
    if not safe_categories:
        return []

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                n.id,
                n.category,
                n.title,
                n.message,
                n.status,
                n.link,
                n.reference_table,
                n.reference_id,
                n.metadata,
                n.created_at,
                n.read_at
            FROM notifications n
            WHERE n.user_id = %s
              AND n.status <> 'archived'
              AND n.category = ANY(%s::text[])
            ORDER BY n.created_at DESC, n.id DESC
            LIMIT %s
            """,
            [int(user_id), list(safe_categories), safe_limit],
        )
        rows = [dict(row) for row in cur.fetchall()]

    for row in rows:
        metadata_value = row.get("metadata")
        if isinstance(metadata_value, str):
            try:
                row["metadata"] = json.loads(metadata_value)
            except json.JSONDecodeError:
                row["metadata"] = {}
        elif not isinstance(metadata_value, dict):
            row["metadata"] = {}

    return rows


def mark_user_notifications_read(
    *,
    user_id: int,
    notification_ids: Optional[List[int]] = None,
    mark_all: bool = False,
    categories: Optional[List[str]] = None,
) -> int:
    safe_ids: List[int] = []
    for raw_id in notification_ids or []:
        try:
            safe_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    _ensure_guestbook_notification_schema()
    safe_categories = _normalize_notification_categories(categories)
    if not safe_categories:
        return 0

    with get_cursor(commit=True) as cur:
        if mark_all:
            cur.execute(
                """
                UPDATE notifications n
                SET status = 'read',
                    read_at = COALESCE(n.read_at, NOW())
                WHERE n.user_id = %s
                  AND n.status = 'unread'
                  AND n.category = ANY(%s::text[])
                """,
                [int(user_id), list(safe_categories)],
            )
            return cur.rowcount

        if not safe_ids:
            return 0

        cur.execute(
            """
            UPDATE notifications n
            SET status = 'read',
                read_at = COALESCE(n.read_at, NOW())
            WHERE n.user_id = %s
              AND n.status = 'unread'
              AND n.category = ANY(%s::text[])
              AND n.id = ANY(%s::int[])
            """,
            [int(user_id), list(safe_categories), safe_ids],
        )
        return cur.rowcount


def create_guestbook_status_notifications(
    *,
    transaction_id: int,
    status: str,
    actor_name: Optional[str] = None,
    reviewer_notes: Optional[str] = None,
    link: Optional[str] = None,
    school_link: Optional[str] = None,
) -> int:
    safe_status = (status or "").strip().lower()
    if safe_status not in TRANSACTION_STATUSES:
        raise ValueError("Invalid status")

    _ensure_guestbook_notification_schema()

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                t.id,
                t.school_id,
                t.visit_at,
                s.name AS school_name,
                (
                    {guest_names}
                ) AS guest_names
            FROM daftar_tamu_transactions t
            JOIN portal_schools s ON s.id = t.school_id
            WHERE t.id = %s
            """.format(guest_names=_GUEST_NAMES_SUBQUERY.format(tx_ref="t.id")),
            [int(transaction_id)],
        )
        tx_row = cur.fetchone()
        if not tx_row:
            return 0
        tx_data = dict(tx_row)

        cur.execute(
            """
            SELECT DISTINCT target.user_id, u.role
            FROM (
                SELECT g.user_id
                FROM daftar_tamu_transaction_guests g
                WHERE g.transaction_id = %s
                  AND g.user_id IS NOT NULL
                UNION
                SELECT t.created_by AS user_id
                FROM daftar_tamu_transactions t
                WHERE t.id = %s
                  AND t.created_by IS NOT NULL
            ) target
            JOIN dashboard_users u ON u.id = target.user_id
            WHERE u.role IN ('staff', 'coordinator', 'sekolah')
            """,
            [int(transaction_id), int(transaction_id)],
        )
        recipient_rows = [dict(row) for row in cur.fetchall()]

    staff_coordinator_ids: list[int] = []
    school_ids: list[int] = []
    for row in recipient_rows:
        raw_id = row.get("user_id")
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        role = (row.get("role") or "").strip().lower()
        if role == "sekolah":
            school_ids.append(user_id)
        else:
            staff_coordinator_ids.append(user_id)

    if not staff_coordinator_ids and not school_ids:
        return 0

    raw_guest_names = (tx_data.get("guest_names") or "").strip()
    guest_names = [name.strip() for name in raw_guest_names.split(",") if name.strip()]
    guest_summary = ""
    if guest_names:
        if len(guest_names) > 2:
            guest_summary = f"{guest_names[0]} +{len(guest_names) - 1}"
        elif len(guest_names) == 2:
            guest_summary = f"{guest_names[0]} & {guest_names[1]}"
        else:
            guest_summary = guest_names[0]

    title, status_label = _build_guestbook_status_notification_text(safe_status)
    school_name = (tx_data.get("school_name") or "Sekolah").strip()
    actor_label = (actor_name or "").strip()
    note_text = (reviewer_notes or "").strip()
    if len(note_text) > 220:
        note_text = note_text[:217].rstrip() + "..."

    message_parts = [f"{school_name}: status menjadi {status_label}."]
    if guest_summary:
        message_parts.append(f"Tamu: {guest_summary}.")
    if actor_label:
        message_parts.append(f"Oleh {actor_label}.")
    if note_text:
        message_parts.append(f"Catatan: {note_text}")
    message = " ".join(message_parts).strip()

    metadata = {
        "transaction_id": int(transaction_id),
        "status": safe_status,
        "status_label": status_label,
        "actor_name": actor_label,
        "school_id": tx_data.get("school_id"),
        "school_name": school_name,
        "visit_at": tx_data.get("visit_at").isoformat() if tx_data.get("visit_at") else None,
        "guest_summary": guest_summary,
    }
    if note_text:
        metadata["reviewer_notes"] = note_text

    total_created = 0
    if staff_coordinator_ids:
        total_created += create_user_notifications(
            recipient_ids=staff_coordinator_ids,
            category=GUESTBOOK_NOTIFICATION_CATEGORY,
            title=title,
            message=message,
            link=link,
            reference_table="daftar_tamu_transactions",
            reference_id=int(transaction_id),
            metadata=metadata,
        )
    if school_ids:
        total_created += create_user_notifications(
            recipient_ids=school_ids,
            category=GUESTBOOK_NOTIFICATION_CATEGORY,
            title=title,
            message=message,
            link=(school_link or "").strip() or link,
            reference_table="daftar_tamu_transactions",
            reference_id=int(transaction_id),
            metadata=metadata,
        )
    return total_created


def fetch_user_guestbook_notification_summary(
    *,
    user_id: int,
) -> Dict[str, int]:
    return fetch_user_notification_summary(user_id=user_id, categories=[GUESTBOOK_NOTIFICATION_CATEGORY])


def list_user_guestbook_notifications(
    *,
    user_id: int,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    return list_user_notifications(
        user_id=user_id,
        limit=limit,
        categories=[GUESTBOOK_NOTIFICATION_CATEGORY],
    )


def mark_user_guestbook_notifications_read(
    *,
    user_id: int,
    notification_ids: Optional[List[int]] = None,
    mark_all: bool = False,
) -> int:
    return mark_user_notifications_read(
        user_id=user_id,
        notification_ids=notification_ids,
        mark_all=mark_all,
        categories=[GUESTBOOK_NOTIFICATION_CATEGORY],
    )


def upsert_transaction_staff_note(
    *,
    transaction_id: int,
    user_id: int,
    note: Optional[str] = None,
    level: Optional[str] = None,
) -> bool:
    safe_note = (note or "").strip()
    safe_level = _normalize_staff_note_level(level) or "tindak_lanjut"
    note_path = ["staff_notes", str(user_id)]

    if safe_note:
        payload = json.dumps(
            {
                "note": safe_note,
                "level": safe_level,
                "updated_at": datetime.now(_JAKARTA_TZ).isoformat(timespec="seconds"),
            }
        )
        query = """
            UPDATE daftar_tamu_transactions t
            SET metadata = jsonb_set(COALESCE(t.metadata, '{}'::jsonb), %s::text[], %s::jsonb, true),
                updated_at = NOW()
            WHERE t.id = %s
              AND t.status = 'approved'
              AND COALESCE(t.photo_path, '') <> ''
              AND (
                  t.created_by = %s
                  OR EXISTS (
                      SELECT 1
                      FROM daftar_tamu_transaction_guests g
                      WHERE g.transaction_id = t.id
                        AND g.user_id = %s
                  )
              )
        """
        params: List[Any] = [note_path, payload, transaction_id, user_id, user_id]
    else:
        query = """
            UPDATE daftar_tamu_transactions t
            SET metadata = (COALESCE(t.metadata, '{}'::jsonb) #- %s::text[]),
                updated_at = NOW()
            WHERE t.id = %s
              AND t.status = 'approved'
              AND COALESCE(t.photo_path, '') <> ''
              AND (
                  t.created_by = %s
                  OR EXISTS (
                      SELECT 1
                      FROM daftar_tamu_transaction_guests g
                      WHERE g.transaction_id = t.id
                        AND g.user_id = %s
                  )
              )
        """
        params = [note_path, transaction_id, user_id, user_id]

    with get_cursor(commit=True) as cur:
        cur.execute(query, params)
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


def list_popular_purposes(*, limit: int = 50, min_count: int = 1) -> List[str]:
    safe_limit = max(1, min(int(limit or 50), 500))
    safe_min_count = max(1, min(int(min_count or 1), 1000))

    with get_cursor() as cur:
        cur.execute(
            """
            WITH normalized_purposes AS (
                SELECT
                    regexp_replace(btrim(COALESCE(t.purpose, '')), '\s+', ' ', 'g') AS purpose_clean
                FROM daftar_tamu_transactions t
                WHERE COALESCE(btrim(t.purpose), '') <> ''
            ),
            ranked AS (
                SELECT
                    lower(purpose_clean) AS purpose_key,
                    MIN(purpose_clean) AS purpose_label,
                    COUNT(*) AS usage_count
                FROM normalized_purposes
                GROUP BY lower(purpose_clean)
            )
            SELECT purpose_label
            FROM ranked
            WHERE usage_count >= %s
            ORDER BY usage_count DESC, lower(purpose_label) ASC
            LIMIT %s
            """,
            [safe_min_count, safe_limit],
        )
        rows = [dict(row) for row in cur.fetchall()]

    purposes: List[str] = []
    for row in rows:
        value = (row.get("purpose_label") or "").strip()
        if value:
            purposes.append(value)
    return purposes


def list_purpose_keywords_by_usage(*, active_only: bool = True, limit: int = 50) -> List[str]:
    safe_limit = max(1, min(int(limit or 50), 500))

    with get_cursor() as cur:
        cur.execute(
            """
            WITH keyword_source AS (
                SELECT
                    keyword,
                    lower(regexp_replace(btrim(keyword), '\s+', ' ', 'g')) AS keyword_key
                FROM daftar_tamu_purpose_keywords
                WHERE (%s = FALSE OR active = TRUE)
            ),
            purpose_usage AS (
                SELECT
                    lower(regexp_replace(btrim(COALESCE(t.purpose, '')), '\s+', ' ', 'g')) AS purpose_key,
                    COUNT(*)::int AS usage_count
                FROM daftar_tamu_transactions t
                WHERE COALESCE(btrim(t.purpose), '') <> ''
                GROUP BY 1
            )
            SELECT
                ks.keyword,
                ks.keyword_key,
                COALESCE(pu.usage_count, 0) AS usage_count
            FROM keyword_source ks
            LEFT JOIN purpose_usage pu ON pu.purpose_key = ks.keyword_key
            ORDER BY COALESCE(pu.usage_count, 0) DESC, ks.keyword_key ASC
            LIMIT %s
            """,
            [bool(active_only), safe_limit],
        )
        rows = [dict(row) for row in cur.fetchall()]

    keywords: List[str] = []
    seen: set[str] = set()
    for row in rows:
        kw = (row.get("keyword") or "").strip()
        key = (row.get("keyword_key") or "").strip() or kw.lower()
        if not kw or key in seen:
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


_UX_METRICS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_ux_metrics (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    session_key TEXT NOT NULL,
    page_path TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, session_key)
);
"""

_UX_METRICS_UPDATED_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_ux_metrics_updated_at
ON daftar_tamu_ux_metrics (updated_at DESC);
"""

_UX_METRICS_USER_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_ux_metrics_user_id
ON daftar_tamu_ux_metrics (user_id);
"""


def _ensure_guestbook_ux_metrics_table() -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(_UX_METRICS_TABLE_SQL)
        cur.execute(_UX_METRICS_UPDATED_INDEX_SQL)
        cur.execute(_UX_METRICS_USER_INDEX_SQL)


def upsert_guestbook_ux_metrics(
    *,
    user_id: int,
    session_key: str,
    payload: Dict[str, Any],
    page_path: Optional[str] = None,
) -> Dict[str, Any]:
    _ensure_guestbook_ux_metrics_table()
    safe_session = (session_key or "").strip()
    if not safe_session:
        raise ValueError("session_key wajib diisi.")

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO daftar_tamu_ux_metrics (user_id, session_key, page_path, payload)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (user_id, session_key)
            DO UPDATE SET
                page_path = EXCLUDED.page_path,
                payload = EXCLUDED.payload,
                updated_at = NOW()
            RETURNING id, user_id, session_key, page_path, payload, created_at, updated_at
            """,
            [int(user_id), safe_session, (page_path or "").strip() or None, json.dumps(payload or {})],
        )
        row = cur.fetchone()
    return dict(row) if row else {}


def fetch_guestbook_ux_metric_rows(
    *,
    days: int = 14,
    limit: int = 400,
) -> List[Dict[str, Any]]:
    _ensure_guestbook_ux_metrics_table()
    safe_days = max(1, min(int(days or 14), 90))
    safe_limit = max(1, min(int(limit or 400), 2000))
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                m.id,
                m.user_id,
                u.full_name,
                u.email,
                u.role,
                m.session_key,
                m.page_path,
                m.payload,
                m.created_at,
                m.updated_at
            FROM daftar_tamu_ux_metrics m
            LEFT JOIN dashboard_users u ON u.id = m.user_id
            WHERE m.updated_at >= NOW() - (%s || ' days')::interval
            ORDER BY m.updated_at DESC
            LIMIT %s
            """,
            [safe_days, safe_limit],
        )
        rows = [dict(row) for row in cur.fetchall()]
    return rows
