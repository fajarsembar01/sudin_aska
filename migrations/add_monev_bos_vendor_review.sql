ALTER TABLE monev_bos_vendors
    ADD COLUMN IF NOT EXISTS verification_checklist JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE monev_bos_vendors
    ADD COLUMN IF NOT EXISTS review_notes TEXT;
