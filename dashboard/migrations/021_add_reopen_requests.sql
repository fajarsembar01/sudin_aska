-- Create table for assessment reopen requests
CREATE TABLE IF NOT EXISTS portal_assessment_reopen_requests (
    id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES portal_assessments(id) ON DELETE CASCADE,
    staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, approved, rejected
    reviewer_id INTEGER REFERENCES dashboard_users(id),
    reviewer_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reopen_requests_assessment ON portal_assessment_reopen_requests(assessment_id);
CREATE INDEX IF NOT EXISTS idx_reopen_requests_status ON portal_assessment_reopen_requests(status);
