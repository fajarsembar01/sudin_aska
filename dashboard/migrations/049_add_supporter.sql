-- Migration 049: Supporter task, point, and Telegram verification system

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

ALTER TABLE supporter_tasks
ADD COLUMN IF NOT EXISTS action_types JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE supporter_tasks
ADD COLUMN IF NOT EXISTS end_at TIMESTAMPTZ;

ALTER TABLE supporter_tasks
ALTER COLUMN late_penalty_percent SET DEFAULT 50;

UPDATE supporter_tasks
SET action_types = jsonb_build_array(action_type)
WHERE action_types = '[]'::jsonb
  AND COALESCE(action_type, '') <> '';

CREATE INDEX IF NOT EXISTS idx_supporter_tasks_status_deadline
ON supporter_tasks (status, deadline_at);

CREATE INDEX IF NOT EXISTS idx_supporter_tasks_status_end
ON supporter_tasks (status, end_at);

CREATE INDEX IF NOT EXISTS idx_supporter_tasks_platform_action
ON supporter_tasks (platform, action_type);

CREATE INDEX IF NOT EXISTS idx_supporter_tasks_action_types
ON supporter_tasks USING GIN (action_types);

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

CREATE INDEX IF NOT EXISTS idx_supporter_submissions_staff_status
ON supporter_submissions (staff_id, status, submitted_at DESC);

CREATE INDEX IF NOT EXISTS idx_supporter_submissions_task_status
ON supporter_submissions (task_id, status, submitted_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_supporter_point_events_staff_created
ON supporter_point_events (staff_id, created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_supporter_activity_logs_created
ON supporter_activity_logs (created_at DESC);

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

ALTER TABLE telegram_admin_accounts ADD COLUMN IF NOT EXISTS notification_scope TEXT NOT NULL DEFAULT 'default';
ALTER TABLE telegram_admin_accounts DROP CONSTRAINT IF EXISTS telegram_admin_accounts_telegram_username_key;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'telegram_admin_accounts_telegram_username_scope_key') THEN
    ALTER TABLE telegram_admin_accounts ADD CONSTRAINT telegram_admin_accounts_telegram_username_scope_key UNIQUE (telegram_username, notification_scope);
  END IF;
END $$;
