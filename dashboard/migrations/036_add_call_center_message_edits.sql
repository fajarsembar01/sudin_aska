ALTER TABLE cc_messages
    ADD COLUMN IF NOT EXISTS original_message_text TEXT,
    ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS edited_by_admin_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL;
