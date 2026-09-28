# Register layanan staf

Akses melalui **Portal → Layanan** (`/layanan/`). Jenis register: ijazah,
SKPI, legalisasi, dan mutasi siswa. Nomor register dibuat otomatis; nomor surat
resmi tetap diisi petugas. Nomor ijazah dan NISN disimpan sebagai teks agar
nol awal tidak hilang. Data foto buku tidak diimpor otomatis.

NISN ditempatkan sebelum nama pemohon. Mulai tiga angka, pencarian menampilkan
maksimal sepuluh siswa dari catatan sebelumnya; satu hasil per NISN memakai
catatan yang terakhir diperbarui. Memilih hasil mengisi nama dan sekolah asal
yang masih ada di database. Jenis layanan, dokumen, tanggal, dan status tidak
disalin. Petugas dapat memeriksa atau memperbarui data pada catatan baru.
Endpoint `/layanan/siswa/cari` mengikuti izin Layanan dan respons tidak di-cache.
Kolom `nisn` terpisah dari kolom lama `student_number` yang berisi campuran
NIS/NISN; data lama tersebut dipertahankan tanpa menebak jenis nomornya.

Navigasi staf disederhanakan menjadi Beranda, Daftar Layanan, dan Laporan.
Beranda memprioritaskan pencatatan baru dan pencarian layanan lama. Formulir
memiliki empat bagian bernomor, petunjuk status, serta penanda isian opsional.
Filter tambahan pada daftar dibuka hanya saat diperlukan.

Alamat halaman:

- `/layanan/`: pilihan kegiatan, jumlah layanan belum selesai, dan catatan terbaru.
- `/layanan/register`: seluruh register dengan pencarian dan filter.
- `/layanan/register/<jenis>`: halaman ijazah, SKPI, legalisasi, atau mutasi.
- `/layanan/baru`: formulir pencatatan; tautan dari register memilih jenis otomatis.
- `/layanan/laporan`: rekap status per jenis, filter periode, cetak, dan ekspor data.

Navbar menyediakan menu Akses Staf bagi admin dan tombol kembali ke Portal OSS.
Alamat lama `/portal/layanan/...` dialihkan ke `/layanan/...` dengan HTTP 308,
termasuk parameter pencarian dan kiriman formulir.
Semua halaman tetap mengikuti izin Layanan. Rekap dihitung dari status terkini
catatan berdasarkan tanggal layanan, bukan riwayat perubahan status.

Sekolah asal dipilih dari `portal_schools`, dengan pencarian nama/NPSN.
ID sekolah disimpan bersama nama saat pencatatan sebagai arsip. Nama diambil
dari database dan divalidasi di server. Sekolah nonaktif tetap tersedia untuk
register historis. Isian manual tidak diperbolehkan; sekolah asal wajib dipilih
dari database. Saat mengubah catatan lama tanpa ID sekolah, petugas harus memilih
sekolah terdaftar sebelum menyimpan.

Admin memilih petugas melalui **OSS Admin → Pengaturan → Akun → Akses Layanan**.
Staf, pengawas, kasi, dan operator dengan akun disetujui harus diberi akses secara
eksplisit; daftar izin awal kosong. Admin selalu dapat mengakses register.
Pencabutan izin berlaku pada permintaan berikutnya, termasuk URL langsung dan
ekspor, tanpa menghapus catatan. Menu portal nonaktif bila tidak memiliki izin.
Hanya pembuat catatan atau admin yang dapat mengubahnya. Form menyimpan versi
catatan untuk mencegah penimpaan perubahan serentak. Status tersedia: Dicatat,
Diproses, Selesai, Diserahkan. Status Diserahkan memerlukan nama penerima dan
tanggal penyerahan; ini bukan tanda tangan elektronik.

Filter pencarian, jenis, status, dan rentang tanggal berlaku pada daftar dan
unduhan CSV. Detail dapat dicetak melalui tombol Cetak. CSV memakai UTF-8 BOM
serta menetralkan awalan formula. Saat mengimpor CSV ke spreadsheet, pilih tipe
teks untuk kolom nomor agar spreadsheet tidak menghapus nol awal.

Tabel disiapkan oleh startup aplikasi jika `ASKA_DASHBOARD_AUTO_INIT=1`.
Jika inisialisasi otomatis dimatikan, jalankan `schema.sql` pada database aplikasi
setelah tabel `dashboard_users` tersedia. Restart proses aplikasi setelah deploy.

Pengujian:

```sh
ASKA_DASHBOARD_AUTO_INIT=0 venv/bin/python -m unittest discover -s dashboard/layanan/tests -v
```
