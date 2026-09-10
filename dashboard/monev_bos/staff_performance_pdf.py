"""PDF evidence report for Monev BOS/BOP staff performance."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT, MARGIN = 1240, 1754, 70
INK, MUTED, PRIMARY = "#172033", "#667085", "#0d6efd"
LIGHT, BORDER = "#f5f8fc", "#d8e0eb"


def _font(size: int, bold: bool = False):
    candidates = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for candidate in candidates:
        try:
            if not candidate.startswith("/") or Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _clean(value: Any, fallback: str = "-") -> str:
    value = " ".join(str(value or "").split())
    return value or fallback


def _fit(draw, value: Any, font, width: int) -> str:
    value = _clean(value)
    if draw.textbbox((0, 0), value, font=font)[2] <= width:
        return value
    while value and draw.textbbox((0, 0), value + "...", font=font)[2] > width:
        value = value[:-1]
    return value.rstrip() + "..."


def _date(value: Any) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if isinstance(value, datetime) else "-"


def _page(heading: str, period_label: str, generated_at: datetime, number: int):
    page = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(page)
    draw.text((MARGIN, 55), "LAPORAN PERFORMA STAFF", font=_font(29, True), fill=PRIMARY)
    draw.text((MARGIN, 105), heading, font=_font(22, True), fill=INK)
    draw.text((MARGIN, 145), f"Periode: {period_label}", font=_font(16), fill=MUTED)
    draw.text((WIDTH - MARGIN, 65), f"Dibuat: {_date(generated_at)} WIB", font=_font(14), fill=MUTED, anchor="ra")
    draw.text((WIDTH - MARGIN, 100), f"Halaman {number}", font=_font(14), fill=MUTED, anchor="ra")
    draw.line((MARGIN, 190, WIDTH - MARGIN, 190), fill=BORDER, width=3)
    return page, draw, 225


def _footer(draw, text: str):
    draw.line((MARGIN, HEIGHT - 72, WIDTH - MARGIN, HEIGHT - 72), fill=BORDER, width=2)
    draw.text((MARGIN, HEIGHT - 52), text, font=_font(12), fill=MUTED)


def _leaderboard_window(rows, staff_id: int, limit: int = 25):
    """Return the downloader with up to 12 ranks above and below."""
    rows = list(rows)
    if len(rows) <= limit:
        return rows
    current_index = next(
        (index for index, row in enumerate(rows) if int(row.get("staff_id") or 0) == int(staff_id)),
        None,
    )
    if current_index is None:
        return rows[:limit]
    half = limit // 2
    start = max(0, current_index - half)
    end = min(len(rows), start + limit)
    start = max(0, end - limit)
    return rows[start:end]


def _leaderboard_page(rows, period_label, generated_at, number, downloader_id):
    page, draw, y = _page(
        "LEADERBOARD STAFF",
        period_label, generated_at, number,
    )
    draw.rounded_rectangle((MARGIN, y, WIDTH - MARGIN, y + 64), radius=10, fill="#eaf2ff")
    draw.text((MARGIN + 18, y + 20), "Maksimal 25 peringkat: staff pengunduh, 12 di atas, dan 12 di bawah.", font=_font(14), fill="#194f9b")
    y += 88
    columns = [
        ("Rank", MARGIN, 65), ("Staff", MARGIN + 65, 260),
        ("Skor", MARGIN + 325, 70), ("Kegiatan", MARGIN + 395, 95),
        ("Vendor/Narsum", MARGIN + 490, 125), ("Laporan", MARGIN + 615, 90),
        ("Foto", MARGIN + 705, 65), ("Hari Aktif", MARGIN + 770, 100),
        ("Aksi Terakhir", MARGIN + 870, 230),
    ]
    draw.rectangle((MARGIN, y, WIDTH - MARGIN, y + 46), fill="#dce9fb")
    for label, x, _ in columns:
        draw.text((x + 7, y + 13), label, font=_font(13, True), fill=INK)
    y += 48
    if not rows:
        draw.text((MARGIN + 8, y + 18), "Belum ada aktivitas staff pada periode ini.", font=_font(15), fill=MUTED)
    for index, row in enumerate(rows):
        is_downloader = int(row.get("staff_id") or 0) == int(downloader_id or 0)
        if is_downloader:
            draw.rectangle((MARGIN, y, WIDTH - MARGIN, y + 50), fill="#dbeafe")
        elif index % 2:
            draw.rectangle((MARGIN, y, WIDTH - MARGIN, y + 50), fill=LIGHT)
        values = [
            f"#{row.get('rank')}", row.get("staff_name") or "Staff",
            row.get("score", 0), row.get("validated_activities", 0),
            row.get("vendor_decisions", 0), row.get("completed_reports", 0), row.get("uploaded_photos", 0),
            row.get("active_days", 0), _date(row.get("last_action_at")),
        ]
        row_font = _font(13, is_downloader)
        row_color = PRIMARY if is_downloader else INK
        for value, (_, x, width) in zip(values, columns):
            draw.text((x + 7, y + 15), _fit(draw, value, row_font, width - 12), font=row_font, fill=row_color)
        draw.line((MARGIN, y + 50, WIDTH - MARGIN, y + 50), fill=BORDER, width=1)
        y += 50
    _footer(draw, "Skor = kegiatan + vendor/narasumber + laporan + foto + aksi pendukung. Semua berbobot 1.")
    return page


def _personal_page(personal, downloader, period_label, generated_at, number):
    page, draw, y = _page("REKAP PERFORMA PRIBADI", period_label, generated_at, number)
    summary = personal.get("summary") or {}
    name = _clean(downloader.get("full_name"), "Staff")
    draw.rounded_rectangle((MARGIN, y, WIDTH - MARGIN, y + 98), radius=13, fill="#f1f6ff", outline=BORDER, width=2)
    draw.text((MARGIN + 20, y + 18), name, font=_font(21, True), fill=INK)
    draw.text((MARGIN + 20, y + 57), "Staff Verifikator Monev BOS/BOP", font=_font(14), fill=MUTED)
    rank = summary.get("rank")
    rank_label = f"Peringkat #{rank}" if rank else "Belum masuk leaderboard"
    draw.text((WIDTH - MARGIN - 20, y + 32), rank_label, font=_font(17, True), fill=PRIMARY, anchor="ra")
    y += 125
    metrics = [
        ("Total Skor", summary.get("score", 0)),
        ("Kegiatan Divalidasi", summary.get("validated_activities", 0)),
        ("Vendor/Narasumber", summary.get("vendor_decisions", 0)),
        ("Laporan Diselesaikan", summary.get("completed_reports", 0)),
        ("Foto Lapangan", summary.get("uploaded_photos", 0)),
        ("Hari Aktif", summary.get("active_days", 0)),
    ]
    gap = 14
    card_width = (WIDTH - 2 * MARGIN - gap * (len(metrics) - 1)) // len(metrics)
    for index, (label, value) in enumerate(metrics):
        x = MARGIN + index * (card_width + gap)
        draw.rounded_rectangle((x, y, x + card_width, y + 105), radius=11, fill=LIGHT, outline=BORDER, width=2)
        draw.text((x + 14, y + 14), _fit(draw, label, _font(12), card_width - 28), font=_font(12), fill=MUTED)
        draw.text((x + 14, y + 52), str(value or 0), font=_font(22, True), fill=PRIMARY)
    y += 135
    draw.text((MARGIN, y), "Rincian Jenis Aksi", font=_font(17, True), fill=INK)
    y += 38
    action_labels = {
        "VALIDATE": "Validasi kegiatan", "UPDATE_STATUS": "Penyelesaian laporan",
        "UPLOAD_PHOTO": "Upload foto lapangan", "ANNUL_SCHOOL_PHOTO": "Anulir foto sekolah",
        "RESTORE_SCHOOL_PHOTO": "Pulihkan foto sekolah", "DELETE_PHOTO": "Hapus foto staff",
        "VERIFY_APPROVE": "Verifikasi vendor/narasumber", "VERIFY_REJECT": "Tolak vendor/narasumber",
    }
    action_counts = personal.get("action_counts") or []
    for index, row in enumerate(action_counts[:10]):
        x = MARGIN + (index % 2) * 550
        row_y = y + (index // 2) * 38
        label = action_labels.get(row.get("action"), str(row.get("action") or "-").replace("_", " ").title())
        draw.text((x + 8, row_y), _fit(draw, f"{label}: {row.get('count') or 0}", _font(13), 500), font=_font(13), fill=INK)
    y += max(1, (min(len(action_counts), 10) + 1) // 2) * 38 + 25
    draw.text(
        (MARGIN, y),
        f"Aktivitas pertama: {_date(summary.get('first_action_at'))}    |    Aktivitas terakhir: {_date(summary.get('last_action_at'))}",
        font=_font(13), fill=MUTED,
    )
    y += 40
    draw.text((MARGIN, y), "Sekolah dan TW yang Dikerjakan", font=_font(17, True), fill=INK)
    y += 38
    columns = [("Sekolah", MARGIN, 410), ("TW/Tahun", MARGIN + 410, 280), ("Kegiatan", MARGIN + 690, 110), ("Aksi", MARGIN + 800, 100), ("Terakhir", MARGIN + 900, 200)]
    draw.rectangle((MARGIN, y, WIDTH - MARGIN, y + 42), fill="#dce9fb")
    for label, x, _ in columns:
        draw.text((x + 7, y + 12), label, font=_font(13, True), fill=INK)
    y += 44
    schools = personal.get("school_summaries") or []
    if not schools:
        draw.text((MARGIN + 8, y + 16), "Belum ada sekolah yang dikerjakan pada periode ini.", font=_font(14), fill=MUTED)
    for index, row in enumerate(schools[:20]):
        if index % 2:
            draw.rectangle((MARGIN, y, WIDTH - MARGIN, y + 38), fill=LIGHT)
        values = [row.get("school_name"), row.get("periods"), row.get("validated_activities", 0), row.get("action_count", 0), _date(row.get("last_action_at"))]
        for value, (_, x, width) in zip(values, columns):
            draw.text((x + 7, y + 11), _fit(draw, value, _font(11), width - 12), font=_font(11), fill=INK)
        y += 38
    if len(schools) > 20:
        draw.text((MARGIN + 8, y + 10), f"+{len(schools) - 20} sekolah lainnya", font=_font(12, True), fill=PRIMARY)
    _footer(draw, "Rekap pribadi dibuat untuk akun staff yang mengunduh dokumen ini.")
    return page


def _recent_activity_page(personal, period_label, generated_at, number):
    page, draw, y = _page("AKTIVITAS TERBARU", period_label, generated_at, number)
    recent = personal.get("recent_actions") or []
    draw.text(
        (MARGIN, y),
        "Menampilkan maksimal 34 aktivitas terbaru pada periode yang dipilih.",
        font=_font(14), fill=MUTED,
    )
    y += 38
    columns = [
        ("Waktu", MARGIN, 175),
        ("Sekolah", MARGIN + 175, 275),
        ("Aksi", MARGIN + 450, 220),
        ("Kegiatan/Objek", MARGIN + 670, 430),
    ]
    draw.rectangle((MARGIN, y, WIDTH - MARGIN, y + 42), fill="#dce9fb")
    for label, x, _ in columns:
        draw.text((x + 7, y + 12), label, font=_font(13, True), fill=INK)
    y += 44
    action_labels = {
        "VALIDATE": "Validasi kegiatan",
        "UPDATE_STATUS": "Penyelesaian laporan",
        "UPLOAD_PHOTO": "Upload foto lapangan",
        "ANNUL_SCHOOL_PHOTO": "Anulir foto sekolah",
        "RESTORE_SCHOOL_PHOTO": "Pulihkan foto sekolah",
        "DELETE_PHOTO": "Hapus foto staff",
        "VERIFY_APPROVE": "Verifikasi vendor/narasumber",
        "VERIFY_REJECT": "Tolak vendor/narasumber",
    }
    if not recent:
        draw.text((MARGIN + 8, y + 16), "Belum ada aktivitas pada periode ini.", font=_font(14), fill=MUTED)
    for index, row in enumerate(recent[:34]):
        if index % 2:
            draw.rectangle((MARGIN, y, WIDTH - MARGIN, y + 39), fill=LIGHT)
        raw_action = row.get("action")
        action_label = action_labels.get(raw_action, str(raw_action or "-").replace("_", " ").title())
        values = [_date(row.get("created_at")), row.get("school_name"), action_label, row.get("activity_name")]
        for value, (_, x, width) in zip(values, columns):
            draw.text((x + 7, y + 11), _fit(draw, value, _font(11), width - 12), font=_font(11), fill=INK)
        y += 39
    _footer(draw, "Urutan berdasarkan waktu aktivitas terbaru pada periode yang dipilih.")
    return page


def build_staff_performance_pdf(*, leaderboard: Iterable[Dict[str, Any]], personal: Dict[str, Any], downloader: Dict[str, Any], period_label: str, generated_at: datetime) -> io.BytesIO:
    rows = list(leaderboard)
    downloader_id = int(downloader.get("id") or 0)
    visible_rows = _leaderboard_window(rows, downloader_id, limit=25)
    pages: List[Image.Image] = [
        _leaderboard_page(visible_rows, period_label, generated_at, 1, downloader_id),
        _personal_page(personal, downloader, period_label, generated_at, 2),
        _recent_activity_page(personal, period_label, generated_at, 3),
    ]
    output = io.BytesIO()
    pages[0].save(output, format="PDF", resolution=150, save_all=True, append_images=pages[1:], title=f"Performa Staff - {period_label}", author="ASKA Dashboard")
    output.seek(0)
    return output
