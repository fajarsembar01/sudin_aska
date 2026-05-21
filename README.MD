# 🤖 ASKA — Agent AI Sekolah Kita

ASKA adalah _stack_ AI untuk SD(sekolah dasar) hingga menengah yang siap digandakan. Satu repositori ini berisi:

- Bot Telegram yang mengenali konteks sekolah, menerima teks, foto, serta suara.
- Mesin RAG (Retrieval Augmented Generation) berbasis LangChain + Groq Llama 3.1 (bisa diganti OpenAI atau embedding lokal gratis).
- Dashboard Flask untuk monitoring percakapan, data kedisiplinan, dan notifikasi laporan sensitif.
- Web chat dengan login Google (belajar.id / Gmail) plus kuota percakapan.
- Workflow pelaporan bullying, psikolog, dan dugaan korupsi yang langsung masuk PostgreSQL.
- Worker opsional untuk Twitter/X (balas mention dan auto-post berbasis RAG).

Repo ini awalnya diproduksi untuk satu sekolah, namun seluruh konfigurasi dipisah ke `.env` dan file markdown sehingga mudah diadaptasi, misalnya untuk **Suku Dinas Pendidikan Jakarta Utara 2**.

---

## 🔍 Kenapa Cocok untuk Sekolah Lain?

- **Modular** — tiga kanal (Telegram, Web, Twitter) berbagi _logic_ yang sama di `ai_core.py` + `flows/`.
- **Pengetahuan mudah diganti** — cukup edit `kecerdasan/markdown/profil_sudindikju2.md` & `kecerdasan/markdown/umum.md`, lalu jalankan `python knowledge_loader.py`.
- **Data internal aman** — semua laporan masuk PostgreSQL dan bisa dimonitor via dashboard.
- **Ops-friendly** — tersedia skrip `scripts/init_db.py`, CLI dashboard (`dashboard/cli.py`), serta contoh unit `systemd` dan Nginx.
- **Gratis bila perlu** — dukung embedding lokal HuggingFace dan STT/LLM OpenAI-compatible.

---

## 🧱 Arsitektur Singkat

```
Telegram / Web / WhatsApp / Twitter
        │
        ▼
   handlers.py
        │
        ▼
   LangChain RAG (ai_core.py)
        │           ▲
        │           │
        ▼           │
  PostgreSQL  ◄─────┘  (chat_logs, laporan, quota, dashboard)
        │
        ▼
Dashboard Flask
```

Direktori penting:

- `bot_sekolah.py` – entri bot Telegram.
- `dashboard/` – dashboard admin dan CLI utility.
- `flows/` – percakapan khusus (bullying, psikologi, guru, korupsi, small talk).
- `responses/` – template jawaban dan detektor niat.
- `knowledge_loader.py` + `kecerdasan/` – sumber pengetahuan sekolah.
- `twitter_bot.py` – worker balas mention & auto-post.
- `scripts/whatsapp_bridge.js` – worker WhatsApp QR bridge (chat pribadi).
- `db.py` & `scripts/init_db.py` – koneksi dan bootstrap PostgreSQL.
- `scripts/` – kumpulan skrip maintenance (migrasi, seed, export).

> Folder `backup/` tidak dipakai di produksi; abaikan saat melakukan penyesuaian.

---

## ✅ Prasyarat

**Server & Tooling**

- Ubuntu 22.04 LTS atau setara.
- Python 3.10+, `python3-venv`, `pip`, `git`.
- Node.js 18+ dan npm (untuk WhatsApp QR bridge).
- PostgreSQL 13+ (boleh layanan _managed_ seperti Supabase/Railway).
- Nginx + Certbot bila ingin HTTPS.

**Akun & Token**

- Token Bot Telegram dari `@BotFather`.
- Token internal untuk endpoint WhatsApp bridge (`ASKA_WHATSAPP_INTERNAL_TOKEN`).
- Groq API key **atau** OpenAI API key (untuk LLM + embedding).
- (Opsional) OpenAI/HuggingFace key untuk embedding/STT lokal.
- Google OAuth client (untuk login web, bisa satu project per sekolah).
- (Opsional) Twitter/X developer keys.

---

## ⚡️ Langkah Instalasi Cepat (Ubuntu)

```bash
# 0. Sistem dasar
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-venv python3-pip nginx certbot python3-certbot-nginx postgresql nodejs npm

# 1. Clone repo
cd /opt
sudo git clone https://github.com/sofelijo/ai-agent-sekolah.git
sudo chown -R $USER:$USER ai-agent-sekolah
cd ai-agent-sekolah

# 2. Virtualenv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Salin konfigurasi
cp .env .env.local.example  # opsional backup
nano .env                   # isi sesuai sekolah Anda

# 4. Susun ulang pengetahuan & cache vektor
python knowledge_loader.py

# 5. Inisialisasi semua tabel
python -m scripts.init_db

# 6. Buat akun admin dashboard
python -m dashboard.cli create-user admin@sekolah.sch.id "Admin Sekolah"

# 7. Uji komponen
python bot_sekolah.py          # hentikan dengan Ctrl+C setelah tes
python -m web_aska.app &
npm run wa:start
python -m dashboard.app &
```

---

## 🔐 Konfigurasi `.env`

Contoh templat (hapus bagian yang tidak dipakai):

```bash
###############################################################################
# Identitas dasar
###############################################################################
ASKA_SCHOOL_NAME="SDN Contoh 01"
ASKA_TIMEZONE=Asia/Jakarta

###############################################################################
# LLM & RAG
###############################################################################
GROQ_API_KEY=sk-...
OPENAI_API_KEY=                      # isi bila pakai OpenAI langsung
ASKA_QA_MODEL=llama-3.1-8b-instant   # bisa ganti gpt-4o, dsb.
ASKA_QA_TEMPERATURE=0
ASKA_QA_MAX_TOKENS=350

# Embedding
ASKA_EMBEDDING_BACKEND=auto          # auto | openai | local
ASKA_EMBEDDING_API_KEY=              # pakai OPENAI_API_KEY jika kosong
ASKA_EMBEDDING_MODEL=text-embedding-3-large
ASKA_EMBEDDING_MODEL_LOCAL=sentence-transformers/all-MiniLM-L6-v2
ASKA_EMBEDDING_DEVICE=cpu
ASKA_CHUNK_SIZE=500
ASKA_CHUNK_OVERLAP=50
ASKA_VECTORSTORE_PATH=.aska_vectorstore
ASKA_VECTORSTORE_INDEX=kecerdasan

# Speech-to-text (Telegram voice note)
ASKA_STT_API_KEY=
ASKA_STT_API_BASE=https://api.openai.com/v1
OPENAI_STT_MODEL=gpt-4o-mini-transcribe

###############################################################################
# Database (dipakai bot, dashboard, web, twitter worker)
###############################################################################
DB_NAME=aska_db
DB_USER=aska_user
DB_PASS=super-secret
DB_HOST=127.0.0.1
DB_PORT=5432
DB_SSLMODE=                       # isi require bila perlu

###############################################################################
# Kanal Telegram
###############################################################################
TELEGRAM_BOT_TOKEN=123456:ABC

###############################################################################
# Kanal WhatsApp (gratis, scan QR sekali via worker)
###############################################################################
ASKA_WHATSAPP_INTERNAL_TOKEN=ganti-token-acak-min-24-char
ASKA_WHATSAPP_INTERNAL_URL=http://127.0.0.1:5001/api/whatsapp/inbound
ASKA_WHATSAPP_SESSION_PATH=.wa_session
ASKA_WHATSAPP_CLIENT_ID=aska-main
ASKA_WHATSAPP_TIMEOUT_MS=45000
ASKA_WHATSAPP_URL=082143646463       # dipakai tombol WhatsApp di ASKA Insight

###############################################################################
# Call Center WhatsApp (bridge khusus dashboard)
###############################################################################
ASKA_CC_WHATSAPP_INTERNAL_TOKEN=ganti-token-acak-cc-min-24-char
ASKA_CC_WHATSAPP_INTERNAL_URL=http://127.0.0.1:5002/api/callcenter/inbound
ASKA_CC_WHATSAPP_SESSION_PATH=.wa_cc_session
ASKA_CC_WHATSAPP_CLIENT_ID=cc-main
ASKA_CC_WHATSAPP_STATUS_PATH=runtime/whatsapp_cc_status.json
ASKA_CC_HTTP_PORT=3100

###############################################################################
# Dashboard Flask
###############################################################################
DASHBOARD_SECRET_KEY=ubah-ke-random-32-karakter
DASHBOARD_SESSION_DAYS=14
DASHBOARD_DB_MAX_CONN=8

###############################################################################
# Web Chat (OAuth Google)
###############################################################################
APP_SECRET_KEY=ubah-lagi-untuk-web
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=yyy
WEB_QUOTA_LIMIT=3
WEB_QUOTA_RESET_HOURS=24

###############################################################################
# Twitter / X (opsional)
###############################################################################
TWITTER_BEARER_TOKEN=
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=
TWITTER_POLL_INTERVAL=90
TWITTER_STATE_PATH=twitter_state.json
TWITTER_AUTOPOST_ENABLED=false
TWITTER_AUTOPOST_INTERVAL=3600
TWITTER_AUTOPOST_MESSAGES_PATH=twitter_posts.txt
TWITTER_AUTOPOST_RECENT_LIMIT=8
TWITTER_SPAM_KEYWORDS=promo,follback
```

> Saran: gunakan `cp .env .env.production` lalu simpan versi berbeda untuk staging.

---

## 📚 Menyiapkan Pengetahuan Sekolah

1. Isi `kecerdasan/markdown/profil_sudindikju2.md` dengan data unik instansi (profil, layanan, jadwal kegiatan).
2. Lengkapi `kecerdasan/markdown/umum.md` untuk panduan generik (layanan, kebijakan nasional, FAQ).
3. Sisipkan `<!-- {{ASKA_PROFIL_DAN_JADWAL}} -->` di `umum.md` bila ingin menempel profil secara otomatis.
4. Jalankan `python knowledge_loader.py` agar `kecerdasan.md` diperbarui dan tersimpan di cache FAISS.
5. Jika ingin mereset vektor, hapus folder `.aska_vectorstore/` kemudian jalankan ulang bot.

---

## 🗄️ Inisialisasi Database & Data Referensi

- Jalankan `python -m scripts.init_db` setiap kali mengubah struktur atau saat setup baru. Skrip ini memanggil `db.py` dan `dashboard/schema.py` untuk menyiapkan:
  - `chat_logs`, `web_users`, `telegram_users`, `whatsapp_users`, `corruption_reports`, `bullying_reports`, `psych_reports`, `twitter_worker_logs`.
  - Tabel dashboard (`dashboard_users`, `bullying_report_events`, `notifications`).
- Buat akun dashboard dengan CLI:

```bash
python -m dashboard.cli create-user admin@contoh.sch.id "Admin Contoh" --role admin
python -m dashboard.cli list-users
```

## ▶️ Menjalankan Komponen

### 1. Telegram Bot

```bash
source venv/bin/activate
python bot_sekolah.py
```

### 2. Dashboard Admin

```bash
export FLASK_APP=dashboard.app:create_app
flask run --host 0.0.0.0 --port 8000
# produksi: gunicorn -w 2 -k gthread -b 127.0.0.1:8000 dashboard.app:app
```

### 3. Web Chat (OAuth Google)

```bash
python -m web_aska.app
# produksi: gunicorn -w 2 -k gthread -b 127.0.0.1:5001 web_aska.app:app
```

### 4. WhatsApp Bridge (QR sekali, chat pribadi)

```bash
npm install
npm run wa:start
```

Saat pertama jalan, terminal menampilkan QR. Scan di WhatsApp:
`Settings > Linked Devices > Link a Device`.

### 4b. WhatsApp Bridge Call Center (untuk dashboard)

```bash
# variabel di .env: ASKA_CC_WHATSAPP_INTERNAL_TOKEN, ASKA_CC_HTTP_PORT (default 3100)
ASKA_CC_HTTP_PORT=3200 npm run wa:cc   # lepas override bila port 3100 kosong
```

- Buka dashboard `Call Center > Settings > WhatsApp`, tekan Generate QR, lalu scan QR di WhatsApp `Linked Devices`.
- Pastikan backend dashboard (`dashboard.app` port 5002) sudah jalan; bridge ini meneruskan chat ke endpoint `api/callcenter/inbound` dengan header `X-ASKA-CC-TOKEN` yang sama dengan `ASKA_CC_WHATSAPP_INTERNAL_TOKEN`.

### 5. Twitter Worker (opsional)

```bash
python twitter_bot.py
```

### 6. Regenerasi Knowledge & Cache

```bash
python knowledge_loader.py
rm -rf .aska_vectorstore && python bot_sekolah.py   # paksa rebuild
```

---

## ⏹️ Menghentikan Komponen

### Menghentikan Semua (lokal)

```bash
# Telegram Bot — tekan Ctrl+C di terminal yang menjalankan bot_sekolah.py

# Dashboard Admin (port 8000)
lsof -ti :8000 | xargs kill -9

# Web Chat / WhatsApp Backend (port 5001)
lsof -ti :5001 | xargs kill -9

# WhatsApp Bridge
pkill -f "whatsapp_bridge"

# Twitter Worker — tekan Ctrl+C di terminal yang menjalankan twitter_bot.py
```

### Menghentikan per Komponen

| Komponen | Perintah stop |
| --- | --- |
| Telegram Bot | `Ctrl+C` di terminal |
| Dashboard Admin | `lsof -ti :8000 \| xargs kill -9` |
| Web Chat (port 5001) | `lsof -ti :5001 \| xargs kill -9` |
| WhatsApp Bridge | `pkill -f "whatsapp_bridge"` |
| Twitter Worker | `Ctrl+C` di terminal |

### Menghentikan di Produksi (systemd)

```bash
sudo systemctl stop ai-bot.service            # Telegram Bot
sudo systemctl stop aska-dashboard.service     # Dashboard
sudo systemctl stop aska-webapp.service        # Web Chat
sudo systemctl stop aska-whatsapp.service      # WhatsApp Bridge
```

---

## 🛡️ Contoh Unit `systemd`

Sesuaikan jalur `WorkingDirectory` dengan lokasi repo Anda (mis. `/opt/aska`).

### `ai-bot.service`

```ini
[Unit]
Description=ASKA Telegram Bot
After=network.target

[Service]
WorkingDirectory=/opt/ai-agent-sekolah
EnvironmentFile=/opt/ai-agent-sekolah/.env
ExecStart=/opt/ai-agent-sekolah/venv/bin/python bot_sekolah.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### `aska-dashboard.service`

```ini
[Unit]
Description=ASKA Dashboard
After=network.target

[Service]
WorkingDirectory=/opt/ai-agent-sekolah
EnvironmentFile=/opt/ai-agent-sekolah/.env
ExecStart=/opt/ai-agent-sekolah/venv/bin/gunicorn -w 2 -k gthread -b 127.0.0.1:8000 dashboard.app:app
User=www-data
Group=www-data
Restart=always

[Install]
WantedBy=multi-user.target
```

### `aska-whatsapp.service`

```ini
[Unit]
Description=ASKA WhatsApp Bridge (QR Session)
After=network.target

[Service]
WorkingDirectory=/opt/ai-agent-sekolah
EnvironmentFile=/opt/ai-agent-sekolah/.env
ExecStart=/usr/bin/npm run wa:start --silent
Restart=always
RestartSec=5
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

## 🌐 Contoh Nginx

```nginx
server {
    listen 80;
    server_name dashboard.sekolah.sch.id;

    location /static/ {
        alias /opt/ai-agent-sekolah/dashboard/static/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Ulangi pola yang sama untuk web chat (port 5001). Jangan lupa TLS:

```bash
sudo certbot --nginx -d dashboard.sekolah.sch.id -d aska.sekolah.sch.id
```

---

## 🏫 Checklist Migrasi ke Sekolah Baru

1. **Branding & Copy**
   - Ubah nama sekolah di `.env` dan `dashboard/templates/*.html`.
   - Sesuaikan emoji/gaya bahasa di `responses/`.
2. **Pengetahuan**
   - Tulis data unik instansi di `kecerdasan/markdown/profil_sudindikju2.md`.
   - Isi kalender kegiatan dan SOP di `kecerdasan/markdown/umum.md`.
   - Jalankan `python knowledge_loader.py`.
3. **Integrasi Google**
   - Buat OAuth client baru, isi `GOOGLE_CLIENT_ID/SECRET`, dan perbarui domain yang diizinkan.
4. **Kebijakan Akses**
   - Atur kuota web di `.env` (`DEFAULT_LIMITED_QUOTA`, dsb).
   - Gunakan `account_status.py` untuk memblokir atau memberi prioritas user tertentu.
5. **Keamanan & Privasi**
   - Ganti semua `SECRET_KEY`, `APP_SECRET_KEY`, password DB, serta buat user PostgreSQL unik.
   - Pastikan hanya admin sekolah yang punya akses dashboard (`dashboard_users`).
6. **Opsional: Twitter & Voice**
   - Isi kredensial `TWITTER_*` bila ingin kampanye publik.
   - Aktifkan `ASKA_STT_API_KEY` untuk fitur voice note.

---

## 📊 Monitoring & Pemeliharaan

```bash
sudo systemctl status ai-bot.service
sudo systemctl status aska-dashboard.service
sudo systemctl status aska-webapp.service
sudo systemctl status aska-whatsapp.service
sudo journalctl -u ai-bot.service -f   # lihat log real-time
```

Update kode secara berkala:

```bash
cd /opt/ai-agent-sekolah
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart ai-bot.service aska-dashboard.service aska-webapp.service aska-whatsapp.service
```

---

## 📥 Panduan Ekstra: Download File dari Server (ke Lokal Mac)

Gunakan perintah bawaan `scp` (*Secure Copy*) di Terminal Mac Anda (pastikan posisi **tidak sedang login (SSH)** di dalam server). 

Format dasar:
```bash
scp -r <username_server>@<ip_server>:<lokasi_folder_server> <lokasi_tujuan_lokal>
```

**Contoh 1: Download folder `uploads` ke Desktop Mac (menggunakan username `root`)**
```bash
scp -r root@202.10.37.22:/opt/sudin_aska/uploads ~/Desktop/
```
Lalu masukkan password server Anda (*ketikan tidak akan terlihat, biarkan saja lalu tekan Enter*).

> **💡 Tips:** Jika Anda telanjur berada di dalam server karena menjalankan perintah `ssh`, ketik `exit` lalu Enter untuk kembali ke Terminal Mac, baru jalankan perintah `scp` di atas.

---

## 🧪 Troubleshooting Cepat

| Gejala | Langkah cek cepat |
| --- | --- |
| Tidak bisa membuat `venv` | `sudo apt install python3-venv -y` |
| Bot diam | Pastikan `.env` benar, cek `journalctl -u ai-bot.service -f` |
| WhatsApp tidak membalas | Pastikan `npm run wa:start` aktif, token internal cocok, dan scan QR sudah sukses |
| Error `faiss` | `pip install faiss-cpu` (atau pasang dari conda pada CPU lawas) |
| Google login gagal | Pastikan domain di konsol Google sudah memasukkan URL callback `/authorize` |
| Dashboard blank | Periksa koneksi DB (`psql`), jalankan ulang `python -m scripts.init_db` |
| Embedding lokal error | Install `pip install langchain-huggingface sentence-transformers torch>=1.11` |

---

## 🙋‍♂️ Kontributor

- MH. Ainun Fajar — Latsar CPNS 2025, lingkungan pendidikan Jakarta Utara 2.
- GitHub: [@sofelijo](https://github.com/sofelijo)

Silakan buka _issue_ atau _pull request_ bila ada saran perbaikan. Semoga membantu sekolah Anda membangun layanan AI dengan cepat! 🙌
