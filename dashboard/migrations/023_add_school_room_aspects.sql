-- Add table to track enabled aspects per school room.

BEGIN;

CREATE TABLE IF NOT EXISTS portal_school_room_aspects (
    school_room_id INTEGER NOT NULL REFERENCES portal_school_rooms(id) ON DELETE CASCADE,
    aspect_id INTEGER NOT NULL REFERENCES portal_aspects(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (school_room_id, aspect_id)
);

CREATE INDEX IF NOT EXISTS idx_psra_aspect ON portal_school_room_aspects (aspect_id);

COMMIT;
