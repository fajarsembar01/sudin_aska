-- Migration: make classroom rooms and aspects optional by default
BEGIN;

UPDATE portal_rooms
SET is_required = FALSE
WHERE name ILIKE 'Ruang Kelas%';

UPDATE portal_aspects a
SET is_required = FALSE
FROM portal_rooms r
WHERE a.room_id = r.id
  AND r.name ILIKE 'Ruang Kelas%';

COMMIT;
