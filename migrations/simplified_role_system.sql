-- Migration: Simplified Role System with Sections
-- Date: 2025-12-30
-- Purpose: Add sections table and simplify user roles

-- ==========================================
-- Step 1: Create sections table
-- ==========================================

CREATE TABLE IF NOT EXISTS sections (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    coordinator_id INT REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- Step 2: Insert initial sections
-- ==========================================

INSERT INTO sections (name, description) VALUES
('PAUD & PMPK', 'Pendidikan Anak Usia Dini dan Pendidikan Masyarakat & Pendidikan Khusus'),
('SD', 'Sekolah Dasar'),
('SMP & SMA', 'Sekolah Menengah Pertama dan Atas'),
('SMK, Kursus & Pelatihan', 'Sekolah Menengah Kejuruan, Kursus dan Pelatihan'),
('PTK', 'Pendidik dan Tenaga Kependidikan')
ON CONFLICT DO NOTHING;

-- ==========================================
-- Step 3: Add new columns to dashboard_users
-- ==========================================

-- Add section and supervisor tracking
ALTER TABLE dashboard_users 
ADD COLUMN IF NOT EXISTS section_id INT REFERENCES sections(id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS supervisor_id INT REFERENCES dashboard_users(id) ON DELETE SET NULL;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_section ON dashboard_users(section_id);
CREATE INDEX IF NOT EXISTS idx_users_supervisor ON dashboard_users(supervisor_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON dashboard_users(role);

-- ==========================================
-- Step 4: BACKUP old admin fields (optional)
-- ==========================================

-- Create backup columns in case we need to rollback
ALTER TABLE dashboard_users 
ADD COLUMN IF NOT EXISTS admin_level_backup VARCHAR(50),
ADD COLUMN IF NOT EXISTS access_scope_backup VARCHAR(50);

-- Copy existing values to backup
UPDATE dashboard_users 
SET admin_level_backup = admin_level,
    access_scope_backup = access_scope
WHERE admin_level IS NOT NULL OR access_scope IS NOT NULL;

-- ==========================================
-- Step 5: Remove old complexity fields
-- ==========================================

-- WARNING: This is permanent! Make sure to backup first
-- Uncomment the following lines when ready:

-- ALTER TABLE dashboard_users DROP COLUMN IF EXISTS admin_level;
-- ALTER TABLE dashboard_users DROP COLUMN IF EXISTS access_scope;

-- For now, we'll keep them for safety during testing
-- They can be removed after verification

-- ==========================================
-- Step 6: Migration Notes
-- ==========================================

-- MANUAL STEPS REQUIRED:
-- 1. Identify which users should be coordinators (Kepala Seksi)
-- 2. Update their role to 'coordinator' and assign section_id
-- 3. Assign staff members to sections and set their supervisor_id
--
-- Example:
-- UPDATE dashboard_users 
-- SET role = 'coordinator', 
--     section_id = (SELECT id FROM sections WHERE name = 'SD')
-- WHERE email = 'mulyadi@example.com';
--
-- UPDATE dashboard_users 
-- SET section_id = (SELECT id FROM sections WHERE name = 'SD'),
--     supervisor_id = (SELECT id FROM dashboard_users WHERE email = 'mulyadi@example.com')
-- WHERE jabatan LIKE '%Staff Seksi SD%' AND role = 'staff';

-- ==========================================
-- Verification Queries
-- ==========================================

-- Check sections created
SELECT * FROM sections ORDER BY id;

-- Check users with sections assigned
SELECT 
    u.email,
    u.role,
    s.name as section_name,
    sup.full_name as supervisor_name
FROM dashboard_users u
LEFT JOIN sections s ON u.section_id = s.id
LEFT JOIN dashboard_users sup ON u.supervisor_id = sup.id
WHERE u.section_id IS NOT NULL OR u.supervisor_id IS NOT NULL;

-- Check for any remaining admin_level/access_scope values
SELECT 
    COUNT(*) as users_with_old_fields,
    COUNT(CASE WHEN admin_level IS NOT NULL THEN 1 END) as has_admin_level,
    COUNT(CASE WHEN access_scope IS NOT NULL THEN 1 END) as has_access_scope
FROM dashboard_users;
