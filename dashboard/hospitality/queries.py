"""Query helpers for Hospitality assessments."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

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

HOSPITALITY_SCORE_MAX = 5
HOSPITALITY_STATUSES = ("draft", "submitted", "verified", "reopened")
REOPEN_STATUSES = ("pending", "approved", "rejected")
GUESTBOOK_REVIEW_STATUSES = ("pending", "completed")


def _today_jakarta() -> date:
    return datetime.now(_JAKARTA_TZ).date()


def list_components_with_aspects(*, active_only: bool = True) -> List[Dict[str, Any]]:
    """Return components and their aspects ordered for form rendering."""
    conditions = []
    params: List[Any] = []
    if active_only:
        conditions.append("c.active = TRUE")
        conditions.append("(a.id IS NULL OR a.active = TRUE)")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                c.id AS component_id,
                c.name AS component_name,
                c.description AS component_description,
                c.sort_order AS component_sort,
                c.active AS component_active,
                c.is_required AS component_required,
                a.id AS aspect_id,
                a.name AS aspect_name,
                a.description AS aspect_description,
                a.sort_order AS aspect_sort,
                a.is_required AS aspect_required,
                a.active AS aspect_active
            FROM hospitality_components c
            LEFT JOIN hospitality_aspects a ON a.component_id = c.id
            {where}
            ORDER BY c.sort_order, c.id, a.sort_order, a.id
            """,
            params,
        )
        rows = cur.fetchall() or []

    components: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for row in rows:
        comp_id = row["component_id"]
        if current is None or current.get("id") != comp_id:
            current = {
                "id": comp_id,
                "name": row["component_name"],
                "description": row["component_description"],
                "sort_order": row["component_sort"],
                "active": row.get("component_active", True),
                "is_required": row.get("component_required", True),
                "aspects": [],
            }
            components.append(current)
        if row["aspect_id"] is not None:
            current["aspects"].append(
                {
                    "id": row["aspect_id"],
                    "name": row["aspect_name"],
                    "description": row["aspect_description"],
                    "sort_order": row["aspect_sort"],
                    "is_required": bool(row["aspect_required"]),
                    "active": row.get("aspect_active", True),
                }
            )
    return components


def ensure_daily_limit(*, school_id: int, staff_id: int, max_per_day: int = 1) -> None:
    """Raise ValueError if staff already submitted max assessments for school today."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM hospitality_assessments
            WHERE school_id = %s AND staff_id = %s
              AND (created_at AT TIME ZONE 'Asia/Jakarta')::date = %s::date
            """,
            (school_id, staff_id, _today_jakarta()),
        )
        row = cur.fetchone() or {}
        if int(row.get("cnt", 0)) >= max_per_day:
            raise ValueError("Sudah ada penilaian untuk sekolah ini hari ini oleh staff yang sama.")


def create_assessment(
    *,
    school_id: int,
    staff_id: int,
    score_scale_max: int = HOSPITALITY_SCORE_MAX,
    note_text: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_daily_limit(school_id=school_id, staff_id=staff_id, max_per_day=1)
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO hospitality_assessments (school_id, staff_id, status, score_scale_max, note_text)
            VALUES (%s, %s, 'draft', %s, %s)
            RETURNING *
            """,
            (school_id, staff_id, score_scale_max, note_text),
        )
        return dict(cur.fetchone())


def get_draft_assessment(*, school_id: int, staff_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, s.name AS school_name, s.npsn, s.jenjang,
                   u.full_name AS staff_name
            FROM hospitality_assessments a
            JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN dashboard_users u ON u.id = a.staff_id
            WHERE a.school_id = %s AND a.staff_id = %s AND a.status = 'draft'
            ORDER BY a.updated_at DESC, a.created_at DESC
            LIMIT 1
            """,
            (school_id, staff_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_latest_draft_assessment_for_staff(*, staff_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, s.name AS school_name, s.npsn, s.jenjang,
                   u.full_name AS staff_name
            FROM hospitality_assessments a
            JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN dashboard_users u ON u.id = a.staff_id
            WHERE a.staff_id = %s AND a.status = 'draft'
            ORDER BY a.updated_at DESC, a.created_at DESC
            LIMIT 1
            """,
            (staff_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_latest_assessment_for_staff_school(*, school_id: int, staff_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, s.name AS school_name, s.npsn, s.jenjang,
                   u.full_name AS staff_name
            FROM hospitality_assessments a
            JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN dashboard_users u ON u.id = a.staff_id
            WHERE a.school_id = %s AND a.staff_id = %s
            ORDER BY a.updated_at DESC, a.created_at DESC
            LIMIT 1
            """,
            (school_id, staff_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def upsert_scores(
    *,
    assessment_id: int,
    scores: Sequence[Dict[str, Any]],
) -> None:
    if not scores:
        return
    rows = []
    for item in scores:
        try:
            aspect_id = int(item.get("aspect_id"))
            component_id = int(item.get("component_id"))
            score = int(item.get("score"))
        except (TypeError, ValueError):
            continue
        note_text = (item.get("note") or "").strip() or None
        rows.append((assessment_id, component_id, aspect_id, score, note_text))
    if not rows:
        return
    with get_cursor(commit=True) as cur:
        cur.executemany(
            """
            INSERT INTO hospitality_assessment_scores (assessment_id, component_id, aspect_id, score, note)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (assessment_id, aspect_id) DO UPDATE
            SET score = EXCLUDED.score,
                note = EXCLUDED.note,
                component_id = EXCLUDED.component_id,
                updated_at = NOW()
            """,
            rows,
        )


def submit_assessment(
    *,
    assessment_id: int,
    note_text: Optional[str] = None,
    score_scale_max: int = HOSPITALITY_SCORE_MAX,
) -> Dict[str, Any]:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE hospitality_assessments
            SET status = 'submitted',
                note_text = %s,
                score_scale_max = %s,
                submitted_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (note_text, score_scale_max, assessment_id),
        )
        row = cur.fetchone()
    return dict(row) if row else {}


def list_assessments_for_staff(
    *,
    staff_id: int,
    status: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    clauses = ["a.staff_id = %s"]
    params: List[Any] = [staff_id]
    if status:
        clauses.append("LOWER(a.status) = %s")
        params.append(status.lower())
    if search:
        clauses.append("(s.name ILIKE %s OR s.npsn ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])
    where = " AND ".join(clauses)
    params.append(limit)
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT a.*, s.name AS school_name, s.npsn, s.jenjang,
                   g.transaction_id AS guestbook_transaction_id
            FROM hospitality_assessments a
            JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN hospitality_assessment_guestbook_links g ON g.assessment_id = a.id
            WHERE {where}
            ORDER BY a.created_at DESC
            LIMIT %s
            """,
            params,
        )
        return [dict(row) for row in cur.fetchall()]


def list_assessments_for_school(
    *,
    school_id: int,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, u.full_name AS staff_name,
                   g.transaction_id AS guestbook_transaction_id
            FROM hospitality_assessments a
            LEFT JOIN dashboard_users u ON u.id = a.staff_id
            LEFT JOIN hospitality_assessment_guestbook_links g ON g.assessment_id = a.id
            WHERE a.school_id = %s
            ORDER BY a.created_at DESC
            LIMIT %s
            """,
            (school_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def fetch_stats() -> Dict[str, Any]:
    """Return aggregate hospitality stats."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE TRUE) AS total_assessments,
                COUNT(*) FILTER (WHERE status = 'verified') AS verified_assessments,
                COUNT(*) FILTER (WHERE status = 'submitted') AS pending_assessments,
                COUNT(DISTINCT school_id) AS unique_schools,
                COUNT(*) FILTER (
                    WHERE (created_at AT TIME ZONE 'Asia/Jakarta')::date = (NOW() AT TIME ZONE 'Asia/Jakarta')::date
                ) AS today_assessments
            FROM hospitality_assessments
            """
        )
        row = cur.fetchone() or {}

        cur.execute(
            """
            WITH scored AS (
                SELECT
                    a.id,
                    AVG(s.score)::DECIMAL(10,2) AS avg_score,
                    MAX(a.score_scale_max) AS scale_max
                FROM hospitality_assessments a
                JOIN hospitality_assessment_scores s ON s.assessment_id = a.id
                WHERE a.status IN ('submitted', 'verified')
                GROUP BY a.id
            )
            SELECT AVG(
                CASE WHEN scale_max > 0 THEN (avg_score / scale_max) * 100 ELSE NULL END
            )::DECIMAL(5,2) AS avg_score_pct
            FROM scored
            """
        )
        avg_row = cur.fetchone() or {}

    return {
        "total_assessments": int(row.get("total_assessments") or 0),
        "verified_assessments": int(row.get("verified_assessments") or 0),
        "pending_assessments": int(row.get("pending_assessments") or 0),
        "unique_schools": int(row.get("unique_schools") or 0),
        "today_assessments": int(row.get("today_assessments") or 0),
        "avg_score_pct": float(avg_row.get("avg_score_pct") or 0),
    }


def fetch_daily_trend(*, days: int = 30) -> List[Dict[str, Any]]:
    """Daily count of hospitality assessments (submitted/verified)."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                (created_at AT TIME ZONE 'Asia/Jakarta')::date AS day,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'verified') AS verified
            FROM hospitality_assessments
            WHERE created_at >= (NOW() AT TIME ZONE 'Asia/Jakarta') - INTERVAL '%s days'
            GROUP BY day
            ORDER BY day ASC
            """,
            (days,),
        )
        return [dict(row) for row in cur.fetchall()]


def fetch_top_schools(*, limit: int = 10) -> List[Dict[str, Any]]:
    """Top schools by average score percentage."""
    with get_cursor() as cur:
        cur.execute(
            """
            WITH scored AS (
                SELECT
                    a.id,
                    a.school_id,
                    AVG(s.score)::DECIMAL(10,2) AS avg_score,
                    MAX(a.score_scale_max) AS scale_max
                FROM hospitality_assessments a
                JOIN hospitality_assessment_scores s ON s.assessment_id = a.id
                WHERE a.status IN ('submitted','verified')
                GROUP BY a.id, a.school_id
            )
            SELECT
                sc.school_id,
                sch.name AS school_name,
                sch.npsn,
                sch.jenjang,
                COUNT(*) AS assessment_count,
                AVG(
                    CASE WHEN sc.scale_max > 0 THEN (sc.avg_score / sc.scale_max) * 100 ELSE 0 END
                )::DECIMAL(5,2) AS avg_pct
            FROM scored sc
            JOIN portal_schools sch ON sch.id = sc.school_id
            GROUP BY sc.school_id, sch.name, sch.npsn, sch.jenjang
            HAVING COUNT(*) > 0
            ORDER BY avg_pct DESC NULLS LAST, assessment_count DESC, sch.name ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def fetch_bottom_schools(*, limit: int = 10) -> List[Dict[str, Any]]:
    """Bottom schools by average score percentage (lowest first)."""
    with get_cursor() as cur:
        cur.execute(
            """
            WITH scored AS (
                SELECT
                    a.id,
                    a.school_id,
                    AVG(s.score)::DECIMAL(10,2) AS avg_score,
                    MAX(a.score_scale_max) AS scale_max
                FROM hospitality_assessments a
                JOIN hospitality_assessment_scores s ON s.assessment_id = a.id
                WHERE a.status IN ('submitted','verified')
                GROUP BY a.id, a.school_id
            )
            SELECT
                sc.school_id,
                sch.name AS school_name,
                sch.npsn,
                sch.jenjang,
                COUNT(*) AS assessment_count,
                AVG(
                    CASE WHEN sc.scale_max > 0 THEN (sc.avg_score / sc.scale_max) * 100 ELSE 0 END
                )::DECIMAL(5,2) AS avg_pct
            FROM scored sc
            JOIN portal_schools sch ON sch.id = sc.school_id
            GROUP BY sc.school_id, sch.name, sch.npsn, sch.jenjang
            HAVING COUNT(*) > 0
            ORDER BY avg_pct ASC NULLS LAST, assessment_count DESC, sch.name ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def fetch_recent_assessments(*, limit: int = 20) -> List[Dict[str, Any]]:
    """Recent assessments with link info."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                a.id,
                a.school_id,
                s.name AS school_name,
                s.npsn,
                a.status,
                a.created_at,
                a.verified_at,
                u.full_name AS staff_name,
                g.transaction_id AS guestbook_transaction_id
            FROM hospitality_assessments a
            JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN dashboard_users u ON u.id = a.staff_id
            LEFT JOIN hospitality_assessment_guestbook_links g ON g.assessment_id = a.id
            ORDER BY a.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def fetch_linked_photos(*, limit: int = 12) -> List[Dict[str, Any]]:
    """Fetch guestbook photos linked to hospitality assessments."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                g.transaction_id,
                t.photo_path,
                t.visit_at,
                s.name AS school_name,
                s.npsn,
                a.id AS assessment_id
            FROM hospitality_assessment_guestbook_links g
            JOIN daftar_tamu_transactions t ON t.id = g.transaction_id
            JOIN hospitality_assessments a ON a.id = g.assessment_id
            JOIN portal_schools s ON s.id = a.school_id
            WHERE t.photo_path IS NOT NULL
            ORDER BY t.visit_at DESC, t.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def _build_guestbook_review_filters(
    *,
    school_id: int | None = None,
    review_status: str | None = None,
    transaction_status: str | None = None,
    rating: int | None = None,
    search: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["TRUE"]
    params: list[Any] = []

    if school_id:
        clauses.append("r.school_id = %s")
        params.append(school_id)

    clean_review_status = (review_status or "").strip().lower()
    if clean_review_status and clean_review_status != "all" and clean_review_status in GUESTBOOK_REVIEW_STATUSES:
        clauses.append("LOWER(r.status) = %s")
        params.append(clean_review_status)

    clean_transaction_status = (transaction_status or "").strip().lower()
    if clean_transaction_status and clean_transaction_status != "all" and clean_transaction_status in {"pending", "approved", "rejected"}:
        clauses.append("LOWER(t.status) = %s")
        params.append(clean_transaction_status)

    if rating is not None:
        try:
            clean_rating = int(rating)
        except (TypeError, ValueError):
            clean_rating = 0
        if 1 <= clean_rating <= 5:
            clauses.append("r.rating = %s")
            params.append(clean_rating)

    if start_date:
        clauses.append("COALESCE(r.completed_at, r.created_at)::date >= %s::date")
        params.append(start_date)
    if end_date:
        clauses.append("COALESCE(r.completed_at, r.created_at)::date <= %s::date")
        params.append(end_date)

    clean_search = (search or "").strip()
    if clean_search:
        like = f"%{clean_search}%"
        clauses.append(
            """
            (
                s.name ILIKE %s
                OR s.npsn ILIKE %s
                OR COALESCE(t.purpose, '') ILIKE %s
                OR COALESCE(t.notes, '') ILIKE %s
                OR COALESCE(r.comment, '') ILIKE %s
                OR EXISTS (
                    SELECT 1
                    FROM daftar_tamu_general_transaction_guests g
                    WHERE g.transaction_id = t.id
                      AND (
                        g.full_name ILIKE %s
                        OR COALESCE(g.phone, '') ILIKE %s
                        OR COALESCE(g.email, '') ILIKE %s
                    )
                )
            )
            """
        )
        params.extend([like, like, like, like, like, like, like, like])

    return " AND ".join(clauses), params


def fetch_guestbook_review_stats(
    *,
    school_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Dict[str, Any]:
    where_sql, params = _build_guestbook_review_filters(
        school_id=school_id,
        start_date=start_date,
        end_date=end_date,
    )
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                COUNT(*) AS total_reviews,
                COUNT(*) FILTER (WHERE r.status = 'completed') AS completed_reviews,
                COUNT(*) FILTER (WHERE r.status = 'pending') AS pending_reviews,
                COUNT(*) FILTER (WHERE gl.assessment_id IS NOT NULL) AS linked_reviews,
                COUNT(*) FILTER (WHERE gl.assessment_id IS NULL) AS unlinked_reviews,
                COUNT(*) FILTER (
                    WHERE r.status = 'completed'
                      AND (r.completed_at AT TIME ZONE 'Asia/Jakarta')::date = (NOW() AT TIME ZONE 'Asia/Jakarta')::date
                ) AS completed_today,
                COUNT(*) FILTER (
                    WHERE (r.created_at AT TIME ZONE 'Asia/Jakarta')::date = (NOW() AT TIME ZONE 'Asia/Jakarta')::date
                ) AS created_today,
                COALESCE(AVG(r.rating) FILTER (WHERE r.status = 'completed'), 0) AS avg_rating,
                COALESCE(AVG(r.rating) FILTER (WHERE r.status = 'completed' AND r.rating IS NOT NULL), 0) AS avg_rating_completed
            FROM hospitality_guestbook_reviews r
            JOIN daftar_tamu_general_transactions t ON t.id = r.transaction_id
            JOIN portal_schools s ON s.id = r.school_id
            LEFT JOIN hospitality_assessment_guestbook_links gl ON gl.transaction_id = t.id
            WHERE {where_sql}
            """,
            params,
        )
        row = cur.fetchone() or {}

    total_reviews = int(row.get("total_reviews") or 0)
    completed_reviews = int(row.get("completed_reviews") or 0)
    pending_reviews = int(row.get("pending_reviews") or 0)
    linked_reviews = int(row.get("linked_reviews") or 0)
    unlinked_reviews = int(row.get("unlinked_reviews") or 0)
    completion_rate = (completed_reviews / total_reviews * 100) if total_reviews else 0.0
    linked_rate = (linked_reviews / total_reviews * 100) if total_reviews else 0.0
    avg_rating = float(row.get("avg_rating") or 0)
    return {
        "total_reviews": total_reviews,
        "completed_reviews": completed_reviews,
        "pending_reviews": pending_reviews,
        "linked_reviews": linked_reviews,
        "unlinked_reviews": unlinked_reviews,
        "completed_today": int(row.get("completed_today") or 0),
        "created_today": int(row.get("created_today") or 0),
        "avg_rating": avg_rating,
        "avg_rating_completed": float(row.get("avg_rating_completed") or 0),
        "completion_rate": round(completion_rate, 2),
        "linked_rate": round(linked_rate, 2),
    }


def fetch_guestbook_review_trend(
    *,
    days: int = 30,
    school_id: int | None = None,
) -> List[Dict[str, Any]]:
    safe_days = max(1, int(days or 30))
    today = _today_jakarta()
    start = today - timedelta(days=safe_days - 1)
    where_sql, params = _build_guestbook_review_filters(
        school_id=school_id,
        start_date=start,
    )
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                (COALESCE(r.completed_at, r.created_at) AT TIME ZONE 'Asia/Jakarta')::date AS day,
                COUNT(*) AS total_reviews,
                COUNT(*) FILTER (WHERE r.status = 'completed') AS completed_reviews,
                COUNT(*) FILTER (WHERE r.status = 'pending') AS pending_reviews,
                COALESCE(AVG(r.rating) FILTER (WHERE r.status = 'completed'), 0) AS avg_rating
            FROM hospitality_guestbook_reviews r
            JOIN daftar_tamu_general_transactions t ON t.id = r.transaction_id
            JOIN portal_schools s ON s.id = r.school_id
            WHERE {where_sql}
            GROUP BY day
            ORDER BY day ASC
            """,
            params,
        )
        rows = [dict(row) for row in cur.fetchall()]

    rows_by_day = {row.get("day"): row for row in rows}
    trend_rows: List[Dict[str, Any]] = []
    current = start
    while current <= today:
        row = rows_by_day.get(current) or {}
        trend_rows.append(
            {
                "day": current.isoformat(),
                "total_reviews": int(row.get("total_reviews") or 0),
                "completed_reviews": int(row.get("completed_reviews") or 0),
                "pending_reviews": int(row.get("pending_reviews") or 0),
                "avg_rating": float(row.get("avg_rating") or 0),
            }
        )
        current += timedelta(days=1)
    return trend_rows


def fetch_guestbook_review_rating_distribution(
    *,
    school_id: int | None = None,
) -> List[Dict[str, Any]]:
    where_sql, params = _build_guestbook_review_filters(
        school_id=school_id,
        review_status="completed",
    )
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                r.rating,
                COUNT(*) AS total
            FROM hospitality_guestbook_reviews r
            JOIN daftar_tamu_general_transactions t ON t.id = r.transaction_id
            JOIN portal_schools s ON s.id = r.school_id
            WHERE {where_sql}
              AND r.rating IS NOT NULL
            GROUP BY r.rating
            ORDER BY r.rating ASC
            """,
            params,
        )
        rows = [dict(row) for row in cur.fetchall()]

    counts = {int(row.get("rating") or 0): int(row.get("total") or 0) for row in rows}
    return [
        {"rating": rating, "total": counts.get(rating, 0)}
        for rating in range(1, 6)
    ]


def fetch_guestbook_review_top_schools(*, limit: int = 10) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 10), 100))
    with get_cursor() as cur:
        cur.execute(
            """
            WITH scored AS (
                SELECT
                    r.school_id,
                    r.rating,
                    r.completed_at
                FROM hospitality_guestbook_reviews r
                WHERE r.status = 'completed'
                  AND r.rating IS NOT NULL
            )
            SELECT
                s.id AS school_id,
                s.name AS school_name,
                s.npsn,
                s.jenjang,
                COUNT(*) AS review_count,
                AVG(scored.rating)::DECIMAL(5,2) AS avg_rating,
                MAX(scored.completed_at) AS last_completed_at
            FROM scored
            JOIN portal_schools s ON s.id = scored.school_id
            GROUP BY s.id, s.name, s.npsn, s.jenjang
            HAVING COUNT(*) > 0
            ORDER BY avg_rating DESC NULLS LAST, review_count DESC, s.name ASC
            LIMIT %s
            """,
            (safe_limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def fetch_guestbook_review_bottom_schools(*, limit: int = 10) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 10), 100))
    with get_cursor() as cur:
        cur.execute(
            """
            WITH scored AS (
                SELECT
                    r.school_id,
                    r.rating,
                    r.completed_at
                FROM hospitality_guestbook_reviews r
                WHERE r.status = 'completed'
                  AND r.rating IS NOT NULL
            )
            SELECT
                s.id AS school_id,
                s.name AS school_name,
                s.npsn,
                s.jenjang,
                COUNT(*) AS review_count,
                AVG(scored.rating)::DECIMAL(5,2) AS avg_rating,
                MAX(scored.completed_at) AS last_completed_at
            FROM scored
            JOIN portal_schools s ON s.id = scored.school_id
            GROUP BY s.id, s.name, s.npsn, s.jenjang
            HAVING COUNT(*) > 0
            ORDER BY avg_rating ASC NULLS LAST, review_count DESC, s.name ASC
            LIMIT %s
            """,
            (safe_limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def list_guestbook_reviews(
    *,
    school_id: int | None = None,
    review_status: str | None = None,
    transaction_status: str | None = None,
    rating: int | None = None,
    search: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    per_page: int = 25,
) -> Tuple[List[Dict[str, Any]], int]:
    safe_page = max(1, int(page or 1))
    safe_per_page = max(1, min(int(per_page or 25), 200))
    offset = (safe_page - 1) * safe_per_page
    where_sql, params = _build_guestbook_review_filters(
        school_id=school_id,
        review_status=review_status,
        transaction_status=transaction_status,
        rating=rating,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM hospitality_guestbook_reviews r
        JOIN daftar_tamu_general_transactions t ON t.id = r.transaction_id
        JOIN portal_schools s ON s.id = r.school_id
        WHERE {where_sql}
    """
    data_query = f"""
        SELECT
            r.id AS review_id,
            r.transaction_id,
            r.school_id,
            s.name AS school_name,
            s.npsn,
            s.jenjang,
            r.review_token,
            r.status AS review_status,
            r.rating,
            r.comment,
            r.completed_at,
            r.created_at AS review_created_at,
            r.updated_at AS review_updated_at,
            t.visit_at,
            t.status AS transaction_status,
            t.purpose,
            t.notes,
            t.created_at AS transaction_created_at,
            gl.assessment_id AS linked_assessment_id,
            gl.linked_by AS linked_by,
            gl.linked_at AS linked_at,
            ha.status AS linked_assessment_status,
            ha.created_at AS linked_assessment_created_at,
            hu.full_name AS linked_assessment_staff_name,
            (
                SELECT STRING_AGG(g.full_name, ', ' ORDER BY g.full_name)
                FROM daftar_tamu_general_transaction_guests g
                WHERE g.transaction_id = t.id
            ) AS guest_names,
            (
                SELECT COUNT(*)
                FROM daftar_tamu_general_transaction_guests g
                WHERE g.transaction_id = t.id
            ) AS guest_count,
            COALESCE(r.completed_at, r.created_at) AS activity_at
        FROM hospitality_guestbook_reviews r
        JOIN daftar_tamu_general_transactions t ON t.id = r.transaction_id
        JOIN portal_schools s ON s.id = r.school_id
        LEFT JOIN hospitality_assessment_guestbook_links gl ON gl.transaction_id = t.id
        LEFT JOIN hospitality_assessments ha ON ha.id = gl.assessment_id
        LEFT JOIN dashboard_users hu ON hu.id = ha.staff_id
        WHERE {where_sql}
        ORDER BY COALESCE(r.completed_at, r.created_at) DESC NULLS LAST, r.id DESC
        LIMIT %s OFFSET %s
    """

    with get_cursor() as cur:
        cur.execute(count_query, params)
        total_rows = int((cur.fetchone() or {}).get("total") or 0)
        cur.execute(data_query, params + [safe_per_page, offset])
        rows = [dict(row) for row in cur.fetchall()]

    for row in rows:
        names_raw = row.get("guest_names") or ""
        names = [name.strip() for name in names_raw.split(",") if name.strip()]
        row["guest_names_list"] = names
        row["guest_count"] = int(row.get("guest_count") or len(names))
        if names:
            if len(names) > 2:
                row["guest_display"] = f"{names[0]} +{len(names) - 1}"
            elif len(names) == 2:
                row["guest_display"] = f"{names[0]} & {names[1]}"
            else:
                row["guest_display"] = names[0]
        else:
            row["guest_display"] = None
        row["review_status"] = (row.get("review_status") or "").strip().lower()
        row["transaction_status"] = (row.get("transaction_status") or "").strip().lower()
        row["linked_assessment_id"] = int(row.get("linked_assessment_id")) if row.get("linked_assessment_id") is not None else None
        rating_val = row.get("rating")
        row["rating"] = int(rating_val) if rating_val is not None else None
        comment = (row.get("comment") or "").strip()
        row["comment_preview"] = comment[:140] if comment else ""

    return rows, total_rows


def fetch_guestbook_reviews_export(
    *,
    school_id: int | None = None,
    review_status: str | None = None,
    transaction_status: str | None = None,
    rating: int | None = None,
    search: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> List[Dict[str, Any]]:
    where_sql, params = _build_guestbook_review_filters(
        school_id=school_id,
        review_status=review_status,
        transaction_status=transaction_status,
        rating=rating,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )
    query = f"""
        SELECT
            r.id AS review_id,
            r.transaction_id,
            r.school_id,
            s.name AS school_name,
            s.npsn,
            s.jenjang,
            r.review_token,
            r.status AS review_status,
            r.rating,
            r.comment,
            r.completed_at,
            r.created_at AS review_created_at,
            r.updated_at AS review_updated_at,
            t.visit_at,
            t.status AS transaction_status,
            t.purpose,
            t.notes,
            t.created_at AS transaction_created_at,
            gl.assessment_id AS linked_assessment_id,
            gl.linked_by AS linked_by,
            gl.linked_at AS linked_at,
            ha.status AS linked_assessment_status,
            ha.created_at AS linked_assessment_created_at,
            hu.full_name AS linked_assessment_staff_name,
            (
                SELECT STRING_AGG(g.full_name, ', ' ORDER BY g.full_name)
                FROM daftar_tamu_general_transaction_guests g
                WHERE g.transaction_id = t.id
            ) AS guest_names,
            (
                SELECT COUNT(*)
                FROM daftar_tamu_general_transaction_guests g
                WHERE g.transaction_id = t.id
            ) AS guest_count,
            COALESCE(r.completed_at, r.created_at) AS activity_at
        FROM hospitality_guestbook_reviews r
        JOIN daftar_tamu_general_transactions t ON t.id = r.transaction_id
        JOIN portal_schools s ON s.id = r.school_id
        LEFT JOIN hospitality_assessment_guestbook_links gl ON gl.transaction_id = t.id
        LEFT JOIN hospitality_assessments ha ON ha.id = gl.assessment_id
        LEFT JOIN dashboard_users hu ON hu.id = ha.staff_id
        WHERE {where_sql}
        ORDER BY COALESCE(r.completed_at, r.created_at) DESC NULLS LAST, r.id DESC
    """
    with get_cursor() as cur:
        cur.execute(query, params)
        rows = [dict(row) for row in cur.fetchall()]

    for row in rows:
        names_raw = row.get("guest_names") or ""
        names = [name.strip() for name in names_raw.split(",") if name.strip()]
        row["guest_names_list"] = names
        row["guest_count"] = int(row.get("guest_count") or len(names))
        if names:
            if len(names) > 2:
                row["guest_display"] = f"{names[0]} +{len(names) - 1}"
            elif len(names) == 2:
                row["guest_display"] = f"{names[0]} & {names[1]}"
            else:
                row["guest_display"] = names[0]
        else:
            row["guest_display"] = None
        row["review_status"] = (row.get("review_status") or "").strip().lower()
        row["transaction_status"] = (row.get("transaction_status") or "").strip().lower()
        row["linked_assessment_id"] = int(row.get("linked_assessment_id")) if row.get("linked_assessment_id") is not None else None
        rating_val = row.get("rating")
        row["rating"] = int(rating_val) if rating_val is not None else None
        comment = (row.get("comment") or "").strip()
        row["comment_preview"] = comment[:140] if comment else ""

    return rows


def get_guestbook_review_detail(review_id: int) -> Dict[str, Any] | None:
    if not review_id:
        return None
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                r.id AS review_id,
                r.transaction_id,
                r.school_id,
                s.name AS school_name,
                s.npsn,
                s.jenjang,
                r.review_token,
                r.status AS review_status,
                r.rating,
                r.comment,
                r.completed_at,
                r.created_at AS review_created_at,
                r.updated_at AS review_updated_at,
                t.visit_at,
                t.status AS transaction_status,
                t.purpose,
                t.notes,
                t.created_at AS transaction_created_at,
                gl.assessment_id AS linked_assessment_id,
                gl.linked_by AS linked_by,
                gl.linked_at AS linked_at,
                ha.status AS linked_assessment_status,
                ha.created_at AS linked_assessment_created_at,
                hu.full_name AS linked_assessment_staff_name,
                (
                    SELECT STRING_AGG(g.full_name, ', ' ORDER BY g.full_name)
                    FROM daftar_tamu_general_transaction_guests g
                    WHERE g.transaction_id = t.id
                ) AS guest_names,
                (
                    SELECT COUNT(*)
                    FROM daftar_tamu_general_transaction_guests g
                    WHERE g.transaction_id = t.id
                ) AS guest_count,
                COALESCE(r.completed_at, r.created_at) AS activity_at
            FROM hospitality_guestbook_reviews r
            JOIN daftar_tamu_general_transactions t ON t.id = r.transaction_id
            JOIN portal_schools s ON s.id = r.school_id
            LEFT JOIN hospitality_assessment_guestbook_links gl ON gl.transaction_id = t.id
            LEFT JOIN hospitality_assessments ha ON ha.id = gl.assessment_id
            LEFT JOIN dashboard_users hu ON hu.id = ha.staff_id
            WHERE r.id = %s
            LIMIT 1
            """,
            (review_id,),
        )
        row = cur.fetchone()

    if not row:
        return None
    detail = dict(row)
    names_raw = detail.get("guest_names") or ""
    names = [name.strip() for name in names_raw.split(",") if name.strip()]
    detail["guest_names_list"] = names
    detail["guest_count"] = int(detail.get("guest_count") or len(names))
    if names:
        if len(names) > 2:
            detail["guest_display"] = f"{names[0]} +{len(names) - 1}"
        elif len(names) == 2:
            detail["guest_display"] = f"{names[0]} & {names[1]}"
        else:
            detail["guest_display"] = names[0]
    else:
        detail["guest_display"] = None
    detail["review_status"] = (detail.get("review_status") or "").strip().lower()
    detail["transaction_status"] = (detail.get("transaction_status") or "").strip().lower()
    detail["linked_assessment_id"] = int(detail.get("linked_assessment_id")) if detail.get("linked_assessment_id") is not None else None
    rating_val = detail.get("rating")
    detail["rating"] = int(rating_val) if rating_val is not None else None
    return detail


# ===== Master data (component / aspect) =====

def create_component(
    *,
    name: str,
    description: str | None = None,
    sort_order: int = 0,
    is_required: bool = True,
    active: bool = True,
) -> Dict[str, Any]:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO hospitality_components (name, description, sort_order, is_required, active)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (LOWER(name)) DO NOTHING
            RETURNING *
            """,
            (name, description, sort_order, is_required, active),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError("Komponen sudah ada.")
    return dict(row)


def get_component(component_id: int) -> Dict[str, Any] | None:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM hospitality_components WHERE id = %s
            """,
            (component_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def update_component(
    *,
    component_id: int,
    name: str,
    description: str | None,
    sort_order: int,
    is_required: bool,
    active: bool,
) -> Dict[str, Any] | None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE hospitality_components
            SET name = %s,
                description = %s,
                sort_order = %s,
                is_required = %s,
                active = %s
            WHERE id = %s
            RETURNING *
            """,
            (name, description, sort_order, is_required, active, component_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def delete_component(component_id: int) -> bool:
    """Soft-delete component if referenced; otherwise hard delete."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt FROM hospitality_assessment_scores WHERE component_id = %s
            """,
            (component_id,),
        )
        cnt = cur.fetchone()["cnt"]
        if cnt and int(cnt) > 0:
            cur.execute(
                "UPDATE hospitality_components SET active = FALSE WHERE id = %s",
                (component_id,),
            )
            return True
        cur.execute("DELETE FROM hospitality_components WHERE id = %s RETURNING id", (component_id,))
    return cur.fetchone() is not None


def toggle_component_active(component_id: int) -> Dict[str, Any] | None:
    comp = get_component(component_id)
    if not comp:
        return None
    return update_component(
        component_id=component_id,
        name=comp.get("name") or "",
        description=comp.get("description"),
        sort_order=int(comp.get("sort_order") or 0),
        is_required=bool(comp.get("is_required")),
        active=not bool(comp.get("active")),
    )


def toggle_component_required(component_id: int) -> Dict[str, Any] | None:
    comp = get_component(component_id)
    if not comp:
        return None
    return update_component(
        component_id=component_id,
        name=comp.get("name") or "",
        description=comp.get("description"),
        sort_order=int(comp.get("sort_order") or 0),
        is_required=not bool(comp.get("is_required")),
        active=bool(comp.get("active")),
    )


def reorder_components(order_ids: list[int]) -> None:
    with get_cursor(commit=True) as cur:
        for idx, cid in enumerate(order_ids):
            cur.execute(
                "UPDATE hospitality_components SET sort_order = %s WHERE id = %s",
                (idx, cid),
            )


def create_hosp_aspect(
    *,
    component_id: int,
    name: str,
    description: str | None = None,
    sort_order: int = 0,
    is_required: bool = True,
    active: bool = True,
) -> Dict[str, Any]:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO hospitality_aspects (component_id, name, description, sort_order, is_required, active)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (component_id, name, description, sort_order, is_required, active),
        )
        row = cur.fetchone()
    return dict(row) if row else {}


def get_hosp_aspect(aspect_id: int) -> Dict[str, Any] | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM hospitality_aspects WHERE id = %s", (aspect_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def update_hosp_aspect(
    *,
    aspect_id: int,
    name: str,
    description: str | None,
    sort_order: int,
    is_required: bool,
    active: bool,
) -> Dict[str, Any] | None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE hospitality_aspects
            SET name = %s,
                description = %s,
                sort_order = %s,
                is_required = %s,
                active = %s
            WHERE id = %s
            RETURNING *
            """,
            (name, description, sort_order, is_required, active, aspect_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def delete_hosp_aspect(aspect_id: int) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM hospitality_assessment_scores WHERE aspect_id = %s",
            (aspect_id,),
        )
        cnt = cur.fetchone()["cnt"]
        if cnt and int(cnt) > 0:
            cur.execute(
                "UPDATE hospitality_aspects SET active = FALSE WHERE id = %s",
                (aspect_id,),
            )
            return True
        cur.execute("DELETE FROM hospitality_aspects WHERE id = %s RETURNING id", (aspect_id,))
        return cur.fetchone() is not None


def toggle_aspect_active(aspect_id: int) -> Dict[str, Any] | None:
    asp = get_hosp_aspect(aspect_id)
    if not asp:
        return None
    return update_hosp_aspect(
        aspect_id=aspect_id,
        name=asp.get("name") or "",
        description=asp.get("description"),
        sort_order=int(asp.get("sort_order") or 0),
        is_required=bool(asp.get("is_required")),
        active=not bool(asp.get("active")),
    )


def toggle_aspect_required(aspect_id: int) -> Dict[str, Any] | None:
    asp = get_hosp_aspect(aspect_id)
    if not asp:
        return None
    return update_hosp_aspect(
        aspect_id=aspect_id,
        name=asp.get("name") or "",
        description=asp.get("description"),
        sort_order=int(asp.get("sort_order") or 0),
        is_required=not bool(asp.get("is_required")),
        active=bool(asp.get("active")),
    )


def reorder_hosp_aspects(order_ids: list[int]) -> None:
    with get_cursor(commit=True) as cur:
        for idx, aid in enumerate(order_ids):
            cur.execute(
                "UPDATE hospitality_aspects SET sort_order = %s WHERE id = %s",
                (idx, aid),
            )

def get_assessment(assessment_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, s.name AS school_name, s.npsn, s.jenjang,
                   u.full_name AS staff_name,
                   g.transaction_id AS guestbook_transaction_id,
                   t.photo_path AS guestbook_photo_path,
                   t.visit_at AS guestbook_visit_at,
                   t.latitude AS guestbook_latitude,
                   t.longitude AS guestbook_longitude
            FROM hospitality_assessments a
            JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN dashboard_users u ON u.id = a.staff_id
            LEFT JOIN hospitality_assessment_guestbook_links g ON g.assessment_id = a.id
            LEFT JOIN daftar_tamu_transactions t ON t.id = g.transaction_id
            WHERE a.id = %s
            """,
            (assessment_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_assessment_scores(assessment_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.assessment_id, s.component_id, s.aspect_id, s.score, s.note,
                   c.name AS component_name, a.name AS aspect_name
            FROM hospitality_assessment_scores s
            LEFT JOIN hospitality_components c ON c.id = s.component_id
            LEFT JOIN hospitality_aspects a ON a.id = s.aspect_id
            WHERE s.assessment_id = %s
            ORDER BY c.sort_order, a.sort_order
            """,
            (assessment_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def list_guestbook_candidates(
    *,
    school_id: int,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """List approved guestbook transactions for a school with flags for linking priority."""
    today = _today_jakarta()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                t.id,
                t.visit_at,
                t.status,
                t.purpose,
                t.photo_path,
                t.latitude,
                t.longitude,
                t.created_at,
                EXISTS(
                    SELECT 1 FROM hospitality_assessment_guestbook_links l
                    WHERE l.transaction_id = t.id
                ) AS is_linked
            FROM daftar_tamu_transactions t
            WHERE t.school_id = %s
              AND t.status = 'approved'
            ORDER BY t.visit_at DESC, t.id DESC
            LIMIT %s
            """,
            (school_id, limit),
        )
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        visit_date = row.get("visit_at")
        is_same_day = False
        if isinstance(visit_date, datetime):
            try:
                visit_date = visit_date.astimezone(_JAKARTA_TZ).date()
            except Exception:
                visit_date = visit_date.date()
        if isinstance(visit_date, date):
            is_same_day = visit_date == today
        row["is_same_day"] = is_same_day
    # Sort: same-day & not linked first, then others, linked last
    rows.sort(
        key=lambda r: (
            0 if (r.get("is_same_day") and not r.get("is_linked")) else 1,
            1 if not r.get("is_linked") else 2,
            -(r.get("visit_at").timestamp() if isinstance(r.get("visit_at"), datetime) else 0),
        )
    )
    return rows


def link_guestbook_transaction(
    *,
    assessment_id: int,
    transaction_id: int,
    linked_by: Optional[int] = None,
) -> Dict[str, Any]:
    with get_cursor(commit=True) as cur:
        # Ensure transaction approved and not already linked
        cur.execute(
            "SELECT status FROM daftar_tamu_transactions WHERE id = %s",
            (transaction_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Transaksi buku tamu tidak ditemukan")
        if (row.get("status") or "").lower() != "approved":
            raise ValueError("Transaksi buku tamu belum terverifikasi")

        cur.execute(
            """
            INSERT INTO hospitality_assessment_guestbook_links (assessment_id, transaction_id, linked_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (assessment_id) DO UPDATE
            SET transaction_id = EXCLUDED.transaction_id,
                linked_by = EXCLUDED.linked_by,
                linked_at = NOW()
            RETURNING assessment_id, transaction_id, linked_at
            """,
            (assessment_id, transaction_id, linked_by),
        )
        link_row = cur.fetchone()

        cur.execute(
            """
            UPDATE hospitality_assessments
            SET status = 'verified', verified_at = NOW(), updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (assessment_id,),
        )
        assessment = cur.fetchone()

    return {"link": dict(link_row), "assessment": dict(assessment) if assessment else None}


def create_comment(
    *, assessment_id: int, author_user_id: int, author_role: str, message: str, parent_comment_id: Optional[int] = None
) -> Dict[str, Any]:
    clean_msg = (message or "").strip()
    if not clean_msg:
        raise ValueError("Pesan komentar wajib diisi")
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO hospitality_assessment_comments (
                assessment_id, author_user_id, author_role, message, parent_comment_id
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (assessment_id, author_user_id, author_role, clean_msg, parent_comment_id),
        )
        return dict(cur.fetchone())


def list_comments(assessment_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT c.*, u.full_name AS author_name
            FROM hospitality_assessment_comments c
            LEFT JOIN dashboard_users u ON u.id = c.author_user_id
            WHERE c.assessment_id = %s
            ORDER BY c.created_at ASC, c.id ASC
            """,
            (assessment_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def create_reopen_request(
    *, assessment_id: int, staff_id: int, reason: Optional[str]
) -> Dict[str, Any]:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO hospitality_reopen_requests (
                assessment_id, staff_id, reason, status
            ) VALUES (%s, %s, %s, 'pending')
            RETURNING *
            """,
            (assessment_id, staff_id, reason),
        )
        row = cur.fetchone()
    return dict(row) if row else {}


def list_reopen_requests(*, status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    conditions = []
    params: List[Any] = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT r.*, a.school_id, a.staff_id, a.status AS assessment_status,
                   s.name AS school_name, s.npsn AS npsn, u.full_name AS staff_name
            FROM hospitality_reopen_requests r
            JOIN hospitality_assessments a ON a.id = r.assessment_id
            LEFT JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN dashboard_users u ON u.id = a.staff_id
            {where}
            ORDER BY r.created_at DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [dict(row) for row in cur.fetchall()]


def get_latest_reopen_request(assessment_id: int) -> Optional[Dict[str, Any]]:
    query = """
        SELECT r.*, u.full_name AS staff_name, u.email AS staff_email,
               reviewer.full_name AS reviewer_name, reviewer.email AS reviewer_email
        FROM hospitality_reopen_requests r
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


def get_latest_reopen_request_id(assessment_id: int) -> Optional[int]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM hospitality_reopen_requests
            WHERE assessment_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (assessment_id,),
        )
        row = cur.fetchone()
    return int(row["id"]) if row else None


def update_reopen_request_status(
    *,
    request_id: int,
    status: str,
    reviewer_id: int,
    reviewer_note: Optional[str] = None,
) -> Dict[str, Any]:
    safe_status = (status or "").strip().lower()
    if safe_status not in REOPEN_STATUSES:
        raise ValueError("Status reopen tidak valid")
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE hospitality_reopen_requests
            SET status = %s,
                reviewer_id = %s,
                reviewer_note = %s,
                reviewed_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (safe_status, reviewer_id, reviewer_note, request_id),
        )
        req = cur.fetchone()
        if req and safe_status == "approved":
            cur.execute(
                """
                UPDATE hospitality_assessments
                SET status = 'reopened', reopened_at = NOW(), reopened_by = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (reviewer_id, req["assessment_id"]),
            )
    return dict(req) if req else {}
