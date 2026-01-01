# Testing Checklist - User Management & Monev Teams

Checklist untuk testing fitur-fitur yang baru diimplementasikan.

---

## 🗂️ Struktur Aplikasi

Aplikasi ASKA memiliki **2 app terpisah**:

### 1. **ASKA Insights** (Dashboard Utama)
- **Base URL**: `http://127.0.0.1:5002/`
- **Location**: `dashboard/` (routes di `dashboard/auth.py`, `dashboard/routes.py`)
- **Fitur**: Chat logs, Reports, User Management, **Tim Monev**
- **Menu**: Navbar biru dengan "ASKA Bot", "Laporan", "Manajemen"

### 2. **Portal PANBERSS** (Portal Penilaian Sekolah)
- **Base URL**: `http://127.0.0.1:5002/portal/`
- **Location**: `dashboard/portal/` (routes di `dashboard/portal/routes.py`)
- **Fitur**: Penilaian Sekolah, Statistik, Setup Data Master, Sidak Planner
- **Menu**: Navbar hijau dengan icon sekolah

**⚠️ PENTING**: Fitur User Management dan Tim Monev yang kita test ada di **ASKA Insights**, bukan di Portal!

---

## Prerequisites - Persiapan

- [x] Jalankan migration: `python3 run_monev_teams_migration.py`
  - Expected: "Migration completed successfully!"
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

## TEST 2: Admin - User Verification

**App Context**: 🎯 ASKA Insights (Dashboard Utama)

### 2.1 Login sebagai Admin
- [x] Login dengan akun admin di ASKA Insights
- [x] Pastikan di navbar ada menu "Manajemen" (warna biru)
- [x] Go to: Manajemen → Admin Dashboard (`/settings/users`)
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

## TEST 3: Admin - Konfigurasi Tim Monev

**App Context**: 🎯 ASKA Insights (Dashboard Utama)

### 3.1 Access Monev Teams
- [ ] Pastikan masih login sebagai admin di ASKA Insights (navbar biru)
- [ ] Go to: Manajemen → Tim Monev (`/settings/monev-teams`)
- [ ] **JANGAN** buka dari Portal (navbar hijau) - fitur ini khusus ASKA Insights!
- [ ] Expected: Halaman dengan tab per kecamatan

### 3.2 Assign Coordinator
- [ ] Pilih tab "Cilincing" (atau kecamatan lain)
- [ ] Di dropdown "Pilih Koordinator", pilih user dengan role coordinator
- [ ] Klik "Simpan"
- [ ] Expected: Flash "Koordinator berhasil diperbarui"
- [ ] Expected: Alert biru muncul: "Koordinator saat ini: [Nama]"

### 3.3 Add Team Member
- [ ] Scroll ke section "Tambah Anggota"
- [ ] Pilih `Test Staff Updated` dari dropdown
- [ ] Klik "Tambah"
- [ ] Expected: Flash "Anggota berhasil ditambahkan"
- [ ] Expected: Nama muncul di table anggota
- [ ] Expected: Badge count di tab bertambah

### 3.4 Remove Team Member
- [ ] Klik icon 🗑️ di samping anggota
- [ ] Confirm deletion
- [ ] Expected: Flash "Anggota berhasil dihapus"
- [ ] Expected: Nama hilang dari table

---

## TEST 4: Coordinator/Staff View

### 4.1 Login as Coordinator/Staff
- [ ] Logout dari admin
- [ ] Login dengan akun `test.staff@testing.com` (password: `testing123`)
- [ ] Expected: Menu "Tim Saya" muncul di navbar

### 4.2 View Team
- [ ] Klik "Tim Saya" (`/my-team`)
- [ ] Expected: Tampil info tim (Kecamatan, Koordinator, Jumlah Anggota)
- [ ] Expected: Badge "Anda adalah Anggota tim ini" (hijau)
- [ ] Expected: Row dengan nama Anda ter-highlight (biru)
- [ ] Expected: Badge "Anda" di samping nama

### 4.3 Test Read-Only
- [ ] Expected: TIDAK ADA button edit/hapus
- [ ] Expected: Hanya tampilan informasi saja

---

## TEST 5: Sticky Form (User Management)

### 5.1 Test Sticky Behavior
- [ ] Login sebagai admin
- [ ] Go to `/settings/users`
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
