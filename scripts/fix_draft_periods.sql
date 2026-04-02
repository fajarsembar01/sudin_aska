-- =============================================================
-- FIX: Pulihkan draft yang period-nya berubah karena _sync_assessment_period_to_active
-- Jalankan di DB production
-- =============================================================

-- =====================
-- STEP 1: DIAGNOSTIC - Lihat draft yang terkena bug
-- Draft yang dibuat di bulan lalu tapi period_id-nya sudah berubah ke bulan ini
-- =====================

-- Cek periode aktif saat ini
SELECT id, name, start_date, end_date, is_active 
FROM portal_assessment_periods 
WHERE is_active = TRUE;

-- Lihat semua draft yang kemungkinan terkena sync
-- (dibuat sebelum periode aktif dimulai, tapi period_id = periode aktif)
SELECT 
    a.id AS assessment_id,
    a.status,
    a.period_id,
    p.name AS current_period_name,
    a.created_at,
    a.updated_at,
    s.name AS school_name,
    s.npsn,
    u.email,
    u.full_name,
    -- Periode yang seharusnya berdasarkan tanggal pembuatan
    correct_p.id AS correct_period_id,
    correct_p.name AS correct_period_name,
    (SELECT COUNT(*) FROM portal_assessment_scores WHERE assessment_id = a.id) AS score_count,
    (SELECT COUNT(*) FROM portal_assessment_photos WHERE assessment_id = a.id) AS photo_count
FROM portal_assessments a
JOIN portal_schools s ON s.id = a.school_id
JOIN dashboard_users u ON u.id = a.staff_id
LEFT JOIN portal_assessment_periods p ON p.id = a.period_id
-- Cari periode yang cocok dengan tanggal pembuatan draft
LEFT JOIN portal_assessment_periods correct_p 
    ON a.created_at::date >= correct_p.start_date 
    AND a.created_at::date <= correct_p.end_date
WHERE a.status = 'draft'
  AND a.period_id <> correct_p.id  -- period_id tidak cocok dengan tanggal pembuatan
ORDER BY a.created_at DESC;

-- =====================
-- STEP 2: KEMBALIKAN period_id draft ke periode yang benar
-- berdasarkan tanggal pembuatan draft
-- =====================

BEGIN;

UPDATE portal_assessments a
SET period_id = correct_p.id
FROM portal_assessment_periods correct_p
WHERE a.status = 'draft'
  AND a.created_at::date >= correct_p.start_date
  AND a.created_at::date <= correct_p.end_date
  AND a.period_id <> correct_p.id;

-- Verifikasi hasil (harusnya 0 baris = semua sudah benar)
SELECT COUNT(*) AS remaining_mismatched
FROM portal_assessments a
JOIN portal_assessment_periods correct_p 
    ON a.created_at::date >= correct_p.start_date 
    AND a.created_at::date <= correct_p.end_date
WHERE a.status = 'draft'
  AND a.period_id <> correct_p.id;

COMMIT;

-- =====================
-- STEP 3: HAPUS draft kosong duplikat
-- Draft yang tidak punya skor DAN tidak punya foto (dibuat karena bug)
-- =====================

-- Preview dulu: draft kosong yang akan dihapus
SELECT 
    a.id,
    a.staff_id,
    a.school_id,
    s.name AS school_name,
    u.email,
    p.name AS period_name,
    a.created_at
FROM portal_assessments a
JOIN portal_schools s ON s.id = a.school_id
JOIN dashboard_users u ON u.id = a.staff_id
LEFT JOIN portal_assessment_periods p ON p.id = a.period_id
WHERE a.status = 'draft'
  AND NOT EXISTS (SELECT 1 FROM portal_assessment_scores WHERE assessment_id = a.id)
  AND NOT EXISTS (SELECT 1 FROM portal_assessment_photos WHERE assessment_id = a.id)
  -- Hanya hapus jika ada draft LAIN yang berisi data untuk sekolah+staff yang sama
  AND EXISTS (
      SELECT 1 FROM portal_assessments other
      WHERE other.school_id = a.school_id
        AND other.staff_id = a.staff_id
        AND other.status = 'draft'
        AND other.id <> a.id
        AND (
            EXISTS (SELECT 1 FROM portal_assessment_scores WHERE assessment_id = other.id)
            OR EXISTS (SELECT 1 FROM portal_assessment_photos WHERE assessment_id = other.id)
        )
  )
ORDER BY a.created_at DESC;

-- Hapus draft kosong duplikat (uncomment untuk eksekusi)
-- BEGIN;
-- DELETE FROM portal_assessments a
-- USING portal_schools s, dashboard_users u
-- WHERE s.id = a.school_id AND u.id = a.staff_id
--   AND a.status = 'draft'
--   AND NOT EXISTS (SELECT 1 FROM portal_assessment_scores WHERE assessment_id = a.id)
--   AND NOT EXISTS (SELECT 1 FROM portal_assessment_photos WHERE assessment_id = a.id)
--   AND EXISTS (
--       SELECT 1 FROM portal_assessments other
--       WHERE other.school_id = a.school_id
--         AND other.staff_id = a.staff_id
--         AND other.status = 'draft'
--         AND other.id <> a.id
--         AND (
--             EXISTS (SELECT 1 FROM portal_assessment_scores WHERE assessment_id = other.id)
--             OR EXISTS (SELECT 1 FROM portal_assessment_photos WHERE assessment_id = other.id)
--         )
--   );
-- COMMIT;
