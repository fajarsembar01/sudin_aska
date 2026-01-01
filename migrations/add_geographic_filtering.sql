-- Geographic Filtering Migration
-- Date: 2025-12-30
-- Purpose: Add kecamatan filter and dual coordinator support

-- ==========================================
-- ADD NEW COLUMNS
-- ==========================================

-- Geographic assignment (which kecamatan user works in)
ALTER TABLE dashboard_users 
ADD COLUMN kecamatan_id INT;

-- Coordinator type (seksi vs wilayah)
ALTER TABLE dashboard_users 
ADD COLUMN coordinator_type VARCHAR(20);

-- Secondary supervisor for dual reporting (optional)
ALTER TABLE dashboard_users 
ADD COLUMN secondary_supervisor_id INT;

-- ==========================================
-- ADD CONSTRAINTS
-- ==========================================

-- Foreign key to kecamatan
ALTER TABLE dashboard_users
ADD CONSTRAINT fk_users_kecamatan 
  FOREIGN KEY (kecamatan_id) REFERENCES portal_kecamatan(id) ON DELETE SET NULL;

-- Foreign key to secondary supervisor
ALTER TABLE dashboard_users
ADD CONSTRAINT fk_users_secondary_supervisor
  FOREIGN KEY (secondary_supervisor_id) REFERENCES dashboard_users(id) ON DELETE SET NULL;

-- Check constraint for coordinator_type
ALTER TABLE dashboard_users
ADD CONSTRAINT chk_coordinator_type
  CHECK (coordinator_type IN ('seksi', 'wilayah') OR coordinator_type IS NULL);

-- ==========================================
-- CREATE INDEXES
-- ==========================================

CREATE INDEX idx_users_kecamatan ON dashboard_users(kecamatan_id);
CREATE INDEX idx_users_coordinator_type ON dashboard_users(coordinator_type);
CREATE INDEX idx_users_secondary_supervisor ON dashboard_users(secondary_supervisor_id);

-- ==========================================
-- UPDATE EXISTING COORDINATORS
-- ==========================================

-- Mark existing section coordinators as 'seksi' type
UPDATE dashboard_users 
SET coordinator_type = 'seksi'
WHERE role = 'coordinator' 
  AND section_id IS NOT NULL;

-- ==========================================
-- VERIFICATION
-- ==========================================

-- Check new columns
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_name = 'dashboard_users' 
  AND column_name IN ('kecamatan_id', 'coordinator_type', 'secondary_supervisor_id')
ORDER BY column_name;

-- Check coordinators with types
SELECT 
    id,
    email,
    full_name,
    role,
    coordinator_type,
    section_id,
    kecamatan_id
FROM dashboard_users 
WHERE role = 'coordinator'
ORDER BY coordinator_type, full_name;

-- Success message
SELECT '✅ Geographic filtering columns added successfully' as status;
