# Rollout Checklist Review Buku Tamu Hospitality

Checklist ini dipakai saat deploy fitur review pelayanan QR buku tamu ke environment server.

## 1. Pra-deploy

- Pastikan branch deploy sudah memuat perubahan di `web_aska`, `dashboard/hospitality`, `db.py`, dan `dashboard/schema.py`.
- Pastikan backup database terbaru tersedia.
- Pastikan folder upload portal tetap tersedia dan permission baca-tulis tidak berubah.

## 2. Migrasi Database

- Jalankan migration `dashboard/migrations/028_add_hospitality_guestbook_reviews.sql`.
- Verifikasi tabel `hospitality_guestbook_reviews` berhasil dibuat.
- Verifikasi index berikut tersedia:
  - `uq_hosp_guestbook_reviews_transaction`
  - `idx_hosp_guestbook_reviews_school`
  - `idx_hosp_guestbook_reviews_status`
  - `idx_hosp_guestbook_reviews_completed_at`

## 3. Restart Service

- Restart service `web_aska`.
- Restart service dashboard / portal.
- Bila memakai gunicorn atau supervisor, pastikan worker lama benar-benar berhenti.

## 4. Verifikasi Alur QR

- Buka QR buku tamu sekolah aktif.
- Isi buku tamu umum minimal 1 tamu.
- Pastikan submit buku tamu redirect ke route review:
  - `/buku-tamu/<npsn>/review/<review_token>`
- Pastikan transaksi buku tamu sudah tersimpan walau halaman review belum disubmit.
- Submit rating 1-5 dan komentar opsional.
- Pastikan redirect ke:
  - `/buku-tamu/<npsn>/selesai?tx=<id>`
- Pastikan chat ASKA aktif hanya setelah review selesai.

## 5. Verifikasi Dashboard

- Login sebagai admin/koordinator.
- Buka `/hospitality/admin`.
- Buka `/hospitality/guestbook-reviews`.
- Pastikan statistik, tabel review, detail review, dan export CSV berjalan.
- Login sebagai sekolah yang memiliki data review.
- Pastikan `/hospitality/guestbook-reviews` otomatis scoped ke sekolah sendiri.
- Pastikan sekolah tidak melihat filter semua sekolah.

## 6. Verifikasi Data

- Pastikan 1 transaksi buku tamu umum menghasilkan 1 row di `hospitality_guestbook_reviews`.
- Pastikan status awal review adalah `pending`.
- Pastikan setelah submit review, status berubah menjadi `completed`.
- Pastikan `rating`, `comment`, dan `completed_at` terisi sesuai input.

## 7. Monitoring Pasca Deploy

- Pantau log `web_aska` untuk route:
  - `/buku-tamu/<npsn>`
  - `/buku-tamu/<npsn>/review/<token>`
  - `/api/guest-chat`
- Pantau log dashboard untuk route:
  - `/hospitality/admin`
  - `/hospitality/guestbook-reviews`
  - `/hospitality/guestbook-reviews/export`
- Pastikan tidak ada lonjakan `500`, `403`, atau `404` asset di halaman hospitality.

## 8. Smoke Test Cepat Pasca Deploy

- Submit 1 transaksi buku tamu umum.
- Submit 1 review bintang.
- Kirim 1 chat ASKA dari halaman selesai.
- Buka dashboard admin dan pastikan review baru muncul.
- Export CSV dan cek header kolom.
