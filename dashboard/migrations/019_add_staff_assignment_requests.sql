-- Migration: add staff assignment request workflow
-- Creates table to track coordinator-submitted requests for assigning staff to schools.

BEGIN;

CREATE TABLE IF NOT EXISTS staff_assignment_requests (
    id SERIAL PRIMARY KEY,
    coordinator_id INT NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    staff_id INT NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    school_id INT NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    note TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending|approved|rejected
    reviewed_by INT REFERENCES dashboard_users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_staff_assignment_requests_status ON staff_assignment_requests(status);
CREATE INDEX IF NOT EXISTS idx_staff_assignment_requests_staff ON staff_assignment_requests(staff_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignment_requests_school ON staff_assignment_requests(school_id);

-- Unique pending request per coordinator/staff/school to avoid spam
CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_assignment_pending
ON staff_assignment_requests (coordinator_id, staff_id, school_id)
WHERE status = 'pending';

COMMIT;
