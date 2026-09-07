# 📞 Tutorial Setup Call Center Dashboard (CCD)

Panduan lengkap untuk menyiapkan, menjalankan, dan mengelola fitur **Call Center** berbasis WhatsApp pada ASKA Dashboard — mulai dari konfigurasi `.env`, setup bridge, hingga troubleshooting umum.

---

## 📋 Daftar Isi

1. [Gambaran Umum](#1-gambaran-umum)
2. [Prasyarat](#2-prasyarat)
3. [Konfigurasi `.env`](#3-konfigurasi-env)
4. [Setup Bridge WhatsApp CC](#4-setup-bridge-whatsapp-cc)
5. [Mengelola Bridge dari Dashboard (Direkomendasikan)](#5-mengelola-bridge-dari-dashboard-direkomendasikan)
6. [Cara Scan QR & Menghubungkan WhatsApp](#6-cara-scan-qr--menghubungkan-whatsapp)
7. [Sync Pesan Lama](#7-sync-pesan-lama)
8. [Monitoring & Log](#8-monitoring--log)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Gambaran Umum

Call Center Dashboard memungkinkan tim admin membalas pesan WhatsApp langsung dari browser, tanpa perlu memegang HP. Arsitekturnya:

```
WhatsApp Pengguna
      │
      ▼
wa_bridge_cc.js  (Node.js, port 3100)
      │  POST /api/callcenter/inbound
      ▼
Gunicorn / Flask  (port 8000)
      │
      ▼
PostgreSQL  ──►  Dashboard Admin (browser)
```

**Komponen utama:**

| Komponen | File | Port |
|---|---|---|
| Dashboard Flask | `dashboard/app.py` | 8000 (via Gunicorn) |
| WhatsApp CC Bridge | `scripts/whatsapp_bridge_cc.js` | 3100 |

> **Penting:** Bridge CC (`port 3100`) adalah proses terpisah dari bridge AI WhatsApp (`wa:start`). Keduanya bisa berjalan bersamaan menggunakan nomor WhatsApp yang berbeda.

---

## 2. Prasyarat

- Dashboard ASKA sudah berjalan (service `aska-dashboard.service` aktif via Gunicorn di port **8000**)
- Node.js 18+ dan `npm install` sudah dijalankan
- Nomor WhatsApp terpisah khusus untuk Call Center (berbeda dari nomor bot ASKA biasa)
- Akun admin dashboard sudah dibuat

---

## 3. Konfigurasi `.env`

Tambahkan/pastikan variabel berikut ada di file `.env` di root proyek:

```bash
###############################################################################
# Call Center WhatsApp Bridge
###############################################################################

# Token rahasia (wajib) — minimal 24 karakter, buat acak
ASKA_CC_WHATSAPP_INTERNAL_TOKEN=ganti-token-acak-cc-min-24-char

# URL endpoint inbound — sesuaikan port dengan port Gunicorn (default: 8000)
# PENTING: Gunakan port yang sama dengan Gunicorn, bukan 5002 (Flask dev)
ASKA_CC_WHATSAPP_INTERNAL_URL=http://127.0.0.1:8000/api/callcenter/inbound

# Port HTTP bridge CC (default: 3100)
ASKA_CC_HTTP_PORT=3100

# (Opsional) — bisa dibiarkan default
# ASKA_CC_WHATSAPP_SESSION_PATH=.wa_cc_session
# ASKA_CC_WHATSAPP_CLIENT_ID=cc-main
# ASKA_CC_WHATSAPP_STATUS_PATH=runtime/whatsapp_cc_status.json

# (Opsional darurat) — jangan diisi kecuali QR bermasalah karena perubahan WhatsApp Web
# ASKA_CC_WHATSAPP_WEB_VERSION=2.3000.xxxxx
# ASKA_CC_WHATSAPP_WEB_CACHE_TYPE=local
```

> ⚠️ **Jangan gunakan port 5002** untuk `ASKA_CC_WHATSAPP_INTERNAL_URL` di produksi. Port 5002 adalah Flask development server. Di produksi, dashboard berjalan di Gunicorn pada port **8000**.

---

## 4. Setup Bridge WhatsApp CC

### Verifikasi instalasi Node

```bash
node -v    # harus >= 18
npm -v
```

### Install dependency (jika belum)

```bash
cd /opt/sudin_aska
npm install
```

### Verifikasi script tersedia

```bash
cat package.json | grep wa:cc
# Output: "wa:cc": "node scripts/whatsapp_bridge_cc.js"
```

---

## 5. Mengelola Bridge dari Dashboard (Direkomendasikan)

> ✅ **Gunakan selalu cara ini.** Jangan jalankan `npm run wa:cc` manual di terminal — proses akan mati saat terminal ditutup.

Dashboard sudah memiliki sistem manajemen bridge otomatis. Saat Anda menekan tombol **"Generate QR Baru"** di halaman `/call-center/settings/wa`, dashboard akan:

1. Menghentikan proses bridge lama (via PID yang tersimpan di `runtime/whatsapp_cc.pid`)
2. Membersihkan lock file Chromium yang tersisa
3. Menjalankan `npm run wa:cc` sebagai background process (`start_new_session=True`)
4. Menyimpan PID baru ke `runtime/whatsapp_cc.pid`
5. Menulis status ke `runtime/whatsapp_cc_status.json`

### Alur lengkap dari dashboard:

```
Buka /call-center/settings/wa
        │
        ▼
Klik "Generate QR Baru"
        │
        ▼
Tunggu 5-15 detik
        │
        ▼
Status berubah → "qr" (QR code muncul)
        │
        ▼
Scan QR di WhatsApp → Linked Devices
        │
        ▼
Status berubah → "ready" ✅
```

---

## 6. Cara Scan QR & Menghubungkan WhatsApp

1. Buka halaman **Call Center → Settings → WhatsApp** di dashboard
2. Klik tombol **"Generate QR Baru"**
3. Tunggu QR muncul (5–15 detik)
4. Di HP dengan nomor WhatsApp CC:
   - Buka WhatsApp → **Setelan** → **Perangkat Tertaut** → **Tautkan Perangkat**
   - Scan QR yang tampil di dashboard
5. Status akan berubah menjadi **"ready"**
6. Bridge siap menerima dan mengirim pesan

> 💡 Session WhatsApp tersimpan di `.wa_cc_session/`. Anda tidak perlu scan ulang kecuali session expired atau Anda menekan "Generate QR Baru" (yang akan mereset session).

---

## 7. Sync Pesan Lama

Fitur **"Sync Pesan Lama"** mengimpor histori chat WhatsApp yang sudah ada ke database dashboard.

### Cara pakai:

1. Pastikan bridge sudah **"ready"**
2. Di halaman `/call-center/settings/wa`, atur:
   - **Chat terbaru**: jumlah chat yang akan diambil (default: 25, max: 200)
   - **Pesan/chat**: jumlah pesan per chat (default: 50, max: 500)
3. Klik **"Sync Pesan Lama"**
4. Tunggu proses selesai (bisa beberapa menit tergantung jumlah chat)

> **Catatan:** Pesan duplikat akan dilewati otomatis. Sync aman dijalankan berulang kali.

---

## 8. Monitoring & Log

### Cek status bridge

```bash
# Status file JSON
cat /opt/sudin_aska/runtime/whatsapp_cc_status.json

# Log bridge (output dari wa:cc)
tail -f /opt/sudin_aska/runtime/whatsapp_cc.log

# Cek proses berjalan
ps aux | grep whatsapp_bridge_cc

# Cek port 3100
ss -tlnp | grep 3100
```

### Cek log dashboard (Gunicorn)

```bash
journalctl -u aska-dashboard.service -f -n 50
```

### State bridge yang mungkin muncul di status JSON:

| State | Artinya |
|---|---|
| `starting` | Bridge sedang inisialisasi Puppeteer/Chromium |
| `qr` | QR sudah siap, tunggu scan |
| `authenticated` | Sudah auth, menunggu ready |
| `ready` | ✅ Bridge aktif dan siap |
| `disconnected` | WhatsApp terputus, bridge akan reconnect otomatis |
| `auth_failure` | Sesi expired, perlu Generate QR Baru |
| `stopped` | Bridge tidak berjalan |

---

## 9. Troubleshooting

### ❌ Error: `EADDRINUSE: address already in use :::3100`

Port 3100 sudah dipakai proses lain.

```bash
# Cari proses yang pakai port 3100
lsof -i :3100

# Kill proses tersebut (ganti PID dengan hasil di atas)
kill -9 <PID>

# Atau langsung:
fuser -k 3100/tcp
```

---

### ❌ Error: `Backend error: connect ECONNREFUSED 127.0.0.1:5002`

Bridge mencoba kirim ke port 5002, tapi dashboard berjalan di port 8000.

**Penyebab:** `ASKA_CC_WHATSAPP_INTERNAL_URL` di `.env` masih mengarah ke port lama (5002 = Flask dev server).

**Solusi:**

```bash
# Cek isi .env
grep "ASKA_CC_WHATSAPP_INTERNAL_URL" /opt/sudin_aska/.env

# Tambah/update ke port 8000
echo "ASKA_CC_WHATSAPP_INTERNAL_URL=http://127.0.0.1:8000/api/callcenter/inbound" >> /opt/sudin_aska/.env

# Restart bridge dari dashboard (klik Generate QR Baru)
# atau kill manual lalu restart:
fuser -k 3100/tcp && pkill -f "\.wa_cc_session" && sleep 2 && npm run wa:cc
```

---

### ❌ Saat scan QR muncul "Saat ini tidak bisa menautkan perangkat baru"

Penyebab umum:
- Session/QR dibuat dari WhatsApp Web cache lama.
- Akun WhatsApp sudah mencapai batas linked device.
- WhatsApp sedang membatasi penautan sementara untuk akun tersebut.

Langkah perbaikan:

```bash
# Pastikan proses bridge lama berhenti dan lock Chromium bersih
fuser -k 3100/tcp
pkill -f whatsapp_bridge_cc
pkill -f "\.wa_cc_session"
rm -f /opt/sudin_aska/runtime/whatsapp_cc.pid
rm -f /opt/sudin_aska/.wa_cc_session/session-cc-main/SingletonLock
```

Lalu buka dashboard dan klik **Generate QR** lagi. Jika masih gagal, buka WhatsApp di HP -> **Perangkat tertaut**, hapus perangkat lama yang tidak dipakai, lalu scan QR baru.

---

### ❌ Error: `The browser is already running for .../.wa_cc_session/session-cc-main`

Ada proses Chromium lama yang belum mati.

```bash
# Kill proses Chromium dari session CC
pkill -f "\.wa_cc_session"

# Atau kill semua chromium (hati-hati jika ada proses lain)
pkill -f chromium

# Tunggu sebentar lalu restart
sleep 2 && npm run wa:cc
```

---

### ❌ Status "Memulai bridge..." tidak berubah / muter terus

**Penyebab paling umum:** Chromium/Puppeteer gagal launch (biasanya crash karena OOM atau permission).

**Langkah diagnosis:**

```bash
# 1. Cek apakah Chromium berjalan
ps aux | grep -E "chrom|puppeteer" | grep -v grep

# 2. Cek log bridge
tail -50 /opt/sudin_aska/runtime/whatsapp_cc.log

# 3. Cek memory server
free -h

# 4. Cek OOM killer
dmesg | grep -E "oom|killed" | tail -10
```

**Solusi:**

```bash
# Kill semua proses lama
fuser -k 3100/tcp
pkill -f whatsapp_bridge_cc
pkill -f chromium
rm -f /opt/sudin_aska/runtime/whatsapp_cc.pid

# Bersihkan lock file
rm -f /opt/sudin_aska/.wa_cc_session/session-cc-main/SingletonLock

# Lalu klik "Generate QR Baru" dari dashboard
```

> ⚠️ **Jangan** jalankan `npm run wa:cc` manual! Gunakan tombol **"Generate QR Baru"** di dashboard agar PID tercatat dan bridge bisa dikelola otomatis.

---

### ❌ Error saat Sync Pesan Lama: `Cannot read properties of undefined (reading 'waitForChatLoading')`

Ini error umum pada `whatsapp-web.js` saat chat internal store belum siap saat `fetchMessages` dipanggil.

**Ini bukan error kritis** — script sudah memiliki mekanisme retry otomatis:
- Delay 300ms antar chat agar store siap
- Retry 1x setelah 1.5 detik jika gagal
- Chat yang tetap gagal di-skip dan dicatat sebagai `failedChats`

**Solusi jika terjadi banyak:**
- Tunggu beberapa menit setelah bridge `ready` sebelum sync
- Kurangi jumlah chat (mis. dari 25 → 10) agar lebih ringan
- Jalankan sync ulang — pesan duplikat dilewati otomatis

---

### ❌ Dashboard menampilkan "Bridge tidak berjalan" padahal proses ada

Dashboard membaca PID dari `runtime/whatsapp_cc.pid`. Jika bridge dijalankan manual (bukan lewat dashboard), PID tidak tercatat.

```bash
# Cek PID file
cat /opt/sudin_aska/runtime/whatsapp_cc.pid

# Cek proses aktif
ps aux | grep whatsapp_bridge_cc | grep -v grep
```

**Solusi:** Selalu gunakan tombol **"Generate QR Baru"** dari dashboard untuk memulai bridge. Ini akan mencatat PID dengan benar.

---

## 🔄 Update Kode & Restart Bridge

Setelah `git pull` dan ada perubahan pada `scripts/whatsapp_bridge_cc.js`:

```bash
# Di server
cd /opt/sudin_aska
git pull

# Restart bridge dari dashboard:
# Buka /call-center/settings/wa → klik "Generate QR Baru"
# (Tidak perlu restart aska-dashboard.service)
```

Jika perubahan ada di backend Python (`dashboard/`):

```bash
sudo systemctl restart aska-dashboard.service
```

---

## 📌 Checklist Setup Awal

- [ ] Variabel `ASKA_CC_WHATSAPP_INTERNAL_TOKEN` diisi di `.env`
- [ ] Variabel `ASKA_CC_WHATSAPP_INTERNAL_URL` mengarah ke port **8000** (bukan 5002)
- [ ] Service `aska-dashboard.service` aktif (`systemctl status aska-dashboard`)
- [ ] Port 8000 aktif (`ss -tlnp | grep 8000`)
- [ ] `npm install` sudah dijalankan di `/opt/sudin_aska`
- [ ] Klik "Generate QR Baru" → tunggu QR muncul
- [ ] Scan QR dengan nomor WhatsApp CC
- [ ] Status bridge berubah menjadi **"ready"**
- [ ] Tes kirim pesan ke nomor CC → muncul di inbox dashboard ✅
