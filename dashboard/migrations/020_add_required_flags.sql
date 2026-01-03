-- Migration: add required flags to rooms and aspects
BEGIN;

ALTER TABLE portal_rooms
    ADD COLUMN IF NOT EXISTS is_required BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE portal_aspects
    ADD COLUMN IF NOT EXISTS is_required BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;
