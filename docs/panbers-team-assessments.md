# Penilaian Tim Panberss

Menu Panberss dan Monev BOS/BOP tetap terpisah. Tim Panberss menggunakan susunan
anggota dan sekolah yang sudah ditugaskan di Monev.

## Penggunaan

1. Admin cukup membuat tim dan menugaskan sekolah di **Monev BOS/BOP** seperti biasa.
   Tim, anggota, dan sekolah otomatis tersedia di Panberss tanpa aktivasi kedua.
2. Jika ada sekolah yang tidak boleh menggunakan mode Tim Panberss, admin membuka
   **Pengecualian sekolah** dan menonaktifkannya. Halaman ini opsional; penugasan
   Individu tetap tersedia.
3. Anggota memilih **Panberss** di OSS, lalu memilih **Penilaian Tim** atau
   **Penilaian Individu**. Mode Tim membuka sekolah tim; Individu membuka tugas
   pribadi. Tautan langsung ke daftar/draft tetap dapat dipakai.
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

- Tanpa pengaturan tambahan, sekolah otomatis tersedia. Hanya pengecualian yang
  dinonaktifkan perlu disimpan; mengaktifkan kembali mengembalikan perilaku otomatis.
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

## Performa staff

Menu **Performa Staff** tersedia di `/portal/staff/performance`. Mode Gabungan,
Tim, dan Individu dapat difilter menurut tanggal aktivitas WIB serta periode
penilaian. Draft tanpa periode hanya muncul saat memilih semua periode.

Perubahan skor, catatan, unggah/hapus foto, simpan draft, dan kirim final dicatat
atas nama akun pelaku. Penyimpanan skor/catatan yang nilainya sama tidak membuat
event baru. Aspek, catatan, dan foto dihitung unik per penilaian/ruangan/isian
untuk setiap pelaku; pengiriman dihitung unik per penilaian dan akun pengirim.
Tidak memberikan kredit otomatis kepada seluruh anggota tim.

Staff dapat melihat rincian aktivitas dirinya sendiri dan ringkasan kontribusi
staff lain; admin dapat memilih rincian akun lain. Riwayat dibatasi 100 event
terbaru, sedangkan ringkasan menghitung seluruh event pada filter. Data lama
yang belum merekam pelaku tidak direkonstruksi. Event mengikuti penilaian dan
ikut terhapus jika admin menghapus penilaian tersebut; ini ringkasan pekerjaan
yang masih tersimpan, bukan arsip audit penghapusan yang permanen.

## Validasi

Migrasi: `dashboard/migrations/061_panbers_team_assessments.sql` (idempoten), juga
tercakup pada inisialisasi schema aplikasi. Migrasi
`062_auto_panbers_monev_assignments.sql` menetapkan default otomatis aktif.

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
