ALTER TABLE hospitality_assessments
ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE hospitality_assessments
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

ALTER TABLE hospitality_assessments
ADD COLUMN IF NOT EXISTS deleted_by INTEGER REFERENCES dashboard_users(id);

CREATE INDEX IF NOT EXISTS idx_hosp_assessment_is_deleted
ON hospitality_assessments (is_deleted);

ALTER TABLE hospitality_guestbook_reviews
ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE hospitality_guestbook_reviews
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

ALTER TABLE hospitality_guestbook_reviews
ADD COLUMN IF NOT EXISTS deleted_by INTEGER REFERENCES dashboard_users(id);

CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_is_deleted
ON hospitality_guestbook_reviews (is_deleted);
