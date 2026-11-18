ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS assessment_mode TEXT NOT NULL DEFAULT 'individual' CHECK (assessment_mode IN ('individual', 'team'));
ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS monev_team_id INTEGER;
ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS team_name_snapshot TEXT;
ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS team_members_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS submitted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_portal_assessments_mode ON portal_assessments (assessment_mode, status, period_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_portal_team_one_draft ON portal_assessments (school_id) WHERE assessment_mode = 'team' AND status = 'draft';
CREATE TABLE IF NOT EXISTS portal_team_assessment_settings (
    school_id INTEGER PRIMARY KEY REFERENCES portal_schools(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS portal_assessment_field_versions (
    assessment_id INTEGER NOT NULL REFERENCES portal_assessments(id) ON DELETE CASCADE,
    school_room_id INTEGER NOT NULL REFERENCES portal_school_rooms(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    edited_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (assessment_id, school_room_id, field_key)
);
CREATE TABLE IF NOT EXISTS portal_assessment_presence (
    assessment_id INTEGER NOT NULL REFERENCES portal_assessments(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    client_id VARCHAR(64) NOT NULL,
    school_room_id INTEGER REFERENCES portal_school_rooms(id) ON DELETE CASCADE,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (assessment_id, user_id, client_id)
);
ALTER TABLE portal_assessment_photos ADD COLUMN IF NOT EXISTS uploaded_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL;
ALTER TABLE portal_assessments ADD COLUMN IF NOT EXISTS period_locked BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE portal_assessments SET period_locked = TRUE WHERE period_locked = FALSE AND (status IN ('submitted', 'verified') OR submitted_at IS NOT NULL);
CREATE TABLE IF NOT EXISTS portal_assessment_team_events (
    id BIGSERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES portal_assessments(id) ON DELETE CASCADE,
    school_room_id INTEGER REFERENCES portal_school_rooms(id) ON DELETE SET NULL,
    field_key TEXT NOT NULL,
    user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_portal_team_events_assessment ON portal_assessment_team_events (assessment_id, user_id);
