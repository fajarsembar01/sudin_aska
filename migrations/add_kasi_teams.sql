-- Migration: Add Kasi Teams Support
-- Run this after create_monev_teams.sql

-- Step 1: Add team_type column to distinguish Kasi vs Kecamatan teams
ALTER TABLE monev_teams ADD COLUMN IF NOT EXISTS team_type VARCHAR(20) DEFAULT 'kecamatan';

-- Step 2: Add team_name column for Kasi teams (they don't have kecamatan_id)
ALTER TABLE monev_teams ADD COLUMN IF NOT EXISTS team_name VARCHAR(100);

-- Step 3: Update existing teams to have explicit team_type
UPDATE monev_teams SET team_type = 'kecamatan' WHERE kecamatan_id IS NOT NULL;

-- Step 4: Create Kasi teams
INSERT INTO monev_teams (kecamatan_id, team_type, team_name, coordinator_id) VALUES
(NULL, 'kasi', 'PAUD PMPK', NULL),
(NULL, 'kasi', 'SD', NULL),
(NULL, 'kasi', 'SMP SMA', NULL),
(NULL, 'kasi', 'SMK, Kursus & Pelatihan', NULL)
ON CONFLICT DO NOTHING;

-- Verify
SELECT id, team_type, team_name, kecamatan_id, coordinator_id FROM monev_teams ORDER BY team_type, id;
