"""Database queries for portal assessment system."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from ..db_access import get_cursor


def list_portal_schools(
    search: Optional[str] = None,
    jenjang: Optional[str] = None,
    active_only: bool = True,
) -> List[Dict[str, Any]]:
    """Fetch all schools available for assessment."""
    conditions = []
    params = []
    
    if active_only:
        conditions.append("active = TRUE")
    
    if jenjang:
        conditions.append("jenjang = %s")
        params.append(jenjang)
    
    if search:
        conditions.append("(name ILIKE %s OR npsn ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    query = f"""
        SELECT 
            id, npsn, name, jenjang, alamat, kelurahan, kecamatan,
            user_id, active, created_at
        FROM portal_schools
        {where_clause}
        ORDER BY jenjang, name
    """
    
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def get_school_by_id(school_id: int) -> Optional[Dict[str, Any]]:
    """Get a single school by ID."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, npsn, name, jenjang, alamat, kelurahan, kecamatan,
                   user_id, active, created_at
            FROM portal_schools
            WHERE id = %s
            """,
            (school_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_portal_rooms(active_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch all room types with their aspects."""
    condition = "WHERE r.active = TRUE" if active_only else ""
    
    query = f"""
        SELECT 
            r.id, r.name, r.description, r.category, r.sort_order,
            COALESCE(
                json_agg(
                    json_build_object(
                        'id', a.id,
                        'name', a.name,
                        'description', a.description,
                        'sort_order', a.sort_order
                    ) ORDER BY a.sort_order, a.id
                ) FILTER (WHERE a.id IS NOT NULL),
                '[]'
            ) as aspects
        FROM portal_rooms r
        LEFT JOIN portal_aspects a ON a.room_id = r.id AND a.active = TRUE
        {condition}
        GROUP BY r.id, r.name, r.description, r.category, r.sort_order
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
            s.name as school_name, s.npsn, s.jenjang
        FROM portal_assessments a
        JOIN portal_schools s ON s.id = a.school_id
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
            r.name as room_name, a.name as aspect_name
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
    """Fetch photos for stats gallery, with room score summary."""
    where = "WHERE a.status IN ('submitted', 'verified')"
    params = []
    if period_id:
        where += " AND a.period_id = %s"
        params.append(period_id)
        
    query = f"""
        SELECT 
            p.photo_path, 
            s.name as school_name, 
            r.name as room_name,
            p.captured_at,
            p.latitude,
            p.longitude,
            COALESCE(AVG(sc.score), 0)::DECIMAL(5,2) AS room_score
        FROM portal_assessment_photos p
        JOIN portal_assessments a ON p.assessment_id = a.id
        JOIN portal_schools s ON a.school_id = s.id
        JOIN portal_school_rooms sr ON p.school_room_id = sr.id
        JOIN portal_rooms r ON sr.room_id = r.id
        LEFT JOIN portal_assessment_scores sc 
            ON sc.assessment_id = p.assessment_id 
           AND sc.school_room_id = p.school_room_id
        {where}
        GROUP BY p.photo_path, s.name, r.name, p.captured_at, p.latitude, p.longitude
    """
    order_clause = "ORDER BY RANDOM()"
    if order == "newest":
        order_clause = "ORDER BY p.captured_at DESC NULLS LAST"
    elif order == "lowest":
        order_clause = "ORDER BY room_score ASC"
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
    
    Some databases may not have the UNIQUE constraint; use update-then-insert to avoid ON CONFLICT errors.
    """
    with get_cursor(commit=True) as cur:
        # Try update first
        cur.execute(
            """
            UPDATE portal_assessment_photos
            SET photo_path = %s,
                latitude = %s,
                longitude = %s,
                captured_at = COALESCE(%s, captured_at, NOW()),
                created_at = COALESCE(created_at, NOW())
            WHERE assessment_id = %s AND school_room_id = %s
            RETURNING id, assessment_id, school_room_id, photo_path, latitude, longitude, COALESCE(captured_at, created_at) AS captured_at
            """,
            (photo_path, latitude, longitude, captured_at, assessment_id, school_room_id),
        )
        row = cur.fetchone()
        if row:
            return dict(row)

        # Insert if not updated
        cur.execute(
            """
            INSERT INTO portal_assessment_photos 
                (assessment_id, school_room_id, photo_path, latitude, longitude, captured_at)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s, NOW()))
            RETURNING id, assessment_id, school_room_id, photo_path, latitude, longitude, COALESCE(captured_at, created_at) AS captured_at
            """,
            (assessment_id, school_room_id, photo_path, latitude, longitude, captured_at),
        )
        return dict(cur.fetchone())


def get_assessment_photos(assessment_id: int) -> List[Dict[str, Any]]:
    """Get all photos for an assessment."""
    query = """
        SELECT 
            id, 
            assessment_id, 
            school_room_id, 
            photo_path, 
            latitude, 
            longitude, 
            COALESCE(captured_at, created_at) AS captured_at
        FROM portal_assessment_photos
        WHERE assessment_id = %s
        ORDER BY captured_at DESC NULLS LAST
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
                COUNT(*) FILTER (WHERE status = 'verified' {pid_cond}) as verified,
                AVG(total_score) FILTER (WHERE status IN ('submitted', 'verified') {pid_cond}) as avg_score
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


def fetch_top_schools(limit: int = 5, period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch top performing schools based on their latest assessment."""
    where = "WHERE a.status IN ('submitted', 'verified')"
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
    where = "WHERE a.status IN ('submitted', 'verified')"
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


def list_recent_assessments(limit: int = 50, period_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List recent submitted/verified assessments for admin dashboard."""
    where = "WHERE a.status IN ('submitted', 'verified')"
    params = []
    if period_id:
        where += " AND a.period_id = %s"
        params.append(period_id)
    params.append(limit)
        
    query = f"""
            SELECT 
                a.id,
                a.school_id,
                s.name as school_name,
                s.npsn,
                s.jenjang,
                a.status,
                a.total_score,
                a.submitted_at,
                u.full_name as assessor_name
            FROM portal_assessments a
            JOIN portal_schools s ON a.school_id = s.id
            LEFT JOIN dashboard_users u ON a.staff_id = u.id
            {where}
            ORDER BY a.submitted_at DESC
            LIMIT %s
            """
    with get_cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

def fetch_school_avg_scores(period_id: Optional[int] = None) -> Dict[int, float]:
    """Return map {school_id: avg_score} for submitted/verified assessments."""
    params = []
    where = "WHERE status IN ('submitted', 'verified')"
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


def create_school(
    npsn: str,
    name: str,
    jenjang: str = "SD",
    alamat: Optional[str] = None,
    kelurahan: Optional[str] = None,
    kecamatan: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new school record."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan, kecamatan)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (npsn) DO UPDATE SET
                name = EXCLUDED.name,
                jenjang = EXCLUDED.jenjang,
                alamat = EXCLUDED.alamat,
                kelurahan = EXCLUDED.kelurahan,
                kecamatan = EXCLUDED.kecamatan,
                updated_at = NOW()
            RETURNING id, npsn, name, jenjang, alamat, kelurahan, kecamatan
            """,
            (npsn, name, jenjang, alamat, kelurahan, kecamatan),
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
