-- Hospitality module schema

CREATE TABLE IF NOT EXISTS hospitality_components (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    sort_order INT NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_hosp_components_name ON hospitality_components (LOWER(name));

CREATE TABLE IF NOT EXISTS hospitality_aspects (
    id SERIAL PRIMARY KEY,
    component_id INTEGER NOT NULL REFERENCES hospitality_components(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    sort_order INT NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hosp_aspects_component ON hospitality_aspects(component_id);

CREATE TABLE IF NOT EXISTS hospitality_assessments (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
    staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'draft', -- draft, submitted, verified, reopened
    score_scale_max SMALLINT NOT NULL DEFAULT 5,
    note_text TEXT,
    submitted_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    reopened_at TIMESTAMPTZ,
    reopened_by INTEGER REFERENCES dashboard_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 1x per day per staff-school
CREATE UNIQUE INDEX IF NOT EXISTS uq_hosp_assessment_daily
    ON hospitality_assessments (school_id, staff_id, ((created_at AT TIME ZONE 'Asia/Jakarta')::date));

CREATE INDEX IF NOT EXISTS idx_hosp_assessment_status ON hospitality_assessments(status);
CREATE INDEX IF NOT EXISTS idx_hosp_assessment_school ON hospitality_assessments(school_id);
CREATE INDEX IF NOT EXISTS idx_hosp_assessment_staff ON hospitality_assessments(staff_id);

CREATE TABLE IF NOT EXISTS hospitality_assessment_scores (
    assessment_id INTEGER NOT NULL REFERENCES hospitality_assessments(id) ON DELETE CASCADE,
    component_id INTEGER NOT NULL REFERENCES hospitality_components(id) ON DELETE CASCADE,
    aspect_id INTEGER NOT NULL REFERENCES hospitality_aspects(id) ON DELETE CASCADE,
    score SMALLINT NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (assessment_id, aspect_id)
);

CREATE INDEX IF NOT EXISTS idx_hosp_scores_component ON hospitality_assessment_scores(component_id);

CREATE TABLE IF NOT EXISTS hospitality_assessment_guestbook_links (
    assessment_id INTEGER PRIMARY KEY REFERENCES hospitality_assessments(id) ON DELETE CASCADE,
    transaction_id INTEGER NOT NULL REFERENCES daftar_tamu_transactions(id) ON DELETE RESTRICT,
    linked_by INTEGER REFERENCES dashboard_users(id),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hosp_guestbook_transaction ON hospitality_assessment_guestbook_links(transaction_id);

CREATE TABLE IF NOT EXISTS hospitality_assessment_comments (
    id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES hospitality_assessments(id) ON DELETE CASCADE,
    author_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    author_role VARCHAR(20),
    message TEXT NOT NULL,
    parent_comment_id INTEGER REFERENCES hospitality_assessment_comments(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hosp_comments_assessment ON hospitality_assessment_comments(assessment_id);
CREATE INDEX IF NOT EXISTS idx_hosp_comments_parent ON hospitality_assessment_comments(parent_comment_id);

-- Reopen requests mirip PANBERSS
CREATE TABLE IF NOT EXISTS hospitality_reopen_requests (
    id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES hospitality_assessments(id) ON DELETE CASCADE,
    staff_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
    reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, approved, rejected
    reviewer_id INTEGER REFERENCES dashboard_users(id),
    reviewer_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_hosp_reopen_assessment ON hospitality_reopen_requests(assessment_id);
CREATE INDEX IF NOT EXISTS idx_hosp_reopen_status ON hospitality_reopen_requests(status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_hosp_reopen_pending ON hospitality_reopen_requests(assessment_id) WHERE status = 'pending';
