-- Migration 031: Add hospitality activity logs table
BEGIN;

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

CREATE INDEX IF NOT EXISTS idx_hospitality_activity_logs_created ON hospitality_activity_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hospitality_activity_logs_target ON hospitality_activity_logs (target_type, target_id);

COMMIT;
