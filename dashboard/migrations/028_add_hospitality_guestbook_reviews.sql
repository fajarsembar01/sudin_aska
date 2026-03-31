-- Review pelayanan buku tamu umum untuk flow QR ASKA

CREATE TABLE IF NOT EXISTS hospitality_guestbook_reviews (
    id SERIAL PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES daftar_tamu_general_transactions(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    review_token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    rating SMALLINT,
    comment TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT hospitality_guestbook_reviews_rating_check CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hosp_guestbook_reviews_transaction
    ON hospitality_guestbook_reviews (transaction_id);

CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_school
    ON hospitality_guestbook_reviews (school_id);

CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_status
    ON hospitality_guestbook_reviews (status);

CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_completed_at
    ON hospitality_guestbook_reviews (completed_at DESC);
