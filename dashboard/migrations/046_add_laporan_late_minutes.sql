-- Store exact late duration in minutes for laporan submissions.
ALTER TABLE laporan_forms
    ADD COLUMN IF NOT EXISTS very_late_after_minutes INTEGER NOT NULL DEFAULT 180;

ALTER TABLE laporan_forms
    ADD COLUMN IF NOT EXISTS no_submission_after_minutes INTEGER;

ALTER TABLE laporan_forms
    ADD COLUMN IF NOT EXISTS no_submission_jenjangs TEXT;

ALTER TABLE laporan_submissions
    ADD COLUMN IF NOT EXISTS late_minutes INTEGER DEFAULT 0;

UPDATE laporan_submissions
SET late_minutes = COALESCE(late_minutes, late_days * 1440, 0)
WHERE is_late = TRUE
  AND COALESCE(late_minutes, 0) = 0
  AND COALESCE(late_days, 0) > 0;
