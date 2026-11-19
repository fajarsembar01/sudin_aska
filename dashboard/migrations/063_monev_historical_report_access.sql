-- Historical readers survive membership changes and team deletion. Editing still
-- uses the current assignment; these rows never grant write access.
CREATE TABLE IF NOT EXISTS monev_bos_report_readers (
    report_id INTEGER NOT NULL REFERENCES monev_bos_reports(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (report_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_monev_report_readers_user ON monev_bos_report_readers(user_id, report_id);

CREATE OR REPLACE FUNCTION capture_monev_report_readers(target_team INTEGER, target_report INTEGER)
RETURNS void LANGUAGE sql AS $$
    INSERT INTO monev_bos_report_readers(report_id, user_id)
    SELECT DISTINCT r.id, members.user_id
    FROM monev_bos_reports r
    JOIN monev_bos_assignments a ON a.school_id = r.school_id AND a.period_id = r.period_id
    JOIN (
        SELECT id AS team_id, leader_id AS user_id FROM monev_bos_teams WHERE leader_id IS NOT NULL
        UNION
        SELECT team_id, staff_id FROM monev_bos_team_members
    ) members ON members.team_id = a.team_id
    WHERE (target_team IS NULL OR a.team_id = target_team)
      AND (target_report IS NULL OR r.id = target_report)
    ON CONFLICT DO NOTHING;
$$;

CREATE OR REPLACE FUNCTION preserve_monev_report_readers()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'monev_bos_reports' THEN
        PERFORM capture_monev_report_readers(NULL, NEW.id);
    ELSIF TG_TABLE_NAME = 'monev_bos_teams' THEN
        IF TG_OP <> 'INSERT' THEN
            PERFORM capture_monev_report_readers(OLD.id, NULL);
        END IF;
        IF TG_WHEN = 'AFTER' THEN
            PERFORM capture_monev_report_readers(NEW.id, NULL);
        END IF;
    ELSE
        IF TG_OP <> 'INSERT' THEN
            PERFORM capture_monev_report_readers(OLD.team_id, NULL);
        END IF;
        IF TG_WHEN = 'AFTER' THEN
            PERFORM capture_monev_report_readers(NEW.team_id, NULL);
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS monev_readers_member_before ON monev_bos_team_members;
CREATE TRIGGER monev_readers_member_before BEFORE UPDATE OR DELETE ON monev_bos_team_members
FOR EACH ROW EXECUTE FUNCTION preserve_monev_report_readers();
DROP TRIGGER IF EXISTS monev_readers_member_after ON monev_bos_team_members;
CREATE TRIGGER monev_readers_member_after AFTER INSERT OR UPDATE ON monev_bos_team_members
FOR EACH ROW EXECUTE FUNCTION preserve_monev_report_readers();
DROP TRIGGER IF EXISTS monev_readers_team_before ON monev_bos_teams;
CREATE TRIGGER monev_readers_team_before BEFORE UPDATE OR DELETE ON monev_bos_teams
FOR EACH ROW EXECUTE FUNCTION preserve_monev_report_readers();
DROP TRIGGER IF EXISTS monev_readers_team_after ON monev_bos_teams;
CREATE TRIGGER monev_readers_team_after AFTER UPDATE ON monev_bos_teams
FOR EACH ROW EXECUTE FUNCTION preserve_monev_report_readers();
DROP TRIGGER IF EXISTS monev_readers_assignment_before ON monev_bos_assignments;
CREATE TRIGGER monev_readers_assignment_before BEFORE UPDATE OR DELETE ON monev_bos_assignments
FOR EACH ROW EXECUTE FUNCTION preserve_monev_report_readers();
DROP TRIGGER IF EXISTS monev_readers_assignment_after ON monev_bos_assignments;
CREATE TRIGGER monev_readers_assignment_after AFTER INSERT OR UPDATE ON monev_bos_assignments
FOR EACH ROW EXECUTE FUNCTION preserve_monev_report_readers();
DROP TRIGGER IF EXISTS monev_readers_report_after ON monev_bos_reports;
CREATE TRIGGER monev_readers_report_after AFTER INSERT OR UPDATE OF school_id, period_id ON monev_bos_reports
FOR EACH ROW EXECUTE FUNCTION preserve_monev_report_readers();

SELECT capture_monev_report_readers(NULL, NULL);
-- Recover evidenced historical participation where the team was changed before
-- this migration. Do not infer membership from the school's new team.
INSERT INTO monev_bos_report_readers(report_id, user_id)
SELECT report_id, user_id FROM monev_bos_audit_logs
UNION SELECT report_id, author_id FROM monev_bos_report_note_revisions WHERE author_id IS NOT NULL
ON CONFLICT DO NOTHING;
