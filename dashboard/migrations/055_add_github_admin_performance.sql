ALTER TABLE dashboard_users
ADD COLUMN IF NOT EXISTS github_username TEXT;

ALTER TABLE dashboard_users
ADD COLUMN IF NOT EXISTS github_author_email TEXT;

CREATE TABLE IF NOT EXISTS github_admin_commits (
    id BIGSERIAL PRIMARY KEY,
    repository TEXT NOT NULL,
    github_username TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL,
    commit_url TEXT,
    commit_message TEXT,
    additions INTEGER,
    deletions INTEGER,
    stats_synced_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repository, github_username, commit_sha)
);

CREATE INDEX IF NOT EXISTS idx_github_admin_commits_period
ON github_admin_commits (repository, github_username, committed_at DESC);

CREATE TABLE IF NOT EXISTS github_admin_sync_state (
    repository TEXT NOT NULL,
    github_username TEXT NOT NULL,
    author_email TEXT,
    last_synced_at TIMESTAMPTZ,
    last_error TEXT,
    synced_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    PRIMARY KEY (repository, github_username)
);

ALTER TABLE github_admin_sync_state
ADD COLUMN IF NOT EXISTS author_email TEXT;

ALTER TABLE github_admin_commits ADD COLUMN IF NOT EXISTS additions INTEGER;
ALTER TABLE github_admin_commits ADD COLUMN IF NOT EXISTS deletions INTEGER;
ALTER TABLE github_admin_commits ADD COLUMN IF NOT EXISTS stats_synced_at TIMESTAMPTZ;
