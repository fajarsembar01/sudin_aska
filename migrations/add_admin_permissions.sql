-- Migration: Add Admin Permissions and Monthly Periods
-- Date: 2025-12-29

-- =====================================================
-- 1. Add Admin Permission Columns
-- =====================================================

ALTER TABLE dashboard_users
ADD COLUMN IF NOT EXISTS admin_level VARCHAR(20) DEFAULT 'viewer',
ADD COLUMN IF NOT EXISTS access_scope VARCHAR(20) DEFAULT 'portal_only';

COMMENT ON COLUMN dashboard_users.admin_level IS 'Admin permission level: superadmin (full CRUD) or viewer (read-only)';
COMMENT ON COLUMN dashboard_users.access_scope IS 'Access scope: portal_only (Portal only) or full_access (Portal + ASKA)';

-- =====================================================
-- 2. Update Existing Admin Users
-- =====================================================

-- Set all existing admins to superadmin with full access
UPDATE dashboard_users 
SET admin_level = 'superadmin', 
    access_scope = 'full_access'
WHERE role = 'admin';

-- =====================================================
-- 3. Migrate Assessment Periods to Monthly (2026)
-- =====================================================

-- Update first existing period to Januari 2026 and make it active
UPDATE portal_assessment_periods
SET name = 'Januari 2026',
    start_date = '2026-01-01',
    end_date = '2026-01-31',
    is_active = TRUE
WHERE id = (SELECT MIN(id) FROM portal_assessment_periods);

-- Deactivate any other periods
UPDATE portal_assessment_periods
SET is_active = FALSE
WHERE name != 'Januari 2026';

-- =====================================================
-- 4. Create Remaining 2026 Monthly Periods
-- =====================================================

-- Insert February through December 2026 if they don't exist
INSERT INTO portal_assessment_periods (name, start_date, end_date, is_active)
SELECT 
    month_name,
    start_date::date,
    end_date::date,
    FALSE as is_active
FROM (VALUES
    ('Februari 2026', '2026-02-01', '2026-02-28'),
    ('Maret 2026', '2026-03-01', '2026-03-31'),
    ('April 2026', '2026-04-01', '2026-04-30'),
    ('Mei 2026', '2026-05-01', '2026-05-31'),
    ('Juni 2026', '2026-06-01', '2026-06-30'),
    ('Juli 2026', '2026-07-01', '2026-07-31'),
    ('Agustus 2026', '2026-08-01', '2026-08-31'),
    ('September 2026', '2026-09-01', '2026-09-30'),
    ('Oktober 2026', '2026-10-01', '2026-10-31'),
    ('November 2026', '2026-11-01', '2026-11-30'),
    ('Desember 2026', '2026-12-01', '2026-12-31')
) AS months(month_name, start_date, end_date)
WHERE NOT EXISTS (
    SELECT 1 FROM portal_assessment_periods WHERE name = months.month_name
);

-- =====================================================
-- 5. Verification Queries
-- =====================================================

-- Check admin permissions
DO $$
DECLARE
    admin_count INTEGER;
    superadmin_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO admin_count FROM dashboard_users WHERE role = 'admin';
    SELECT COUNT(*) INTO superadmin_count FROM dashboard_users WHERE role = 'admin' AND admin_level = 'superadmin';
    
    RAISE NOTICE 'Total admins: %, Superadmins: %', admin_count, superadmin_count;
END $$;

-- Check periods
DO $$
DECLARE
    period_count INTEGER;
    active_period TEXT;
BEGIN
    SELECT COUNT(*) INTO period_count FROM portal_assessment_periods;
    SELECT name INTO active_period FROM portal_assessment_periods WHERE is_active = TRUE LIMIT 1;
    
    RAISE NOTICE 'Total periods: %, Active period: %', period_count, active_period;
END $$;

-- =====================================================
-- Migration Complete
-- =====================================================
