-- Daily SPMB queue counter for public evaluation screen.

CREATE TABLE IF NOT EXISTS spmb_queue_counters (
    id SERIAL PRIMARY KEY,
    service_date DATE NOT NULL UNIQUE,
    current_number INTEGER NOT NULL DEFAULT 0 CHECK (current_number >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_spmb_queue_counters_date
ON spmb_queue_counters (service_date DESC);
