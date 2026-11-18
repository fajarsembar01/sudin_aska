CREATE TABLE IF NOT EXISTS monev_bos_report_notes (
    report_id INTEGER PRIMARY KEY REFERENCES monev_bos_reports(id) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 0,
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS monev_bos_report_note_revisions (
    report_id INTEGER NOT NULL REFERENCES monev_bos_reports(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    changes JSONB NOT NULL,
    author_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    author_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (report_id, version)
);
