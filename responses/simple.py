from __future__ import annotations

import ast
import operator
import random
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


_WHY_FALLBACK_PATTERNS = (
    "kenapa gk bisa jawab",
    "kenapa ga bisa jawab",
    "kenapa gak bisa jawab",
    "kenapa nggak bisa jawab",
    "kenapa tidak bisa jawab",
    "kenapa belum bisa jawab",
    "kok gk bisa jawab",
    "kok ga bisa jawab",
    "kok gak bisa jawab",
    "kok nggak bisa jawab",
    "kok tidak bisa jawab",
    "gk bisa jawab",
    "ga bisa jawab",
    "gak bisa jawab",
    "nggak bisa jawab",
    "tidak bisa jawab",
)

_WHY_FALLBACK_RESPONSES = [
    "*ASKA* sengaja nggak nebak kalau datanya belum ketemu di dokumen resmi, biar nggak ngarang 😅📚\n\nCoba pakai kata kunci yang lebih spesifik, misalnya nama sekolah, jenjang, jalur, atau kelurahan.",
    "Bukan cuek ya 😅 *ASKA* lagi mode data resmi. Kalau konteksnya kurang kuat, aku tahan jawaban supaya nggak halu 📌\n\nCoba tanya dengan detail sekolah/jenjang/jalur biar lebih kebaca.",
    "*ASKA* bisa jawab kalau datanya nyambung sama dokumen resmi. Kalau belum ketemu, aku pilih aman daripada sok tahu 😭✅\n\nDrop detailnya lagi: sekolah apa, wilayah mana, atau topik SPMB yang mana?",
]

_KNOWLEDGE_CONTEXT_KEYWORDS = {
    "spmb",
    "ppdb",
    "pmb",
    "sekolah",
    "sd",
    "sdn",
    "smp",
    "smpn",
    "sma",
    "sman",
    "smk",
    "smkn",
    "negeri",
    "swasta",
    "prioritas",
    "perioritas",
    "jalur",
    "domisili",
    "kelurahan",
    "kecamatan",
    "rw",
    "rt",
    "zonasi",
    "jadwal",
    "pendaftaran",
    "daftar",
    "verifikasi",
    "kjp",
    "kip",
    "kartu jakarta pintar",
    "posko",
    "call center",
}

_MOOD_PATTERNS = (
    "apa kabar",
    "gimana kabarnya",
    "gmna kabarnya",
    "kabar kamu",
)

_TEST_PATTERNS = (
    "tes",
    "test",
    "testing",
    "ping",
    "coba",
)

_CAN_ANSWER_PATTERNS = (
    "lagi apa",
    "lagi ngapain",
    "ngapain",
    "bisa jawab",
    "jawab dong",
    "respon dong",
)

_MOOD_RESPONSES = [
    "*ASKA* baik, mode sat-set aktif 🚀 Kamu mau tanya ringan atau cek info sekolah?",
    "Aman terkendali 😄 *ASKA* standby. Kalau info sekolah/SPMB, aku cek dokumen resmi dulu ya 📚",
    "Baik nih 🤖✨ Siap bantu yang ringan, dan kalau soal sekolah aku cocokkan ke kecerdasan dulu.",
]

_TEST_RESPONSES = [
    "Tes berhasil. *ASKA* nyala 🔥 Mau tanya ringan boleh, mau tanya sekolah juga boleh.",
    "Masuk, kebaca jelas 😄 *ASKA* standby. Pertanyaan ringan boleh, info sekolah tetap aku cek dari data resmi 📌",
    "Ping kebalas. *ASKA* online dan siap bantu 🤖✅",
]

_CAN_ANSWER_RESPONSES = [
    "*ASKA* aman, online, dan siap bantu. Kalau pertanyaannya data sekolah/SPMB, aku cek dokumen resmi dulu ya 🤖📚",
    "Bisa. Pertanyaan ringan *ASKA* jawab langsung; kalau data sekolah/SPMB, aku cek kecerdasan dulu biar valid 📌",
    "Bisa jawab, tapi *ASKA* tetap bedain: pertanyaan ringan dijawab langsung, data sekolah dicek dari kecerdasan dulu 📌",
]

_TIME_PATTERNS = (
    "jam berapa",
    "sekarang jam",
    "pukul berapa",
)

_DATE_PATTERNS = (
    "tanggal berapa",
    "hari apa",
    "hari ini apa",
    "tanggal hari ini",
    "sekarang tanggal",
)

_DAY_NAMES = (
    "Senin",
    "Selasa",
    "Rabu",
    "Kamis",
    "Jumat",
    "Sabtu",
    "Minggu",
)

_MONTH_NAMES = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)

_MATH_WORD_REPLACEMENTS = (
    (r"\bditambah\b|\btambah\b|\bplus\b", "+"),
    (r"\bdikurangi\b|\bkurang\b|\bminus\b", "-"),
    (r"\bdikali\b|\bkali\b|\bx\b|×", "*"),
    (r"\bdibagi\b|\bbagi\b|÷", "/"),
)

_FILLER_WORDS = (
    "berapa",
    "hasil",
    "hasilnya",
    "hitung",
    "hitungin",
    "tolong",
    "dong",
    "ya",
    "yah",
    "kak",
    "min",
    "nih",
    "sih",
    "ask",
    "aska",
)

_ALLOWED_MATH_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
    ast.Load,
)

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _requires_knowledge_context(text: str) -> bool:
    lowered = text.lower()
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", lowered)
        for keyword in _KNOWLEDGE_CONTEXT_KEYWORDS
    )


def is_why_fallback_question(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(pattern in lowered for pattern in _WHY_FALLBACK_PATTERNS)


def get_why_fallback_response() -> str:
    return random.choice(_WHY_FALLBACK_RESPONSES)


def _normalize_math_expression(text: str) -> str | None:
    lowered = text.lower()
    for pattern, replacement in _MATH_WORD_REPLACEMENTS:
        lowered = re.sub(pattern, replacement, lowered)

    for word in _FILLER_WORDS:
        lowered = re.sub(rf"\b{re.escape(word)}\b", " ", lowered)

    lowered = lowered.replace(",", ".")
    lowered = re.sub(r"[^0-9+\-*/().\s]", " ", lowered)
    expression = re.sub(r"\s+", "", lowered)

    if not expression:
        return None
    if not re.search(r"[+\-*/]", expression):
        return None
    if len(expression) > 80:
        return None
    if re.search(r"[+\-*/]{2,}", expression.replace("+-", "+").replace("-+", "+")):
        return None
    return expression


def _eval_math_node(node: ast.AST) -> float:
    if not isinstance(node, _ALLOWED_MATH_NODES):
        raise ValueError("unsupported expression")

    if isinstance(node, ast.Expression):
        return _eval_math_node(node.body)

    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError("unsupported constant")
        return float(node.value)

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        operation = _BIN_OPS.get(op_type)
        if operation is None:
            raise ValueError("unsupported operator")
        right = _eval_math_node(node.right)
        if op_type is ast.Div and right == 0:
            raise ZeroDivisionError
        return operation(_eval_math_node(node.left), right)

    if isinstance(node, ast.UnaryOp):
        operation = _UNARY_OPS.get(type(node.op))
        if operation is None:
            raise ValueError("unsupported unary")
        return operation(_eval_math_node(node.operand))

    raise ValueError("unsupported expression")


def _format_number(value: float) -> str:
    try:
        decimal_value = Decimal(str(value)).normalize()
    except InvalidOperation:
        return str(value)
    if decimal_value == decimal_value.to_integral():
        return str(decimal_value.quantize(Decimal(1)))
    return format(decimal_value, "f").rstrip("0").rstrip(".")


def get_simple_math_response(text: str) -> str | None:
    expression = _normalize_math_expression(text)
    if not expression:
        return None
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_math_node(tree)
    except ZeroDivisionError:
        return "*ASKA* hitung cepat: pembagian dengan nol nggak bisa ya 😅🧮"
    except Exception:
        return None

    if abs(result) > 1_000_000_000:
        return None

    readable_expression = (
        expression.replace("*", " × ")
        .replace("/", " ÷ ")
        .replace("+", " + ")
        .replace("-", " - ")
    )
    readable_expression = re.sub(r"\s+", " ", readable_expression).strip()
    return f"*ASKA* hitung cepat: {readable_expression} = {_format_number(result)} 🧮✨"


def get_datetime_response(text: str) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    if not any(pattern in lowered for pattern in _TIME_PATTERNS + _DATE_PATTERNS):
        return None

    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    day_name = _DAY_NAMES[now.weekday()]
    month_name = _MONTH_NAMES[now.month - 1]

    asks_time = any(pattern in lowered for pattern in _TIME_PATTERNS)
    asks_date = any(pattern in lowered for pattern in _DATE_PATTERNS)

    if asks_time and asks_date:
        return (
            f"Sekarang {day_name}, {now.day} {month_name} {now.year}, "
            f"pukul {now:%H:%M} WIB 🕒✨"
        )
    if asks_time:
        return f"Sekarang pukul {now:%H:%M} WIB 🕒"
    return f"Hari ini {day_name}, {now.day} {month_name} {now.year} 📅"


def get_casual_light_response(text: str) -> str | None:
    if not text:
        return None
    lowered = text.lower().strip()
    if len(lowered.split()) > 8:
        return None
    if any(pattern in lowered for pattern in _MOOD_PATTERNS):
        return random.choice(_MOOD_RESPONSES)
    if any(pattern in lowered for pattern in _TEST_PATTERNS):
        return random.choice(_TEST_RESPONSES)
    if any(pattern in lowered for pattern in _CAN_ANSWER_PATTERNS):
        return random.choice(_CAN_ANSWER_RESPONSES)
    return None


def get_simple_response(text: str) -> str | None:
    if is_why_fallback_question(text):
        return get_why_fallback_response()

    if _requires_knowledge_context(text):
        return None

    math_response = get_simple_math_response(text)
    if math_response:
        return math_response

    datetime_response = get_datetime_response(text)
    if datetime_response:
        return datetime_response

    casual_response = get_casual_light_response(text)
    if casual_response:
        return casual_response

    return None
