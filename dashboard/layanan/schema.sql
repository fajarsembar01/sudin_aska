CREATE TABLE IF NOT EXISTS layanan_records (
    id BIGSERIAL PRIMARY KEY,
    service_type TEXT NOT NULL CHECK (service_type IN ('ijazah', 'skpi', 'legalisasi', 'mutasi')),
    service_date DATE NOT NULL,
    student_name VARCHAR(200) NOT NULL,
    school_origin VARCHAR(250) NOT NULL,
    diploma_number VARCHAR(150),
    student_number VARCHAR(30),
    letter_code VARCHAR(100),
    letter_number VARCHAR(150),
    school_destination VARCHAR(250),
    transfer_direction TEXT CHECK (transfer_direction IN ('masuk', 'keluar')),
    grade VARCHAR(30),
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'dicatat' CHECK (status IN ('dicatat', 'diproses', 'selesai', 'diserahkan')),
    recipient_name VARCHAR(200),
    received_date DATE,
    created_by INTEGER NOT NULL REFERENCES dashboard_users(id),
    updated_by INTEGER NOT NULL REFERENCES dashboard_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1,
    CHECK (service_type <> 'mutasi' OR (school_destination IS NOT NULL AND transfer_direction IS NOT NULL AND grade IS NOT NULL)),
    CHECK (status <> 'diserahkan' OR (recipient_name IS NOT NULL AND received_date IS NOT NULL)),
    CHECK (received_date IS NULL OR received_date >= service_date)
);
CREATE INDEX IF NOT EXISTS layanan_records_date_idx ON layanan_records (service_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS layanan_records_type_status_idx ON layanan_records (service_type, status);
ALTER TABLE layanan_records ADD COLUMN IF NOT EXISTS school_origin_id INTEGER
    REFERENCES portal_schools(id) ON DELETE SET NULL;
ALTER TABLE layanan_records ADD COLUMN IF NOT EXISTS school_destination_id INTEGER
    REFERENCES portal_schools(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS layanan_access (
    user_id INTEGER PRIMARY KEY REFERENCES dashboard_users(id) ON DELETE CASCADE,
    granted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Keep the former mixed NIS/NISN field as history; do not guess its meaning.
ALTER TABLE layanan_records ADD COLUMN IF NOT EXISTS nisn VARCHAR(10);
CREATE INDEX IF NOT EXISTS layanan_records_nisn_idx
    ON layanan_records (nisn text_pattern_ops, updated_at DESC, id DESC);
