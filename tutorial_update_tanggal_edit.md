# Tutorial Update Kolom `tanggal_edit` di Database Server

Tutorial ini menjelaskan langkah-langkah untuk mengaplikasikan perubahan struktur tabel (penambahan kolom) beserta sinkronisasi datanya ke dalam database server *production/staging* PostgreSQL.

## Persiapan
1. Pastikan Anda telah memiliki file `update_tanggal_edit.sql` yang berisikan perintah `ALTER TABLE` dan `UPDATE` (file ini sudah berhasil di-generate dari data lokal).
2. Pastikan Anda memiliki akses ke server database PostgreSQL (misalnya melalui pgAdmin, DBeaver, atau akses CLI `psql`).

---

## Langkah 1: Backup Database (Sangat Disarankan)
Sebelum mengeksekusi script modifikasi tabel, selalu lakukan *backup* atau *dump* terhadap database saat ini untuk mencegah hilangnya data apabila terjadi kesalahan.

Jika menggunakan `pg_dump`:
```bash
pg_dump -U username_database -h host_database nama_database > backup_db_sebelum_update.sql
```

---

## Langkah 2: Menjalankan File SQL

Anda bisa menggunakan salah satu dari dua cara di bawah ini untuk mengeksekusi file `.sql` tersebut ke server:

### Cara A: Menggunakan GUI (pgAdmin / DBeaver / DataGrip)
1. Buka aplikasi *Database Manager* Anda.
2. Konek ke server database yang dituju.
3. Buka Query Tool (atau SQL Editor) yang mengarah ke database `sudin_aska` (atau nama database aplikasi).
4. Buka isi file `update_tanggal_edit.sql` dengan *text editor*, lalu **copy** seluruh isinya.
5. **Paste** ke dalam Query Tool / SQL Editor.
6. Blok semua baris kode tersebut, lalu tekan **Run / Execute (F5)**.

### Cara B: Menggunakan CLI (psql)
Jika Anda login langsung ke server via SSH atau memiliki `psql` di terminal Anda, jalankan perintah berikut:

```bash
psql -U username_database -h host_database -d nama_database -f "path/menuju/update_tanggal_edit.sql"
```
*(Sesuaikan username, host, dan nama database server Anda)*

---

## Langkah 3: Verifikasi Hasil

Setelah script dijalankan, pastikan tidak ada *error* pada output atau log eksekusi. Untuk memastikan data sudah terupdate, jalankan query verifikasi berikut:

```sql
SELECT id, completed_at, created_at, tanggal_edit 
FROM hospitality_guestbook_reviews 
ORDER BY id DESC 
LIMIT 10;
```

**Pengecekan Sukses:**
- Kolom `tanggal_edit` harusnya sudah ada.
- Nilai `tanggal_edit` tidak boleh kosong (*NULL*) untuk baris yang merupakan data historis, nilainya harus sama persis dengan yang ada di lokal (sesuai isi query di file `.sql`).

---

## Selesai
Jika struktur kolom sudah bertambah dan data historis sudah terisi, kode aplikasi (Backend Python/Flask) untuk fitur *toggle edit/original* pada tanggal *review guestbook* sudah bisa Anda deploy dan gunakan secara langsung.
