# Sudin Pendidikan Jakarta Utara — Wilayah 2

Portal layanan digital Suku Dinas Pendidikan Jakarta Utara Wilayah 2. Dibangun dengan [Next.js](https://nextjs.org).

---

## Development (Lokal)

```bash
npm install
npm run dev
```

Buka [http://localhost:3000](http://localhost:3000) di browser.

Edit halaman di `app/page.tsx` — otomatis reload saat disimpan.

---

## Deploy ke Server Production

### Pertama kali (setup awal)

```bash
# 1. Masuk ke direktori
cd /opt/sudin_aska/sudindikju22

# 2. Install dependencies
npm install

# 3. Build
npm run build

# 4. Jalankan dengan PM2
pm2 start ./node_modules/.bin/next --name "sudindikju22" -- start

# 5. Simpan agar auto-start saat server reboot
pm2 save
pm2 startup
```

### Setup PM2 startup (sekali saja)

```bash
pm2 startup
# jalankan perintah yang ditampilkan, lalu:
pm2 save
```

---

## Update / Deploy Ulang

Setelah push perubahan dari lokal, jalankan di server:

```bash
cd /opt/sudin_aska/sudindikju22
git pull
npm install        # jika ada package baru
npm run build
pm2 restart sudindikju22
```

---

## Monitoring

```bash
pm2 status                    # lihat status semua proses
pm2 logs sudindikju22         # lihat log realtime
pm2 logs sudindikju22 --lines 50  # lihat 50 baris terakhir
pm2 restart sudindikju22      # restart app
pm2 stop sudindikju22         # stop app
```

---

## Info Server

| Item | Detail |
|------|--------|
| Server | `root@sudindikju2` |
| IP | `202.10.37.22` |
| Port App | `3000` (Next.js via PM2) |
| Directory | `/opt/sudin_aska/sudindikju22` |
| PM2 Name | `sudindikju22` |
| Nginx Config | `/etc/nginx/sites-available/sudindikju22` |
| URL (local) | http://202.10.37.22:3000 |
| URL (production) | https://sudindikju2.com |
| DNS | Cloudflare (Proxied) |
| SSL | Cloudflare (otomatis) |
