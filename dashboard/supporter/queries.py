from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json

from dashboard.db_access import get_cursor
from utils import current_jakarta_time, to_jakarta


SUPPORTER_TELEGRAM_SCOPE = "supporter"

TASK_STATUSES = ("draft", "active", "paused", "archived")
SUBMISSION_STATUSES = (
    "submitted",
    "under_review",
    "verified",
    "rejected",
    "needs_revision",
    "cancelled",
)

ACTION_OPTIONS = (
    ("like", "Like"),
    ("comment", "Komentar"),
    ("share", "Share"),
    ("repost", "Repost"),
    ("follow", "Follow"),
    ("subscribe", "Subscribe"),
    ("view", "View"),
    ("save", "Save"),
    ("mention", "Mention"),
    ("tag", "Tag"),
    ("story", "Story"),
    ("join", "Join"),
    ("review", "Review"),
    ("click", "Klik Link"),
    ("custom", "Custom"),
)

PLATFORM_OPTIONS = (
    ("instagram", "Instagram"),
    ("tiktok", "TikTok"),
    ("youtube", "YouTube"),
    ("facebook", "Facebook"),
    ("x", "X / Twitter"),
    ("threads", "Threads"),
    ("linkedin", "LinkedIn"),
    ("telegram", "Telegram"),
    ("whatsapp_channel", "WhatsApp Channel"),
    ("website", "Website"),
    ("google_maps", "Google Maps"),
    ("other", "Lainnya"),
)

ACTION_LABELS = dict(ACTION_OPTIONS)


def normalize_action_types(raw_value: Any, fallback: Optional[str] = None) -> List[str]:
    """Return a stable list of task action keys for old and new task rows."""
    values: list[Any]
    if isinstance(raw_value, str):
        clean = raw_value.strip()
        if clean.startswith("["):
            try:
                loaded = json.loads(clean)
                values = loaded if isinstance(loaded, list) else [clean]
            except (TypeError, ValueError):
                values = [clean]
        elif "," in clean:
            values = [item.strip() for item in clean.split(",")]
        elif clean:
            values = [clean]
        else:
            values = []
    elif isinstance(raw_value, (list, tuple, set)):
        values = list(raw_value)
    elif raw_value:
        values = [raw_value]
    else:
        values = []

    result: list[str] = []
    for item in values:
        action = str(item or "").strip()
        if action and action not in result:
            result.append(action)
    if not result and fallback:
        fallback_clean = str(fallback).strip()
        if fallback_clean:
            result.append(fallback_clean)
    return result


def action_summary_for(raw_value: Any, fallback: Optional[str] = None) -> str:
    labels = [
        ACTION_LABELS.get(action, action)
        for action in normalize_action_types(raw_value, fallback=fallback)
    ]
    return ", ".join(labels) if labels else "-"


def _normalize_action_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    if "action_types" not in row and "action_type" not in row:
        return row
    actions = normalize_action_types(row.get("action_types"), fallback=row.get("action_type"))
    action_count = len(actions)
    points_per_action = int(row.get("base_points") or 0)
    row["action_types"] = actions
    row["action_summary"] = action_summary_for(actions)
    row["action_count"] = action_count
    row["points_per_action"] = points_per_action
    row["total_task_points"] = points_per_action * max(1, action_count)
    if not row.get("action_type") and actions:
        row["action_type"] = actions[0]
    return row


def ensure_supporter_schema() -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS supporter_tasks (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                campaign_name TEXT,
                description TEXT,
                platform TEXT NOT NULL DEFAULT 'instagram',
                action_type TEXT NOT NULL DEFAULT 'like',
                action_types JSONB NOT NULL DEFAULT '[]'::jsonb,
                target_url TEXT,
                target_account TEXT,
                instructions TEXT,
                base_points INTEGER NOT NULL DEFAULT 10 CHECK (base_points >= 0),
                late_penalty_percent NUMERIC(5,2) NOT NULL DEFAULT 50 CHECK (late_penalty_percent >= 0 AND late_penalty_percent <= 100),
                start_at TIMESTAMPTZ,
                deadline_at TIMESTAMPTZ,
                end_at TIMESTAMPTZ,
                allow_late_submission BOOLEAN NOT NULL DEFAULT TRUE,
                requires_proof_url BOOLEAN NOT NULL DEFAULT TRUE,
                requires_proof_text BOOLEAN NOT NULL DEFAULT TRUE,
                requires_screenshot BOOLEAN NOT NULL DEFAULT TRUE,
                verification_mode TEXT NOT NULL DEFAULT 'manual_telegram',
                status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'archived')),
                created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            ALTER TABLE supporter_tasks
            ADD COLUMN IF NOT EXISTS action_types JSONB NOT NULL DEFAULT '[]'::jsonb
            """
        )
        cur.execute(
            """
            ALTER TABLE supporter_tasks
            ADD COLUMN IF NOT EXISTS end_at TIMESTAMPTZ
            """
        )
        cur.execute(
            """
            ALTER TABLE supporter_tasks
            ALTER COLUMN late_penalty_percent SET DEFAULT 50
            """
        )
        cur.execute(
            """
            ALTER TABLE supporter_tasks
            ALTER COLUMN requires_proof_text SET DEFAULT TRUE
            """
        )
        cur.execute(
            """
            ALTER TABLE supporter_tasks
            ALTER COLUMN requires_screenshot SET DEFAULT TRUE
            """
        )
        cur.execute(
            """
            UPDATE supporter_tasks
            SET action_types = jsonb_build_array(action_type)
            WHERE action_types = '[]'::jsonb
              AND COALESCE(action_type, '') <> ''
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supporter_tasks_status_deadline
            ON supporter_tasks (status, deadline_at)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supporter_tasks_status_end
            ON supporter_tasks (status, end_at)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supporter_tasks_platform_action
            ON supporter_tasks (platform, action_type)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supporter_tasks_action_types
            ON supporter_tasks USING GIN (action_types)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS supporter_submissions (
                id SERIAL PRIMARY KEY,
                task_id INTEGER NOT NULL REFERENCES supporter_tasks(id) ON DELETE CASCADE,
                staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted', 'under_review', 'verified', 'rejected', 'needs_revision', 'cancelled')),
                social_username TEXT,
                proof_url TEXT,
                proof_text TEXT,
                proof_file_path TEXT,
                submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                reviewed_at TIMESTAMPTZ,
                reviewed_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
                reviewer_note TEXT,
                base_points INTEGER NOT NULL DEFAULT 0,
                penalty_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
                potential_points INTEGER NOT NULL DEFAULT 0,
                awarded_points INTEGER NOT NULL DEFAULT 0,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (task_id, staff_id)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supporter_submissions_staff_status
            ON supporter_submissions (staff_id, status, submitted_at DESC)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supporter_submissions_task_status
            ON supporter_submissions (task_id, status, submitted_at DESC)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS supporter_point_events (
                id SERIAL PRIMARY KEY,
                submission_id INTEGER REFERENCES supporter_submissions(id) ON DELETE SET NULL,
                task_id INTEGER REFERENCES supporter_tasks(id) ON DELETE SET NULL,
                staff_id INTEGER REFERENCES dashboard_users(id) ON DELETE CASCADE,
                points_delta INTEGER NOT NULL DEFAULT 0,
                event_type TEXT NOT NULL DEFAULT 'verified',
                note TEXT,
                created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supporter_point_events_staff_created
            ON supporter_point_events (staff_id, created_at DESC)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS supporter_activity_logs (
                id SERIAL PRIMARY KEY,
                actor_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id INTEGER,
                summary TEXT,
                details JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supporter_activity_logs_created
            ON supporter_activity_logs (created_at DESC)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS supporter_telegram_groups (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT UNIQUE NOT NULL,
                title TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS supporter_telegram_delivery_messages (
                submission_id INTEGER NOT NULL REFERENCES supporter_submissions(id) ON DELETE CASCADE,
                chat_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (submission_id, chat_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS supporter_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
            )
            """
        )


def _dict(row: Any) -> Optional[Dict[str, Any]]:
    return _normalize_action_payload(dict(row)) if row else None


def _rows(rows: Any) -> List[Dict[str, Any]]:
    return [_normalize_action_payload(dict(row)) for row in (rows or [])]


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def calculate_points(task: Dict[str, Any], submitted_at: Optional[datetime] = None) -> Dict[str, Any]:
    points_per_action = int(task.get("base_points") or 0)
    action_count = len(normalize_action_types(task.get("action_types"), fallback=task.get("action_type")))
    action_count = max(1, action_count)
    base_points = points_per_action * action_count
    deadline = _aware(task.get("deadline_at"))
    end_at = _aware(task.get("end_at"))
    submitted = _aware(submitted_at or current_jakarta_time())
    allow_late = bool(task.get("allow_late_submission", True))
    is_late = bool(deadline and submitted and submitted > deadline)
    is_ended = bool(end_at and submitted and submitted > end_at)
    if is_ended or (is_late and not allow_late):
        return {
            "base_points": base_points,
            "points_per_action": points_per_action,
            "action_count": action_count,
            "penalty_percent": Decimal("100.00") if is_late else Decimal("0"),
            "potential_points": 0,
            "is_late": is_late,
            "is_ended": is_ended,
            "is_expired": True,
        }
    penalty = Decimal(str(task.get("late_penalty_percent") or 0)) if is_late else Decimal("0")
    penalty = max(Decimal("0"), min(Decimal("100"), penalty))
    multiplier = (Decimal("100") - penalty) / Decimal("100")
    potential = int((Decimal(base_points) * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "base_points": base_points,
        "points_per_action": points_per_action,
        "action_count": action_count,
        "penalty_percent": penalty,
        "potential_points": max(0, potential),
        "is_late": is_late,
        "is_ended": is_ended,
        "is_expired": False,
    }


def log_activity(
    *,
    actor_user_id: Optional[int],
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    summary: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    ensure_supporter_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO supporter_activity_logs (
                actor_user_id, action, target_type, target_id, summary, details
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (actor_user_id, action, target_type, target_id, summary, Json(details or {})),
        )


def create_task(data: Dict[str, Any], *, created_by: Optional[int]) -> int:
    ensure_supporter_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO supporter_tasks (
                title, campaign_name, description, platform, action_type, action_types, target_url,
                target_account, instructions, base_points, late_penalty_percent,
                start_at, deadline_at, end_at, allow_late_submission, requires_proof_url,
                requires_proof_text, requires_screenshot, verification_mode, status,
                created_by
            )
            VALUES (
                %(title)s, %(campaign_name)s, %(description)s, %(platform)s,
                %(action_type)s, %(action_types_json)s, %(target_url)s, %(target_account)s,
                %(instructions)s, %(base_points)s, %(late_penalty_percent)s,
                %(start_at)s, %(deadline_at)s, %(end_at)s, %(allow_late_submission)s,
                %(requires_proof_url)s, %(requires_proof_text)s,
                %(requires_screenshot)s, %(verification_mode)s, %(status)s,
                %(created_by)s
            )
            RETURNING id
            """,
            {
                **data,
                "action_types_json": Json(data.get("action_types") or []),
                "created_by": created_by,
            },
        )
        task_id = int(cur.fetchone()["id"])
    log_activity(
        actor_user_id=created_by,
        action="CREATE",
        target_type="TASK",
        target_id=task_id,
        summary=f"Membuat task supporter: {data.get('title')}",
        details={
            "status": data.get("status"),
            "platform": data.get("platform"),
            "action_type": data.get("action_type"),
            "action_types": data.get("action_types") or [],
        },
    )
    return task_id


def update_task(task_id: int, data: Dict[str, Any], *, actor_user_id: Optional[int]) -> bool:
    ensure_supporter_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE supporter_tasks
            SET title = %(title)s,
                campaign_name = %(campaign_name)s,
                description = %(description)s,
                platform = %(platform)s,
                action_type = %(action_type)s,
                action_types = %(action_types_json)s,
                target_url = %(target_url)s,
                target_account = %(target_account)s,
                instructions = %(instructions)s,
                base_points = %(base_points)s,
                late_penalty_percent = %(late_penalty_percent)s,
                start_at = %(start_at)s,
                deadline_at = %(deadline_at)s,
                end_at = %(end_at)s,
                allow_late_submission = %(allow_late_submission)s,
                requires_proof_url = %(requires_proof_url)s,
                requires_proof_text = %(requires_proof_text)s,
                requires_screenshot = %(requires_screenshot)s,
                verification_mode = %(verification_mode)s,
                status = %(status)s,
                updated_at = NOW()
            WHERE id = %(task_id)s
            """,
            {
                **data,
                "action_types_json": Json(data.get("action_types") or []),
                "task_id": task_id,
            },
        )
        updated = cur.rowcount > 0
    if updated:
        log_activity(
            actor_user_id=actor_user_id,
            action="UPDATE",
            target_type="TASK",
            target_id=task_id,
            summary=f"Memperbarui task supporter: {data.get('title')}",
            details={
                "status": data.get("status"),
                "platform": data.get("platform"),
                "action_type": data.get("action_type"),
                "action_types": data.get("action_types") or [],
            },
        )
    return updated


def update_task_status(task_id: int, status: str, *, actor_user_id: Optional[int]) -> bool:
    if status not in TASK_STATUSES:
        return False
    ensure_supporter_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE supporter_tasks
            SET status = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (status, task_id),
        )
        updated = cur.rowcount > 0
    if updated:
        log_activity(
            actor_user_id=actor_user_id,
            action="STATUS",
            target_type="TASK",
            target_id=task_id,
            summary=f"Mengubah status task supporter menjadi {status}",
            details={"status": status},
        )
    return updated


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT t.*, u.full_name AS created_by_name, u.email AS created_by_email
            FROM supporter_tasks t
            LEFT JOIN dashboard_users u ON u.id = t.created_by
            WHERE t.id = %s
            """,
            (task_id,),
        )
        row = _dict(cur.fetchone())
        if row:
            dl = to_jakarta(row.get("deadline_at")) if row.get("deadline_at") else None
            row["deadline_iso"] = dl.isoformat() if dl else None
        return row


def list_tasks(*, status: Optional[str] = None, q: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    ensure_supporter_schema()
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("t.status = %s")
        params.append(status)
    if q:
        like = f"%{q.strip()}%"
        clauses.append("(t.title ILIKE %s OR t.campaign_name ILIKE %s OR t.target_account ILIKE %s)")
        params.extend([like, like, like])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(int(limit or 200), 1000)))
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                t.*,
                COUNT(s.id) AS submission_count,
                COUNT(s.id) FILTER (WHERE s.status = 'verified') AS verified_count,
                COUNT(s.id) FILTER (WHERE s.status IN ('submitted', 'under_review')) AS pending_count
            FROM supporter_tasks t
            LEFT JOIN supporter_submissions s ON s.task_id = t.id
            {where_sql}
            GROUP BY t.id
            ORDER BY
                CASE t.status WHEN 'active' THEN 0 WHEN 'draft' THEN 1 WHEN 'paused' THEN 2 ELSE 3 END,
                t.deadline_at ASC NULLS LAST,
                t.created_at DESC
            LIMIT %s
            """,
            params,
        )
        return _rows(cur.fetchall())


def get_staff_submission_for_task(*, task_id: int, staff_id: int) -> Optional[Dict[str, Any]]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM supporter_submissions
            WHERE task_id = %s AND staff_id = %s
            LIMIT 1
            """,
            (task_id, staff_id),
        )
        return _dict(cur.fetchone())


def list_staff_tasks(*, staff_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                t.*,
                s.id AS submission_id,
                s.status AS submission_status,
                s.submitted_at,
                s.reviewed_at,
                s.potential_points,
                s.awarded_points,
                s.reviewer_note
            FROM supporter_tasks t
            LEFT JOIN supporter_submissions s
              ON s.task_id = t.id AND s.staff_id = %s
            WHERE t.status = 'active'
              AND (t.start_at IS NULL OR t.start_at <= NOW())
            ORDER BY
                CASE WHEN s.id IS NULL THEN 0 ELSE 1 END,
                t.deadline_at ASC NULLS LAST,
                t.created_at DESC
            LIMIT %s
            """,
            (staff_id, max(1, min(int(limit or 100), 500))),
        )
        rows = _rows(cur.fetchall())
    now = current_jakarta_time()
    for row in rows:
        calc = calculate_points(row, submitted_at=now)
        row["current_penalty_percent"] = calc["penalty_percent"]
        row["current_potential_points"] = calc["potential_points"]
        row["is_late_now"] = calc["is_late"]
        row["is_expired_now"] = calc["is_expired"]
        dl = to_jakarta(row.get("deadline_at")) if row.get("deadline_at") else None
        row["deadline_iso"] = dl.isoformat() if dl else None
    return rows


def submit_task(
    *,
    task: Dict[str, Any],
    staff_id: int,
    social_username: Optional[str],
    proof_url: Optional[str],
    proof_text: Optional[str],
    proof_file_path: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_supporter_schema()
    submitted_at = current_jakarta_time()
    calc = calculate_points(task, submitted_at=submitted_at)
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO supporter_submissions (
                task_id, staff_id, status, social_username, proof_url, proof_text,
                proof_file_path, submitted_at, reviewed_at, reviewed_by, reviewer_note,
                base_points, penalty_percent, potential_points, awarded_points, metadata,
                updated_at
            )
            VALUES (
                %s, %s, 'submitted', %s, %s, %s, %s, %s, NULL, NULL, NULL,
                %s, %s, %s, 0, %s, NOW()
            )
            ON CONFLICT (task_id, staff_id) DO UPDATE
            SET status = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN 'submitted'
                    ELSE supporter_submissions.status
                END,
                social_username = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN EXCLUDED.social_username
                    ELSE supporter_submissions.social_username
                END,
                proof_url = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN EXCLUDED.proof_url
                    ELSE supporter_submissions.proof_url
                END,
                proof_text = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN EXCLUDED.proof_text
                    ELSE supporter_submissions.proof_text
                END,
                proof_file_path = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN EXCLUDED.proof_file_path
                    ELSE supporter_submissions.proof_file_path
                END,
                submitted_at = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN EXCLUDED.submitted_at
                    ELSE supporter_submissions.submitted_at
                END,
                reviewed_at = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN NULL
                    ELSE supporter_submissions.reviewed_at
                END,
                reviewed_by = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN NULL
                    ELSE supporter_submissions.reviewed_by
                END,
                reviewer_note = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN NULL
                    ELSE supporter_submissions.reviewer_note
                END,
                base_points = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN EXCLUDED.base_points
                    ELSE supporter_submissions.base_points
                END,
                penalty_percent = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN EXCLUDED.penalty_percent
                    ELSE supporter_submissions.penalty_percent
                END,
                potential_points = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN EXCLUDED.potential_points
                    ELSE supporter_submissions.potential_points
                END,
                awarded_points = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN 0
                    ELSE supporter_submissions.awarded_points
                END,
                metadata = CASE
                    WHEN supporter_submissions.status IN ('needs_revision', 'rejected', 'cancelled')
                    THEN EXCLUDED.metadata
                    ELSE supporter_submissions.metadata
                END,
                updated_at = NOW()
            RETURNING *
            """,
            (
                task["id"],
                staff_id,
                social_username,
                proof_url,
                proof_text,
                proof_file_path,
                submitted_at,
                calc["base_points"],
                calc["penalty_percent"],
                calc["potential_points"],
                Json(metadata or {}),
            ),
        )
        row = _dict(cur.fetchone()) or {}
    return row


def get_submission_detail(submission_id: int) -> Optional[Dict[str, Any]]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                s.*,
                t.title AS task_title,
                t.campaign_name,
                t.platform,
                t.action_type,
                t.action_types,
                t.target_url,
                t.target_account,
                t.instructions,
                t.deadline_at,
                t.end_at,
                t.late_penalty_percent AS task_late_penalty_percent,
                u.full_name AS staff_name,
                u.email AS staff_email,
                u.nip AS staff_nip,
                reviewer.full_name AS reviewer_name,
                reviewer.email AS reviewer_email
            FROM supporter_submissions s
            JOIN supporter_tasks t ON t.id = s.task_id
            JOIN dashboard_users u ON u.id = s.staff_id
            LEFT JOIN dashboard_users reviewer ON reviewer.id = s.reviewed_by
            WHERE s.id = %s
            """,
            (submission_id,),
        )
        return _dict(cur.fetchone())


def list_submissions(
    *,
    status: Optional[str] = None,
    q: Optional[str] = None,
    staff_id: Optional[int] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    ensure_supporter_schema()
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        if status == "pending":
            clauses.append("s.status IN ('submitted', 'under_review')")
        else:
            clauses.append("s.status = %s")
            params.append(status)
    if staff_id:
        clauses.append("s.staff_id = %s")
        params.append(staff_id)
    if q:
        like = f"%{q.strip()}%"
        clauses.append(
            "(CAST(s.id AS TEXT) = %s OR t.title ILIKE %s OR u.full_name ILIKE %s OR u.email ILIKE %s OR s.social_username ILIKE %s)"
        )
        params.extend([q.strip(), like, like, like, like])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(int(limit or 200), 1000)))
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                s.*,
                t.title AS task_title,
                t.platform,
                t.action_type,
                t.action_types,
                t.target_url,
                t.target_account,
                t.deadline_at,
                t.end_at,
                u.full_name AS staff_name,
                u.email AS staff_email,
                reviewer.full_name AS reviewer_name
            FROM supporter_submissions s
            JOIN supporter_tasks t ON t.id = s.task_id
            JOIN dashboard_users u ON u.id = s.staff_id
            LEFT JOIN dashboard_users reviewer ON reviewer.id = s.reviewed_by
            {where_sql}
            ORDER BY
                CASE s.status WHEN 'submitted' THEN 0 WHEN 'under_review' THEN 1 WHEN 'needs_revision' THEN 2 ELSE 3 END,
                s.submitted_at DESC
            LIMIT %s
            """,
            params,
        )
        return _rows(cur.fetchall())


def review_submission(
    *,
    submission_id: int,
    status: str,
    reviewer_id: Optional[int],
    reviewer_note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if status not in SUBMISSION_STATUSES or status == "submitted":
        return None
    ensure_supporter_schema()
    already_verified = False
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM supporter_submissions WHERE id = %s FOR UPDATE", (submission_id,))
        current = _dict(cur.fetchone())
        if not current:
            return None
        old_status = current.get("status")
        if old_status == "verified" and status == "verified":
            already_verified = True
            awarded_points = int(current.get("awarded_points") or 0)
            updated = current
        else:
            awarded_points = int(current.get("potential_points") or 0) if status == "verified" else 0
            cur.execute(
                """
                UPDATE supporter_submissions
                SET status = %s,
                    reviewed_at = NOW(),
                    reviewed_by = %s,
                    reviewer_note = %s,
                    awarded_points = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (status, reviewer_id, reviewer_note, awarded_points, submission_id),
            )
            updated = _dict(cur.fetchone())
            if status == "verified" and old_status != "verified" and awarded_points:
                cur.execute(
                    """
                    INSERT INTO supporter_point_events (
                        submission_id, task_id, staff_id, points_delta, event_type, note, created_by
                    )
                    VALUES (%s, %s, %s, %s, 'verified', %s, %s)
                    """,
                    (
                        submission_id,
                        current.get("task_id"),
                        current.get("staff_id"),
                        awarded_points,
                        reviewer_note,
                        reviewer_id,
                    ),
                )
    if not already_verified:
        log_activity(
            actor_user_id=reviewer_id,
            action="REVIEW",
            target_type="SUBMISSION",
            target_id=submission_id,
            summary=f"Review submission supporter menjadi {status}",
            details={"status": status, "old_status": old_status, "points": awarded_points},
        )
    return get_submission_detail(submission_id) if updated else None


ACTION_REVIEW_STATUSES = ("verified", "rejected", "needs_revision")


def _submission_action_keys(metadata: Dict[str, Any]) -> List[str]:
    """Action keys that have a screenshot in this submission."""
    screenshots = (metadata or {}).get("screenshots") or {}
    if isinstance(screenshots, dict):
        return [str(key) for key in screenshots.keys()]
    return []


def review_submission_action(
    *,
    submission_id: int,
    action_key: str,
    status: str,
    reviewer_id: Optional[int],
    reviewer_note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Verify/reject/revise a single action within a submission.

    Awarded points are recomputed as the sum of verified actions, and the
    overall submission status is derived from the per-action states.
    """
    if status not in ACTION_REVIEW_STATUSES:
        return None
    ensure_supporter_schema()
    action_key = str(action_key or "").strip()
    if not action_key:
        return None

    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM supporter_submissions WHERE id = %s FOR UPDATE", (submission_id,))
        row = cur.fetchone()
        if not row:
            return None
        current = dict(row)
        if current.get("status") == "cancelled":
            return None

        metadata = current.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (TypeError, ValueError):
                metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}

        action_keys = _submission_action_keys(metadata)
        if not action_keys:
            # Single-proof submission: treat the whole submission as one action.
            action_keys = [action_key]
        if action_key not in action_keys:
            return None

        count = max(1, len(action_keys))
        total_potential = int(current.get("potential_points") or 0)
        per_action = round(total_potential / count)

        reviews = metadata.get("action_reviews")
        if not isinstance(reviews, dict):
            reviews = {}
        reviewed_at = current_jakarta_time()
        reviews[action_key] = {
            "status": status,
            "points": per_action if status == "verified" else 0,
            "reviewed_by": reviewer_id,
            "reviewed_at": reviewed_at.isoformat(),
            "note": reviewer_note,
        }
        metadata["action_reviews"] = reviews

        verified_keys = [k for k in action_keys if (reviews.get(k) or {}).get("status") == "verified"]
        revision_keys = [k for k in action_keys if (reviews.get(k) or {}).get("status") == "needs_revision"]
        rejected_keys = [k for k in action_keys if (reviews.get(k) or {}).get("status") == "rejected"]
        decided = set(verified_keys) | set(revision_keys) | set(rejected_keys)
        pending_keys = [k for k in action_keys if k not in decided]

        if len(verified_keys) == count:
            awarded = total_potential
        else:
            awarded = per_action * len(verified_keys)

        if pending_keys:
            new_status = "under_review"
        elif len(verified_keys) == count:
            new_status = "verified"
        elif revision_keys:
            new_status = "needs_revision"
        elif verified_keys:
            new_status = "verified"  # partial accepted, nothing left pending
        else:
            new_status = "rejected"

        cur.execute(
            """
            UPDATE supporter_submissions
            SET status = %s,
                awarded_points = %s,
                reviewed_at = NOW(),
                reviewed_by = %s,
                reviewer_note = %s,
                metadata = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id
            """,
            (
                new_status,
                awarded,
                reviewer_id,
                reviewer_note or current.get("reviewer_note"),
                Json(metadata),
                submission_id,
            ),
        )
        updated = cur.fetchone()

        old_awarded = int(current.get("awarded_points") or 0)
        delta = awarded - old_awarded
        if delta != 0:
            cur.execute(
                """
                INSERT INTO supporter_point_events (
                    submission_id, task_id, staff_id, points_delta, event_type, note, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    submission_id,
                    current.get("task_id"),
                    current.get("staff_id"),
                    delta,
                    "verified" if delta > 0 else "adjust",
                    reviewer_note,
                    reviewer_id,
                ),
            )

    if not updated:
        return None
    log_activity(
        actor_user_id=reviewer_id,
        action="REVIEW_ACTION",
        target_type="SUBMISSION",
        target_id=submission_id,
        summary=f"Review aksi {action_key} menjadi {status}",
        details={"action_key": action_key, "status": status, "awarded_points": awarded},
    )
    return get_submission_detail(submission_id)


def cancel_submission(*, submission_id: int, staff_id: int) -> bool:
    ensure_supporter_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE supporter_submissions
            SET status = 'cancelled', awarded_points = 0, updated_at = NOW()
            WHERE id = %s
              AND staff_id = %s
              AND status IN ('submitted', 'under_review', 'needs_revision', 'rejected')
            """,
            (submission_id, staff_id),
        )
        return cur.rowcount > 0


def fetch_admin_stats() -> Dict[str, Any]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_tasks,
                COUNT(*) FILTER (WHERE status = 'active') AS active_tasks,
                (SELECT COUNT(*) FROM supporter_submissions) AS total_submissions,
                (SELECT COUNT(*) FROM supporter_submissions WHERE status IN ('submitted', 'under_review')) AS pending_submissions,
                (SELECT COUNT(*) FROM supporter_submissions WHERE status = 'verified') AS verified_submissions,
                (SELECT COALESCE(SUM(awarded_points), 0) FROM supporter_submissions) AS total_points
            FROM supporter_tasks
            """
        )
        return _dict(cur.fetchone()) or {}


def fetch_staff_stats(staff_id: int) -> Dict[str, Any]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_submissions,
                COUNT(*) FILTER (WHERE status IN ('submitted', 'under_review')) AS pending_submissions,
                COUNT(*) FILTER (WHERE status = 'verified') AS verified_submissions,
                COUNT(*) FILTER (WHERE status = 'needs_revision') AS revision_submissions,
                COALESCE(SUM(awarded_points), 0) AS total_points
            FROM supporter_submissions
            WHERE staff_id = %s
            """,
            (staff_id,),
        )
        stats = _dict(cur.fetchone()) or {}
    rank = fetch_staff_rank(staff_id)
    stats["rank"] = rank.get("rank") if rank else None
    return stats


def fetch_leaderboard(*, limit: int = 50) -> List[Dict[str, Any]]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                u.id AS staff_id,
                u.full_name AS staff_name,
                u.email AS staff_email,
                u.nip AS staff_nip,
                COUNT(s.id) FILTER (WHERE s.awarded_points > 0) AS verified_count,
                COALESCE(SUM(s.awarded_points), 0) AS total_points,
                MAX(s.reviewed_at) FILTER (WHERE s.awarded_points > 0) AS last_verified_at,
                RANK() OVER (
                    ORDER BY
                        COALESCE(SUM(s.awarded_points), 0) DESC,
                        COUNT(s.id) FILTER (WHERE s.awarded_points > 0) DESC,
                        MAX(s.reviewed_at) FILTER (WHERE s.awarded_points > 0) ASC NULLS LAST
                ) AS rank
            FROM dashboard_users u
            LEFT JOIN supporter_submissions s ON s.staff_id = u.id
            WHERE u.role = 'staff'
            GROUP BY u.id, u.full_name, u.email, u.nip
            HAVING COALESCE(SUM(s.awarded_points), 0) > 0
            ORDER BY rank ASC, u.full_name ASC
            LIMIT %s
            """,
            (max(1, min(int(limit or 50), 500)),),
        )
        return _rows(cur.fetchall())


def fetch_staff_rank(staff_id: int) -> Optional[Dict[str, Any]]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
                SELECT
                    u.id AS staff_id,
                    COALESCE(SUM(s.awarded_points), 0) AS total_points,
                    COUNT(s.id) FILTER (WHERE s.awarded_points > 0) AS verified_count,
                    RANK() OVER (
                        ORDER BY
                            COALESCE(SUM(s.awarded_points), 0) DESC,
                            COUNT(s.id) FILTER (WHERE s.awarded_points > 0) DESC,
                            MAX(s.reviewed_at) FILTER (WHERE s.awarded_points > 0) ASC NULLS LAST
                    ) AS rank
                FROM dashboard_users u
                LEFT JOIN supporter_submissions s ON s.staff_id = u.id
                WHERE u.role = 'staff'
                GROUP BY u.id
            )
            SELECT *
            FROM ranked
            WHERE staff_id = %s
            """,
            (staff_id,),
        )
        row = _dict(cur.fetchone())
    if not row or int(row.get("total_points") or 0) <= 0:
        return None
    return row


def list_activity_logs(*, limit: int = 100) -> List[Dict[str, Any]]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.*, u.full_name AS actor_name, u.email AS actor_email
            FROM supporter_activity_logs l
            LEFT JOIN dashboard_users u ON u.id = l.actor_user_id
            ORDER BY l.created_at DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 100), 500)),),
        )
        return _rows(cur.fetchall())


def list_supporter_telegram_groups() -> List[Dict[str, Any]]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT g.*, u.full_name AS created_by_name, u.email AS created_by_email
            FROM supporter_telegram_groups g
            LEFT JOIN dashboard_users u ON u.id = g.created_by
            ORDER BY g.updated_at DESC
            """
        )
        return _rows(cur.fetchall())


def upsert_supporter_telegram_group(
    *,
    chat_id: int,
    title: Optional[str],
    created_by: Optional[int],
) -> bool:
    ensure_supporter_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO supporter_telegram_groups (chat_id, title, created_by, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (chat_id) DO UPDATE
            SET title = EXCLUDED.title,
                created_by = EXCLUDED.created_by,
                updated_at = NOW()
            """,
            (chat_id, title, created_by),
        )
    return True


def delete_supporter_telegram_group_by_chat_id(chat_id: int) -> bool:
    ensure_supporter_schema()
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM supporter_telegram_groups WHERE chat_id = %s", (chat_id,))
        return cur.rowcount > 0


def delete_supporter_telegram_group(group_id: int) -> bool:
    ensure_supporter_schema()
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM supporter_telegram_groups WHERE id = %s", (group_id,))
        return cur.rowcount > 0


def list_supporter_admin_delivery_status() -> List[Dict[str, Any]]:
    """Registered supporter admins with resolved Telegram chat_id (reachability)."""
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                ta.id,
                ta.telegram_username,
                u.full_name AS admin_name,
                u.email AS admin_email,
                tu.telegram_user_id
            FROM telegram_admin_accounts ta
            LEFT JOIN dashboard_users u ON u.id = ta.dashboard_user_id
            LEFT JOIN telegram_users tu ON LOWER(tu.username) = LOWER(ta.telegram_username)
            WHERE ta.notification_scope = %s
            ORDER BY LOWER(ta.telegram_username) ASC
            """,
            (SUPPORTER_TELEGRAM_SCOPE,),
        )
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["reachable"] = bool(row.get("telegram_user_id"))
    return rows


def get_supporter_setting(key: str) -> Optional[str]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute("SELECT value FROM supporter_settings WHERE key = %s", (key,))
        row = cur.fetchone()
    if not row:
        return None
    value = (dict(row).get("value") or "").strip()
    return value or None


def set_supporter_setting(key: str, value: Optional[str], *, updated_by: Optional[int] = None) -> None:
    ensure_supporter_schema()
    clean_value = (value or "").strip() or None
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO supporter_settings (key, value, updated_at, updated_by)
            VALUES (%s, %s, NOW(), %s)
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
            """,
            (key, clean_value, updated_by),
        )


def upsert_supporter_delivery_message(*, submission_id: int, chat_id: int, message_id: int) -> None:
    ensure_supporter_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO supporter_telegram_delivery_messages (submission_id, chat_id, message_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (submission_id, chat_id) DO UPDATE
            SET message_id = EXCLUDED.message_id,
                updated_at = NOW()
            """,
            (submission_id, chat_id, message_id),
        )


def export_submissions() -> List[Dict[str, Any]]:
    ensure_supporter_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                s.*,
                t.title AS task_title,
                t.platform,
                t.action_type,
                t.action_types,
                t.target_url,
                t.target_account,
                t.deadline_at,
                t.end_at,
                u.full_name AS staff_name,
                u.email AS staff_email,
                reviewer.full_name AS reviewer_name
            FROM supporter_submissions s
            JOIN supporter_tasks t ON t.id = s.task_id
            JOIN dashboard_users u ON u.id = s.staff_id
            LEFT JOIN dashboard_users reviewer ON reviewer.id = s.reviewed_by
            ORDER BY s.submitted_at DESC
            """
        )
        return _rows(cur.fetchall())
