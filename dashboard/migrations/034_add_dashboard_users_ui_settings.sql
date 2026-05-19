-- Migration 034: Add dashboard_users.ui_settings for per-user dashboard preferences

ALTER TABLE dashboard_users
ADD COLUMN IF NOT EXISTS ui_settings JSONB NOT NULL DEFAULT '{}'::jsonb;
