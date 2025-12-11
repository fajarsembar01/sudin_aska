-- Portal school + kelurahan/kecamatan import
-- Source file : DAFTAR SEKOLAH NEGERI & SWASTA DI JAKARTA UTARA II.xlsx
-- Generated   : 2025-12-11 09:51:27
-- Total       : 336 schools, 17 kelurahan, 3 kecamatan
-- Safe to re-run: uses ON CONFLICT upserts; existing rows are updated, missing rows stay untouched.

BEGIN;
-- Schema (idempotent)
CREATE TABLE IF NOT EXISTS portal_kecamatan (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portal_kelurahan (
    id SERIAL PRIMARY KEY,
    kecamatan_id INTEGER NOT NULL REFERENCES portal_kecamatan(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kecamatan_id, name)
);

CREATE TABLE IF NOT EXISTS portal_schools (
    id SERIAL PRIMARY KEY,
    npsn TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    jenjang TEXT NOT NULL DEFAULT 'SD',
    alamat TEXT,
    user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    metadata JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'NEGERI',
    kelurahan_id INTEGER REFERENCES portal_kelurahan(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_portal_kecamatan_name ON portal_kecamatan (name);
CREATE INDEX IF NOT EXISTS idx_portal_kelurahan_kecamatan ON portal_kelurahan (kecamatan_id);
CREATE INDEX IF NOT EXISTS idx_portal_schools_npsn ON portal_schools (npsn);

-- Kecamatan
INSERT INTO portal_kecamatan (name, code) VALUES ('CILINCING', 'CLC') ON CONFLICT (name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kecamatan (name, code) VALUES ('KOJA', 'KOJ') ON CONFLICT (name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kecamatan (name, code) VALUES ('KELAPA GADING', 'KPG') ON CONFLICT (name) DO UPDATE SET code = EXCLUDED.code;

-- Kelurahan (linked to kecamatan by name)
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Cilincing', NULL
FROM portal_kecamatan k
WHERE k.name = 'CILINCING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Kali Baru', NULL
FROM portal_kecamatan k
WHERE k.name = 'CILINCING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Kec. Cilincing', NULL
FROM portal_kecamatan k
WHERE k.name = 'CILINCING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Marunda', NULL
FROM portal_kecamatan k
WHERE k.name = 'CILINCING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Rorotan', NULL
FROM portal_kecamatan k
WHERE k.name = 'CILINCING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Semper Barat', NULL
FROM portal_kecamatan k
WHERE k.name = 'CILINCING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Semper Timur', NULL
FROM portal_kecamatan k
WHERE k.name = 'CILINCING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Suka Pura', NULL
FROM portal_kecamatan k
WHERE k.name = 'CILINCING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Koja', NULL
FROM portal_kecamatan k
WHERE k.name = 'KOJA'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Lagoa', NULL
FROM portal_kecamatan k
WHERE k.name = 'KOJA'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Rawabadak Selatan', NULL
FROM portal_kecamatan k
WHERE k.name = 'KOJA'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Rawabadak Utara', NULL
FROM portal_kecamatan k
WHERE k.name = 'KOJA'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Tugu Selatan', NULL
FROM portal_kecamatan k
WHERE k.name = 'KOJA'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Tugu Utara', NULL
FROM portal_kecamatan k
WHERE k.name = 'KOJA'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Kelapa Gading Barat', NULL
FROM portal_kecamatan k
WHERE k.name = 'KELAPA GADING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Kelapa Gading Timur', NULL
FROM portal_kecamatan k
WHERE k.name = 'KELAPA GADING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;
INSERT INTO portal_kelurahan (kecamatan_id, name, code)
SELECT k.id, 'Pegangsaan Dua', NULL
FROM portal_kecamatan k
WHERE k.name = 'KELAPA GADING'
ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;

-- Schools (linked via kelurahan -> kecamatan)
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706517', 'MIS MIFTAHUL JANNAH', 'MI', 'Jl. Baru Gg. II Dalam No. 26 RT. 05/01', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69963381', 'MIS TAHFIZH BAITUL HUDA', 'MI', 'Jl. Sungai Landak No.15A', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178194', 'MTSN 5 JAKARTA', 'MTS', 'Jl. Sungai Landak No.10', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '70042178', 'MTSS Tahfizh Baitul Huda', 'MTS', 'Jl. Sungai Landak No. 15A', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105076', 'SD ISLAM NURUL IKHLAS', 'SD', 'Jl. Baru Gg. II No. 1 Rt.002/02', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101028', 'SD NEGERI CILINCING 05 PG', 'SD', 'Jl. Baru Gg. II Rt.011/02 No.2', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104847', 'SD NEGERI CILINCING 08 PAGI', 'SD', 'Jl. Pedongkelan No. 2 Rt.001/06', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '70009509', 'SDIT AZIZAH', 'SD', 'Jl. Bhakti VI No. 41D RT 008 RW 006', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101010', 'SDN CILINCING 09', 'SD', 'Jl. Bakti Rt. 05 Rw. 06 No. 12', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104844', 'SDN Cilincing 01 Pg.', 'SD', 'Jl. Bhakti IX No.63', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104845', 'SDN Cilincing 02 Pg.', 'SD', 'Jl. Bhakti VI', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101026', 'SDN Cilincing 03', 'SD', 'Jl. Sungai Landak No.36', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104846', 'SDN Cilincing 07 Pg.', 'SD', 'Jl. Arteri Cakung Drain No. 1A', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104871', 'SDN Cilincing 10', 'SD', 'Kawasan Rusunawa Nagrak', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105011', 'SDS Kristen Damai', 'MA', 'Jl. Kelapa Dua No. 7 RT.014/03', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101093', 'SDS Mahaprajna', 'MA', 'Jl. Cilincing Lama No.3', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105075', 'SDS Nurul Huda', 'SD', 'Jl. Bakti IX No. 27', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100822', 'SMP Maha Prajna', 'MA', 'Jl. Cilincing Lama', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100759', 'SMP NEGERI 244 JAKARTA', 'SMP', 'Jl. Cilincing Bhakti VI No. 28', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100757', 'SMP NEGERI 266 JAKARTA', 'SMP', 'Jl. Cilincing Bakti Vi No. 29', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100763', 'SMP Negeri 143', 'SMP', 'Jl. Cilincing Bakti IX', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106682', 'SMP SYAHID 1', 'SMP', 'Jl. Bakti No. 27', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109325', 'SMP Syahid II', 'SMP', 'Jl. Baru Gg. II No.1', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69977354', 'MI BACHRUL ILMI AL-AMIN', 'MI', 'JL. KALIBARU TIMUR IVE', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706523', 'MIS AL BARKAH', 'MI', 'Jl. Kalibaru Timur RT 11/ 02', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69725309', 'MIS AL HUSNA', 'MI', 'Jl.Kalibaru Timur VII', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706521', 'MIS AL ITTIHADIYAH', 'MI', 'Jl. Kalibaru Barat VI No. 48 Rt. 012/015', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706522', 'MIS AL JIHAD', 'MI', 'Jl. Pelelangan RT 09/04', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69727486', 'MIS AL MAARIF', 'MI', 'Jl. Pelabuhan No. 17', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69725310', 'MIS AL MUBASYIRIN', 'MI', 'Jl. Kalibaru Barat IV No. 34 Rt. 008 Rw. 007', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706514', 'MIS ASH-SHIDDIQIN', 'MI', 'Kalibaru Barat IV RT. 002/007', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706513', 'MIS MIFTAHUL HIKMAH', 'MI', 'Jl. Kalibaru Barat VIII No. 2 RT. 006/05', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706520', 'MIS NURHIDAYAH', 'MI', 'Jl. Kalibaru Barat IV RT. 02/12 No. 3', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60730096', 'MIS TARBIYATUL ISLAMIYAH', 'MI', 'Jl. Kalibaru Barat VII No. 26 RT. 12/01', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60727337', 'MTSS AL MIFFTAHIYYAH', 'MTS', 'Jl. Kalibaru Barat Vii No.17 Rt. 01/04 Kel. Kalibaru', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178198', 'MTSS AL MUBASYIRIN', 'MTS', 'Jl. Kalibaru Barat Iv, No, 34, Rt.008. Rw.007', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105066', 'SD MUHAMMADIYAH 18', 'MA', 'Jl. Kalibaru Barat Vii Rt. 013/05 No. 9', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101003', 'SD Negeri Kalibaru 07 Pagi', 'SD', 'Jl. Kalibaru Barat IV No. 60', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104991', 'SDI BABURRIDHO', 'SD', 'Jl. Baru No. 52', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100997', 'SDN KALIBARU 03', 'SD', 'Jl. Kali Baru Timur III F No. 2', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101005', 'SDN KALIBARU 09', 'SD', 'Jl. Kali Baru Timur VII /5 Rt.15/01', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104848', 'SDN Kali Baru 01 Pg.', 'SD', 'Jl. Kalibaru Timur IV', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101001', 'SDN Kali Baru 05 Pagi', 'SD', 'Jl. Kalibaru Barat IV No.60 RT.003 RW.012', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104983', 'SDS Al-Islamiyah', 'MI', 'Jl. Kalibaru Timur III L', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105014', 'SDS DARUSSALAM', 'SD', 'Jl. Kali Baru Barat Rt. 05/10', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105017', 'SDS Dewi Sartika', 'SD', 'Jl. Manunggal VII No. 18', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105083', 'SDS Pantai Indah', 'SD', 'Jl. Kalibaru Timur', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106448', 'SMP AL-ISLAMIYAH', 'MI', 'Jl. Kalibaru Timur III Rt. 007 Rw. 03', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109495', 'SMP Baburridho', 'SMP', 'Jl. Baru No. 52', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106498', 'SMP DARUSSA ADAH', 'SMP', 'Jl. Kosambi I No. 1 RT.013 RW.002', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109250', 'SMP ISLAM AL HUSNA', 'SMP', 'Jl. Kalibaru Timur VII No. 31', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100749', 'SMP Negeri 53', 'SMP', 'Jl. Tanah Merdeka 33', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106688', 'SMP TERPADU MENARA CENDEKIA', 'SMP', 'Jl. Kalibaru Barat VI No. 48 Rt. 012/015', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kali Baru' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '70048009', 'MTSS Al-Anwariyah', 'MTS', 'Jalan Malaka I No. 6', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kec. Cilincing' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69975759', 'MI AL GIVARI', 'MI', 'JL.Pelopor', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706511', 'MIN 20 JAKARTA', 'MI', 'Jl. Marunda Baru No.25', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60729477', 'MIS EL NUR EL KASYSYAF IV', 'MI', 'Marunda Makmur Rt.007/01', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178195', 'MTSN 15 JAKARTA', 'MTS', 'Marunda Baru Iii No. 28', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69927699', 'MTsS El-NUR EL-KASYSYAF', 'MTS', 'Jl.marunda Makmur Rt 007/01', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104982', 'SD AL IKHWAN', 'SD', 'Jl. Karang Kendal No. 21 Rt. 008/05', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104873', 'SD NEGERI MARUNDA 03 PG', 'MA', 'Jl. Marunda Baru I No. 14', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20110224', 'SD ROBIATUL ADAWIYAH', 'SD', 'Jl. Sungai Tiram Rt. 01/06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109372', 'SDIT YUDHA PATRIA', 'SD', 'Jl. Marunda Baru III Rt.08/06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69980873', 'SDN MARUNDA 05', 'MA', 'Jl. Rumah Susun Marunda', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104872', 'SDN Marunda 02 Pg.', 'MA', 'Jl. Marunda Pulo', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104995', 'SDS Bambu Kuning', 'SD', 'Jl. S. Sirem', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105027', 'SDS Fadhilah', 'SD', 'Jl. Sungai Tiram Rt.09/02 No.25', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100766', 'SMP NEGERI 162 JAKARTA', 'SMP', 'Jl. Marunda Baru IV No. 1', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109320', 'SMP PGRI 7 Jakarta', 'SMP', 'Jl. Marunda Baru III', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69980874', 'SMPN 290', 'SMP', 'Jl. Rumah Susun Marunda', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Marunda' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '70010698', 'MI AL ANWARIYAH', 'MI', 'Jl. Malaka I RT.009/001 No.6', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706512', 'MIN 22 JAKARTA', 'MI', 'Jl. Tambun Rengas No. 49', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69725311', 'MIS AL HIKMAH', 'MI', 'Jl.Malaka Bulak RT.015/012 No.18 Kel.Rorotan', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706518', 'MIS AL WATHONIYAH 1', 'MI', 'Jl. Rorotan IX RT. 06/07 No. 26', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706525', 'MIS AL WATHONIYAH 14', 'MI', 'Jl. Rorotan II RT. 007/04', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706516', 'MIS AL WATHONIYAH 43', 'MI', 'Jl. Rorotan No. 1 RT. 01/10', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69994655', 'MIS AL-FATIMIYAH AN-NUR', 'MI', 'JL. ROROTAN 6 KP. MALAKA 2', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60730095', 'MIS ARRRUHANIYAH', 'MI', 'Sungai Kendal RT. 004/08 No. 64', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706519', 'MIS IMADUN NAJAH', 'MI', 'Malaka HB RT. 08/06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178196', 'MTSN 38 JAKARTA', 'MTS', 'Jl. Tambun Rengas No. 47 Rt. 001/007', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178197', 'MTSS AL HIKMAH', 'MTS', 'Jl. Malaka Bulak No. 18 Rt15/12', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60729658', 'MTSS AL ISHLAH', 'MTS', 'Malaka Iv No.27 Rt.013 Rw.006', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178199', 'MTSS AL WATHONIYAH 14', 'MTS', 'Rorotan 2 Rt.007/004 No.1', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178200', 'MTSS AL WATHONIYAH 43', 'MTS', 'Jl.rorotan 01/10', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69725386', 'MTSS IMADUN NAJAH', 'MTS', 'Jl. Malaka HB RT. 007/06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104840', 'SD ISLAM AL WATHONIYAH 43', 'SD', 'Jalan Rorotan I Nomor 10', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109315', 'SD KHUSUS DARUT TAUHID', 'SD', 'Kp. Bedeng Malaka Ii No. 85 Rt. 11/rw. 05', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100677', 'SDN ROROTAN 01', 'SD', 'Jl. Rorotan IX No. 1 Rt. 11 Rw. 10', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100679', 'SDN Rorotan 02 Pg.', 'SD', 'Jl. Rorotan IX No. 3 Rt.11/10 Kel. Rorotan Kec.Cilincing Jakarta Utara', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104907', 'SDN Rorotan 03', 'SD', 'Jl. Rorotan XI NO. 30', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109047', 'SDN Rorotan 07 Pg.', 'SD', 'Jl. Rorotan IV Malaka III HB Rt.006/006', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104839', 'SDS Kemala Bhayangkari I', 'MA', 'Jl. Rorotan XII', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106452', 'SMP AL WATHONIYAH 43', 'SMP', 'Jl. Raya Rorotan No.1 Rt. 01/10', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100769', 'SMP Negeri 200', 'SMP', 'Jl. Rorotan IX No. 2', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rorotan' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706524', 'MIS AL MUZAYYANAH', 'MI', 'Tipar Timur RT.006/004', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105045', 'SD KEBON BARU 1', 'SD', 'Blok X Gg. IV No. 25 Rt. 08/12', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100633', 'SD NEGERI SEMPER BARAT 07', 'SD', 'Jl. Pepaya V/20', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100686', 'SDN SEMPER BARAT 05', 'SD', 'Jl. F Kebon Baru Rt. 008/10', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100586', 'SDN SEMPER BARAT 13', 'SD', 'Jl. Pemadam Kebakaran', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100682', 'SDN Semper Barat 01', 'SD', 'Jl. Raya Tugu Semper No. 1', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100684', 'SDN Semper Barat 03 Pg.', 'SD', 'Jl. Kapuas Raya', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100582', 'SDN Semper Barat 09 Pagi', 'SD', 'Jl. F. No. 1 Kebon Baru', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100584', 'SDN Semper Barat 11 Pg.', 'SD', 'Jl. Kapuas Raya RT.016/001 Kel. Semper Barat Kec. Cilincing Jakarta Utara', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104911', 'SDN Semper Barat 15 Pg.', 'SD', 'Jl. S.Citandui Raya', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104975', 'SDS Advent IX Tg. Priok', 'SD', 'Jl. Kramat Jaya C-15', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105025', 'SDS Dua Harapan', 'SD', 'Jl. Tipar Timur', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105034', 'SDS Hang Tuah V', 'SD', 'Jl. Khatulistiwa No. 2 Komp. TNI AL Dewa Ruci', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109083', 'SDS Islam Darus Syifa', 'SD', 'Jl. S. Barito No. 45 Kp. Kurus', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105105', 'SDS STRADA TUNAS KELUARGA MULIA I', 'SD', 'Jl. Khatulistiwa No. 06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105118', 'SDS Tugu Bhakti', 'SD', 'Jl. Raya Tugu Semper', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105137', 'SDS Yaspi', 'SD', 'Jl. Dinas Kebersihan DKI', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109337', 'SMP Hang Tuah 1', 'SMP', 'Komplek TNI - AL Dewa Ruci, Jl. Angin Prahara No.11 2,', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109065', 'SMP Islam Darus Syifa', 'SMP', 'Jl. Sungai Barito No. 45 B Rt. 001/06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100773', 'SMP NEGERI 231 JAKARTA', 'SMP', 'Jl. Gereja Tugu', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20122006', 'SMP PLUS AL-FUDHOLA', 'SMP', 'Jakarta', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106651', 'SMP SARI PUTRA', 'SMP', 'Jl. Kebon Baru Blok X Gg. IV No. 25', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109340', 'SMP Tugu Bhakti', 'SMP', 'Jl. Raya Tugu No. 21', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106713', 'SMP Yaspi', 'SMP', 'Jl. Komp. Kebersihan DKI', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Barat' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69752288', 'MIS AT TAUFIQ', 'MI', 'Jl. Kebantenan I Rt. 007/07 No. 1', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105047', 'SD KAMPUNG SAWAH', 'SD', 'Semper Timur', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105044', 'SD KASIH IMMANUEL', 'MA', 'Kampung Sawah Blok B No.16', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69984785', 'SD KRISTEN HARAPAN BAGI BANGSA', 'SD', 'Jl. Kebantenan I No. 10 Rt. 002/005, Kel. Semper Timur, Kec. Cilincing, Kota Adm', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109629', 'SD Khusus Al-Rahmah', 'MA', 'Jl. Kampung Sawah Blok B', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104914', 'SD NEGERI SEMPER TIMUR 03', 'SD', 'Jl. Kebantenan IV No. 19', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100591', 'SD NEGERI SEMPER TIMUR 05 PG JAKARTA', 'SD', 'Jl. Kebantenan Iv No. 19', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104915', 'SD NEGERI SEMPER TIMUR 07', 'SD', 'Jl. Kebantenan IV No.35 RT. 012 RW. 06', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69952902', 'SD SALSABILA AL KAUTSAR', 'SD', 'Kampung Rawa Malang Rt006 Rw010', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69922219', 'SDI AL-AMINIYAH', 'MI', 'Jl. Kp Rawa Malang Rt.006 Rw.010 Semper Timur Cilincing Jakarta Utara', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104912', 'SDN Semper Timur 01', 'SD', 'Jl. Kebantenan IX No. 36 RT. 005 RW. 006', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69913134', 'SDS AZ-ZAHRAH', 'SD', 'JL. INSPEKSI CAKUNG DRAIN BLOK E KAMPUNG SAWAH', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105031', 'SDS Gaya Remaja', 'MA', 'Komp. Eks Gaya Motor', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105071', 'SDS Nurul Falah I', 'SD', 'Jl. Dewa Kembar Komp. TNI AL', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105072', 'SDS Nurul Falah II', 'SD', 'Jl. Dewa Kembar Komp. TNI AL', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105106', 'SDS STRADA TUNAS KELUARGA MULIA II', 'SD', 'Jl. Raya Cakung Cilincing No. 11', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109901', 'SMP AL RAHMAH', 'MA', 'Kp. Sawah Blok B Rt. 06/10', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69913135', 'SMP AZ-ZAHRAH', 'SMP', 'JL. INSPEKSI CAKUNG DRAIN BLOK E KP. SAWAH', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106470', 'SMP At-Taufiq', 'SMP', 'Jl. Kebantenan I No. 1', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106497', 'SMP DARUL MAARIF', 'MA', 'Jl. Madya Kebantenan No. 14', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109305', 'SMP KASIH IMMANUEL', 'MA', 'Jl. Kampung Sawah Blok B16 Rt. 06/10', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69985711', 'SMP KRISTEN HARAPAN BAGI BANGSA', 'SMP', 'Jl. Kebantenan I No. 10 Rt. 002 / Rw. 005', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106616', 'SMP Nurul Falah', 'SMP', 'Jl. Dewa Kembar Rt.010/01', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106656', 'SMP Strada St. Fransiskus Xaverius III', 'SMP', 'Jl. Raya Cakung Cilincing No.11', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Semper Timur' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69727484', 'MIS AL ARAF', 'MI', 'Jl. Raya Tipar Cakung No. 1 RT. 08/01', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706515', 'MIS AR RIDHA', 'MI', 'Jl Teluk Semangka No 103 RT 006 RW 010 Komp BPP Sukapura', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60729599', 'MIS NURUL AKHYAR', 'MI', 'Jl. Tipar Cakung No.50', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100596', 'SD NEGERI SUKAPURA 04 PG', 'SD', 'Jl. Tipar Cakung Gg. Bambu Kuning Rt.07/04', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104984', 'SDI Al-Irsyadiah', 'SD', 'Jl. Tipar Cakung Rt 008/01', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104994', 'SDIT Baiturrahman', 'MA', 'Jl. Masjid Baiturrahman', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104916', 'SDN SUKAPURA 02', 'SD', 'Jl. Kompi Jenggot No.28', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100593', 'SDN Sukapura 01', 'SD', 'Jl. Beo No.15 Komp.Walikota', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104917', 'SDN Sukapura 05 Pg.', 'SD', 'Jl. Tipar Cakung Rt. 007/ 04', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '70010608', 'SDS GLOBAL VILLAGE TRILINGUAL SCHOOL', 'SD', 'Imperial Gading Pelindo 2 Blok E1 No. 24 RT 009 RW 008', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109937', 'SDS Lilin Bangsa', 'SD', 'Jl. Raya Terusan Hibrida Gading Orchad Kelurahan Suka Pura', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105058', 'SDS MAMBA UL HIKMAH', 'MA', 'JL. TIPAR CAKUNG SUKAPURA NO 2', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106466', 'SMP ARRIDHA', 'SMP', 'Jl. Teluk Semangka 103', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109369', 'SMP Fatahillah Jaya', 'SMP', 'Tipar Cakung Gg Kompi Jenggot I No 21', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69956986', 'SMP LILIN BANGSA', 'SMP', 'Jl. Raya Terusan Hibrida, Gading Orchard', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106556', 'SMP Manbaul Hikmah', 'MA', 'Jl. Tipar No. 2', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69800097', 'SMP NEGERI 289 JAKARTA', 'SMP', 'JALAN TIPAR CAKUNG, SUKAPURA', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Suka Pura' AND k.name = 'CILINCING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69883487', 'SD JAKARTA TAIPEI SCHOOL', 'SD', 'Jl. Raya Kelapa Hybrida Blok QH', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109039', 'SD MAHATMA GADING', 'MA', 'Jl. Boulevard BGR Komplek Villa Gading Indah Blok D', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69889102', 'SD MAHATMA GADING INTERCULTURAL SCHOOL', 'MA', 'Jl. Boulevard BGR Komplek Villa Gading Indah Blok Q', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69856890', 'SD NORTH JAKARTA INTERCULTURAL SCHOOL', 'SD', 'JL. BOULEVARD BUKIT GADING RAYA', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105033', 'SD PLUS HANG TUAH 6', 'SD', 'Jl. Tabah Raya Komp. TNI AL', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69892595', 'SD SATORI MONTESSORI', 'SD', 'Apartemen Gading Mediterania Tower B unit CB/GF 11', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69830128', 'SDIT AL-BARKAH', 'SD', 'Jl. Teguh Raya No.3 Komplek TNI AL Kodamar', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104861', 'SDN Kelapa Gading Barat 01', 'SD', 'Jl. P. Tamiang I No. 45 Komplek TNI AL', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109346', 'SDS 6 BPK Penabur', 'SD', 'Jl. Hibrida Raya Blok QA 3', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104992', 'SDS HANG TUAH 8', 'SD', 'JL. PERINTIS KEMERDEKAAN KOMPLEK TNI AL', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109172', 'SDS Montessori Gading Permata', 'MA', 'Jl. Boulevard Artha Gading Kav.D No.10', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109521', 'SDS RAISING STARS INSTITUTE', 'SD', 'Jl. Casablanca IX, Bukit Gading Mediterania', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109312', 'SDS Universal', 'SD', 'Jl. Boulevard Barat Raya, Komp. Inkopal', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109938', 'SEKOLAH DASAR PENABUR INTERCULTURAL SCHOOL - PRIMARY KELAPA GADING', 'MA', 'Jl Bulevard Bukit Gading Raya Blok A5-A8', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106524', 'SMP HANG TUAH 3', 'SMP', 'Jl. Tangguh Raya Komplek TNI-AL', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106471', 'SMP HANG TUAH 5 JAKARTA', 'SMP', 'Jl.Perintis Kemerdekan Rt.005/ Rw.003 Kompl, TNI AL Kelapa Gading', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69883488', 'SMP JAKARTA TAIPEI SCHOOL', 'SMP', 'Jl. Raya Kelapa Hybrida Blok QH', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106551', 'SMP Kristen 4 Penabur', 'SMP', 'Jl. Hibrida Raya Blok QF-10', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100823', 'SMP MAHATMA GADING', 'MA', 'Jl. Boulevard BGR Komplek Villa Gading Indah Blok D', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69889103', 'SMP MAHATMA GADING INTERCULTURAL SCHOOL', 'MA', 'Jl. Boulevard BGR Komplek Villa Gading Indah Blok Q', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69856891', 'SMP NORTH JAKARTA INTERCULTURAL SCHOOL', 'SMP', 'JL. BOULEVARD BUKIT GADING RAYA', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109313', 'SMP UNIVERSAL', 'SMP', 'JL. BOULEVAR BARAT RAYA I', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69725680', 'Sekolah Menengah Pertama Intercultural School - Secondary Kelapa Gading', 'MA', 'Jalan Boulevard Bukit Gading Raya Blok A5-A8', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Barat' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69788312', 'MTsS AL-AQSHA', 'MTS', 'Jl. Sutra Ungu Blok D-6 No. 30-31', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Timur' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104863', 'SDN Kelapa Gading Timur 01', 'SD', 'Jl. Puskesmas No. 32 RT 006 RW 006', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Timur' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104865', 'SDN Kelapa Gading Timur 03', 'SD', 'Jl. Komplek PT. HI No.134', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Timur' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105120', 'SDS Tunas Gading', 'SD', 'Jl. Gading Putih Raya P2/ 23', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Timur' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105122', 'SDS Tunas Karya I', 'SD', 'Jalan Gading Putih IV', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Timur' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109382', 'SMP AL CHALIDIYAH', 'SMP', 'Jl. Perintis Kemerdekaan Komp Pt Hii Rt. 03/05', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Timur' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100760', 'SMP NEGERI 123 JAKARTA', 'SMP', 'Jl. Kelapa Gading I Komp. PT. HII', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Timur' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109350', 'SMP TUNAS KARYA', 'SMP', 'Jl. Pelepah Kuning III', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Timur' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106691', 'SMP Tunas Gading', 'SMP', 'Jl. Gading Putih Raya P2/23', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Kelapa Gading Timur' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706526', 'MIS NUR - ATTAQWA', 'MI', 'Jl. Pegangsaan Dua KM.4', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69725388', 'MTSS NUR ATTAQWA', 'MTS', 'Pegangsaan Dua Km 4 Rt 003/003', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69888567', 'SD BEACON ACADEMY', 'SD', 'JL. PEGANGSAAN DUA NO.66', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105060', 'SD MAWAR SARON', 'MA', 'Jl. Hibrida Timur', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109384', 'SD Marie Joseph', 'MA', 'JL. Puspa Gading I Blok H2 No. 2 Jakarta Utara', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69938151', 'SD RAFFLES CHRISTIAN SCHOOL KELAPA GADING', 'SD', 'Jl. Gading Pelangi Indah No. 1', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109528', 'SD SAINT PETER', 'SD', 'Jl. Boulevard Timur Raya No. 8, Kelapa Gading Permai', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69879019', 'SD SAINT PETER SCHOOL', 'SD', 'JL. RAYA BOULEVARD TIMUR NO. 8', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109397', 'SD Sekolah HighScope Indonesia Jakarta Kelapa Gading', 'SD', 'Jl. Pegangsaan Dua No. 22, Kelapa Gading, Jakarta Utara 14250', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105124', 'SD TUNAS KARYA II', 'SD', 'Jl. Gading Indah III, Kelapa Gading - Jakarta Utara', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105125', 'SD TUNAS KARYA III', 'SD', 'Jl. Kelapa Hibrida Vii Jakarta Utara', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104978', 'SDIT AL MU MIN', 'MI', 'Jl. Bangun Cipta Raya No.16A RT 06 RW 06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69964730', 'SDIT Al-Huda', 'SD', 'Jl. Musik Raya No. 2 Blok. Z Rt.003/009', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104886', 'SDN PEGANGSAAN DUA 07 PAGI', 'SD', 'Jl. Acordion', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104880', 'SDN Pegangsaan Dua 01', 'SD', 'Jl. Kepu. No.21 RT001 RW01', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104882', 'SDN Pegangsaan Dua 03', 'SD', 'Jl. Kepu No 21 Rt 001 Rw 01', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104884', 'SDN Pegangsaan Dua 05 Pg.', 'SD', 'Jl. Harpa I Pengangsaan Dua Kelapa Gading', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104885', 'SDN Pegangsaan Dua 06 Pg.', 'SD', 'Jl. Kompi Udin', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104977', 'SDS Al Azhar Kelapa Gading', 'SD', 'Jl. Raya Boulevard Timur Kelapa Gading', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105024', 'SDS Don Bosco I', 'SD', 'Jl. Raya Boulevard Timur', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105101', 'SDS Santo Yakobus', 'SD', 'Jl. Raya Pengangsaan Dua Km 3,5', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20121012', 'SDS Tunas Indonesia Sejati', 'SD', 'Jl. Raya Pegangsaan Dua No.97, Apartemen Gading Greenhill Lt.2 - 3', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105043', 'SDS. KASIH ANANDA I', 'SD', 'Jl. Raya Pegangsaan Dua No. 3', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69888568', 'SMP BEACON ACADEMY', 'SMP', 'JL. PEGANGSAAN DUA RAYA NO. 66', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100838', 'SMP Don Bosco I', 'SMP', 'Jl. Raya Timur Bulevar', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106454', 'SMP Islam Al-Azhar Kelapa Gading', 'SMP', 'Jl. Boulevar Timur', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69934013', 'SMP JAC', 'SMP', 'Jl. Pegangsaan Dua No. 75A', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106544', 'SMP KASIH ANANDA I', 'SMP', 'Jl. Pegangsaan Dua Raya No. 3', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109255', 'SMP Marie Joseph', 'MA', 'Jl. Puspa Gading I Blok H2 No. 4-6', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100742', 'SMP NEGERI 270 JAKARTA', 'SMP', 'Jl. Kompi Udin', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100767', 'SMP Negeri 170', 'SMP', 'Jl. Kepu Pegangsaan Dua No. 17', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69939306', 'SMP Raffles Christian School Kelapa Gading', 'SMP', 'Jalan Gading Pelangi 1, Kelurahan Pegangsaan Dua, Kecamatan Kelapa Gading, Kota', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109066', 'SMP SAINT PETER', 'SMP', 'Jl. Boulevard Timur Raya No. 8, Kelapa Gading Permai', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69879020', 'SMP SAINT PETER SCHOOL', 'SMP', 'JL. BOULEVARD TIMUR RAYA NO. 8', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109271', 'SMP Santo Yakobus', 'SMP', 'Jl. Pegangsaan Dua KM 3.5', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178279', 'SMP Sekolah HighScope Indonesia Jakarta Kelapa Gading', 'SMP', 'Jl. Pegangsaan Dua No. 22, Kelapa Gading, Jakarta Utara 14250', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Pegangsaan Dua' AND k.name = 'KELAPA GADING'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706530', 'MIS AR RASYIDIYYAH', 'MI', 'Jl. Mualim Rasyid Kp. Mangga No.34', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Koja' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60727338', 'MTSS PERSIS 12', 'MTS', 'Jl. Yos Sudarso Lorong 103/56', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Koja' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105110', 'SD STRADA ST FRANSISKUS XAVERIUS', 'SD', 'Jl. Deli No. 20', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Koja' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105003', 'SDS Bina Pusaka', 'SD', 'Jl. Yos Sudarso Lorong 100 Timur No.70', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Koja' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105087', 'SDS Persis', 'SD', 'Jl. Yos Sudarso Lorong 103 No.56', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Koja' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105112', 'SDS Suraya', 'SD', 'Jl. Yos Sudarso Lorong 100', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Koja' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105134', 'SDS Yapis', 'SD', 'Jl. Deli Gg. 28 No. 12', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Koja' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106674', 'SMP Strada Santo FX-I', 'SMP', 'Jl. Deli No. 20', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Koja' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706529', 'MIS AL IKHWAN', 'MI', 'Jl. Cemara, Blok B No.27', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706532', 'MIS AL KHAIRIYAH PAGI', 'MI', 'MINDI NO. 2', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69727098', 'MIS AR RAUDHAH', 'MI', 'Jl. Cemara Gg,2 Blok I No.79 Rt.004 Rw.016', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706534', 'MIS ILHAM 1', 'MI', 'Jl. Muncang blok K No.131 Rt.002 Rw.013', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178201', 'MTSS AL KHAIRIYAH KOJA', 'MTS', 'Mindi No.2', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100884', 'SD ISLAM AL IKHLAS', 'SD', 'Jl. Lagoa Terusan Gg IV DI No. 26', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105064', 'SD MUHAMMADIYAH 22', 'MA', 'Jl. Mundu Luar No. 1', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101061', 'SD NEGERI LAGOA 09 PG JAKARTA', 'SD', 'Jl. LAGOA TERUSAN IV D 1 Rt. 017/03', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104985', 'SDI AL KHAIRIYAH', 'SD', 'Jl. Mindi No. 2', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101062', 'SDN LAGOA 11', 'SD', 'JL. LAGOA TERUSAN GG. IV D.1 NO.1 RT.17/03', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104869', 'SDN Lagoa 01 Pg.', 'SD', 'Jl. Menteng No. 2-4 Jakarta Utara', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101054', 'SDN Lagoa 02 Pg.', 'SD', 'Jl. Menteng No. 2-4', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101057', 'SDN Lagoa 05 Pg.', 'SD', 'Jl. Menteng No. 2-4', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20101059', 'SDN Lagoa 07 Pg.', 'SD', 'Jl. Pramuka Gg. IV No. 15', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105054', 'SDS LAGOA (YPUL)', 'SD', 'JL. LAGOA Gg. III NO.1-3-5', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109343', 'SDS TUNAS KELUARGA MULIA', 'SD', 'Jl. Kramat Jaya Ib', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105133', 'SDS Yapensori', 'SD', 'Jl. Maja No. 53 A', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100788', 'SMP AR RAUDHAH', 'SMP', 'Jl. Cemara Blok I No. 79', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106458', 'SMP Al-Irsyad Al-Islamiyyah', 'MI', 'Jl. Mindi Raya No. 29-35', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106461', 'SMP Al-Khairiyah I', 'SMP', 'Jl. Mindi No. 2 RT 014/008', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106462', 'SMP Al-Khairiyah II', 'SMP', 'Jl. Mindi Raya No. 2', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106547', 'SMP KELUARGA KUSUMA MARSUDIRINI', 'MA', 'Jl. Kramat Jaya Ib', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106552', 'SMP LAGOA', 'SMP', 'Jl. Lagoa III No.135', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100744', 'SMP NEGERI 279 JAKARTA', 'SMP', 'Jl. Mahoni No. 44', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100752', 'SMP Negeri 84', 'SMP', 'Jl. Semangka No 1', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106684', 'SMP TANJUNG PRIOK', 'SMP', 'Jl. Mangga No. 40 Rt.009 / Rw.009', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106704', 'SMP YAMIFSA', 'MI', 'Jl. Maja No. 40', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106709', 'SMP Yapensori', 'SMP', 'Jl. Maja No. 53 A', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Lagoa' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706527', 'MIN 5 JAKARTA', 'MI', 'Kp.Bend.Melayu RT.003/01 No.100', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '70009512', 'MIS TAHFIDZ AL MARJAN', 'MI', 'JL. SAMUDRA NO.10 RT 004/06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178202', 'MTSS AL MUHAJIRIN KJ', 'MTS', 'Jl. Tunda No. 20-21 Rt. 001/007', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69949704', 'SD ISLAM MAFAZA', 'MA', 'JL. SAMUDERA NO. 221 RT 05 RW 06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100647', 'SD NEGERI RAWA BADAK SELATAN 03 PG JAKARTA', 'SD', 'Jl. Kemudi Komplek Pelindo 2', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100648', 'SD NEGERI RAWA BADAK SELATAN 05', 'SD', 'Jl. Alur Laut Gg. Pattimura No. 45', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100690', 'SD NEGERI RAWA BADAK SELATAN 09 PG JAKARTA', 'SD', 'Jl. Mundari No.15 Rt 002 Rw 001', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100691', 'SD NEGERI RAWA BADAK SELATAN 11 PG JAKARTA', 'SD', 'Jl. Bendungan Melayu Rt. 04/01', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105113', 'SD TABITA', 'SD', 'Jl. Bandar II No. 28', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109525', 'SDIT AL MUHAJIRIN', 'SD', 'Jl. Tunda No. 20-21', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69988491', 'SDIT GEMA INSAN MANDIRI', 'MA', 'Jl. Samudra No.6&8 Rt.004 Rw.006', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100645', 'SDN Rawa Badak Selatan 01 Pg.', 'SD', 'Jl. Kemudi No. 1 K. Perumtel', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100669', 'SDN Rawa Badak Selatan 07', 'SD', 'Jl. Mundari No.51', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105131', 'SDS Wening', 'SD', 'Jl. Mesjid Rt.007/03 No. 47', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69990141', 'SMP ISLAM MAFAZA', 'MA', 'JL. BANDAR II NO.42 RT/RW 06/06', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100764', 'SMP NEGERI 151 JAKARTA', 'SMP', 'Jl. Kepil No. 1', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178205', 'MTSS AL HIDAYAH RBU', 'MTS', 'Jl. B N0.1', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104974', 'SD ADVENT ANGGREK', 'SD', 'Jl. Anggrek No. 17', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100699', 'SD NEGERI RAWA BADAK UTARA 07', 'SD', 'Jl. Rawa Binangun III/17A', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100702', 'SD NEGERI RAWA BADAK UTARA 11', 'SD', 'JL. RAWA BADAK BARAT NO. 37', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100693', 'SD Standar Nasional Rawa Badak Utara 01 Pg.', 'SD', 'Jl. Sunter II No. 35', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100697', 'SDN RAWA BADAK UTARA 05 PAGI', 'SD', 'Jl. Rawa Binangun V No.36A Rt.008/08', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100695', 'SDN Rawa Badak Utara 03 Pg.', 'SD', 'Jl. Alur Laut No.37', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100689', 'SDN Rawa Badak Utara 15 Pg.', 'SD', 'Jl. Rawa Badak Barat. No. 37', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100671', 'SDN Rawa Badak Utara 19 Pg.', 'SD', 'Jl. Rawa Badak Barat No. 36', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100673', 'SDN Rawa Badak Utara 21', 'SD', 'Jl. F. Gg. L. Rt.01/05 No.35', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104906', 'SDN Rawa Badak Utara 23 Pg.', 'SD', 'Jl. F. Gg. L. Rt.02/02 No.33', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104976', 'SDS Aisyiyah', 'SD', 'Jl. Seroja No. 2', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105001', 'SDS Barunawati IV', 'SD', 'Jl. Anjungan No. 14 RT 001 RW 01', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106447', 'SMP Advent Anggrek', 'SMP', 'Jl. Anggrek No. 17', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106474', 'SMP BARUNAWATI 3', 'SMP', 'Jl. Anjungan No. 14-16 Komp. Bpp Walang Kel. Rawabadak Utara', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100768', 'SMP NEGERI 173 JAKARTA', 'SMP', 'Jl. Alur Laut No. 57', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100743', 'SMP NEGERI 277 JAKARTA', 'SMP', 'Jl. Sindang Terusan No. 34 A', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100746', 'SMP Negeri 30', 'SMP', 'Jl. Anggrek No. 4 Koja', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Rawabadak Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100852', 'MTS AR RASYIDIYYAH', 'MTS', 'Jl. Mu alim Rasyid Kp. Mangga No. 34', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109251', 'SD JAC', 'SD', 'Jl. Pegangsaan Dua No 21', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105073', 'SD NURUL FARHAH', 'SD', 'Jl. Raya Logistik Kp. Batu Tumbuh No. 65', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100568', 'SDN Tugu Selatan 01 Pg', 'SD', 'Jl. Balai Rakyat No. 17', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100565', 'SDN Tugu Selatan 03 Pg.', 'SD', 'Jl. Balai Rakyat No. 19', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106514', 'SMP FIKRI', 'SMP', 'Jl. Masjid Al-anfal No. 51', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20112417', 'SMP IT ASH-SHIDDIQ', 'SMP', 'Jl. Bendungan Melayu Utara Rt. 11/01', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100740', 'SMP NEGERI 121 JAKARTA', 'SMP', 'Jl.Plumpang Semper No.20', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106716', 'SMP NEGERI 136 JAKARTA', 'SMP', 'Jl. Bendungan Melayu No. 80', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Selatan' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706528', 'MIS AL HIDAYAH', 'MI', 'Kramat Jaya Komplek UKA No.17 RT.02 RW 08', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706531', 'MIS ASH SHIDDIQQIYAH', 'MI', 'Mawar IV No.15 Rt.012 Rw.006', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '60706533', 'MIS RAUDLATUL MUTTAQIEN', 'MI', 'Jl. Mangga No.12-14', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178206', 'MTSS AL HIDAYAH UKA', 'MTS', 'Al Hidayah Komplek Uka Rt 02 Rw 08 No.17', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178203', 'MTSS ASH SHIDIQIYAH', 'MTS', 'Mawar Iv No 15', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20178204', 'MTSS RAUDHATUL MUTTAQIN', 'MTS', 'Jl. Mangga Lontar Ii No.12-14', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '69963071', 'SD IT HARUM', 'SD', 'JL. WALANG BARU 5 BLOK C 1-2', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104954', 'SD NEGERI TUGU UTARA 03 PG JAKARTA', 'SD', 'Jl. Mangga Ujung No. 3', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104956', 'SD NEGERI TUGU UTARA 05', 'SD', 'Jl. Mangga Ujung No. 2-3', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100577', 'SD NEGERI TUGU UTARA 11', 'SD', 'Jl. Komplek Uka', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105108', 'SD STRADA ST IGNATIUS', 'SD', 'Jl. Bhayangkara No. 38', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104952', 'SDN TUGU UTARA 01 PAGI', 'SD', 'Jl. Mangga Ujung No.1- 3', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100575', 'SDN TUGU UTARA 09.', 'SD', 'Jl.Mahoni Ujung Komp.UKA', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100618', 'SDN TUGU UTARA 14 PAGI', 'SD', 'Jl. Kramat Jaya Gg.VIII Blok R No. 43', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100625', 'SDN TUGU UTARA 22', 'SD', 'Jl. Kramat Jaya Komplek Deperla', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104958', 'SDN Tugu Utara 07 Pg.', 'SD', 'Jl. Turi No. 3', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100598', 'SDN Tugu Utara 13 Pg.', 'SD', 'Jl. Keramat Jaya Gg.VIII Blok R', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100619', 'SDN Tugu Utara 15 Pg.', 'SD', 'Jl. H. M. Darpi Plump. Semper', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20104963', 'SDN Tugu Utara 17 Pg.', 'SD', 'Jl. Kramat Jaya Gg.VIII Blok R', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100622', 'SDN Tugu Utara 19 Pg.', 'SD', 'Jl. Kramat Jaya Gg.VIII Blok R', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100624', 'SDN Tugu Utara 21 Pg.', 'SD', 'Jl. Kr. Jaya Gg.VIII Blok R', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105128', 'SDS UNWANUS SAADAH', 'SD', 'Jl. Plumpang Semper', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20105129', 'SDS Uswatun Hasanah Pg', 'SD', 'Jl. Mawar Luar No. 1', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100825', 'SMP Muhammadiyah 14', 'MA', 'Jl. H. Murtadho No. 2A', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20100719', 'SMP Negeri 114', 'SMP', 'Jl. H.M Darpi No. 2 Rt. 001 Rw. 13 Plumpang Semper', l.id, 'NEGERI', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20109401', 'SMP Nusantara', 'SMP', 'Jl. Kramat Jaya Gg. VIII', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106653', 'SMP Sejahtera', 'SMP', 'Jl. Walang Baru VI No. 19', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106675', 'SMP Strada FX. II', 'SMP', 'Jl. Bhayangkara No.38', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106693', 'SMP Unwanus Saadah', 'SMP', 'Jl. Plumpang Semper No. 3', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)
SELECT '20106715', 'SMP YUSHA', 'SMP', 'Mawar Luar No. 1', l.id, 'SWASTA', TRUE, NOW()
FROM portal_kelurahan l
JOIN portal_kecamatan k ON k.id = l.kecamatan_id
WHERE l.name = 'Tugu Utara' AND k.name = 'KOJA'
ON CONFLICT (npsn) DO UPDATE SET
  name = EXCLUDED.name,
  jenjang = EXCLUDED.jenjang,
  alamat = EXCLUDED.alamat,
  kelurahan_id = EXCLUDED.kelurahan_id,
  status = EXCLUDED.status,
  updated_at = NOW();
COMMIT;
