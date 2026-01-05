-- Migration: add optional period to staff assignment requests
-- Adds a nullable period_id that references portal_assessment_periods,
-- backfills with the active period when available, and updates the unique
-- pending index to include the period.

BEGIN;

ALTER TABLE staff_assignment_requests
    ADD COLUMN IF NOT EXISTS period_id INTEGER REFERENCES portal_assessment_periods(id) ON DELETE SET NULL;

-- Backfill existing pending requests with the current active period (if any)
UPDATE staff_assignment_requests sar
SET period_id = p.id
FROM portal_assessment_periods p
WHERE p.is_active = TRUE
  AND sar.period_id IS NULL;

-- Refresh unique index so requests can be unique per period
DROP INDEX IF EXISTS uq_staff_assignment_pending;
CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_assignment_pending
ON staff_assignment_requests (coordinator_id, staff_id, school_id, period_id)
WHERE status = 'pending';

COMMIT;
