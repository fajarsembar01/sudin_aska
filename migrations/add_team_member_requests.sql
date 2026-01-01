-- Create table for team member join requests (submitted by coordinators)
CREATE TABLE IF NOT EXISTS monev_team_member_requests (
    id SERIAL PRIMARY KEY,
    team_id INT NOT NULL REFERENCES monev_teams(id) ON DELETE CASCADE,
    staff_id INT NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    requested_by INT NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    note TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending | approved | rejected
    reviewed_by INT REFERENCES dashboard_users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Prevent duplicate pending requests for the same staff & team
CREATE UNIQUE INDEX IF NOT EXISTS ux_monev_member_requests_pending
    ON monev_team_member_requests (team_id, staff_id)
    WHERE status = 'pending';
