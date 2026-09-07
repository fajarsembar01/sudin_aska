-- Mark whether a laporan form is required for its target audience.
-- Existing forms remain required to preserve the behavior before this option existed.
ALTER TABLE laporan_forms
ADD COLUMN IF NOT EXISTS is_mandatory BOOLEAN NOT NULL DEFAULT TRUE;
