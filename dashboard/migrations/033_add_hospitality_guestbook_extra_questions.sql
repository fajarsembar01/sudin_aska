-- Migration 033: Add extra questions for public hospitality review

CREATE TABLE IF NOT EXISTS hospitality_guestbook_extra_questions (
    id SERIAL PRIMARY KEY,
    question_text TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hosp_extra_questions_active_order
ON hospitality_guestbook_extra_questions (active, sort_order, id);

CREATE TABLE IF NOT EXISTS hospitality_guestbook_extra_answers (
    id SERIAL PRIMARY KEY,
    review_id INTEGER NOT NULL REFERENCES hospitality_guestbook_reviews(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES hospitality_guestbook_extra_questions(id) ON DELETE CASCADE,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (review_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_hosp_extra_answers_review
ON hospitality_guestbook_extra_answers (review_id);

CREATE INDEX IF NOT EXISTS idx_hosp_extra_answers_question
ON hospitality_guestbook_extra_answers (question_id);
