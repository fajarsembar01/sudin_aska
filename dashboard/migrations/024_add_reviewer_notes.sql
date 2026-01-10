-- Migration: add reviewer notes for admin approvals

BEGIN;

ALTER TABLE IF EXISTS staff_assignment_requests
    ADD COLUMN IF NOT EXISTS reviewer_note TEXT;

ALTER TABLE IF EXISTS monev_team_member_requests
    ADD COLUMN IF NOT EXISTS reviewer_note TEXT;

COMMIT;
