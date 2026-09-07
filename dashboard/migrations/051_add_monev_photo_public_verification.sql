ALTER TABLE monev_bos_school_posts
    ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS public_token VARCHAR(64),
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS photo_sha256 CHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS idx_monev_bos_school_posts_public_token
    ON monev_bos_school_posts (public_token)
    WHERE public_token IS NOT NULL;
