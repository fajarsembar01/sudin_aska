ALTER TABLE laporan_forms
    ADD COLUMN IF NOT EXISTS is_paused BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_laporan_forms_paused
    ON laporan_forms (is_paused, created_at DESC);
