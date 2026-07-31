"""Variasi jawaban saat provider LLM sedang rate-limit atau kuota habis."""

from __future__ import annotations

import random

RATE_LIMIT_RESPONSES: tuple[str, ...] = (
    "Maaf ya, ASKA lagi agak kewalahan karena yang nanya rame banget sampai antreannya numpuk 😵‍💫💬\n"
    "Coba tanya lagi beberapa saat lagi ya. 🙏✨",
    "ASKA lagi kena lampu merah dulu nih, request yang masuk lagi padat merayap 🚦🛵\n"
    "Tunggu sebentar, terus kirim ulang ya.",
    "Waduh, jalur server ASKA lagi penuh karena banyak yang tanya barengan 😅⚡\n"
    "Coba lagi beberapa menit lagi biar jawabannya tetap stabil.",
    "ASKA lagi mode isi napas dulu, kuota jawab gratisannya lagi kepakai rame-rame 🫠📚\n"
    "Tanya ulang sebentar lagi ya.",
    "Sebentar ya, ASKA lagi ke-limit karena traffic chat lagi rame pol 🚀💥\n"
    "Coba lagi nanti pas antreannya mulai longgar.",
    "ASKA belum bisa jawab sekarang karena batas pemakaian sementaranya lagi mentok 😵‍💫📶\n"
    "Coba ulang beberapa saat lagi ya.",
    "Lagi jam sibuk di markas ASKA, chat masuknya pada ngegas semua 🏃‍♂️💬\n"
    "Tunggu sebentar, habis itu tanya lagi ya.",
    "Maaf, antrean jawaban ASKA lagi penuh banget karena banyak user aktif barengan 🙏💫\n"
    "Coba beberapa saat lagi, biar ASKA bisa jawab lebih aman.",
    "ASKA lagi kena batas layanan sementara, vibes-nya kayak WiFi sekolah pas semua login 😬📡\n"
    "Santai, coba kirim lagi beberapa saat lagi ya.",
    "Chat yang masuk lagi rame pol, jadi ASKA perlu jeda biar nggak jawab asal-asalan 😵‍💫🔥\n"
    "Coba tanya lagi nanti ya.",
)


def get_rate_limit_response() -> str:
    return random.choice(RATE_LIMIT_RESPONSES)
