-- Migration: Monev Team Configuration
-- Date: 2025-12-30
-- Purpose: Create tables for managing monev teams per kecamatan

-- =====================================================
-- 1. Create Monev Teams Table
-- =====================================================

CREATE TABLE IF NOT EXISTS monev_teams (
    id SERIAL PRIMARY KEY,
    kecamatan_id INTEGER NOT NULL REFERENCES portal_kecamatan(id) ON DELETE CASCADE,
    coordinator_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kecamatan_id)
);

COMMENT ON TABLE monev_teams IS 'Monitoring and evaluation teams per kecamatan';
COMMENT ON COLUMN monev_teams.kecamatan_id IS 'Reference to kecamatan this team is responsible for';
COMMENT ON COLUMN monev_teams.coordinator_id IS 'Team coordinator (usually role=coordinator)';
COMMENT ON COLUMN monev_teams.name IS 'Team name (e.g., "Tim Monev Cilincing")';

-- =====================================================
-- 2. Create Monev Team Members Table
-- =====================================================

CREATE TABLE IF NOT EXISTS monev_team_members (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES monev_teams(id) ON DELETE CASCADE,
    staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    added_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    UNIQUE (team_id, staff_id)
);

COMMENT ON TABLE monev_team_members IS 'Members of monev teams';
COMMENT ON COLUMN monev_team_members.team_id IS 'Reference to monev team';
COMMENT ON COLUMN monev_team_members.staff_id IS 'Staff member assigned to this team';
COMMENT ON COLUMN monev_team_members.added_by IS 'Admin who added this member';

-- =====================================================
-- 3. Create Indexes for Performance
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_monev_teams_kecamatan ON monev_teams(kecamatan_id);
CREATE INDEX IF NOT EXISTS idx_monev_teams_coordinator ON monev_teams(coordinator_id);
CREATE INDEX IF NOT EXISTS idx_monev_members_team ON monev_team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_monev_members_staff ON monev_team_members(staff_id);

-- =====================================================
-- 4. Initialize Teams for Existing Kecamatans
-- =====================================================

-- Auto-create teams for existing kecamatans with default names
INSERT INTO monev_teams (kecamatan_id, name)
SELECT 
    id, 
    'Tim Monev ' || name
FROM portal_kecamatan
WHERE id NOT IN (SELECT kecamatan_id FROM monev_teams)
ON CONFLICT (kecamatan_id) DO NOTHING;

-- =====================================================
-- Migration Complete
-- =====================================================
