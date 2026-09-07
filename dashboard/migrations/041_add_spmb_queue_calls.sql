-- Store SPMB queue calls selected by dashboard staff.

CREATE TABLE IF NOT EXISTS spmb_queue_calls (
    id SERIAL PRIMARY KEY,
    service_date DATE NOT NULL,
    queue_number INTEGER NOT NULL CHECK (queue_number > 0),
    table_number INTEGER NOT NULL CHECK (table_number BETWEEN 1 AND 12),
    status TEXT NOT NULL DEFAULT 'sedang_dilayani',
    officer_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    called_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (service_date, queue_number)
);

CREATE INDEX IF NOT EXISTS idx_spmb_queue_calls_date_status
ON spmb_queue_calls (service_date, status, queue_number);

CREATE INDEX IF NOT EXISTS idx_spmb_queue_calls_called
ON spmb_queue_calls (service_date, called_at DESC, id DESC);
