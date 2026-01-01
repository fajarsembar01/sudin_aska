# Testing Checklist - Tim Monev Management

Last Updated: 2026-01-01

---

## 🔐 Test Credentials

**Password untuk SEMUA akun:** `testing123`

### Koordinator Kasi (Jenjang)
| Email | Nama | Tim |
|-------|------|-----|
| `kasi.sd@test.com` | Mulyadi | SD |
| `kasi.smp@test.com` | Acep Mahmudin | SMP SMA |
| `kasi.paud@test.com` | Meliyati | PAUD PMPK |
| `kasi.smk@test.com` | Suyamti | SMK KP |

### Koordinator Kecamatan (Kasatlak)
| Email | Nama | Tim |
|-------|------|-----|
| `kasatlak.cilincing@test.com` | Sahri | Cilincing |
| `kasatlak.koja@test.com` | Jumaedy | Koja |
| `kasatlak.kgading@test.com` | Sriyono | Kelapa Gading |

### Staff
| Email | Nama | Tim |
|-------|------|-----|
| `staff.sd1@test.com` | Richi Fernando | SD |
| `staff.sd2@test.com` | Ade Budiman | SD |
| `staff.smp1@test.com` | July Astuti | SMP SMA |
| `staff.cilincing1@test.com` | Ahmad Turmuzi | Cilincing |
| `staff.koja1@test.com` | Anton Purbaya | Koja |

---

## 📍 TEST 1: Access Tim Monev Page (Admin)

**Login:** `fajar.admin@test.com` / `testing123` (atau akun admin lain)

- [ ] Navigasi: **Manajemen → Tim Monev**
- [ ] ✅ Expected: 3 tab utama (Kasi | Kecamatan | Tim Khusus)
- [ ] ✅ Expected: Tombol **"+ Tambah Tim Baru"**

---

## 📍 TEST 2: Verifikasi Koordinator & Anggota

### 2.1 Tim Kasi SD
- [ ] Klik tab **"Tim Kasi"** → **"SD"**
- [ ] ✅ Expected: Koordinator = **Mulyadi (Kasi SD)**
- [ ] ✅ Expected: Anggota = Richi Fernando, Ade Budiman

### 2.2 Tim Kecamatan Cilincing
- [ ] Klik tab **"Tim Kecamatan"** → **"Cilincing"**
- [ ] ✅ Expected: Koordinator = **Sahri (Kasatlak Cilincing)**
- [ ] ✅ Expected: Anggota = Ahmad Turmuzi

---

## 📍 TEST 3: Login sebagai Koordinator

### 3.1 Test Kasi SD
- [ ] Login: `kasi.sd@test.com` / `testing123`
- [ ] ✅ Expected: Role = coordinator
- [ ] Klik **"Tim Saya"**
- [ ] ✅ Expected: Tampil info Tim SD
- [ ] ✅ Expected: Daftar anggota (Richi, Ade)

### 3.2 Test Kasatlak Cilincing
- [ ] Logout
- [ ] Login: `kasatlak.cilincing@test.com` / `testing123`
- [ ] Klik **"Tim Saya"**
- [ ] ✅ Expected: Tampil info Tim Cilincing

---

## 📍 TEST 4: Login sebagai Staff

- [ ] Login: `staff.sd1@test.com` / `testing123`
- [ ] ✅ Expected: Role = staff
- [ ] Klik **"Tim Saya"**
- [ ] ✅ Expected: Tampil info Tim SD
- [ ] ✅ Expected: Row saya ter-highlight dengan badge "Anda"

---

## 📍 TEST 5: Create Custom Team

- [ ] Login admin
- [ ] Klik **"+ Tambah Tim Baru"**
- [ ] Buat: `Tim Audit 2026` tipe `Tim Khusus`
- [ ] ✅ Expected: Tim muncul di tab "Tim Khusus"

---

## 📍 TEST 6: Delete Custom Team

- [ ] Di tab "Tim Khusus" → pilih tim
- [ ] Klik **"Hapus Tim"**
- [ ] ✅ Expected: Tim terhapus

---

## 📍 TEST 7: Portal Integration

**URL:** `/portal/settings/monev-teams`

- [ ] Login admin ke Portal
- [ ] ✅ Expected: Navbar **HIJAU**
- [ ] ✅ Expected: UI sama, koordinator & anggota tampil

---

## 🔧 Commands

```bash
# Restart server
python3 -m dashboard.app

# Re-create dummy data jika perlu
python3 create_dummy_team_data.py
```
