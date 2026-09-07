-- Migration 039: Store public SPMB service evaluations in database

CREATE TABLE IF NOT EXISTS spmb_evaluations (
    id SERIAL PRIMARY KEY,
    service_type TEXT NOT NULL,
    table_number INTEGER NOT NULL CHECK (table_number BETWEEN 1 AND 12),
    indicator TEXT NOT NULL CHECK (indicator IN ('baik', 'sedang', 'buruk')),
    note TEXT,
    client_ip TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_spmb_evaluations_created
ON spmb_evaluations (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_spmb_evaluations_indicator
ON spmb_evaluations (indicator);

CREATE INDEX IF NOT EXISTS idx_spmb_evaluations_table_created
ON spmb_evaluations (table_number, created_at DESC);
