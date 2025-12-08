"""Database schema helpers for the dashboard application."""

from __future__ import annotations

from typing import Iterable

from .db_access import get_cursor

_DASHBOARD_USERS_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    nrk TEXT,
    nip TEXT,
    jabatan TEXT,
    degree_prefix TEXT,
    degree_suffix TEXT,
    no_tester_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
"""

_SCHOOL_CLASSES_SQL = """
CREATE TABLE IF NOT EXISTS school_classes (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    academic_year TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_STUDENTS_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    class_id INTEGER NOT NULL REFERENCES school_classes(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    student_number TEXT,
    sequence INTEGER,
    nisn TEXT,
    gender TEXT,
    birth_place TEXT,
    birth_date DATE,
    religion TEXT,
    address_line TEXT,
    rt TEXT,
    rw TEXT,
    kelurahan TEXT,
    kecamatan TEXT,
    father_name TEXT,
    mother_name TEXT,
    nik TEXT,
    kk_number TEXT,
    metadata JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (class_id, full_name)
);
"""

_STUDENTS_CLASS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_students_class_id
ON students (class_id);
"""

_BULLYING_REPORTS_SQL = """
CREATE TABLE IF NOT EXISTS bullying_reports (
    id SERIAL PRIMARY KEY,
    chat_log_id INTEGER UNIQUE REFERENCES chat_logs(id) ON DELETE CASCADE,
    user_id BIGINT,
    username TEXT,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    last_updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category TEXT NOT NULL DEFAULT 'general',
    severity TEXT,
    metadata JSONB,
    assigned_to TEXT,
    due_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    escalated BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT bullying_reports_status_check CHECK (status IN ('pending', 'in_progress', 'resolved', 'spam'))
);
"""

_BULLYING_STATUS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_bullying_reports_status
ON bullying_reports (status);
"""

_BULLYING_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS bullying_report_events (
    id SERIAL PRIMARY KEY,
    report_id INTEGER REFERENCES bullying_reports(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_BULLYING_EVENTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_bullying_report_events_report
ON bullying_report_events (report_id);
"""

_NOTIFICATIONS_SQL = """
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'unread' CHECK (status IN ('unread', 'read', 'archived')),
    link TEXT,
    reference_table TEXT,
    reference_id INTEGER,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at TIMESTAMPTZ
);
"""

_NOTIFICATIONS_INDEX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_notifications_status
ON notifications (status);
"""

_NOTIFICATIONS_INDEX_CREATED = """
CREATE INDEX IF NOT EXISTS idx_notifications_created_at
ON notifications (created_at DESC);
"""

_TWITTER_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS twitter_worker_logs (
    id SERIAL PRIMARY KEY,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    context JSONB,
    tweet_id BIGINT,
    twitter_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_TWITTER_LOGS_INDEX_CREATED = """
CREATE INDEX IF NOT EXISTS idx_twitter_worker_logs_created
ON twitter_worker_logs (created_at DESC);
"""

_TWITTER_LOGS_INDEX_LEVEL = """
CREATE INDEX IF NOT EXISTS idx_twitter_worker_logs_level
ON twitter_worker_logs (level);
"""

_CHAT_FEEDBACK_SQL = """
CREATE TABLE IF NOT EXISTS chat_feedback (
    id SERIAL PRIMARY KEY,
    chat_log_id INTEGER NOT NULL REFERENCES chat_logs(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    username TEXT,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('like', 'dislike')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chat_log_id, user_id)
);
"""

_CHAT_FEEDBACK_CHAT_LOG_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_chat_feedback_chat_log ON chat_feedback (chat_log_id);
"""

_CHAT_FEEDBACK_USER_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_chat_feedback_user ON chat_feedback (user_id);
"""

_CHAT_FEEDBACK_TYPE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_chat_feedback_type ON chat_feedback (feedback_type);
"""

_CHAT_FEEDBACK_CREATED_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_chat_feedback_created ON chat_feedback (created_at DESC);
"""

_TELEGRAM_USERS_SQL = """
CREATE TABLE IF NOT EXISTS telegram_users (
    id SERIAL PRIMARY KEY,
    telegram_user_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_preview TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','under_review')),
    status_reason TEXT,
    status_changed_at TIMESTAMPTZ,
    status_changed_by TEXT,
    metadata JSONB
);
"""

_TELEGRAM_USERS_INDEX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_telegram_users_status ON telegram_users (status);
"""

# ===== Portal PANBERSS Schema =====

_PORTAL_SCHOOLS_SQL = """
CREATE TABLE IF NOT EXISTS portal_schools (
    id SERIAL PRIMARY KEY,
    npsn TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    jenjang TEXT NOT NULL DEFAULT 'SD',
    alamat TEXT,
    kelurahan TEXT,
    kecamatan TEXT,
    user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    metadata JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_PORTAL_SCHOOLS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_schools_npsn ON portal_schools (npsn);
"""

_PORTAL_ROOMS_SQL = """
CREATE TABLE IF NOT EXISTS portal_rooms (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    category TEXT NOT NULL DEFAULT 'umum',
    sort_order INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_PORTAL_ASPECTS_SQL = """
CREATE TABLE IF NOT EXISTS portal_aspects (
    id SERIAL PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES portal_rooms(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (room_id, name)
);
"""

_PORTAL_ASPECTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_aspects_room ON portal_aspects (room_id);
"""

_PORTAL_SCHOOL_ROOMS_SQL = """
CREATE TABLE IF NOT EXISTS portal_school_rooms (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    room_id INTEGER NOT NULL REFERENCES portal_rooms(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (school_id, room_id)
);
"""

_PORTAL_SCHOOL_ROOMS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_school_rooms_school ON portal_school_rooms (school_id);
"""

_PORTAL_ASSESSMENT_PERIODS_SQL = """
CREATE TABLE IF NOT EXISTS portal_assessment_periods (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_PORTAL_ASSESSMENT_PERIODS_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_portal_periods_active ON portal_assessment_periods (is_active) WHERE is_active = TRUE;
"""

_PORTAL_ASSESSMENTS_SQL = """
CREATE TABLE IF NOT EXISTS portal_assessments (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    period_id INTEGER REFERENCES portal_assessment_periods(id) ON DELETE SET NULL,
    assessment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'verified', 'rejected')),
    total_score DECIMAL(5,2),
    notes TEXT,
    submitted_at TIMESTAMPTZ,
    verified_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_PORTAL_ASSESSMENTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_assessments_school ON portal_assessments (school_id);
CREATE INDEX IF NOT EXISTS idx_portal_assessments_staff ON portal_assessments (staff_id);
CREATE INDEX IF NOT EXISTS idx_portal_assessments_period ON portal_assessments (period_id);
CREATE INDEX IF NOT EXISTS idx_portal_assessments_date ON portal_assessments (assessment_date DESC);
CREATE INDEX IF NOT EXISTS idx_portal_assessments_status ON portal_assessments (status);
"""

_PORTAL_ASSESSMENT_SCORES_SQL = """
CREATE TABLE IF NOT EXISTS portal_assessment_scores (
    id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES portal_assessments(id) ON DELETE CASCADE,
    school_room_id INTEGER NOT NULL REFERENCES portal_school_rooms(id) ON DELETE CASCADE,
    aspect_id INTEGER NOT NULL REFERENCES portal_aspects(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score >= 0 AND score <= 3),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (assessment_id, school_room_id, aspect_id)
);
"""

_PORTAL_ASSESSMENT_SCORES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_scores_assessment ON portal_assessment_scores (assessment_id);
"""

_PORTAL_ASSESSMENT_PHOTOS_SQL = """
CREATE TABLE IF NOT EXISTS portal_assessment_photos (
    id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES portal_assessments(id) ON DELETE CASCADE,
    school_room_id INTEGER NOT NULL REFERENCES portal_school_rooms(id) ON DELETE CASCADE,
    photo_path TEXT NOT NULL,
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    captured_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (assessment_id, school_room_id)
);
"""

_PORTAL_ASSESSMENT_PHOTOS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_photos_assessment ON portal_assessment_photos (assessment_id);
"""

_PORTAL_ASSESSMENT_ROOM_DETAILS_SQL = """
CREATE TABLE IF NOT EXISTS portal_assessment_room_details (
    id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES portal_assessments(id) ON DELETE CASCADE,
    school_room_id INTEGER NOT NULL REFERENCES portal_school_rooms(id) ON DELETE CASCADE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (assessment_id, school_room_id)
);
"""

_PORTAL_ASSESSMENT_ROOM_DETAILS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_room_details_assessment ON portal_assessment_room_details (assessment_id);
"""


def ensure_dashboard_schema() -> None:
    """Create core dashboard tables when they do not yet exist."""
    statements: Iterable[str] = (
        _DASHBOARD_USERS_SQL,
        _SCHOOL_CLASSES_SQL,
        _STUDENTS_SQL,
        _STUDENTS_CLASS_INDEX_SQL,
        _BULLYING_REPORTS_SQL,
        _BULLYING_STATUS_INDEX_SQL,
        _BULLYING_EVENTS_SQL,
        _BULLYING_EVENTS_INDEX_SQL,
        _NOTIFICATIONS_SQL,
        _NOTIFICATIONS_INDEX_STATUS,
        _NOTIFICATIONS_INDEX_CREATED,
        _TWITTER_LOGS_SQL,
        _TWITTER_LOGS_INDEX_CREATED,
        _TWITTER_LOGS_INDEX_LEVEL,
        _CHAT_FEEDBACK_SQL,
        _CHAT_FEEDBACK_CHAT_LOG_INDEX_SQL,
        _CHAT_FEEDBACK_USER_INDEX_SQL,
        _CHAT_FEEDBACK_TYPE_INDEX_SQL,
        _CHAT_FEEDBACK_CREATED_INDEX_SQL,
        _TELEGRAM_USERS_SQL,
        _TELEGRAM_USERS_INDEX_STATUS,
        # Portal PANBERSS tables
        _PORTAL_SCHOOLS_SQL,
        _PORTAL_SCHOOLS_INDEX_SQL,
        _PORTAL_ROOMS_SQL,
        _PORTAL_ASPECTS_SQL,
        _PORTAL_ASPECTS_INDEX_SQL,
        _PORTAL_SCHOOL_ROOMS_SQL,
        _PORTAL_SCHOOL_ROOMS_INDEX_SQL,
        _PORTAL_ASSESSMENT_PERIODS_SQL,
        _PORTAL_ASSESSMENT_PERIODS_INDEX_SQL,
        _PORTAL_ASSESSMENTS_SQL,
        _PORTAL_ASSESSMENTS_INDEX_SQL,
        _PORTAL_ASSESSMENT_SCORES_SQL,
        _PORTAL_ASSESSMENT_SCORES_INDEX_SQL,
        _PORTAL_ASSESSMENT_PHOTOS_SQL,
        _PORTAL_ASSESSMENT_PHOTOS_INDEX_SQL,
        _PORTAL_ASSESSMENT_ROOM_DETAILS_SQL,
        _PORTAL_ASSESSMENT_ROOM_DETAILS_INDEX_SQL,
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS no_tester_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS nrk TEXT",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS nip TEXT",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS jabatan TEXT",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS degree_prefix TEXT",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS degree_suffix TEXT",
        "ALTER TABLE bullying_reports ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'general'",
        "ALTER TABLE bullying_reports ADD COLUMN IF NOT EXISTS severity TEXT",
        "ALTER TABLE bullying_reports ADD COLUMN IF NOT EXISTS metadata JSONB",
        "ALTER TABLE bullying_reports ADD COLUMN IF NOT EXISTS assigned_to TEXT",
        "ALTER TABLE bullying_reports ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ",
        "ALTER TABLE bullying_reports ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ",
        "ALTER TABLE bullying_reports ADD COLUMN IF NOT EXISTS escalated BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE bullying_reports DROP CONSTRAINT IF EXISTS bullying_reports_status_check",
        "ALTER TABLE bullying_reports ADD CONSTRAINT bullying_reports_status_check CHECK (status IN ('pending', 'in_progress', 'resolved', 'spam'))",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS assigned_class_id INTEGER REFERENCES school_classes(id) ON DELETE SET NULL",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS nisn TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS sequence INTEGER",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS gender TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS birth_place TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS birth_date DATE",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS religion TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS address_line TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS rt TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS rw TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS kelurahan TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS kecamatan TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS father_name TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS mother_name TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS nik TEXT",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS kk_number TEXT",
        "ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS period_id INTEGER REFERENCES portal_assessment_periods(id) ON DELETE SET NULL",
        "ALTER TABLE portal_assessment_scores ADD COLUMN IF NOT EXISTS notes TEXT",
        # Rename taken_at to captured_at if it exists (handling legacy schema)
        "DO $$ BEGIN IF EXISTS(SELECT * FROM information_schema.columns WHERE table_name='portal_assessment_photos' AND column_name='taken_at') THEN ALTER TABLE portal_assessment_photos RENAME COLUMN taken_at TO captured_at; END IF; END $$;",
        "ALTER TABLE portal_assessment_photos ADD COLUMN IF NOT EXISTS captured_at TIMESTAMPTZ",
    )
    
    # Execute statements one by one to ensure partial success and better error reporting
    for i, statement in enumerate(statements):
        try:
            # We use a fresh cursor/transaction for each statement or block
            with get_cursor(commit=True) as cur:
                cur.execute(statement)
        except Exception as e:
            # Log error but continue with other statements if possible
            print(f"Error executing schema statement #{i+1}: {e}")
            print(f"Statement: {statement[:100]}...")


__all__ = ["ensure_dashboard_schema"]
