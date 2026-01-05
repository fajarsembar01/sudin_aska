# Tutorial Portal ASKA (PANBERSS)

Dokumen ini berisi materi presentasi untuk alur penggunaan fitur Portal ASKA bagi tiga role utama: **Sekolah**, **Staff/Penilai**, dan **Admin**.

---

## Slide 1: Pendahuluan
**Judul:** Tutorial Penggunaan Portal ASKA (PANBERSS)  
**Subtitle:** Panduan Lengkap untuk Sekolah, Staff Penilai, dan Administrator  
**Poin Utama:**
- Pendaftaran & Konfigurasi Sekolah
- Penilaian Aset & Fasilitas oleh Staff
- Monitoring & Perencanaan oleh Admin

---

## Slide 2: Role Sekolah - Pendaftaran Akun
**Tujuan:** Sekolah mendaftarkan akun baru untuk mengakses portal.

**Langkah-langkah:**
1. Buka URL: `http://127.0.0.1:5002/portal/register`
2. **Pilih Sekolah:** Ketik NPSN atau Nama Sekolah (Contoh: `20100677` / SDN ROROTAN 01).
3. **Isi Kredensial:** Masukkan Email (misal: `sekolah_demo@test.com`) dan Password.
4. Klik **Daftar**.

**Ilustrasi:**
![Halaman Pendaftaran](/Users/ainunfajar/SUDIN_ASKA/ai-agent-sekolah/tutorial_ppt_materials/1_register_annotated.png)
*Gambar 1: Tampilan form registrasi pendaftaran akun sekolah*

---

## Slide 3: Role Sekolah - Login & Profil
**Tujuan:** Melengkapi data profil sekolah setelah login pertama kali.

**Langkah-langkah:**
1. Login menggunakan email & password yang baru didaftarkan.
2. Sistem akan menampilkan **Modal Lengkapi Profil**.
3. Isi data penting: Alamat, Titik Gmaps, Jumlah Siswa, dan Kontak Sekolah.
4. Klik **Simpan** untuk melanjutkan.

**Ilustrasi:**
![Modal Profil](/Users/ainunfajar/.gemini/antigravity/brain/b81885be-96f4-4e1d-b83a-597219007532/3b_after_next_click_1765961643622.png)
*Gambar 2: Tampilan modal pengisian data kapasitas sekolah*

---

## Slide 4: Role Sekolah - Konfigurasi Ruangan
**Tujuan:** Menentukan ruangan apa saja yang dimiliki sekolah untuk dinilai.

**Langkah-langkah:**
1. Masuk ke menu **Data Ruangan** (`/portal/sekolah/rooms`).
2. Centang daftar ruangan yang tersedia di sekolah (Contoh: Ruang Kepala Sekolah, Ruang Guru, Ruang Kelas).
3. Klik **Simpan Konfigurasi**.

**Ilustrasi:**
![Konfigurasi Ruangan](/Users/ainunfajar/.gemini/antigravity/brain/b81885be-96f4-4e1d-b83a-597219007532/5_rooms_configured_1765961796091.png)
*Gambar 3: Daftar checkbox ruangan yang telah dipilih*

---

## Slide 5: Role Staff - Login
**Tujuan:** Masuk sebagai staff untuk memulai tugas penilaian.

**User Demo:** `admin@sudindikju2.com` (Role Admin/Staff)

**Langkah-langkah:**
1. Buka halaman Login.
2. Masukkan Email & Password Staff.
3. Klik tombol Masuk.

**Ilustrasi:**
![Login Staff](/Users/ainunfajar/SUDIN_ASKA/ai-agent-sekolah/tutorial_ppt_materials/2_login_annotated.png)
*Gambar 4: Halaman login staff dengan petunjuk pengisian*

---

## Slide 6: Role Staff - Pencarian Sekolah
**Tujuan:** Menemukan sekolah target yang akan dinilai.

**Langkah-langkah:**
1. Pilih menu **Daftar Sekolah**.
2. Ketik nama sekolah atau NPSN pada kolom pencarian (Contoh: 20100677).
3. Klik tombol **Nilai** pada daftar yang muncul.

**Ilustrasi:**
![Pencarian Sekolah](/Users/ainunfajar/SUDIN_ASKA/ai-agent-sekolah/tutorial_ppt_materials/7_school_search.png)
*Gambar 5: Hasil pencarian sekolah pada menu staff*

---

## Slide 7: Role Staff - Input Penilaian
**Tujuan:** Memberikan skor dan bukti foto kondisi ruangan.

**Langkah-langkah:**
1. **Pilih Ruangan:** Klik header ruangan (misal: Pintu Gerbang) untuk membuka detailnya.
2. **Beri Nilai:** Tentukan skor (0-3) untuk setiap aspek (Cat, Kondisi, dll).
3. **Upload Foto:** Klik tombol **Ambil Foto Ruangan**.
4. **Isi Keterangan:** Tambahkan catatan jika diperlukan.
5. **Submit:** Klik **Submit Penilaian**.

**Ilustrasi:**
![Halaman Penilaian](/Users/ainunfajar/SUDIN_ASKA/ai-agent-sekolah/tutorial_ppt_materials/8_assessment_annotated.png)
*Gambar 6: Form penilaian lengkap dengan 5 langkah (Pilih Ruangan s/d Submit)*

---

## Slide 8: Role Admin - Dashboard Monitoring
**Tujuan:** Memantau progres penilaian seluruh wilayah.

**Fitur:**
- Statistik total penilaian (Draft vs Submitted).
- Peta sebaran skor (Hijau/Kuning/Merah).
- Grafik performa per kecamatan.

**Ilustrasi:**
![Admin Stats](/Users/ainunfajar/.gemini/antigravity/brain/b81885be-96f4-4e1d-b83a-597219007532/11_admin_stats_1765962092358.png)
*Gambar 7: Dashboard statistik monitoring admin*

---

## Slide 9: Role Admin - AI Sidak Planner
**Tujuan:** Merencanakan rute kunjungan prioritas berbasis data.

**Fitur:**
- Rekomendasi sekolah dengan nilai rendah (prioritas sidak).
- Optimasi rute kunjungan paling efisien.

**Ilustrasi:**
![AI Sidak Planner](/Users/ainunfajar/SUDIN_ASKA/ai-agent-sekolah/tutorial_ppt_materials/12_admin_sidak.png)
*Gambar 8: Halaman perencanaan sidak berbasis AI*

---

## Slide 10: Role Admin - Master Data Setup
**Tujuan:** Mengelola referensi sistem.

**Fitur:**
- Tambah/Edit Master Ruangan.
- Tambah/Edit Aspek Penilaian.
- Manajemen Data Referensi Sekolah.

**Ilustrasi:**
![Admin Setup](/Users/ainunfajar/.gemini/antigravity/brain/b81885be-96f4-4e1d-b83a-597219007532/13_admin_setup_1765962098799.png)
*Gambar 9: Halaman pengaturan master data*

---

## Penutup
**Selesai.**
Tutorial ini mencakup seluruh siklus penggunaan Portal ASKA dari registrasi sekolah, penilaian lapangan, hingga monitoring eksekutif.
