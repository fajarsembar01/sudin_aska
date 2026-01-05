# Testing Checklist - User Management & Monev Teams

Checklist untuk testing fitur-fitur yang baru diimplementasikan.

---

## 🗂️ Struktur Aplikasi

Aplikasi ASKA memiliki **2 app terpisah**:

### 1. **ASKA Insights** (Dashboard Utama)
- **Base URL**: `http://127.0.0.1:5002/`
- **Location**: `dashboard/` (routes di `dashboard/auth.py`, `dashboard/routes.py`)
- **Fitur utama**: Chat logs, Reports, statistik global
- **Menu**: Navbar biru dengan "ASKA Bot", "Laporan", "Manajemen"

### 2. **Portal PANBERSS** (Portal Penilaian Sekolah)
- **Base URL**: `http://127.0.0.1:5002/portal/`
- **Location**: `dashboard/portal/` (routes di `dashboard/portal/routes.py`)
- **Fitur utama**: Penilaian Sekolah, Statistik Portal, Setup Data, Sidak Planner, **User Dashboard & Tim Monev (baru)**
- **Menu**: Navbar hijau dengan icon sekolah

**⚠️ PENTING**: Semua alur **User Dashboard & Tim Monev** yang baru (termasuk approval anggota) dites dari Portal (navbar hijau) via menu Admin.

---

## Prerequisites - Persiapan

- [x] Jalankan migration: `python3 run_monev_teams_migration.py`
  - Expected: "Migration completed successfully!"
- [x] Pastikan migration request anggota sudah jalan (table `monev_team_member_requests` ada)
  - File SQL: `migrations/add_team_member_requests.sql`
  - Quick check (opsional): `\d monev_team_member_requests` di psql
- [x] Start server: `python3 -m dashboard.app` atau `python3 app.py`
  - Expected: Server running di port 5002

---

## TEST 1: Staff Registration Flow

**App Context**: 🎯 ASKA Insights (Dashboard Utama)

### 1.1 Access Registration Page
- [x] Buka: `http://127.0.0.1:5002/login` (ASKA Insights login)
- [x] Klik link "Daftar Akun Baru (Staff/Admin)"
- [x] Expected: Redirect ke `/register`

### 1.2 Submit Registration
- [x] Isi form dengan data test:
  - Nama: `Test Staff`
  - Email: `test.staff@testing.com`
  - Password: `testing123`
  - Kecamatan: Pilih salah satu
  - WhatsApp: `08123456789`
  - NIP: `123456`
  - Jabatan: `Pengawas`
- [x] Klik "Daftar"
- [x] Expected: Redirect ke `/registration-status/X`
- [x] Expected: Tampil pesan "Status: Pending Verifikasi"

---

## TEST 2: Admin - User Verification (Portal)

**App Context**: 🎯 Portal PANBERSS (navbar hijau)

### 2.1 Login sebagai Admin
- [x] Login dengan akun admin di Portal (`/portal/login` atau dari sesi aktif)
- [x] Buka menu **Admin → User Dashboard** (`/portal/settings/users`)
- [x] Expected: Halaman dengan 2 tab (Daftar User & Verifikasi User)

### 2.2 Verify Tab "Verifikasi User"
- [x] Klik tab "Verifikasi User"
- [x] Expected: User `test.staff@testing.com` muncul dengan badge "Pending"
- [x] Expected: Badge count di tab (misal: "1")
- [x] Expected: Kolom "Tanggal Pengajuan" tampil dengan datetime

### 2.3 Approve User
- [x] Klik button ✓ (Setujui) di samping user
- [x] Expected: Flash message "Status user berhasil diubah menjadi approved"
- [x] Expected: User pindah ke tab "Daftar User"

### 2.4 Test Dynamic Edit
- [ ] Di tab "Daftar User", klik row user `test.staff@testing.com`
- [ ] Expected: Form kiri terisi otomatis
- [ ] Expected: Title berubah "Edit User"
- [ ] Expected: Button "Batal Edit" muncul
- [ ] Ubah Nama jadi `Test Staff Updated`
- [ ] Klik "Update User"
- [ ] Expected: Flash "Data user berhasil diperbarui"

---

## TEST 3: Admin - Tim Monev & Approval (Portal)

**App Context**: 🎯 Portal PANBERSS (navbar hijau)

### 3.1 Access Monev Teams
- [ ] Pastikan login sebagai admin
- [ ] Buka menu **Admin → Tim Monev** (`/portal/settings/monev-teams`)
- [ ] Expected: Ada tab Tim Kasi, Tim Kecamatan, Tim Khusus

### 3.2 Assign Coordinator
- [ ] Pilih tab kecamatan/kasi sesuai tim
- [ ] Dropdown "Pilih Koordinator" → pilih user role coordinator
- [ ] Klik "Simpan"
- [ ] Expected: Flash "Koordinator berhasil diperbarui"
- [ ] Expected: Alert biru muncul: "Koordinator saat ini: [Nama]"

### 3.3 Add Team Member (langsung oleh admin)
- [ ] Section "Tambah Anggota" → pilih `Test Staff Updated`
- [ ] Klik "Tambah"
- [ ] Expected: Flash "Anggota berhasil ditambahkan"
- [ ] Expected: Nama muncul di table anggota & badge count bertambah

### 3.4 Remove Team Member
- [ ] Klik icon 🗑️ di samping anggota
- [ ] Confirm deletion
- [ ] Expected: Flash "Anggota berhasil dihapus"
- [ ] Expected: Nama hilang dari table

### 3.5 Approve/Reject Request (baru)
- [ ] Pastikan ada permintaan pending (lihat TEST 4)
- [ ] Di kartu "Permintaan Anggota" klik **Setujui** → expected: flash "Permintaan anggota ... disetujui" dan anggota otomatis masuk tabel tim
- [ ] Coba kasus **Tolak** untuk request lain → expected: flash info penolakan, status di tabel permintaan menjadi "Ditolak"

---

## TEST 4: Coordinator - Tim Saya & Pengajuan Anggota

### 4.1 Login as Coordinator
- [ ] Logout dari admin
- [ ] Login dengan akun koordinator (contoh: `test.staff@testing.com`)
- [ ] Expected: Menu "Tim Saya" muncul di navbar hijau

### 4.2 View Team (Tim Saya)
- [ ] Klik "Tim Saya" (`/portal/my-team`)
- [ ] Expected: Tampil info tim (kecamatan/koordinator/jumlah anggota)
- [ ] Expected: Row dengan nama Anda ter-highlight (biru) + badge "Anda"

### 4.3 Cari & Ajukan Anggota
- [ ] Di form "Ajukan Penambahan Anggota" ketik di input pencarian (nama/email/NIP) → dropdown menyaring opsi
- [ ] Pilih satu staff lalu isi catatan opsional, klik "Ajukan"
- [ ] Expected: Flash "Permintaan tambah anggota dikirim..."
- [ ] Expected: Tabel "Status Permintaan Anggota" menampilkan baris baru status Pending

### 4.4 Role Member (read-only)
- [ ] Login sebagai anggota biasa yang tergabung di tim
- [ ] Buka `/portal/my-team`
- [ ] Expected: Hanya tampilan informasi, tidak ada tombol tambah anggota

---

## TEST 5: Sticky Form (User Management)

### 5.1 Test Sticky Behavior
- [ ] Login sebagai admin
- [ ] Go to `/portal/settings/users`
- [ ] Scroll down list "Daftar User" yang panjang
- [ ] Expected: Form kiri tetap di atas, tidak ikut scroll

---

## TEST 6: Database Verification

```sql
-- Check monev teams
SELECT * FROM monev_teams;

-- Check monev members
SELECT 
    mtm.*,
    u.full_name,
    u.email
FROM monev_team_members mtm
JOIN dashboard_users u ON mtm.staff_id = u.id;

-- Check member requests
SELECT 
    r.*, t.name AS team_name, u.full_name AS staff_name
FROM monev_team_member_requests r
JOIN monev_teams t ON r.team_id = t.id
JOIN dashboard_users u ON r.staff_id = u.id;

-- Check user verification
SELECT 
    full_name,
    email,
    account_status,
    whatsapp_number
FROM dashboard_users
WHERE email = 'test.staff@testing.com';
```

- [ ] All queries return expected data

---

## Summary Checklist

| Feature | Tested | Pass |
|---------|--------|------|
| Staff Registration | ✅ | ✅ |
| Registration Status Page | ✅ | ✅ |
| User Verification Tabs | ✅ | ✅ |
| Approve/Reject Users | ✅ | ✅ |
| Dynamic Edit Form | ✅ | ✅ |
| Sticky Form Behavior | ✅ | ✅ |
| Assign Coordinator | ✅ | ✅ |
| Add Team Member | ✅ | ✅ |
| Remove Team Member | ✅ | ✅ |
| Member Request Flow (Coordinator→Admin) | ☐ | ☐ |
| Dropdown Search Staff (Tim Saya) | ☐ | ☐ |
| Coordinator View Team | ✅ | ✅ |
| Read-Only Permissions | ✅ | ✅ |
| Portal Admin Stats (All data) | ☐ | ☐ |
| Portal Admin Stats (Filter per Tim) | ☐ | ☐ |
| Portal Coordinator Stats (Tim) | ✅ | ✅ |
| Portal Gallery/Related Photos (Tim scope) | ✅ | ✅ |
| Portal Map (Team vs All) | ☐ | ☐ |

---

## Notes / Issues Found

_(Catat di sini jika ada bug atau masalah yang ditemukan selama testing)_

- 
