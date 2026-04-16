CREATE TABLE IF NOT EXISTS cms_artikel (
    id SERIAL PRIMARY KEY,
    judul TEXT NOT NULL,
    kategori TEXT NOT NULL,
    tanggal_publikasi DATE NOT NULL,
    deskripsi TEXT NOT NULL,
    thumbnail_path TEXT,
    penulis TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Aktif',
    status_publikasi TEXT NOT NULL DEFAULT 'Draft',
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT cms_artikel_status_check CHECK (status IN ('Aktif', 'Tidak Aktif')),
    CONSTRAINT cms_artikel_status_publikasi_check CHECK (status_publikasi IN ('Draft', 'Published'))
);

CREATE INDEX IF NOT EXISTS idx_cms_artikel_tanggal_publikasi
ON cms_artikel (tanggal_publikasi DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cms_artikel_status_publikasi
ON cms_artikel (status_publikasi, status);

CREATE TABLE IF NOT EXISTS cms_artikel_files (
    id SERIAL PRIMARY KEY,
    artikel_id INTEGER NOT NULL REFERENCES cms_artikel(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cms_artikel_files_artikel_id
ON cms_artikel_files (artikel_id, created_at);
