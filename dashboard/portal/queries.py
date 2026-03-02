"""Database queries for portal assessment system."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence
from datetime import datetime, date, timedelta, timezone
import calendar

from ..db_access import get_cursor

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

_AUTO_PERIOD_MONTHS_AHEAD = 36
_MONTH_NAMES_ID = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)

PORTAL_UNDO_WINDOW_DEFAULT_SECONDS = 7
PORTAL_UNDO_WINDOW_MIN_SECONDS = 1
PORTAL_UNDO_WINDOW_MAX_SECONDS = 60
PORTAL_LEGACY_SCORE_SCALE_MAX = 3
PORTAL_NEW_SCORE_SCALE_MAX = 5
PORTAL_NEW_SCORE_MIN = 1
PORTAL_LEGACY_SCORE_MIN = 0


def _sync_portal_assessment_periods_sequence(cur) -> None:
    """Keep portal_assessment_periods.id sequence in sync with existing max(id)."""
    cur.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('portal_assessment_periods', 'id'),
            COALESCE((SELECT MAX(id) FROM portal_assessment_periods), 1),
            EXISTS(SELECT 1 FROM portal_assessment_periods)
        )
        """
    )


def _normalize_score_scale_max(value: Any) -> int:
    """Normalize score scale marker to supported values."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = PORTAL_LEGACY_SCORE_SCALE_MAX
    if parsed == PORTAL_NEW_SCORE_SCALE_MAX:
        return PORTAL_NEW_SCORE_SCALE_MAX
    return PORTAL_LEGACY_SCORE_SCALE_MAX


def _normalize_score_pct(score: Any, scale_max: Any) -> float:
    """Convert raw score to 0-100 percentage using assessment scale."""
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        return 0.0
    normalized_scale = _normalize_score_scale_max(scale_max)
    if normalized_scale <= 0:
        return 0.0
    return (score_value / normalized_scale) * 100.0


def _score_pct_sql(score_expr: str, scale_expr: str) -> str:
    """Build SQL expression that normalizes raw score to 0-100 percentage."""
    return (
        f"(CASE WHEN COALESCE({scale_expr}, {PORTAL_LEGACY_SCORE_SCALE_MAX}) = {PORTAL_NEW_SCORE_SCALE_MAX} "
        f"THEN ({score_expr})::DECIMAL / {PORTAL_NEW_SCORE_SCALE_MAX}.0 * 100.0 "
        f"ELSE ({score_expr})::DECIMAL / {PORTAL_LEGACY_SCORE_SCALE_MAX}.0 * 100.0 END)"
    )


def normalize_portal_undo_window_seconds(
    value: Any,
    *,
    fallback: int = PORTAL_UNDO_WINDOW_DEFAULT_SECONDS,
) -> int:
    """Normalize undo delay (seconds) into configured safe range."""
    safe_fallback = PORTAL_UNDO_WINDOW_DEFAULT_SECONDS
    try:
        safe_fallback = int(fallback)
    except (TypeError, ValueError):
        safe_fallback = PORTAL_UNDO_WINDOW_DEFAULT_SECONDS
    safe_fallback = max(PORTAL_UNDO_WINDOW_MIN_SECONDS, min(PORTAL_UNDO_WINDOW_MAX_SECONDS, safe_fallback))

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = safe_fallback
    return max(PORTAL_UNDO_WINDOW_MIN_SECONDS, min(PORTAL_UNDO_WINDOW_MAX_SECONDS, parsed))


def fetch_portal_undo_window_seconds() -> int:
    """Return global undo waiting window (seconds) used across Portal."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT undo_window_seconds
            FROM portal_ui_settings
            WHERE id = 1
            """
        )
        row = cur.fetchone()
    if not row:
        return PORTAL_UNDO_WINDOW_DEFAULT_SECONDS
    if isinstance(row, dict):
        raw_value = row.get("undo_window_seconds")
    elif isinstance(row, (list, tuple)) and row:
        raw_value = row[0]
    else:
        raw_value = None
    return normalize_portal_undo_window_seconds(raw_value, fallback=PORTAL_UNDO_WINDOW_DEFAULT_SECONDS)


def upsert_portal_undo_window_seconds(seconds: int, updated_by: Optional[int]) -> int:
    """Persist global undo waiting window and return saved value."""
    normalized = normalize_portal_undo_window_seconds(seconds)
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_ui_settings (id, undo_window_seconds, updated_at, updated_by)
            VALUES (1, %s, NOW(), %s)
            ON CONFLICT (id)
            DO UPDATE SET
                undo_window_seconds = EXCLUDED.undo_window_seconds,
                updated_at = NOW(),
                updated_by = EXCLUDED.updated_by
            RETURNING undo_window_seconds
            """,
            (normalized, updated_by),
        )
        row = cur.fetchone()
    if not row:
        return normalized
    if isinstance(row, dict):
        raw_value = row.get("undo_window_seconds")
    elif isinstance(row, (list, tuple)) and row:
        raw_value = row[0]
    else:
        raw_value = normalized
    return normalize_portal_undo_window_seconds(raw_value, fallback=normalized)


def list_preview_pins(admin_user_id: int) -> List[int]:
    """Return pinned target user ids for preview workspace."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT target_user_id
            FROM portal_preview_pins
            WHERE admin_user_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (admin_user_id,),
        )
        rows = cur.fetchall()
    pinned_ids: List[int] = []
    for row in rows or []:
        target_id = None
        if isinstance(row, dict):
            target_id = row.get("target_user_id")
        elif isinstance(row, (list, tuple)) and row:
            target_id = row[0]
        if target_id is None:
            continue
        try:
            pinned_ids.append(int(target_id))
        except (TypeError, ValueError):
            continue
    return pinned_ids


def is_preview_pin(admin_user_id: int, target_user_id: int) -> bool:
    """Check if target user is pinned for preview workspace."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM portal_preview_pins
            WHERE admin_user_id = %s AND target_user_id = %s
            LIMIT 1
            """,
            (admin_user_id, target_user_id),
        )
        row = cur.fetchone()
    return bool(row)


def add_preview_pin(admin_user_id: int, target_user_id: int) -> None:
    """Pin a target account for preview workspace."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_preview_pins (admin_user_id, target_user_id, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (admin_user_id, target_user_id)
            DO NOTHING
            """,
            (admin_user_id, target_user_id),
        )


def remove_preview_pin(admin_user_id: int, target_user_id: int) -> None:
    """Unpin a target account for preview workspace."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM portal_preview_pins
            WHERE admin_user_id = %s AND target_user_id = %s
            """,
            (admin_user_id, target_user_id),
        )


def list_portal_schools(
    search: Optional[str] = None,
    jenjang: Optional[str] = None,
    kecamatan_id: Optional[int] = None,
    kelurahan_id: Optional[int] = None,
    active_only: bool = True,
) -> List[Dict[str, Any]]:
    """Fetch all schools available for assessment."""
    conditions = []
    params = []
    
    if active_only:
        conditions.append("s.active = TRUE")
    
    if jenjang:
        conditions.append("s.jenjang = %s")
        params.append(jenjang)
    
    if kecamatan_id:
        conditions.append("l.kecamatan_id = %s")
        params.append(kecamatan_id)
    
    if kelurahan_id:
        conditions.append("s.kelurahan_id = %s")
        params.append(kelurahan_id)
    
    if search:
        conditions.append("(s.name ILIKE %s OR s.npsn ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    query = f"""
        SELECT 
            s.id, s.npsn, s.name, s.jenjang, s.alamat, s.status,
            s.kelurahan_id, s.user_id, s.active, s.created_at,
            l.name as kelurahan_name,
            k.name as kecamatan_name
        FROM portal_schools s
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        {where_clause}
        ORDER BY k.name, l.name, s.jenjang, s.name
    """
    
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def get_school_by_id(school_id: int) -> Optional[Dict[str, Any]]:
    """Get a single school by ID."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.id, s.npsn, s.name, s.jenjang, s.alamat, s.status,
                   s.kelurahan_id, s.user_id, s.active, s.created_at,
                   l.name as kelurahan_name,
                   k.name as kecamatan_name
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            WHERE s.id = %s
            """,
            (school_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_portal_rooms(active_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch all room types with their aspects."""
    condition = "WHERE r.active = TRUE" if active_only else ""
    aspect_condition = "AND a.active = TRUE" if active_only else ""
    
    query = f"""
        SELECT 
            r.id, r.name, r.description, r.category, r.sort_order, r.active, r.is_required,
            COALESCE(
                json_agg(
                    json_build_object(
                        'id', a.id,
                        'name', a.name,
                        'description', a.description,
                        'sort_order', a.sort_order,
                        'active', a.active,
                        'is_required', a.is_required
                    ) ORDER BY a.sort_order, a.id
                ) FILTER (WHERE a.id IS NOT NULL),
                '[]'
            ) as aspects
        FROM portal_rooms r
        LEFT JOIN portal_aspects a ON a.room_id = r.id {aspect_condition}
        {condition}
        GROUP BY r.id, r.name, r.description, r.category, r.sort_order, r.active, r.is_required
        ORDER BY r.sort_order, r.id
    """
    
    with get_cursor() as cur:
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def list_school_rooms(school_id: int, include_all_aspects: bool = False) -> List[Dict[str, Any]]:
    """
    Fetch rooms configured for a specific school with aspects.
    - If include_all_aspects=True: return all aspects with is_selected flag.
    - If False: return only required or selected aspects (enabled for scoring).
    """
    if include_all_aspects:
        query = """
            SELECT 
                sr.id as school_room_id,
                sr.quantity,
                sr.notes,
                r.id as room_id,
                r.name as room_name,
                r.category,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', a.id,
                            'name', a.name,
                            'description', a.description,
                            'is_required', a.is_required,
                            'is_selected', (a.is_required OR psra.aspect_id IS NOT NULL)
                        ) ORDER BY a.sort_order, a.id
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'
                ) as aspects
            FROM portal_school_rooms sr
            JOIN portal_rooms r ON r.id = sr.room_id
            LEFT JOIN portal_aspects a ON a.room_id = r.id AND a.active = TRUE
            LEFT JOIN portal_school_room_aspects psra ON psra.school_room_id = sr.id AND psra.aspect_id = a.id
            WHERE sr.school_id = %s AND r.active = TRUE
            GROUP BY sr.id, sr.quantity, sr.notes, r.id, r.name, r.category
            ORDER BY r.sort_order, r.id
        """
    else:
        query = """
            SELECT 
                sr.id as school_room_id,
                sr.quantity,
                sr.notes,
                r.id as room_id,
                r.name as room_name,
                r.category,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', a.id,
                            'name', a.name,
                            'description', a.description,
                            'is_required', a.is_required
                        ) ORDER BY a.sort_order, a.id
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'
                ) as aspects
            FROM portal_school_rooms sr
            JOIN portal_rooms r ON r.id = sr.room_id
            LEFT JOIN portal_aspects a 
                ON a.room_id = r.id 
                AND a.active = TRUE
                AND (a.is_required = TRUE OR EXISTS (
                    SELECT 1 FROM portal_school_room_aspects psra 
                    WHERE psra.school_room_id = sr.id AND psra.aspect_id = a.id
                ))
            WHERE sr.school_id = %s AND r.active = TRUE
            GROUP BY sr.id, sr.quantity, sr.notes, r.id, r.name, r.category
            ORDER BY r.sort_order, r.id
        """
    
    with get_cursor() as cur:
        cur.execute(query, (school_id,))
        return [dict(row) for row in cur.fetchall()]


def create_assessment(
    school_id: int,
    staff_id: int,
    period_id: Optional[int] = None,
    creator_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new draft assessment for the given period (defaults to active)."""
    if period_id is None:
        period = get_active_period()
        period_id = period["id"] if period else None

    with get_cursor(commit=True) as cur:
        # Avoid duplicate drafts for the same staff/school/period
        cur.execute(
            """
            SELECT id, school_id, staff_id, status, created_at, period_id, score_scale_max
            FROM portal_assessments
            WHERE school_id = %s
              AND staff_id = %s
              AND status = 'draft'
              AND (
                    (period_id IS NULL AND %s IS NULL)
                    OR period_id = %s
                  )
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (school_id, staff_id, period_id, period_id),
        )
        existing = cur.fetchone()
        if existing:
            data = dict(existing)
            data["_is_new"] = False
            return data

        cur.execute(
            """
            INSERT INTO portal_assessments (school_id, staff_id, period_id, status, score_scale_max)
            VALUES (%s, %s, %s, 'draft', %s)
            RETURNING id, school_id, staff_id, status, created_at, period_id, score_scale_max
            """,
            (school_id, staff_id, period_id, PORTAL_NEW_SCORE_SCALE_MAX),
        )
        # creator_email retained for backward compatibility (not stored yet)
        data = dict(cur.fetchone())
        data["_is_new"] = True
        return data


def delete_assessment_scores(assessment_id: int) -> int:
    """Delete all scores for an assessment (used to clear auto-filled defaults)."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM portal_assessment_scores WHERE assessment_id = %s",
            (assessment_id,),
        )
        return cur.rowcount


def get_latest_final_assessment_for_period(
    school_id: int,
    staff_id: int,
    period_id: Optional[int],
) -> Optional[Dict[str, Any]]:
    """Get the latest submitted/verified assessment for a staff & school in a given period."""
    query = """
        SELECT id, status, period_id, created_at
        FROM portal_assessments
        WHERE school_id = %s
          AND staff_id = %s
          AND status IN ('submitted', 'verified')
          AND (
                (period_id IS NULL AND %s IS NULL)
                OR period_id = %s
              )
        ORDER BY created_at DESC
        LIMIT 1
    """
    with get_cursor() as cur:
        cur.execute(query, (school_id, staff_id, period_id, period_id))
        row = cur.fetchone()
        return dict(row) if row else None


def get_assessment_by_id(assessment_id: int) -> Optional[Dict[str, Any]]:
    """Get assessment details with school info."""
    query = """
        SELECT 
            a.id, a.school_id, a.staff_id, a.assessment_date,
            a.status, a.total_score, a.notes, a.submitted_at,
            a.created_at, a.updated_at,
            a.period_id, a.score_scale_max,
            CASE
                WHEN a.total_score IS NULL THEN NULL
                ELSE {score_pct_expr}
            END AS score_pct,
            p.name AS period_name,
            p.start_date AS period_start_date,
            p.end_date AS period_end_date,
            s.name as school_name, s.npsn, s.jenjang,
            u.full_name as assessor_name, u.email as assessor_email
        FROM portal_assessments a
        JOIN portal_schools s ON s.id = a.school_id
        LEFT JOIN portal_assessment_periods p ON p.id = a.period_id
        LEFT JOIN dashboard_users u ON u.id = a.staff_id
        WHERE a.id = %s
    """.format(score_pct_expr=_score_pct_sql("a.total_score", "a.score_scale_max"))
    with get_cursor() as cur:
        cur.execute(query, (assessment_id,))
        row = cur.fetchone()
        return dict(row) if row else None


# ===== Reopen Requests =====

def get_latest_reopen_request(assessment_id: int) -> Optional[Dict[str, Any]]:
    query = """
        SELECT r.*, u.full_name AS staff_name, u.email AS staff_email,
               reviewer.full_name AS reviewer_name, reviewer.email AS reviewer_email
        FROM portal_assessment_reopen_requests r
        JOIN dashboard_users u ON u.id = r.staff_id
        LEFT JOIN dashboard_users reviewer ON reviewer.id = r.reviewer_id
        WHERE r.assessment_id = %s
        ORDER BY r.created_at DESC
        LIMIT 1
    """
    with get_cursor() as cur:
        cur.execute(query, (assessment_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def create_reopen_request(assessment_id: int, staff_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_assessment_reopen_requests
                (assessment_id, staff_id, reason, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING *
            """,
            (assessment_id, staff_id, reason),
        )
        return dict(cur.fetchone())


def update_reopen_request_status(
    request_id: int,
    status: str,
    reviewer_id: int,
    reviewer_note: Optional[str] = None,
) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_assessment_reopen_requests
            SET status = %s,
                reviewer_id = %s,
                reviewer_note = %s,
                reviewed_at = NOW()
            WHERE id = %s
            """,
            (status, reviewer_id, reviewer_note, request_id),
        )
        return cur.rowcount > 0


def list_reopen_requests(status: Optional[str] = None) -> List[Dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("r.status = %s")
        params.append(status)
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    query = f"""
        SELECT r.*, s.name AS school_name, s.npsn, u.full_name AS staff_name,
               reviewer.full_name AS reviewer_name
        FROM portal_assessment_reopen_requests r
        JOIN portal_assessments a ON a.id = r.assessment_id
        JOIN portal_schools s ON s.id = a.school_id
        JOIN dashboard_users u ON u.id = r.staff_id
        LEFT JOIN dashboard_users reviewer ON reviewer.id = r.reviewer_id
        {where_sql}
        ORDER BY r.created_at DESC
    """
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def fetch_admin_pending_summary() -> Dict[str, int]:
    """Return counts of pending admin confirmations for Portal."""
    query = """
        SELECT
            (SELECT COUNT(*) FROM dashboard_users WHERE account_status = 'pending') AS pending_users,
            (SELECT COUNT(*) FROM staff_assignment_requests WHERE status = 'pending') AS pending_assignment_requests,
            (SELECT COUNT(*) FROM monev_team_member_requests WHERE status = 'pending') AS pending_team_member_requests,
            (SELECT COUNT(*) FROM portal_assessment_reopen_requests WHERE status = 'pending') AS pending_reopen_requests,
            (SELECT COUNT(*) FROM daftar_tamu_transactions WHERE status = 'pending') AS pending_guestbook
    """
    with get_cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()

    if not row:
        return {
            "pending_users": 0,
            "pending_assignment_requests": 0,
            "pending_team_member_requests": 0,
            "pending_reopen_requests": 0,
            "pending_guestbook": 0,
            "total": 0,
        }

    summary = {
        "pending_users": int(row["pending_users"] or 0),
        "pending_assignment_requests": int(row["pending_assignment_requests"] or 0),
        "pending_team_member_requests": int(row["pending_team_member_requests"] or 0),
        "pending_reopen_requests": int(row["pending_reopen_requests"] or 0),
        "pending_guestbook": int(row["pending_guestbook"] or 0),
    }
    summary["total"] = (
        summary["pending_users"]
        + summary["pending_assignment_requests"]
        + summary["pending_team_member_requests"]
        + summary["pending_reopen_requests"]
        + summary["pending_guestbook"]
    )
    return summary


def fetch_admin_pending_preview(limit_per_type: int = 3) -> Dict[str, Any]:
    """Return pending summaries and preview items for admin quick actions."""
    limit = max(1, int(limit_per_type))
    summary = fetch_admin_pending_summary()
    preview: Dict[str, Any] = {
        "summary": summary,
        "users": [],
        "assignment_requests": [],
        "team_member_requests": [],
        "reopen_requests": [],
        "guestbook_transactions": [],
    }

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                u.id,
                u.full_name,
                u.email,
                u.role,
                u.created_at,
                u.whatsapp_number,
                k.name AS kecamatan_name,
                s.name AS school_name,
                s.npsn AS school_npsn,
                s.jenjang AS school_jenjang,
                sk.name AS school_kecamatan_name
            FROM dashboard_users u
            LEFT JOIN portal_kecamatan k ON u.requested_kecamatan = k.id
            LEFT JOIN portal_schools s ON u.school_id = s.id
            LEFT JOIN portal_kelurahan sl ON s.kelurahan_id = sl.id
            LEFT JOIN portal_kecamatan sk ON sl.kecamatan_id = sk.id
            WHERE u.account_status = 'pending'
            ORDER BY u.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        preview["users"] = [dict(row) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT
                sar.id,
                sar.created_at,
                sar.note,
                s.full_name AS staff_name,
                s.email AS staff_email,
                c.full_name AS coordinator_name,
                sch.name AS school_name,
                sch.npsn AS school_npsn,
                k.name AS kecamatan_name,
                p.name AS period_name
            FROM staff_assignment_requests sar
            JOIN dashboard_users s ON sar.staff_id = s.id
            JOIN dashboard_users c ON sar.coordinator_id = c.id
            JOIN portal_schools sch ON sar.school_id = sch.id
            LEFT JOIN portal_kelurahan l ON sch.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            LEFT JOIN portal_assessment_periods p ON sar.period_id = p.id
            WHERE sar.status = 'pending'
            ORDER BY sar.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        preview["assignment_requests"] = [dict(row) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT
                r.id,
                r.created_at,
                r.note,
                u.full_name AS staff_name,
                u.email AS staff_email,
                t.name AS team_name,
                t.team_type,
                k.name AS kecamatan_name,
                rb.full_name AS requested_by_name
            FROM monev_team_member_requests r
            JOIN monev_teams t ON r.team_id = t.id
            LEFT JOIN portal_kecamatan k ON t.kecamatan_id = k.id
            JOIN dashboard_users u ON r.staff_id = u.id
            JOIN dashboard_users rb ON r.requested_by = rb.id
            WHERE r.status = 'pending'
            ORDER BY r.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        preview["team_member_requests"] = [dict(row) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT
                r.id,
                r.created_at,
                r.assessment_id,
                r.reason,
                s.name AS school_name,
                s.npsn,
                u.id AS staff_id,
                u.full_name AS staff_name,
                u.email AS staff_email
            FROM portal_assessment_reopen_requests r
            JOIN portal_assessments a ON a.id = r.assessment_id
            JOIN portal_schools s ON s.id = a.school_id
            JOIN dashboard_users u ON u.id = r.staff_id
            WHERE r.status = 'pending'
            ORDER BY r.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        preview["reopen_requests"] = [dict(row) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT
                t.id,
                t.visit_at,
                t.created_at,
                t.photo_path,
                s.name AS school_name,
                s.npsn,
                s.jenjang,
                k.name AS kecamatan_name,
                l.name AS kelurahan_name,
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
            WHERE t.status = 'pending'
            ORDER BY t.visit_at DESC, t.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        preview["guestbook_transactions"] = [dict(row) for row in cur.fetchall()]

    return preview


def get_or_create_draft_assessment(school_id: int, staff_id: int) -> Dict[str, Any]:
    """Get existing draft assessment or create a new one."""
    with get_cursor(commit=True) as cur:
        # Check for existing draft
        cur.execute(
            """
            SELECT id, school_id, staff_id, assessment_date, status, total_score, notes, score_scale_max
            FROM portal_assessments
            WHERE school_id = %s AND staff_id = %s AND status = 'draft'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (school_id, staff_id),
        )
        row = cur.fetchone()
        
        if row:
            return dict(row)
        
        # Create new draft
        cur.execute(
            """
            INSERT INTO portal_assessments (school_id, staff_id, status, score_scale_max)
            VALUES (%s, %s, 'draft', %s)
            RETURNING id, school_id, staff_id, assessment_date, status, total_score, notes, score_scale_max
            """,
            (school_id, staff_id, PORTAL_NEW_SCORE_SCALE_MAX),
        )
        return dict(cur.fetchone())


def save_assessment_score(
    assessment_id: int,
    school_room_id: int,
    aspect_id: int,
    score: int,
    notes: Optional[str] = None,
) -> bool:
    """Save or update a score for an aspect."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_assessment_scores 
                (assessment_id, school_room_id, aspect_id, score, notes)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (assessment_id, school_room_id, aspect_id)
            DO UPDATE SET 
                score = EXCLUDED.score,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            RETURNING id
            """,
            (assessment_id, school_room_id, aspect_id, score, notes),
        )
        return cur.fetchone() is not None


def get_assessment_scores(assessment_id: int) -> List[Dict[str, Any]]:
    """Get all scores for an assessment."""
    query = """
        SELECT 
            s.id, s.school_room_id, s.aspect_id, s.score, s.notes,
            r.id as room_id, r.name as room_name, a.name as aspect_name
        FROM portal_assessment_scores s
        JOIN portal_school_rooms sr ON sr.id = s.school_room_id
        JOIN portal_rooms r ON r.id = sr.room_id
        JOIN portal_aspects a ON a.id = s.aspect_id
        WHERE s.assessment_id = %s
        ORDER BY r.sort_order, a.sort_order
    """
    with get_cursor() as cur:
        cur.execute(query, (assessment_id,))
        return [dict(row) for row in cur.fetchall()]


def create_period(
    name: str, 
    start_date: str, 
    end_date: str, 
    is_active: bool = False
) -> Dict[str, Any]:
    """Create a new assessment period."""
    with get_cursor(commit=True) as cur:
        if is_active:
            # Deactivate others
            cur.execute("UPDATE portal_assessment_periods SET is_active = FALSE")

        _sync_portal_assessment_periods_sequence(cur)
        cur.execute(
            """
            INSERT INTO portal_assessment_periods (name, start_date, end_date, is_active)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, start_date, end_date, is_active
            """,
            (name, start_date, end_date, is_active),
        )
        return dict(cur.fetchone())

def _ensure_monthly_periods(cur, months_ahead: int = _AUTO_PERIOD_MONTHS_AHEAD) -> None:
    """Ensure monthly periods exist from current month up to N months ahead."""
    if months_ahead < 0:
        return
    _sync_portal_assessment_periods_sequence(cur)
    today = _today_jakarta()
    start = date(today.year, today.month, 1)
    end_month_offset = start.month - 1 + months_ahead
    end_year = start.year + end_month_offset // 12
    end_month = end_month_offset % 12 + 1
    end_last_day = calendar.monthrange(end_year, end_month)[1]
    window_end = date(end_year, end_month, end_last_day)

    cur.execute(
        """
        SELECT start_date, end_date
        FROM portal_assessment_periods
        WHERE end_date >= %s AND start_date <= %s
        """,
        (start, window_end),
    )
    existing_ranges = [(row["start_date"], row["end_date"]) for row in cur.fetchall()]

    def _overlaps(month_start: date, month_end: date) -> bool:
        for range_start, range_end in existing_ranges:
            if range_start <= month_end and range_end >= month_start:
                return True
        return False

    for offset in range(months_ahead + 1):
        year = start.year + (start.month - 1 + offset) // 12
        month = (start.month - 1 + offset) % 12 + 1
        month_start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)
        if _overlaps(month_start, month_end):
            continue
        name = f"{_MONTH_NAMES_ID[month - 1]} {year}"
        cur.execute(
            """
            INSERT INTO portal_assessment_periods (name, start_date, end_date, is_active)
            VALUES (%s, %s, %s, FALSE)
            """,
            (name, month_start, month_end),
        )
        existing_ranges.append((month_start, month_end))

def _ensure_monthly_period_for_date(cur, target_date: date) -> None:
    """Ensure a monthly period exists for the month containing target_date."""
    month_start = date(target_date.year, target_date.month, 1)
    last_day = calendar.monthrange(target_date.year, target_date.month)[1]
    month_end = date(target_date.year, target_date.month, last_day)
    cur.execute(
        """
        SELECT 1
        FROM portal_assessment_periods
        WHERE start_date <= %s AND end_date >= %s
        LIMIT 1
        """,
        (month_end, month_start),
    )
    if cur.fetchone():
        return
    _sync_portal_assessment_periods_sequence(cur)
    name = f"{_MONTH_NAMES_ID[target_date.month - 1]} {target_date.year}"
    cur.execute(
        """
        INSERT INTO portal_assessment_periods (name, start_date, end_date, is_active)
        VALUES (%s, %s, %s, FALSE)
        """,
        (name, month_start, month_end),
    )

def _auto_activate_period_for_today(cur) -> Optional[Dict[str, Any]]:
    """Activate the period that contains today's date (if any)."""
    _ensure_monthly_periods(cur)
    cur.execute(
        """
        SELECT *
        FROM portal_assessment_periods
        WHERE start_date <= CURRENT_DATE
          AND end_date >= CURRENT_DATE
        ORDER BY start_date DESC, id DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        return None
    period = dict(row)
    if not period.get("is_active"):
        cur.execute(
            "UPDATE portal_assessment_periods SET is_active = FALSE WHERE id <> %s",
            (period["id"],),
        )
        cur.execute(
            "UPDATE portal_assessment_periods SET is_active = TRUE WHERE id = %s",
            (period["id"],),
        )
        period["is_active"] = True
    return period


def list_periods() -> List[Dict[str, Any]]:
    """List all assessment periods (auto-activates the current period if needed)."""
    with get_cursor(commit=True) as cur:
        _auto_activate_period_for_today(cur)
        cur.execute("SELECT * FROM portal_assessment_periods ORDER BY start_date DESC")
        return [dict(row) for row in cur.fetchall()]

def get_active_period() -> Optional[Dict[str, Any]]:
    """Get the active period, auto-activating the one that matches today's date."""
    with get_cursor(commit=True) as cur:
        today_period = _auto_activate_period_for_today(cur)
        if today_period:
            return today_period
        cur.execute("SELECT * FROM portal_assessment_periods WHERE is_active = TRUE LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None

def get_period_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get the period that contains the given date (auto-creates monthly if missing)."""
    with get_cursor(commit=True) as cur:
        _ensure_monthly_period_for_date(cur, target_date)
        cur.execute(
            """
            SELECT *
            FROM portal_assessment_periods
            WHERE start_date <= %s AND end_date >= %s
            ORDER BY start_date DESC, id DESC
            LIMIT 1
            """,
            (target_date, target_date),
        )
        row = cur.fetchone()
        return dict(row) if row else None

def get_period_by_id(period_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM portal_assessment_periods WHERE id = %s", (period_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def assign_assessment(school_id: int, staff_id: int, period_id: Optional[int] = None) -> Dict[str, Any]:
    """Admin assigns an assessment to a staff member."""
    with get_cursor(commit=True) as cur:
        if not period_id:
            active = _auto_activate_period_for_today(cur)
            if not active:
                cur.execute("SELECT id FROM portal_assessment_periods WHERE is_active = TRUE")
                row = cur.fetchone()
                period_id = row["id"] if row else None
            else:
                period_id = active["id"]

        # Avoid duplicate drafts for the same staff/school/period
        cur.execute(
            """
            SELECT id
            FROM portal_assessments
            WHERE school_id = %s
              AND staff_id = %s
              AND status = 'draft'
              AND (
                    (period_id IS NULL AND %s IS NULL)
                    OR period_id = %s
                  )
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (school_id, staff_id, period_id, period_id),
        )
        existing = cur.fetchone()
        if existing:
            return dict(existing)

        cur.execute(
            """
            INSERT INTO portal_assessments (school_id, staff_id, period_id, status, score_scale_max)
            VALUES (%s, %s, %s, 'draft', %s)
            RETURNING id
            """,
            (school_id, staff_id, period_id, PORTAL_NEW_SCORE_SCALE_MAX),
        )
        return dict(cur.fetchone())

def reopen_assessment(assessment_id: int) -> bool:
    """Reopen a submitted assessment (set to draft)."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE portal_assessments SET status = 'draft', submitted_at = NULL WHERE id = %s RETURNING id",
            (assessment_id,)
        )
        return cur.fetchone() is not None

def fetch_random_photos(
    limit: int = 6,
    period_id: Optional[int] = None,
    order: str = "random",
    staff_ids: Optional[List[int]] = None,
    restrict_to_staff: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch photos for stats gallery, with room score summary.
    
    Returns one photo per unique school+room combination.
    Score is normalized to percentage (0-100) using each assessment scale.
    """
    order = (order or "random").strip().lower()
    allowed_orders = {"random", "newest", "lowest"}
    if order not in allowed_orders:
        order = "random"
    if staff_ids is not None and len(staff_ids) == 0:
        return []
    if restrict_to_staff and not staff_ids:
        return []
    
    clauses = ["a.status = 'submitted'"]
    params: List[Any] = []
    if period_id:
        clauses.append("a.period_id = %s")
        params.append(period_id)
    if staff_ids:
        placeholders = ",".join(["%s"] * len(staff_ids))
        clauses.append(f"a.staff_id IN ({placeholders})")
        params.extend(staff_ids)
    where = "WHERE " + " AND ".join(clauses)
    
    score_pct_expr = _score_pct_sql("sc2.score", "a.score_scale_max")

    # Use subquery to get one photo per school+room combo with normalized score
    query = f"""
        SELECT * FROM (
            SELECT DISTINCT ON (s.id, r.id)
                p.photo_path, 
                s.name as school_name, 
                s.id as school_id,
                a.id as assessment_id,
                a.score_scale_max,
                r.name as room_name,
                r.id as room_id,
                p.captured_at,
                p.latitude,
                p.longitude,
                (
                    SELECT COALESCE(AVG(sc2.score), 0)::DECIMAL(5,2)
                    FROM portal_assessment_scores sc2
                    WHERE sc2.assessment_id = a.id AND sc2.school_room_id = sr.id
                ) AS room_score,
                (
                    SELECT COALESCE(AVG({score_pct_expr}), 0)::DECIMAL(5,2)
                    FROM portal_assessment_scores sc2
                    WHERE sc2.assessment_id = a.id AND sc2.school_room_id = sr.id
                ) AS room_score_pct
            FROM portal_assessment_photos p
            JOIN portal_assessments a ON p.assessment_id = a.id
            JOIN portal_schools s ON a.school_id = s.id
            JOIN portal_school_rooms sr ON p.school_room_id = sr.id
            JOIN portal_rooms r ON sr.room_id = r.id
            {where}
            ORDER BY s.id, r.id, p.captured_at DESC NULLS LAST
        ) sub
    """
    
    order_clause = "ORDER BY RANDOM()"
    if order == "newest":
        order_clause = "ORDER BY captured_at DESC NULLS LAST, room_score_pct ASC NULLS LAST, school_name, room_name"
    elif order == "lowest":
        order_clause = "ORDER BY room_score_pct ASC NULLS LAST, captured_at DESC NULLS LAST, school_name, room_name"
    
    query += f" {order_clause} LIMIT %s"
    params.append(limit)
    
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def save_assessment_photo(
    assessment_id: int,
    school_room_id: int,
    photo_path: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    captured_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Save a photo for an assessment room (upsert per room).
    
    Uses atomic INSERT ... ON CONFLICT to handle upserts safely.
    """
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_assessment_photos 
                (assessment_id, school_room_id, photo_path, latitude, longitude, captured_at, created_at)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s, NOW()), NOW())
            ON CONFLICT (assessment_id, school_room_id)
            DO UPDATE SET 
                photo_path = EXCLUDED.photo_path,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                captured_at = EXCLUDED.captured_at,
                created_at = NOW()
            RETURNING id, assessment_id, school_room_id, photo_path, latitude, longitude, captured_at
            """,
            (assessment_id, school_room_id, photo_path, latitude, longitude, captured_at),
        )
        return dict(cur.fetchone())


def get_assessment_photos(assessment_id: int) -> List[Dict[str, Any]]:
    """Get all photos for an assessment."""
    query = """
        SELECT 
            p.id, 
            p.assessment_id, 
            p.school_room_id, 
            p.photo_path, 
            p.latitude, 
            p.longitude, 
            COALESCE(p.captured_at, p.created_at) AS captured_at,
            du.full_name AS uploader_name,
            du.email AS uploader_email
        FROM portal_assessment_photos p
        LEFT JOIN portal_assessments a ON a.id = p.assessment_id
        LEFT JOIN dashboard_users du ON du.id = a.staff_id
        WHERE p.assessment_id = %s
        ORDER BY p.captured_at DESC NULLS LAST
    """
    with get_cursor() as cur:
        cur.execute(query, (assessment_id,))
        return [dict(row) for row in cur.fetchall()]


def save_room_details(
    assessment_id: int,
    school_room_id: int,
    notes: str,
) -> Dict[str, Any]:
    """Save or update room details (notes)."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_assessment_room_details 
                (assessment_id, school_room_id, notes)
            VALUES (%s, %s, %s)
            ON CONFLICT (assessment_id, school_room_id)
            DO UPDATE SET 
                notes = EXCLUDED.notes,
                updated_at = NOW()
            RETURNING id, assessment_id, school_room_id, notes
            """,
            (assessment_id, school_room_id, notes),
        )
        return dict(cur.fetchone())


def get_assessment_room_details(assessment_id: int) -> Dict[int, str]:
    """Get room details map {school_room_id: notes}."""
    query = """
        SELECT school_room_id, notes
        FROM portal_assessment_room_details
        WHERE assessment_id = %s
    """
    with get_cursor() as cur:
        cur.execute(query, (assessment_id,))
        return {row["school_room_id"]: row["notes"] for row in cur.fetchall()}

def get_assessment_room_score_pct(assessment_id: int, school_room_id: int) -> float:
    """Return room score percentage (0-100). Missing scores count as 0."""
    query = """
        SELECT
            COUNT(a.id) AS total_aspects,
            COALESCE(SUM(COALESCE(s.score, 0)), 0) AS total_score,
            COALESCE(MAX(pa.score_scale_max), 3) AS score_scale_max
        FROM portal_school_rooms sr
        JOIN portal_rooms r ON r.id = sr.room_id
        JOIN portal_assessments pa ON pa.id = %s
        LEFT JOIN portal_aspects a
            ON a.room_id = r.id
            AND a.active = TRUE
            AND (
                a.is_required = TRUE OR EXISTS (
                    SELECT 1
                    FROM portal_school_room_aspects psra
                    WHERE psra.school_room_id = sr.id
                      AND psra.aspect_id = a.id
                )
            )
        LEFT JOIN portal_assessment_scores s
            ON s.assessment_id = %s
            AND s.school_room_id = sr.id
            AND s.aspect_id = a.id
        WHERE sr.id = %s
    """
    with get_cursor() as cur:
        cur.execute(query, (assessment_id, assessment_id, school_room_id))
        row = cur.fetchone()
        if not row:
            return 0.0
        total_aspects = row.get("total_aspects") or 0
        total_score = row.get("total_score") or 0
        score_scale_max = row.get("score_scale_max") or PORTAL_LEGACY_SCORE_SCALE_MAX
        if total_aspects <= 0:
            return 0.0
        avg = total_score / total_aspects
        return float(_normalize_score_pct(avg, score_scale_max))


def submit_assessment(assessment_id: int) -> bool:
    """Submit an assessment and calculate total score.
    
    Missing aspects are auto-filled with scale baseline:
    legacy scale=3 -> 0, new scale=5 -> 1.
    """
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT COALESCE(score_scale_max, %s) AS score_scale_max
            FROM portal_assessments
            WHERE id = %s
            """,
            (PORTAL_LEGACY_SCORE_SCALE_MAX, assessment_id),
        )
        assessment = cur.fetchone() or {}
        score_scale_max = _normalize_score_scale_max(assessment.get("score_scale_max"))
        default_score = PORTAL_NEW_SCORE_MIN if score_scale_max == PORTAL_NEW_SCORE_SCALE_MAX else PORTAL_LEGACY_SCORE_MIN

        # 1. Fill missing scores with scale-aware default
        cur.execute(
            """
            INSERT INTO portal_assessment_scores (assessment_id, school_room_id, aspect_id, score, created_at, updated_at)
            SELECT %s, sr.id, pa.id, %s, NOW(), NOW()
            FROM portal_school_rooms sr
            JOIN portal_assessments a ON a.id = %s
            JOIN portal_aspects pa ON pa.room_id = sr.room_id
            WHERE sr.school_id = a.school_id
              AND NOT EXISTS (
                  SELECT 1 
                  FROM portal_assessment_scores s 
                  WHERE s.assessment_id = %s 
                    AND s.school_room_id = sr.id 
                    AND s.aspect_id = pa.id
              )
            """,
            (assessment_id, default_score, assessment_id, assessment_id),
        )

        # 2. Calculate average score
        cur.execute(
            """
            SELECT AVG(score)::DECIMAL(5,2) as avg_score
            FROM portal_assessment_scores
            WHERE assessment_id = %s
            """,
            (assessment_id,),
        )
        row = cur.fetchone()
        avg_score = row["avg_score"] if row else 0.00
        
        # 3. Update assessment
        cur.execute(
            """
            UPDATE portal_assessments
            SET status = 'submitted',
                total_score = %s,
                submitted_at = NOW(),
                updated_at = NOW()
            WHERE id = %s AND status = 'draft'
            RETURNING id
            """,
            (avg_score, assessment_id),
        )
        return cur.fetchone() is not None


def list_staff_assessments(
    staff_id: int,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List assessments by a staff member."""
    conditions = ["a.staff_id = %s"]
    params = [staff_id]
    
    if status:
        conditions.append("a.status = %s")
        params.append(status)
    
    params.append(limit)
    where_clause = " AND ".join(conditions)
    
    query = f"""
        SELECT 
            a.id, a.school_id, a.assessment_date, a.status,
            a.total_score,
            a.score_scale_max,
            CASE
                WHEN a.total_score IS NULL THEN NULL
                ELSE {_score_pct_sql("a.total_score", "a.score_scale_max")}
            END AS score_pct,
            a.submitted_at, a.created_at,
            s.name as school_name, s.npsn, s.jenjang
        FROM portal_assessments a
        JOIN portal_schools s ON s.id = a.school_id
        WHERE {where_clause}
        ORDER BY a.created_at DESC
        LIMIT %s
    """
    
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def get_active_assessment(
    school_id: int,
    staff_id: Optional[int] = None,
    period_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Get an active draft assessment for a school (optionally filtered by period)."""
    query = """
        SELECT *
        FROM portal_assessments
        WHERE school_id = %s AND status = 'draft'
    """
    params = [school_id]
    
    if staff_id:
        query += " AND staff_id = %s"
        params.append(staff_id)

    if period_id is not None:
        query += " AND period_id = %s"
        params.append(period_id)
        
    query += " ORDER BY created_at DESC LIMIT 1"

    with get_cursor() as cur:
        cur.execute(query, params)
        return dict(row) if (row := cur.fetchone()) else None


def fetch_portal_stats(
    period_id: Optional[int] = None,
    staff_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Get aggregate statistics for portal assessments.
    
    If staff_ids is provided, restrict calculations to assessments created by those staff members.
    """
    if staff_ids is not None and len(staff_ids) == 0:
        return {
            "schools": {"total_schools": 0, "active_schools": 0},
            "assessments": {
                "total": 0,
                "drafts": 0,
                "submitted": 0,
                "avg_score": None,
                "avg_score_pct": None,
            },
        }
    
    staff_ids = staff_ids or []
    has_staff_filter = bool(staff_ids)
    
    assess_conditions = []
    assess_params: List[Any] = []
    
    if staff_ids:
        placeholders = ",".join(["%s"] * len(staff_ids))
        assess_conditions.append(f"a.staff_id IN ({placeholders})")
        assess_params.extend(staff_ids)
    
    if period_id:
        assess_conditions.append("a.period_id = %s")
        assess_params.append(period_id)
    
    where_clause = f"WHERE {' AND '.join(assess_conditions)}" if assess_conditions else ""

    with get_cursor() as cur:
        if has_staff_filter:
            # Only count schools that the filtered staff have assessed
            cur.execute(
                f"""
                SELECT 
                    COUNT(DISTINCT s.id) as total_schools,
                    COUNT(DISTINCT s.id) FILTER (WHERE s.active) as active_schools
                FROM portal_assessments a
                JOIN portal_schools s ON s.id = a.school_id
                {where_clause}
                """,
                assess_params,
            )
        else:
            cur.execute(
                """
                SELECT 
                    COUNT(*) as total_schools,
                    COUNT(*) FILTER (WHERE active) as active_schools
                FROM portal_schools
                """
            )
        schools = dict(cur.fetchone())
        
        cur.execute(
            f"""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'draft') as drafts,
                COUNT(*) FILTER (WHERE status IN ('submitted', 'verified')) as submitted,
                AVG(total_score) FILTER (WHERE status IN ('submitted', 'verified')) as avg_score,
                AVG({_score_pct_sql("a.total_score", "a.score_scale_max")})
                    FILTER (WHERE status IN ('submitted', 'verified') AND total_score IS NOT NULL) as avg_score_pct
            FROM portal_assessments a
            {where_clause}
            """,
            assess_params,
        )
        assess_stats = dict(cur.fetchone())
        
        return {
            "schools": schools,
            "assessments": assess_stats,
        }


def fetch_score_distribution(
    period_id: Optional[int] = None,
    staff_ids: Optional[List[int]] = None,
) -> List[int]:
    """Calculate score distribution (9 bins: <60, 60-65, ..., 95-100)."""
    if staff_ids is not None and len(staff_ids) == 0:
        return [0] * 9
    
    conditions = ["status IN ('submitted', 'verified')", "total_score IS NOT NULL"]
    params: List[Any] = []
    
    if period_id:
        conditions.append("period_id = %s")
        params.append(period_id)
    
    if staff_ids:
        placeholders = ",".join(["%s"] * len(staff_ids))
        conditions.append(f"staff_id IN ({placeholders})")
        params.extend(staff_ids)
        
    where_clause = "WHERE " + " AND ".join(conditions)
    query = f"SELECT total_score, score_scale_max FROM portal_assessments {where_clause}"
    
    distribution = [0] * 9  # 9 Buckets
    
    with get_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        
        for row in rows:
            score = row["total_score"]
            if score is None:
                continue
            
            score_100 = _normalize_score_pct(score, row.get("score_scale_max"))
            
            if score_100 < 60:
                idx = 0
            elif score_100 >= 95:
                idx = 8
            else:
                idx = int((score_100 - 60) // 5) + 1
            
            if 0 <= idx < 9:
                distribution[idx] += 1
            
    return distribution



def fetch_map_data(
    period_id: Optional[int] = None,
    staff_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Fetch school locations and status for the map.
    
    Returns one marker per school with:
    - Average school score (from all assessments, not per room)
    - Location from the most recent photo that has GPS coordinates
    """
    if staff_ids is not None and len(staff_ids) == 0:
        return []
    
    conditions = ["status IN ('submitted', 'verified')"]
    params: List[Any] = []
    
    if period_id:
        conditions.append("period_id = %s")
        params.append(period_id)
    
    if staff_ids:
        placeholders = ",".join(["%s"] * len(staff_ids))
        conditions.append(f"staff_id IN ({placeholders})")
        params.extend(staff_ids)
    
    filter_clause = "WHERE " + " AND ".join(conditions)
    score_pct_expr = _score_pct_sql("a2.total_score", "a2.score_scale_max")
    
    # Subquery to get most recent photo with GPS per school
    query = f"""
        WITH filtered AS (
            SELECT * FROM portal_assessments
            {filter_clause}
        )
        SELECT 
            s.id, 
            s.name, 
            s.npsn, 
            s.jenjang,
            k.name as kecamatan, 
            l.name as kelurahan,
            -- Get school average score from all assessments
            (
                SELECT AVG(a2.total_score)::DECIMAL(5,2)
                FROM filtered a2
                WHERE a2.school_id = s.id 
                  AND a2.total_score IS NOT NULL
            ) AS school_avg_score,
            (
                SELECT AVG({score_pct_expr})::DECIMAL(5,2)
                FROM filtered a2
                WHERE a2.school_id = s.id 
                  AND a2.total_score IS NOT NULL
            ) AS school_avg_score_pct,
            -- Get latest status
            (
                SELECT a3.status 
                FROM filtered a3 
                WHERE a3.school_id = s.id 
                ORDER BY a3.submitted_at DESC NULLS LAST
                LIMIT 1
            ) AS status,
            -- Get location from most recent photo with GPS
            (
                SELECT p.latitude 
                FROM portal_assessment_photos p
                JOIN filtered a4 ON p.assessment_id = a4.id
                WHERE a4.school_id = s.id 
                  AND p.latitude IS NOT NULL
                ORDER BY p.captured_at DESC NULLS LAST
                LIMIT 1
            ) AS latitude,
            (
                SELECT p.longitude 
                FROM portal_assessment_photos p
                JOIN filtered a5 ON p.assessment_id = a5.id
                WHERE a5.school_id = s.id 
                  AND p.longitude IS NOT NULL
                ORDER BY p.captured_at DESC NULLS LAST
                LIMIT 1
            ) AS longitude
        FROM portal_schools s
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        WHERE EXISTS (
            SELECT 1 FROM filtered a 
            WHERE a.school_id = s.id
        )
    """
    
    with get_cursor() as cur:
        cur.execute(query, params)
        data = []
        for row in cur.fetchall():
            item = dict(row)
            # Only include schools with valid GPS
            if not item.get("latitude") or not item.get("longitude"):
                continue
            if item.get("latitude"):
                item["latitude"] = float(item["latitude"])
            if item.get("longitude"):
                item["longitude"] = float(item["longitude"])
            if item.get("school_avg_score") is not None:
                item["total_score"] = float(item["school_avg_score"])
            else:
                item["total_score"] = None
            if item.get("school_avg_score_pct") is not None:
                item["score_pct"] = float(item["school_avg_score_pct"])
            else:
                item["score_pct"] = None
            data.append(item)
        return data


def fetch_top_schools(limit: int = 5, offset: int = 0, period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch top performing schools based on their latest assessment."""
    where = "WHERE a.status IN ('submitted', 'verified')"
    params = []
    if period_id:
        where += " AND a.period_id = %s"
        params.append(period_id)
    
    params.append(limit)
    params.append(offset)
        
    query = f"""
            SELECT * FROM (
                SELECT DISTINCT ON (a.school_id)
                    s.name,
                    s.jenjang,
                    a.total_score,
                    a.score_scale_max,
                    {_score_pct_sql("a.total_score", "a.score_scale_max")} AS score_pct,
                    a.submitted_at
                FROM portal_assessments a
                JOIN portal_schools s ON a.school_id = s.id
                {where}
                ORDER BY a.school_id, a.submitted_at DESC
            ) sub
            ORDER BY score_pct DESC NULLS LAST
            LIMIT %s OFFSET %s
            """
            
    with get_cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

def log_activity(
    user_id: Optional[int],
    action: str,
    target_type: str,
    target_id: Optional[int],
    target_name: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Log an admin activity."""
    import json
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_activity_logs 
                (user_id, action, target_type, target_id, target_name, details)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, action, target_type, target_id, target_name, json.dumps(details) if details else None),
        )

def fetch_activity_logs(
    limit: int = 50,
    target_types: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Fetch recent activity logs."""
    import json
    conditions: List[str] = []
    params: List[Any] = []
    if target_types:
        conditions.append("l.target_type = ANY(%s)")
        params.append(list(target_types))
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT 
            l.id, l.user_id, l.action, l.target_type, l.target_id, l.target_name, 
            l.details, l.created_at,
            u.full_name as user_name, u.email as user_email,
            r.name AS room_name_fallback
        FROM portal_activity_logs l
        LEFT JOIN dashboard_users u ON l.user_id = u.id
        LEFT JOIN portal_aspects pa ON l.target_type = 'ASPECT' AND l.target_id = pa.id
        LEFT JOIN portal_rooms r ON pa.room_id = r.id
        {where_clause}
        ORDER BY l.created_at DESC
        LIMIT %s
    """
    with get_cursor() as cur:
        params.append(limit)
        cur.execute(query, params)
        rows = []
        for row in cur.fetchall():
            d = dict(row)
            if d.get("details"):
                try:
                    d["details"] = json.loads(d["details"])
                except Exception:
                    pass
            # Normalize details to include room name when applicable
            if isinstance(d.get("details"), dict):
                if d.get("room_name_fallback") and not d["details"].get("room_name"):
                    d["details"]["room_name"] = d["room_name_fallback"]
            elif d.get("room_name_fallback"):
                d["details"] = {"room_name": d["room_name_fallback"]}
            rows.append(d)
        return rows

def delete_school(school_id: int) -> bool:
    """Delete a school by ID."""
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM portal_schools WHERE id = %s", (school_id,))
        return cur.rowcount > 0

def fetch_bottom_schools(limit: int = 5, offset: int = 0, period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch lowest performing schools based on their latest assessment."""
    where = "WHERE a.status IN ('submitted', 'verified')"
    params = []
    if period_id:
        where += " AND a.period_id = %s"
        params.append(period_id)
    
    params.append(limit)
    params.append(offset)
        
    query = f"""
            SELECT * FROM (
                SELECT DISTINCT ON (a.school_id)
                    s.name,
                    s.jenjang,
                    a.total_score,
                    a.score_scale_max,
                    {_score_pct_sql("a.total_score", "a.score_scale_max")} AS score_pct,
                    a.submitted_at
                FROM portal_assessments a
                JOIN portal_schools s ON a.school_id = s.id
                {where}
                ORDER BY a.school_id, a.submitted_at DESC
            ) sub
            ORDER BY score_pct ASC NULLS LAST
            LIMIT %s OFFSET %s
            """
            
    with get_cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def list_recent_assessments(
    limit: int = 50,
    period_id: Optional[int] = None,
    jenjang: Optional[str] = None,
    order: str = "recent",
    staff_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """List recent submitted assessments for admin dashboard."""
    if staff_ids is not None and len(staff_ids) == 0:
        return []
    
    where = "WHERE a.status IN ('submitted', 'verified')"
    params = []
    if period_id:
        where += " AND a.period_id = %s"
        params.append(period_id)
    if jenjang:
        where += " AND s.jenjang = %s"
        params.append(jenjang)
    if staff_ids:
        placeholders = ",".join(["%s"] * len(staff_ids))
        where += f" AND a.staff_id IN ({placeholders})"
        params.extend(staff_ids)
    params.append(limit)

    order_clause = "submitted_at DESC"
    if order == "score_desc":
        order_clause = "score_pct DESC NULLS LAST"
    elif order == "score_asc":
        order_clause = "score_pct ASC NULLS LAST"
    elif order == "staff_desc":
        order_clause = "COALESCE(total_staff,0) DESC, submitted_at DESC"
    elif order == "staff_asc":
        order_clause = "COALESCE(total_staff,0) ASC, submitted_at DESC"
    elif order == "name_asc":
        order_clause = "school_name ASC"
    elif order == "name_desc":
        order_clause = "school_name DESC"
    elif order == "date_asc":
        order_clause = "submitted_at ASC NULLS LAST"
    elif order == "date_desc":
        order_clause = "submitted_at DESC NULLS LAST"

    query = f"""
        WITH latest AS (
            SELECT DISTINCT ON (a.school_id)
                a.id,
                a.school_id,
                s.name as school_name,
                s.npsn,
                s.jenjang,
                a.status,
                a.total_score,
                a.score_scale_max,
                CASE
                    WHEN a.total_score IS NULL THEN NULL
                    ELSE {_score_pct_sql("a.total_score", "a.score_scale_max")}
                END AS score_pct,
                COALESCE(staff_counts.total_staff, 0) AS total_staff,
                a.submitted_at,
                u.full_name as assessor_name
            FROM portal_assessments a
            JOIN portal_schools s ON a.school_id = s.id
            LEFT JOIN dashboard_users u ON a.staff_id = u.id
            LEFT JOIN (
                SELECT school_id, COUNT(DISTINCT staff_id) AS total_staff
                FROM portal_assessments
                WHERE status IN ('submitted', 'verified')
                GROUP BY school_id
            ) staff_counts ON staff_counts.school_id = s.id
            {where}
            ORDER BY a.school_id, a.submitted_at DESC NULLS LAST
        )
        SELECT * FROM latest
        ORDER BY {order_clause}
        LIMIT %s
        """
    with get_cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def list_staff_latest_assessments(
    period_id: Optional[int] = None,
    staff_ids: Optional[List[int]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """List staff/coordinator members with their latest submitted assessment."""
    if staff_ids is not None and len(staff_ids) == 0:
        return []

    latest_filters = ["a.staff_id = u.id", "a.status IN ('submitted', 'verified')"]
    latest_params: List[Any] = []
    if period_id:
        latest_filters.append("a.period_id = %s")
        latest_params.append(period_id)
    latest_where = " AND ".join(latest_filters)

    staff_where = "WHERE u.role IN ('staff', 'coordinator') AND u.account_status = 'approved'"
    staff_params: List[Any] = []
    if staff_ids:
        placeholders = ",".join(["%s"] * len(staff_ids))
        staff_where += f" AND u.id IN ({placeholders})"
        staff_params.extend(staff_ids)

    query = f"""
        SELECT
            u.id AS staff_id,
            u.full_name AS staff_name,
            u.jabatan,
            uk.name AS placement_kecamatan_name,
            visited.total_visited_schools,
            latest.assessment_id AS last_assessment_id,
            latest.school_name AS last_school_name,
            latest.total_score AS last_total_score,
            latest.score_scale_max AS last_score_scale_max,
            latest.score_pct AS last_score_pct,
            latest.submitted_at AS last_submitted_at,
            latest.kecamatan_name AS last_kecamatan_name
        FROM dashboard_users u
        LEFT JOIN portal_kecamatan uk ON uk.id = u.requested_kecamatan
        LEFT JOIN LATERAL (
            SELECT COUNT(DISTINCT a.school_id) AS total_visited_schools
            FROM portal_assessments a
            WHERE {latest_where}
        ) visited ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                a.id AS assessment_id,
                s.name AS school_name,
                a.total_score,
                a.score_scale_max,
                CASE
                    WHEN a.total_score IS NULL THEN NULL
                    ELSE {_score_pct_sql("a.total_score", "a.score_scale_max")}
                END AS score_pct,
                a.submitted_at,
                k.name AS kecamatan_name
            FROM portal_assessments a
            JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            WHERE {latest_where}
            ORDER BY a.submitted_at DESC NULLS LAST, a.id DESC
            LIMIT 1
        ) latest ON TRUE
        {staff_where}
        ORDER BY latest.submitted_at DESC NULLS LAST, u.full_name ASC
        LIMIT %s
    """
    params = [*latest_params, *staff_params, limit]

    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def fetch_school_avg_scores(
    period_id: Optional[int] = None,
    staff_ids: Optional[List[int]] = None,
) -> Dict[int, float]:
    """Return map {school_id: avg_score_pct} for submitted assessments."""
    if staff_ids is not None and len(staff_ids) == 0:
        return {}
    
    params: List[Any] = []
    where_clauses = ["status IN ('submitted', 'verified')"]
    if period_id:
        where_clauses.append("period_id = %s")
        params.append(period_id)
    if staff_ids:
        placeholders = ",".join(["%s"] * len(staff_ids))
        where_clauses.append(f"staff_id IN ({placeholders})")
        params.extend(staff_ids)
    where = "WHERE " + " AND ".join(where_clauses)
    
    query = f"""
        SELECT school_id,
               AVG({_score_pct_sql("total_score", "score_scale_max")})::DECIMAL(5,2) as avg_score_pct
        FROM portal_assessments
        {where}
        GROUP BY school_id
    """
    with get_cursor() as cur:
        cur.execute(query, params)
        return {
            row["school_id"]: float(row["avg_score_pct"]) if row["avg_score_pct"] is not None else 0.0
            for row in cur.fetchall()
        }

def delete_assessment(assessment_id: int) -> bool:
    """Delete an assessment and cascaded children."""
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM portal_assessments WHERE id = %s RETURNING id", (assessment_id,))
        return cur.fetchone() is not None

def delete_photo(photo_id: int, assessment_id: int, school_room_id: int) -> bool:
    """Delete a photo by id with safety checks."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM portal_assessment_photos 
            WHERE id = %s AND assessment_id = %s AND school_room_id = %s
            RETURNING id
            """,
            (photo_id, assessment_id, school_room_id),
        )
        return cur.fetchone() is not None


def fetch_related_photos(
    school_id: int,
    room_id: int,
    limit: int = 10,
    staff_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Fetch other photos from the same school and room type for comparison."""
    if staff_ids is not None and len(staff_ids) == 0:
        return []
    
    conditions = [
        "a.status IN ('submitted', 'verified')",
        "s.id = %s",
        "r.id = %s",
    ]
    params: List[Any] = [school_id, room_id]
    
    if staff_ids:
        placeholders = ",".join(["%s"] * len(staff_ids))
        conditions.append(f"a.staff_id IN ({placeholders})")
        params.extend(staff_ids)
    
    where_clause = " AND ".join(conditions)
    room_score_pct_expr = _score_pct_sql("sc.score", "a.score_scale_max")
    
    query = f"""
        SELECT 
            p.photo_path, 
            s.name as school_name, 
            s.id as school_id,
            r.name as room_name,
            r.id as room_id,
            p.captured_at,
            p.latitude,
            p.longitude,
            u.full_name AS uploader_name,
            a.id AS assessment_id,
            a.score_scale_max,
            COALESCE(AVG(sc.score), 0)::DECIMAL(5,2) AS room_score,
            COALESCE(AVG({room_score_pct_expr}), 0)::DECIMAL(5,2) AS room_score_pct
        FROM portal_assessment_photos p
        JOIN portal_assessments a ON p.assessment_id = a.id
        LEFT JOIN dashboard_users u ON a.staff_id = u.id
        JOIN portal_schools s ON a.school_id = s.id
        JOIN portal_school_rooms sr ON p.school_room_id = sr.id
        JOIN portal_rooms r ON sr.room_id = r.id
        LEFT JOIN portal_assessment_scores sc 
            ON sc.assessment_id = p.assessment_id 
           AND sc.school_room_id = p.school_room_id
        WHERE {where_clause}
        GROUP BY
            p.photo_path,
            s.name,
            s.id,
            r.name,
            r.id,
            p.captured_at,
            p.latitude,
            p.longitude,
            u.full_name,
            a.id,
            a.score_scale_max
        ORDER BY p.captured_at DESC NULLS LAST
        LIMIT %s
    """
    params.append(limit)
    
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


# ===== Admin/Setup Queries =====

def create_room(
    name: str,
    description: Optional[str] = None,
    category: str = "umum",
    sort_order: int = 0,
    is_required: bool = True,
) -> Dict[str, Any]:
    """Create a new room type."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_rooms (name, description, category, sort_order, is_required)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, description, category, sort_order, active, is_required
            """,
            (name, description, category, sort_order, is_required),
        )
        return dict(cur.fetchone())


def create_aspect(
    room_id: int,
    name: str,
    description: Optional[str] = None,
    sort_order: int = 0,
    is_required: bool = True,
) -> Dict[str, Any]:
    """Create a new aspect for a room."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_aspects (room_id, name, description, sort_order, is_required)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, room_id, name, description, sort_order, active, is_required
            """,
            (room_id, name, description, sort_order, is_required),
        )
        return dict(cur.fetchone())


def get_room_by_id(room_id: int) -> Optional[Dict[str, Any]]:
    """Get a single room by ID."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, description, category, sort_order, active, is_required FROM portal_rooms WHERE id = %s",
            (room_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_room(
    room_id: int,
    name: str,
    description: Optional[str] = None,
    category: str = "umum",
    sort_order: int = 0,
    active: bool = True,
    is_required: bool = False,
) -> Optional[Dict[str, Any]]:
    """Update an existing room."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_rooms 
            SET name = %s, description = %s, category = %s, sort_order = %s, active = %s, is_required = %s
            WHERE id = %s
            RETURNING id, name, description, category, sort_order, active, is_required
            """,
            (name, description, category, sort_order, active, is_required, room_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def delete_room(room_id: int) -> bool:
    """Delete a room. Returns True if deleted."""
    with get_cursor(commit=True) as cur:
        # Check if room is used in any assessments
        cur.execute(
            """
            SELECT COUNT(*) as cnt FROM portal_assessment_scores sc
            JOIN portal_school_rooms sr ON sc.school_room_id = sr.id
            WHERE sr.room_id = %s
            """,
            (room_id,),
        )
        if cur.fetchone()["cnt"] > 0:
            # Soft delete - just deactivate
            cur.execute(
                "UPDATE portal_rooms SET active = FALSE WHERE id = %s RETURNING id",
                (room_id,),
            )
        else:
            # Hard delete - no assessments reference this room
            cur.execute(
                "DELETE FROM portal_rooms WHERE id = %s RETURNING id",
                (room_id,),
            )
        return cur.fetchone() is not None


def get_aspect_by_id(aspect_id: int) -> Optional[Dict[str, Any]]:
    """Get a single aspect by ID."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.room_id, a.name, a.description, a.sort_order, a.active, a.is_required, r.name as room_name
            FROM portal_aspects a
            JOIN portal_rooms r ON a.room_id = r.id
            WHERE a.id = %s
            """,
            (aspect_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_aspect(
    aspect_id: int,
    name: str,
    description: Optional[str] = None,
    sort_order: int = 0,
    active: bool = True,
    is_required: bool = True,
) -> Optional[Dict[str, Any]]:
    """Update an existing aspect."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_aspects 
            SET name = %s, description = %s, sort_order = %s, active = %s, is_required = %s
            WHERE id = %s
            RETURNING id, room_id, name, description, sort_order, active, is_required
            """,
            (name, description, sort_order, active, is_required, aspect_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def delete_aspect(aspect_id: int) -> bool:
    """Delete an aspect. Returns True if deleted."""
    with get_cursor(commit=True) as cur:
        # Check if aspect is used in any assessments
        cur.execute(
            "SELECT COUNT(*) as cnt FROM portal_assessment_scores WHERE aspect_id = %s",
            (aspect_id,),
        )
        if cur.fetchone()["cnt"] > 0:
            # Soft delete - just deactivate
            cur.execute(
                "UPDATE portal_aspects SET active = FALSE WHERE id = %s RETURNING id",
                (aspect_id,),
            )
        else:
            # Hard delete
            cur.execute(
                "DELETE FROM portal_aspects WHERE id = %s RETURNING id",
                (aspect_id,),
            )
        return cur.fetchone() is not None


def get_school_by_npsn(npsn: str) -> Optional[Dict[str, Any]]:
    """Get a school by its NPSN (exact match)."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM portal_schools WHERE npsn = %s
            """,
            (npsn,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

def create_school(
    npsn: str,
    name: str,
    jenjang: str = "SD",
    alamat: Optional[str] = None,
    kelurahan_id: Optional[int] = None,
    status: str = "NEGERI",
) -> Dict[str, Any]:
    """Create a new school record."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (npsn) DO UPDATE SET
                name = EXCLUDED.name,
                jenjang = EXCLUDED.jenjang,
                alamat = EXCLUDED.alamat,
                kelurahan_id = EXCLUDED.kelurahan_id,
                status = EXCLUDED.status,
                updated_at = NOW()
            RETURNING id, npsn, name, jenjang, alamat, kelurahan_id, status
            """,
            (npsn, name, jenjang, alamat, kelurahan_id, status),
        )
        return dict(cur.fetchone())


def update_school_rooms(
    school_id: int,
    room_ids: List[int],
    aspect_map: Optional[Dict[int, List[int]]] = None,
) -> int:
    """
    Update the rooms and enabled aspects for a school.
    - room_ids: list of portal_room IDs to enable
    - aspect_map: mapping room_id -> list of aspect IDs selected (optional aspects)
    Required aspects are auto-enabled.
    """
    aspect_map = aspect_map or {}
    with get_cursor(commit=True) as cur:
        # Deduplicate while preserving order
        deduped_room_ids = list(dict.fromkeys(room_ids))

        # Fetch existing school rooms to avoid full delete (prevents wiping drafts)
        cur.execute(
            """
            SELECT id, room_id
            FROM portal_school_rooms
            WHERE school_id = %s
            """,
            (school_id,),
        )
        existing_rows = cur.fetchall()
        existing_map: Dict[int, int] = {row["room_id"]: row["id"] for row in existing_rows}

        selected_set = set(deduped_room_ids)
        existing_set = set(existing_map.keys())

        # Remove rooms that are no longer selected
        removed_room_ids = [rid for rid in existing_set if rid not in selected_set]
        if removed_room_ids:
            cur.execute(
                """
                DELETE FROM portal_school_rooms
                WHERE school_id = %s AND room_id = ANY(%s)
                """,
                (school_id, removed_room_ids),
            )

        # Add rooms and collect mapping to school_room_id
        room_map: Dict[int, int] = {}
        for rid in deduped_room_ids:
            existing_sr_id = existing_map.get(rid)
            if existing_sr_id:
                room_map[rid] = existing_sr_id
                continue

            cur.execute(
                """
                INSERT INTO portal_school_rooms (school_id, room_id)
                VALUES (%s, %s)
                RETURNING id
                """,
                (school_id, rid),
            )
            sr_id = cur.fetchone()[0]
            room_map[rid] = sr_id

        if room_map:
            # Reset aspect selections for the selected rooms only
            selected_school_room_ids = list(room_map.values())
            cur.execute(
                """
                DELETE FROM portal_school_room_aspects
                WHERE school_room_id = ANY(%s)
                """,
                (selected_school_room_ids,),
            )

            # Required aspects per room
            cur.execute(
                """
                SELECT id, room_id
                FROM portal_aspects
                WHERE room_id = ANY(%s) AND is_required = TRUE
                """,
                ([rid for rid in room_map.keys()],),
            )
            required_by_room: Dict[int, List[int]] = {}
            for row in cur.fetchall():
                required_by_room.setdefault(row["room_id"], []).append(row["id"])

            aspect_values: List[tuple[int, int]] = []
            for room_id, sr_id in room_map.items():
                selected: set[int] = set(required_by_room.get(room_id, []))
                selected.update(aspect_map.get(room_id, []) or [])
                for aid in selected:
                    aspect_values.append((sr_id, aid))

            if aspect_values:
                from psycopg2.extras import execute_values
                execute_values(
                    cur,
                    """
                    INSERT INTO portal_school_room_aspects (school_room_id, aspect_id)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                    """,
                    aspect_values,
                )

        return len(deduped_room_ids)


def list_all_staff() -> List[Dict[str, Any]]:
    """List all staff users."""
    with get_cursor() as cur:
        cur.execute("SELECT id, full_name, email FROM dashboard_users WHERE role = 'staff' ORDER BY full_name")
        return [dict(row) for row in cur.fetchall()]


def list_kecamatan() -> List[Dict[str, Any]]:
    """List all kecamatan for dropdown selection."""
    with get_cursor() as cur:
        cur.execute("SELECT id, name, code FROM portal_kecamatan ORDER BY name")
        return [dict(row) for row in cur.fetchall()]


# ===== Portal Kontak Wilayah =====

def list_portal_kontak() -> List[Dict[str, Any]]:
    """List kontak penanggung jawab per wilayah."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   wilayah,
                   nama,
                   kontak,
                   kontak_1_active,
                   nama_2,
                   kontak_2,
                   kontak_2_active
            FROM portal_kontak
            ORDER BY wilayah ASC, id ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def get_portal_kontak_by_wilayah(wilayah: str) -> Optional[Dict[str, Any]]:
    """Fetch kontak wilayah by area (wilayah), latest first."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   wilayah,
                   nama,
                   kontak,
                   kontak_1_active,
                   nama_2,
                   kontak_2,
                   kontak_2_active
            FROM portal_kontak
            WHERE lower(btrim(wilayah)) = lower(btrim(%s))
            ORDER BY id DESC
            LIMIT 1
            """,
            (wilayah,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def create_portal_kontak(
    wilayah: str,
    nama_1: str,
    kontak_1: str,
    nama_2: str,
    kontak_2: str,
    kontak_1_active: bool = True,
    kontak_2_active: bool = True,
) -> Optional[int]:
    """Create kontak wilayah and return new id."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_kontak (
                wilayah,
                nama,
                kontak,
                kontak_1_active,
                nama_2,
                kontak_2,
                kontak_2_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (wilayah, nama_1, kontak_1, kontak_1_active, nama_2, kontak_2, kontak_2_active),
        )
        row = cur.fetchone()
        return int(row["id"]) if row else None


def update_portal_kontak(
    kontak_id: int,
    wilayah: str,
    nama_1: str,
    kontak_1: str,
    nama_2: str,
    kontak_2: str,
    kontak_1_active: bool = True,
    kontak_2_active: bool = True,
) -> bool:
    """Update kontak wilayah."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_kontak
            SET wilayah = %s,
                nama = %s,
                kontak = %s,
                kontak_1_active = %s,
                nama_2 = %s,
                kontak_2 = %s,
                kontak_2_active = %s
            WHERE id = %s
            """,
            (
                wilayah,
                nama_1,
                kontak_1,
                kontak_1_active,
                nama_2,
                kontak_2,
                kontak_2_active,
                kontak_id,
            ),
        )
        return cur.rowcount > 0


def update_portal_kontak_status(kontak_id: int, contact_index: int, is_active: bool) -> bool:
    """Update status aktif/inaktif untuk kontak tertentu."""
    column_map = {1: "kontak_1_active", 2: "kontak_2_active"}
    column = column_map.get(contact_index)
    if not column:
        return False
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE portal_kontak SET {column} = %s WHERE id = %s",
            (is_active, kontak_id),
        )
        return cur.rowcount > 0


def delete_portal_kontak(kontak_id: int) -> bool:
    """Delete kontak wilayah."""
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM portal_kontak WHERE id = %s", (kontak_id,))
        return cur.rowcount > 0


def list_kelurahan(kecamatan_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List kelurahan, optionally filtered by kecamatan."""
    with get_cursor() as cur:
        if kecamatan_id:
            cur.execute(
                "SELECT id, kecamatan_id, name FROM portal_kelurahan WHERE kecamatan_id = %s ORDER BY name",
                (kecamatan_id,)
            )
        else:
            cur.execute(
                """
                SELECT l.id, l.kecamatan_id, l.name, k.name as kecamatan_name
                FROM portal_kelurahan l
                JOIN portal_kecamatan k ON l.kecamatan_id = k.id
                ORDER BY k.name, l.name
                """
            )
        return [dict(row) for row in cur.fetchall()]


def search_schools_by_npsn(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search schools by NPSN or name for autocomplete."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.id, s.npsn, s.name, s.jenjang, s.status,
                   l.name as kelurahan_name, k.name as kecamatan_name
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            WHERE s.active = TRUE AND (s.npsn LIKE %s OR s.name ILIKE %s)
            ORDER BY 
                CASE WHEN s.npsn LIKE %s THEN 0 ELSE 1 END,
                s.npsn
            LIMIT %s
            """,
            (f"{query}%", f"%{query}%", f"{query}%", limit),
        )
        return [dict(row) for row in cur.fetchall()]


def get_school_by_npsn(npsn: str) -> Optional[Dict[str, Any]]:
    """Get a single school by NPSN."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.id, s.npsn, s.name, s.jenjang, s.status,
                   l.name as kelurahan_name, k.name as kecamatan_name
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            WHERE s.npsn = %s AND s.active = TRUE
            """,
            (npsn,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

def get_portal_schools_paginated(
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    jenjang: Optional[str] = None,
    active_only: bool = True,
) -> Dict[str, Any]:
    """Fetch paginated schools."""
    conditions = []
    params = []
    
    if active_only:
        conditions.append("s.active = TRUE")
    
    if jenjang:
        conditions.append("s.jenjang = %s")
        params.append(jenjang)
    
    if search:
        conditions.append("(s.name ILIKE %s OR s.npsn ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    # 1. Get total count
    count_query = f"""
        SELECT COUNT(*) as total
        FROM portal_schools s
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        {where_clause}
    """
    
    items = []
    total = 0
    pages = 0
    
    with get_cursor() as cur:
        cur.execute(count_query, params)
        total = cur.fetchone()["total"]
        
        import math
        pages = math.ceil(total / per_page) if per_page > 0 else 1
        
        if page > pages and pages > 0:
            page = pages
        if page < 1:
            page = 1
            
        offset = (page - 1) * per_page
        
        # 2. Get items
        query = f"""
            SELECT 
                s.id, s.npsn, s.name, s.jenjang, s.alamat, s.status,
                s.kelurahan_id, s.user_id, s.active, s.created_at,
                l.name as kelurahan_name,
                k.name as kecamatan_name
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            {where_clause}
            ORDER BY k.name, l.name, s.jenjang, s.name
            LIMIT %s OFFSET %s
        """
        
        # Add LIMIT/OFFSET params
        query_params = params + [per_page, offset]
        
        cur.execute(query, query_params)
        items = [dict(row) for row in cur.fetchall()]
        
    return {
        "items": items,
        "total": total,
        "pages": pages,
        "current_page": page, 
        "per_page": per_page
    }

def fetch_export_data(period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch all assessment data for Excel export."""
    where_clause = "WHERE a.status IN ('submitted', 'verified')"
    params = []
    
    if period_id:
        where_clause += " AND a.period_id = %s"
        params.append(period_id)
        
    query = f"""
        SELECT 
            a.submitted_at::DATE as tanggal,
            s.name as sekolah,
            s.npsn,
            s.jenjang,
            k.name as kecamatan,
            l.name as kelurahan,
            r.name as ruangan,
            asp.name as aspek,
            sc.score as nilai,
            sc.notes as catatan,
            u.full_name as penilai
        FROM portal_assessment_scores sc
        JOIN portal_assessments a ON sc.assessment_id = a.id
        JOIN portal_schools s ON a.school_id = s.id
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        JOIN portal_school_rooms sr ON sc.school_room_id = sr.id
        JOIN portal_rooms r ON sr.room_id = r.id
        JOIN portal_aspects asp ON sc.aspect_id = asp.id
        LEFT JOIN dashboard_users u ON a.staff_id = u.id
        {where_clause}
        ORDER BY s.name, r.name, asp.sort_order
    """
    
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def list_kelurahan_by_urgency(period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List kelurahan sorted by urgency (lowest average school score first).
    
    Returns kelurahan with:
    - Average score percentage of all schools in that kelurahan
    - Count of schools with low scores (<60)
    - Order by urgency (lowest score first)
    """
    params: List[Any] = []
    period_cond = ""
    if period_id:
        period_cond = "AND a.period_id = %s"
        params.append(period_id)
    
    query = f"""
        WITH school_scores AS (
            SELECT
                s.id AS school_id,
                s.kelurahan_id,
                AVG({_score_pct_sql("a.total_score", "a.score_scale_max")})::DECIMAL(5,2) AS school_avg_pct
            FROM portal_schools s
            JOIN portal_assessments a ON a.school_id = s.id
            WHERE s.active = TRUE
              AND a.status IN ('submitted', 'verified')
              AND a.total_score IS NOT NULL
              {period_cond}
            GROUP BY s.id, s.kelurahan_id
        )
        SELECT 
            l.id,
            l.name,
            k.name as kecamatan_name,
            k.id as kecamatan_id,
            COUNT(ss.school_id) as school_count,
            COALESCE(AVG(ss.school_avg_pct), 0)::DECIMAL(5,2) as avg_score_pct,
            COUNT(ss.school_id) FILTER (WHERE ss.school_avg_pct < 60) as low_score_count
        FROM portal_kelurahan l
        JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        LEFT JOIN school_scores ss ON ss.kelurahan_id = l.id
        GROUP BY l.id, l.name, k.name, k.id
        HAVING COUNT(ss.school_id) > 0
        ORDER BY avg_score_pct ASC NULLS LAST, low_score_count DESC
    """
    
    with get_cursor() as cur:
        cur.execute(query, params)
        results = []
        for row in cur.fetchall():
            item = dict(row)
            item["avg_score_pct"] = round(float(item.get("avg_score_pct") or 0), 1)
            results.append(item)
        return results


def fetch_schools_for_sidak(
    kelurahan_id: int,
    max_score_pct: float = 60.0,
    period_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch schools with low scores and GPS in specific kelurahan for sidak planning."""
    # Build period filter inline to avoid param count issues
    period_cond = ""
    if period_id:
        period_cond = f"AND a.period_id = {int(period_id)}"
    
    query = f"""
        SELECT 
            s.id,
            s.name,
            s.npsn,
            s.jenjang,
            l.name as kelurahan_name,
            k.name as kecamatan_name,
            (SELECT AVG({_score_pct_sql("a.total_score", "a.score_scale_max")})::DECIMAL(5,2)
             FROM portal_assessments a
             WHERE a.school_id = s.id 
               AND a.status IN ('submitted', 'verified')
               AND a.total_score IS NOT NULL
               {period_cond}) as avg_score_pct,
            (SELECT p.latitude
             FROM portal_assessment_photos p
             JOIN portal_assessments a ON p.assessment_id = a.id
             WHERE a.school_id = s.id AND p.latitude IS NOT NULL
             ORDER BY p.captured_at DESC NULLS LAST
             LIMIT 1) as latitude,
            (SELECT p.longitude
             FROM portal_assessment_photos p
             JOIN portal_assessments a ON p.assessment_id = a.id
             WHERE a.school_id = s.id AND p.longitude IS NOT NULL
             ORDER BY p.captured_at DESC NULLS LAST
             LIMIT 1) as longitude,
            (SELECT r.name
             FROM portal_assessment_scores sc
             JOIN portal_school_rooms sr ON sc.school_room_id = sr.id
             JOIN portal_rooms r ON sr.room_id = r.id
             JOIN portal_assessments a ON sc.assessment_id = a.id
             WHERE a.school_id = s.id AND a.status IN ('submitted', 'verified')
               {period_cond}
             GROUP BY r.id, r.name
             ORDER BY AVG({_score_pct_sql("sc.score", "a.score_scale_max")}) ASC
             LIMIT 1) as worst_room
        FROM portal_schools s
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        WHERE s.kelurahan_id = %s
          AND s.active = TRUE
          AND EXISTS (
              SELECT 1 FROM portal_assessments a
              WHERE a.school_id = s.id
                AND a.status IN ('submitted', 'verified')
                {period_cond}
          )
        ORDER BY avg_score_pct ASC NULLS LAST
    """
    
    with get_cursor() as cur:
        cur.execute(query, (kelurahan_id,))
        results = []
        for row in cur.fetchall():
            item = dict(row)
            item["score_pct"] = round(float(item.get("avg_score_pct") or 0), 1)
            if item.get("latitude"):
                item["latitude"] = float(item["latitude"])
            if item.get("longitude"):
                item["longitude"] = float(item["longitude"])
            item["is_priority"] = item["score_pct"] < max_score_pct
            results.append(item)
        return results


def fetch_kecamatan_avg_scores(
    period_id: Optional[int] = None,
    staff_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Fetch average assessment scores grouped by kecamatan (0-100 scale)."""
    if staff_ids is not None and len(staff_ids) == 0:
        return []
    
    conditions = ["a.status IN ('submitted', 'verified')"]
    params: List[Any] = []
    if period_id:
        conditions.append("a.period_id = %s")
        params.append(period_id)
    if staff_ids:
        placeholders = ",".join(["%s"] * len(staff_ids))
        conditions.append(f"a.staff_id IN ({placeholders})")
        params.extend(staff_ids)
    
    where = "WHERE " + " AND ".join(conditions)
    
    query = f"""
        SELECT 
            k.name,
            AVG(a.total_score) as avg_score_raw,
            AVG({_score_pct_sql("a.total_score", "a.score_scale_max")})::DECIMAL(5,1) as avg_score_pct,
            COUNT(a.id) as assessment_count
        FROM portal_assessments a
        JOIN portal_schools s ON a.school_id = s.id
        JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        {where}
        GROUP BY k.id, k.name
        ORDER BY avg_score_pct DESC
    """
    
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]



# ============================================
# Kecamatan Access Control Functions
# ============================================

def get_user_kecamatan_ids(user_id: int) -> List[int]:
    """Get list of kecamatan IDs assigned to a user (admin)."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT kecamatan_id FROM user_kecamatan WHERE user_id = %s ORDER BY kecamatan_id",
            (user_id,)
        )
        return [row["kecamatan_id"] for row in cur.fetchall()]


def get_user_kecamatan_details(user_id: int) -> List[Dict[str, Any]]:
    """Get detailed kecamatan information for a user."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 
                uk.id,
                uk.kecamatan_id,
                k.name as kecamatan_name,
                k.code as kecamatan_code,
                uk.assigned_at,
                u.full_name as assigned_by_name
            FROM user_kecamatan uk
            JOIN portal_kecamatan k ON uk.kecamatan_id = k.id
            LEFT JOIN dashboard_users u ON uk.assigned_by = u.id
            WHERE uk.user_id = %s
            ORDER BY k.name
            """,
            (user_id,)
        )
        return [dict(row) for row in cur.fetchall()]


def assign_user_kecamatan(
    user_id: int, 
    kecamatan_ids: List[int], 
    assigned_by: Optional[int] = None
) -> bool:
    """
    Assign kecamatans to a user (admin). Maximum 3 kecamatans allowed.
    Replaces existing assignments.
    """
    if len(kecamatan_ids) > 3:
        raise ValueError("User cannot be assigned more than 3 kecamatans")
    
    with get_cursor(commit=True) as cur:
        # Remove existing assignments
        cur.execute("DELETE FROM user_kecamatan WHERE user_id = %s", (user_id,))
        
        # Add new assignments
        for kec_id in kecamatan_ids:
            cur.execute(
                """
                INSERT INTO user_kecamatan (user_id, kecamatan_id, assigned_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, kecamatan_id) DO NOTHING
                """,
                (user_id, kec_id, assigned_by)
            )
        return True


def list_schools_by_kecamatan(
    kecamatan_ids: List[int],
    search: Optional[str] = None,
    jenjang: Optional[str] = None,
    active_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    List schools filtered by kecamatan access.
    Used by admins to see only schools in their assigned kecamatans.
    """
    if not kecamatan_ids:
        return []
    
    conditions = ["l.kecamatan_id = ANY(%s)"]
    params = [kecamatan_ids]
    
    if active_only:
        conditions.append("s.active = TRUE")
    
    if jenjang:
        conditions.append("s.jenjang = %s")
        params.append(jenjang)
    
    if search:
        conditions.append("(s.name ILIKE %s OR s.npsn ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    where_clause = "WHERE " + " AND ".join(conditions)
    
    query = f"""
        SELECT 
            s.id, s.npsn, s.name, s.jenjang, s.alamat, s.status,
            s.kelurahan_id, s.user_id, s.active, s.created_at,
            l.name as kelurahan_name,
            k.id as kecamatan_id,
            k.name as kecamatan_name
        FROM portal_schools s
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        {where_clause}
        ORDER BY k.name, l.name, s.jenjang, s.name
    """
    
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def get_portal_schools_paginated(
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    jenjang: Optional[str] = None,
    kecamatan_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Paginated school listing with optional kecamatan filtering.
    If kecamatan_ids is provided, only shows schools in those kecamatans.
    """
    conditions = ["s.active = TRUE"]
    params = []
    
    if kecamatan_ids:
        conditions.append("l.kecamatan_id = ANY(%s)")
        params.append(kecamatan_ids)
    
    if jenjang:
        conditions.append("s.jenjang = %s")
        params.append(jenjang)
    
    if search:
        conditions.append("(s.name ILIKE %s OR s.npsn ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Count total
    count_query = f"""
        SELECT COUNT(*)
        FROM portal_schools s
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        {where_clause}
    """
    
    with get_cursor() as cur:
        cur.execute(count_query, params)
        total = cur.fetchone()[0]
        
        # Calculate pagination
        total_pages = (total + per_page - 1) // per_page
        offset = (page - 1) * per_page
        
        # Fetch page data
        data_query = f"""
            SELECT 
                s.id, s.npsn, s.name, s.jenjang, s.alamat, s.status,
                s.kelurahan_id, s.user_id, s.active,
                l.name as kelurahan_name,
                k.name as kecamatan_name
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            {where_clause}
            ORDER BY k.name, s.jenjang, s.name
            LIMIT %s OFFSET %s
        """
        
        cur.execute(data_query, params + [per_page, offset])
        items = [dict(row) for row in cur.fetchall()]
        
        return {
            "items": items,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            # Compatibility keys for templates expecting .pages and .current_page
            "pages": total_pages,
            "current_page": page,
        }


# ============================================
# Staff School Assignment Functions
# ============================================

def assign_staff_to_school(
    staff_id: int,
    school_id: int,
    assigned_by: int,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Admin assigns a school to a staff member."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO staff_school_assignments (staff_id, school_id, assigned_by, notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (staff_id, school_id) 
            DO UPDATE SET 
                assigned_by = EXCLUDED.assigned_by,
                assigned_at = NOW(),
                notes = EXCLUDED.notes
            RETURNING id, staff_id, school_id, assigned_by, assigned_at, notes
            """,
            (staff_id, school_id, assigned_by, notes)
        )
        return dict(cur.fetchone())


def get_staff_assigned_schools(staff_id: int, period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get all schools assigned to a staff member.

    If ``period_id`` is provided, draft/last assessment status is scoped to that period.
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 
                ssa.id as assignment_id,
                ssa.assigned_at,
                ssa.notes,
                s.id as school_id,
                s.npsn,
                s.name as school_name,
                s.jenjang,
                s.alamat,
                l.name as kelurahan_name,
                k.name as kecamatan_name,
                u.full_name as assigned_by_name,
                -- Get latest assessment status for this school by this staff
                (
                    SELECT a.status
                    FROM portal_assessments a
                    WHERE a.school_id = s.id
                      AND a.staff_id = %s
                      AND (%s IS NULL OR a.period_id = %s)
                    ORDER BY a.created_at DESC
                    LIMIT 1
                ) as last_assessment_status,
                (
                    SELECT a.id
                    FROM portal_assessments a
                    WHERE a.school_id = s.id
                      AND a.staff_id = %s
                      AND (%s IS NULL OR a.period_id = %s)
                    ORDER BY a.created_at DESC
                    LIMIT 1
                ) as last_assessment_id,
                (
                    SELECT a.id
                    FROM portal_assessments a
                    WHERE a.school_id = s.id 
                      AND a.staff_id = %s 
                      AND a.status = 'draft'
                      AND (%s IS NULL OR a.period_id = %s)
                    ORDER BY a.created_at DESC
                    LIMIT 1
                ) as draft_assessment_id,
                (
                    SELECT a.period_id
                    FROM portal_assessments a
                    WHERE a.school_id = s.id 
                      AND a.staff_id = %s 
                      AND a.status = 'draft'
                      AND (%s IS NULL OR a.period_id = %s)
                    ORDER BY a.created_at DESC
                    LIMIT 1
                ) as draft_period_id,
                (
                    SELECT p.name
                    FROM portal_assessment_periods p
                    WHERE p.id = (
                        SELECT a.period_id
                        FROM portal_assessments a
                        WHERE a.school_id = s.id 
                          AND a.staff_id = %s 
                          AND a.status = 'draft'
                          AND (%s IS NULL OR a.period_id = %s)
                        ORDER BY a.created_at DESC
                        LIMIT 1
                    )
                ) as draft_period_name,
                (
                    SELECT a.period_id
                    FROM portal_assessments a
                    WHERE a.school_id = s.id
                      AND a.staff_id = %s
                      AND (%s IS NULL OR a.period_id = %s)
                    ORDER BY a.created_at DESC
                    LIMIT 1
                ) as last_period_id,
                (
                    SELECT COUNT(*)
                    FROM portal_assessments a
                    WHERE a.school_id = s.id
                      AND a.staff_id = %s
                      AND a.status IN ('submitted', 'verified')
                ) as total_assessment_count,
                (
                    SELECT p.name
                    FROM portal_assessment_periods p
                    WHERE p.id = (
                        SELECT a.period_id
                        FROM portal_assessments a
                        WHERE a.school_id = s.id
                          AND a.staff_id = %s
                          AND (%s IS NULL OR a.period_id = %s)
                        ORDER BY a.created_at DESC
                        LIMIT 1
                    )
                ) as last_period_name
            FROM staff_school_assignments ssa
            JOIN portal_schools s ON ssa.school_id = s.id
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            LEFT JOIN dashboard_users u ON ssa.assigned_by = u.id
            WHERE ssa.staff_id = %s AND s.active = TRUE
            ORDER BY k.name, s.name
            """,
            (
                staff_id,
                period_id,
                period_id,
                staff_id,
                period_id,
                period_id,
                staff_id,
                period_id,
                period_id,
                staff_id,
                period_id,
                period_id,
                staff_id,
                period_id,
                period_id,
                staff_id,
                period_id,
                period_id,
                staff_id,
                staff_id,
                period_id,
                period_id,
                staff_id,
            )
        )
        return [dict(row) for row in cur.fetchall()]


def list_all_staff_assignments_overview() -> List[Dict[str, Any]]:
    """List all staff/coordinator school assignments with latest assessment status."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                ssa.id as assignment_id,
                ssa.assigned_at,
                ssa.notes,
                u.id as staff_id,
                u.full_name as staff_name,
                u.email as staff_email,
                u.role as staff_role,
                s.id as school_id,
                s.npsn,
                s.name as school_name,
                s.jenjang,
                k.name as kecamatan_name,
                l.name as kelurahan_name,
                last_assessment.id as last_assessment_id,
                last_assessment.status as last_assessment_status,
                last_assessment.created_at as last_assessment_created_at,
                draft_assessment.id as draft_assessment_id
            FROM staff_school_assignments ssa
            JOIN dashboard_users u ON u.id = ssa.staff_id
            JOIN portal_schools s ON ssa.school_id = s.id
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            LEFT JOIN LATERAL (
                SELECT a.id, a.status, a.created_at
                FROM portal_assessments a
                WHERE a.school_id = s.id AND a.staff_id = u.id
                ORDER BY a.created_at DESC
                LIMIT 1
            ) last_assessment ON TRUE
            LEFT JOIN LATERAL (
                SELECT a.id
                FROM portal_assessments a
                WHERE a.school_id = s.id AND a.staff_id = u.id AND a.status = 'draft'
                ORDER BY a.created_at DESC
                LIMIT 1
            ) draft_assessment ON TRUE
            WHERE u.role IN ('staff', 'coordinator')
              AND u.account_status = 'approved'
              AND s.active = TRUE
            ORDER BY ssa.assigned_at DESC NULLS LAST, u.full_name, s.name
            """
        )
        return [dict(row) for row in cur.fetchall()]


def update_staff_assignment_notes(assignment_id: int, notes: Optional[str], updated_by: int) -> Optional[Dict[str, Any]]:
    """Update notes for a staff-school assignment."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE staff_school_assignments
            SET notes = %s, assigned_by = %s
            WHERE id = %s
            RETURNING id, staff_id, school_id, notes
            """,
            (notes, updated_by, assignment_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def delete_staff_assignments_by_ids(assignment_ids: list[int]) -> int:
    """Delete staff-school assignments by ids. Returns number of deleted rows."""
    if not assignment_ids:
        return 0
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM staff_school_assignments WHERE id = ANY(%s) RETURNING id",
            (assignment_ids,),
        )
        return len(cur.fetchall())


def get_schools_assigned_to_staff_ids(staff_id: int) -> List[int]:
    """Get list of school IDs assigned to a staff member (for access control)."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT school_id FROM staff_school_assignments WHERE staff_id = %s",
            (staff_id,)
        )
        return [row["school_id"] for row in cur.fetchall()]


def remove_staff_school_assignment(staff_id: int, school_id: int) -> bool:
    """Remove a school assignment from a staff member."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM staff_school_assignments WHERE staff_id = %s AND school_id = %s RETURNING id",
            (staff_id, school_id)
        )
        return cur.fetchone() is not None


def list_all_staff_with_assignments() -> List[Dict[str, Any]]:
    """List staff/coordinator members with their assigned schools count (for admin management)."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 
                u.id,
                u.email,
                u.full_name,
                u.nip,
                u.role,
                u.jabatan,
                u.created_at,
                u.last_login_at,
                COUNT(ssa.id) as assigned_schools_count,
                ARRAY_AGG(s.name ORDER BY s.name) FILTER (WHERE s.id IS NOT NULL) as school_names
            FROM dashboard_users u
            LEFT JOIN staff_school_assignments ssa ON u.id = ssa.staff_id
            LEFT JOIN portal_schools s ON ssa.school_id = s.id AND s.active = TRUE
            WHERE u.role IN ('staff', 'coordinator') AND u.account_status = 'approved'
            GROUP BY u.id, u.email, u.full_name, u.nip, u.role, u.jabatan, u.created_at, u.last_login_at
            ORDER BY u.full_name
            """
        )
        return [dict(row) for row in cur.fetchall()]


# ============================================
# Staff Assignment Requests (Coordinator -> Admin)
# ============================================

def create_assignment_request(
    coordinator_id: int,
    staff_id: int,
    school_id: int,
    note: Optional[str] = None,
    period_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Coordinator submits assignment request."""
    if period_id is None:
        period = get_active_period()
        period_id = period["id"] if period else None

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO staff_assignment_requests (coordinator_id, staff_id, school_id, note, period_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (coordinator_id, staff_id, school_id, period_id)
            WHERE status = 'pending'
            DO UPDATE SET updated_at = NOW(), note = EXCLUDED.note, period_id = EXCLUDED.period_id
            RETURNING *
            """,
            (coordinator_id, staff_id, school_id, note, period_id),
        )
        return dict(cur.fetchone())


def list_assignment_requests(
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List assignment requests for admin review."""
    params: List[Any] = []
    where = []
    if status:
        where.append("sar.status = %s")
        params.append(status)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    query = f"""
        SELECT
            sar.*,
            c.full_name AS coordinator_name,
            s.full_name AS staff_name,
            s.email AS staff_email,
            sch.name AS school_name,
            sch.npsn AS school_npsn,
            k.name AS kecamatan_name,
            p.name AS period_name,
            r.full_name AS reviewer_name
        FROM staff_assignment_requests sar
        JOIN dashboard_users c ON sar.coordinator_id = c.id
        JOIN dashboard_users s ON sar.staff_id = s.id
        JOIN portal_schools sch ON sar.school_id = sch.id
        LEFT JOIN portal_kelurahan l ON sch.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        LEFT JOIN portal_assessment_periods p ON sar.period_id = p.id
        LEFT JOIN dashboard_users r ON sar.reviewed_by = r.id
        {where_clause}
        ORDER BY sar.created_at DESC
    """
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def update_assignment_request_status(
    request_id: int,
    status: str,
    reviewer_id: Optional[int] = None,
    reviewer_note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Approve/reject an assignment request."""
    if status not in ("approved", "rejected"):
        raise ValueError("Invalid status")
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE staff_assignment_requests
            SET status = %s,
                reviewed_by = %s,
                reviewer_note = %s,
                reviewed_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (status, reviewer_id, reviewer_note, request_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_coordinator_requests(
    coordinator_id: int,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List requests submitted by a coordinator."""
    params: List[Any] = [coordinator_id]
    where = ["sar.coordinator_id = %s"]
    if status:
        where.append("sar.status = %s")
        params.append(status)
    where_clause = "WHERE " + " AND ".join(where)
    query = f"""
        SELECT
            sar.*,
            s.full_name AS staff_name,
            s.nip AS staff_nip,
            sch.name AS school_name,
            sch.npsn AS school_npsn,
            k.name AS kecamatan_name,
            p.name AS period_name
        FROM staff_assignment_requests sar
        JOIN dashboard_users s ON sar.staff_id = s.id
        JOIN portal_schools sch ON sar.school_id = sch.id
        LEFT JOIN portal_kelurahan l ON sch.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        LEFT JOIN portal_assessment_periods p ON sar.period_id = p.id
        {where_clause}
        ORDER BY sar.created_at DESC
    """
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def set_active_period(period_id: int) -> bool:
    """Set the given period as active (others become inactive)."""
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT id FROM portal_assessment_periods WHERE id = %s", (period_id,))
        if not cur.fetchone():
            return False
        cur.execute("UPDATE portal_assessment_periods SET is_active = FALSE WHERE id <> %s", (period_id,))
        cur.execute("UPDATE portal_assessment_periods SET is_active = TRUE WHERE id = %s", (period_id,))
        return True


def update_period(
    period_id: int,
    name: str,
    start_date: str,
    end_date: str,
    is_active: bool,
) -> bool:
    """Update an assessment period; optionally set as active."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_assessment_periods
            SET name = %s,
                start_date = %s,
                end_date = %s,
                is_active = %s
            WHERE id = %s
            RETURNING id
            """,
            (name, start_date, end_date, is_active, period_id),
        )
        updated = cur.fetchone()
        if not updated:
            return False
        if is_active:
            cur.execute("UPDATE portal_assessment_periods SET is_active = FALSE WHERE id <> %s", (period_id,))
            cur.execute("UPDATE portal_assessment_periods SET is_active = TRUE WHERE id = %s", (period_id,))
        return True


def delete_period(period_id: int) -> bool:
    """Delete a period if it is not active and not referenced."""
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT is_active FROM portal_assessment_periods WHERE id = %s", (period_id,))
        row = cur.fetchone()
        if not row or row["is_active"]:
            return False
        cur.execute("DELETE FROM portal_assessment_periods WHERE id = %s", (period_id,))
        return cur.rowcount > 0


def get_dashboard_user_profile(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch basic profile info (including password hash) for a dashboard user."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                email,
                full_name,
                role,
                nip,
                nrk,
                jabatan,
                whatsapp_number,
                profile_photo_path,
                password_hash
            FROM dashboard_users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_dashboard_user_profile(
    user_id: int,
    *,
    full_name: Optional[str] = None,
    email: Optional[str] = None,
    whatsapp_number: Optional[str] = None,
    nip: Optional[str] = None,
    nrk: Optional[str] = None,
    jabatan: Optional[str] = None,
    password_hash: Optional[str] = None,
) -> bool:
    """Update editable profile fields for a dashboard user."""
    updates = []
    params: List[Any] = []

    if full_name:
        updates.append("full_name = %s")
        params.append(full_name)
    if email:
        updates.append("email = %s")
        params.append(email)
    updates.append("whatsapp_number = %s")
    params.append(whatsapp_number)
    updates.append("nip = %s")
    params.append(nip)
    updates.append("nrk = %s")
    params.append(nrk)
    updates.append("jabatan = %s")
    params.append(jabatan)
    if password_hash:
        updates.append("password_hash = %s")
        params.append(password_hash)

    if not updates:
        return False

    params.append(user_id)
    query = f"UPDATE dashboard_users SET {', '.join(updates)} WHERE id = %s"
    with get_cursor(commit=True) as cur:
        cur.execute(query, params)
        return cur.rowcount > 0


def update_dashboard_user_profile_photo(
    user_id: int,
    *,
    photo_path: Optional[str],
) -> bool:
    """Update profile photo path for a dashboard user."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE dashboard_users
            SET profile_photo_path = %s
            WHERE id = %s
            """,
            (photo_path, user_id),
        )
        return cur.rowcount > 0


# ============================================
# School Classroom Configuration Functions
# ============================================

def list_school_classrooms(school_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
    """Get all classroom configurations for a school."""
    with get_cursor() as cur:
        query = """
            SELECT 
                id, school_id, name, grade_level, variant,
                capacity, notes, active, created_at, updated_at
            FROM school_classrooms
            WHERE school_id = %s
        """
        params = [school_id]
        
        if active_only:
            query += " AND active = TRUE"
        
        query += " ORDER BY grade_level, variant, name"
        
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def create_school_classroom(
    school_id: int,
    name: str,
    grade_level: Optional[int] = None,
    variant: Optional[str] = None,
    capacity: Optional[int] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new classroom configuration for a school."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO school_classrooms 
                (school_id, name, grade_level, variant, capacity, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, school_id, name, grade_level, variant, capacity, notes, active, created_at
            """,
            (school_id, name, grade_level, variant, capacity, notes)
        )
        return dict(cur.fetchone())


def update_school_classroom(
    classroom_id: int,
    name: Optional[str] = None,
    grade_level: Optional[int] = None,
    variant: Optional[str] = None,
    capacity: Optional[int] = None,
    notes: Optional[str] = None,
    active: Optional[bool] = None
) -> bool:
    """Update classroom configuration."""
    updates = []
    params = []
    
    if name is not None:
        updates.append("name = %s")
        params.append(name)
    if grade_level is not None:
        updates.append("grade_level = %s")
        params.append(grade_level)
    if variant is not None:
        updates.append("variant = %s")
        params.append(variant)
    if capacity is not None:
        updates.append("capacity = %s")
        params.append(capacity)
    if notes is not None:
        updates.append("notes = %s")
        params.append(notes)
    if active is not None:
        updates.append("active = %s")
        params.append(active)
    
    if not updates:
        return False
    
    updates.append("updated_at = NOW()")
    params.append(classroom_id)
    
    with get_cursor(commit=True) as cur:
        query = f"UPDATE school_classrooms SET {', '.join(updates)} WHERE id = %s RETURNING id"
        cur.execute(query, params)
        return cur.fetchone() is not None


def delete_school_classroom(classroom_id: int) -> bool:
    """Delete a classroom configuration."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM school_classrooms WHERE id = %s RETURNING id",
            (classroom_id,)
        )
        return cur.fetchone() is not None


def save_school_classrooms_batch(
    school_id: int,
    classrooms: List[Dict[str, Any]]
) -> bool:
    """
    Save multiple classrooms at once (replace all).
    Expects list of dicts with keys: name, grade_level, variant, capacity
    """
    with get_cursor(commit=True) as cur:
        # Delete existing classrooms
        cur.execute("DELETE FROM school_classrooms WHERE school_id = %s", (school_id,))
        
        # Insert new ones
        for classroom in classrooms:
            cur.execute(
                """
                INSERT INTO school_classrooms 
                    (school_id, name, grade_level, variant, capacity, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    school_id,
                    classroom.get("name"),
                    classroom.get("grade_level"),
                    classroom.get("variant"),
                    classroom.get("capacity"),
                    classroom.get("notes")
                )
            )
        return True


# ==========================================
# Section & Coordinator Queries
# ==========================================


def ensure_classroom_rooms_for_school(school_id: int) -> None:
    """
    Ensure there is a portal_room + portal_school_rooms entry for each configured classroom.
    Uses the base room for the matching grade (e.g., "Ruang Kelas 1") as a template and
    copies its aspects to generated rooms (e.g., "Ruang Kelas 1A").
    """
    import re  # Import at function level for regex operations

    tk_variant_pattern = re.compile(r"^\s*(?:Ruang\s+)?Kelas\s+TK\s+([AB])\s*\d+\s*$", re.IGNORECASE)
    tk_base_pattern = re.compile(r"^\s*(?:Ruang\s+)?Kelas\s+TK\s*$", re.IGNORECASE)
    numeric_variant_pattern = re.compile(r"\bKelas\s+-?\d+[A-Z]+$", re.IGNORECASE)
    
    classrooms = list_school_classrooms(school_id, active_only=True)
    if not classrooms:
        # No classrooms configured - remove all variant classroom rooms for this school
        with get_cursor(commit=True) as cur:
            cur.execute("""
                DELETE FROM portal_school_rooms
                WHERE school_id = %s
                AND room_id IN (
                    SELECT id FROM portal_rooms
                    WHERE name ~ E'Kelas\\\\s+-?\\\\d+[A-Z]+' OR name ~ E'Kelas\\\\s+TK\\\\s+[AB]\\\\d+'
                )
            """, (school_id,))
        return

    # Include inactive rooms so we can revive old variants instead of colliding on insert
    all_rooms = list_portal_rooms(active_only=False)

    def _is_variant_name(room_name: str) -> bool:
        return bool(numeric_variant_pattern.search(room_name or "") or tk_variant_pattern.match(room_name or ""))

    def _room_grade(room_name: str) -> Optional[int]:
        m = re.search(r"\bKelas\s+(-?\d+)", room_name or "", flags=re.IGNORECASE)
        if not m:
            return None
        try:
            return int(m.group(1))
        except (TypeError, ValueError):
            return None

    def _tk_base_label(grade_int: int) -> Optional[str]:
        if grade_int == -1:
            return "Kelas TK A"
        if grade_int == 0:
            return "Kelas TK B"
        return None

    def _build_room_name(grade_int: int, variant: str | None) -> str:
        tk_label = _tk_base_label(grade_int)
        if tk_label:
            return f"{tk_label}{variant or ''}".strip()
        base_room = template_by_grade.get(grade_int)
        base_name = (base_room or {}).get("name") or f"Ruang Kelas {grade_int}"
        return f"{base_name}{variant or ''}".strip()

    def _normalize_tk_variant(grade_int: int, variant: str) -> str:
        if grade_int in (-1, 0) and variant and not variant.isdigit():
            if len(variant) == 1 and variant.isalpha():
                return str(ord(variant) - ord("A") + 1)
        return variant

    # Map grade -> base room, plus fallback template for missing grades
    template_by_grade: Dict[int, Dict[str, Any]] = {}
    fallback_template: Optional[Dict[str, Any]] = None
    for room in all_rooms:
        name_val = room.get("name") or ""
        # Map base TK room as template for TK A/B
        if tk_base_pattern.match(name_val):
            template_by_grade.setdefault(-1, room)
            template_by_grade.setdefault(0, room)
            if not fallback_template:
                fallback_template = room
            continue
        # Skip variant names like "Ruang Kelas 1A" or "Kelas TK A1" when choosing template
        if _is_variant_name(name_val):
            continue
        grade = _room_grade(name_val)
        if grade is not None and grade not in template_by_grade:
            template_by_grade[grade] = room
        if not fallback_template and "kelas" in name_val.lower():
            fallback_template = room

    # Quick lookup by name (case-insensitive)
    room_by_name = {r["name"].lower(): r for r in all_rooms if r.get("name")}

    with get_cursor(commit=True) as cur:
        for cls in classrooms:
            grade = cls.get("grade_level")
            if grade is None:
                continue
            try:
                grade_int = int(grade)
            except (TypeError, ValueError):
                continue

            base_room = template_by_grade.get(grade_int)
            # Reactivate base template if it was deactivated in the past
            if base_room and not base_room.get("active"):
                cur.execute("UPDATE portal_rooms SET active = TRUE WHERE id = %s", (base_room["id"],))
                base_room["active"] = True
                room_by_name[(base_room.get("name") or "").lower()] = base_room
            if not base_room:
                # Create a base template for this grade using fallback styling (aspects/category/etc).
                template_source = fallback_template
                if grade_int in (-1, 0):
                    base_name = "Ruang Kelas TK"
                else:
                    base_name = f"Ruang Kelas {grade_int}"
                base_cat = (template_source or {}).get("category") or "akademik"
                base_desc = (template_source or {}).get("description")
                base_sort = (template_source or {}).get("sort_order") or 0
                base_required = (template_source or {}).get("is_required") or False

                cur.execute(
                    """
                    INSERT INTO portal_rooms (name, description, category, sort_order, active, is_required)
                    VALUES (%s, %s, %s, %s, TRUE, %s)
                    RETURNING id, name, description, category, sort_order, is_required
                    """,
                    (base_name, base_desc, base_cat, base_sort, base_required),
                )
                new_base = dict(cur.fetchone())
                template_by_grade[grade_int] = new_base
                if grade_int in (-1, 0):
                    template_by_grade[-1] = new_base
                    template_by_grade[0] = new_base
                room_by_name[base_name.lower()] = new_base
                base_room = new_base

                # Copy aspects from the fallback template (if any) to the new base
                base_aspects = (template_source or {}).get("aspects") or []
                for idx, asp in enumerate(base_aspects):
                    cur.execute(
                        """
                        INSERT INTO portal_aspects (room_id, name, description, sort_order, active, is_required)
                        VALUES (%s, %s, %s, %s, TRUE, %s)
                        """,
                        (
                            new_base["id"],
                            asp.get("name"),
                            asp.get("description"),
                            asp.get("sort_order") if asp.get("sort_order") is not None else idx,
                            asp.get("is_required") or False,
                        ),
                    )

            raw_variant = (cls.get("variant") or "").strip().upper()
            variant = _normalize_tk_variant(grade_int, raw_variant)
            target_name = _build_room_name(grade_int, variant)

            # Debug logging to track variant room creation
            from flask import current_app
            current_app.logger.info(
                "[ensure_classroom_rooms] Processing classroom: school_id=%s, grade=%s, variant='%s', target_name='%s'",
                school_id, grade_int, variant, target_name
            )

            existing_room = room_by_name.get(target_name.lower())
            if existing_room:
                target_room_id = existing_room["id"]
                # Ensure existing room is active so it appears in room lists
                if not existing_room.get("active"):
                    cur.execute("UPDATE portal_rooms SET active = TRUE WHERE id = %s", (target_room_id,))
                    existing_room["active"] = True
                    room_by_name[target_name.lower()] = existing_room
                current_app.logger.info(
                    "[ensure_classroom_rooms] Room '%s' already exists in portal_rooms (room_id=%s)",
                    target_name, target_room_id
                )
            else:
                cur.execute(
                    """
                    INSERT INTO portal_rooms (name, description, category, sort_order, active, is_required)
                    VALUES (%s, %s, %s, %s, TRUE, %s)
                    RETURNING id, name, description, category, sort_order, is_required
                    """,
                    (
                        target_name,
                        base_room.get("description"),
                        base_room.get("category") or "akademik",
                        base_room.get("sort_order") or 0,
                        base_room.get("is_required") or False,
                    ),
                )
                new_room = dict(cur.fetchone())
                room_by_name[target_name.lower()] = new_room
                target_room_id = new_room["id"]
                
                current_app.logger.info(
                    "[ensure_classroom_rooms] Created NEW room '%s' in portal_rooms (room_id=%s, category=%s)",
                    target_name, target_room_id, new_room.get("category")
                )

                # Copy aspects from base room if target has none
                base_aspects = base_room.get("aspects") or []
                for idx, asp in enumerate(base_aspects):
                    cur.execute(
                        """
                        INSERT INTO portal_aspects (room_id, name, description, sort_order, active, is_required)
                        VALUES (%s, %s, %s, %s, TRUE, %s)
                        """,
                        (
                            target_room_id,
                            asp.get("name"),
                            asp.get("description"),
                            asp.get("sort_order") if asp.get("sort_order") is not None else idx,
                            asp.get("is_required") or False,
                        ),
                    )


            # Attach room to school with quantity = capacity (fallback 1)
            quantity_val = cls.get("capacity") or 1
            notes_val = cls.get("notes")
            cur.execute(
                """
                INSERT INTO portal_school_rooms (school_id, room_id, quantity, notes)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (school_id, room_id)
                DO UPDATE SET 
                    quantity = EXCLUDED.quantity,
                    notes = EXCLUDED.notes
                """,
                (school_id, target_room_id, quantity_val, notes_val),
            )
            # Ensure required aspects are marked enabled for this school room
            cur.execute(
                """
                INSERT INTO portal_school_room_aspects (school_room_id, aspect_id)
                SELECT sr.id, a.id
                FROM portal_school_rooms sr
                JOIN portal_aspects a ON a.room_id = sr.room_id AND a.is_required = TRUE
                WHERE sr.school_id = %s AND sr.room_id = %s
                ON CONFLICT DO NOTHING
                """,
                (school_id, target_room_id),
            )

    # CLEANUP: Remove variant rooms that are no longer configured
    # Build set of expected variant room names based on current classroom config
    configured_room_names = set()
    for cls in classrooms:
        grade = cls.get("grade_level")
        if grade is None:
            continue
        try:
            grade_int = int(grade)
        except (TypeError, ValueError):
            continue
        raw_variant = (cls.get("variant") or "").strip().upper()
        variant = _normalize_tk_variant(grade_int, raw_variant)
        if variant:
            configured_room_names.add(_build_room_name(grade_int, variant))
    
    # Get all variant rooms currently assigned to this school
    with get_cursor() as cur:
        cur.execute("""
            SELECT sr.room_id, r.name
            FROM portal_school_rooms sr
            JOIN portal_rooms r ON r.id = sr.room_id
            WHERE sr.school_id = %s
            AND (r.name ~ E'Kelas\\\\s+-?\\\\d+[A-Z]+' OR r.name ~ E'Kelas\\\\s+TK\\\\s+[AB]\\\\d+')
        """, (school_id,))
        
        assigned_variant_rooms = cur.fetchall()
    
    # Find orphaned room IDs (assigned but not configured anymore)
    orphaned_room_ids = [
        row[0] for row in assigned_variant_rooms
        if row[1] not in configured_room_names
    ]
    
    if orphaned_room_ids:
        with get_cursor(commit=True) as cur:
            cur.execute("""
                DELETE FROM portal_school_rooms
                WHERE school_id = %s
                AND room_id = ANY(%s)
            """, (school_id, orphaned_room_ids))
            
        orphaned_names = [row[1] for row in assigned_variant_rooms if row[0] in orphaned_room_ids]
        current_app.logger.info(
            "[ensure_classroom_rooms] Removed %d orphaned variant rooms for school_id=%s: %s",
            len(orphaned_room_ids), school_id, orphaned_names
        )

def get_section_by_coordinator(coordinator_id: int):
    """Get section managed by coordinator."""
    from dashboard.db_access import get_cursor
    with get_cursor() as cur:
        cur.execute("""
            SELECT * FROM sections 
            WHERE coordinator_id = %s
        """, (coordinator_id,))
        return cur.fetchone()


def get_optional_rooms_for_schools(school_ids: list[int]) -> dict:
    """
    Get optional rooms (not required) and which assigned schools have selected them.
    
    Returns dict with format:
        {'SD': [{'room_id': 1, 'room_name': 'Perpustakaan', 'selection_count': 3, 'total_schools': 5}, ...]}
    """
    from dashboard.db_access import get_cursor
    
    if not school_ids:
        return {}
    
    with get_cursor() as cur:
        cur.execute("""
            SELECT 
                r.id as room_id,
                r.name as room_name,
                r.category as room_category,
                s.id as school_id,
                s.jenjang,
                sr.id as is_selected
            FROM portal_rooms r
            CROSS JOIN (
                SELECT id, jenjang 
                FROM portal_schools 
                WHERE id = ANY(%s) AND active = TRUE
            ) s
            LEFT JOIN portal_school_rooms sr ON sr.room_id = r.id AND sr.school_id = s.id
            WHERE r.active = TRUE AND r.is_required = FALSE
            ORDER BY s.jenjang, r.name
        """, (school_ids,))
        rows = cur.fetchall()
    
    result = {}
    for row in rows:
        jenjang, room_id, room_name = row['jenjang'], row['room_id'], row['room_name']
        room_category = row.get('room_category')
        is_selected = row['is_selected'] is not None
        
        if jenjang not in result:
            result[jenjang] = {}
        if room_id not in result[jenjang]:
            result[jenjang][room_id] = {
                'room_name': room_name,
                'room_category': room_category,
                'selected_by_schools': [],
                'total_schools': 0,
            }
        result[jenjang][room_id]['total_schools'] += 1
        if is_selected:
            result[jenjang][room_id]['selected_by_schools'].append(row['school_id'])
    
    formatted = {}
    for jenjang, rooms in result.items():
        formatted[jenjang] = [
            {'room_id': rid, **data, 'selection_count': len(data['selected_by_schools'])}
            for rid, data in rooms.items()
        ]
    return formatted


def get_room_with_aspects(room_id: int) -> dict:
    """Get room details with all its aspects."""
    from dashboard.db_access import get_cursor
    
    with get_cursor() as cur:
        # Get room
        cur.execute("""
            SELECT id, name, description, category, is_required
            FROM portal_rooms
            WHERE id = %s AND active = TRUE
        """, (room_id,))
        
        room = cur.fetchone()
        if not room:
            return None
        
        room_dict = dict(room)
        
        # Get aspects
        cur.execute("""
            SELECT id, name, description, sort_order, is_required
            FROM portal_aspects
            WHERE room_id = %s AND active = TRUE
            ORDER BY sort_order, name
        """, (room_id,))
        
        room_dict['aspects'] = [dict(row) for row in cur.fetchall()]
        
    return room_dict


def get_section_by_id(section_id: int):
    """Get section by ID."""
    from dashboard.db_access import get_cursor
    with get_cursor() as cur:
        cur.execute("SELECT * FROM sections WHERE id = %s", (section_id,))
        return cur.fetchone()


def get_staff_by_section(section_id: int):
    """Get all staff in a section."""
    from dashboard.db_access import get_cursor
    with get_cursor() as cur:
        cur.execute("""
            SELECT u.*, s.name as section_name
            FROM dashboard_users u
            LEFT JOIN sections s ON u.section_id = s.id
            WHERE u.section_id = %s 
            AND u.role = 'staff'
            ORDER BY u.full_name
        """, (section_id,))
        return cur.fetchall()


def get_team_assessment_stats(section_id: int):
    """Get assessment statistics for team in a section."""
    from dashboard.db_access import get_cursor
    with get_cursor() as cur:
        cur.execute("""
            SELECT 
                COUNT(DISTINCT u.id) as total_staff,
                COUNT(a.id) as total_assessments,
                COUNT(CASE WHEN a.status = 'completed' THEN 1 END) as completed_assessments,
                COUNT(DISTINCT a.school_id) as schools_assessed
            FROM dashboard_users u
            LEFT JOIN portal_assessments a ON a.staff_id = u.id
            WHERE u.section_id = %s AND u.role = 'staff'
        """, (section_id,))
        return cur.fetchone()


# =====================================================
# Coordinator Team Statistics Functions
# =====================================================

def fetch_coordinator_team_stats(staff_ids: List[int], period_id: Optional[int] = None) -> Dict[str, Any]:
    """Fetch aggregated stats for a coordinator's team members.
    
    Args:
        staff_ids: List of team member user IDs
        period_id: Optional period filter
    """
    if not staff_ids:
        return {
            "total_assessments": 0,
            "schools_assessed": 0,
            "avg_score": 0,
            "avg_score_pct": 0,
            "verified_count": 0,
            "submitted_count": 0,
        }
    
    with get_cursor() as cur:
        placeholders = ",".join(["%s"] * len(staff_ids))
        params = list(staff_ids)
        period_filter = ""
        if period_id:
            period_filter = " AND period_id = %s"
            params.append(period_id)
        
        cur.execute(f"""
            SELECT 
                COUNT(*) as total_assessments,
                COUNT(DISTINCT school_id) as schools_assessed,
                ROUND(AVG(total_score)::numeric, 1) as avg_score,
                ROUND(AVG({_score_pct_sql("total_score", "score_scale_max")})::numeric, 1) as avg_score_pct,
                COUNT(*) FILTER (WHERE status = 'verified') as verified_count,
                COUNT(*) FILTER (WHERE status = 'submitted') as submitted_count
            FROM portal_assessments
            WHERE staff_id IN ({placeholders})
              AND status IN ('submitted', 'verified')
              {period_filter}
        """, params)
        
        row = cur.fetchone()
        return {
            "total_assessments": row['total_assessments'] or 0,
            "schools_assessed": row['schools_assessed'] or 0,
            "avg_score": float(row['avg_score']) if row['avg_score'] else 0,
            "avg_score_pct": float(row['avg_score_pct']) if row['avg_score_pct'] else 0,
            "verified_count": row['verified_count'] or 0,
            "submitted_count": row['submitted_count'] or 0,
        }


def list_team_assessments(
    staff_ids: List[int],
    limit: int = 50,
    period_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List recent assessments by team members only.
    
    Args:
        staff_ids: List of team member user IDs
        limit: Max results
        period_id: Optional period filter
    """
    if not staff_ids:
        return []
    
    with get_cursor() as cur:
        placeholders = ",".join(["%s"] * len(staff_ids))
        params = list(staff_ids)
        period_filter = ""
        if period_id:
            period_filter = " AND a.period_id = %s"
            params.append(period_id)
        params.append(limit)
        
        cur.execute(f"""
            SELECT 
                a.id,
                a.school_id,
                s.name as school_name,
                s.npsn,
                s.jenjang,
                a.status,
                a.total_score,
                a.score_scale_max,
                CASE
                    WHEN a.total_score IS NULL THEN NULL
                    ELSE {_score_pct_sql("a.total_score", "a.score_scale_max")}
                END AS score_pct,
                a.submitted_at,
                u.full_name as assessor_name,
                u.id as assessor_id
            FROM portal_assessments a
            JOIN portal_schools s ON a.school_id = s.id
            LEFT JOIN dashboard_users u ON a.staff_id = u.id
            WHERE a.staff_id IN ({placeholders})
              AND a.status IN ('submitted', 'verified')
              {period_filter}
            ORDER BY a.submitted_at DESC NULLS LAST
            LIMIT %s
        """, params)
        
        return [dict(row) for row in cur.fetchall()]


def fetch_team_top_schools(
    staff_ids: List[int],
    period_id: Optional[int] = None,
    limit: int = 5,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Fetch top scoring schools assessed by team members."""
    if not staff_ids:
        return []
    
    with get_cursor() as cur:
        placeholders = ",".join(["%s"] * len(staff_ids))
        params = list(staff_ids)
        period_filter = ""
        if period_id:
            period_filter = " AND a.period_id = %s"
            params.append(period_id)
        params.extend([limit, offset])
        
        cur.execute(
            f"""
            WITH latest AS (
                SELECT DISTINCT ON (a.school_id)
                    s.id,
                    s.name,
                    s.npsn,
                    s.jenjang,
                    a.total_score,
                    a.score_scale_max,
                    {_score_pct_sql("a.total_score", "a.score_scale_max")} AS score_pct,
                    a.submitted_at,
                    u.full_name AS assessor_name
                FROM portal_assessments a
                JOIN portal_schools s ON a.school_id = s.id
                LEFT JOIN dashboard_users u ON a.staff_id = u.id
                WHERE a.staff_id IN ({placeholders})
                  AND a.status IN ('submitted', 'verified')
                  AND a.total_score IS NOT NULL
                  {period_filter}
                ORDER BY a.school_id, a.submitted_at DESC NULLS LAST, a.id DESC
            )
            SELECT * FROM latest
            ORDER BY score_pct DESC NULLS LAST
            LIMIT %s OFFSET %s
            """,
            params,
        )
        
        return [dict(row) for row in cur.fetchall()]


def fetch_team_bottom_schools(
    staff_ids: List[int],
    period_id: Optional[int] = None,
    limit: int = 5,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Fetch lowest scoring schools assessed by team members."""
    if not staff_ids:
        return []
    
    with get_cursor() as cur:
        placeholders = ",".join(["%s"] * len(staff_ids))
        params = list(staff_ids)
        period_filter = ""
        if period_id:
            period_filter = " AND a.period_id = %s"
            params.append(period_id)
        params.extend([limit, offset])
        
        cur.execute(
            f"""
            WITH latest AS (
                SELECT DISTINCT ON (a.school_id)
                    s.id,
                    s.name,
                    s.npsn,
                    s.jenjang,
                    a.total_score,
                    a.score_scale_max,
                    {_score_pct_sql("a.total_score", "a.score_scale_max")} AS score_pct,
                    a.submitted_at,
                    u.full_name AS assessor_name
                FROM portal_assessments a
                JOIN portal_schools s ON a.school_id = s.id
                LEFT JOIN dashboard_users u ON a.staff_id = u.id
                WHERE a.staff_id IN ({placeholders})
                  AND a.status IN ('submitted', 'verified')
                  AND a.total_score IS NOT NULL
                  {period_filter}
                ORDER BY a.school_id, a.submitted_at DESC NULLS LAST, a.id DESC
            )
            SELECT * FROM latest
            ORDER BY score_pct ASC NULLS LAST
            LIMIT %s OFFSET %s
            """,
            params,
        )
        
        return [dict(row) for row in cur.fetchall()]
