-- Database Cleanup Migration
-- Date: 2025-12-30
-- Purpose: Remove deprecated admin_level and access_scope columns

-- ==========================================
-- BACKUP CHECK: Ensure backup columns exist
-- ==========================================

-- Verify backup columns were created (optional safety check)
-- SELECT column_name FROM information_schema.columns 
-- WHERE table_name = 'dashboard_users' 
-- AND column_name IN ('admin_level_backup', 'access_scope_backup');

-- ==========================================
-- DROP DEPRECATED COLUMNS
-- ==========================================

-- These columns are no longer used in the simplified role system
-- Role-based access now uses: role (admin/coordinator/staff/sekolah)
-- Team hierarchy uses: section_id, supervisor_id

ALTER TABLE dashboard_users 
DROP COLUMN IF EXISTS admin_level CASCADE;

ALTER TABLE dashboard_users 
DROP COLUMN IF EXISTS access_scope CASCADE;

-- Optional: Also drop backup columns after verification
-- ALTER TABLE dashboard_users 
-- DROP COLUMN IF EXISTS admin_level_backup CASCADE;

-- ALTER TABLE dashboard_users 
-- DROP COLUMN IF EXISTS access_scope_backup CASCADE;

-- ==========================================
-- VERIFICATION
-- ==========================================

-- Check remaining columns
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'dashboard_users' 
ORDER BY ordinal_position;

-- Check users with new structure
SELECT 
    id,
    email,
    full_name,
    role,
    section_id,
    supervisor_id,
    account_status
FROM dashboard_users 
WHERE role IN ('admin', 'coordinator', 'staff')
ORDER BY role, section_id, full_name
LIMIT 10;

-- ==========================================
-- SUCCESS MESSAGE
-- ==========================================

-- Migration complete!
-- Old columns removed: admin_level, access_scope
-- New system uses: role, section_id, supervisor_id
