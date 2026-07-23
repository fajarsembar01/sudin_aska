-- Migration 038: Daily officer assignments for SPMB service desks

CREATE TABLE IF NOT EXISTS spmb_table_assignments (
    id SERIAL PRIMARY KEY,
    assignment_date DATE NOT NULL,
    table_number INTEGER NOT NULL CHECK (table_number BETWEEN 1 AND 12),
    officer_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    note TEXT,
    updated_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (assignment_date, table_number)
);

CREATE INDEX IF NOT EXISTS idx_spmb_table_assignments_date
ON spmb_table_assignments (assignment_date, table_number);

CREATE INDEX IF NOT EXISTS idx_spmb_table_assignments_officer
ON spmb_table_assignments (officer_user_id);
