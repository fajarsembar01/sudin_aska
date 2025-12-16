# Roadmap Pengembangan Portal PANBERSS
*Dokumen Perencanaan Fitur & Pengembangan Jangka Panjang*

Status: **Draft**
Last Updated: 2024 (Simulated)

Dokumen ini merinci rencana pengembangan aplikasi portal penilaian sekolah (PANBERSS) untuk meningkatkan efektivitas monitoring, efisiensi kerja staff, dan akuntabilitas data.

---

## 1. Smart Sidak Planner 2.0 (AI-Powered)

### Latar Belakang
Saat ini, fitur "Sidak Planner" hanya menggunakan algoritma *Nearest Neighbor* sederhana berdasarkan lokasi geografis. Ini belum mempertimbangkan urgensi inspeksi berdasarkan riwayat data.

### Solusi Fitur
Mengembangkan sistem rekomendasi rute yang cerdas (Intelligent Route Planning) yang menggabungkan faktor lokasi dan faktor risiko.

#### Spesifikasi Fungsional
1.  **Risk-Based Prioritization**:
    *   Setiap sekolah memiliki "Risk Score" yang dihitung otomatis setiap hari.
    *   Rumus Risk Score: `(Hari sejak kunjungan terakhir * 0.3) + (100 - Skor Terakhir * 0.5) + (Jumlah Laporan Warga * 0.2)`.
    *   Sekolah dengan Risk Score tinggi akan otomatis muncul sebagai prioritas di sidak planner.
2.  **Multi-Staff Clustering**:
    *   Jika ada 5 staff yang turun lapangan, sistem otomatis membagi Jakarta Utara menjadi 5 kluster optimal agar tidak ada tumpang tindih rute.
3.  **Calendar Integration**:
    *   Tombol "Add to Calendar" yang mengirim jadwal rute ke Google Calendar staff, lengkap dengan link rute Google Maps.

#### Implementasi Teknis
*   **Algoritma**: K-Means Clustering untuk pembagian zona staff, Weighted Graph untuk penentuan urutan kunjungan.
*   **Library**: `scikit-learn` (untuk clustering), `networkx` (untuk graph), `google-api-python-client` (untuk Calendar API).
*   **Database**: Tabel baru `school_risk_scores` untuk menyimpan histori risiko.

---

## 2. Visual AI Inspector (Computer Vision)

### Latar Belakang
Penilaian saat ini 100% manual. Staff sering bingung menentukan apakah kondisi ruangan masuk kategori "Rusak Ringan" atau "Rusak Sedang", menyebabkan data tidak konsisten antar penilai.

### Solusi Fitur
Mengintegrasikan AI untuk membantu standarisasi penilaian melalui analisis foto.

#### Spesifikasi Fungsional
1.  **Foto First Assessment**:
    *   UI diubah: Ambil foto dulu -> AI menganalisis -> AI menyarankan Skor & Tag -> Staff mengkonfirmasi/edit.
2.  **Defect Detection**:
    *   Mendeteksi objek spesifik: keramik pecah, plafon bocor, dinding berjamur, kursi rusak.
3.  **Auto-Captioning**:
    *   "Terdeteksi plafon berlubang di sudut kiri atas" (disimpan sebagai notes otomatis).

#### Implementasi Teknis
*   **Model Service**: Integrasi dengan Google Gemini Vision API atau OpenAI GPT-4 Vision.
*   **Flow**:
    1.  User upload foto ke endpoint `/api/analyze-image`.
    2.  Server kirim resize image ke AI Service dengan prompt instruksi standar penilaian per sarpras.
    3.  Response JSON (skor, tags, reasoning) dikembalikan ke frontend.

---

## 3. Mode Offline & PWA (Progressive Web App)

### Latar Belakang
Banyak ruangan sekolah (terutama gudang, basement, atau area belakang) memiliki sinyal seluler yang buruk. Staff sering mengalami kegagalan upload foto saat sedang inspeksi.

### Solusi Fitur
Mengubah aplikasi web menjadi PWA *Offline-First*.

#### Spesifikasi Fungsional
1.  **Offline Draft**:
    *   Staff bisa membuka form penilaian, mengisi skor, dan mengambil foto tanpa koneksi internet.
    *   Data disimpan di `IndexedDB` browser lokal.
2.  **Background Sync**:
    *   Saat sinyal kembali stabil, aplikasi otomatis mengupload antrian data di background.
3.  **Installable**:
    *   Aplikasi bisa di-"install" ke Homescreen HP tanpa masuk App Store/Play Store (Fitur standar PWA).

#### Implementasi Teknis
*   **Service Workers**: Untuk caching app shell (HTML/CSS/JS) agar bisa dibuka offline.
*   **Local Storage**: Menggunakan library `idb` atau `localforage` untuk `IndexedDB` wrapper.
*   **Sync Logic**: Queue manager di Javascript untuk menangani retry logic saat upload gagal.

---

## 4. Siklus "Tindak Lanjut" (Closed Loop Feedback)

### Latar Belakang
Saat ini sistem hanya bersifat "Satu Arah" (Admin menilai -> Selesai). Tidak ada mekanisme sistematis bagi sekolah untuk melaporkan perbaikan, sehingga data di dashboard bisa jadi "basi" (sekolah sudah memperbaiki tapi status masih merah).

### Solusi Fitur
Mekanisme tiket/isu yang memungkinkan komunikasi dua arah.

#### Spesifikasi Fungsional
1.  **Ticket System**:
    *   Jika nilai aspek < 60 (Kurang), otomatis terbuat "Tiket Temuan".
2.  **Portal Sekolah - Tindak Lanjut**:
    *   Sekolah login -> melihat daftar Tiket Temuan.
    *   Sekolah melakukan perbaikan -> Upload foto bukti ("After").
    *   Status berubah menjadi "Menunggu Verifikasi Verifikator".
3.  **Verifikasi**:
    *   Admin/Staff melihat bukti perbaikan -> Klik "Approve" -> Skor otomatis terupdate atau Tiket ditutup.

#### Implementasi Teknis
*   **Database**: Tabel `assessment_issues` dan `issue_resolutions`.
*   **Notifikasi**: Email/WhatsApp notifikasi ke sekolah saat ada temuan baru, dan ke admin saat ada laporan perbaikan.

---

## 5. Gamification & Public Dashboard

### Latar Belakang
Perlu insentif psikologis agar sekolah berlomba-lomba menjaga kebersihan, tidak hanya karena takut disidak.

### Solusi Fitur
Membangun dashboard publik dan sistem penghargaan (gamifikasi).

#### Spesifikasi Fungsional
1.  **Leaderboards**:
    *   "Top 5 Sekolah Terbersih Minggu Ini"
    *   "Top 3 Sekolah Paling Improvisasi" (Kenaikan skor tertinggi).
2.  **Badges & Levels**:
    *   Sekolah mendapat badge digital (misal: "Green Flag", "Clean Canteen Award") yang bisa dipajang di profil mereka.
3.  **Kecamatan Battle**:
    *   Grafik rata-rata skor per kecamatan untuk memicu kompetisi sehat antar wilayah (Camat vs Camat).

---

## 6. Laporan Eksekutif Otomatis (PDF Generator)

### Latar Belakang
Admin sering diminta laporan manual oleh pimpinan (Kasudin/Walikota) yang memakan waktu untuk rekap data Excel dan copy-paste foto.

### Solusi Fitur
Generator laporan PDF satu klik yang siap cetak/kirim.

#### Spesifikasi Fungsional
1.  **Template Laporan**:
    *   Halaman 1: Executive Summary (Grafik tren, ringkasan angka).
    *   Halaman 2: Peta Sebaran Heatmap.
    *   Halaman 3dst: Detail temuan mayor (Foto *Before/After* jika ada).
2.  **Custom Filter**:
    *   "Generate Laporan Kecamatan Cilincing - Periode November 2024".

#### Implementasi Teknis
*   **Library**: `WeasyPrint` (HTML to PDF) atau `ReportLab`.
*   **Format**: Layout A4 profesional dengan header/kop surat resmi instansi.

---

## Matriks Prioritas

| Fitur | Dampak | Kompleksitas | Prioritas |
| :--- | :---: | :---: | :---: |
| **Offline Mode (PWA)** | Tinggi | Sedang | **P1 (Segera)** |
| **Smart Sidak Planner** | Sedang | Rendah | **P1 (Segera)** |
| **Laporan PDF** | Tinggi | Rendah | **P2** |
| **Siklus Tindak Lanjut** | Tinggi | Tinggi | **P2** |
| **Visual AI Inspector** | Sedang | Tinggi | **P3 (Eksperimental)** |
| **Gamification** | Rendah | Sedang | **P3** |

---

*Disimpan di `.agent` folder untuk referensi pengembangan masa depan.*
