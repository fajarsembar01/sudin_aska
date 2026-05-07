CREATE TABLE IF NOT EXISTS hospitality_preview_access (
    user_id INTEGER PRIMARY KEY REFERENCES dashboard_users(id) ON DELETE CASCADE,
    granted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hospitality_preview_access_granted_by
    ON hospitality_preview_access (granted_by);
