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
    profile_photo_path TEXT,
    no_tester_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ui_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
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

_DASHBOARD_ADMIN_ACTION_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_admin_action_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    feature_key TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER,
    target_name TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DASHBOARD_ADMIN_ACTION_LOGS_INDEX_CREATED = """
CREATE INDEX IF NOT EXISTS idx_dashboard_admin_action_logs_created
ON dashboard_admin_action_logs (created_at DESC);
"""

_DASHBOARD_ADMIN_ACTION_LOGS_INDEX_FEATURE = """
CREATE INDEX IF NOT EXISTS idx_dashboard_admin_action_logs_feature
ON dashboard_admin_action_logs (feature_key, created_at DESC);
"""

_DASHBOARD_ADMIN_ACTION_LOGS_INDEX_USER = """
CREATE INDEX IF NOT EXISTS idx_dashboard_admin_action_logs_user
ON dashboard_admin_action_logs (user_id, created_at DESC);
"""

_NOTIFICATIONS_SQL = """
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dashboard_users(id) ON DELETE CASCADE,
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

_NOTIFICATIONS_INDEX_USER_STATUS_CREATED = """
CREATE INDEX IF NOT EXISTS idx_notifications_user_status_created_at
ON notifications (user_id, status, created_at DESC);
"""

_NOTIFICATIONS_INDEX_USER_CATEGORY_CREATED = """
CREATE INDEX IF NOT EXISTS idx_notifications_user_category_created_at
ON notifications (user_id, category, created_at DESC);
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

_WHATSAPP_USERS_SQL = """
CREATE TABLE IF NOT EXISTS whatsapp_users (
    id SERIAL PRIMARY KEY,
    whatsapp_user_id BIGINT UNIQUE NOT NULL,
    display_name TEXT,
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

_WHATSAPP_USERS_INDEX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_whatsapp_users_status ON whatsapp_users (status);
"""

_TELEGRAM_NOTIFICATION_SETTINGS_SQL = """
CREATE TABLE IF NOT EXISTS telegram_notification_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    bot_token TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
"""

_WHATSAPP_LINK_SETTINGS_SQL = """
CREATE TABLE IF NOT EXISTS whatsapp_link_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    wa_link TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
"""

_SPMB_SERVICE_TYPES_SQL = """
CREATE TABLE IF NOT EXISTS spmb_service_types (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_SPMB_SERVICE_TYPES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_spmb_service_types_active_order
ON spmb_service_types (active, sort_order, id);
"""

_SPMB_SERVICE_TYPES_SEED_SQL = """
INSERT INTO spmb_service_types (name, description, sort_order, active)
VALUES
    ('Informasi SPMB', 'Pertanyaan umum alur dan informasi SPMB.', 10, TRUE),
    ('Verifikasi Berkas', 'Pemeriksaan atau validasi berkas pendaftaran.', 20, TRUE),
    ('Bantuan Akun', 'Bantuan login, akun, atau akses aplikasi.', 30, TRUE),
    ('Perubahan Data', 'Bantuan koreksi atau penyesuaian data.', 40, TRUE),
    ('Pengaduan', 'Keluhan atau kendala selama layanan SPMB.', 50, TRUE),
    ('Lainnya', 'Jenis pelayanan lain di luar kategori utama.', 60, TRUE)
ON CONFLICT (name) DO NOTHING;
"""

_SPMB_TABLE_ASSIGNMENTS_SQL = """
CREATE TABLE IF NOT EXISTS spmb_table_assignments (
    id SERIAL PRIMARY KEY,
    assignment_date DATE NOT NULL,
    table_number INTEGER NOT NULL CHECK (table_number BETWEEN 1 AND 12),
    officer_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    note TEXT,
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (assignment_date, table_number)
);
"""

_SPMB_TABLE_ASSIGNMENTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_spmb_table_assignments_date
ON spmb_table_assignments (assignment_date, table_number);
CREATE INDEX IF NOT EXISTS idx_spmb_table_assignments_officer
ON spmb_table_assignments (officer_user_id);
"""

_SPMB_EVALUATIONS_SQL = """
CREATE TABLE IF NOT EXISTS spmb_evaluations (
    id SERIAL PRIMARY KEY,
    service_type TEXT NOT NULL,
    table_number INTEGER NOT NULL CHECK (table_number BETWEEN 1 AND 12),
    indicator TEXT NOT NULL CHECK (indicator IN ('baik', 'sedang', 'buruk')),
    note TEXT,
    client_ip TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_SPMB_EVALUATIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_spmb_evaluations_created
ON spmb_evaluations (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_spmb_evaluations_indicator
ON spmb_evaluations (indicator);
CREATE INDEX IF NOT EXISTS idx_spmb_evaluations_table_created
ON spmb_evaluations (table_number, created_at DESC);
"""

_SPMB_QUEUE_COUNTERS_SQL = """
CREATE TABLE IF NOT EXISTS spmb_queue_counters (
    id SERIAL PRIMARY KEY,
    service_date DATE NOT NULL UNIQUE,
    current_number INTEGER NOT NULL DEFAULT 0 CHECK (current_number >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_SPMB_QUEUE_COUNTERS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_spmb_queue_counters_date
ON spmb_queue_counters (service_date DESC);
"""

_SPMB_QUEUE_CALLS_SQL = """
CREATE TABLE IF NOT EXISTS spmb_queue_calls (
    id SERIAL PRIMARY KEY,
    service_date DATE NOT NULL,
    queue_number INTEGER NOT NULL CHECK (queue_number > 0),
    table_number INTEGER NOT NULL CHECK (table_number BETWEEN 1 AND 12),
    status TEXT NOT NULL DEFAULT 'sedang_dilayani',
    officer_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    called_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (service_date, queue_number)
);
"""

_SPMB_QUEUE_CALLS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_spmb_queue_calls_date_status
ON spmb_queue_calls (service_date, status, queue_number);
CREATE INDEX IF NOT EXISTS idx_spmb_queue_calls_called
ON spmb_queue_calls (service_date, called_at DESC, id DESC);
"""

_TELEGRAM_ADMIN_ACCOUNTS_SQL = """
CREATE TABLE IF NOT EXISTS telegram_admin_accounts (
    id SERIAL PRIMARY KEY,
    dashboard_user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    telegram_username TEXT NOT NULL,
    notification_scope TEXT NOT NULL DEFAULT 'default',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    UNIQUE (telegram_username, notification_scope)
);
"""

_TELEGRAM_ADMIN_ACCOUNTS_INDEX_USER = """
CREATE INDEX IF NOT EXISTS idx_telegram_admin_accounts_user
ON telegram_admin_accounts (dashboard_user_id);
"""

_TELEGRAM_NOTIFICATION_GROUPS_SQL = """
CREATE TABLE IF NOT EXISTS telegram_notification_groups (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT UNIQUE NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
"""

_SUPPORTER_SCHEMA_SQL = """
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
    requires_proof_text BOOLEAN NOT NULL DEFAULT FALSE,
    requires_screenshot BOOLEAN NOT NULL DEFAULT FALSE,
    verification_mode TEXT NOT NULL DEFAULT 'manual_telegram',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE supporter_tasks ADD COLUMN IF NOT EXISTS action_types JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE supporter_tasks ADD COLUMN IF NOT EXISTS end_at TIMESTAMPTZ;
ALTER TABLE supporter_tasks ALTER COLUMN late_penalty_percent SET DEFAULT 50;
UPDATE supporter_tasks
SET action_types = jsonb_build_array(action_type)
WHERE action_types = '[]'::jsonb
  AND COALESCE(action_type, '') <> '';
CREATE INDEX IF NOT EXISTS idx_supporter_tasks_status_deadline ON supporter_tasks (status, deadline_at);
CREATE INDEX IF NOT EXISTS idx_supporter_tasks_status_end ON supporter_tasks (status, end_at);
CREATE INDEX IF NOT EXISTS idx_supporter_tasks_platform_action ON supporter_tasks (platform, action_type);
CREATE INDEX IF NOT EXISTS idx_supporter_tasks_action_types ON supporter_tasks USING GIN (action_types);

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
);
CREATE INDEX IF NOT EXISTS idx_supporter_submissions_staff_status ON supporter_submissions (staff_id, status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_supporter_submissions_task_status ON supporter_submissions (task_id, status, submitted_at DESC);

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
);
CREATE INDEX IF NOT EXISTS idx_supporter_point_events_staff_created ON supporter_point_events (staff_id, created_at DESC);

CREATE TABLE IF NOT EXISTS supporter_activity_logs (
    id SERIAL PRIMARY KEY,
    actor_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER,
    summary TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_supporter_activity_logs_created ON supporter_activity_logs (created_at DESC);

CREATE TABLE IF NOT EXISTS supporter_telegram_groups (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT UNIQUE NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS supporter_telegram_delivery_messages (
    submission_id INTEGER NOT NULL REFERENCES supporter_submissions(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (submission_id, chat_id)
);
"""

# ===== Portal PANBERSS Schema =====

_PORTAL_KECAMATAN_SQL = """
CREATE TABLE IF NOT EXISTS portal_kecamatan (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_PORTAL_KECAMATAN_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_kecamatan_name ON portal_kecamatan (name);
"""

_PORTAL_KELURAHAN_SQL = """
CREATE TABLE IF NOT EXISTS portal_kelurahan (
    id SERIAL PRIMARY KEY,
    kecamatan_id INTEGER NOT NULL REFERENCES portal_kecamatan(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kecamatan_id, name)
);
"""

_PORTAL_KELURAHAN_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_kelurahan_kecamatan ON portal_kelurahan (kecamatan_id);
"""

_PORTAL_KONTAK_WILAYAH_SQL = """
CREATE TABLE IF NOT EXISTS portal_kontak (
    id SERIAL PRIMARY KEY,
    nama TEXT NOT NULL,
    wilayah TEXT NOT NULL,
    kontak TEXT NOT NULL,
    kontak_1_active BOOLEAN NOT NULL DEFAULT TRUE,
    nama_2 TEXT,
    kontak_2 TEXT,
    kontak_2_active BOOLEAN NOT NULL DEFAULT TRUE
);
"""

_PORTAL_KONTAK_WILAYAH_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_kontak_wilayah
ON portal_kontak (wilayah);
"""

_PORTAL_KONTAK_WILAYAH_SEED_SQL = """
INSERT INTO portal_kontak (nama, wilayah, kontak)
SELECT 'Faris Rani', 'Koja', '081292236799'
WHERE NOT EXISTS (
    SELECT 1 FROM portal_kontak
    WHERE nama = 'Faris Rani' AND wilayah = 'Koja' AND kontak = '081292236799'
);
"""

_PORTAL_UI_SETTINGS_SQL = """
CREATE TABLE IF NOT EXISTS portal_ui_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    undo_window_seconds INTEGER NOT NULL DEFAULT 7 CHECK (undo_window_seconds BETWEEN 1 AND 60),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
"""

_PORTAL_PREVIEW_PINS_SQL = """
CREATE TABLE IF NOT EXISTS portal_preview_pins (
    id SERIAL PRIMARY KEY,
    admin_user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    target_user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (admin_user_id, target_user_id)
);
"""

_PORTAL_PREVIEW_PINS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_preview_pins_admin
ON portal_preview_pins (admin_user_id);
"""

_HOSPITALITY_GUESTBOOK_REVIEWS_SQL = """
CREATE TABLE IF NOT EXISTS hospitality_guestbook_reviews (
    id SERIAL PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES daftar_tamu_general_transactions(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    review_token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    rating SMALLINT,
    comment TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT hospitality_guestbook_reviews_rating_check CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)
);
"""

_HOSPITALITY_GUESTBOOK_REVIEWS_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_hosp_guestbook_reviews_transaction
ON hospitality_guestbook_reviews (transaction_id);
CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_school
ON hospitality_guestbook_reviews (school_id);
CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_status
ON hospitality_guestbook_reviews (status);
CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_completed_at
ON hospitality_guestbook_reviews (completed_at DESC);
"""

_HOSPITALITY_ACTIVITY_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS hospitality_activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER,
    target_name TEXT,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_HOSPITALITY_ACTIVITY_LOGS_INDEX_CREATED = """
CREATE INDEX IF NOT EXISTS idx_hospitality_activity_logs_created ON hospitality_activity_logs (created_at DESC);
"""

_HOSPITALITY_ACTIVITY_LOGS_INDEX_TARGET = """
CREATE INDEX IF NOT EXISTS idx_hospitality_activity_logs_target ON hospitality_activity_logs (target_type, target_id);
"""

_HOSPITALITY_GUESTBOOK_EXTRA_QUESTIONS_SQL = """
CREATE TABLE IF NOT EXISTS hospitality_guestbook_extra_questions (
    id SERIAL PRIMARY KEY,
    question_text TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_HOSPITALITY_GUESTBOOK_EXTRA_QUESTIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_hosp_extra_questions_active_order
ON hospitality_guestbook_extra_questions (active, sort_order, id);
"""

_HOSPITALITY_GUESTBOOK_EXTRA_ANSWERS_SQL = """
CREATE TABLE IF NOT EXISTS hospitality_guestbook_extra_answers (
    id SERIAL PRIMARY KEY,
    review_id INTEGER NOT NULL REFERENCES hospitality_guestbook_reviews(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES hospitality_guestbook_extra_questions(id) ON DELETE CASCADE,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (review_id, question_id)
);
"""

_HOSPITALITY_GUESTBOOK_EXTRA_ANSWERS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_hosp_extra_answers_review
ON hospitality_guestbook_extra_answers (review_id);
CREATE INDEX IF NOT EXISTS idx_hosp_extra_answers_question
ON hospitality_guestbook_extra_answers (question_id);
"""

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
    score_scale_max INTEGER NOT NULL DEFAULT 3 CHECK (score_scale_max IN (3, 5)),
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
    score INTEGER NOT NULL CHECK (score >= 0 AND score <= 5),
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
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

_PORTAL_ACTIVITY_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS portal_activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER,
    target_name TEXT,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_PORTAL_ACTIVITY_LOGS_INDEX_CREATED = """
CREATE INDEX IF NOT EXISTS idx_portal_activity_logs_created ON portal_activity_logs (created_at DESC);
"""

_PORTAL_ACTIVITY_LOGS_INDEX_TARGET = """
CREATE INDEX IF NOT EXISTS idx_portal_activity_logs_target ON portal_activity_logs (target_type, target_id);
"""

_PORTAL_ROOM_FOLLOW_UP_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS portal_room_follow_up_tickets (
    id SERIAL PRIMARY KEY,
    ticket_code TEXT UNIQUE,
    assessment_id INTEGER NOT NULL REFERENCES portal_assessments(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    school_room_id INTEGER NOT NULL REFERENCES portal_school_rooms(id) ON DELETE CASCADE,
    room_id INTEGER NOT NULL REFERENCES portal_rooms(id) ON DELETE CASCADE,
    room_name_snapshot TEXT NOT NULL,
    staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    trigger_score_pct DECIMAL(5,2) NOT NULL,
    threshold_pct DECIMAL(5,2) NOT NULL DEFAULT 60.00,
    status TEXT NOT NULL DEFAULT 'baru' CHECK (status IN ('baru', 'diproses', 'diajukan', 'selesai')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    verified_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    reminder_count INTEGER NOT NULL DEFAULT 0,
    last_reminder_at TIMESTAMPTZ,
    next_reminder_at TIMESTAMPTZ,
    UNIQUE (assessment_id, school_room_id)
);
"""

_PORTAL_ROOM_FOLLOW_UP_TICKETS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_follow_up_tickets_school_status
ON portal_room_follow_up_tickets (school_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_portal_follow_up_tickets_staff_status
ON portal_room_follow_up_tickets (staff_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_portal_follow_up_tickets_reminder
ON portal_room_follow_up_tickets (next_reminder_at)
WHERE status <> 'selesai' AND next_reminder_at IS NOT NULL;
"""

_PORTAL_ROOM_FOLLOW_UP_UPDATES_SQL = """
CREATE TABLE IF NOT EXISTS portal_room_follow_up_updates (
    id SERIAL PRIMARY KEY,
    follow_up_id INTEGER NOT NULL REFERENCES portal_room_follow_up_tickets(id) ON DELETE CASCADE,
    actor_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    actor_role TEXT,
    event_type TEXT NOT NULL CHECK (event_type IN ('created', 'school_update', 'school_submit', 'staff_verify', 'reminder')),
    status_before TEXT,
    status_after TEXT,
    note TEXT,
    photo_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_PORTAL_ROOM_FOLLOW_UP_UPDATES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_portal_follow_up_updates_ticket_created
ON portal_room_follow_up_updates (follow_up_id, created_at DESC);
"""

_PORTAL_ADIWIYATA_POSTS_SQL = """
CREATE TABLE IF NOT EXISTS portal_adiwiyata_posts (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    media_path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    description TEXT,
    thumbnail_path TEXT,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_PORTAL_ADIWIYATA_POSTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_adiwiyata_posts_school_category 
ON portal_adiwiyata_posts (school_id, category);
"""

_PORTAL_ADIWIYATA_POSTS_CREATED_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_adiwiyata_posts_created_at
ON portal_adiwiyata_posts (created_at DESC);
"""

_ADIWIYATA_POST_LIKES_SQL = """
CREATE TABLE IF NOT EXISTS adiwiyata_post_likes (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES portal_adiwiyata_posts(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('like', 'dislike')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (post_id, fingerprint)
);
"""

_ADIWIYATA_POST_LIKES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_adiwiyata_post_likes_post_action
ON adiwiyata_post_likes (post_id, action);
"""

_USER_KECAMATAN_SQL = """
CREATE TABLE IF NOT EXISTS user_kecamatan (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    kecamatan_id INTEGER NOT NULL REFERENCES portal_kecamatan(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    UNIQUE (user_id, kecamatan_id)
);
"""

_USER_KECAMATAN_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_user_kecamatan_user ON user_kecamatan (user_id);
CREATE INDEX IF NOT EXISTS idx_user_kecamatan_kecamatan ON user_kecamatan (kecamatan_id);
"""

_STAFF_SCHOOL_ASSIGNMENTS_SQL = """
CREATE TABLE IF NOT EXISTS staff_school_assignments (
    id SERIAL PRIMARY KEY,
    staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    assigned_by INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT,
    UNIQUE (staff_id, school_id)
);
"""

_STAFF_SCHOOL_ASSIGNMENTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_staff_assignments_staff ON staff_school_assignments (staff_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_school ON staff_school_assignments (school_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_assigned_by ON staff_school_assignments (assigned_by);
"""

_SCHOOL_CLASSROOMS_SQL = """
CREATE TABLE IF NOT EXISTS school_classrooms (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    grade_level INTEGER,
    variant TEXT,
    capacity INTEGER,
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (school_id, name)
);
"""

_SCHOOL_CLASSROOMS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_school_classrooms_school ON school_classrooms (school_id);
CREATE INDEX IF NOT EXISTS idx_school_classrooms_grade ON school_classrooms (grade_level);
CREATE INDEX IF NOT EXISTS idx_school_classrooms_active ON school_classrooms (active);
"""

# ===== Daftar Tamu Schema =====

_DAFTAR_TAMU_SCHOOLS_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_schools (
    id SERIAL PRIMARY KEY,
    npsn TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    jenjang TEXT NOT NULL DEFAULT 'SD',
    alamat TEXT,
    kecamatan TEXT,
    kelurahan TEXT,
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DAFTAR_TAMU_SCHOOLS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_schools_name ON daftar_tamu_schools (name);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_schools_kecamatan ON daftar_tamu_schools (kecamatan);
"""

_DAFTAR_TAMU_VISITS_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_visits (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES daftar_tamu_schools(id) ON DELETE CASCADE,
    visit_date DATE NOT NULL DEFAULT CURRENT_DATE,
    guest_name TEXT NOT NULL,
    guest_institution TEXT NOT NULL,
    purpose TEXT,
    notes TEXT,
    photo_path TEXT,
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DAFTAR_TAMU_VISITS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_visits_school ON daftar_tamu_visits (school_id);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_visits_date ON daftar_tamu_visits (visit_date DESC);
"""

_DAFTAR_TAMU_TRANSACTIONS_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_transactions (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    visit_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    purpose TEXT,
    notes TEXT,
    photo_path TEXT NOT NULL,
    photo_raw_path TEXT,
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DAFTAR_TAMU_TRANSACTIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_transactions_school ON daftar_tamu_transactions (school_id);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_transactions_status ON daftar_tamu_transactions (status);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_transactions_visit_at ON daftar_tamu_transactions (visit_at DESC);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_transactions_created_by ON daftar_tamu_transactions (created_by);
"""

_DAFTAR_TAMU_GENERAL_GUESTS_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_general_guests (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    instansi TEXT,
    jabatan TEXT,
    is_parent BOOLEAN NOT NULL DEFAULT FALSE,
    student_class TEXT,
    student_name TEXT,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    deleted_at TIMESTAMPTZ,
    verified_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DAFTAR_TAMU_GENERAL_GUESTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_guests_name ON daftar_tamu_general_guests (lower(full_name));
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_guests_verified ON daftar_tamu_general_guests (is_verified);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_guests_email ON daftar_tamu_general_guests (lower(email));
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_guests_phone ON daftar_tamu_general_guests (phone);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_guests_deleted ON daftar_tamu_general_guests (is_deleted);
"""

_DAFTAR_TAMU_TRANSACTION_GUESTS_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_transaction_guests (
    id SERIAL PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES daftar_tamu_transactions(id) ON DELETE CASCADE,
    guest_type TEXT NOT NULL DEFAULT 'sudin' CHECK (guest_type IN ('sudin', 'umum')),
    user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    general_guest_id INTEGER REFERENCES daftar_tamu_general_guests(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (transaction_id, user_id),
    UNIQUE (transaction_id, general_guest_id)
);
"""

_DAFTAR_TAMU_TRANSACTION_GUESTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_transaction_guests_tx ON daftar_tamu_transaction_guests (transaction_id);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_transaction_guests_user ON daftar_tamu_transaction_guests (user_id);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_transaction_guests_general ON daftar_tamu_transaction_guests (general_guest_id);
"""

_DAFTAR_TAMU_GENERAL_TRANSACTIONS_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_general_transactions (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    visit_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    purpose TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DAFTAR_TAMU_GENERAL_TRANSACTIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transactions_school ON daftar_tamu_general_transactions (school_id);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transactions_status ON daftar_tamu_general_transactions (status);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transactions_visit_at ON daftar_tamu_general_transactions (visit_at DESC);
"""

_DAFTAR_TAMU_GENERAL_TRANSACTION_GUESTS_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_general_transaction_guests (
    id SERIAL PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES daftar_tamu_general_transactions(id) ON DELETE CASCADE,
    general_guest_id INTEGER REFERENCES daftar_tamu_general_guests(id) ON DELETE SET NULL,
    full_name TEXT NOT NULL,
    phone TEXT,
    instansi TEXT,
    jabatan TEXT,
    email TEXT,
    student_class TEXT,
    student_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DAFTAR_TAMU_GENERAL_TRANSACTION_GUESTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transaction_guests_tx ON daftar_tamu_general_transaction_guests (transaction_id);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transaction_guests_guest ON daftar_tamu_general_transaction_guests (general_guest_id);
"""

_DAFTAR_TAMU_PURPOSE_KEYWORDS_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_purpose_keywords (
    id SERIAL PRIMARY KEY,
    keyword TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DAFTAR_TAMU_PURPOSE_KEYWORDS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_purpose_keywords_active ON daftar_tamu_purpose_keywords (active);
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_purpose_keywords_keyword ON daftar_tamu_purpose_keywords (lower(keyword));
"""

_DAFTAR_TAMU_CONTACT_PRIORITY_SQL = """
CREATE TABLE IF NOT EXISTS daftar_tamu_contact_priority (
    id SERIAL PRIMARY KEY,
    contact_key TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DAFTAR_TAMU_CONTACT_PRIORITY_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_daftar_tamu_contact_priority_active ON daftar_tamu_contact_priority (active);
"""


# ===== CMS Schema =====

_CMS_PROFIL_INSTANSI_SQL = """
CREATE TABLE IF NOT EXISTS cms_profil_instansi (
    id SERIAL PRIMARY KEY,
    cms_deskripsi_utama TEXT,
    cms_visi TEXT,
    cms_misi TEXT,
    cms_tugas_fungsi TEXT,
    cms_motto_pelayanan TEXT,
    cms_struktur_organisasi TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CMS_INFORMASI_PUBLIK_SQL = """
CREATE TABLE IF NOT EXISTS cms_informasi_publik (
    id SERIAL PRIMARY KEY,
    cms_jaminan_pelayanan TEXT,
    cms_keamanan_keselamatan TEXT,
    cms_kompensasi_pelayanan TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CMS_LAYANAN_PUBLIK_SQL = """
CREATE TABLE IF NOT EXISTS cms_layanan_publik (
    id SERIAL PRIMARY KEY,
    cms_nama_layanan TEXT NOT NULL,
    cms_deskripsi TEXT,
    cms_icon TEXT NOT NULL DEFAULT 'bi-star',
    cms_status TEXT NOT NULL DEFAULT 'Aktif' CHECK (cms_status IN ('Aktif', 'Tidak Aktif')),
    cms_files JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CMS_ARTIKEL_SQL = """
CREATE TABLE IF NOT EXISTS cms_artikel (
    id SERIAL PRIMARY KEY,
    judul TEXT NOT NULL,
    kategori TEXT NOT NULL,
    tanggal_publikasi DATE NOT NULL,
    deskripsi TEXT NOT NULL,
    thumbnail_path TEXT,
    penulis TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Aktif',
    status_publikasi TEXT NOT NULL DEFAULT 'Draft',
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT cms_artikel_status_check CHECK (status IN ('Aktif', 'Tidak Aktif')),
    CONSTRAINT cms_artikel_status_publikasi_check CHECK (status_publikasi IN ('Draft', 'Published'))
);
"""

_CMS_ARTIKEL_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cms_artikel_tanggal_publikasi
ON cms_artikel (tanggal_publikasi DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cms_artikel_status_publikasi
ON cms_artikel (status_publikasi, status);
"""

_CMS_ARTIKEL_FILES_SQL = """
CREATE TABLE IF NOT EXISTS cms_artikel_files (
    id SERIAL PRIMARY KEY,
    artikel_id INTEGER NOT NULL REFERENCES cms_artikel(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CMS_ARTIKEL_FILES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cms_artikel_files_artikel_id
ON cms_artikel_files (artikel_id, created_at);
"""

# ===== Call Center Schema =====

_CC_CONVERSATIONS_SQL = """
CREATE TABLE IF NOT EXISTS cc_conversations (
    id SERIAL PRIMARY KEY,
    wa_user_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    last_message_at TIMESTAMPTZ,
    unread_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CC_CONVERSATIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cc_conversations_status ON cc_conversations (status);
CREATE INDEX IF NOT EXISTS idx_cc_conversations_last_msg ON cc_conversations (last_message_at DESC NULLS LAST);
"""

_CC_WA_ROUTING_SQL = """
CREATE TABLE IF NOT EXISTS cc_wa_routing (
    id SERIAL PRIMARY KEY,
    wa_user_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    route_mode TEXT NOT NULL DEFAULT 'manual' CHECK (route_mode IN ('manual','ai')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by INTEGER
);
"""

_CC_WA_ROUTING_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cc_wa_routing_mode_active
ON cc_wa_routing (route_mode, is_active);
CREATE INDEX IF NOT EXISTS idx_cc_wa_routing_updated_at
ON cc_wa_routing (updated_at DESC);
"""

_CC_WA_BRIDGE_ACCOUNTS_SQL = """
CREATE TABLE IF NOT EXISTS cc_wa_bridge_accounts (
    id SERIAL PRIMARY KEY,
    bridge_key TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    wa_number_hint TEXT,
    client_id TEXT NOT NULL,
    http_port INTEGER NOT NULL UNIQUE,
    session_path TEXT NOT NULL,
    status_path TEXT NOT NULL,
    pid_path TEXT NOT NULL,
    log_path TEXT NOT NULL,
    internal_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by INTEGER
);
"""

_CC_WA_BRIDGE_ACCOUNTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cc_wa_bridge_accounts_active
ON cc_wa_bridge_accounts (is_active, bridge_key);
"""

_CC_MESSAGES_SQL = """
CREATE TABLE IF NOT EXISTS cc_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES cc_conversations(id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK (direction IN ('inbound','outbound')),
    message_text TEXT NOT NULL,
    admin_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    admin_display_name TEXT,
    wa_message_id TEXT,
    media_path TEXT,
    media_mime_type TEXT,
    media_filename TEXT,
    media_size INTEGER,
    original_message_text TEXT,
    edited_at TIMESTAMPTZ,
    edited_by_admin_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CC_MESSAGES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cc_messages_conversation ON cc_messages (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_cc_messages_created ON cc_messages (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cc_messages_wa_message_id ON cc_messages (wa_message_id) WHERE wa_message_id IS NOT NULL;
"""

_CC_TELEGRAM_SETTINGS_SQL = """
CREATE TABLE IF NOT EXISTS cc_telegram_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    bot_token TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
"""

# Migration: add notification_scope to telegram_admin_accounts (existing DBs)
_TELEGRAM_ADMIN_SCOPE_MIGRATION = """
ALTER TABLE telegram_admin_accounts ADD COLUMN IF NOT EXISTS notification_scope TEXT NOT NULL DEFAULT 'default';
"""
_TELEGRAM_ADMIN_DROP_OLD_UNIQUE = """
ALTER TABLE telegram_admin_accounts DROP CONSTRAINT IF EXISTS telegram_admin_accounts_telegram_username_key;
"""
_TELEGRAM_ADMIN_ADD_SCOPE_UNIQUE = """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'telegram_admin_accounts_telegram_username_scope_key') THEN
    ALTER TABLE telegram_admin_accounts ADD CONSTRAINT telegram_admin_accounts_telegram_username_scope_key UNIQUE (telegram_username, notification_scope);
  END IF;
END $$;
"""

_CC_TELEGRAM_GROUPS_SQL = """
CREATE TABLE IF NOT EXISTS cc_telegram_groups (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT UNIQUE NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
"""

_CC_PUBLIC_WHATSAPP_CTA_SETTINGS_SQL = """
CREATE TABLE IF NOT EXISTS cc_public_whatsapp_cta_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    wa_number TEXT,
    opening_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
"""

_CC_MESSAGE_DRAFTS_SQL = """
CREATE TABLE IF NOT EXISTS cc_message_drafts (
    id SERIAL PRIMARY KEY,
    admin_user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Umum',
    message_text TEXT NOT NULL,
    media_path TEXT,
    media_mime_type TEXT,
    media_filename TEXT,
    media_size INTEGER,
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CC_MESSAGE_DRAFTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cc_message_drafts_admin ON cc_message_drafts (admin_user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cc_message_drafts_admin_category ON cc_message_drafts (admin_user_id, category);
"""

_SYSTEM_SETTINGS_SQL = """
CREATE TABLE IF NOT EXISTS system_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT,
    category VARCHAR(50) NOT NULL DEFAULT 'general',
    description TEXT,
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
"""

_PUBLIC_API_KEYS_SQL = """
CREATE TABLE IF NOT EXISTS public_api_keys (
    id SERIAL PRIMARY KEY,
    client_name VARCHAR(150) NOT NULL,
    contact_email VARCHAR(150),
    api_key VARCHAR(100) UNIQUE NOT NULL,
    scopes JSONB NOT NULL DEFAULT '["schools:read"]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
"""

_PUBLIC_API_KEYS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_public_api_keys_key ON public_api_keys (api_key);
CREATE INDEX IF NOT EXISTS idx_public_api_keys_active ON public_api_keys (is_active);
"""

def ensure_dashboard_schema() -> None:
    """Create core dashboard tables when they do not yet exist."""
    statements: Iterable[str] = (
        _DASHBOARD_USERS_SQL,
        _SYSTEM_SETTINGS_SQL,
        _PUBLIC_API_KEYS_SQL,
        _PUBLIC_API_KEYS_INDEX_SQL,
        _SCHOOL_CLASSES_SQL,
        _STUDENTS_SQL,
        _STUDENTS_CLASS_INDEX_SQL,
        _BULLYING_REPORTS_SQL,
        _BULLYING_STATUS_INDEX_SQL,
        _BULLYING_EVENTS_SQL,
        _BULLYING_EVENTS_INDEX_SQL,
        _DASHBOARD_ADMIN_ACTION_LOGS_SQL,
        _DASHBOARD_ADMIN_ACTION_LOGS_INDEX_CREATED,
        _DASHBOARD_ADMIN_ACTION_LOGS_INDEX_FEATURE,
        _DASHBOARD_ADMIN_ACTION_LOGS_INDEX_USER,
        _NOTIFICATIONS_SQL,
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES dashboard_users(id) ON DELETE CASCADE",
        _NOTIFICATIONS_INDEX_STATUS,
        _NOTIFICATIONS_INDEX_CREATED,
        _NOTIFICATIONS_INDEX_USER_STATUS_CREATED,
        _NOTIFICATIONS_INDEX_USER_CATEGORY_CREATED,
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
        _WHATSAPP_USERS_SQL,
        _WHATSAPP_USERS_INDEX_STATUS,
        _TELEGRAM_NOTIFICATION_SETTINGS_SQL,
        _WHATSAPP_LINK_SETTINGS_SQL,
        _SPMB_SERVICE_TYPES_SQL,
        _SPMB_SERVICE_TYPES_INDEX_SQL,
        _SPMB_SERVICE_TYPES_SEED_SQL,
        _SPMB_TABLE_ASSIGNMENTS_SQL,
        _SPMB_TABLE_ASSIGNMENTS_INDEX_SQL,
        _SPMB_EVALUATIONS_SQL,
        _SPMB_EVALUATIONS_INDEX_SQL,
        _SPMB_QUEUE_COUNTERS_SQL,
        _SPMB_QUEUE_COUNTERS_INDEX_SQL,
        _SPMB_QUEUE_CALLS_SQL,
        _SPMB_QUEUE_CALLS_INDEX_SQL,
        _TELEGRAM_ADMIN_ACCOUNTS_SQL,
        _TELEGRAM_ADMIN_ACCOUNTS_INDEX_USER,
        _TELEGRAM_ADMIN_SCOPE_MIGRATION,
        _TELEGRAM_ADMIN_DROP_OLD_UNIQUE,
        _TELEGRAM_ADMIN_ADD_SCOPE_UNIQUE,
        _TELEGRAM_NOTIFICATION_GROUPS_SQL,
        _SUPPORTER_SCHEMA_SQL,
        # Portal PANBERSS tables
        _PORTAL_KECAMATAN_SQL,
        _PORTAL_KECAMATAN_INDEX_SQL,
        _PORTAL_KELURAHAN_SQL,
        _PORTAL_KELURAHAN_INDEX_SQL,
        _PORTAL_KONTAK_WILAYAH_SQL,
        _PORTAL_KONTAK_WILAYAH_INDEX_SQL,
        "ALTER TABLE portal_kontak ADD COLUMN IF NOT EXISTS kontak_1_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE portal_kontak ADD COLUMN IF NOT EXISTS nama_2 TEXT",
        "ALTER TABLE portal_kontak ADD COLUMN IF NOT EXISTS kontak_2 TEXT",
        "ALTER TABLE portal_kontak ADD COLUMN IF NOT EXISTS kontak_2_active BOOLEAN NOT NULL DEFAULT TRUE",
        _PORTAL_UI_SETTINGS_SQL,
        _PORTAL_PREVIEW_PINS_SQL,
        _PORTAL_PREVIEW_PINS_INDEX_SQL,
        _HOSPITALITY_GUESTBOOK_REVIEWS_SQL,
        _HOSPITALITY_GUESTBOOK_REVIEWS_INDEX_SQL,
        _HOSPITALITY_ACTIVITY_LOGS_SQL,
        _HOSPITALITY_ACTIVITY_LOGS_INDEX_CREATED,
        _HOSPITALITY_ACTIVITY_LOGS_INDEX_TARGET,
        _HOSPITALITY_GUESTBOOK_EXTRA_QUESTIONS_SQL,
        _HOSPITALITY_GUESTBOOK_EXTRA_QUESTIONS_INDEX_SQL,
        _HOSPITALITY_GUESTBOOK_EXTRA_ANSWERS_SQL,
        _HOSPITALITY_GUESTBOOK_EXTRA_ANSWERS_INDEX_SQL,
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
        _PORTAL_ACTIVITY_LOGS_SQL,
        _PORTAL_ACTIVITY_LOGS_INDEX_CREATED,
        _PORTAL_ACTIVITY_LOGS_INDEX_TARGET,
        _PORTAL_ROOM_FOLLOW_UP_TICKETS_SQL,
        _PORTAL_ROOM_FOLLOW_UP_TICKETS_INDEX_SQL,
        _PORTAL_ROOM_FOLLOW_UP_UPDATES_SQL,
        _PORTAL_ROOM_FOLLOW_UP_UPDATES_INDEX_SQL,
        _PORTAL_ADIWIYATA_POSTS_SQL,
        _PORTAL_ADIWIYATA_POSTS_INDEX_SQL,
        _PORTAL_ADIWIYATA_POSTS_CREATED_INDEX_SQL,
        _ADIWIYATA_POST_LIKES_SQL,
        _ADIWIYATA_POST_LIKES_INDEX_SQL,
        # Kecamatan access control tables
        _USER_KECAMATAN_SQL,
        _USER_KECAMATAN_INDEX_SQL,
        # Staff school assignments
        _STAFF_SCHOOL_ASSIGNMENTS_SQL,
        _STAFF_SCHOOL_ASSIGNMENTS_INDEX_SQL,
        # School classroom configuration
        _SCHOOL_CLASSROOMS_SQL,
        _SCHOOL_CLASSROOMS_INDEX_SQL,
        # Daftar Tamu tables
        _DAFTAR_TAMU_SCHOOLS_SQL,
        _DAFTAR_TAMU_SCHOOLS_INDEX_SQL,
        _DAFTAR_TAMU_VISITS_SQL,
        _DAFTAR_TAMU_VISITS_INDEX_SQL,
        _DAFTAR_TAMU_TRANSACTIONS_SQL,
        _DAFTAR_TAMU_TRANSACTIONS_INDEX_SQL,
        _DAFTAR_TAMU_GENERAL_GUESTS_SQL,
        "ALTER TABLE daftar_tamu_general_guests ADD COLUMN IF NOT EXISTS email TEXT",
        "ALTER TABLE daftar_tamu_general_guests ADD COLUMN IF NOT EXISTS is_parent BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE daftar_tamu_general_guests ADD COLUMN IF NOT EXISTS student_class TEXT",
        "ALTER TABLE daftar_tamu_general_guests ADD COLUMN IF NOT EXISTS student_name TEXT",
        "ALTER TABLE daftar_tamu_general_guests ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE daftar_tamu_general_guests ADD COLUMN IF NOT EXISTS deleted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL",
        "ALTER TABLE daftar_tamu_general_guests ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
        _DAFTAR_TAMU_GENERAL_GUESTS_INDEX_SQL,
        _DAFTAR_TAMU_GENERAL_TRANSACTIONS_SQL,
        _DAFTAR_TAMU_GENERAL_TRANSACTIONS_INDEX_SQL,
        _DAFTAR_TAMU_GENERAL_TRANSACTION_GUESTS_SQL,
        _DAFTAR_TAMU_GENERAL_TRANSACTION_GUESTS_INDEX_SQL,
        "ALTER TABLE daftar_tamu_general_transaction_guests ADD COLUMN IF NOT EXISTS student_class TEXT",
        "ALTER TABLE daftar_tamu_general_transaction_guests ADD COLUMN IF NOT EXISTS student_name TEXT",
        _DAFTAR_TAMU_PURPOSE_KEYWORDS_SQL,
        _DAFTAR_TAMU_PURPOSE_KEYWORDS_INDEX_SQL,
        _DAFTAR_TAMU_CONTACT_PRIORITY_SQL,
        _DAFTAR_TAMU_CONTACT_PRIORITY_INDEX_SQL,
        _DAFTAR_TAMU_TRANSACTION_GUESTS_SQL,
        _DAFTAR_TAMU_TRANSACTION_GUESTS_INDEX_SQL,
        "ALTER TABLE daftar_tamu_transaction_guests ADD COLUMN IF NOT EXISTS guest_type TEXT NOT NULL DEFAULT 'sudin'",
        "ALTER TABLE daftar_tamu_transaction_guests ADD COLUMN IF NOT EXISTS general_guest_id INTEGER REFERENCES daftar_tamu_general_guests(id) ON DELETE SET NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uniq_daftar_tamu_tx_general_guest_full ON daftar_tamu_transaction_guests (transaction_id, general_guest_id)",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS no_tester_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS ui_settings JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS nrk TEXT",
        "ALTER TABLE dashboard_users ALTER COLUMN nrk DROP NOT NULL",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS nip TEXT",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS jabatan TEXT",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS degree_prefix TEXT",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS degree_suffix TEXT",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS profile_photo_path TEXT",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS merged_to INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS merged_at TIMESTAMPTZ",
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
        "ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS score_scale_max INTEGER",
        "ALTER TABLE portal_assessments ALTER COLUMN score_scale_max SET DEFAULT 3",
        "UPDATE portal_assessments SET score_scale_max = 3 WHERE score_scale_max IS NULL OR score_scale_max NOT IN (3, 5)",
        "ALTER TABLE portal_assessments ALTER COLUMN score_scale_max SET NOT NULL",
        "ALTER TABLE portal_assessments DROP CONSTRAINT IF EXISTS portal_assessments_score_scale_max_check",
        "ALTER TABLE portal_assessments ADD CONSTRAINT portal_assessments_score_scale_max_check CHECK (score_scale_max IN (3, 5))",
        "ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS period_id INTEGER REFERENCES portal_assessment_periods(id) ON DELETE SET NULL",
        """
        DO $$
        DECLARE
            _constraint_name TEXT;
        BEGIN
            FOR _constraint_name IN
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND t.relname = 'portal_assessment_scores'
                  AND c.contype = 'c'
                  AND pg_get_constraintdef(c.oid) ILIKE '%score%'
            LOOP
                EXECUTE format(
                    'ALTER TABLE portal_assessment_scores DROP CONSTRAINT IF EXISTS %I',
                    _constraint_name
                );
            END LOOP;
        END $$;
        """,
        "ALTER TABLE portal_assessment_scores ADD CONSTRAINT portal_assessment_scores_score_check CHECK (score >= 0 AND score <= 5)",
        "ALTER TABLE portal_assessment_scores ADD COLUMN IF NOT EXISTS notes TEXT",
        # Rename taken_at to captured_at if it exists (handling legacy schema)
        "DO $$ BEGIN IF EXISTS(SELECT * FROM information_schema.columns WHERE table_name='portal_assessment_photos' AND column_name='taken_at') THEN ALTER TABLE portal_assessment_photos RENAME COLUMN taken_at TO captured_at; END IF; END $$;",
        "ALTER TABLE portal_assessment_photos ADD COLUMN IF NOT EXISTS captured_at TIMESTAMPTZ",
        "ALTER TABLE portal_assessment_photos ADD COLUMN IF NOT EXISTS notes TEXT",
        # Clean up duplicates before adding unique constraint (keep latest)
        """
        DELETE FROM portal_assessment_photos a USING portal_assessment_photos b
        WHERE a.assessment_id = b.assessment_id 
          AND a.school_room_id = b.school_room_id 
          AND a.created_at < b.created_at
        """,
        # Enforce unique constraint for atomic upserts
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'portal_assessment_photos_assessment_id_school_room_id_key'
            ) THEN
                ALTER TABLE portal_assessment_photos ADD CONSTRAINT portal_assessment_photos_assessment_id_school_room_id_key UNIQUE (assessment_id, school_room_id);
            END IF;
        END $$;
        """,
        # Portal schools additional columns
        "ALTER TABLE portal_schools ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'NEGERI'",
        "ALTER TABLE portal_schools ADD COLUMN IF NOT EXISTS kelurahan_id INTEGER REFERENCES portal_kelurahan(id) ON DELETE SET NULL",
        # Drop legacy columns from portal_schools (kecamatan can be derived from kelurahan->kecamatan relation)
        "ALTER TABLE portal_schools DROP CONSTRAINT IF EXISTS portal_schools_kecamatan_id_fkey",
        "ALTER TABLE portal_schools DROP COLUMN IF EXISTS kecamatan_id",
        "ALTER TABLE portal_schools DROP COLUMN IF EXISTS kecamatan",
        "ALTER TABLE portal_schools DROP COLUMN IF EXISTS kelurahan",
        # School registration - link dashboard users to schools
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS school_id INTEGER REFERENCES portal_schools(id) ON DELETE SET NULL",
        # School logo column
        "ALTER TABLE portal_schools ADD COLUMN IF NOT EXISTS logo_url TEXT",
        # Kecamatan cache column for dashboard_users
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS kecamatan_cache JSONB",
        "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS social_username TEXT",
        # Daftar tamu compatibility columns
        "ALTER TABLE daftar_tamu_schools ADD COLUMN IF NOT EXISTS metadata JSONB",
        "ALTER TABLE daftar_tamu_visits ADD COLUMN IF NOT EXISTS photo_path TEXT",
        "ALTER TABLE daftar_tamu_visits ADD COLUMN IF NOT EXISTS latitude DECIMAL(9,6)",
        "ALTER TABLE daftar_tamu_visits ADD COLUMN IF NOT EXISTS longitude DECIMAL(9,6)",
        "ALTER TABLE daftar_tamu_visits ADD COLUMN IF NOT EXISTS metadata JSONB",
        # ===== CMS tables =====
        _CMS_PROFIL_INSTANSI_SQL,
        _CMS_INFORMASI_PUBLIK_SQL,
        _CMS_LAYANAN_PUBLIK_SQL,
        _CMS_ARTIKEL_SQL,
        _CMS_ARTIKEL_INDEX_SQL,
        _CMS_ARTIKEL_FILES_SQL,
        _CMS_ARTIKEL_FILES_INDEX_SQL,
        # ===== Call Center tables =====
        _CC_CONVERSATIONS_SQL,
        _CC_CONVERSATIONS_INDEX_SQL,
        _CC_WA_ROUTING_SQL,
        _CC_WA_ROUTING_INDEX_SQL,
        _CC_WA_BRIDGE_ACCOUNTS_SQL,
        "ALTER TABLE cc_wa_bridge_accounts ADD COLUMN IF NOT EXISTS wa_number_hint TEXT",
        _CC_WA_BRIDGE_ACCOUNTS_INDEX_SQL,
        _CC_MESSAGES_SQL,
        "ALTER TABLE cc_messages ADD COLUMN IF NOT EXISTS media_path TEXT",
        "ALTER TABLE cc_messages ADD COLUMN IF NOT EXISTS media_mime_type TEXT",
        "ALTER TABLE cc_messages ADD COLUMN IF NOT EXISTS media_filename TEXT",
        "ALTER TABLE cc_messages ADD COLUMN IF NOT EXISTS media_size INTEGER",
        "ALTER TABLE cc_messages ADD COLUMN IF NOT EXISTS original_message_text TEXT",
        "ALTER TABLE cc_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ",
        "ALTER TABLE cc_messages ADD COLUMN IF NOT EXISTS edited_by_admin_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL",
        _CC_MESSAGES_INDEX_SQL,
        _CC_TELEGRAM_SETTINGS_SQL,
        _CC_TELEGRAM_GROUPS_SQL,
        _CC_PUBLIC_WHATSAPP_CTA_SETTINGS_SQL,
        _CC_MESSAGE_DRAFTS_SQL,
        "ALTER TABLE cc_message_drafts ADD COLUMN IF NOT EXISTS media_path TEXT",
        "ALTER TABLE cc_message_drafts ADD COLUMN IF NOT EXISTS media_mime_type TEXT",
        "ALTER TABLE cc_message_drafts ADD COLUMN IF NOT EXISTS media_filename TEXT",
        "ALTER TABLE cc_message_drafts ADD COLUMN IF NOT EXISTS media_size INTEGER",
        _CC_MESSAGE_DRAFTS_INDEX_SQL,
        # ===== Laporan (Form Reports) tables =====
        _LAPORAN_FORMS_SQL,
        _LAPORAN_FORMS_STATUS_MIGRATION_SQL,
        _LAPORAN_FORMS_PAUSE_MIGRATION_SQL,
        _LAPORAN_REPEAT_POLICY_MIGRATION_SQL,
        _LAPORAN_FORMS_INDEX_SQL,
        _LAPORAN_FORM_TARGETS_SQL,
        _LAPORAN_FORM_TARGETS_INDEX_SQL,
        _LAPORAN_FORM_FIELDS_SQL,
        _LAPORAN_FORM_FIELDS_INDEX_SQL,
        _LAPORAN_SUBMISSIONS_SQL,
        _LAPORAN_SUBMISSIONS_REPEAT_PERIOD_MIGRATION_SQL,
        _LAPORAN_SUBMISSIONS_INDEX_SQL,
        _LAPORAN_SUBMISSION_ANSWERS_SQL,
        _LAPORAN_SUBMISSION_ANSWERS_UNIQUE_MIGRATION_SQL,
        _LAPORAN_SUBMISSION_ANSWERS_INDEX_SQL,
        _LAPORAN_SUBMISSION_FILES_SQL,
        _LAPORAN_SUBMISSION_FILES_INDEX_SQL,
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


# ===== Laporan Schema SQL =====

_LAPORAN_FORMS_SQL = """
CREATE TABLE IF NOT EXISTS laporan_forms (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    target_scope TEXT NOT NULL DEFAULT 'all' CHECK (target_scope IN ('all', 'jenjang', 'specific')),
    target_jenjang TEXT,
    allow_multiple BOOLEAN NOT NULL DEFAULT FALSE,
    allow_late BOOLEAN NOT NULL DEFAULT FALSE,
    very_late_after_minutes INTEGER NOT NULL DEFAULT 180,
    no_submission_after_minutes INTEGER,
    no_submission_jenjangs TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_paused BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('draft', 'published')),
    repeat_policy TEXT NOT NULL DEFAULT 'once' CHECK (repeat_policy IN ('once', 'multiple', 'daily', 'weekly', 'monthly')),
    repeat_until_at TIMESTAMPTZ,
    repeat_deadline_time TIME,
    repeat_deadline_day INTEGER,
    deadline_at TIMESTAMPTZ,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_LAPORAN_FORMS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_laporan_forms_active ON laporan_forms (is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_laporan_forms_paused ON laporan_forms (is_paused, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_laporan_forms_scope ON laporan_forms (target_scope);
CREATE INDEX IF NOT EXISTS idx_laporan_forms_status ON laporan_forms (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_laporan_forms_repeat_policy ON laporan_forms (repeat_policy, repeat_until_at);
"""

_LAPORAN_FORMS_STATUS_MIGRATION_SQL = """
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'published';
DO $$
BEGIN
    ALTER TABLE laporan_forms
    ADD CONSTRAINT laporan_forms_status_check
    CHECK (status IN ('draft', 'published'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
UPDATE laporan_forms SET status = 'published' WHERE status IS NULL;
"""

_LAPORAN_FORMS_PAUSE_MIGRATION_SQL = """
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS is_paused BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_laporan_forms_paused ON laporan_forms (is_paused, created_at DESC);
"""

_LAPORAN_REPEAT_POLICY_MIGRATION_SQL = """
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS repeat_policy TEXT NOT NULL DEFAULT 'once';
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS repeat_until_at TIMESTAMPTZ;
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS repeat_deadline_time TIME;
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS repeat_deadline_day INTEGER;
DO $$
BEGIN
    ALTER TABLE laporan_forms
    ADD CONSTRAINT laporan_forms_repeat_policy_check
    CHECK (repeat_policy IN ('once', 'multiple', 'daily', 'weekly', 'monthly'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
UPDATE laporan_forms
SET repeat_policy = CASE WHEN allow_multiple THEN 'multiple' ELSE 'once' END
WHERE repeat_policy IS NULL OR (repeat_policy = 'once' AND allow_multiple = TRUE);
"""

_LAPORAN_FORM_TARGETS_SQL = """
CREATE TABLE IF NOT EXISTS laporan_form_targets (
    id SERIAL PRIMARY KEY,
    form_id INTEGER NOT NULL REFERENCES laporan_forms(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    UNIQUE (form_id, school_id)
);
"""

_LAPORAN_FORM_TARGETS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_laporan_form_targets_form ON laporan_form_targets (form_id);
CREATE INDEX IF NOT EXISTS idx_laporan_form_targets_school ON laporan_form_targets (school_id);
"""

_LAPORAN_FORM_FIELDS_SQL = """
CREATE TABLE IF NOT EXISTS laporan_form_fields (
    id SERIAL PRIMARY KEY,
    form_id INTEGER NOT NULL REFERENCES laporan_forms(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    field_type TEXT NOT NULL DEFAULT 'text' CHECK (field_type IN ('text', 'textarea', 'radio', 'checkbox', 'file', 'upload_dokumen', 'upload_gambar', 'date', 'number', 'rating', 'dropdown', 'time', 'email', 'header', 'info', 'link')),
    options_json JSONB,
    required BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_LAPORAN_FORM_FIELDS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_laporan_form_fields_form ON laporan_form_fields (form_id, sort_order);
"""

_LAPORAN_SUBMISSIONS_SQL = """
CREATE TABLE IF NOT EXISTS laporan_submissions (
    id SERIAL PRIMARY KEY,
    form_id INTEGER NOT NULL REFERENCES laporan_forms(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    submitted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('draft', 'submitted', 'no_submission')),
    submitted_at TIMESTAMPTZ,
    is_late BOOLEAN NOT NULL DEFAULT FALSE,
    late_days INTEGER DEFAULT 0,
    late_minutes INTEGER DEFAULT 0,
    repeat_period_key TEXT,
    repeat_period_label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_LAPORAN_SUBMISSIONS_REPEAT_PERIOD_MIGRATION_SQL = """
ALTER TABLE laporan_submissions ADD COLUMN IF NOT EXISTS repeat_period_key TEXT;
ALTER TABLE laporan_submissions ADD COLUMN IF NOT EXISTS repeat_period_label TEXT;
"""

_LAPORAN_SUBMISSIONS_STATUS_CHECK_MIGRATION_SQL = """
ALTER TABLE laporan_submissions DROP CONSTRAINT IF EXISTS laporan_submissions_status_check;
ALTER TABLE laporan_submissions ADD CONSTRAINT laporan_submissions_status_check 
CHECK (status IN ('draft', 'submitted', 'no_submission'));
"""

_LAPORAN_FORMS_LATE_MIGRATION_SQL = """
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS allow_late BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS very_late_after_minutes INTEGER NOT NULL DEFAULT 180;
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS no_submission_after_minutes INTEGER;
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS no_submission_jenjangs TEXT;
"""

_LAPORAN_FORMS_STATUS_FILTER_MIGRATION_SQL = """
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS no_submission_statuses TEXT;
"""

_LAPORAN_SUBMISSIONS_LATE_MIGRATION_SQL = """
ALTER TABLE laporan_submissions ADD COLUMN IF NOT EXISTS is_late BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE laporan_submissions ADD COLUMN IF NOT EXISTS late_days INTEGER DEFAULT 0;
ALTER TABLE laporan_submissions ADD COLUMN IF NOT EXISTS late_minutes INTEGER DEFAULT 0;
"""

_LAPORAN_FIELDS_CONSTRAINT_MIGRATION_SQL = """
ALTER TABLE laporan_form_fields DROP CONSTRAINT IF EXISTS laporan_form_fields_field_type_check;
ALTER TABLE laporan_form_fields ADD CONSTRAINT laporan_form_fields_field_type_check 
CHECK (field_type IN ('text', 'textarea', 'radio', 'checkbox', 'file', 'upload_dokumen', 'upload_gambar', 'date', 'number', 'rating', 'dropdown', 'time', 'email', 'header', 'info', 'link'));
"""

_LAPORAN_SUBMISSIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_laporan_submissions_form ON laporan_submissions (form_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_laporan_submissions_school ON laporan_submissions (school_id, form_id);
CREATE INDEX IF NOT EXISTS idx_laporan_submissions_status ON laporan_submissions (status);
CREATE INDEX IF NOT EXISTS idx_laporan_submissions_is_late ON laporan_submissions (is_late);
CREATE INDEX IF NOT EXISTS idx_laporan_submissions_period ON laporan_submissions (form_id, school_id, repeat_period_key);
CREATE UNIQUE INDEX IF NOT EXISTS ux_laporan_submissions_period
    ON laporan_submissions (form_id, school_id, repeat_period_key)
    WHERE status = 'submitted' AND repeat_period_key IS NOT NULL;
"""

_LAPORAN_SUBMISSION_ANSWERS_SQL = """
CREATE TABLE IF NOT EXISTS laporan_submission_answers (
    id SERIAL PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES laporan_submissions(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES laporan_form_fields(id) ON DELETE CASCADE,
    answer_text TEXT,
    answer_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (submission_id, field_id)
);
"""

_LAPORAN_SUBMISSION_ANSWERS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_laporan_answers_submission ON laporan_submission_answers (submission_id);
CREATE INDEX IF NOT EXISTS idx_laporan_answers_field ON laporan_submission_answers (field_id);
"""

_LAPORAN_SUBMISSION_ANSWERS_UNIQUE_MIGRATION_SQL = """
DO $$
BEGIN
    IF to_regclass('public.laporan_submission_files') IS NOT NULL THEN
        WITH ranked AS (
            SELECT
                id,
                FIRST_VALUE(id) OVER (
                    PARTITION BY submission_id, field_id
                    ORDER BY id DESC
                ) AS keep_id,
                ROW_NUMBER() OVER (
                    PARTITION BY submission_id, field_id
                    ORDER BY id DESC
                ) AS rn
            FROM laporan_submission_answers
        )
        UPDATE laporan_submission_files sf
        SET answer_id = ranked.keep_id
        FROM ranked
        WHERE sf.answer_id = ranked.id
          AND ranked.rn > 1;
    END IF;
END $$;

WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY submission_id, field_id
            ORDER BY id DESC
        ) AS rn
    FROM laporan_submission_answers
)
DELETE FROM laporan_submission_answers a
USING ranked
WHERE a.id = ranked.id
  AND ranked.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS ux_laporan_submission_answers_submission_field
    ON laporan_submission_answers (submission_id, field_id);
"""

_LAPORAN_SUBMISSION_FILES_SQL = """
CREATE TABLE IF NOT EXISTS laporan_submission_files (
    id SERIAL PRIMARY KEY,
    answer_id INTEGER NOT NULL REFERENCES laporan_submission_answers(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    original_name TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_LAPORAN_SUBMISSION_FILES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_laporan_files_answer ON laporan_submission_files (answer_id);
"""


def ensure_laporan_schema() -> None:
    """Create laporan (form reports) tables without touching unrelated schema."""
    statements = (
        _LAPORAN_FORMS_SQL,
        _LAPORAN_FORMS_STATUS_MIGRATION_SQL,
        _LAPORAN_FORMS_PAUSE_MIGRATION_SQL,
        _LAPORAN_REPEAT_POLICY_MIGRATION_SQL,
        _LAPORAN_FORMS_LATE_MIGRATION_SQL,
        _LAPORAN_FORMS_STATUS_FILTER_MIGRATION_SQL,
        _LAPORAN_FORMS_INDEX_SQL,
        _LAPORAN_FORM_TARGETS_SQL,
        _LAPORAN_FORM_TARGETS_INDEX_SQL,
        _LAPORAN_FORM_FIELDS_SQL,
        _LAPORAN_FIELDS_CONSTRAINT_MIGRATION_SQL,
        _LAPORAN_FORM_FIELDS_INDEX_SQL,
        _LAPORAN_SUBMISSIONS_SQL,
        _LAPORAN_SUBMISSIONS_STATUS_CHECK_MIGRATION_SQL,
        _LAPORAN_SUBMISSIONS_REPEAT_PERIOD_MIGRATION_SQL,
        _LAPORAN_SUBMISSIONS_LATE_MIGRATION_SQL,
        _LAPORAN_SUBMISSIONS_INDEX_SQL,
        _LAPORAN_SUBMISSION_ANSWERS_SQL,
        _LAPORAN_SUBMISSION_ANSWERS_UNIQUE_MIGRATION_SQL,
        _LAPORAN_SUBMISSION_ANSWERS_INDEX_SQL,
        _LAPORAN_SUBMISSION_FILES_SQL,
        _LAPORAN_SUBMISSION_FILES_INDEX_SQL,
    )
    for i, statement in enumerate(statements):
        try:
            with get_cursor(commit=True) as cur:
                cur.execute(statement)
        except Exception as e:
            print(f"Error executing laporan schema statement #{i + 1}: {e}")
            print(f"Statement: {statement[:100]}...")


def ensure_cms_artikel_schema() -> None:
    """Create CMS artikel tables without touching unrelated dashboard schema."""
    statements: Iterable[str] = (
        _CMS_ARTIKEL_SQL,
        _CMS_ARTIKEL_INDEX_SQL,
        _CMS_ARTIKEL_FILES_SQL,
        _CMS_ARTIKEL_FILES_INDEX_SQL,
    )

    for i, statement in enumerate(statements):
        try:
            with get_cursor(commit=True) as cur:
                cur.execute(statement)
        except Exception as e:
            message = str(e)
            if "pg_type_typname_nsp_index" in message and "cms_artikel" in message:
                continue
            print(f"Error executing CMS artikel schema statement #{i+1}: {e}")
            print(f"Statement: {statement[:100]}...")
            raise

# ===== MONEV BOS/BOP Schema =====

_MONEV_BOS_PERIODS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_periods (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    tw INTEGER NOT NULL CHECK (tw IN (1, 2, 3, 4)),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (year, tw)
);
"""

_MONEV_BOS_PERIODS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_monev_bos_periods_active ON monev_bos_periods (is_active) WHERE is_active = TRUE;
"""

_MONEV_BOS_CHECKLISTS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_checklists (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_TEAMS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_teams (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    leader_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_TEAM_MEMBERS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_team_members (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES monev_bos_teams(id) ON DELETE CASCADE,
    staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, staff_id)
);
"""

_MONEV_BOS_ASSIGNMENTS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_assignments (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES monev_bos_teams(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    period_id INTEGER NOT NULL REFERENCES monev_bos_periods(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (school_id, period_id)
);
"""

_MONEV_BOS_REPORTS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_reports (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    period_id INTEGER NOT NULL REFERENCES monev_bos_periods(id) ON DELETE RESTRICT,
    bosp_receipt_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    bop_receipt_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'in_review', 'completed', 'needs_revision', 'completed_with_notes')),
    assigned_team_id INTEGER REFERENCES monev_bos_teams(id) ON DELETE SET NULL,
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (school_id, period_id)
);
"""

_MONEV_BOS_REPORTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_monev_bos_reports_school ON monev_bos_reports (school_id);
CREATE INDEX IF NOT EXISTS idx_monev_bos_reports_period ON monev_bos_reports (period_id);
CREATE INDEX IF NOT EXISTS idx_monev_bos_reports_status ON monev_bos_reports (status);
"""

_MONEV_BOS_ACTIVITIES_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_activities (
    id SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES monev_bos_reports(id) ON DELETE CASCADE,
    fund_source TEXT NOT NULL CHECK (fund_source IN ('BOS', 'BOP')),
    activity_code TEXT NOT NULL,
    activity_name TEXT NOT NULL,
    account_code TEXT,
    realized_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    vendor_name TEXT,
    bku_number TEXT,
    item_name TEXT,
    item_specs TEXT,
    item_quantity INTEGER,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_review', 'valid', 'invalid')),
    audit_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_ACTIVITIES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_monev_bos_activities_report ON monev_bos_activities (report_id);
"""

_MONEV_BOS_ACTIVITY_DOCS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_activity_docs (
    id SERIAL PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES monev_bos_activities(id) ON DELETE CASCADE,
    doc_type TEXT NOT NULL CHECK (doc_type IN ('transfer', 'invoice', 'live_photo', 'physical_proof', 'field_photo')),
    file_path TEXT NOT NULL,
    file_size INTEGER,
    uploaded_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    lat NUMERIC(9,6),
    lng NUMERIC(9,6),
    is_audit_valid BOOLEAN NOT NULL DEFAULT TRUE,
    photo_audit_notes TEXT,
    photo_audited_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    photo_audited_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_ACTIVITY_DOCS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_monev_bos_activity_docs_activity ON monev_bos_activity_docs (activity_id);
"""

_MONEV_BOS_CHECKLIST_RESULTS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_checklist_results (
    id SERIAL PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES monev_bos_activities(id) ON DELETE CASCADE,
    checklist_id INTEGER NOT NULL REFERENCES monev_bos_checklists(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('yes', 'no', 'na')),
    notes TEXT,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (activity_id, checklist_id)
);
"""

_MONEV_BOS_AUDIT_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_audit_logs (
    id SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES monev_bos_reports(id) ON DELETE CASCADE,
    activity_id INTEGER REFERENCES monev_bos_activities(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_AUDIT_LOGS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_monev_bos_audit_logs_report ON monev_bos_audit_logs (report_id);
"""

_MONEV_BOS_EDIT_REQUESTS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_edit_requests (
    id SERIAL PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES monev_bos_activities(id) ON DELETE CASCADE,
    requested_by INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    requested_data JSONB,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    review_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_EDIT_REQUESTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_monev_bos_edit_requests_activity ON monev_bos_edit_requests (activity_id);
CREATE INDEX IF NOT EXISTS idx_monev_bos_edit_requests_status ON monev_bos_edit_requests (status);
"""

_MONEV_BOS_ACTIVITY_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_activity_history (
    id SERIAL PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES monev_bos_activities(id) ON DELETE CASCADE,
    changed_by INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    previous_data JSONB,
    change_reason TEXT,
    activity_status_at_change TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_ACTIVITY_HISTORY_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_monev_bos_activity_history_activity ON monev_bos_activity_history (activity_id);
"""


_MONEV_BOS_MASTER_ACTIVITIES_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_master_activities (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    code_prefix TEXT,
    fund_source TEXT DEFAULT 'ALL' CHECK (fund_source IN ('ALL', 'BOS', 'BOP')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_VENDORS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_vendors (
    id SERIAL PRIMARY KEY,
    school_id INTEGER REFERENCES dashboard_users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    npwp VARCHAR(50),
    phone VARCHAR(50),
    address TEXT,
    owner_name VARCHAR(150),
    bank_name VARCHAR(100),
    bank_account VARCHAR(100),
    status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'rejected')),
    rejection_reason TEXT,
    verified_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_VENDORS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_monev_bos_vendors_school ON monev_bos_vendors (school_id);
CREATE INDEX IF NOT EXISTS idx_monev_bos_vendors_status ON monev_bos_vendors (status);
"""

_MONEV_BOS_CHECKLIST_MASTER_ACTIVITIES_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_checklist_master_activities (
    checklist_id INTEGER NOT NULL REFERENCES monev_bos_checklists(id) ON DELETE CASCADE,
    master_activity_id INTEGER NOT NULL REFERENCES monev_bos_master_activities(id) ON DELETE CASCADE,
    PRIMARY KEY (checklist_id, master_activity_id)
);
"""

_MONEV_BOS_EXPENSE_TYPES_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_expense_types (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    code TEXT,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_ACCOUNT_CODES_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_account_codes (
    id SERIAL PRIMARY KEY,
    code VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255),
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_MONEV_BOS_CHECKLIST_EXPENSE_TYPES_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_checklist_expense_types (
    checklist_id INTEGER NOT NULL REFERENCES monev_bos_checklists(id) ON DELETE CASCADE,
    expense_type_id INTEGER NOT NULL REFERENCES monev_bos_expense_types(id) ON DELETE CASCADE,
    PRIMARY KEY (checklist_id, expense_type_id)
);
"""

_MONEV_BOS_SCHOOL_POSTS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_school_posts (
    id SERIAL PRIMARY KEY,
    school_user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    photo_path TEXT NOT NULL,
    photo_size INTEGER NOT NULL CHECK (photo_size > 0 AND photo_size <= 204800),
    latitude NUMERIC(10,7) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude NUMERIC(10,7) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    location_accuracy NUMERIC(10,2),
    location_text VARCHAR(100) NOT NULL,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    story_expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days'),
    deleted_at TIMESTAMPTZ,
    deleted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_monev_bos_school_posts_school_created
    ON monev_bos_school_posts (school_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_monev_bos_school_posts_story
    ON monev_bos_school_posts (story_expires_at DESC)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_monev_bos_school_posts_search
    ON monev_bos_school_posts USING GIN (to_tsvector('simple', title || ' ' || location_text));
"""

_MONEV_BOS_ACTIVITY_POST_LINKS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_activity_post_links (
    id SERIAL PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES monev_bos_activities(id) ON DELETE CASCADE,
    post_id INTEGER NOT NULL REFERENCES monev_bos_school_posts(id) ON DELETE RESTRICT,
    activity_doc_id INTEGER REFERENCES monev_bos_activity_docs(id) ON DELETE SET NULL,
    linked_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    copied_on_post_delete_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_monev_bos_activity_post_links_post
    ON monev_bos_activity_post_links (post_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_monev_bos_activity_post_links_activity_post
    ON monev_bos_activity_post_links (activity_id, post_id);
"""

_MONEV_BOS_STORY_AUDIT_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS monev_bos_story_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES monev_bos_school_posts(id) ON DELETE SET NULL,
    school_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    activity_id INTEGER REFERENCES monev_bos_activities(id) ON DELETE SET NULL,
    actor_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    action VARCHAR(30) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_monev_bos_story_audit_logs_post
    ON monev_bos_story_audit_logs (post_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_monev_bos_story_audit_logs_actor
    ON monev_bos_story_audit_logs (actor_id, created_at DESC);
"""


def ensure_monev_bos_schema() -> None:
    statements = (
        _MONEV_BOS_VENDORS_SQL,
        _MONEV_BOS_VENDORS_INDEX_SQL,
        "ALTER TABLE monev_bos_vendors DROP CONSTRAINT IF EXISTS monev_bos_vendors_school_id_fkey;",
        "ALTER TABLE monev_bos_vendors ADD CONSTRAINT monev_bos_vendors_school_id_fkey FOREIGN KEY (school_id) REFERENCES dashboard_users(id) ON DELETE CASCADE;",
        "ALTER TABLE monev_bos_vendors ADD COLUMN IF NOT EXISTS vendor_type VARCHAR(20) NOT NULL DEFAULT 'vendor' CHECK (vendor_type IN ('vendor', 'narsum'));",
        _MONEV_BOS_PERIODS_SQL,
        _MONEV_BOS_PERIODS_INDEX_SQL,
        _MONEV_BOS_CHECKLISTS_SQL,
        _MONEV_BOS_TEAMS_SQL,
        _MONEV_BOS_TEAM_MEMBERS_SQL,
        _MONEV_BOS_ASSIGNMENTS_SQL,
        _MONEV_BOS_REPORTS_SQL,
        _MONEV_BOS_REPORTS_INDEX_SQL,
        _MONEV_BOS_MASTER_ACTIVITIES_SQL,
        _MONEV_BOS_EXPENSE_TYPES_SQL,
        _MONEV_BOS_ACCOUNT_CODES_SQL,
        _MONEV_BOS_ACTIVITIES_SQL,
        _MONEV_BOS_ACTIVITIES_INDEX_SQL,
        "ALTER TABLE monev_bos_activities ADD COLUMN IF NOT EXISTS vendor_id INTEGER REFERENCES monev_bos_vendors(id) ON DELETE SET NULL;",
        "ALTER TABLE monev_bos_activities ADD COLUMN IF NOT EXISTS activity_type_id INTEGER REFERENCES monev_bos_master_activities(id) ON DELETE SET NULL;",
        "ALTER TABLE monev_bos_activities ADD COLUMN IF NOT EXISTS expense_type_id INTEGER REFERENCES monev_bos_expense_types(id) ON DELETE SET NULL;",
        "ALTER TABLE monev_bos_activities ADD COLUMN IF NOT EXISTS account_code TEXT;",
        "ALTER TABLE monev_bos_activities DROP CONSTRAINT IF EXISTS monev_bos_activities_status_check;",
        "ALTER TABLE monev_bos_activities ADD CONSTRAINT monev_bos_activities_status_check CHECK (status IN ('pending', 'in_review', 'valid', 'invalid'));",
        _MONEV_BOS_ACTIVITY_DOCS_SQL,
        _MONEV_BOS_ACTIVITY_DOCS_INDEX_SQL,
        "ALTER TABLE monev_bos_activity_docs ADD COLUMN IF NOT EXISTS is_audit_valid BOOLEAN NOT NULL DEFAULT TRUE;",
        "ALTER TABLE monev_bos_activity_docs ADD COLUMN IF NOT EXISTS photo_audit_notes TEXT;",
        "ALTER TABLE monev_bos_activity_docs ADD COLUMN IF NOT EXISTS photo_audited_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL;",
        "ALTER TABLE monev_bos_activity_docs ADD COLUMN IF NOT EXISTS photo_audited_at TIMESTAMPTZ;",
        "ALTER TABLE monev_bos_activity_docs DROP CONSTRAINT IF EXISTS monev_bos_activity_docs_doc_type_check;",
        "ALTER TABLE monev_bos_activity_docs ADD CONSTRAINT monev_bos_activity_docs_doc_type_check CHECK (doc_type IN ('transfer', 'invoice', 'live_photo', 'physical_proof', 'field_photo'));",
        _MONEV_BOS_CHECKLISTS_SQL,
        _MONEV_BOS_CHECKLIST_MASTER_ACTIVITIES_SQL,
        _MONEV_BOS_CHECKLIST_EXPENSE_TYPES_SQL,
        _MONEV_BOS_CHECKLIST_RESULTS_SQL,
        _MONEV_BOS_AUDIT_LOGS_SQL,
        _MONEV_BOS_AUDIT_LOGS_INDEX_SQL,
        _MONEV_BOS_EDIT_REQUESTS_SQL,
        _MONEV_BOS_EDIT_REQUESTS_INDEX_SQL,
        _MONEV_BOS_ACTIVITY_HISTORY_SQL,
        _MONEV_BOS_ACTIVITY_HISTORY_INDEX_SQL,
        _MONEV_BOS_SCHOOL_POSTS_SQL,
        _MONEV_BOS_ACTIVITY_POST_LINKS_SQL,
        "ALTER TABLE monev_bos_activity_post_links DROP CONSTRAINT IF EXISTS monev_bos_activity_post_links_activity_id_key;",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_monev_bos_activity_post_links_activity_post ON monev_bos_activity_post_links (activity_id, post_id);",
        _MONEV_BOS_STORY_AUDIT_LOGS_SQL,
    )
    for i, statement in enumerate(statements):
        try:
            with get_cursor(commit=True) as cur:
                cur.execute(statement)
        except Exception as e:
            print(f"Error executing MONEV BOS schema statement #{i + 1}: {e}")
            print(f"Statement: {statement[:100]}...")


__all__ = ["ensure_dashboard_schema", "ensure_cms_artikel_schema", "ensure_laporan_schema", "ensure_monev_bos_schema"]
