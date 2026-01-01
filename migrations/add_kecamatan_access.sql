-- Migration: Add Kecamatan Access Control, Staff Assignments, and Classroom Configuration
-- Created: 2025-12-29
-- Description: Implements kecamatan-based access control for admins, staff-school assignments, and classroom configuration

-- ============================================
-- 1. User Kecamatan Access (Many-to-Many)
-- ============================================

-- Junction table linking users (admins) to kecamatans they can access
CREATE TABLE IF NOT EXISTS user_kecamatan (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    kecamatan_id INTEGER NOT NULL REFERENCES portal_kecamatan(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    UNIQUE (user_id, kecamatan_id)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_user_kecamatan_user ON user_kecamatan (user_id);
CREATE INDEX IF NOT EXISTS idx_user_kecamatan_kecamatan ON user_kecamatan (kecamatan_id);

-- Add constraint to limit admins to maximum 3 kecamatans
-- Note: This is enforced at application level, but we add a trigger for database-level enforcement
CREATE OR REPLACE FUNCTION check_kecamatan_limit()
RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT COUNT(*) FROM user_kecamatan WHERE user_id = NEW.user_id) >= 3 THEN
        RAISE EXCEPTION 'User cannot be assigned more than 3 kecamatans';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS enforce_kecamatan_limit ON user_kecamatan;
CREATE TRIGGER enforce_kecamatan_limit
    BEFORE INSERT ON user_kecamatan
    FOR EACH ROW
    EXECUTE FUNCTION check_kecamatan_limit();

-- ============================================
-- 2. Staff School Assignments
-- ============================================

-- Track which schools are assigned to which staff members by admins
CREATE TABLE IF NOT EXISTS staff_school_assignments (
    id SERIAL PRIMARY KEY,
    staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    assigned_by INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT,
    UNIQUE (staff_id, school_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_staff_assignments_staff ON staff_school_assignments (staff_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_school ON staff_school_assignments (school_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_assigned_by ON staff_school_assignments (assigned_by);

-- ============================================
-- 3. School Classroom Configuration
-- ============================================

-- Allow schools to configure classroom variants (e.g., Kelas 1A, 1B, 1C)
CREATE TABLE IF NOT EXISTS school_classrooms (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    grade_level INTEGER,
    variant TEXT,
    capacity INTEGER,
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (school_id, name)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_school_classrooms_school ON school_classrooms (school_id);
CREATE INDEX IF NOT EXISTS idx_school_classrooms_grade ON school_classrooms (grade_level);
CREATE INDEX IF NOT EXISTS idx_school_classrooms_active ON school_classrooms (active);

-- ============================================
-- 4. Data Migration: Assign All Admins to All Kecamatans
-- ============================================

-- Get all admin users and assign them to all 3 kecamatans
-- This ensures backward compatibility - existing admins retain full access
DO $$
DECLARE
    admin_record RECORD;
    kec_record RECORD;
BEGIN
    -- Loop through all admin users
    FOR admin_record IN 
        SELECT id FROM dashboard_users WHERE role = 'admin'
    LOOP
        -- Loop through all kecamatans and assign
        FOR kec_record IN 
            SELECT id FROM portal_kecamatan
        LOOP
            -- Insert if not exists
            INSERT INTO user_kecamatan (user_id, kecamatan_id, assigned_by)
            VALUES (admin_record.id, kec_record.id, NULL)
            ON CONFLICT (user_id, kecamatan_id) DO NOTHING;
        END LOOP;
    END LOOP;
    
    RAISE NOTICE 'Successfully assigned all kecamatans to all admin users';
END $$;

-- ============================================
-- 5. Add Metadata Columns (if needed for future use)
-- ============================================

-- Add kecamatan access metadata to dashboard_users for caching purposes
ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS kecamatan_cache JSONB;

-- Comment on tables
COMMENT ON TABLE user_kecamatan IS 'Junction table for admin user kecamatan access control';
COMMENT ON TABLE staff_school_assignments IS 'Tracks admin-assigned schools for staff members';
COMMENT ON TABLE school_classrooms IS 'School classroom configuration (e.g., Kelas 1A, 1B, 1C)';

-- ============================================
-- Migration Complete
-- ============================================

-- Verify migration
DO $$
DECLARE
    admin_count INTEGER;
    kec_count INTEGER;
    assignment_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO admin_count FROM dashboard_users WHERE role = 'admin';
    SELECT COUNT(*) INTO kec_count FROM portal_kecamatan;
    SELECT COUNT(*) INTO assignment_count FROM user_kecamatan;
    
    RAISE NOTICE '==============================================';
    RAISE NOTICE 'Migration Summary:';
    RAISE NOTICE 'Admin users: %', admin_count;
    RAISE NOTICE 'Kecamatans: %', kec_count;
    RAISE NOTICE 'User-Kecamatan assignments: %', assignment_count;
    RAISE NOTICE 'Expected assignments: % (% admins × % kecamatans)', 
                 admin_count * kec_count, admin_count, kec_count;
    RAISE NOTICE '==============================================';
END $$;
