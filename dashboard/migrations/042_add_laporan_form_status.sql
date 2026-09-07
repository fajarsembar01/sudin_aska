ALTER TABLE laporan_forms
ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'published';

DO $$
BEGIN
    ALTER TABLE laporan_forms
    ADD CONSTRAINT laporan_forms_status_check
    CHECK (status IN ('draft', 'published'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

UPDATE laporan_forms
SET status = 'published'
WHERE status IS NULL;

CREATE INDEX IF NOT EXISTS idx_laporan_forms_status
ON laporan_forms (status, created_at DESC);
