-- Migration: User Registration & Verification System
-- Date: 2025-12-29

-- =====================================================
-- 1. Add Verification Columns to dashboard_users
-- =====================================================

ALTER TABLE dashboard_users
ADD COLUMN IF NOT EXISTS account_status VARCHAR(20) DEFAULT 'approved',
ADD COLUMN IF NOT EXISTS verification_notes TEXT,
ADD COLUMN IF NOT EXISTS verified_by INTEGER REFERENCES dashboard_users(id),
ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS requested_kecamatan INTEGER REFERENCES portal_kecamatan(id),
ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR(20);

-- Add comments
COMMENT ON COLUMN dashboard_users.account_status IS 'Account verification status: pending, approved, rejected, suspended';
COMMENT ON COLUMN dashboard_users.verification_notes IS 'Admin notes for approval/rejection decisions';
COMMENT ON COLUMN dashboard_users.verified_by IS 'Admin user who verified this account';
COMMENT ON COLUMN dashboard_users.verified_at IS 'Timestamp when account was verified';
COMMENT ON COLUMN dashboard_users.requested_kecamatan IS 'Kecamatan selected during registration';
COMMENT ON COLUMN dashboard_users.whatsapp_number IS 'WhatsApp number for notifications';

-- =====================================================
-- 2. Set Existing Users as Approved
-- =====================================================

-- All existing users are automatically approved
UPDATE dashboard_users
SET account_status = 'approved',
    verified_at = created_at
WHERE account_status IS NULL OR account_status = '';

-- =====================================================
-- 3. Create Indexes for Performance
-- =====================================================

-- Index for status lookups
CREATE INDEX IF NOT EXISTS idx_users_account_status 
ON dashboard_users(account_status) 
WHERE account_status IS NOT NULL;

-- Composite index for kecamatan-filtered status queries
CREATE INDEX IF NOT EXISTS idx_users_kecamatan_status 
ON dashboard_users(requested_kecamatan, account_status) 
WHERE requested_kecamatan IS NOT NULL AND account_status = 'pending';

-- =====================================================
-- 4. Verification
-- =====================================================

DO $$
DECLARE
    total_users INTEGER;
    approved_users INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_users FROM dashboard_users;
    SELECT COUNT(*) INTO approved_users FROM dashboard_users WHERE account_status = 'approved';
    
    RAISE NOTICE 'Total users: %, Approved: %', total_users, approved_users;
END $$;

-- =====================================================
-- Migration Complete
-- =====================================================
