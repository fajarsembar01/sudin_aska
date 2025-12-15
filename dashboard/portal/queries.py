"""Database queries for portal assessment system."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from ..db_access import get_cursor


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
            r.id, r.name, r.description, r.category, r.sort_order, r.active,
            COALESCE(
                json_agg(
                    json_build_object(
                        'id', a.id,
                        'name', a.name,
                        'description', a.description,
                        'sort_order', a.sort_order,
                        'active', a.active
                    ) ORDER BY a.sort_order, a.id
                ) FILTER (WHERE a.id IS NOT NULL),
                '[]'
            ) as aspects
        FROM portal_rooms r
        LEFT JOIN portal_aspects a ON a.room_id = r.id {aspect_condition}
        {condition}
        GROUP BY r.id, r.name, r.description, r.category, r.sort_order, r.active
        ORDER BY r.sort_order, r.id
    """
    
    with get_cursor() as cur:
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def list_school_rooms(school_id: int) -> List[Dict[str, Any]]:
    """Fetch rooms configured for a specific school with aspects."""
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
                        'description', a.description
                    ) ORDER BY a.sort_order, a.id
                ) FILTER (WHERE a.id IS NOT NULL),
                '[]'
            ) as aspects
        FROM portal_school_rooms sr
        JOIN portal_rooms r ON r.id = sr.room_id
        LEFT JOIN portal_aspects a ON a.room_id = r.id AND a.active = TRUE
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
    creator_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new draft assessment for the active period (if any)."""
    period = get_active_period()
    period_id = period["id"] if period else None

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_assessments (school_id, staff_id, period_id, status)
            VALUES (%s, %s, %s, 'draft')
            RETURNING id, school_id, staff_id, status, created_at, period_id
            """,
            (school_id, staff_id, period_id),
        )
        # creator_email retained for backward compatibility (not stored yet)
        return dict(cur.fetchone())


def get_assessment_by_id(assessment_id: int) -> Optional[Dict[str, Any]]:
    """Get assessment details with school info."""
    query = """
        SELECT 
            a.id, a.school_id, a.staff_id, a.assessment_date,
            a.status, a.total_score, a.notes, a.submitted_at,
            a.created_at, a.updated_at,
            s.name as school_name, s.npsn, s.jenjang,
            u.full_name as assessor_name, u.email as assessor_email
        FROM portal_assessments a
        JOIN portal_schools s ON s.id = a.school_id
        LEFT JOIN dashboard_users u ON u.id = a.staff_id
        WHERE a.id = %s
    """
    with get_cursor() as cur:
        cur.execute(query, (assessment_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_or_create_draft_assessment(school_id: int, staff_id: int) -> Dict[str, Any]:
    """Get existing draft assessment or create a new one."""
    with get_cursor(commit=True) as cur:
        # Check for existing draft
        cur.execute(
            """
            SELECT id, school_id, staff_id, assessment_date, status, total_score, notes
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
            INSERT INTO portal_assessments (school_id, staff_id, status)
            VALUES (%s, %s, 'draft')
            RETURNING id, school_id, staff_id, assessment_date, status, total_score, notes
            """,
            (school_id, staff_id),
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
            
        cur.execute(
            """
            INSERT INTO portal_assessment_periods (name, start_date, end_date, is_active)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, start_date, end_date, is_active
            """,
            (name, start_date, end_date, is_active),
        )
        return dict(cur.fetchone())

def list_periods() -> List[Dict[str, Any]]:
    """List all assessment periods."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM portal_assessment_periods ORDER BY start_date DESC")
        return [dict(row) for row in cur.fetchall()]

def get_active_period() -> Optional[Dict[str, Any]]:
    """Get the currently active assessment period."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM portal_assessment_periods WHERE is_active = TRUE LIMIT 1")
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
            cur.execute("SELECT id FROM portal_assessment_periods WHERE is_active = TRUE")
            row = cur.fetchone()
            period_id = row["id"] if row else None
        
        cur.execute(
            """
            INSERT INTO portal_assessments (school_id, staff_id, period_id, status)
            VALUES (%s, %s, %s, 'draft')
            RETURNING id
            """,
            (school_id, staff_id, period_id)
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
) -> List[Dict[str, Any]]:
    """Fetch photos for stats gallery, with room score summary.
    
    Returns one photo per unique school+room combination.
    Score is the average of all aspect scores for that room.
    """
    where = "WHERE a.status = 'submitted'"
    params = []
    if period_id:
        where += " AND a.period_id = %s"
        params.append(period_id)
    
    # Use subquery to get one photo per school+room combo with avg score
    query = f"""
        SELECT * FROM (
            SELECT DISTINCT ON (s.id, r.id)
                p.photo_path, 
                s.name as school_name, 
                s.id as school_id,
                a.id as assessment_id,
                r.name as room_name,
                r.id as room_id,
                p.captured_at,
                p.latitude,
                p.longitude,
                (
                    SELECT COALESCE(AVG(sc2.score), 0)::DECIMAL(5,2)
                    FROM portal_assessment_scores sc2
                    JOIN portal_school_rooms sr2 ON sc2.school_room_id = sr2.id
                    WHERE sr2.school_id = s.id AND sr2.room_id = r.id
                ) AS room_score
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
        order_clause = "ORDER BY captured_at DESC NULLS LAST"
    elif order == "lowest":
        order_clause = "ORDER BY room_score ASC NULLS LAST"
    
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


def submit_assessment(assessment_id: int) -> bool:
    """Submit an assessment and calculate total score.
    
    If any aspect hasn't been scored, it defaults to 3 (Baik).
    """
    with get_cursor(commit=True) as cur:
        # 1. Fill missing scores with default 3
        cur.execute(
            """
            INSERT INTO portal_assessment_scores (assessment_id, school_room_id, aspect_id, score, created_at, updated_at)
            SELECT %s, sr.id, pa.id, 3, NOW(), NOW()
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
            (assessment_id, assessment_id, assessment_id),
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
            a.total_score, a.submitted_at, a.created_at,
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


def get_active_assessment(school_id: int, staff_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Get an active draft assessment for a school."""
    query = """
        SELECT *
        FROM portal_assessments
        WHERE school_id = %s AND status = 'draft'
    """
    params = [school_id]
    
    if staff_id:
        query += " AND staff_id = %s"
        params.append(staff_id)
        
    query += " ORDER BY created_at DESC LIMIT 1"

    with get_cursor() as cur:
        cur.execute(query, params)
        return dict(row) if (row := cur.fetchone()) else None


def fetch_portal_stats(period_id: Optional[int] = None) -> Dict[str, Any]:
    """Get aggregate statistics for portal assessments."""
    
    pid_cond = f"AND period_id = {int(period_id)}" if period_id else ""

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 
                COUNT(*) as total_schools,
                COUNT(*) FILTER (WHERE active) as active_schools
            FROM portal_schools
            """
        )
        schools = dict(cur.fetchone())
        
        query = f"""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'draft' {pid_cond}) as drafts,
                COUNT(*) FILTER (WHERE status = 'submitted' {pid_cond}) as submitted,
                AVG(total_score) FILTER (WHERE status = 'submitted' {pid_cond}) as avg_score
            FROM portal_assessments
            WHERE 1=1 {pid_cond}
        """
        # Note: if period_id is provided, total count restricts to period.
        
        cur.execute(query)
        assess_stats = dict(cur.fetchone())
        
        return {
            "schools": schools,
            "assessments": assess_stats,
        }


def fetch_score_distribution(period_id: Optional[int] = None) -> List[int]:
    """Calculate score distribution (9 bins: <60, 60-65, ..., 95-100)."""
    where_clause = "WHERE status = 'submitted' AND total_score IS NOT NULL"
    params = []
    
    if period_id:
        where_clause += " AND period_id = %s"
        params.append(period_id)
        
    query = f"SELECT total_score FROM portal_assessments {where_clause}"
    
    distribution = [0] * 9  # 9 Buckets
    
    with get_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        
        for row in rows:
            score = row['total_score']
            if score is None: continue
            
            score_100 = (float(score) / 3.0) * 100
            
            if score_100 < 60:
                idx = 0
            elif score_100 >= 95:
                idx = 8
            else:
                # Range 60 <= score < 95
                # 60-65 -> idx 1
                # 65-70 -> idx 2
                idx = int((score_100 - 60) // 5) + 1
            
            if 0 <= idx < 9:
                distribution[idx] += 1
            
    return distribution



def fetch_map_data(period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch school locations and status for the map.
    
    Returns one marker per school with:
    - Average school score (from all assessments, not per room)
    - Location from the most recent photo that has GPS coordinates
    """
    params = []
    period_filter = ""
    if period_id:
        period_filter = "AND a.period_id = %s"
        params.append(period_id)
    
    # Subquery to get most recent photo with GPS per school
    query = f"""
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
                FROM portal_assessments a2
                WHERE a2.school_id = s.id 
                  AND a2.status = 'submitted'
                  AND a2.total_score IS NOT NULL
                  {period_filter}
            ) AS school_avg_score,
            -- Get latest status
            (
                SELECT a3.status 
                FROM portal_assessments a3 
                WHERE a3.school_id = s.id 
                  AND a3.status = 'submitted'
                  {period_filter}
                ORDER BY a3.submitted_at DESC NULLS LAST
                LIMIT 1
            ) AS status,
            -- Get location from most recent photo with GPS
            (
                SELECT p.latitude 
                FROM portal_assessment_photos p
                JOIN portal_assessments a4 ON p.assessment_id = a4.id
                WHERE a4.school_id = s.id 
                  AND p.latitude IS NOT NULL
                  {period_filter}
                ORDER BY p.captured_at DESC NULLS LAST
                LIMIT 1
            ) AS latitude,
            (
                SELECT p.longitude 
                FROM portal_assessment_photos p
                JOIN portal_assessments a5 ON p.assessment_id = a5.id
                WHERE a5.school_id = s.id 
                  AND p.longitude IS NOT NULL
                  {period_filter}
                ORDER BY p.captured_at DESC NULLS LAST
                LIMIT 1
            ) AS longitude
        FROM portal_schools s
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        WHERE EXISTS (
            SELECT 1 FROM portal_assessments a 
            WHERE a.school_id = s.id 
              AND a.status = 'submitted'
              {period_filter}
        )
    """
    
    # Duplicate params for each subquery that uses period_filter (5 times)
    if period_id:
        params = [period_id] * 5
    
    with get_cursor() as cur:
        cur.execute(query, params)
        data = []
        for row in cur.fetchall():
            item = dict(row)
            # Only include schools with valid GPS
            if not item.get('latitude') or not item.get('longitude'):
                continue
            if item.get('latitude'): item['latitude'] = float(item['latitude'])
            if item.get('longitude'): item['longitude'] = float(item['longitude'])
            if item.get('school_avg_score') is not None: 
                item['total_score'] = float(item['school_avg_score'])
            else:
                item['total_score'] = None
            data.append(item)
        return data


def fetch_top_schools(limit: int = 5, period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch top performing schools based on their latest assessment."""
    where = "WHERE a.status = 'submitted'"
    params = []
    if period_id:
        where += " AND a.period_id = %s"
        params.append(period_id)
    
    params.append(limit)
        
    query = f"""
            SELECT * FROM (
                SELECT DISTINCT ON (a.school_id)
                    s.name,
                    s.jenjang,
                    a.total_score,
                    a.submitted_at
                FROM portal_assessments a
                JOIN portal_schools s ON a.school_id = s.id
                {where}
                ORDER BY a.school_id, a.submitted_at DESC
            ) sub
            ORDER BY total_score DESC
            LIMIT %s
            """
            
    with get_cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

def fetch_bottom_schools(limit: int = 5, period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch lowest performing schools based on their latest assessment."""
    where = "WHERE a.status = 'submitted'"
    params = []
    if period_id:
        where += " AND a.period_id = %s"
        params.append(period_id)
    
    params.append(limit)
        
    query = f"""
            SELECT * FROM (
                SELECT DISTINCT ON (a.school_id)
                    s.name,
                    s.jenjang,
                    a.total_score,
                    a.submitted_at
                FROM portal_assessments a
                JOIN portal_schools s ON a.school_id = s.id
                {where}
                ORDER BY a.school_id, a.submitted_at DESC
            ) sub
            ORDER BY total_score ASC NULLS LAST
            LIMIT %s
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
) -> List[Dict[str, Any]]:
    """List recent submitted assessments for admin dashboard."""
    where = "WHERE a.status = 'submitted'"
    params = []
    if period_id:
        where += " AND a.period_id = %s"
        params.append(period_id)
    if jenjang:
        where += " AND s.jenjang = %s"
        params.append(jenjang)
    params.append(limit)

    order_clause = "submitted_at DESC"
    if order == "score_desc":
        order_clause = "total_score DESC NULLS LAST"
    elif order == "score_asc":
        order_clause = "total_score ASC NULLS LAST"
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
                COALESCE(staff_counts.total_staff, 0) AS total_staff,
                a.submitted_at,
                u.full_name as assessor_name
            FROM portal_assessments a
            JOIN portal_schools s ON a.school_id = s.id
            LEFT JOIN dashboard_users u ON a.staff_id = u.id
            LEFT JOIN (
                SELECT school_id, COUNT(DISTINCT staff_id) AS total_staff
                FROM portal_assessments
                WHERE status = 'submitted'
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

def fetch_school_avg_scores(period_id: Optional[int] = None) -> Dict[int, float]:
    """Return map {school_id: avg_score} for submitted assessments."""
    params = []
    where = "WHERE status = 'submitted'"
    if period_id:
        where += " AND period_id = %s"
        params.append(period_id)
    query = f"""
        SELECT school_id, AVG(total_score)::DECIMAL(5,2) as avg_score
        FROM portal_assessments
        {where}
        GROUP BY school_id
    """
    with get_cursor() as cur:
        cur.execute(query, params)
        return {row["school_id"]: float(row["avg_score"]) if row["avg_score"] is not None else 0.0 for row in cur.fetchall()}

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
) -> List[Dict[str, Any]]:
    """Fetch other photos from the same school and room type for comparison."""
    query = """
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
            COALESCE(AVG(sc.score), 0)::DECIMAL(5,2) AS room_score
        FROM portal_assessment_photos p
        JOIN portal_assessments a ON p.assessment_id = a.id
        LEFT JOIN dashboard_users u ON a.staff_id = u.id
        JOIN portal_schools s ON a.school_id = s.id
        JOIN portal_school_rooms sr ON p.school_room_id = sr.id
        JOIN portal_rooms r ON sr.room_id = r.id
        LEFT JOIN portal_assessment_scores sc 
            ON sc.assessment_id = p.assessment_id 
           AND sc.school_room_id = p.school_room_id
        WHERE a.status = 'submitted'
          AND s.id = %s
          AND r.id = %s
        GROUP BY p.photo_path, s.name, s.id, r.name, r.id, p.captured_at, p.latitude, p.longitude
        ORDER BY p.captured_at DESC NULLS LAST
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(query, (school_id, room_id, limit))
        return [dict(row) for row in cur.fetchall()]


# ===== Admin/Setup Queries =====

def create_room(
    name: str,
    description: Optional[str] = None,
    category: str = "umum",
    sort_order: int = 0,
) -> Dict[str, Any]:
    """Create a new room type."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_rooms (name, description, category, sort_order)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, description, category, sort_order
            """,
            (name, description, category, sort_order),
        )
        return dict(cur.fetchone())


def create_aspect(
    room_id: int,
    name: str,
    description: Optional[str] = None,
    sort_order: int = 0,
) -> Dict[str, Any]:
    """Create a new aspect for a room."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_aspects (room_id, name, description, sort_order)
            VALUES (%s, %s, %s, %s)
            RETURNING id, room_id, name, description, sort_order
            """,
            (room_id, name, description, sort_order),
        )
        return dict(cur.fetchone())


def get_room_by_id(room_id: int) -> Optional[Dict[str, Any]]:
    """Get a single room by ID."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, description, category, sort_order, active FROM portal_rooms WHERE id = %s",
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
) -> Optional[Dict[str, Any]]:
    """Update an existing room."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_rooms 
            SET name = %s, description = %s, category = %s, sort_order = %s, active = %s
            WHERE id = %s
            RETURNING id, name, description, category, sort_order, active
            """,
            (name, description, category, sort_order, active, room_id),
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
            SELECT a.id, a.room_id, a.name, a.description, a.sort_order, a.active, r.name as room_name
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
) -> Optional[Dict[str, Any]]:
    """Update an existing aspect."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_aspects 
            SET name = %s, description = %s, sort_order = %s, active = %s
            WHERE id = %s
            RETURNING id, room_id, name, description, sort_order, active
            """,
            (name, description, sort_order, active, aspect_id),
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


def update_school_rooms(school_id: int, room_ids: List[int]) -> int:
    """Update the rooms available for a school. Returns count of rooms set."""
    with get_cursor(commit=True) as cur:
        # Remove existing
        cur.execute(
            "DELETE FROM portal_school_rooms WHERE school_id = %s",
            (school_id,),
        )
        
        # Add new
        if room_ids:
            values = [(school_id, rid) for rid in room_ids]
            from psycopg2.extras import execute_values
            execute_values(
                cur,
                "INSERT INTO portal_school_rooms (school_id, room_id) VALUES %s",
                values,
            )
        
        return len(room_ids)


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
    where_clause = "WHERE a.status = 'submitted'"
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
