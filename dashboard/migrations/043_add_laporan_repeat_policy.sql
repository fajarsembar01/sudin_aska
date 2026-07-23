ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS repeat_policy TEXT NOT NULL DEFAULT 'once';
ALTER TABLE laporan_forms ADD COLUMN IF NOT EXISTS repeat_until_at TIMESTAMPTZ;

DO $$
BEGIN
    ALTER TABLE laporan_forms
    ADD CONSTRAINT laporan_forms_repeat_policy_check
    CHECK (repeat_policy IN ('once', 'multiple', 'daily', 'weekly', 'monthly'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

UPDATE laporan_forms
SET repeat_policy = CASE WHEN allow_multiple THEN 'multiple' ELSE 'once' END
WHERE repeat_policy IS NULL OR (repeat_policy = 'once' AND allow_multiple = TRUE);

ALTER TABLE laporan_submissions ADD COLUMN IF NOT EXISTS repeat_period_key TEXT;
ALTER TABLE laporan_submissions ADD COLUMN IF NOT EXISTS repeat_period_label TEXT;

CREATE INDEX IF NOT EXISTS idx_laporan_forms_repeat_policy
    ON laporan_forms (repeat_policy, repeat_until_at);

CREATE INDEX IF NOT EXISTS idx_laporan_submissions_period
    ON laporan_submissions (form_id, school_id, repeat_period_key);

CREATE UNIQUE INDEX IF NOT EXISTS ux_laporan_submissions_period
    ON laporan_submissions (form_id, school_id, repeat_period_key)
    WHERE status = 'submitted' AND repeat_period_key IS NOT NULL;
