# Penilaian Tim Panberss

Menu Panberss dan Monev BOS/BOP tetap terpisah. Tim Panberss menggunakan susunan
anggota dan sekolah yang sudah ditugaskan di Monev.

## Penggunaan

1. Admin membuka **Panberss → Penilaian Tim → Atur penugasan**, atau tautan
   **Gunakan penugasan untuk Panberss** di halaman Tim & Penugasan Monev.
2. Aktifkan mode Tim untuk sekolah yang diperlukan. Pencarian dan pilihan semua
   yang terlihat tersedia. Penugasan Individu tidak dihapus.
3. Anggota membuka **Panberss → Penilaian Tim** dan memilih sekolah.
4. Semua anggota menggunakan draft bersama. Nilai, catatan, foto, dan penanda
   anggota yang membuka ruangan diperbarui setiap 2 detik selama terhubung.
   Penanda tidak mengunci ruangan. Kehadiran tab kedaluwarsa setelah 45 detik.
5. Jika dua orang mengubah isian yang sama dari versi lama, penyimpanan ditolak.
   Pilihan lokal tetap tersedia untuk dibandingkan dengan versi tim. Pengguna
   memilih versi tim atau secara eksplisit menyimpan pilihannya kembali.
6. Setiap anggota dapat mengirim final. Periode Panberss aktif ditetapkan pada
   transaksi pengiriman, bukan saat membuka atau mengisi draft. Jika periode
   berubah sejak halaman dibuka, muat ulang dan periksa periode sebelum mengirim.
   Tanpa periode aktif, draft tetap aman dan pengiriman final ditahan.
7. Setelah final, mulai penilaian lagi untuk membuat hasil berikutnya. Individu
   dan Tim dapat memiliki beberapa hasil di sekolah/periode yang sama.

## Penugasan dan riwayat

- Penugasan efektif dipilih per sekolah dari periode Monev **aktif** terbaru,
  diurutkan berdasarkan tahun, triwulan, periode, lalu penugasan.
- Sekolah Monev dihubungkan ke sekolah Panberss melalui relasi akun sekolah
  (`dashboard_users.school_id`, atau `portal_schools.user_id`), bukan kesamaan nama.
- Pekerjaan berjalan mengikuti perubahan anggota/penugasan. Hasil final menyimpan
  salinan nama tim dan anggota; mantan anggota tetap dapat membaca hasil tersebut.
- Kontribusi pengisian dan pengiriman dicatat berdasarkan akun pelaku. Pengunggah
  foto menggunakan akun sebenarnya, bukan selalu pembuat draft.
- Hasil yang dibuka ulang tetap memakai periode dan identitas tim final asal.
  Reopen ditahan jika sekolah masih mempunyai draft tim lain. Penghapusan draft
  bersama hanya untuk admin.

## Statistik

Dashboard Panberss menyediakan filter **Gabungan**, **Individu**, dan **Tim**.
Filter diteruskan ke peta, distribusi nilai, peringkat, galeri, frekuensi, dan
Excel. Setiap hasil tim dihitung satu kali tanpa dikalikan jumlah anggota.
Rekap sekolah tetap menggunakan pola tampilan penilaian terbaru per sekolah;
jumlah/rekap agregat menghitung seluruh hasil yang masuk filter. Riwayat tim
menampilkan setiap hasil final secara terpisah.

## Validasi

Migrasi: `dashboard/migrations/061_panbers_team_assessments.sql` (idempoten), juga
tercakup pada inisialisasi schema aplikasi.

```sh
PANBERS_TEAM_DB_TEST=1 venv/bin/python -m unittest dashboard.tests.test_panbers_team
node --test dashboard/tests/test_panbers_team.js
```

Pengujian database membuat fixture dalam satu transaksi lalu selalu melakukan
rollback. Tidak mengubah penugasan atau hasil pengguna yang sudah tersimpan.

### Uji browser langsung — 18 November 2026

Diverifikasi melalui dua sesi Chrome yang terpisah (admin dan akun anggota uji):

- Nilai dan catatan dari satu akun muncul di akun lain tanpa memuat ulang.
- Penanda anggota yang sedang membuka ruangan terlihat pada akun lain.
- Dua perubahan pada aspek yang sama dari versi yang sama menghasilkan konflik;
  pilihan lokal dan versi tim ditampilkan, tanpa menimpa hasil yang lebih baru.
- Pengiriman final ditahan selama konflik belum diselesaikan.
- Memilih versi tim menyamakan kembali skor kedua sesi.
- Anggota staff berhasil mengirim final; editor di sesi admin otomatis terkunci.
- Data final memuat nilai, catatan, periode aktif, dan akun pengirim yang benar.

Sekolah, tim, akun, foto, serta hasil uji sementara telah dibersihkan. Tautan login
juga diperbaiki agar mempertahankan parameter mode Tim dan ID draft.
