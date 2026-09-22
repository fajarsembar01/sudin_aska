ALTER TABLE monev_bos_activities
    ADD COLUMN IF NOT EXISTS needs_item_check BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS item_check_marked_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS item_check_marked_at TIMESTAMPTZ;
