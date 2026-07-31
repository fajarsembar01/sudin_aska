# responses/greeting.py
from __future__ import annotations

import random
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from ._shared import tokenize

# ─────────────────────────────────────────────────────────
# 0) Penanda pertanyaan dasar (untuk mencegah false positive greeting)
QUESTION_TOKENS = {
    "apa",
    "gimana",
    "bagaimana",
    "kenapa",
    "mengapa",
    "siapa",
    "kapan",
    "dimana",
    "di",
    "mana",
    "berapa",
    "kah",
}


# ─────────────────────────────────────────────────────────
# 1) Kata/frasa sapaan umum (tanpa kata waktu agar tidak bentrok)
GREETING_KEYWORDS = (
    "hai",
    "hay",
    "halo",
    "hallo",
    "helo",
    "hello",
    "hey",
    "heyy",
    "heyyy",
    "hi",
    "hii",
    "hiya",
    "yo",
    "yoo",
    "yooo",
    "yoooo",
    "yow",
    "oy",
    "oi",
    "oii",
    "woy",
    "hoi",
    "cuy",
    "cui",
    "bro",
    "sis",
    "gan",
    "min",
    "permisi",
    "p",
    "assalamualaikum",
    "asswrwb",
    # Catatan: sengaja TIDAK menyertakan "morning/afternoon/evening"
    # maupun "pagi/siang/sore/malam" di sini; itu diproses di TIME_*
)
GREETING_KEYWORDS_SET = set(GREETING_KEYWORDS)

GREETING_PHRASES = (
    "selamat pagi",
    "selamat siang",
    "selamat sore",
    "selamat malam",
    "good morning",
    "good afternoon",
    "good evening",
    "assalamualaikum",
    "assalamualaikum wr wb",
    "assalamu alaikum",
    "permisi kak",
    "permisi min",
    "permisi bang",
    "ass wr wb",
    "ass.wr.wb",
)

GREETING_RESPONSES = [
    # 30 sapaan baru - Edisi Gen Z Final Form 💥💅✨
    "Yo, {user_name}! 🤙✨ Kenalin, aku ASKA, bestie virtual kamu di sekolah.\n\nButuh info, mau curhat, atau gabut? 🤪 Langsung spill aja, aku siap dengerin 24/7! 🎧🔥",
    "Wassup, {user_name}! 🤘😎 ASKA in the house!\n\nSiap ngebantu kamu kapan aja, di mana aja. 🚀\n\nInfo KJP, SPMB, atau cuma pengen gibah? Chat ASKA aja, gaskeun! 😉🔥",
    "Heyo, {user_name}! 🥳 Welcome to the hub Suku Dinas Pendidikan Jakarta Utara 2! 🏫\n\nAku ASKA, AI paling up-to-date di sini. 🤖\n\nJangan malu-malu, tanya apa aja, pasti aku jawab! ✨💯",
    "Bestie {user_name}! ✨ Bingung sendirian itu canon event, mending tanya ASKA. 🍵\n\nInfo sekolah, jadwal, sampe akun sosmed, semua ada di sini! Spill the tea! 💅",
    "Oiii!!, {user_name}! 👋\n\nLagi pusing sama alur SPMB 2025, {user_name}? 🤯💥\n\nTenang, woles... Tanya ASKA aja soal jadwal, jalur, atau syaratnya. Aku bantu biar prosesnya lancar jaya! 💅✨",
    "Haiii!!, {user_name}! 👋\n\nKamu atau kenalan kamu mau daftar SD, {user_name}? 👶 Pas banget! 💯\n\nASKA punya semua info SPMB paling update. Coba ketik 'info SPMB', aku kasih tau A-Z. 🚀",
    "Wassup, {user_name}! 👋\n\nBingung cara bikin akun SPMB atau verifikasi KK, {user_name}? 🤔\n\nSini aku bisikin caranya, no ribet-ribet club! 🙅‍♀️ Aku pandu step-by-step, gampang pol! 📝✅",
    "Eh, {user_name}, lagi mantau seleksi, ygy? 👀\n\nKepo sama ranking kamu? Cek di sohib aku `@spmblive_bot` di Telegram. Biar nggak overthinking! 🫣🤫",
    "Hai sunshine! Semoga harimu vibes positif—ASKA standby ya ☀️🤖\n\nBiar nggak saltum atau telat, {user_name}, cusss cek jadwal pelajaran hari ini ke ASKA! 🏃💨\n\nTinggal ketik 'jadwal kelasku', auto muncul. Sat set sat set! 💅✨",
    "Cek cek! *ASKA* connected—ketik aja!💬\n\nKepo minggu ini ada ekskul apa aja, {user_name}? 🧐 Atau jadwal upacara? 🇮🇩\n\nTanya ASKA aja! Semua jadwal kegiatan sekolah ada di genggaman kamu. Praktis abis! 🤳💯",
    "Heyyy!!\n\n'Hari ini pake seragam apa, woy?!' 👕👖\n\nNah, daripada galau, {user_name}, mending tanya ASKA. Aku punya info seragam harian lengkap! ✨ Biar nggak salah kostum! 😉",
    "Good day! *ASKA* online—kamu santai aja😌 \n\nKamu ngerasa nggak aman atau liat ada perundungan, {user_name}? 😥\n\nPlis, jangan diem aja. 🤫 Lapor ke ASKA, 100% rahasia. 🤐\n\nSpill ceritanya, kita cari solusinya bareng. Kamu nggak sendirian. 🫂❤️",
    "Hola!👋✨ *ASKA* nongol nih, kabarin aja kebutuhanmu 😉📲\n\nKalo kamu jadi korban atau saksi bullying, {user_name}, kamu itu kuat & berani. 💪\n\nLaporin ke ASKA ya, identitas kamu aman. You are not alone in this. ❤️‍🩹🫂",
    "Halooo!!👋✨Liat ada yang aneh soal dana atau fasilitas sekolah, {user_name}? 🧐🤨\n\nYuk, jadi hero kejujuran! 🦸 Laporin ke ASKA, identitas kamu dijamin aman. Bikin sekolah kita makin proper & transparan! ✨Transparency check! ✨",
    "Heyyy!👋✨ Jangan takut buat speak up, {user_name}! 🗣️\n\nKalo ada indikasi korupsi, sekecil apa pun, laporan dari kamu berharga banget. ASKA siap jaga kerahasiaannya. ✊🔒 Integrity check!",
    "Heyyy!👋✨ Ngerasa overthinking atau butuh temen ngobrol, {user_name}? 😵‍💫\n\nIt's okay not to be okay. Di ASKA ada fitur curhat sama psikolog. Aman, nyaman, dan no judge. ❤️‍🩹🧘",
    "Halooo!!!, {user_name}! 👋\n\nKadang, kita cuma butuh didengerin, {user_name}. 👂\n\nKalo lagi ngerasa berat, coba deh ngobrol sama ASKA atau pake fitur konsultasi psikolog. *You are not alone*. 🤗🫂",
    "Haii!!👋✨, Lagi cemas atau sedih, {user_name}? 😥 Wajar banget, kok.\n\nASKA di sini buat dengerin. 🎧 Kalo butuh bantuan pro, aku bisa arahin ke fitur psikolog. Peluk jauh! 🤗🫂",
    "Haii!! Curhat, yuk {user_name}! 💬\n\nSoal apa aja, dari pertemanan, keluarga, sampe tugas numpuk. 📚 ASKA siap jadi pendengar setia kamu. Siapa tau abis ini jadi lebih plong. 😮‍💨✨",
    "Yo, squad! Info sekolah? *ASKA* bantuin dari A sampai Z 🔤🧩\n\nGalau milih ekskul atau bingung ngatur waktu belajar, {user_name}? 🤔\n\nCoba deh tanya ASKA. Siapa tau saran dari aku bisa jadi life hack buat kamu. 💡✨",
    "Haii! *ASKA* hadir, siap bantu kamu hari ini ✨👋\n\nButuh saran soal pertemanan atau cara ngadepin guru, {user_name}? 🧑‍🤝‍🧑\n\nSini, ngobrol sama ASKA. Aku punya beberapa tips jitu buat kamu! 😉📝",
    "'Aku harus gimana, ya?' 🤷‍♀️\n\nKalo pertanyaan itu lagi muter-muter di kepala kamu, {user_name}, coba ceritain masalahnya ke ASKA. Kita cari jalan keluarnya bareng. 🧠💪",
    "Yo yo! *ASKA* udah online, spill aja pertanyaannya 😉💬\n\nKepo sama guru baru atau mau kirim email ke wali kelas, {user_name}? 🤪\n\nTanya ASKA aja profil lengkap guru-guru di sekolah kita. Siapa tau dapet fun fact-nya juga! 🤫🎉",
    "Hey there! *ASKA* hadir dengan good vibes, gaskeun pertanyaannya 🌈\n\nMau kenalan lebih deket sama guru-guru kamu, {user_name}? 👩‍🏫👨‍🏫\n\nCoba ketik nama guru yang pengen kamu tau, nanti ASKA kasih infonya. Stalking for science! 🧑‍🔬🔬",
    "Hai {user_name}! 👋\n\nMau tau jadwal pelajaran, curhat, atau laporin sesuatu yang ngeganjel? 🤔 Bisa banget!\n\nKamu mau mulai dari mana, nih? 😊 ASKA siap bantu! 🚀",
    "Yo, {user_name}! ☀️ Butuh info SPMB atau sekadar pengen ngobrol biar semangat? 🔥\n\nASKA di sini buat kamu. *Just a text away!* 🚀📲",
    "Woy, {user_name}! 👋 Jangan lupa istirahat & makan, ya. 🍔\n\nSambil chill, kalo ada yang mau kamu tanyain soal sekolah atau butuh temen curhat, ASKA siap sedia. 🍽️💬",
    "Hey {user_name}, jangan sungkan sama ASKA, ya. 🙅‍♀️\n\nMau laporin hal serius kayak bullying atau cuma nanya info receh, semuanya penting buat aku. Your voice matters! 🤝❤️",
    "Hai tim sukses! *ASKA* siap jadi co-pilotmu hari ini 🛫🧭\n\nApapun kebutuhan kamu, {user_name}—info akademis 📚, mental support ❤️‍🩹, atau sekadar iseng nanya 🤔—aku, ASKA, siap bantu.\n\nKamu itu prioritas! 🌟👑",
    "Welcome, {user_name}! 🎉 Aku ASKA, sobat digital kamu. 🤖\n\nDari A sampai Z soal sekolah, dari info SPMB sampe butuh nasihat, *I got your back!* Kasih tau aja apa yang kamu butuhin. 🚀💯",
]

QA_ONLY_GREETING_RESPONSES = [
    "Yooo, {user_name}! *ASKA* standby buat bantu info sekolah dan SPMB ya 🤖✨",
    "Halo {user_name}! Mau cek data sekolah, jadwal, atau SPMB? Spill aja ke *ASKA* 🔎📚",
    "Hai {user_name}! *ASKA* online. Tanya info resmi sekolah? Gaskeun 💬✅",
    "Yo {user_name}! Aku *ASKA*, fokus bantu jawab dari data resmi sekolah biar nggak ngarang 😄📌",
    "Wassup {user_name}! Ada yang mau dicek soal sekolah/SPMB? *ASKA* siap bantu sat-set 🚀",
]


# ─────────────────────────────────────────────────────────
# 2) Sapaan berbasis waktu (dibersihkan agar konsisten)
TIME_GREETING_PATTERNS = {
    "pagi": ("selamat pagi", "good morning", "met pagi"),
    "siang": ("selamat siang", "good afternoon", "met siang"),
    "sore": ("selamat sore", "met sore"),
    # Konsisten: "good evening" → malam
    "malam": ("selamat malam", "good evening", "good night", "met malam"),
}

TIME_GREETING_KEYWORDS = {
    "pagi": {
        "pagi",
        "pagii",
        "pagiii",
        "pg",
        "morning",
        "gm",
        "gmorn",
        "goodmorning",
        "subuh",
    },
    "siang": {"siang", "siangg", "sianggg", "afternoon", "noon", "midday"},
    "sore": {"sore", "soree", "sorean", "petang"},
    "malam": {
        "malam",
        "malemm",
        "malammm",
        "mlm",
        "night",
        "evening",
        "gn",
        "goodnight",
        "nite",
        "midnight",
        "larut",
    },
}

# Respons sapaan bergaya Gen-Z + sopan (≤10/slot waktu)
TIME_GREETING_RESPONSES = {
    "pagi": [
        "Selamat pagi, {user_name}! ☀️ *ASKA* doain harimu sesegar kopi pertama ☕",
        "Morning {user_name}! ☀️ *ASKA* siap bikin pagi kamu makin produktif 🚀",
        "Hai pagi, {user_name}! Yuk mulai hari dengan info valid dari *ASKA* 🌅🧠",
        "Pagi, {user_name}! Biar makin on-track, tanya *ASKA* dulu 🌞📋",
        "Rise and shine, {user_name}! *ASKA* ready bantu urusan sekolah kamu 🌤️📚",
        "Pagi ceria, {user_name}! Cek jadwal/seragam/tugas bareng *ASKA* 🗓️✅",
        "Semoga nilai & mood kamu sama-sama naik hari ini, {user_name} 📈😊",
        "Good morning, {user_name}! Butuh pengumuman terbaru? *ASKA* siap spill 🗞️🤖",
        "Pagi-pagi udah rajin, {user_name}? Mantap! *ASKA* temenin cari info 💪🔎",
        "Gaskeun aktivitas dengan data akurat dari *ASKA*, {user_name} ⚡️✅",
    ],
    "siang": [
        "Selamat siang, {user_name}! Jangan lupa makan dulu, *ASKA* jagain infonya 🍽️🤖",
        "Siang {user_name}! *ASKA* standby kalau butuh update sekolah 🌤️📚",
        "Halo siang, {user_name}! Mau lanjut urusan sekolah? Spill ke *ASKA* ☀️💬",
        "Siang gini enaknya ngerapiin agenda, {user_name}. *ASKA* bantuin ya 🗂️🕑",
        "Good afternoon, {user_name}! Cek pengumuman atau jadwal bareng *ASKA* 🗓️📰",
        "Siang produktif, {user_name}! *ASKA* siap jawab yang bikin bingung 💡🙌",
        "Minum air dulu, {user_name}, lanjut tanya *ASKA* biar fokus 💧🧠",
        "Lagi di sekolah, {user_name}? *ASKA* bisa cek info cepat untukmu 🏫⚡️",
        "Siang cerah, info juga harus terang. Tanya *ASKA* ya, {user_name} 🌞🔍",
        "Mau kirim izin/agenda, {user_name}? *ASKA* kasih panduan singkat ✉️📌",
    ],
    "sore": [
        "Selamat sore, {user_name}! Saatnya wrap-up bareng *ASKA* 🌇📋",
        "Sore vibes, {user_name}! *ASKA* siap bantu beresin agenda hari ini 🌆🤖",
        "Hai sore, {user_name}! Butuh rekap info sekolah? *ASKA* bantu 🌄📝",
        "Sore-sore waktunya cek tugas besok, {user_name}. *ASKA* temenin 🌤️✅",
        "Sore chill, {user_name}, info tetap clear. Tanyain ke *ASKA* aja ✨🔎",
        "Ada ekskul, {user_name}? *ASKA* bisa cekin detailnya 🏀🎶",
        "Biar pulang tenang, {user_name}, pastiin infonya valid via *ASKA* 🏠✅",
        "Perlu ringkas pengumuman hari ini, {user_name}? *ASKA* ringkasin 🗞️✂️",
        "Waktunya wind down, {user_name}. *ASKA* bantu planning to-do besok 🗒️🕟",
        "Sebelum magrib, {user_name}, cek checklist bareng *ASKA* 🌇📝",
    ],
    "malam": [
        "Selamat malam, {user_name}! 🌙 Urusan info sekolah biar *ASKA* yang handle 😴",
        "Malam {user_name}! Yuk tutup hari dengan data akurat *ASKA* 🌌📊",
        "Halo malam, {user_name}! Kalau masih ada PR info sekolah, tanya *ASKA* 🌛💬",
        "Good evening, {user_name}! Siapkan seragam & jadwal, *ASKA* bantu cek 🧺🗓️",
        "Malam produktif, {user_name}? Boleh. *ASKA* siap cari referensi 📚✨",
        "Minum hangat, {user_name}, lalu cek checklist besok bareng *ASKA* 🍵🕘",
        "Malam-malam kepo pengumuman, {user_name}? *ASKA* bisa spill terbaru 🌙🗞️",
        "Time to recharge, {user_name}. Sebelum tidur, cek to-do bareng *ASKA* 🔋📝",
        "Malam hening, info tetap jernih. Tanyain *ASKA*, {user_name} 🌃🔍",
        "Good night, {user_name}! Semoga mimpi indah, besok kita gas lagi 🌠🚀",
    ],
}


# ─────────────────────────────────────────────────────────
# 3) Util: infer periode waktu dari jam lokal Asia/Jakarta
def _infer_period_from_clock(now: datetime | None = None) -> str:
    """
    pagi: 04:00–10:59
    siang: 11:00–14:59
    sore: 15:00–18:29
    malam: 18:30–03:59
    """
    if now is None:
        try:
            now = datetime.now(ZoneInfo("Asia/Jakarta"))
        except Exception:
            now = datetime.now()
    h, m = now.hour, now.minute
    total = h * 60 + m
    if 4 * 60 <= total <= 10 * 60 + 59:
        return "pagi"
    if 11 * 60 <= total <= 14 * 60 + 59:
        return "siang"
    if 15 * 60 <= total <= 18 * 60 + 29:
        return "sore"
    return "malam"


# ─────────────────────────────────────────────────────────
# 4) Deteksi sapaan waktu dari teks (dipersempit agar tidak false positive)
def _detect_time_greeting(text: str) -> str | None:
    if not text:
        return None

    lowered = text.lower()
    tokens = tokenize(lowered)

    # Jika ada indikasi pertanyaan, jangan anggap salam waktu
    if "?" in lowered or (tokens & QUESTION_TOKENS):
        return None

    # Cek frasa salam eksplisit (selamat pagi, good evening, dst.)
    for period, phrases in TIME_GREETING_PATTERNS.items():
        if any(phrase in lowered for phrase in phrases):
            return period

    # Untuk kata kunci waktu (pagi/siang/sore/malam/morning/...), anggap salam
    # hanya bila:
    #   - kata waktu berada di awal kalimat, dan
    #   - panjang kalimat pendek (≤ 3 kata)
    # Ini mencegah "pagi ini ada rapat..." dianggap sebagai salam.
    words = re.findall(r"\w+", lowered)
    for period, keywords in TIME_GREETING_KEYWORDS.items():
        if words and words[0] in keywords and len(words) <= 3:
            return period

    return None


def get_time_based_greeting_response(
    text: str, user_name: Optional[str] = None
) -> str | None:
    period = _detect_time_greeting(text)
    if not period:
        return None
    options = TIME_GREETING_RESPONSES.get(period)
    if not options:
        return None
    response = random.choice(options)
    return response.format(user_name=user_name or "bestie")


def get_contextual_greeting_response(
    text: str | None = None,
    now: datetime | None = None,
    user_name: Optional[str] = None,
) -> str:
    """
    Gunakan ini kalau ingin sapaan terasa kontekstual:
    - Jika teks berisi salam waktu → pakai respons waktu.
    - Jika tidak → fallback ke waktu jam lokal Asia/Jakarta.
    """
    if text:
        resp = get_time_based_greeting_response(text, user_name=user_name)
        if resp:
            return resp
    period = _infer_period_from_clock(now)
    options = TIME_GREETING_RESPONSES.get(period)
    if options:
        response = random.choice(options)
        return response.format(user_name=user_name or "bestie")
    return get_greeting_response(user_name=user_name)


# ─────────────────────────────────────────────────────────
# 5) Deteksi apakah sebuah pesan adalah "pure greeting"
def is_greeting_message(text: str) -> bool:
    """
    Mengembalikan True hanya jika pesan adalah sapaan "murni".
    Aturan utama:
      - Jika ada penanda pertanyaan (token tanya atau '?') → BUKAN greeting.
      - 'p' dihitung greeting hanya bila pesan sangat pendek.
      - Kata/Frasa salam umum diizinkan bila panjang kalimat pendek (≤3 kata).
      - Salam waktu diizinkan bila ada frasa eksplisit atau kata waktu
        berada di awal kalimat dan kalimatnya pendek (≤3 kata).
    """
    if not text:
        return False

    lowered = text.lower().strip()
    tokens = tokenize(lowered)

    # Kalau ada indikasi bertanya → bukan greeting
    if "?" in lowered or (tokens & QUESTION_TOKENS):
        return False

    # Perlakukan 'p' / 'permisi' sebagai greeting bila pesan memang pendek/salam
    if lowered in {"p", "permisi", "permisi min", "permisi kak"} or tokens == {"p"}:
        return True

    # Frasa sapaan eksplisit
    if any(phrase in lowered for phrase in GREETING_PHRASES):
        # Batasi supaya tidak menelan kalimat panjang non-salam
        words = re.findall(r"\w+", lowered)
        return (
            len(words) <= 6
        )  # frasa salam + 1–2 kata tambahan (mis. "selamat pagi min")

    # Kata salam umum (tanpa waktu) → hanya kalau pesan pendek
    if GREETING_KEYWORDS_SET & tokens:
        words = re.findall(r"\w+", lowered)
        return len(words) <= 3

    # Salam waktu yang dipersempit
    return _detect_time_greeting(lowered) is not None


# ─────────────────────────────────────────────────────────
# 6) Ambil respons sapaan generik (kompatibilitas lama)
def get_greeting_response(user_name: Optional[str] = None) -> str:
    response = random.choice(GREETING_RESPONSES)
    return response.format(user_name=user_name or "bestie")


def get_qa_only_greeting_response(user_name: Optional[str] = None) -> str:
    response = random.choice(QA_ONLY_GREETING_RESPONSES)
    return response.format(user_name=user_name or "bestie")
