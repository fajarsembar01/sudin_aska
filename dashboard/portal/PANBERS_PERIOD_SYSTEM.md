# Sistem Periode di PANBERS (Portal Penilaian Berseri)

Dokumen ini merangkum cara kerja **periode penilaian** di modul PANBERS berdasarkan implementasi saat ini.

## 1) Struktur data inti

Periode disimpan di tabel `portal_assessment_periods` dengan kolom:
- `id`
- `name`
- `start_date`
- `end_date`
- `is_active`
- `created_at`

Ada indeks unik parsial untuk menjamin **hanya satu periode aktif**:
- `idx_portal_periods_active` pada `is_active = TRUE`.

Relasi utama:
- `portal_assessments.period_id -> portal_assessment_periods.id` (`ON DELETE SET NULL`).
- `staff_assignment_requests.period_id -> portal_assessment_periods.id` (`ON DELETE SET NULL`, dari migrasi 022).

## 2) Pembuatan periode manual vs otomatis

### Manual (oleh admin)
Admin dapat membuat periode dari halaman `/admin/periods`.
Jika opsi "set aktif" dipilih saat create/edit, sistem akan menonaktifkan periode lain lalu mengaktifkan periode terpilih.

### Otomatis (monthly auto-provisioning)
Saat daftar periode/periode aktif diakses, sistem akan:
1. memastikan periode bulanan tersedia dari bulan berjalan sampai **36 bulan ke depan**;
2. mencari periode yang mencakup tanggal hari ini;
3. mengaktifkan periode tersebut jika belum aktif.

Nama periode otomatis memakai format bulan Indonesia (mis. `Januari 2026`).

## 3) Aturan periode aktif

- Hanya role `admin` yang boleh mengelola periode (create/edit/activate/delete).
- `set_active_period(period_id)` selalu men-set satu periode aktif dan menonaktifkan yang lain.
- `get_active_period()` memprioritaskan auto-activation periode yang mencakup hari ini.

## 4) Dampak periode ke proses bisnis

### A. Penugasan & draft assessment
Pada `assign_assessment(...)`:
- Jika `period_id` tidak dikirim, sistem memakai periode aktif (dengan auto-activation).
- Sistem mencegah duplikasi draft untuk kombinasi: `school_id + staff_id + period_id`.

### B. Assessment coordinator/staff
- Halaman coordinator/admin yang butuh konteks periode memuat daftar periode dari `list_periods()`.
- Default pilihan periode umumnya mengarah ke periode aktif.

### C. Permintaan penugasan (assignment request)
- Request dapat membawa `period_id` opsional.
- Unique pending request mempertimbangkan periode, sehingga request sekolah yang sama bisa tetap valid jika periodenya berbeda.

## 5) Penghapusan periode

`delete_period(period_id)` hanya menghapus periode yang:
- ada, dan
- **bukan** periode aktif.

Walau fungsi menyebut "not referenced", implementasi saat ini hanya memblokir periode aktif.
Referensi di tabel lain aman karena FK menggunakan `ON DELETE SET NULL`.

## 6) Risiko/hal yang perlu diwaspadai

1. **Overlapping period**
   - Create/edit manual belum memvalidasi overlap tanggal.
   - Jika overlap terjadi, auto-activation akan memilih period dengan `start_date` terbaru (lalu `id` terbaru).

2. **Ketergantungan pada akses fungsi list/get active**
   - Auto-create & auto-activate berjalan ketika fungsi terkait dipanggil.
   - Bila tidak ada traffic ke endpoint terkait periode, provisioning tidak berjalan sampai fungsi itu diakses lagi.

3. **Delete period tetap memungkinkan saat direferensikan**
   - Karena FK `ON DELETE SET NULL`, data assessment/request tidak hilang, tapi periodenya menjadi `NULL`.

## 7) Rekomendasi peningkatan

- Tambah validasi non-overlap di create/edit periode.
- Tambah guardrail agar `start_date <= end_date` divalidasi eksplisit di layer route/queries.
- Tambah opsi soft-delete atau arsip periode untuk audit historis yang lebih kuat.
- Pertimbangkan fallback label konsisten saat `period_id` menjadi `NULL` (mis. "Tanpa Periode").

---

Ringkasnya, sistem periode PANBERS saat ini sudah kuat untuk kebutuhan operasional bulanan (auto-provision + single active period), namun masih bisa ditingkatkan pada validasi overlap dan tata kelola lifecycle periode.
