-- Migration 037: Add configurable SPMB evaluation service types

CREATE TABLE IF NOT EXISTS spmb_service_types (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_spmb_service_types_active_order
ON spmb_service_types (active, sort_order, id);

INSERT INTO spmb_service_types (name, description, sort_order, active)
VALUES
    ('Informasi SPMB', 'Pertanyaan umum alur dan informasi SPMB.', 10, TRUE),
    ('Verifikasi Berkas', 'Pemeriksaan atau validasi berkas pendaftaran.', 20, TRUE),
    ('Bantuan Akun', 'Bantuan login, akun, atau akses aplikasi.', 30, TRUE),
    ('Perubahan Data', 'Bantuan koreksi atau penyesuaian data.', 40, TRUE),
    ('Pengaduan', 'Keluhan atau kendala selama layanan SPMB.', 50, TRUE),
    ('Lainnya', 'Jenis pelayanan lain di luar kategori utama.', 60, TRUE)
ON CONFLICT (name) DO NOTHING;
