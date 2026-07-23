-- Adiwiyata posts and public reactions.
-- Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS portal_adiwiyata_posts (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    media_path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    description TEXT,
    thumbnail_path TEXT,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE portal_adiwiyata_posts
ADD COLUMN IF NOT EXISTS thumbnail_path TEXT;

CREATE INDEX IF NOT EXISTS idx_adiwiyata_posts_school_category
ON portal_adiwiyata_posts (school_id, category);

CREATE INDEX IF NOT EXISTS idx_adiwiyata_posts_created_at
ON portal_adiwiyata_posts (created_at DESC);

CREATE TABLE IF NOT EXISTS adiwiyata_post_likes (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES portal_adiwiyata_posts(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('like', 'dislike')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (post_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_adiwiyata_post_likes_post_action
ON adiwiyata_post_likes (post_id, action);
