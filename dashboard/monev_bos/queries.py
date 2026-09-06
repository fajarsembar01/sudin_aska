from dashboard.db_access import get_cursor
from typing import List, Dict, Any, Optional
from datetime import date
import json
import secrets
from .external_photos import generate_access_token


SUPPORTED_BOP_CLAIM_PERIODS = {(2025, 4), (2026, 1), (2026, 2)}


def _verification_display_text(value: Any) -> Any:
    """Normalize legacy review wording before it is shown in the Monev UI."""
    if not isinstance(value, str):
        return value
    replacements = (
        ("Memvalidasi", "Memverifikasi"),
        ("memvalidasi", "memverifikasi"),
        ("Divalidasi", "Diverifikasi"),
        ("divalidasi", "diverifikasi"),
        ("Validasi", "Verifikasi"),
        ("validasi", "verifikasi"),
        ("Auditor", "Verifikator"),
        ("auditor", "verifikator"),
        ("Diaudit", "Diverifikasi"),
        ("diaudit", "diverifikasi"),
        ("Audit", "Verifikasi"),
        ("audit", "verifikasi"),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    return value


def attach_admin_input_names(
    items: List[Dict[str, Any]],
    target_type: str,
    *,
    actions: Optional[List[str]] = None,
    item_id_field: str = "id",
) -> List[Dict[str, Any]]:
    """Attach the earliest recorded admin creator to master rows."""
    for item in items:
        item["input_admin_name"] = "Tidak ada"
    target_ids = [int(item[item_id_field]) for item in items if item.get(item_id_field) is not None]
    if not target_ids:
        return items

    action_names = [str(action).strip().upper() for action in (actions or ["CREATE"])]
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (log.target_id)
                   log.target_id,
                   COALESCE(admin.full_name, admin.email, 'Tidak ada') AS admin_name
            FROM dashboard_admin_action_logs log
            LEFT JOIN dashboard_users admin ON admin.id = log.user_id
            WHERE log.feature_key = 'monev_bos'
              AND log.target_type = %s
              AND log.target_id = ANY(%s)
              AND log.action = ANY(%s)
            ORDER BY log.target_id, log.created_at ASC, log.id ASC
            """,
            (target_type, target_ids, action_names),
        )
        creator_map = {int(row["target_id"]): row["admin_name"] for row in cur.fetchall()}

    for item in items:
        item_id = item.get(item_id_field)
        if item_id is not None:
            item["input_admin_name"] = creator_map.get(int(item_id), "Tidak ada")
    return items


def attach_period_admin_input_names(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach the admin who generated each period year, when that history exists."""
    for period in periods:
        period["input_admin_name"] = "Tidak ada"
    target_names = sorted({f"Periode {period['year']}" for period in periods if period.get("year") is not None})
    if not target_names:
        return periods

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (log.target_name)
                   log.target_name,
                   COALESCE(admin.full_name, admin.email, 'Tidak ada') AS admin_name
            FROM dashboard_admin_action_logs log
            LEFT JOIN dashboard_users admin ON admin.id = log.user_id
            WHERE log.feature_key = 'monev_bos'
              AND log.target_type = 'MONEV_PERIOD_YEAR'
              AND log.action = 'GENERATE'
              AND log.target_name = ANY(%s)
            ORDER BY log.target_name, log.created_at ASC, log.id ASC
            """,
            (target_names,),
        )
        creator_map = {row["target_name"]: row["admin_name"] for row in cur.fetchall()}

    for period in periods:
        period["input_admin_name"] = creator_map.get(f"Periode {period.get('year')}", "Tidak ada")
    return periods


def list_admin_action_history(target_types: List[str], limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent centralized admin actions for selected Monev master targets."""
    normalized_targets = [str(target).strip().upper() for target in target_types if target]
    if not normalized_targets:
        return []
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT log.id,
                   log.created_at,
                   log.action,
                   log.target_type,
                   log.target_id,
                   log.target_name,
                   log.metadata,
                   COALESCE(admin.full_name, admin.email, 'Tidak ada') AS admin_name
            FROM dashboard_admin_action_logs log
            LEFT JOIN dashboard_users admin ON admin.id = log.user_id
            WHERE log.feature_key = 'monev_bos'
              AND log.target_type = ANY(%s)
            ORDER BY log.created_at DESC, log.id DESC
            LIMIT %s
            """,
            (normalized_targets, max(1, min(int(limit), 200))),
        )
        return [dict(row) for row in cur.fetchall()]

# --- PERIODS ---

# Default TW date ranges (fixed)
_TW_RANGES = {
    1: ("01-01", "03-31"),
    2: ("04-01", "06-30"),
    3: ("07-01", "09-30"),
    4: ("10-01", "12-31"),
}

def ensure_periods_for_year(year: int) -> None:
    """Auto-generate TW 1-4 for a given year, fixing dates if they already exist."""
    with get_cursor(commit=True) as cur:
        for tw in range(1, 5):
            start_str, end_str = _TW_RANGES[tw]
            start_date = date.fromisoformat(f"{year}-{start_str}")
            end_date = date.fromisoformat(f"{year}-{end_str}")
            cur.execute(
                """
                INSERT INTO monev_bos_periods (year, tw, start_date, end_date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (year, tw) DO UPDATE 
                SET start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date
                """,
                (year, tw, start_date, end_date)
            )

def list_periods() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_periods ORDER BY year DESC, tw ASC")
        return [dict(row) for row in cur.fetchall()]

def list_periods_by_year(year: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_periods WHERE year = %s ORDER BY tw ASC", (year,))
        return [dict(row) for row in cur.fetchall()]

def get_available_years() -> List[int]:
    with get_cursor() as cur:
        cur.execute("SELECT DISTINCT year FROM monev_bos_periods ORDER BY year DESC")
        return [row[0] for row in cur.fetchall()]

def get_active_period() -> Optional[Dict[str, Any]]:
    """Get the first active period (backward compat)."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_periods WHERE is_active = TRUE ORDER BY tw ASC LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None

def get_active_periods() -> List[Dict[str, Any]]:
    """Get all active periods."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_periods WHERE is_active = TRUE ORDER BY year DESC, tw ASC")
        return [dict(row) for row in cur.fetchall()]


def get_admin_dashboard_overview(period_id: int) -> Dict[str, Any]:
    """Return period-level reporting, verification, and follow-up metrics."""
    with get_cursor() as cur:
        cur.execute(
            """
            WITH report_stats AS (
                SELECT
                    COUNT(*) AS total_reports,
                    COUNT(*) FILTER (WHERE status = 'draft') AS draft_reports,
                    COUNT(*) FILTER (WHERE status = 'submitted') AS submitted_reports,
                    COUNT(*) FILTER (WHERE status = 'in_review') AS in_review_reports,
                    COUNT(*) FILTER (WHERE status = 'needs_revision') AS revision_reports,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed_reports,
                    COUNT(*) FILTER (WHERE status = 'completed_with_notes') AS completed_with_notes_reports,
                    COALESCE(SUM(bosp_receipt_amount), 0) AS bosp_receipts,
                    COALESCE(SUM(bop_receipt_amount), 0) AS bop_receipts
                FROM monev_bos_reports
                WHERE period_id = %s
            ),
            activity_stats AS (
                SELECT
                    COUNT(a.id) AS total_activities,
                    COUNT(a.id) FILTER (WHERE a.status = 'pending') AS pending_activities,
                    COUNT(a.id) FILTER (WHERE a.status = 'in_review') AS in_review_activities,
                    COUNT(a.id) FILTER (WHERE a.status = 'valid') AS valid_activities,
                    COUNT(a.id) FILTER (WHERE a.status = 'invalid') AS invalid_activities,
                    COALESCE(SUM(a.realized_amount) FILTER (WHERE a.fund_source = 'BOS'), 0) AS bos_realized,
                    COALESCE(SUM(a.realized_amount) FILTER (WHERE a.fund_source = 'BOP'), 0) AS bop_realized
                FROM monev_bos_activities a
                JOIN monev_bos_reports r ON r.id = a.report_id
                WHERE r.period_id = %s
            ),
            assignment_stats AS (
                SELECT COUNT(*) AS assigned_schools, COUNT(DISTINCT team_id) AS assigned_teams
                FROM monev_bos_assignments
                WHERE period_id = %s
            )
            SELECT report_stats.*, activity_stats.*, assignment_stats.*,
                   (SELECT COUNT(*) FROM monev_bos_vendors WHERE status = 'pending') AS pending_vendors,
                   (SELECT COUNT(*) FROM monev_bos_edit_requests WHERE status = 'pending') AS pending_edit_requests,
                   (SELECT COUNT(*)
                    FROM monev_bos_activity_docs photo
                    JOIN monev_bos_activities photo_activity ON photo_activity.id = photo.activity_id
                    JOIN monev_bos_reports photo_report ON photo_report.id = photo_activity.report_id
                    WHERE photo_report.period_id = %s
                      AND photo.doc_type IN ('field_photo', 'live_photo')) AS total_activity_photos
            FROM report_stats, activity_stats, assignment_stats
            """,
            (period_id, period_id, period_id, period_id),
        )
        row = cur.fetchone()
        return dict(row) if row else {}


def list_recent_period_reports(period_id: int, limit: int = 6) -> List[Dict[str, Any]]:
    """Return the most recently updated school reports for an admin dashboard."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT r.id AS report_id,
                   r.status,
                   r.updated_at,
                   r.bosp_receipt_amount,
                   r.bop_receipt_amount,
                   COALESCE(school.name, school_user.full_name) AS school_name,
                   team.name AS team_name,
                   COUNT(activity.id) AS total_activities,
                   COUNT(activity.id) FILTER (WHERE activity.status IN ('valid', 'invalid')) AS audited_activities,
                   COALESCE(SUM(activity.realized_amount) FILTER (WHERE activity.fund_source = 'BOS'), 0) AS bos_realized,
                   COALESCE(SUM(activity.realized_amount) FILTER (WHERE activity.fund_source = 'BOP'), 0) AS bop_realized
            FROM monev_bos_reports r
            JOIN dashboard_users school_user ON school_user.id = r.school_id
            LEFT JOIN LATERAL (
                SELECT portal_school.name
                FROM portal_schools portal_school
                WHERE portal_school.id = school_user.school_id OR portal_school.user_id = school_user.id
                ORDER BY CASE WHEN portal_school.id = school_user.school_id THEN 0 ELSE 1 END
                LIMIT 1
            ) school ON TRUE
            LEFT JOIN monev_bos_assignments assignment
                   ON assignment.school_id = r.school_id AND assignment.period_id = r.period_id
            LEFT JOIN monev_bos_teams team ON team.id = assignment.team_id
            LEFT JOIN monev_bos_activities activity ON activity.report_id = r.id
            WHERE r.period_id = %s
            GROUP BY r.id, school.name, school_user.full_name, team.name
            ORDER BY r.updated_at DESC, r.id DESC
            LIMIT %s
            """,
            (period_id, max(1, min(int(limit), 20))),
        )
        return [dict(row) for row in cur.fetchall()]


def list_admin_period_school_analytics(period_id: int) -> List[Dict[str, Any]]:
    """Return one monitoring row per school assigned or reporting in a period."""
    with get_cursor() as cur:
        cur.execute(
            """
            WITH school_scope AS (
                SELECT school_id FROM monev_bos_assignments WHERE period_id = %s
                UNION
                SELECT school_id FROM monev_bos_reports WHERE period_id = %s
            )
            SELECT scope.school_id,
                   COALESCE(school.name, school_user.full_name) AS school_name,
                   school.npsn,
                   assignment.id IS NOT NULL AS is_assigned,
                   team.id AS team_id,
                   team.name AS team_name,
                   report.id AS report_id,
                   report.status AS report_status,
                   report.bosp_receipt_amount,
                   report.bop_receipt_amount,
                   report.updated_at,
                   COALESCE(activity.total_activities, 0) AS total_activities,
                   COALESCE(activity.pending_activities, 0) AS pending_activities,
                   COALESCE(activity.in_review_activities, 0) AS in_review_activities,
                   COALESCE(activity.valid_activities, 0) AS valid_activities,
                   COALESCE(activity.invalid_activities, 0) AS invalid_activities,
                   COALESCE(activity.bos_activities, 0) AS bos_activities,
                   COALESCE(activity.bop_activities, 0) AS bop_activities,
                   COALESCE(activity.bos_realized, 0) AS bos_realized,
                   COALESCE(activity.bop_realized, 0) AS bop_realized
            FROM school_scope scope
            JOIN dashboard_users school_user ON school_user.id = scope.school_id
            LEFT JOIN LATERAL (
                SELECT portal_school.name, portal_school.npsn
                FROM portal_schools portal_school
                WHERE portal_school.id = school_user.school_id OR portal_school.user_id = school_user.id
                ORDER BY CASE WHEN portal_school.id = school_user.school_id THEN 0 ELSE 1 END
                LIMIT 1
            ) school ON TRUE
            LEFT JOIN monev_bos_assignments assignment
                   ON assignment.school_id = scope.school_id AND assignment.period_id = %s
            LEFT JOIN monev_bos_teams team ON team.id = assignment.team_id
            LEFT JOIN monev_bos_reports report
                   ON report.school_id = scope.school_id AND report.period_id = %s
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS total_activities,
                       COUNT(*) FILTER (WHERE status = 'pending') AS pending_activities,
                       COUNT(*) FILTER (WHERE status = 'in_review') AS in_review_activities,
                       COUNT(*) FILTER (WHERE status = 'valid') AS valid_activities,
                       COUNT(*) FILTER (WHERE status = 'invalid') AS invalid_activities,
                       COUNT(*) FILTER (WHERE fund_source = 'BOS') AS bos_activities,
                       COUNT(*) FILTER (WHERE fund_source = 'BOP') AS bop_activities,
                       COALESCE(SUM(realized_amount) FILTER (WHERE fund_source = 'BOS'), 0) AS bos_realized,
                       COALESCE(SUM(realized_amount) FILTER (WHERE fund_source = 'BOP'), 0) AS bop_realized
                FROM monev_bos_activities
                WHERE report_id = report.id
            ) activity ON TRUE
            ORDER BY COALESCE(school.name, school_user.full_name) ASC
            """,
            (period_id, period_id, period_id, period_id),
        )
        return [dict(row) for row in cur.fetchall()]


def list_admin_team_performance(period_id: int) -> List[Dict[str, Any]]:
    """Summarize reporting and activity verification performance by assigned team."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT team.id AS team_id,
                   team.name AS team_name,
                   leader.full_name AS leader_name,
                   COUNT(DISTINCT assignment.school_id) AS assigned_schools,
                   COUNT(DISTINCT report.id) AS total_reports,
                   COUNT(DISTINCT report.id) FILTER (WHERE report.status IN ('submitted', 'in_review')) AS review_queue,
                   COUNT(DISTINCT report.id) FILTER (WHERE report.status IN ('completed', 'completed_with_notes')) AS completed_reports,
                   COUNT(DISTINCT report.id) FILTER (WHERE report.status = 'needs_revision') AS revision_reports,
                   COUNT(activity.id) AS total_activities,
                   COUNT(activity.id) FILTER (WHERE activity.status IN ('valid', 'invalid')) AS audited_activities,
                   COUNT(activity.id) FILTER (WHERE activity.status = 'valid') AS valid_activities,
                   COUNT(activity.id) FILTER (WHERE activity.status = 'invalid') AS invalid_activities,
                   COUNT(activity.id) FILTER (WHERE activity.status = 'pending') AS pending_activities,
                   COUNT(activity.id) FILTER (WHERE activity.status = 'in_review') AS in_review_activities,
                   COUNT(activity.id) FILTER (
                       WHERE activity.id IS NOT NULL
                         AND (
                             activity.status IS NULL
                             OR activity.status NOT IN ('valid', 'invalid', 'pending', 'in_review')
                         )
                   ) AS other_activities
            FROM monev_bos_teams team
            LEFT JOIN dashboard_users leader ON leader.id = team.leader_id
            LEFT JOIN monev_bos_assignments assignment
                   ON assignment.team_id = team.id AND assignment.period_id = %s
            LEFT JOIN monev_bos_reports report
                   ON report.school_id = assignment.school_id AND report.period_id = %s
            LEFT JOIN monev_bos_activities activity ON activity.report_id = report.id
            GROUP BY team.id, leader.full_name
            HAVING COUNT(DISTINCT assignment.school_id) > 0
            ORDER BY LOWER(team.name) ASC, team.id ASC
            """,
            (period_id, period_id),
        )
        return [dict(row) for row in cur.fetchall()]


def list_admin_activity_photos(
    period_id: Optional[int],
    limit: int = 24,
    team_id: Optional[int] = None,
    fund_source: Optional[str] = None,
    photo_status: Optional[str] = None,
    search_query: Optional[str] = None,
    order: str = "newest",
) -> List[Dict[str, Any]]:
    """List activity and live photos with school, activity, and verification context."""
    query = """
        SELECT photo.id AS photo_id,
               photo.file_path,
               photo.doc_type,
               photo.file_size,
               photo.lat,
               photo.lng,
               photo.is_audit_valid,
               photo.photo_audit_notes,
               photo.created_at AS photo_created_at,
               photo.photo_audited_at,
               activity.id AS activity_id,
               activity.activity_name,
               activity.activity_code,
               activity.bku_number,
               activity.fund_source,
               activity.status AS activity_status,
               activity.realized_amount,
               activity.vendor_name,
               report.id AS report_id,
               report.period_id,
               period.year AS period_year,
               period.tw AS period_tw,
               COALESCE(school.name, school_user.full_name) AS school_name,
               school.npsn,
               team.id AS team_id,
               team.name AS team_name,
               uploader.full_name AS uploader_name,
               auditor.full_name AS photo_auditor_name
        FROM monev_bos_activity_docs photo
        JOIN monev_bos_activities activity ON activity.id = photo.activity_id
        JOIN monev_bos_reports report ON report.id = activity.report_id
        JOIN monev_bos_periods period ON period.id = report.period_id
        JOIN dashboard_users school_user ON school_user.id = report.school_id
        LEFT JOIN LATERAL (
            SELECT portal_school.name, portal_school.npsn
            FROM portal_schools portal_school
            WHERE portal_school.id = school_user.school_id OR portal_school.user_id = school_user.id
            ORDER BY CASE WHEN portal_school.id = school_user.school_id THEN 0 ELSE 1 END
            LIMIT 1
        ) school ON TRUE
        LEFT JOIN monev_bos_assignments assignment
               ON assignment.school_id = report.school_id AND assignment.period_id = report.period_id
        LEFT JOIN monev_bos_teams team ON team.id = assignment.team_id
        LEFT JOIN dashboard_users uploader ON uploader.id = photo.uploaded_by
        LEFT JOIN dashboard_users auditor ON auditor.id = photo.photo_audited_by
        WHERE photo.doc_type IN ('field_photo', 'live_photo')
    """
    params: List[Any] = []
    if period_id is not None:
        query += " AND report.period_id = %s"
        params.append(period_id)
    if team_id:
        query += " AND team.id = %s"
        params.append(team_id)
    if fund_source in ("BOS", "BOP"):
        query += " AND activity.fund_source = %s"
        params.append(fund_source)
    if photo_status == "valid":
        query += " AND photo.is_audit_valid = TRUE"
    elif photo_status == "invalid":
        query += " AND photo.is_audit_valid = FALSE"
    if search_query:
        pattern = f"%{search_query.strip()}%"
        query += """
            AND (activity.activity_name ILIKE %s
                 OR activity.activity_code ILIKE %s
                 OR activity.bku_number ILIKE %s
                 OR activity.vendor_name ILIKE %s
                 OR COALESCE(school.name, school_user.full_name) ILIKE %s)
        """
        params.extend([pattern] * 5)
    if order == "oldest":
        query += " ORDER BY photo.created_at ASC, photo.id ASC"
    elif order == "random":
        query += " ORDER BY RANDOM()"
    else:
        query += " ORDER BY photo.created_at DESC, photo.id DESC"
    query += " LIMIT %s"
    params.append(max(1, min(int(limit), 500)))

    with get_cursor() as cur:
        cur.execute(query, tuple(params))
        return [dict(row) for row in cur.fetchall()]

def set_active_period(period_id: int) -> None:
    """Activate a single period (without deactivating others)."""
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE monev_bos_periods SET is_active = TRUE WHERE id = %s", (period_id,))

def deactivate_period(period_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE monev_bos_periods SET is_active = FALSE WHERE id = %s", (period_id,))

def update_period_deadline(period_id: int, deadline: date) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_periods SET end_date = %s WHERE id = %s",
            (deadline, period_id)
        )

# --- CHECKLISTS & EXPENSE TYPES (JENIS BELANJA) ---

def list_expense_types(include_inactive: bool = False) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        query = "SELECT * FROM monev_bos_expense_types"
        if not include_inactive:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY sort_order ASC, id ASC"
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def create_expense_type(name: str, code: str, description: str, sort_order: int) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_expense_types (name, code, description, sort_order)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (name, code, description, sort_order)
        )
        return cur.fetchone()[0]


def update_expense_type(expense_type_id: int, name: str, code: str, description: str, sort_order: int, is_active: bool) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_expense_types
            SET name = %s, code = %s, description = %s, sort_order = %s, is_active = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (name, code, description, sort_order, is_active, expense_type_id)
        )


def delete_expense_type(expense_type_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_expense_types WHERE id = %s", (expense_type_id,))


def list_checklists(include_inactive: bool = False) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        query = """
            SELECT c.*, 
                   COALESCE(
                       json_agg(
                           json_build_object('id', et.id, 'name', et.name, 'code', et.code)
                       ) FILTER (WHERE et.id IS NOT NULL), '[]'
                   ) AS expense_types
            FROM monev_bos_checklists c
            LEFT JOIN monev_bos_checklist_expense_types cet ON cet.checklist_id = c.id
            LEFT JOIN monev_bos_expense_types et ON et.id = cet.expense_type_id
        """
        if not include_inactive:
            query += " WHERE c.is_active = TRUE"
        query += " GROUP BY c.id ORDER BY c.sort_order ASC, c.id ASC"
        cur.execute(query)
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d['expense_type_ids'] = [e['id'] for e in d.get('expense_types', []) if isinstance(e, dict) and 'id' in e]
            results.append(d)
        return results


def create_checklist(name: str, description: str, sort_order: int, expense_type_ids: Optional[List[int]] = None) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_checklists (name, description, sort_order)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (name, description, sort_order)
        )
        checklist_id = cur.fetchone()[0]
        if expense_type_ids:
            for et_id in expense_type_ids:
                cur.execute(
                    "INSERT INTO monev_bos_checklist_expense_types (checklist_id, expense_type_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (checklist_id, et_id)
                )
        return checklist_id


def update_checklist(checklist_id: int, name: str, description: str, sort_order: int, is_active: bool, expense_type_ids: Optional[List[int]] = None) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_checklists
            SET name = %s, description = %s, sort_order = %s, is_active = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (name, description, sort_order, is_active, checklist_id)
        )
        cur.execute("DELETE FROM monev_bos_checklist_expense_types WHERE checklist_id = %s", (checklist_id,))
        if expense_type_ids:
            for et_id in expense_type_ids:
                cur.execute(
                    "INSERT INTO monev_bos_checklist_expense_types (checklist_id, expense_type_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (checklist_id, et_id)
                )


def delete_checklist(checklist_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_checklists WHERE id = %s", (checklist_id,))


def get_checklists_for_activity(expense_type_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get active checklists that apply to a specific expense type (or all if expense_type_id is None)."""
    with get_cursor() as cur:
        if not expense_type_id:
            return list_checklists(include_inactive=False)

        cur.execute(
            """
            SELECT DISTINCT c.*
            FROM monev_bos_checklists c
            LEFT JOIN monev_bos_checklist_expense_types cet ON cet.checklist_id = c.id
            WHERE c.is_active = TRUE
              AND (cet.expense_type_id = %s OR NOT EXISTS (SELECT 1 FROM monev_bos_checklist_expense_types WHERE checklist_id = c.id))
            ORDER BY c.sort_order ASC, c.id ASC
            """,
            (expense_type_id,)
        )
        return [dict(row) for row in cur.fetchall()]

# --- TEAMS ---
def list_teams() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT t.*, u.full_name as leader_name, u.email as leader_email
            FROM monev_bos_teams t
            LEFT JOIN dashboard_users u ON t.leader_id = u.id
            ORDER BY t.name ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]

def create_team(name: str, leader_id: Optional[int]) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO monev_bos_teams (name, leader_id) VALUES (%s, %s) RETURNING id",
            (name, leader_id)
        )
        team_id = cur.fetchone()[0]
        if leader_id:
            cur.execute(
                "INSERT INTO monev_bos_team_members (team_id, staff_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (team_id, leader_id)
            )
        return team_id

def delete_team(team_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_teams WHERE id = %s", (team_id,))

def update_team_leader(team_id: int, leader_id: Optional[int]) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_teams SET leader_id = %s, updated_at = NOW() WHERE id = %s",
            (leader_id, team_id)
        )
        if leader_id:
            cur.execute(
                "INSERT INTO monev_bos_team_members (team_id, staff_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (team_id, leader_id)
            )

def update_team(team_id: int, name: str, leader_id: Optional[int]) -> None:
    """Update a team's name and leader in one transaction."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_teams
            SET name = %s, leader_id = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (name, leader_id, team_id),
        )
        if leader_id:
            cur.execute(
                "INSERT INTO monev_bos_team_members (team_id, staff_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (team_id, leader_id),
            )

# --- ASSIGNMENTS ---
def list_assignments(period_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, t.name as team_name, s.full_name as school_name, s.email as school_email
            FROM monev_bos_assignments a
            JOIN monev_bos_teams t ON a.team_id = t.id
            JOIN dashboard_users s ON a.school_id = s.id
            WHERE a.period_id = %s
            ORDER BY s.full_name ASC
            """,
            (period_id,)
        )
        return [dict(row) for row in cur.fetchall()]


def list_assignments_for_periods(period_ids: List[int]) -> List[Dict[str, Any]]:
    """List assignments from all requested periods with their period identity."""
    if not period_ids:
        return []

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*,
                   t.name AS team_name,
                   s.full_name AS school_name,
                   s.email AS school_email,
                   p.year AS period_year,
                   p.tw AS period_tw,
                   p.start_date AS period_start_date,
                   p.end_date AS period_end_date
            FROM monev_bos_assignments a
            JOIN monev_bos_teams t ON a.team_id = t.id
            JOIN dashboard_users s ON a.school_id = s.id
            JOIN monev_bos_periods p ON a.period_id = p.id
            WHERE a.period_id = ANY(%s)
            ORDER BY p.year DESC, p.tw ASC, s.full_name ASC
            """,
            (period_ids,),
        )
        return [dict(row) for row in cur.fetchall()]

def assign_team_to_school(team_id: int, school_id: int, period_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_assignments (team_id, school_id, period_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (school_id, period_id) DO UPDATE SET team_id = EXCLUDED.team_id
            """,
            (team_id, school_id, period_id)
        )


def copy_all_assignments_between_periods(source_period_id: int, target_period_id: int) -> Dict[str, int]:
    """Copy every source-period assignment without overwriting target assignments."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT COUNT(*) FROM monev_bos_assignments WHERE period_id = %s",
            (source_period_id,),
        )
        source_count = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO monev_bos_assignments (team_id, school_id, period_id)
            SELECT team_id, school_id, %s
            FROM monev_bos_assignments
            WHERE period_id = %s
            ON CONFLICT (school_id, period_id) DO NOTHING
            RETURNING id
            """,
            (target_period_id, source_period_id),
        )
        copied_count = len(cur.fetchall())
        return {
            "source_count": source_count,
            "copied_count": copied_count,
            "skipped_count": source_count - copied_count,
        }

def unassign_school(assignment_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_assignments WHERE id = %s", (assignment_id,))

# --- USERS ---
def get_staff_users() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, full_name, email FROM dashboard_users WHERE role = 'staff' AND account_status = 'approved' ORDER BY full_name"
        )
        return [dict(row) for row in cur.fetchall()]

def get_sekolah_users() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, full_name, email FROM dashboard_users WHERE role = 'sekolah' AND account_status = 'approved' ORDER BY full_name"
        )
        return [dict(row) for row in cur.fetchall()]

# --- REPORTS (SEKOLAH) ---
def get_school_report(school_id: int, period_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_reports WHERE school_id = %s AND period_id = %s", (school_id, period_id))
        row = cur.fetchone()
        return dict(row) if row else None

def save_school_report_receipts(school_id: int, period_id: int, bosp_amount: float, bop_amount: float) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_reports (school_id, period_id, bosp_receipt_amount, bop_receipt_amount)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (school_id, period_id) DO UPDATE 
            SET bosp_receipt_amount = EXCLUDED.bosp_receipt_amount,
                bop_receipt_amount = EXCLUDED.bop_receipt_amount,
                updated_at = NOW()
            RETURNING id
            """,
            (school_id, period_id, bosp_amount, bop_amount)
        )
        return cur.fetchone()[0]

def submit_school_report(report_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_reports SET status = 'submitted', submitted_at = NOW(), updated_at = NOW() WHERE id = %s",
            (report_id,)
        )


def get_school_claim_identity(school_user_id: int) -> Dict[str, Any]:
    """Return the canonical portal-school identity used to match claim datasets."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT u.id AS user_id,
                   COALESCE(school.npsn, '') AS npsn,
                   COALESCE(school.name, u.full_name) AS school_name
            FROM dashboard_users u
            LEFT JOIN LATERAL (
                SELECT ps.npsn, ps.name
                FROM portal_schools ps
                WHERE ps.id = u.school_id OR ps.user_id = u.id
                ORDER BY CASE WHEN ps.id = u.school_id THEN 0 ELSE 1 END, ps.id
                LIMIT 1
            ) school ON TRUE
            WHERE u.id = %s
            """,
            (school_user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else {}


def claim_bop_transactions(
    report_id: int,
    school_user_id: int,
    transactions: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Atomically add or update repository-backed BOP claim transactions."""
    inserted = 0
    updated = 0
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT r.id, r.school_id, r.status, p.year, p.tw
            FROM monev_bos_reports r
            JOIN monev_bos_periods p ON p.id = r.period_id
            WHERE r.id = %s
            FOR UPDATE OF r
            """,
            (report_id,),
        )
        report = cur.fetchone()
        if not report or int(report["school_id"]) != int(school_user_id):
            raise ValueError("Laporan sekolah tidak valid untuk klaim transaksi.")
        if (int(report["year"]), int(report["tw"])) not in SUPPORTED_BOP_CLAIM_PERIODS:
            raise ValueError("Klaim transaksi tidak tersedia untuk periode laporan ini.")
        if report["status"] not in {"draft", "needs_revision"}:
            raise ValueError("Laporan sudah tidak dapat menerima klaim transaksi.")

        for item in transactions:
            cur.execute(
                """
                SELECT id, status
                FROM monev_bos_activities
                WHERE report_id = %s AND fund_source = 'BOP' AND activity_code = %s
                FOR UPDATE
                """,
                (report_id, item["activity_code"]),
            )
            existing = cur.fetchone()
            if existing:
                if existing["status"] == "valid":
                    raise ValueError(
                        "Transaksi yang sudah berstatus Sesuai tidak dapat diklaim ulang tanpa persetujuan perubahan."
                    )
                cur.execute(
                    """
                    UPDATE monev_bos_activities
                    SET activity_name = %s,
                        account_code = %s,
                        account_code_id = (
                            SELECT id FROM monev_bos_account_codes
                            WHERE code = %s AND is_active = TRUE
                            LIMIT 1
                        ),
                        realized_amount = %s,
                        vendor_name = %s,
                        vendor_id = %s,
                        bku_number = %s,
                        item_name = %s,
                        item_specs = %s,
                        item_quantity = %s,
                        expense_type_id = %s,
                        status = 'pending',
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        item["activity_name"],
                        item["account_code"],
                        item["account_code"],
                        item["realized_amount"],
                        item.get("vendor_name"),
                        item.get("vendor_id"),
                        item["bku_number"],
                        item["item_name"],
                        item["item_specs"],
                        item["item_quantity"],
                        item.get("expense_type_id"),
                        existing["id"],
                    ),
                )
                updated += 1
                continue

            cur.execute(
                """
                INSERT INTO monev_bos_activities
                    (report_id, fund_source, activity_code, activity_name, account_code, account_code_id,
                     realized_amount, vendor_name, vendor_id, bku_number, item_name,
                     item_specs, item_quantity, expense_type_id)
                SELECT %s, 'BOP', %s, %s, %s,
                       (SELECT id FROM monev_bos_account_codes WHERE code = %s AND is_active = TRUE LIMIT 1),
                       %s, %s, %s, %s, %s, %s, %s, %s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM monev_bos_activities
                    WHERE report_id = %s AND fund_source = 'BOP' AND activity_code = %s
                )
                RETURNING id
                """,
                (
                    report_id,
                    item["activity_code"],
                    item["activity_name"],
                    item["account_code"],
                    item["account_code"],
                    item["realized_amount"],
                    item.get("vendor_name"),
                    item.get("vendor_id"),
                    item["bku_number"],
                    item["item_name"],
                    item["item_specs"],
                    item["item_quantity"],
                    item.get("expense_type_id"),
                    report_id,
                    item["activity_code"],
                ),
            )
            if cur.fetchone():
                inserted += 1

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": len(transactions) - inserted - updated,
    }

# --- ACTIVITIES ---
def get_vendor_display_name(vendor: Dict[str, Any]) -> str:
    """Prefer a person's name when the vendor name column contains a KTP number."""
    raw_name = str(vendor.get("name") or "").strip()
    owner_name = str(vendor.get("owner_name") or "").strip()
    compact_name = "".join(char for char in raw_name if char.isalnum())
    looks_like_identity = compact_name.isdigit() and len(compact_name) >= 12
    if owner_name and (vendor.get("vendor_type") == "narsum" or looks_like_identity):
        return owner_name
    return raw_name or owner_name


def list_activities(report_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, 
                   ma.name AS activity_type_name,
                   et.name AS expense_type_name,
                   v.status AS vendor_status,
                   v.vendor_type AS linked_vendor_type,
                   COALESCE(
                       CASE
                           WHEN v.vendor_type = 'narsum'
                             OR v.name ~ '^[[:space:]]*[0-9]{12,20}[[:space:]]*$'
                           THEN NULLIF(TRIM(v.owner_name), '')
                           ELSE v.name
                       END,
                       v.name,
                       a.vendor_name
                   ) AS vendor_display_name,
                   u.full_name AS auditor_name
            FROM monev_bos_activities a
            LEFT JOIN monev_bos_master_activities ma ON a.activity_type_id = ma.id
            LEFT JOIN monev_bos_expense_types et ON a.expense_type_id = et.id
            LEFT JOIN monev_bos_reports r ON a.report_id = r.id
            LEFT JOIN LATERAL (
                SELECT v.id, v.name, v.owner_name, v.status, v.vendor_type
                FROM monev_bos_vendors v
                WHERE (a.vendor_id IS NOT NULL AND v.id = a.vendor_id)
                   OR (
                       a.vendor_id IS NULL
                       AND a.vendor_name IS NOT NULL
                       AND a.vendor_name != ''
                       AND v.school_id = r.school_id
                       AND (
                           LOWER(v.name) = LOWER(a.vendor_name)
                           OR (v.vendor_type = 'narsum' AND LOWER(v.owner_name) = LOWER(a.vendor_name))
                       )
                   )
                ORDER BY v.id DESC
                LIMIT 1
            ) v ON TRUE
            LEFT JOIN LATERAL (
                SELECT l.user_id, du.full_name
                FROM monev_bos_audit_logs l
                JOIN dashboard_users du ON l.user_id = du.id
                WHERE l.activity_id = a.id
                ORDER BY l.id DESC
                LIMIT 1
            ) u ON TRUE
            WHERE a.report_id = %s
            ORDER BY a.fund_source, a.bku_number, a.activity_code
            """,
            (report_id,)
        )
        activities = [dict(row) for row in cur.fetchall()]
    attach_activity_vendors(activities)
    return activities


def find_activity_duplicate_matches_for_data(
    report_id: int,
    fund_source: str,
    data: Dict[str, Any],
    exclude_activity_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Find reused BKU numbers only in the currently opened report/fund page."""
    def normalized_text(value: Any) -> str:
        cleaned = "".join(
            char if char.isalnum() else " "
            for char in str(value or "").casefold()
        )
        return " ".join(cleaned.split())

    def normalized_identifier(value: Any) -> str:
        return "".join(char for char in str(value or "").casefold() if char.isalnum())

    incoming_name = normalized_text(data.get("activity_name"))
    incoming_bku = normalized_identifier(data.get("bku_number"))
    if not incoming_name and not incoming_bku:
        return []

    query = """
        SELECT id, activity_name, bku_number, account_code, realized_amount,
               vendor_name, item_name, status
        FROM monev_bos_activities
        WHERE report_id = %s AND fund_source = %s
    """
    params: List[Any] = [report_id, fund_source]
    if exclude_activity_id is not None:
        query += " AND id <> %s"
        params.append(exclude_activity_id)
    query += " ORDER BY bku_number, id"

    with get_cursor() as cur:
        cur.execute(query, tuple(params))
        candidates = [dict(row) for row in cur.fetchall()]

    matches = []
    for candidate in candidates:
        candidate_bku = normalized_identifier(candidate.get("bku_number"))
        if not incoming_bku or candidate_bku != incoming_bku:
            continue

        duplicate_fields = []
        if incoming_name and normalized_text(candidate.get("activity_name")) == incoming_name:
            duplicate_fields.append("Nama kegiatan")
        duplicate_fields.append("No. BKU")
        matches.append({**candidate, "duplicate_fields": duplicate_fields})
    return matches


def get_activity_vendors_by_activity_ids(activity_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    if not activity_ids:
        return {}
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT av.activity_id, av.sort_order, v.*,
                   COALESCE(ps.name, school.full_name) AS registered_school_name
            FROM monev_bos_activity_vendors av
            JOIN monev_bos_vendors v ON v.id = av.vendor_id
            LEFT JOIN dashboard_users school ON school.id = v.school_id
            LEFT JOIN LATERAL (
                SELECT candidate.name
                FROM portal_schools candidate
                WHERE candidate.user_id = school.id OR candidate.id = school.school_id
                ORDER BY CASE WHEN candidate.id = school.school_id THEN 0 ELSE 1 END, candidate.id
                LIMIT 1
            ) ps ON TRUE
            WHERE av.activity_id = ANY(%s)
            ORDER BY av.activity_id, av.sort_order, av.created_at, v.id
            """,
            (activity_ids,),
        )
        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for row in cur.fetchall():
            item = dict(row)
            grouped.setdefault(int(item["activity_id"]), []).append(item)
        return grouped


def attach_activity_vendors(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped = get_activity_vendors_by_activity_ids(
        [int(activity["id"]) for activity in activities if activity.get("id") is not None]
    )
    for activity in activities:
        vendors = grouped.get(int(activity["id"]), [])
        activity["vendors"] = vendors
        activity["unverified_vendors"] = [
            vendor for vendor in vendors if vendor.get("status") != "verified"
        ]
        activity["vendor_ids"] = [int(vendor["id"]) for vendor in vendors]
        if vendors:
            names = [get_vendor_display_name(vendor) or "Vendor / Narasumber" for vendor in vendors]
            unverified = activity["unverified_vendors"]
            activity["vendor_name"] = ", ".join(names)
            activity["vendor_display_name"] = ", ".join(names)
            activity["linked_vendor_type"] = vendors[0].get("vendor_type") or "vendor"
            activity["vendor_status"] = "pending" if unverified else "verified"
            activity["unverified_vendor_names"] = ", ".join(
                get_vendor_display_name(vendor) or "Vendor / Narasumber"
                for vendor in unverified
            )
            if unverified:
                activity["linked_vendor_type"] = unverified[0].get("vendor_type")
        elif activity.get("vendor_id"):
            activity["vendor_ids"] = [int(activity["vendor_id"])]
            activity["unverified_vendors"] = []
    return activities


def set_activity_vendors(activity_id: int, vendor_ids: List[int]) -> None:
    unique_vendor_ids = list(dict.fromkeys(int(vendor_id) for vendor_id in vendor_ids))
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM monev_bos_activity_vendors WHERE activity_id = %s",
            (activity_id,),
        )
        for sort_order, vendor_id in enumerate(unique_vendor_ids):
            cur.execute(
                """
                INSERT INTO monev_bos_activity_vendors (activity_id, vendor_id, sort_order)
                VALUES (%s, %s, %s)
                """,
                (activity_id, vendor_id, sort_order),
            )

def create_activity(report_id: int, fund_source: str, data: Dict[str, Any]) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_activities 
            (report_id, fund_source, activity_code, activity_name, account_code, account_code_id, realized_amount, vendor_name, vendor_id, bku_number, item_name, item_specs, item_quantity, activity_type_id, expense_type_id)
            VALUES (%s, %s, %s, %s, %s, (SELECT id FROM monev_bos_account_codes WHERE code = %s AND is_active = TRUE LIMIT 1), %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                report_id, fund_source, data['activity_code'], data['activity_name'], data.get('account_code'), data.get('primary_account_code') or data.get('account_code'),
                data['realized_amount'], data.get('vendor_name'), data.get('vendor_id'), data.get('bku_number'),
                data.get('item_name'), data.get('item_specs'), data.get('item_quantity'), data.get('activity_type_id'), data.get('expense_type_id')
            )
        )
        return cur.fetchone()[0]

def update_activity(activity_id: int, data: Dict[str, Any]) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_activities 
            SET activity_code = %s, activity_name = %s, account_code = %s,
                account_code_id = (SELECT id FROM monev_bos_account_codes WHERE code = %s AND is_active = TRUE LIMIT 1),
                realized_amount = %s,
                vendor_name = %s, vendor_id = %s, bku_number = %s, item_name = %s, item_specs = %s, item_quantity = %s,
                activity_type_id = %s, expense_type_id = %s
            WHERE id = %s
            """,
            (
                data['activity_code'], data['activity_name'], data.get('account_code'), data.get('primary_account_code') or data.get('account_code'), data['realized_amount'],
                data.get('vendor_name'), data.get('vendor_id'), data.get('bku_number'),
                data.get('item_name'), data.get('item_specs'), data.get('item_quantity'),
                data.get('activity_type_id'), data.get('expense_type_id'),
                activity_id
            )
        )

def get_activity_by_id(activity_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, 
                   v.status AS vendor_status,
                   v.vendor_type AS linked_vendor_type,
                   COALESCE(
                       CASE WHEN v.vendor_type = 'narsum' THEN NULLIF(v.owner_name, '') ELSE v.name END,
                       v.name,
                       a.vendor_name
                   ) AS vendor_display_name
            FROM monev_bos_activities a
            LEFT JOIN monev_bos_reports r ON a.report_id = r.id
            LEFT JOIN LATERAL (
                SELECT v.id, v.name, v.owner_name, v.status, v.vendor_type
                FROM monev_bos_vendors v
                WHERE (a.vendor_id IS NOT NULL AND v.id = a.vendor_id)
                   OR (
                       a.vendor_id IS NULL
                       AND a.vendor_name IS NOT NULL
                       AND a.vendor_name != ''
                       AND v.school_id = r.school_id
                       AND (
                           LOWER(v.name) = LOWER(a.vendor_name)
                           OR (v.vendor_type = 'narsum' AND LOWER(v.owner_name) = LOWER(a.vendor_name))
                       )
                   )
                ORDER BY v.id DESC
                LIMIT 1
            ) v ON TRUE
            WHERE a.id = %s
            """,
            (activity_id,)
        )
        row = cur.fetchone()
        activity = dict(row) if row else None
    if activity:
        attach_activity_vendors([activity])
    return activity

def delete_activity(activity_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_activities WHERE id = %s", (activity_id,))


def move_activity_fund_source(
    activity_id: int,
    report_id: int,
    target_source: str,
    changed_by: int,
) -> bool:
    """Move an editable activity between BOS and BOP while preserving its relations."""
    import json

    if target_source not in ("BOS", "BOP"):
        return False

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT *
            FROM monev_bos_activities
            WHERE id = %s AND report_id = %s
            FOR UPDATE
            """,
            (activity_id, report_id),
        )
        row = cur.fetchone()
        if not row:
            return False

        activity = dict(row)
        if activity.get("status") == "valid" or activity.get("fund_source") == target_source:
            return False

        previous_data = {
            "fund_source": activity.get("fund_source"),
            "activity_code": activity.get("activity_code"),
            "activity_name": activity.get("activity_name"),
            "realized_amount": str(activity.get("realized_amount", 0)),
            "vendor_name": activity.get("vendor_name"),
            "bku_number": activity.get("bku_number"),
            "item_name": activity.get("item_name"),
            "item_specs": activity.get("item_specs"),
            "item_quantity": activity.get("item_quantity"),
        }
        cur.execute(
            """
            INSERT INTO monev_bos_activity_history
                (activity_id, changed_by, previous_data, change_reason, activity_status_at_change)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                activity_id,
                changed_by,
                json.dumps(previous_data),
                f"Migrasi sumber dana dari {activity.get('fund_source')} ke {target_source}",
                activity.get("status"),
            ),
        )
        cur.execute(
            """
            UPDATE monev_bos_activities
            SET fund_source = %s, updated_at = NOW()
            WHERE id = %s AND report_id = %s
            """,
            (target_source, activity_id, report_id),
        )
        return cur.rowcount > 0

# --- ACTIVITY HISTORY ---
def save_activity_history(activity_id: int, changed_by: int, reason: str = None) -> None:
    """Snapshot data kegiatan saat ini sebelum diubah."""
    import json
    with get_cursor(commit=True) as cur:
        # Ambil data kegiatan saat ini
        cur.execute("SELECT * FROM monev_bos_activities WHERE id = %s", (activity_id,))
        row = cur.fetchone()
        if not row:
            return
        act = dict(row)
        previous_data = {
            "fund_source": act.get("fund_source"),
            "activity_code": act.get("activity_code"),
            "activity_name": act.get("activity_name"),
            "realized_amount": str(act.get("realized_amount", 0)),
            "vendor_name": act.get("vendor_name"),
            "bku_number": act.get("bku_number"),
            "item_name": act.get("item_name"),
            "item_specs": act.get("item_specs"),
            "item_quantity": act.get("item_quantity"),
        }
        cur.execute(
            """
            INSERT INTO monev_bos_activity_history (activity_id, changed_by, previous_data, change_reason, activity_status_at_change)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (activity_id, changed_by, json.dumps(previous_data), reason, act.get("status"))
        )

def get_activity_history(activity_id: int) -> List[Dict[str, Any]]:
    """Ambil semua riwayat perubahan data suatu kegiatan."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT h.*, u.full_name as changed_by_name, u.email as changed_by_email
            FROM monev_bos_activity_history h
            JOIN dashboard_users u ON h.changed_by = u.id
            WHERE h.activity_id = %s
            ORDER BY h.created_at DESC
            """,
            (activity_id,)
        )
        return [dict(row) for row in cur.fetchall()]


def create_edit_request(activity_id: int, requested_by: int, reason: str, requested_data: Optional[dict] = None) -> int:
    import json
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_edit_requests (activity_id, requested_by, reason, requested_data, status)
            VALUES (%s, %s, %s, %s, 'pending') RETURNING id
            """,
            (activity_id, requested_by, reason, json.dumps(requested_data) if requested_data is not None else None)
        )
        return cur.fetchone()[0]

def get_edit_request_by_activity(activity_id: int) -> Optional[Dict[str, Any]]:
    """Get latest pending edit request for an activity."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM monev_bos_edit_requests WHERE activity_id = %s AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
            (activity_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def get_pending_edit_requests_count() -> int:
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM monev_bos_edit_requests WHERE status = 'pending'")
        return cur.fetchone()[0]

def get_submitted_reports_count() -> int:
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM monev_bos_reports WHERE status = 'submitted'")
        return cur.fetchone()[0]

def list_edit_requests(status: str = None) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        if status:
            cur.execute(
                """
                SELECT er.*, a.activity_code, a.activity_name, a.fund_source, a.status as activity_status,
                       r.id as report_id, u.full_name as requester_name, u.email as requester_email,
                       s.full_name as school_name
                FROM monev_bos_edit_requests er
                JOIN monev_bos_activities a ON er.activity_id = a.id
                JOIN monev_bos_reports r ON a.report_id = r.id
                JOIN dashboard_users u ON er.requested_by = u.id
                JOIN dashboard_users s ON r.school_id = s.id
                WHERE er.status = %s
                ORDER BY er.created_at DESC
                """,
                (status,)
            )
        else:
            cur.execute(
                """
                SELECT er.*, a.activity_code, a.activity_name, a.fund_source, a.status as activity_status,
                       r.id as report_id, u.full_name as requester_name, u.email as requester_email,
                       s.full_name as school_name
                FROM monev_bos_edit_requests er
                JOIN monev_bos_activities a ON er.activity_id = a.id
                JOIN monev_bos_reports r ON a.report_id = r.id
                JOIN dashboard_users u ON er.requested_by = u.id
                JOIN dashboard_users s ON r.school_id = s.id
                ORDER BY er.created_at DESC
                """
            )
        return [dict(row) for row in cur.fetchall()]

def get_edit_request_by_id(request_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT er.*, a.activity_code, a.activity_name, a.fund_source, a.report_id,
                   u.full_name as requester_name, s.full_name as school_name
            FROM monev_bos_edit_requests er
            JOIN monev_bos_activities a ON er.activity_id = a.id
            JOIN monev_bos_reports r ON a.report_id = r.id
            JOIN dashboard_users u ON er.requested_by = u.id
            JOIN dashboard_users s ON r.school_id = s.id
            WHERE er.id = %s
            """,
            (request_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def send_reopen_notification_to_staff(activity_id: int, review_notes: str = None) -> None:
    """Kirim notifikasi in-app ke Staff Verifikator bahwa kegiatan dibuka untuk verifikasi ulang."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT a.id as activity_id, a.activity_code, a.activity_name, a.fund_source,
                       r.id as report_id, r.school_id, r.period_id, s.full_name as school_name
                FROM monev_bos_activities a
                JOIN monev_bos_reports r ON a.report_id = r.id
                JOIN dashboard_users s ON r.school_id = s.id
                WHERE a.id = %s
                """,
                (activity_id,)
            )
            act = cur.fetchone()
            if not act:
                return
            act = dict(act)

            # 1. Staff dari tim penugasan sekolah ini
            cur.execute(
                """
                SELECT DISTINCT tm.staff_id
                FROM monev_bos_assignments ass
                JOIN monev_bos_team_members tm ON ass.team_id = tm.team_id
                WHERE ass.school_id = %s AND ass.period_id = %s
                """,
                (act['school_id'], act['period_id'])
            )
            team_staff = [r[0] for r in cur.fetchall() if r[0]]

            # 2. Staff yang sebelumnya pernah melakukan verifikasi pada laporan ini
            cur.execute(
                """
                SELECT DISTINCT l.user_id
                FROM monev_bos_audit_logs l
                JOIN dashboard_users u ON l.user_id = u.id
                WHERE l.report_id = %s AND u.role IN ('staff', 'admin')
                """,
                (act['report_id'],)
            )
            previous_auditors = [r[0] for r in cur.fetchall() if r[0]]

            staff_ids = list(set(team_staff + previous_auditors))

            # Jika tidak ada penugasan tim spesifik maupun verifikator terdahulu, kirim ke semua user role 'staff'
            if not staff_ids:
                cur.execute("SELECT id FROM dashboard_users WHERE role = 'staff' AND account_status = 'approved'")
                staff_ids = [r[0] for r in cur.fetchall() if r[0]]

            title = f"Verifikasi Ulang: {act['activity_code']}"
            message = f"Kegiatan {act['activity_code']} ({act['school_name']}) telah dibuka kembali oleh admin untuk revisi. Silakan lakukan verifikasi ulang setelah sekolah memperbarui data."
            if review_notes:
                message += f" Catatan admin: {review_notes}"
            link = f"/monev-bos/staff/verifikasi/{act['report_id']}"

            for staff_id in staff_ids:
                cur.execute(
                    """
                    INSERT INTO notifications (user_id, category, title, message, status, link, reference_table, reference_id, created_at)
                    VALUES (%s, 'monev_bos', %s, %s, 'unread', %s, 'monev_bos_activities', %s, NOW())
                    """,
                    (staff_id, title, message, link, activity_id)
                )
    except Exception as e:
        print(f"Error sending staff notification: {e}")

def send_revised_activity_notification_to_staff(activity_id: int) -> None:
    """Kirim notifikasi in-app ke Staff Verifikator bahwa revisi kegiatan siap diverifikasi ulang."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT a.id as activity_id, a.activity_code, a.activity_name, a.fund_source,
                       r.id as report_id, r.school_id, r.period_id, s.full_name as school_name
                FROM monev_bos_activities a
                JOIN monev_bos_reports r ON a.report_id = r.id
                JOIN dashboard_users s ON r.school_id = s.id
                WHERE a.id = %s
                """,
                (activity_id,)
            )
            act = cur.fetchone()
            if not act:
                return
            act = dict(act)

            # 1. Staff dari tim penugasan sekolah ini
            cur.execute(
                """
                SELECT DISTINCT tm.staff_id
                FROM monev_bos_assignments ass
                JOIN monev_bos_team_members tm ON ass.team_id = tm.team_id
                WHERE ass.school_id = %s AND ass.period_id = %s
                """,
                (act['school_id'], act['period_id'])
            )
            team_staff = [r[0] for r in cur.fetchall() if r[0]]

            # 2. Staff yang sebelumnya pernah melakukan verifikasi pada laporan ini
            cur.execute(
                """
                SELECT DISTINCT l.user_id
                FROM monev_bos_audit_logs l
                JOIN dashboard_users u ON l.user_id = u.id
                WHERE l.report_id = %s AND u.role IN ('staff', 'admin')
                """,
                (act['report_id'],)
            )
            previous_auditors = [r[0] for r in cur.fetchall() if r[0]]

            staff_ids = list(set(team_staff + previous_auditors))

            # Jika tidak ada penugasan tim spesifik maupun verifikator terdahulu, kirim ke semua user role 'staff'
            if not staff_ids:
                cur.execute("SELECT id FROM dashboard_users WHERE role = 'staff' AND account_status = 'approved'")
                staff_ids = [r[0] for r in cur.fetchall() if r[0]]

            title = f"Perbaikan Kegiatan: {act['activity_code']}"
            message = f"{act['school_name']} telah memperbarui data kegiatan {act['activity_code']} ({act['activity_name']}). Silakan lakukan verifikasi ulang."
            link = f"/monev-bos/staff/verifikasi/{act['report_id']}"

            for staff_id in staff_ids:
                cur.execute(
                    """
                    INSERT INTO notifications (user_id, category, title, message, status, link, reference_table, reference_id, created_at)
                    VALUES (%s, 'monev_bos', %s, %s, 'unread', %s, 'monev_bos_activities', %s, NOW())
                    """,
                    (staff_id, title, message, link, activity_id)
                )
    except Exception as e:
        print(f"Error sending staff revised activity notification: {e}")

def approve_edit_request(request_id: int, reviewed_by: int, review_notes: str = None) -> None:
    """Setujui pengajuan reopen edit: simpan history data saat ini & ubah status kegiatan ke 'invalid' (Revisi) agar sekolah dapat mengedit."""
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM monev_bos_edit_requests WHERE id = %s", (request_id,))
        req = cur.fetchone()
        if not req:
            return
        req = dict(req)
        activity_id = req['activity_id']

        # 1. Simpan snapshot data kegiatan saat ini ke history sebelum kunci dibuka
        save_activity_history(activity_id, req['requested_by'], reason=f"Reopen oleh Admin (Alasan Sekolah: {req.get('reason') or '-'})")

        # 2. Ubah status kegiatan menjadi 'invalid' (Revisi) agar sekolah bisa edit langsung
        cur.execute(
            """
            UPDATE monev_bos_activities
            SET status = 'invalid', audit_notes = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (review_notes or "Kunci edit dibuka oleh admin. Silakan perbarui data kegiatan.", activity_id)
        )

        # 3. Tandai pengajuan sebagai approved
        cur.execute(
            "UPDATE monev_bos_edit_requests SET status = 'approved', reviewed_by = %s, review_notes = %s, updated_at = NOW() WHERE id = %s",
            (reviewed_by, review_notes, request_id)
        )

    # 4. Kirim notifikasi in-app ke Staff Verifikator yang bertugas
    send_reopen_notification_to_staff(activity_id, review_notes)

def reject_edit_request(request_id: int, reviewed_by: int, review_notes: str = None) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_edit_requests SET status = 'rejected', reviewed_by = %s, review_notes = %s, updated_at = NOW() WHERE id = %s",
            (reviewed_by, review_notes, request_id)
        )

def cancel_edit_request(activity_id: int) -> None:
    """Cancel any pending edit requests for an activity (e.g., when school re-edits)."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_edit_requests SET status = 'rejected', updated_at = NOW() WHERE activity_id = %s AND status = 'pending'",
            (activity_id,)
        )



# --- ACTIVITY DOCS ---
def get_activity_docs(activity_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM monev_bos_activity_docs WHERE activity_id = %s ORDER BY created_at, id",
            (activity_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def count_valid_field_photos(activity_id: int) -> int:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM monev_bos_activity_docs
            WHERE activity_id = %s
              AND doc_type = 'field_photo'
              AND is_audit_valid = TRUE
            """,
            (activity_id,),
        )
        return int(cur.fetchone()[0])

def add_activity_doc(activity_id: int, doc_type: str, file_path: str, file_size: int, user_id: int) -> int:
    with get_cursor(commit=True) as cur:
        # Dokumen utama hanya satu. Foto sekolah/staff dan bukti fisik boleh lebih dari satu.
        if doc_type in ['transfer', 'invoice']:
            cur.execute("DELETE FROM monev_bos_activity_docs WHERE activity_id = %s AND doc_type = %s", (activity_id, doc_type))
        elif doc_type == 'field_photo':
            cur.execute(
                """
                SELECT COUNT(*)
                FROM monev_bos_activity_docs
                WHERE activity_id = %s
                  AND doc_type = 'field_photo'
                  AND is_audit_valid = TRUE
                """,
                (activity_id,),
            )
            if int(cur.fetchone()[0]) >= 3:
                raise ValueError("Maksimal 3 Foto Kegiatan/Barang yang sah per kegiatan.")
            
        cur.execute(
            """
            INSERT INTO monev_bos_activity_docs (activity_id, doc_type, file_path, file_size, uploaded_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (activity_id, doc_type, file_path, file_size, user_id)
        )
        return int(cur.fetchone()[0])


def delete_staff_live_photo(
    activity_id: int,
    doc_id: int,
    uploaded_by: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Delete a staff live photo, optionally limited to the staff member who uploaded it."""
    query = """
        DELETE FROM monev_bos_activity_docs
        WHERE id = %s
          AND activity_id = %s
          AND doc_type = 'live_photo'
    """
    params: List[Any] = [doc_id, activity_id]
    if uploaded_by is not None:
        query += " AND uploaded_by = %s"
        params.append(uploaded_by)
    query += " RETURNING *"

    with get_cursor(commit=True) as cur:
        cur.execute(query, tuple(params))
        row = cur.fetchone()
        return dict(row) if row else None


def set_field_photo_audit_validity(
    activity_id: int,
    doc_id: int,
    is_valid: bool,
    user_id: int,
    notes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Anulir atau sahkan kembali satu foto sekolah tanpa menghapus bukti aslinya."""
    with get_cursor(commit=True) as cur:
        if is_valid:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM monev_bos_activity_docs
                WHERE activity_id = %s
                  AND doc_type = 'field_photo'
                  AND is_audit_valid = TRUE
                  AND id <> %s
                """,
                (activity_id, doc_id),
            )
            if int(cur.fetchone()[0]) >= 3:
                raise ValueError("Foto tidak dapat disahkan kembali karena sudah ada 3 foto sah.")

        cur.execute(
            """
            UPDATE monev_bos_activity_docs
            SET is_audit_valid = %s,
                photo_audit_notes = %s,
                photo_audited_by = %s,
                photo_audited_at = NOW()
            WHERE id = %s
              AND activity_id = %s
              AND doc_type = 'field_photo'
            RETURNING *
            """,
            (is_valid, notes or None, user_id, doc_id, activity_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None
# --- STAFF TEAMS & MEMBERS ---
def get_teams_for_staff(staff_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT t.*, 
                   (t.leader_id = %s) as is_leader
            FROM monev_bos_teams t
            LEFT JOIN monev_bos_team_members tm ON t.id = tm.team_id
            WHERE t.leader_id = %s OR tm.staff_id = %s
            GROUP BY t.id
            ORDER BY t.name ASC
            """,
            (staff_id, staff_id, staff_id)
        )
        return [dict(row) for row in cur.fetchall()]

def get_team_members(team_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.full_name, u.email, u.role,
                   (t.leader_id = u.id) as is_leader
            FROM monev_bos_teams t
            JOIN dashboard_users u ON (u.id = t.leader_id OR u.id IN (
                SELECT staff_id FROM monev_bos_team_members WHERE team_id = t.id
            ))
            WHERE t.id = %s
            ORDER BY (t.leader_id = u.id) DESC, u.full_name ASC
            """,
            (team_id,)
        )
        return [dict(row) for row in cur.fetchall()]

def add_team_member(team_id: int, staff_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO monev_bos_team_members (team_id, staff_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (team_id, staff_id)
        )

def remove_team_member(team_id: int, staff_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM monev_bos_team_members WHERE team_id = %s AND staff_id = %s",
            (team_id, staff_id)
        )

# --- VERIFIKASI (STAFF) ---
def get_schools_for_team(team_id: int, period_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.id as school_id, s.full_name as school_name, s.email as school_email,
                   COALESCE(
                       NULLIF(TRIM(s.whatsapp_number), ''),
                       NULLIF(TRIM(s.phone), ''),
                       NULLIF(TRIM(ps.metadata->>'operator_phone'), ''),
                       NULLIF(TRIM(ps.metadata->>'phone'), ''),
                       NULLIF(TRIM(ps.metadata->>'coordinator_phone'), '')
                   ) as school_phone,
                   r.id as report_id, r.status as report_status,
                   r.bosp_receipt_amount, r.bop_receipt_amount,
                   (SELECT COUNT(*) FROM monev_bos_activities a WHERE a.report_id = r.id) as total_activities,
                   (SELECT COUNT(*) FROM monev_bos_activities a WHERE a.report_id = r.id AND a.status IN ('valid', 'invalid')) as audited_activities
            FROM monev_bos_assignments a
            JOIN dashboard_users s ON a.school_id = s.id
            LEFT JOIN portal_schools ps ON ps.user_id = s.id
            LEFT JOIN monev_bos_reports r ON r.school_id = s.id AND r.period_id = a.period_id
            WHERE a.team_id = %s AND a.period_id = %s
            ORDER BY s.full_name ASC
            """,
            (team_id, period_id)
        )
        rows = [dict(row) for row in cur.fetchall()]
        from urllib.parse import quote
        for row in rows:
            phone = row.get("school_phone")
            if phone:
                clean = "".join(c for c in str(phone) if c.isdigit())
                if clean.startswith("0"):
                    clean = "62" + clean[1:]
                elif not clean.startswith("62") and clean:
                    clean = "62" + clean
                msg = f"Halo Operator {row['school_name']}, kami dari Tim Verifikator MONEV BOS/BOP Sudin Pendidikan..."
                row["wa_url"] = f"https://wa.me/{clean}?text={quote(msg)}"
            else:
                row["wa_url"] = None
        return rows

def get_auditor_staff_wa_for_report(report_id: int, school_id: int, period_id: int, activity_id: Optional[int] = None) -> Dict[str, Any]:
    """Retrieve the assigned verifier's name and WhatsApp number for this activity or report."""
    with get_cursor() as cur:
        staff_row = None
        # 1. Staff who verified this specific activity
        if activity_id:
            cur.execute(
                """
                SELECT u.id, u.full_name, COALESCE(u.whatsapp_number, u.phone) as phone
                FROM monev_bos_audit_logs l
                JOIN dashboard_users u ON l.user_id = u.id
                WHERE l.activity_id = %s AND u.role IN ('staff', 'admin')
                  AND COALESCE(u.whatsapp_number, u.phone) IS NOT NULL
                  AND COALESCE(u.whatsapp_number, u.phone) <> ''
                ORDER BY l.id DESC
                LIMIT 1
                """,
                (activity_id,)
            )
            staff_row = cur.fetchone()

        # 2. Staff who logged verification actions for this report
        if not staff_row:
            cur.execute(
                """
                SELECT u.id, u.full_name, COALESCE(u.whatsapp_number, u.phone) as phone
                FROM monev_bos_audit_logs l
                JOIN dashboard_users u ON l.user_id = u.id
                WHERE l.report_id = %s AND u.role IN ('staff', 'admin')
                  AND COALESCE(u.whatsapp_number, u.phone) IS NOT NULL
                  AND COALESCE(u.whatsapp_number, u.phone) <> ''
                ORDER BY l.id DESC
                LIMIT 1
                """,
                (report_id,)
            )
            staff_row = cur.fetchone()

        # 3. If not found in the history, check team assignment
        if not staff_row:
            cur.execute(
                """
                SELECT u.id, u.full_name, COALESCE(u.whatsapp_number, u.phone) as phone
                FROM monev_bos_assignments ass
                JOIN monev_bos_team_members tm ON ass.team_id = tm.team_id
                JOIN dashboard_users u ON tm.staff_id = u.id
                WHERE ass.school_id = %s AND ass.period_id = %s
                  AND COALESCE(u.whatsapp_number, u.phone) IS NOT NULL
                  AND COALESCE(u.whatsapp_number, u.phone) <> ''
                LIMIT 1
                """,
                (school_id, period_id)
            )
            staff_row = cur.fetchone()

        if not staff_row:
            return {}

        s = dict(staff_row)
        phone_raw = s.get("phone") or ""
        phone_formatted = "".join([c for c in str(phone_raw) if c.isdigit()])
        if phone_formatted.startswith("0"):
            phone_formatted = "62" + phone_formatted[1:]

        return {
            "staff_id": s.get("id"),
            "staff_name": s.get("full_name") or "Staff Verifikator",
            "staff_phone": phone_formatted
        }

def get_school_kecamatan_and_admin_wa(school_user_id: int) -> Dict[str, Any]:
    """Retrieves school kecamatan name and primary admin/coordinator WA number for that kecamatan from portal_kontak table."""
    with get_cursor() as cur:
        # Join portal_schools specifically on s.id = u.school_id
        cur.execute(
            """
            SELECT u.id as user_id, u.full_name as school_name, k.id as kecamatan_id, k.name as kecamatan_name
            FROM dashboard_users u
            LEFT JOIN portal_schools s ON s.id = u.school_id
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            WHERE u.id = %s
            """,
            (school_user_id,)
        )
        row = cur.fetchone()
        school_info = dict(row) if row and row.get("kecamatan_name") else {}

        # Fallback if u.school_id is null or has no kecamatan
        if not school_info.get("kecamatan_name"):
            cur.execute(
                """
                SELECT u.id as user_id, u.full_name as school_name, k.id as kecamatan_id, k.name as kecamatan_name
                FROM dashboard_users u
                LEFT JOIN portal_schools s ON s.id = u.id
                LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
                LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
                WHERE u.id = %s
                """,
                (school_user_id,)
            )
            row2 = cur.fetchone()
            if row2 and row2.get("kecamatan_name"):
                school_info = dict(row2)

        kec_id = school_info.get("kecamatan_id")
        kec_name = (school_info.get("kecamatan_name") or "Wilayah").strip()

        # 1. First priority: Check portal_kontak table (Kontak Per Wilayah /portal/kontak)
        admin_name = "Admin Wilayah"
        phone_raw = ""
        admin_id = None

        cur.execute(
            """
            SELECT * FROM portal_kontak WHERE UPPER(TRIM(wilayah)) = UPPER(TRIM(%s)) LIMIT 1
            """,
            (kec_name,)
        )
        pk = cur.fetchone()
        if pk:
            pk = dict(pk)
            if pk.get("kontak_1_active") and pk.get("kontak"):
                admin_name = pk.get("nama") or "Admin Wilayah"
                phone_raw = pk.get("kontak")
            elif pk.get("kontak_2_active") and pk.get("kontak_2"):
                admin_name = pk.get("nama_2") or "Admin Wilayah"
                phone_raw = pk.get("kontak_2")
            elif pk.get("kontak"):
                admin_name = pk.get("nama") or "Admin Wilayah"
                phone_raw = pk.get("kontak")

        # 2. Fallback priority: Check user_kecamatan / dashboard_users table
        if not phone_raw:
            cur.execute(
                """
                SELECT u.id, u.full_name, u.role, COALESCE(u.whatsapp_number, u.phone) as phone
                FROM dashboard_users u
                LEFT JOIN user_kecamatan uk ON u.id = uk.user_id
                WHERE u.account_status = 'approved'
                  AND u.role IN ('coordinator', 'admin', 'staff')
                  AND COALESCE(u.whatsapp_number, u.phone) IS NOT NULL
                  AND COALESCE(u.whatsapp_number, u.phone) <> ''
                  AND (uk.kecamatan_id = %s OR u.kecamatan_id = %s OR u.requested_kecamatan = %s OR LOWER(u.kecamatan) = LOWER(%s))
                ORDER BY CASE WHEN u.role = 'coordinator' THEN 1 WHEN u.role = 'staff' THEN 2 ELSE 3 END
                LIMIT 1
                """,
                (kec_id, kec_id, kec_id, kec_name)
            )
            admin_row = cur.fetchone()
            if admin_row:
                admin_info = dict(admin_row)
                admin_id = admin_info.get("id")
                admin_name = admin_info.get("full_name") or "Admin Wilayah"
                phone_raw = admin_info.get("phone") or ""

        phone_formatted = "".join([c for c in str(phone_raw) if c.isdigit()])
        if phone_formatted.startswith("0"):
            phone_formatted = "62" + phone_formatted[1:]

        return {
            "school_name": school_info.get("school_name") or "Sekolah",
            "kecamatan_id": kec_id,
            "kecamatan_name": kec_name,
            "admin_id": admin_id,
            "admin_name": admin_name,
            "admin_phone": phone_formatted,
        }

def get_report_by_id(report_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT r.*,
                   s.full_name AS school_name,
                   p.year,
                   p.tw,
                   p.start_date AS period_start_date,
                   p.end_date AS period_end_date,
                   p.is_active AS period_is_active
            FROM monev_bos_reports r
            JOIN dashboard_users s ON r.school_id = s.id
            JOIN monev_bos_periods p ON p.id = r.period_id
            WHERE r.id = %s
            """,
            (report_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def update_activity_audit(activity_id: int, status: str, notes: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_activities SET status = %s, audit_notes = %s, updated_at = NOW() WHERE id = %s",
            (status, notes, activity_id)
        )

def update_activity_audit_notes(activity_id: int, notes: str) -> None:
    """Persist draft verification notes without changing the activity status."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_activities SET audit_notes = %s, updated_at = NOW() WHERE id = %s",
            (notes, activity_id)
        )

def save_checklist_result(activity_id: int, checklist_id: int, status: str, notes: str, user_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_checklist_results (activity_id, checklist_id, status, notes, created_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (activity_id, checklist_id) DO UPDATE 
            SET status = EXCLUDED.status, notes = EXCLUDED.notes, created_by = EXCLUDED.created_by, updated_at = NOW()
            """,
            (activity_id, checklist_id, status, notes, user_id)
        )

def get_activity_checklist_results(activity_id: int) -> Dict[int, Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_checklist_results WHERE activity_id = %s", (activity_id,))
        return {row['checklist_id']: dict(row) for row in cur.fetchall()}


def get_checklist_results_by_activity_ids(activity_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Return saved checklist results, including results from inactive checklist masters."""
    if not activity_ids:
        return {}

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT cr.activity_id,
                   cr.checklist_id,
                   cr.status,
                   cr.notes,
                   c.name AS checklist_name
            FROM monev_bos_checklist_results cr
            JOIN monev_bos_checklists c ON c.id = cr.checklist_id
            WHERE cr.activity_id = ANY(%s)
            ORDER BY cr.activity_id, c.sort_order, c.id
            """,
            (activity_ids,),
        )
        results_by_activity: Dict[int, List[Dict[str, Any]]] = {}
        for row in cur.fetchall():
            result = dict(row)
            results_by_activity.setdefault(int(result["activity_id"]), []).append(result)
        return results_by_activity

def add_audit_log(report_id: int, activity_id: Optional[int], user_id: int, action: str, details: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_audit_logs (report_id, activity_id, user_id, action, details)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (report_id, activity_id, user_id, action, details)
        )


# --- MASTER NAMA KEGIATAN ---
def list_master_activities(
    include_inactive: bool = False,
    fund_source: Optional[str] = None,
    search_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        query = "SELECT * FROM monev_bos_master_activities WHERE 1=1"
        params: List[Any] = []
        if not include_inactive:
            query += " AND is_active = TRUE"
        if fund_source and fund_source != "ALL":
            query += " AND (fund_source = %s OR fund_source = 'ALL')"
            params.append(fund_source)
        if search_query:
            query += " AND (name ILIKE %s OR COALESCE(code_prefix, '') ILIKE %s)"
            search_pattern = f"%{search_query.strip()}%"
            params.extend([search_pattern, search_pattern])
        query += " ORDER BY name ASC"
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

def check_master_activity_exists(name: str, exclude_id: Optional[int] = None) -> bool:
    init_activities_table()
    with get_cursor() as cur:
        if exclude_id is not None:
            cur.execute("SELECT 1 FROM monev_bos_master_activities WHERE LOWER(name) = LOWER(%s) AND id != %s", (name, exclude_id))
        else:
            cur.execute("SELECT 1 FROM monev_bos_master_activities WHERE LOWER(name) = LOWER(%s)", (name,))
        return bool(cur.fetchone())


def create_master_activity(name: str, code_prefix: Optional[str] = None, fund_source: str = "ALL") -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_master_activities (name, code_prefix, fund_source)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (name.strip(), (code_prefix or "").strip() or None, fund_source)
        )
        return cur.fetchone()[0]

def update_master_activity(master_id: int, name: str, code_prefix: Optional[str], fund_source: str, is_active: bool) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_master_activities
            SET name = %s, code_prefix = %s, fund_source = %s, is_active = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (name.strip(), (code_prefix or "").strip() or None, fund_source, is_active, master_id)
        )

def delete_master_activity(master_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_master_activities WHERE id = %s", (master_id,))

def seed_default_master_activities() -> None:
    defaults = [
        ("Pemeliharaan Sarana & Alat Pelajaran Komputer", "01.02", "ALL"),
        ("Penyediaan Bahan Kebersihan & Kebutuhan Sanitasi", "01.03", "ALL"),
        ("Pembelian Alat Tulis Kantor", "01.01", "ALL"),
        ("Honorarium Guru Honorer / Tenaga Kependidikan", "02.01", "ALL"),
        ("Langganan Daya dan Jasa (Listrik/Air/Internet)", "03.01", "ALL"),
        ("Pemeliharaan Bangunan Sekolah & Ruang Kelas", "01.04", "ALL"),
        ("Pengadaan Modul & Bahan Ajar Siswa", "04.01", "ALL"),
        ("Kegiatan Asesmen & Evaluasi Pembelajaran", "05.01", "ALL"),
        ("Pengembangan Perpustakaan & Literasi", "06.01", "ALL"),
        ("Kegiatan Ekstrakurikuler & Lomba Siswa", "07.01", "ALL"),
    ]
    for name, code, fs in defaults:
        try:
            create_master_activity(name, code, fs)
        except Exception:
            pass

def get_audit_logs(report_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.*, u.full_name as user_name, a.activity_name
            FROM monev_bos_audit_logs l
            JOIN dashboard_users u ON l.user_id = u.id
            LEFT JOIN monev_bos_activities a ON l.activity_id = a.id
            WHERE l.report_id = %s
            ORDER BY l.created_at DESC
            """,
            (report_id,)
        )
        logs = [dict(row) for row in cur.fetchall()]
        for log in logs:
            log["details"] = _verification_display_text(log.get("details"))
        return logs


# --- VENDOR MANAGEMENT QUERIES ---

def list_school_vendors(school_id: int, status_filter: str = None, search_query: str = None) -> List[Dict[str, Any]]:
    """List vendors registered by a specific school."""
    query = """
        SELECT v.*, u.full_name AS verified_by_name
        FROM monev_bos_vendors v
        LEFT JOIN dashboard_users u ON u.id = v.verified_by
        WHERE v.school_id = %s
    """
    params = [school_id]
    if status_filter:
        query += " AND v.status = %s"
        params.append(status_filter)
    if search_query:
        query += " AND (v.name ILIKE %s OR v.npwp ILIKE %s OR v.phone ILIKE %s OR v.owner_name ILIKE %s OR v.bank_name ILIKE %s OR v.address ILIKE %s)"
        pattern = f"%{search_query.strip()}%"
        params.extend([pattern] * 6)
    query += " ORDER BY v.vendor_type, v.created_at DESC"

    with get_cursor() as cur:
        cur.execute(query, tuple(params))
        return [dict(row) for row in cur.fetchall()]


def list_all_vendors_for_admin(
    status_filter: Optional[str] = None,
    search_query: Optional[str] = None,
    vendor_type_filter: Optional[str] = None,
    school_id_filter: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List all vendor registration requests for admin/staff verification."""
    query = """
        SELECT v.*, 
               COALESCE(ps.name, u_school.full_name) AS school_name, 
               ps.npsn, 
               u.full_name AS verified_by_name
        FROM monev_bos_vendors v
        JOIN dashboard_users u_school ON u_school.id = v.school_id
        LEFT JOIN portal_schools ps ON ps.id = u_school.school_id
        LEFT JOIN dashboard_users u ON u.id = v.verified_by
        WHERE 1=1
    """
    params = []
    if status_filter:
        query += " AND v.status = %s"
        params.append(status_filter)
    if vendor_type_filter:
        query += " AND v.vendor_type = %s"
        params.append(vendor_type_filter)
    if school_id_filter:
        query += " AND v.school_id = %s"
        params.append(school_id_filter)
    if search_query:
        query += " AND (v.name ILIKE %s OR v.npwp ILIKE %s OR v.phone ILIKE %s OR v.owner_name ILIKE %s OR COALESCE(ps.name, u_school.full_name) ILIKE %s)"
        pattern = f"%{search_query.strip()}%"
        params.extend([pattern] * 5)
    query += " ORDER BY v.created_at DESC"

    with get_cursor() as cur:
        cur.execute(query, tuple(params))
        return [dict(row) for row in cur.fetchall()]


def attach_vendor_action_history(vendors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach chronological verification/rejection actions to vendor rows."""
    for vendor in vendors:
        vendor["action_history"] = []
    vendor_ids = [int(vendor["id"]) for vendor in vendors if vendor.get("id") is not None]
    if not vendor_ids:
        return vendors

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT log.id,
                   log.target_id AS vendor_id,
                   log.action,
                   log.metadata,
                   log.created_at,
                   COALESCE(actor.full_name, actor.email, 'Pengguna tidak tersedia') AS actor_name
            FROM dashboard_admin_action_logs log
            LEFT JOIN dashboard_users actor ON actor.id = log.user_id
            WHERE log.feature_key = 'monev_bos'
              AND log.target_type = 'MONEV_VENDOR'
              AND log.target_id = ANY(%s)
              AND log.action IN ('VERIFY_APPROVE', 'VERIFY_REJECT')
            ORDER BY log.created_at DESC, log.id DESC
            """,
            (vendor_ids,),
        )
        history_by_vendor: Dict[int, List[Dict[str, Any]]] = {}
        for row in cur.fetchall():
            entry = dict(row)
            history_by_vendor.setdefault(int(entry["vendor_id"]), []).append(entry)

    for vendor in vendors:
        if vendor.get("id") is not None:
            vendor["action_history"] = history_by_vendor.get(int(vendor["id"]), [])
    return vendors


def list_vendor_schools_for_admin() -> List[Dict[str, Any]]:
    """Return schools that have at least one vendor or speaker registration."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT v.school_id AS id,
                   COALESCE(ps.name, u_school.full_name) AS school_name,
                   ps.npsn
            FROM monev_bos_vendors v
            JOIN dashboard_users u_school ON u_school.id = v.school_id
            LEFT JOIN portal_schools ps ON ps.id = u_school.school_id
            ORDER BY school_name ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def _vendor_duplicate_signatures(vendor: Dict[str, Any]) -> List[tuple]:
    """Build normalized identity fields used to flag likely duplicate registrations."""
    vendor_type = vendor.get("vendor_type") or "vendor"

    def normalized_text(value: Any) -> str:
        cleaned = "".join(
            char if char.isalnum() else " "
            for char in str(value or "").casefold()
        )
        return " ".join(cleaned.split())

    def normalized_identifier(value: Any) -> str:
        return "".join(char for char in str(value or "").casefold() if char.isalnum())

    signatures = []
    if vendor_type == "narsum":
        signatures.extend([
            ("Nama narasumber", normalized_text(vendor.get("owner_name"))),
            ("No. KTP", normalized_identifier(vendor.get("name"))),
        ])
    else:
        signatures.append(("Nama vendor", normalized_text(vendor.get("name"))))
    signatures.append(("NPWP", normalized_identifier(vendor.get("npwp"))))
    return [(label, value) for label, value in signatures if value]


def attach_vendor_duplicate_matches(vendors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach registrations sharing a normalized name, identity number, or NPWP."""
    for vendor in vendors:
        vendor["duplicate_matches"] = []
        vendor["verified_duplicate_matches"] = []
    if not vendors:
        return vendors

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT v.*,
                   COALESCE(ps.name, u_school.full_name) AS school_name,
                   ps.npsn
            FROM monev_bos_vendors v
            JOIN dashboard_users u_school ON u_school.id = v.school_id
            LEFT JOIN portal_schools ps ON ps.id = u_school.school_id
            ORDER BY v.id DESC
            """
        )
        candidates = [dict(row) for row in cur.fetchall()]

    signature_index: Dict[tuple, List[Dict[str, Any]]] = {}
    for candidate in candidates:
        candidate_type = candidate.get("vendor_type") or "vendor"
        for label, value in _vendor_duplicate_signatures(candidate):
            signature_index.setdefault((candidate_type, label, value), []).append(candidate)

    for vendor in vendors:
        vendor_id = int(vendor["id"])
        vendor_type = vendor.get("vendor_type") or "vendor"
        matches: Dict[int, Dict[str, Any]] = {}
        for label, value in _vendor_duplicate_signatures(vendor):
            for candidate in signature_index.get((vendor_type, label, value), []):
                candidate_id = int(candidate["id"])
                if candidate_id == vendor_id:
                    continue
                match = matches.setdefault(candidate_id, dict(candidate, duplicate_fields=[]))
                if label not in match["duplicate_fields"]:
                    match["duplicate_fields"].append(label)
        vendor["duplicate_matches"] = sorted(
            matches.values(),
            key=lambda item: (item.get("status") != "verified", -int(item["id"])),
        )
        vendor["verified_duplicate_matches"] = [
            match for match in vendor["duplicate_matches"]
            if match.get("status") == "verified"
        ]
    return vendors


def filter_verified_duplicate_vendors(vendors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep verified registrations that also match another verified registration."""
    results = []
    for vendor in vendors:
        verified_matches = [
            match
            for match in vendor.get("duplicate_matches", [])
            if match.get("status") == "verified"
        ]
        vendor["duplicate_matches"] = verified_matches
        if vendor.get("status") == "verified" and verified_matches:
            results.append(vendor)
    return results


def attach_vendor_missing_fields(vendors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach human-readable missing fields for verified-data completeness scans."""
    for vendor in vendors:
        missing_fields = []
        vendor_type = vendor.get("vendor_type") or "vendor"

        required_fields = [
            ("name", "No. KTP" if vendor_type == "narsum" else "Nama vendor"),
            ("npwp", "NPWP"),
            ("phone", "No. telepon/WhatsApp"),
            ("address", "Alamat"),
            ("owner_name", "Nama narasumber/instruktur" if vendor_type == "narsum" else "Penanggung jawab/pemilik"),
            ("bank_name", "Nama bank"),
        ]
        for field, label in required_fields:
            if not str(vendor.get(field) or "").strip():
                missing_fields.append(label)

        account_type = str(vendor.get("bank_account_type") or "rekening").strip().lower()
        if account_type != "va" and not str(vendor.get("bank_account") or "").strip():
            missing_fields.append("No. rekening")

        vendor["missing_fields"] = missing_fields
    return vendors


def filter_verified_incomplete_vendors(vendors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep verified vendors that still have one or more empty required fields."""
    attach_vendor_missing_fields(vendors)
    return [
        vendor for vendor in vendors
        if vendor.get("status") == "verified" and vendor.get("missing_fields")
    ]


def find_vendor_duplicate_matches(vendor_id: int) -> List[Dict[str, Any]]:
    vendor = get_vendor_by_id(vendor_id)
    if not vendor:
        return []
    attach_vendor_duplicate_matches([vendor])
    return vendor["duplicate_matches"]


def find_vendor_duplicate_matches_for_data(
    data: Dict[str, Any],
    exclude_vendor_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Find matching registrations before a school creates or updates a vendor."""
    vendor = dict(data)
    # Reuse the same matching rules used during admin verification.  On edit,
    # using the current id prevents the record from matching its stored version.
    vendor["id"] = exclude_vendor_id or 0
    attach_vendor_duplicate_matches([vendor])
    return vendor["duplicate_matches"]


def get_report_selectable_vendors(school_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get selectable vendors, prioritizing the current school then verified entries."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT v.id, v.school_id, v.name, v.npwp, v.phone, v.address,
                   v.owner_name, v.bank_name, v.bank_account, v.status, v.vendor_type,
                   CASE
                       WHEN NULLIF(TRIM(v.owner_name), '') IS NOT NULL
                        AND (v.vendor_type = 'narsum'
                             OR v.name ~ '^[[:space:]]*[0-9]{12,20}[[:space:]]*$')
                       THEN TRIM(v.owner_name)
                       ELSE v.name
                   END AS display_name,
                   (v.school_id = %s) AS is_own_school,
                   COALESCE(ps.name, u_school.full_name) AS registered_school_name
            FROM monev_bos_vendors v
            JOIN dashboard_users u_school ON u_school.id = v.school_id
            LEFT JOIN portal_schools ps ON ps.id = u_school.school_id
            WHERE v.status IN ('verified', 'pending')
            ORDER BY is_own_school DESC NULLS LAST,
                     CASE WHEN v.status = 'verified' THEN 0 ELSE 1 END,
                     v.vendor_type, v.name ASC, v.id DESC
            """,
            (school_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_vendor_by_id(vendor_id: int) -> Optional[Dict[str, Any]]:
    """Get single vendor by ID."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT v.*, 
                   COALESCE(ps.name, u_school.full_name) AS school_name, 
                   ps.npsn
            FROM monev_bos_vendors v
            JOIN dashboard_users u_school ON u_school.id = v.school_id
            LEFT JOIN portal_schools ps ON ps.id = u_school.school_id
            WHERE v.id = %s
            """,
            (vendor_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def create_vendor(school_id: int, data: Dict[str, Any]) -> int:
    """Create a new vendor registration for a school."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_vendors 
            (school_id, name, npwp, phone, address, owner_name, bank_name, bank_account_type, bank_account, vendor_type, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id
            """,
            (
                school_id,
                data.get("name", "").strip(),
                data.get("npwp", "").strip() or None,
                data.get("phone", "").strip() or None,
                data.get("address", "").strip() or None,
                data.get("owner_name", "").strip() or None,
                data.get("bank_name", "").strip() or None,
                data.get("bank_account_type", "rekening") if data.get("bank_account_type") in ("rekening", "va") else "rekening",
                data.get("bank_account", "").strip() or None,
                data.get("vendor_type", "vendor") if data.get("vendor_type") in ("vendor", "narsum") else "vendor",
            )
        )
        return cur.fetchone()[0]


def update_pending_vendor(vendor_id: int, school_id: int, data: Dict[str, Any]) -> bool:
    """Update a vendor owned by the school while it is awaiting verification."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_vendors
            SET name = %s,
                npwp = %s,
                phone = %s,
                address = %s,
                owner_name = %s,
                bank_name = %s,
                bank_account_type = %s,
                bank_account = %s,
                vendor_type = %s,
                updated_at = NOW()
            WHERE id = %s AND school_id = %s AND status = 'pending'
            """,
            (
                data.get("name", "").strip(),
                data.get("npwp", "").strip() or None,
                data.get("phone", "").strip() or None,
                data.get("address", "").strip() or None,
                data.get("owner_name", "").strip() or None,
                data.get("bank_name", "").strip() or None,
                data.get("bank_account_type", "rekening") if data.get("bank_account_type") in ("rekening", "va") else "rekening",
                data.get("bank_account", "").strip() or None,
                data.get("vendor_type", "vendor") if data.get("vendor_type") in ("vendor", "narsum") else "vendor",
                vendor_id,
                school_id,
            ),
        )
        return cur.rowcount > 0


def update_vendor_status(
    vendor_id: int,
    new_status: str,
    verifier_user_id: int,
    rejection_reason: Optional[str] = None,
    verification_notes: Optional[str] = None,
    verification_checklist: Optional[Dict[str, bool]] = None,
    review_notes: Optional[str] = None,
) -> bool:
    """Approve (verify) or Reject a vendor request."""
    if new_status not in ["verified", "rejected"]:
        return False
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_vendors
            SET status = %s,
                verified_by = %s,
                verified_at = NOW(),
                rejection_reason = %s,
                verification_notes = %s,
                verification_checklist = CASE
                    WHEN %s = 'verified' THEN %s::jsonb
                    ELSE verification_checklist
                END,
                review_notes = CASE
                    WHEN %s = 'verified' THEN %s
                    ELSE review_notes
                END,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                new_status,
                verifier_user_id,
                rejection_reason if new_status == "rejected" else None,
                verification_notes if new_status == "verified" else None,
                new_status,
                json.dumps(verification_checklist or {}),
                new_status,
                review_notes,
                vendor_id,
            )
        )
        return cur.rowcount > 0


def delete_vendor(vendor_id: int, school_id: Optional[int] = None) -> bool:
    """Delete a pending vendor, optionally restricted to its owning school."""
    query = "DELETE FROM monev_bos_vendors WHERE id = %s"
    params = [vendor_id]
    if school_id:
        query += " AND school_id = %s"
        params.append(school_id)
    query += " AND status = 'pending'"
    with get_cursor(commit=True) as cur:
        cur.execute(query, tuple(params))
        return cur.rowcount > 0


DEFAULT_MASTER_BANKS = [
    "Bank DKI",
    "Bank DKI Syariah",
    "Bank Mandiri",
    "Bank BCA",
    "Bank BRI",
    "Bank BNI",
    "Bank Syariah Indonesia (BSI)",
    "Bank Tabungan Negara (BTN)",
    "Bank Permata",
    "Bank Danamon",
    "Bank CIMB Niaga"
]


def get_master_banks() -> List[str]:
    """Fetch list of master banks from system_settings or default list."""
    with get_cursor() as cur:
        cur.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'master_bank_list'")
        row = cur.fetchone()
        if row and row["setting_value"]:
            try:
                import json
                banks = json.loads(row["setting_value"])
                if isinstance(banks, list) and len(banks) > 0:
                    return [str(b).strip() for b in banks if str(b).strip()]
            except Exception:
                pass
    return DEFAULT_MASTER_BANKS


def save_master_banks(bank_list: List[str], user_id: Optional[int] = None) -> bool:
    """Save master bank list to system_settings."""
    import json
    cleaned_banks = [b.strip() for b in bank_list if b and b.strip()]
    if not cleaned_banks:
        cleaned_banks = DEFAULT_MASTER_BANKS
    setting_value = json.dumps(cleaned_banks)
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO system_settings (setting_key, setting_value, category, description, is_secret, updated_at, updated_by)
            VALUES ('master_bank_list', %s, 'monev_bos', 'Daftar pilihan nama bank vendor sekolah', FALSE, NOW(), %s)
            ON CONFLICT (setting_key) DO UPDATE
            SET setting_value = EXCLUDED.setting_value,
                updated_at = NOW(),
                updated_by = EXCLUDED.updated_by
            """,
            (setting_value, user_id)
        )
        return True


# --- MASTER KODE REKENING ---
def init_account_codes_table() -> None:
    """Create monev_bos_account_codes table if it does not exist."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS monev_bos_account_codes (
                id SERIAL PRIMARY KEY,
                code VARCHAR(100) UNIQUE NOT NULL,
                name VARCHAR(255),
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """
        )


def list_account_codes(include_inactive: bool = False) -> List[Dict[str, Any]]:
    init_account_codes_table()
    with get_cursor() as cur:
        query = "SELECT * FROM monev_bos_account_codes WHERE 1=1"
        if not include_inactive:
            query += " AND is_active = TRUE"
        query += " ORDER BY code ASC"
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def check_account_code_exists(code: str, exclude_id: Optional[int] = None) -> bool:
    init_account_codes_table()
    with get_cursor() as cur:
        if exclude_id is not None:
            cur.execute("SELECT 1 FROM monev_bos_account_codes WHERE code = %s AND id != %s", (code, exclude_id))
        else:
            cur.execute("SELECT 1 FROM monev_bos_account_codes WHERE code = %s", (code,))
        return bool(cur.fetchone())


def create_account_code(code: str, name: Optional[str] = None, description: Optional[str] = None) -> int:
    init_account_codes_table()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_account_codes (code, name, description)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (code.strip(), (name or "").strip() or None, (description or "").strip() or None)
        )
        return cur.fetchone()[0]


def update_account_code(account_code_id: int, code: str, name: Optional[str], description: Optional[str], is_active: bool) -> None:
    init_account_codes_table()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_account_codes
            SET code = %s, name = %s, description = %s, is_active = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (code.strip(), (name or "").strip() or None, (description or "").strip() or None, is_active, account_code_id)
        )


def delete_account_code(account_code_id: int) -> None:
    init_account_codes_table()
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_account_codes WHERE id = %s", (account_code_id,))


def get_assigned_auditors_for_school(school_id: int, period_id: int) -> Dict[str, Any]:
    """Return assigned team info and verifier members (including the team leader)."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT t.name AS team_name,
                   u.id AS staff_id,
                   u.full_name AS staff_name,
                   u.nip AS staff_nip,
                   (t.leader_id = u.id) AS is_leader
            FROM monev_bos_assignments ass
            JOIN monev_bos_teams t ON ass.team_id = t.id
            JOIN dashboard_users u ON (u.id = t.leader_id OR u.id IN (SELECT staff_id FROM monev_bos_team_members WHERE team_id = t.id))
            WHERE ass.school_id = %s AND ass.period_id = %s
            ORDER BY (t.leader_id = u.id) DESC, u.full_name ASC
            """,
            (school_id, period_id)
        )
        rows = cur.fetchall()
        if not rows:
            cur.execute(
                """
                SELECT DISTINCT u.id AS staff_id,
                       u.full_name AS staff_name,
                       u.nip AS staff_nip,
                       FALSE AS is_leader
                FROM monev_bos_reports r
                JOIN monev_bos_activities a ON r.id = a.report_id
                JOIN monev_bos_activity_history h ON a.id = h.activity_id
                JOIN dashboard_users u ON h.actor_id = u.id
                WHERE r.school_id = %s AND r.period_id = %s
                  AND u.role IN ('staff', 'admin')
                ORDER BY u.full_name ASC
                """,
                (school_id, period_id)
            )
            hist_rows = cur.fetchall()
            if hist_rows:
                return {
                    "team_name": "Tim Verifikator Monev",
                    "members": [dict(r) for r in hist_rows]
                }
            return {"team_name": None, "members": []}

        return {
            "team_name": rows[0]["team_name"],
            "members": [dict(r) for r in rows]
        }


# --- STORY & POST SEKOLAH ---
def save_external_photo_teacher(
    school_user_id: int, full_name: str, nip: str, actor_id: int
) -> Dict[str, Any]:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_external_photo_teachers
                (school_user_id, full_name, nip, created_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (school_user_id, nip) DO UPDATE
            SET full_name = EXCLUDED.full_name, is_active = TRUE, updated_at = NOW()
            RETURNING *
            """,
            (school_user_id, full_name.strip(), nip.strip(), actor_id),
        )
        return dict(cur.fetchone())


def list_external_photo_teachers(school_user_id: int, limit: int = 300) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM monev_bos_external_photo_teachers
            WHERE school_user_id = %s AND is_active = TRUE
            ORDER BY full_name ASC
            LIMIT %s
            """,
            (school_user_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def get_external_photo_teacher(school_user_id: int, nip: str) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM monev_bos_external_photo_teachers
            WHERE school_user_id = %s AND nip = %s AND is_active = TRUE
            """,
            (school_user_id, nip.strip()),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def delete_external_photo_teacher(teacher_id: int, school_user_id: int) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM monev_bos_external_photo_teachers
            WHERE id = %s AND school_user_id = %s
            RETURNING id
            """,
            (teacher_id, school_user_id),
        )
        return cur.fetchone() is not None


def create_external_photo_link(school_user_id: int, actor_id: int) -> Dict[str, Any]:
    public_id = secrets.token_urlsafe(24)
    access_token = generate_access_token()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_external_photo_links
                (school_user_id, public_id, access_token, expires_at, created_by)
            VALUES (%s, %s, %s, NOW() + INTERVAL '24 hours', %s)
            RETURNING *
            """,
            (school_user_id, public_id, access_token, actor_id),
        )
        return dict(cur.fetchone())


def list_external_photo_links(school_user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.*,
                   (l.revoked_at IS NULL AND l.expires_at > NOW()) AS is_active
            FROM monev_bos_external_photo_links l
            WHERE l.school_user_id = %s
            ORDER BY l.created_at DESC
            LIMIT %s
            """,
            (school_user_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def get_external_photo_link(public_id: str) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.*,
                   (l.revoked_at IS NULL AND l.expires_at > NOW()) AS is_active,
                   COALESCE(s.name, owner.full_name, owner.email, 'Sekolah') AS school_name,
                   s.logo_url AS school_logo_url,
                   s.npsn
            FROM monev_bos_external_photo_links l
            JOIN dashboard_users owner ON owner.id = l.school_user_id
            LEFT JOIN portal_schools s ON s.id = owner.school_id
            WHERE l.public_id = %s
            """,
            (public_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def revoke_external_photo_link(link_id: int, school_user_id: int, actor_id: int) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_external_photo_links
            SET revoked_at = NOW(), revoked_by = %s
            WHERE id = %s AND school_user_id = %s AND revoked_at IS NULL
            RETURNING id
            """,
            (actor_id, link_id, school_user_id),
        )
        return cur.fetchone() is not None


def create_school_post(
    school_user_id: int,
    title: str,
    photo_path: str,
    photo_size: int,
    latitude: float,
    longitude: float,
    location_accuracy: Optional[float],
    location_text: str,
    actor_id: Optional[int],
    external_link_id: Optional[int] = None,
    external_photographer_name: Optional[str] = None,
    external_photographer_nip: Optional[str] = None,
) -> int:
    with get_cursor(commit=True) as cur:
        if external_link_id is not None:
            cur.execute(
                """
                SELECT id FROM monev_bos_external_photo_links
                WHERE id = %s AND school_user_id = %s
                  AND revoked_at IS NULL AND expires_at > NOW()
                FOR UPDATE
                """,
                (external_link_id, school_user_id),
            )
            if not cur.fetchone():
                raise ValueError("Tautan foto eksternal sudah tidak aktif.")
        cur.execute(
            """
            INSERT INTO monev_bos_school_posts
                (school_user_id, title, photo_path, photo_size, latitude, longitude,
                 location_accuracy, location_text, created_by, external_link_id,
                 external_photographer_name, external_photographer_nip)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                school_user_id,
                title.strip(),
                photo_path,
                photo_size,
                latitude,
                longitude,
                location_accuracy,
                location_text,
                actor_id,
                external_link_id,
                external_photographer_name,
                external_photographer_nip,
            ),
        )
        post_id = int(cur.fetchone()[0])
        if external_link_id is not None:
            cur.execute(
                """
                UPDATE monev_bos_external_photo_links
                SET last_used_at = NOW(), submission_count = submission_count + 1
                WHERE id = %s
                """,
                (external_link_id,),
            )
        cur.execute(
            """
            INSERT INTO monev_bos_story_audit_logs
                (post_id, school_user_id, actor_id, action, details)
            VALUES (%s, %s, %s, 'CREATE', %s::jsonb)
            """,
            (
                post_id,
                school_user_id,
                actor_id,
                json.dumps({
                    "title": title.strip(),
                    "location_text": location_text,
                    "source": "external_link" if external_link_id else "school",
                    "photographer_name": external_photographer_name,
                    "photographer_nip": external_photographer_nip,
                }),
            ),
        )
        return post_id


def get_school_post(post_id: int, *, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        query = """
            SELECT p.*,
                   COALESCE(s.name, owner.full_name, owner.email, 'Sekolah') AS school_name,
                   s.logo_url AS school_logo_url,
                   CASE WHEN p.story_expires_at > NOW() THEN TRUE ELSE FALSE END AS is_active_story,
                   COALESCE(creator.full_name, creator.email, 'Tidak ada') AS creator_name,
                   COALESCE(deleter.full_name, deleter.email, 'Tidak ada') AS deleter_name
            FROM monev_bos_school_posts p
            JOIN dashboard_users owner ON owner.id = p.school_user_id
            LEFT JOIN portal_schools s ON s.id = owner.school_id
            LEFT JOIN dashboard_users creator ON creator.id = p.created_by
            LEFT JOIN dashboard_users deleter ON deleter.id = p.deleted_by
            WHERE p.id = %s
        """
        if not include_deleted:
            query += " AND p.deleted_at IS NULL"
        cur.execute(query, (post_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_school_posts_by_ids(post_ids: List[int], school_user_id: int) -> List[Dict[str, Any]]:
    """Return undeleted posts owned by one school; callers may restore their chosen order."""
    clean_ids = list(dict.fromkeys(int(post_id) for post_id in post_ids))
    if not clean_ids:
        return []
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT p.*,
                   COALESCE(s.name, owner.full_name, owner.email, 'Sekolah') AS school_name,
                   s.npsn, s.alamat, s.logo_url AS school_logo_url
            FROM monev_bos_school_posts p
            JOIN dashboard_users owner ON owner.id = p.school_user_id
            LEFT JOIN portal_schools s ON s.id = owner.school_id
            WHERE p.id = ANY(%s)
              AND p.school_user_id = %s
              AND p.deleted_at IS NULL
            """,
            (clean_ids, school_user_id),
        )
        return [dict(row) for row in cur.fetchall()]


def publish_school_posts(
    post_ids: List[int],
    school_user_id: int,
    actor_id: int,
    photo_hashes: Optional[Dict[int, str]] = None,
) -> List[Dict[str, Any]]:
    """Publish selected private photos and allocate stable, unguessable verification tokens."""
    clean_ids = list(dict.fromkeys(int(post_id) for post_id in post_ids))
    if not clean_ids:
        return []
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT id, title, is_public, public_token
            FROM monev_bos_school_posts
            WHERE id = ANY(%s)
              AND school_user_id = %s
              AND deleted_at IS NULL
            FOR UPDATE
            """,
            (clean_ids, school_user_id),
        )
        rows = cur.fetchall()
        for row in rows:
            token = row["public_token"] or secrets.token_urlsafe(32)
            cur.execute(
                """
                UPDATE monev_bos_school_posts
                SET is_public = TRUE,
                    public_token = %s,
                    published_at = COALESCE(published_at, NOW()),
                    photo_sha256 = COALESCE(photo_sha256, %s)
                WHERE id = %s
                """,
                (token, (photo_hashes or {}).get(int(row["id"])), row["id"]),
            )
            if not row["is_public"]:
                cur.execute(
                    """
                    INSERT INTO monev_bos_story_audit_logs
                        (post_id, school_user_id, actor_id, action, details)
                    VALUES (%s, %s, %s, 'PUBLISH', %s::jsonb)
                    """,
                    (
                        row["id"],
                        school_user_id,
                        actor_id,
                        json.dumps({"title": row["title"], "reason": "photo_report_pdf"}),
                    ),
                )
    return get_school_posts_by_ids(clean_ids, school_user_id)


def get_public_school_post(public_token: str) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT p.*,
                   COALESCE(s.name, owner.full_name, owner.email, 'Sekolah') AS school_name,
                   s.npsn, s.alamat, s.logo_url AS school_logo_url
            FROM monev_bos_school_posts p
            JOIN dashboard_users owner ON owner.id = p.school_user_id
            LEFT JOIN portal_schools s ON s.id = owner.school_id
            WHERE p.public_token = %s
              AND p.is_public = TRUE
              AND p.deleted_at IS NULL
            """,
            ((public_token or "").strip(),),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_school_post_by_photo_path(photo_path: str) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, school_user_id, is_public, public_token, deleted_at,
                   CASE WHEN story_expires_at > NOW() THEN TRUE ELSE FALSE END AS is_active_story
            FROM monev_bos_school_posts
            WHERE photo_path = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            ((photo_path or "").lstrip("/"),),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_school_post_profile(school_user_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT owner.id AS school_user_id,
                   COALESCE(s.name, owner.full_name, owner.email, 'Sekolah') AS school_name,
                   s.logo_url AS school_logo_url,
                   s.npsn,
                   s.alamat,
                   COUNT(p.id) FILTER (WHERE p.deleted_at IS NULL) AS post_count
            FROM dashboard_users owner
            LEFT JOIN portal_schools s ON s.id = owner.school_id
            LEFT JOIN monev_bos_school_posts p ON p.school_user_id = owner.id
            WHERE owner.id = %s AND owner.role = 'sekolah'
            GROUP BY owner.id, s.name, s.logo_url, s.npsn, s.alamat
            """,
            (school_user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_school_posts(
    *,
    school_user_id: Optional[int] = None,
    search_query: str = "",
    shared_only: bool = False,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        query = """
            SELECT p.*,
                   COALESCE(s.name, owner.full_name, owner.email, 'Sekolah') AS school_name,
                   s.logo_url AS school_logo_url,
                   CASE WHEN p.story_expires_at > NOW() THEN TRUE ELSE FALSE END AS is_active_story
            FROM monev_bos_school_posts p
            JOIN dashboard_users owner ON owner.id = p.school_user_id
            LEFT JOIN portal_schools s ON s.id = owner.school_id
            WHERE p.deleted_at IS NULL
        """
        params: List[Any] = []
        if school_user_id is not None:
            query += " AND p.school_user_id = %s"
            params.append(school_user_id)
        if shared_only:
            query += " AND (p.is_public = TRUE OR p.story_expires_at > NOW())"
        if search_query.strip():
            pattern = f"%{search_query.strip()}%"
            query += """
                AND (
                    p.title ILIKE %s OR p.location_text ILIKE %s OR
                    COALESCE(s.name, owner.full_name, owner.email, '') ILIKE %s
                )
            """
            params.extend([pattern, pattern, pattern])
        query += " ORDER BY p.created_at DESC, p.id DESC LIMIT %s"
        params.append(max(1, min(int(limit), 500)))
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def list_active_story_groups(
    limit: int = 200,
    school_user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    posts = list_school_posts(school_user_id=school_user_id, limit=limit)
    active_posts = [post for post in posts if post.get("is_active_story")]
    groups: Dict[int, Dict[str, Any]] = {}
    for post in reversed(active_posts):
        school_user_id = int(post["school_user_id"])
        group = groups.setdefault(
            school_user_id,
            {
                "school_user_id": school_user_id,
                "school_name": post.get("school_name") or "Sekolah",
                "school_logo_url": post.get("school_logo_url"),
                "posts": [],
            },
        )
        group["posts"].append(post)
    return sorted(
        groups.values(),
        key=lambda group: group["posts"][-1]["created_at"] if group["posts"] else date.min,
        reverse=True,
    )


def get_activity_post_link(activity_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT link.*, p.title AS post_title, p.photo_path AS post_photo_path
            FROM monev_bos_activity_post_links link
            JOIN monev_bos_school_posts p ON p.id = link.post_id
            WHERE link.activity_id = %s
            """,
            (activity_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_activity_post_links(activity_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT link.*, p.title AS post_title, p.photo_path AS post_photo_path
            FROM monev_bos_activity_post_links link
            JOIN monev_bos_school_posts p ON p.id = link.post_id
            WHERE link.activity_id = %s
            ORDER BY link.linked_at, link.id
            """,
            (activity_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def unlink_activity_post(activity_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_activity_post_links WHERE activity_id = %s", (activity_id,))


def link_post_to_activity(activity_id: int, post_id: int, school_user_id: int, actor_id: int) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT id, title, photo_path, photo_size
            FROM monev_bos_school_posts
            WHERE id = %s AND school_user_id = %s AND deleted_at IS NULL
            FOR UPDATE
            """,
            (post_id, school_user_id),
        )
        post = cur.fetchone()
        if not post:
            raise ValueError("Postingan sekolah tidak ditemukan.")

        cur.execute(
            "SELECT id FROM monev_bos_activity_post_links WHERE activity_id = %s AND post_id = %s",
            (activity_id, post_id),
        )
        existing_link = cur.fetchone()
        if existing_link:
            return int(existing_link["id"])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM monev_bos_activity_docs
            WHERE activity_id = %s
              AND doc_type = 'field_photo'
              AND is_audit_valid = TRUE
            """,
            (activity_id,),
        )
        if int(cur.fetchone()[0]) >= 3:
            raise ValueError("Maksimal 3 Foto Kegiatan/Barang yang sah per kegiatan.")

        cur.execute(
            """
            INSERT INTO monev_bos_activity_docs
                (activity_id, doc_type, file_path, file_size, uploaded_by)
            VALUES (%s, 'field_photo', %s, %s, %s)
            RETURNING id
            """,
            (activity_id, post["photo_path"], post["photo_size"], actor_id),
        )
        doc_id = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO monev_bos_activity_post_links
                (activity_id, post_id, activity_doc_id, linked_by)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (activity_id, post_id, doc_id, actor_id),
        )
        link_id = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO monev_bos_story_audit_logs
                (post_id, school_user_id, activity_id, actor_id, action, details)
            VALUES (%s, %s, %s, %s, 'LINK_ACTIVITY', %s::jsonb)
            """,
            (
                post_id,
                school_user_id,
                activity_id,
                actor_id,
                json.dumps({"activity_doc_id": doc_id, "post_title": post["title"]}),
            ),
        )
        return link_id


def list_post_activity_links(post_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT link.*, doc.file_path, a.report_id
            FROM monev_bos_activity_post_links link
            JOIN monev_bos_activities a ON a.id = link.activity_id
            LEFT JOIN monev_bos_activity_docs doc ON doc.id = link.activity_doc_id
            WHERE link.post_id = %s
            ORDER BY link.id
            """,
            (post_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def finalize_school_post_delete(
    post_id: int,
    actor_id: int,
    school_user_id: int,
    copied_links: List[Dict[str, Any]],
    details: Dict[str, Any],
) -> None:
    """Atomically repoint linked activity docs, mark the post deleted, and record its history."""
    with get_cursor(commit=True) as cur:
        for copied in copied_links:
            cur.execute(
                "UPDATE monev_bos_activity_docs SET file_path = %s, file_size = %s WHERE id = %s",
                (copied["copied_path"], copied["copied_size"], copied["activity_doc_id"]),
            )
            if cur.rowcount != 1:
                raise ValueError("Dokumen kegiatan tertaut tidak ditemukan.")
            cur.execute(
                """
                UPDATE monev_bos_activity_post_links
                SET copied_on_post_delete_at = NOW()
                WHERE id = %s
                """,
                (copied["link_id"],),
            )
            if cur.rowcount != 1:
                raise ValueError("Tautan postingan ke kegiatan tidak ditemukan.")

        cur.execute(
            """
            UPDATE monev_bos_school_posts
            SET deleted_at = NOW(), deleted_by = %s
            WHERE id = %s AND deleted_at IS NULL
            """,
            (actor_id, post_id),
        )
        if cur.rowcount != 1:
            raise ValueError("Postingan tidak ditemukan atau sudah dihapus.")
        cur.execute(
            """
            INSERT INTO monev_bos_story_audit_logs
                (post_id, school_user_id, actor_id, action, details)
            VALUES (%s, %s, %s, 'DELETE', %s::jsonb)
            """,
            (post_id, school_user_id, actor_id, json.dumps(details)),
        )


def list_story_audit_logs(limit: int = 100) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT log.*,
                   COALESCE(actor.full_name, actor.email, 'Tidak ada') AS actor_name,
                   COALESCE(s.name, owner.full_name, owner.email, 'Sekolah') AS school_name,
                   p.title AS post_title
            FROM monev_bos_story_audit_logs log
            LEFT JOIN dashboard_users actor ON actor.id = log.actor_id
            LEFT JOIN dashboard_users owner ON owner.id = log.school_user_id
            LEFT JOIN portal_schools s ON s.id = owner.school_id
            LEFT JOIN monev_bos_school_posts p ON p.id = log.post_id
            ORDER BY log.created_at DESC, log.id DESC
            LIMIT %s
            """,
            (max(1, min(int(limit), 500)),),
        )
        return [dict(row) for row in cur.fetchall()]
