-- Pastikan kolom is_required ada
ALTER TABLE portal_rooms  ADD COLUMN IF NOT EXISTS is_required BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE portal_aspects ADD COLUMN IF NOT EXISTS is_required BOOLEAN NOT NULL DEFAULT FALSE;

-- Tambah master ruang PAUD, TK, Paket, dan SLB
INSERT INTO portal_rooms (name, description, category, sort_order, is_required)
VALUES
  ('Ruang Kelas PAUD', 'Kelas dasar PAUD', 'akademik', 50, TRUE),
  ('Ruang Kelas -1',   'Kelas dasar TK',   'akademik', 51, TRUE),
  ('Ruang Kelas Paket', 'Kelas dasar Paket', 'akademik', 52, TRUE),
  ('Ruang Kelas SLB', 'Kelas dasar SLB', 'akademik', 53, TRUE)
ON CONFLICT (name) DO NOTHING;

-- Aspek default untuk PAUD
INSERT INTO portal_aspects (room_id, name, sort_order, is_required)
SELECT r.id, a.name, a.sort_order, TRUE
FROM (VALUES
  ('Kebersihan',1),
  ('Keamanan',2),
  ('Kenyamanan',3),
  ('Ventilasi',4)
) AS a(name, sort_order)
JOIN portal_rooms r ON r.name = 'Ruang Kelas PAUD'
ON CONFLICT (room_id, name) DO NOTHING;

-- Aspek default untuk TK
INSERT INTO portal_aspects (room_id, name, sort_order, is_required)
SELECT r.id, a.name, a.sort_order, TRUE
FROM (VALUES
  ('Kebersihan',1),
  ('Keamanan',2),
  ('Kerapian',3),
  ('Pencahayaan',4)
) AS a(name, sort_order)
JOIN portal_rooms r ON r.name = 'Ruang Kelas -1'
ON CONFLICT (room_id, name) DO NOTHING;

-- Aspek default untuk Paket
INSERT INTO portal_aspects (room_id, name, sort_order, is_required)
SELECT r.id, a.name, a.sort_order, TRUE
FROM (VALUES
  ('Kebersihan',1),
  ('Keamanan',2),
  ('Ventilasi',3),
  ('Pencahayaan',4)
) AS a(name, sort_order)
JOIN portal_rooms r ON r.name = 'Ruang Kelas Paket'
ON CONFLICT (room_id, name) DO NOTHING;

-- Aspek default untuk SLB
INSERT INTO portal_aspects (room_id, name, sort_order, is_required)
SELECT r.id, a.name, a.sort_order, TRUE
FROM (VALUES
  ('Kebersihan',1),
  ('Keamanan',2),
  ('Ventilasi',3),
  ('Pencahayaan',4)
) AS a(name, sort_order)
JOIN portal_rooms r ON r.name = 'Ruang Kelas SLB'
ON CONFLICT (room_id, name) DO NOTHING;
