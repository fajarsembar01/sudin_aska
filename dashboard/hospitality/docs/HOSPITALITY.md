# 📋 Dokumentasi Fitur Hospitality

> Panduan lengkap fitur penilaian hospitality sekolah — meliputi konsep, alur kerja per role, referensi rute, skema basis data, dan konfigurasi sistem.

---

## Daftar Isi

1. [Gambaran Umum](#1-gambaran-umum)
2. [Hubungan dengan Sistem Buku Tamu](#2-hubungan-dengan-sistem-buku-tamu)
3. [Peran & Hak Akses](#3-peran--hak-akses)
4. [Status Penilaian](#4-status-penilaian)
5. [Alur Kerja per Role](#5-alur-kerja-per-role)
   - [5.1 Staff — Melakukan Penilaian Hospitality](#51-staff--melakukan-penilaian-hospitality)
   - [5.2 Tamu — Mengisi Buku Tamu (paralel)](#52-tamu--mengisi-buku-tamu-paralel)
   - [5.3 Admin / Staff — Menyetujui Transaksi Buku Tamu](#53-admin--staff--menyetujui-transaksi-buku-tamu)
   - [5.4 Staff — Verifikasi (Menghubungkan Buku Tamu)](#54-staff--verifikasi-menghubungkan-buku-tamu)
   - [5.5 Sekolah — Melihat & Merespons Penilaian](#55-sekolah--melihat--merespons-penilaian)
   - [5.6 Admin / Koordinator — Memantau Dashboard](#56-admin--koordinator--memantau-dashboard)
   - [5.7 Admin / Koordinator — Mengelola Reopen Request](#57-admin--koordinator--mengelola-reopen-request)
6. [Alur Reopen (Buka Ulang Penilaian)](#6-alur-reopen-buka-ulang-penilaian)
7. [Sistem Notifikasi](#7-sistem-notifikasi)
8. [Referensi URL & Route](#8-referensi-url--route)
9. [Skema Basis Data](#9-skema-basis-data)
10. [Konfigurasi Komponen & Aspek](#10-konfigurasi-komponen--aspek)
11. [Export Data CSV](#11-export-data-csv)
12. [Aturan Bisnis Penting](#12-aturan-bisnis-penting)

---

## 1. Gambaran Umum

Fitur **Hospitality** adalah sistem penilaian kondisi penyambutan dan pelayanan sekolah yang dilakukan oleh staff pengawas lapangan. Setiap kunjungan ke sekolah dinilai berdasarkan beberapa **komponen** (contoh: Kebersihan, Keramahan, Fasilitas) yang masing-masing memiliki sejumlah **aspek** dengan skala skor **1–5**.

### Tujuan Sistem

- Mencatat kondisi hospitality sekolah pada saat kunjungan berlangsung
- Menghubungkan penilaian dengan data kunjungan di **Buku Tamu** sebagai bukti fisik kehadiran
- Memberikan transparansi kepada pihak sekolah tentang hasil penilaian mereka
- Memungkinkan admin memantau tren, perbandingan antar sekolah, dan statistik keseluruhan

### Komponen Teknis

```
Blueprint  : hospitality  (url_prefix="/hospitality")
Template   : dashboard/hospitality/templates/hospitality/
Queries    : dashboard/hospitality/queries.py
Routes     : dashboard/hospitality/routes.py
Skala skor : 1 – 5  (HOSPITALITY_SCORE_MAX = 5)
```

---

## 2. Hubungan dengan Sistem Buku Tamu

### Prinsip Dasar

Penilaian hospitality dan pengisian buku tamu adalah **dua proses yang berjalan independen** dan baru bertemu di satu titik: **langkah verifikasi**.

```
TRACK A — Staff                    TRACK B — Tamu & Admin
─────────────────                  ──────────────────────────
Staff isi form penilaian           Tamu isi form Buku Tamu
→ status: submitted                → transaksi: pending
     (bisa dilakukan                    (bisa terjadi sebelum,
      kapan saja)                        bersamaan, atau setelah
                                         Track A)
         │                                      │
         │                              Admin approve transaksi
         │                              → status: approved
         │                                      │
         └──────────────┬───────────────────────┘
                        ▼
              STAFF MENGHUBUNGKAN TRANSAKSI
              (link_guestbook)
              → status penilaian: verified
```

### Kesimpulan Urutan

> **Nilai hospitality DULU, verifikasi buku tamu BELAKANGAN.**
>
> - Penilaian hospitality (pengisian skor) **tidak membutuhkan** buku tamu sama sekali.
> - Verifikasi (menghubungkan buku tamu) **hanya bisa dilakukan** setelah ada transaksi Buku Tamu berstatus `approved`.

### Mengapa Buku Tamu Diperlukan untuk Verifikasi?

Buku Tamu berfungsi sebagai **bukti fisik** bahwa kunjungan benar-benar terjadi. Tanpa transaksi yang sudah disetujui, penilaian akan tetap berstatus `submitted` dan tidak bisa dianggap terverifikasi.

### Validasi di Sistem (Double Check)

Sistem melakukan pengecekan ganda sebelum mengizinkan penghubungan:

**1. Di query kandidat (`list_guestbook_candidates`):**
```sql
WHERE t.school_id = %s
  AND t.status = 'approved'   -- hanya transaksi approved yang tampil di dropdown
```

**2. Di saat eksekusi (`link_guestbook_transaction`):**
```python
if (row.get("status") or "").lower() != "approved":
    raise ValueError("Transaksi buku tamu belum terverifikasi")
```

Sistem menolak keras jika transaksi belum `approved`, bahkan jika ID transaksi dimanipulasi secara manual.

### Kondisi Dropdown Transaksi

| Kondisi | Tampilan di Dropdown |
|---------|----------------------|
| Belum ada transaksi sama sekali untuk sekolah ini | Kosong; tombol Hubungkan di-disable |
| Transaksi ada tapi masih `pending` | Tidak muncul (difilter sistem) |
| Transaksi ada tapi `rejected` | Tidak muncul |
| Transaksi `approved`, belum dipakai | Muncul, bisa dipilih |
| Transaksi `approved`, sudah dipakai penilaian lain | Muncul tapi di-disable |

---

## 3. Peran & Hak Akses

| Role | Akses | Batasan |
|------|-------|---------|
| **Staff** | Membuat penilaian, menghubungkan buku tamu, menambah komentar, mengajukan reopen | Hanya bisa melihat penilaian milik sendiri; **1 penilaian per sekolah per hari** |
| **Sekolah** | Melihat daftar penilaian sekolah sendiri, menambah komentar | Hanya bisa mengakses data sekolah sendiri |
| **Koordinator** | Akses penuh ke dashboard admin, reopen requests, setup, export | Sama dengan admin kecuali beberapa fitur superadmin |
| **Admin** | Akses penuh ke semua fitur termasuk konfigurasi komponen/aspek | — |

### Matriks Akses Detail

| Fitur | Staff | Sekolah | Koordinator | Admin |
|-------|:-----:|:-------:|:-----------:|:-----:|
| Buat penilaian hospitality | ✅ | ❌ | ❌ | ❌ |
| Lihat penilaian | ✅* | ✅* | ✅ | ✅ |
| Hubungkan buku tamu (verifikasi) | ✅** | ❌ | ❌ | ❌ |
| Tambah komentar | ✅ | ✅ | ✅ | ✅ |
| Ajukan reopen | ✅ | ❌ | ❌ | ❌ |
| Setujui / tolak reopen | ❌ | ❌ | ✅ | ✅ |
| Dashboard statistik | ❌ | ❌ | ✅ | ✅ |
| Setup komponen/aspek | ❌ | ❌ | ✅ | ✅ |
| Export CSV | ❌ | ❌ | ✅ | ✅ |

> \* Hanya bisa melihat milik sendiri / sekolah sendiri
> \*\* Hanya pada penilaian milik sendiri, dan hanya jika ada transaksi Buku Tamu yang sudah `approved`

---

## 4. Status Penilaian

Setiap penilaian memiliki satu dari tiga status aktif berikut:

```
submitted ──────► verified
    ▲                 │
    │                 │  (reopen disetujui)
    └──── reopened ◄──┘
```

> **Catatan**: Status `draft` dibuat oleh sistem secara internal saat `create_assessment`, lalu langsung diubah ke `submitted` dalam request POST yang sama. Status ini tidak pernah terlihat oleh pengguna.

| Status | Deskripsi | Siapa yang mengubah |
|--------|-----------|---------------------|
| `submitted` | Skor telah diinput dan disubmit, menunggu verifikasi buku tamu | Sistem saat form penilaian dikirim |
| `verified` | Penilaian sudah dihubungkan dengan transaksi Buku Tamu `approved` | Sistem saat staff berhasil menghubungkan transaksi |
| `reopened` | Penilaian dikembalikan setelah reopen disetujui, bisa diverifikasi ulang | Sistem saat admin menyetujui reopen request |

---

## 5. Alur Kerja per Role

---

### 5.1 Staff — Melakukan Penilaian Hospitality

Ini adalah langkah **pertama** yang dilakukan. Tidak membutuhkan buku tamu sama sekali.

#### Prasyarat
- Akun aktif dengan role `staff`
- Sekolah sudah terdaftar di sistem (`portal_schools`)
- Komponen dan aspek sudah dikonfigurasi oleh admin

#### Langkah-langkah

```
1. Login ke portal
2. Klik menu "Hospitality" di navbar
   → Redirect ke /hospitality/staff
3. Halaman "Penilaian Hospitality" terbuka
4. Cari sekolah di kolom pencarian (minimal 3 karakter / NPSN)
   → Autocomplete live search dari API /portal/api/schools/search
5. Pilih sekolah dari hasil pencarian
   → Otomatis redirect ke /hospitality/staff/assess/<school_id>
6. Halaman form penilaian terbuka:
   - Tampil semua Komponen beserta Aspek-aspeknya (hanya yang aktif)
   - Setiap aspek memiliki pilihan skor radio button: 1, 2, 3, 4, 5
   - Default skor: 1 untuk semua aspek
   - Isi catatan umum (opsional)
7. Klik tombol "Simpan & Lanjut Verifikasi"
   → POST ke /hospitality/staff/assess/<school_id>
   → Sistem membuat assessment (status: submitted)
   → Flash message: "Penilaian tersimpan. Silakan hubungkan dengan buku tamu untuk verifikasi."
   → Redirect ke /hospitality/assessment/<id>
```

#### Aturan Penting
- **Maksimal 1 penilaian per sekolah per hari** (batasan `ensure_daily_limit` berdasarkan WIB)
- Jika sudah ada penilaian hari ini untuk sekolah yang sama, sistem menampilkan error
- Penilaian dapat dibuat **tanpa perlu buku tamu** — verifikasi dilakukan terpisah di langkah 5.4

#### Melihat Daftar Penilaian Sendiri

Di halaman `/hospitality/staff`:
- Filter berdasarkan status: `submitted` / `verified` / `reopened`
- Pencarian berdasarkan nama sekolah / NPSN
- Klik tombol **Buka** untuk melihat detail

---

### 5.2 Tamu — Mengisi Buku Tamu (paralel)

Proses ini berjalan **independen** dari penilaian hospitality. Bisa terjadi sebelum, bersamaan, atau setelah staff mengisi penilaian — yang penting sudah `approved` saat staff ingin verifikasi.

```
1. Tamu (pengunjung) datang ke sekolah
2. Tamu membuka form Buku Tamu
   → URL: /buku-tamu/<kode_sekolah>
3. Tamu mengisi:
   - Nama lengkap
   - Instansi/asal
   - Keperluan kunjungan
   - (Sistem mencatat waktu kunjungan, foto jika ada, koordinat GPS)
4. Tamu submit form
   → Transaksi masuk dengan status: pending
   → Sekolah dan admin mendapat notifikasi
```

---

### 5.3 Admin / Staff — Menyetujui Transaksi Buku Tamu

Transaksi harus **disetujui (approved)** agar bisa digunakan sebagai bukti di langkah verifikasi.

```
1. Admin/Staff buka modul Daftar Tamu
   → /daftar-tamu/admin  atau  /daftar-tamu/staff
2. Cari transaksi dengan status "pending"
3. Verifikasi data kunjungan (nama, keperluan, waktu)
4. Klik tombol "Setujui" / Approve
   → Status transaksi berubah: pending → approved
   → Transaksi kini tersedia di dropdown verifikasi Hospitality
```

> ⚠️ Langkah ini harus selesai **sebelum** staff bisa melakukan verifikasi di langkah 5.4.

---

### 5.4 Staff — Verifikasi (Menghubungkan Buku Tamu)

Ini adalah titik **pertemuan** antara Track A (penilaian) dan Track B (buku tamu). Kedua proses harus sudah selesai sebelum langkah ini bisa dilakukan.

#### Prasyarat WAJIB
- Penilaian sudah berstatus `submitted` (langkah 5.1 selesai)
- Ada transaksi Buku Tamu berstatus **`approved`** untuk sekolah tersebut (langkah 5.2 + 5.3 selesai)
- Transaksi belum digunakan oleh penilaian lain

#### Langkah-langkah

```
1. Buka detail penilaian di /hospitality/assessment/<id>
2. Di sidebar kiri, lihat kartu "Verifikasi Buku Tamu"
   → Jika ada transaksi approved → dropdown berisi daftar transaksi
   → Jika tidak ada             → muncul pesan warning, tombol di-disable
3. Pilih transaksi dari dropdown:
   - Urutan prioritas:
       1. Transaksi hari yang sama + belum dipakai  (prioritas tertinggi)
       2. Transaksi hari lain + belum dipakai
       3. Transaksi yang sudah dipakai penilaian lain (muncul tapi disabled)
4. Klik "Hubungkan & Verifikasi"
   → POST ke /hospitality/assessment/<id>/link-guestbook
   → Sistem memvalidasi ulang: transaksi harus masih berstatus approved
   → Status penilaian berubah: submitted → verified
   → Foto & tanggal kunjungan dari Buku Tamu ditampilkan di sidebar
   → Notifikasi dikirim ke:
      - Semua akun sekolah terkait (in-app + email)
      - Staff penilai (in-app)
      - Admin via Telegram (jika dikonfigurasi)
```

#### Setelah Verifikasi Berhasil

Kartu "Verifikasi Buku Tamu" berubah menjadi:
- Ikon `bi-book-fill` warna hijau
- Alert success: "Transaksi #`<id>`"
- Foto kunjungan (jika tersedia)
- Tanggal & waktu kunjungan

#### Jika Dropdown Kosong

Berarti belum ada transaksi Buku Tamu `approved` untuk sekolah tersebut. Solusi:
1. Pastikan tamu sudah mengisi Buku Tamu di `/buku-tamu/<kode_sekolah>`
2. Minta admin/staff yang berwenang menyetujui transaksi di modul Daftar Tamu
3. Kembali ke halaman ini — dropdown akan terisi setelah transaksi disetujui

---

### 5.5 Sekolah — Melihat & Merespons Penilaian

#### Akses
- Login dengan akun role `sekolah`
- Klik menu "Hospitality" → otomatis ke `/hospitality/sekolah`

#### Melihat Daftar Penilaian

```
1. Login ke portal → klik "Hospitality" di navbar
2. Halaman daftar terbuka: tanggal, nama petugas penilai, status
3. Klik "Detail" untuk melihat rincian
```

#### Melihat Detail Penilaian

```
Sidebar kiri:
  - Skor rata-rata (0–100) + predikat (Sangat Baik / Baik / Kurang / Kritis)
  - Nama & tanggal staff penilai
  - Info sekolah (NPSN, jenjang, status, skala)
  - Status verifikasi Buku Tamu:
      → Verified  : tampil foto kunjungan + tanggal (dari buku tamu yang di-approve)
      → Belum     : "Menunggu staff menghubungkan transaksi buku tamu"

Konten kanan:
  - Skor per komponen: header menampilkan total/max dan persentase
  - Skor per aspek dengan badge warna:
      → Hijau  : ≥ 85%
      → Kuning : 70–84%
      → Oranye : 55–69%
      → Merah  : < 55%
  - Catatan per aspek (jika ada)
```

> Sekolah **tidak dapat mengubah skor** — hanya membaca dan berkomentar.

#### Menambah Komentar

```
1. Scroll ke bagian "Komentar" di kolom kanan
2. Tulis komentar → klik "Kirim Komentar"
   → POST ke /hospitality/assessment/<id>/comment
   → Notifikasi dikirim ke staff penilai
```

#### Reopen Penilaian

> Sekolah **tidak dapat mengajukan reopen**. Reopen hanya bisa diajukan oleh staff penilai (pemilik penilaian).

---

### 5.6 Admin / Koordinator — Memantau Dashboard

#### Akses
- Login dengan akun role `admin` atau `coordinator`
- Klik menu "Hospitality" → otomatis ke `/hospitality/admin`

#### Isi Dashboard

**Stat Cards (4 kartu ringkasan):**

| Kartu | Isi |
|-------|-----|
| Total Penilaian | Jumlah semua penilaian + delta hari ini |
| Terverifikasi | Jumlah `verified` + % dari total |
| Menunggu Verifikasi | Jumlah `submitted` (penilaian sudah ada tapi belum ada buku tamu approved yang dihubungkan) |
| Sekolah Unik | Jumlah sekolah yang pernah dinilai + rata-rata skor |

**Tren 30 Hari:**
- Line chart: Total penilaian vs Terverifikasi
- Menunjukkan seberapa banyak penilaian yang berhasil diverifikasi

**Perankingan Sekolah:**
- Tab **Terbaik**: Top 10 sekolah rata-rata skor tertinggi
- Tab **Terendah**: 10 sekolah rata-rata skor terendah

**Galeri Foto:**
- Foto dari transaksi Buku Tamu yang berhasil dihubungkan ke penilaian

**Tabel Penilaian Terbaru:**
- 20 penilaian terakhir: Sekolah, Staff, Status, Dibuat, Aksi

**Ringkasan Status (Donut Chart):**
- Proporsi: Verified / Submitted / Draft

**Aksi Cepat:**
- Setup Komponen, Reopen Request, Export CSV, Dashboard Utama PANBERSS

**Reopen Request Panel:**
- Daftar permintaan reopen terbaru dengan tombol Setujui/Tolak

#### Membaca "Menunggu Verifikasi" yang Tinggi

Bisa berarti dua hal:
1. Penilaian sudah ada tapi tamu belum mengisi Buku Tamu
2. Buku Tamu sudah diisi tapi belum di-approve

Admin bisa mencocokkan data di modul Daftar Tamu untuk tindak lanjut.

---

### 5.7 Admin / Koordinator — Mengelola Reopen Request

#### Via Dashboard (`/hospitality/admin`)

```
1. Scroll ke panel "Permintaan Reopen Hospitality"
2. Filter berdasarkan status: pending / approved / rejected
3. Lihat detail: sekolah, staff pengaju, alasan, waktu pengajuan
4. Isi catatan admin (opsional)
5. Klik "Setujui" atau "Tolak"
```

#### Via Halaman Khusus (`/hospitality/admin/reopen-requests`)

```
1. Klik menu "Reopen" di navbar hospitality
   atau tombol "Permintaan Reopen" di Aksi Cepat
2. Tampil seluruh reopen request + filter status
3. Proses setiap request
```

#### Efek Persetujuan Reopen
- Status penilaian berubah → `reopened`
- Staff dapat memilih transaksi Buku Tamu `approved` lain untuk verifikasi ulang
- Notifikasi ke staff dan semua akun sekolah terkait
- Status reopen request → `approved`

#### Efek Penolakan Reopen
- Status penilaian **tidak berubah**
- Notifikasi penolakan ke staff dan sekolah
- Staff penilai bisa mengajukan reopen baru jika diperlukan

---

## 6. Alur Reopen (Buka Ulang Penilaian)

Reopen diperlukan jika penilaian perlu diverifikasi ulang — misalnya terhubung ke transaksi Buku Tamu yang salah, atau ada keberatan dari pihak sekolah.

### Kapan Reopen Diperlukan?

- Penilaian terhubung ke transaksi Buku Tamu yang salah → perlu diganti
- Sekolah mengajukan keberatan atas hasil penilaian
- Ada kesalahan data dan perlu koreksi

### Diagram Alur

```
Staff / Sekolah                   Sistem                        Admin
      │                              │                              │
      │── Isi alasan (opsional) ────►│                              │
      │   POST /assessment/<id>/     │                              │
      │        reopen                │── Buat reopen_request ──────►│
      │                              │   (status: pending)          │
      │◄── Notif: "Sedang            │◄── Notif: ada request ───────│
      │    ditinjau admin"           │    baru (in-app + Telegram)  │
      │                              │                              │
      │  [tombol ajukan di-disable   │                    Admin buka
      │   selama masih pending]      │             /admin/reopen-requests
      │                              │                              │
      │                              │                    Isi catatan (opsional)
      │                              │                    Klik Setujui / Tolak
      │                              │◄── approve / reject ─────────│
      │                              │                              │
      │◄── Notif: hasil keputusan ───│                              │
      │    (in-app + email)          │                              │
      │                              │                              │
  [Jika disetujui]                   │                              │
      │                              │                              │
      │── Pilih transaksi Buku Tamu ►│                              │
      │   (harus approved)           │                              │
      │── Klik Hubungkan            ►│── status → verified ─────────►
```

### Status Reopen Request

| Status | Deskripsi |
|--------|-----------|
| `pending` | Menunggu keputusan admin/koordinator |
| `approved` | Disetujui; penilaian berubah ke status `reopened` |
| `rejected` | Ditolak; penilaian tidak berubah |

### Aturan Reopen

- Hanya boleh ada **satu** reopen request `pending` per penilaian dalam satu waktu
- Selama ada `pending`, tombol "Ajukan ke Admin" di-disable
- Reopen hanya bisa diajukan pada penilaian berstatus `submitted` atau `verified`
- Setelah reopen disetujui, staff tetap harus memilih transaksi Buku Tamu `approved` untuk verifikasi ulang

---

## 7. Sistem Notifikasi

| Event | Penerima | Channel |
|-------|----------|---------|
| Penilaian terverifikasi (buku tamu berhasil dihubungkan) | Semua akun sekolah terkait + staff penilai | In-app + Email |
| Komentar baru ditambahkan | Semua akun sekolah + staff penilai | In-app |
| Reopen request dibuat | Semua admin | In-app + Telegram |
| Reopen disetujui | Staff penilai + semua akun sekolah | In-app + Email |
| Reopen ditolak | Staff penilai + semua akun sekolah | In-app + Email |

### Channel Notifikasi
- **In-app**: Badge merah di ikon lonceng navbar, klik untuk melihat daftar
- **Email**: Dikirim ke email terdaftar pengguna
- **Telegram**: Dikirim ke grup/channel admin yang dikonfigurasi di sistem

---

## 8. Referensi URL & Route

### Navigasi Otomatis
| URL | Deskripsi |
|-----|-----------|
| `GET /hospitality/` | Redirect otomatis sesuai role yang sedang login |

### Staff Routes
| Method | URL | Deskripsi |
|--------|-----|-----------|
| `GET` | `/hospitality/staff` | Daftar penilaian milik staff + filter/search |
| `GET` | `/hospitality/staff/assess/<school_id>` | Form penilaian sekolah |
| `POST` | `/hospitality/staff/assess/<school_id>` | Submit penilaian baru |

### Assessment Routes (Semua Role)
| Method | URL | Deskripsi |
|--------|-----|-----------|
| `GET` | `/hospitality/assessment/<id>` | Detail penilaian |
| `POST` | `/hospitality/assessment/<id>/link-guestbook` | Hubungkan transaksi Buku Tamu (approved) & verifikasi |
| `POST` | `/hospitality/assessment/<id>/comment` | Tambah komentar |
| `POST` | `/hospitality/assessment/<id>/reopen` | Ajukan permintaan reopen |

### Sekolah Routes
| Method | URL | Deskripsi |
|--------|-----|-----------|
| `GET` | `/hospitality/sekolah` | Daftar penilaian sekolah sendiri |

### Admin / Koordinator Routes
| Method | URL | Deskripsi |
|--------|-----|-----------|
| `GET` | `/hospitality/admin` | Dashboard utama + statistik |
| `GET` | `/hospitality/admin/reopen-requests` | Daftar semua reopen request |
| `POST` | `/hospitality/admin/reopen/<id>/approve` | Setujui reopen request |
| `POST` | `/hospitality/admin/reopen/<id>/reject` | Tolak reopen request |
| `GET` | `/hospitality/admin/export` | Download data penilaian sebagai CSV |
| `GET` | `/hospitality/admin/setup` | Halaman konfigurasi komponen & aspek |

### Admin Setup Routes — Komponen
| Method | URL | Deskripsi |
|--------|-----|-----------|
| `POST` | `/hospitality/admin/setup/component` | Buat komponen baru |
| `POST` | `/hospitality/admin/setup/component/<id>` | Update komponen |
| `POST` | `/hospitality/admin/setup/component/<id>/delete` | Hapus komponen |
| `POST` | `/hospitality/admin/setup/component/<id>/toggle-active` | Aktifkan / nonaktifkan |
| `POST` | `/hospitality/admin/setup/component/<id>/toggle-required` | Ubah status wajib |
| `POST` | `/hospitality/admin/setup/components/reorder` | Ubah urutan (JSON: `{"ids":[...]}`) |

### Admin Setup Routes — Aspek
| Method | URL | Deskripsi |
|--------|-----|-----------|
| `POST` | `/hospitality/admin/setup/aspect` | Buat aspek baru |
| `POST` | `/hospitality/admin/setup/aspect/<id>` | Update aspek |
| `POST` | `/hospitality/admin/setup/aspect/<id>/delete` | Hapus aspek |
| `POST` | `/hospitality/admin/setup/aspect/<id>/toggle-active` | Aktifkan / nonaktifkan |
| `POST` | `/hospitality/admin/setup/aspect/<id>/toggle-required` | Ubah status wajib |
| `POST` | `/hospitality/admin/setup/aspects/reorder` | Ubah urutan (JSON: `{"ids":[...]}`) |

---

## 9. Skema Basis Data

### Tabel Utama

#### `hospitality_assessments`
Tabel inti setiap record penilaian.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | serial PK | ID unik penilaian |
| `school_id` | integer FK | Referensi ke `portal_schools.id` |
| `staff_id` | integer FK | Referensi ke `dashboard_users.id` (staff penilai) |
| `status` | varchar | `draft` / `submitted` / `verified` / `reopened` |
| `score_scale_max` | integer | Nilai maksimal skala skor (default: `5`) |
| `note_text` | text | Catatan umum penilaian (opsional) |
| `submitted_at` | timestamptz | Waktu submit penilaian |
| `verified_at` | timestamptz | Waktu verifikasi selesai (setelah Buku Tamu di-link) |
| `created_at` | timestamptz | Waktu record dibuat |
| `updated_at` | timestamptz | Waktu record terakhir diubah |

#### `hospitality_assessment_scores`
Skor individual per aspek dalam setiap penilaian.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | serial PK | — |
| `assessment_id` | integer FK | Referensi ke `hospitality_assessments.id` |
| `component_id` | integer FK | Referensi ke `hospitality_components.id` |
| `aspect_id` | integer FK | Referensi ke `hospitality_aspects.id` |
| `score` | integer | Nilai skor (1–5) |
| `note` | text | Catatan per aspek (opsional) |
| `updated_at` | timestamptz | — |

> **Constraint**: `UNIQUE (assessment_id, aspect_id)` — satu aspek hanya boleh punya satu skor per penilaian. Upsert menggunakan `ON CONFLICT DO UPDATE`.

#### `hospitality_components`
Master data komponen penilaian (dikonfigurasi oleh admin).

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | serial PK | — |
| `name` | varchar | Nama komponen (mis. "Kebersihan") |
| `description` | text | Deskripsi komponen (opsional) |
| `sort_order` | integer | Urutan tampil di form |
| `active` | boolean | Apakah komponen aktif (tampil di form staff) |
| `is_required` | boolean | Apakah wajib diisi |

#### `hospitality_aspects`
Master data aspek per komponen.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | serial PK | — |
| `component_id` | integer FK | Referensi ke `hospitality_components.id` |
| `name` | varchar | Nama aspek (mis. "Kebersihan Halaman") |
| `description` | text | Deskripsi aspek (opsional) |
| `sort_order` | integer | Urutan tampil di dalam komponen |
| `active` | boolean | Apakah aspek aktif |
| `is_required` | boolean | Apakah wajib diisi |

#### `hospitality_assessment_guestbook_links`
Penghubung antara penilaian dengan transaksi Buku Tamu yang sudah `approved`.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `assessment_id` | integer PK/FK | Referensi ke `hospitality_assessments.id` |
| `transaction_id` | integer FK | Referensi ke `daftar_tamu_transactions.id` (wajib `approved`) |
| `linked_by` | integer FK | User ID yang menghubungkan |
| `linked_at` | timestamptz | Waktu penghubungan |

> **Constraint**: `UNIQUE (assessment_id)` — satu penilaian hanya bisa terhubung ke satu transaksi.
> **Validasi**: Sistem menolak jika `daftar_tamu_transactions.status != 'approved'` saat eksekusi.

#### `hospitality_assessment_comments`
Komentar pada penilaian (semua role, mendukung threading).

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | serial PK | — |
| `assessment_id` | integer FK | Referensi ke `hospitality_assessments.id` |
| `author_user_id` | integer FK | Referensi ke `dashboard_users.id` |
| `author_role` | varchar | Role saat komentar dibuat |
| `message` | text | Isi komentar |
| `parent_comment_id` | integer | Untuk threading (opsional) |
| `created_at` | timestamptz | — |

#### `hospitality_reopen_requests`
Permintaan untuk membuka ulang penilaian.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | serial PK | — |
| `assessment_id` | integer FK | Referensi ke `hospitality_assessments.id` |
| `staff_id` | integer FK | User yang mengajukan |
| `reason` | text | Alasan reopen (opsional) |
| `status` | varchar | `pending` / `approved` / `rejected` |
| `reviewer_id` | integer FK | Admin yang memproses (nullable) |
| `reviewer_note` | text | Catatan dari admin (nullable) |
| `reviewed_at` | timestamptz | Waktu diproses admin |
| `created_at` | timestamptz | Waktu pengajuan |

### Relasi Antar Tabel

```
portal_schools ──────────────────────────────┐
                                             │ school_id
dashboard_users (staff) ─────────────────────┤ staff_id
                                             ▼
                                  hospitality_assessments
                                 /          │            \
                      assessment_id    assessment_id    assessment_id
                            │               │                │
                            ▼               ▼                ▼
              hospitality_           hospitality_       hospitality_
              assessment_scores      assessment_        reopen_
              (component_id,         guestbook_links    requests
               aspect_id,            (transaction_id
               score, note)           ──► daftar_tamu_
                    │                      transactions,
                    │                      status=approved)
                    ├──► hospitality_components
                    └──► hospitality_aspects

hospitality_assessments
        │
  assessment_id
        │
        ▼
hospitality_assessment_comments
```

---

## 10. Konfigurasi Komponen & Aspek

Admin mengatur komponen dan aspek penilaian melalui `/hospitality/admin/setup`.

### Struktur Halaman Setup

**Panel Kiri (Sticky Form):**
- Tab **Komponen**: form tambah komponen baru (nama, deskripsi, urutan, status wajib)
- Tab **Aspek**: form tambah aspek baru (pilih komponen induk, nama, deskripsi, urutan, status wajib)

**Panel Kanan (Tabel Scrollable):**
- Daftar semua komponen beserta jumlah aspeknya
- Setiap baris bisa di-expand untuk melihat daftar aspek dan form edit
- Tombol per komponen: toggle aktif, toggle wajib, edit inline, hapus
- Pencarian real-time

### Aturan Penghapusan

- **Komponen**: Jika sudah digunakan dalam penilaian, hanya bisa di-nonaktifkan, tidak bisa dihapus
- **Aspek**: Jika sudah ada di `hospitality_assessment_scores`, hanya bisa di-nonaktifkan (`active = FALSE`), tidak dihapus dari database

### Pengurutan (via API JSON)

```
POST /hospitality/admin/setup/components/reorder  →  body: { "ids": [3, 1, 2] }
POST /hospitality/admin/setup/aspects/reorder     →  body: { "ids": [5, 7, 6] }
```

### Pengaruh Aktif/Nonaktif terhadap Form Staff

| Kondisi | Pengaruh pada Form Penilaian |
|---------|------------------------------|
| Komponen `active = FALSE` | Seluruh komponen & aspeknya tidak tampil |
| Aspek `active = FALSE` | Aspek tersebut tidak tampil; komponen tetap ada jika punya aspek aktif lain |
| Komponen aktif tapi semua aspeknya nonaktif | Komponen tidak tampil (tidak ada yang bisa dinilai) |

---

## 11. Export Data CSV

```
GET /hospitality/admin/export
```

### Kolom yang Di-export

| Kolom | Sumber |
|-------|--------|
| `assessment_id` | `hospitality_assessments.id` |
| `school_name` | `portal_schools.name` |
| `npsn` | `portal_schools.npsn` |
| `jenjang` | `portal_schools.jenjang` |
| `staff_name` | `dashboard_users.full_name` |
| `status` | `hospitality_assessments.status` |
| `created_at` | Tanggal penilaian dibuat (WIB) |
| `submitted_at` | Tanggal disubmit (WIB) |
| `verified_at` | Tanggal diverifikasi (WIB) — kosong jika belum ada buku tamu linked |
| `guestbook_transaction_id` | ID transaksi Buku Tamu — kosong jika belum diverifikasi |
| Per aspek (dinamis) | Skor tiap aspek sebagai kolom terpisah |

### Format Nama File
```
hospitality_export_YYYYMMDD_HHMMSS.csv
```

---

## 12. Aturan Bisnis Penting

### Penilaian Hospitality Tidak Membutuhkan Buku Tamu

```
staff_assess route → TIDAK ADA cek buku tamu sama sekali.
Penilaian bisa dibuat kapan saja, independen dari status buku tamu.
```

Buku Tamu `approved` hanya dibutuhkan di **satu titik**: saat `link_guestbook` (verifikasi).

### Batas Penilaian Harian

```
Maksimal 1 penilaian per staff per sekolah per hari (WIB).
```

Jika staff mencoba menilai sekolah yang sama di hari yang sama, sistem melempar `ValueError`:
> *"Sudah ada penilaian untuk sekolah ini hari ini oleh staff yang sama."*

### Transaksi Buku Tamu Wajib `approved` Saat Verifikasi

Sistem melakukan validasi ganda:
1. `list_guestbook_candidates` — query filter `AND t.status = 'approved'`
2. `link_guestbook_transaction` — cek ulang saat eksekusi, raise error jika bukan `approved`

### Skala Skor

- Nilai minimum: **1**
- Nilai maksimum: **5** (`HOSPITALITY_SCORE_MAX = 5`)
- Tidak ada nilai 0 — form default ke 1 untuk semua aspek
- Persentase: `(total_skor / (jumlah_aspek × 5)) × 100`

### Kategorisasi Skor

| Persentase | Predikat | Badge |
|-----------|----------|-------|
| ≥ 85% | Sangat Baik | Hijau (`bg-success`) |
| 70–84% | Baik | Kuning (`bg-warning`) |
| 55–69% | Kurang | Oranye (`bg-orange`) |
| < 55% | Kritis | Merah (`bg-danger`) |

### Prioritas Urutan Dropdown Transaksi Buku Tamu

Saat staff memilih transaksi, sistem mengurutkan:
1. Transaksi **hari yang sama** + **belum dipakai** *(prioritas tertinggi)*
2. Transaksi hari lain + belum dipakai
3. Transaksi yang sudah dipakai penilaian lain *(tampil tapi disabled)*

### Verifikasi Ganda Tidak Diizinkan

`UNIQUE (assessment_id)` di `hospitality_assessment_guestbook_links`. Jika link sudah ada, sistem menggunakan `ON CONFLICT DO UPDATE` untuk memperbarui (bukan duplikat).

### Reopen Request Ganda Tidak Diizinkan

Hanya satu reopen request `pending` per penilaian dalam satu waktu. Selama ada yang `pending`, tombol "Ajukan ke Admin" di-disable di UI.

---

## Lampiran: Diagram Alur Lengkap End-to-End

```
┌─────────────────────────────────────────────────────────────────────┐
│                   ALUR LENGKAP HOSPITALITY                          │
└─────────────────────────────────────────────────────────────────────┘

  TAHAP 0 — SETUP AWAL (sekali, atau saat ada perubahan)
  ┌─────────────────────────────────────────────────────────────────┐
  │  Admin buat Komponen (mis. Kebersihan, Keramahan, Fasilitas)    │
  │  Admin buat Aspek per Komponen                                  │
  │  Aktifkan komponen & aspek yang diinginkan                      │
  │  → /hospitality/admin/setup                                     │
  └─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                 ┌─────────────────┴──────────────────┐
                 │                                    │
         TRACK A — STAFF                     TRACK B — TAMU
         (bisa dilakukan kapan saja)         (bisa terjadi kapan saja)
  ┌──────────────────────────┐       ┌───────────────────────────────┐
  │  Staff buka              │       │  Tamu isi form Buku Tamu      │
  │  /hospitality/staff      │       │  → /buku-tamu/<kode_sekolah>  │
  │                          │       │  → status: pending            │
  │  Cari sekolah            │       │                               │
  │  → /staff/assess/<id>    │       │  Admin/Staff approve          │
  │                          │       │  di modul Daftar Tamu         │
  │  Isi skor (1–5) per      │       │  → status: approved  ◄─ WAJIB │
  │  komponen & aspek        │       │    sebelum verifikasi         │
  │                          │       │                               │
  │  Submit form             │       └───────────────┬───────────────┘
  │  → status: submitted     │                       │
  └───────────────┬──────────┘                       │
                  │                                  │
                  └──────────────┬───────────────────┘
                                 │
                                 ▼
  TAHAP VERIFIKASI — titik pertemuan Track A & Track B
  ┌─────────────────────────────────────────────────────────────────┐
  │  Staff buka detail penilaian /hospitality/assessment/<id>       │
  │  Pilih transaksi Buku Tamu (approved) dari dropdown             │
  │  Klik "Hubungkan & Verifikasi"                                  │
  │  → status penilaian: verified                                   │
  │  → Notifikasi ke sekolah, staff, admin Telegram                 │
  └─────────────────────────────────────────────────────────────────┘
                                 │
                   ┌─────────────┴──────────────┐
                   ▼                            ▼
          SEKOLAH MERESPONS            ADMIN MEMANTAU
          ┌──────────────────┐        ┌──────────────────────┐
          │ Lihat skor       │        │ Dashboard stats       │
          │ per komponen     │        │ Tren 30 hari          │
          │ Tambah komentar  │        │ Ranking sekolah       │
          │ Ajukan reopen    │        │ Galeri foto verified  │
          └────────┬─────────┘        │ Export CSV            │
                   │                  └──────────────────────┘
                   ▼ (jika reopen diajukan)
  TAHAP REOPEN — jika diperlukan
  ┌─────────────────────────────────────────────────────────────────┐
  │  Staff/Sekolah ajukan → status request: pending                 │
  │  Admin proses di /hospitality/admin/reopen-requests             │
  │  Jika disetujui: status penilaian → reopened                   │
  │  Staff pilih transaksi Buku Tamu approved (bisa yang berbeda)   │
  │  → Hubungkan → status kembali: verified                        │
  └─────────────────────────────────────────────────────────────────┘
```

---

*Dokumentasi ini dibuat berdasarkan source code versi aktif. Perbarui dokumen ini setiap kali ada perubahan pada alur, validasi, atau skema database.*
