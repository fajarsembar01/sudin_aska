# responses/base.py
from .rate_limit import RATE_LIMIT_RESPONSES

ASKA_NO_DATA_RESPONSE = (
    "😅 Maaf nih, *ASKA* belum nemu jawabannya di data sekolah.\n"
    "☎️ Coba hubungi langsung sekolah ya di (021) 4406363."
)

ASKA_TECHNICAL_ISSUE_RESPONSE = (
    "⚠️ Maaf, lagi ada gangguan teknis 🛠️\n"
    "🤖 Coba tanya *ASKA* nanti ya~ 🙏"
)

ASKA_RATE_LIMIT_RESPONSE = (
    RATE_LIMIT_RESPONSES[0]
)
