CREATE TABLE IF NOT EXISTS cc_staff_access (
    user_id INTEGER PRIMARY KEY REFERENCES dashboard_users(id) ON DELETE CASCADE,
    granted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
