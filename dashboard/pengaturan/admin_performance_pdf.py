"""Compact PDF report for the Admin Performance dashboard."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from PIL import Image, ImageDraw, ImageFont


PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
MARGIN = 70
INK = "#172033"
MUTED = "#667085"
PRIMARY = "#0d6efd"
LIGHT = "#f5f8fc"
BORDER = "#d8e0eb"


def _font(size: int, *, bold: bool = False):
    names = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for name in names:
        try:
            if not name.startswith("/") or Path(name).exists():
                return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _clean(value: Any, fallback: str = "-") -> str:
    text = "" if value is None else " ".join(str(value).split())
    return text or fallback


def _fit(draw: ImageDraw.ImageDraw, value: Any, font, width: int) -> str:
    text = _clean(value)
    if draw.textbbox((0, 0), text, font=font)[2] <= width:
        return text
    suffix = "..."
    while text and draw.textbbox((0, 0), text + suffix, font=font)[2] > width:
        text = text[:-1]
    return text.rstrip() + suffix


def _wrap(draw: ImageDraw.ImageDraw, value: Any, font, width: int) -> List[str]:
    """Wrap cell text without dropping feature labels."""
    words = _clean(value).split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or ["-"]


def _date_label(value: Any, *, with_time: bool = True) -> str:
    if not isinstance(value, datetime):
        return "-"
    return value.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")


def _new_page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    page = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
    return page, ImageDraw.Draw(page)


def _draw_header(
    draw: ImageDraw.ImageDraw,
    *,
    heading: str,
    period_label: str,
    generated_at: datetime,
    page_number: int,
) -> int:
    draw.text((MARGIN, 55), "LAPORAN PERFORMA ADMIN", font=_font(29, bold=True), fill=PRIMARY)
    draw.text((MARGIN, 105), heading, font=_font(22, bold=True), fill=INK)
    draw.text((MARGIN, 145), f"Periode: {period_label}", font=_font(16), fill=MUTED)
    draw.text(
        (PAGE_WIDTH - MARGIN, 65),
        f"Dibuat: {_date_label(generated_at)} WIB",
        font=_font(14),
        fill=MUTED,
        anchor="ra",
    )
    draw.text(
        (PAGE_WIDTH - MARGIN, 100),
        f"Halaman {page_number}",
        font=_font(14),
        fill=MUTED,
        anchor="ra",
    )
    draw.line((MARGIN, 190, PAGE_WIDTH - MARGIN, 190), fill=BORDER, width=3)
    return 225


def _draw_footer(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.line((MARGIN, PAGE_HEIGHT - 72, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 72), fill=BORDER, width=2)
    draw.text((MARGIN, PAGE_HEIGHT - 52), text, font=_font(12), fill=MUTED)


def _draw_leaderboard_page(
    rows: List[Dict[str, Any]],
    *,
    downloader_id: int,
    feature_options: Dict[str, str],
    period_label: str,
    generated_at: datetime,
    page_number: int,
    filters_label: str,
    continuation: bool,
) -> Image.Image:
    page, draw = _new_page()
    y = _draw_header(
        draw,
        heading="LEADERBOARD ADMIN" + (" (lanjutan)" if continuation else ""),
        period_label=period_label,
        generated_at=generated_at,
        page_number=page_number,
    )
    note_font = _font(13)
    note = "Leaderboard memuat seluruh admin, termasuk yang skornya 0; pilihan satu admin pada layar diabaikan."
    draw.rounded_rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + 68), radius=12, fill="#eaf2ff")
    draw.text((MARGIN + 18, y + 14), note, font=note_font, fill="#194f9b")
    draw.text((MARGIN + 18, y + 39), _fit(draw, filters_label, note_font, 1040), font=note_font, fill="#194f9b")
    y += 95

    columns = [
        ("No", MARGIN, 45),
        ("Admin", MARGIN + 45, 200),
        ("GitHub", MARGIN + 245, 140),
        ("Skor", MARGIN + 385, 60),
        ("Admin", MARGIN + 445, 70),
        ("Coding", MARGIN + 515, 145),
        ("Fitur", MARGIN + 660, 270),
        ("Aksi Terakhir", MARGIN + 930, 170),
    ]
    draw.rounded_rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + 48), radius=8, fill="#dce9fb")
    header_font = _font(14, bold=True)
    for label, x, _width in columns:
        draw.text((x + 8, y + 14), label, font=header_font, fill=INK)
    y += 52
    if not rows:
        draw.text((MARGIN + 10, y + 18), "Belum ada akun admin.", font=_font(15), fill=MUTED)
    for row in rows:
        feature_counts = row.get("feature_counts") or {}
        feature_text = "; ".join(
            f"{feature_options.get(key, str(key).replace('_', ' ').title())}: {int(count or 0)}"
            for key, count in sorted(
                feature_counts.items(),
                key=lambda item: (-int(item[1] or 0), str(item[0])),
            )
            if int(count or 0) > 0
        ) or "-"
        feature_font = _font(10)
        feature_lines = _wrap(draw, feature_text, feature_font, 258)
        row_height = max(48, 14 + len(feature_lines) * 15)
        is_downloader = int(row.get("actor_user_id") or 0) == int(downloader_id or 0)
        if is_downloader:
            draw.rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + row_height), fill="#dbeafe")
        elif int(row.get("rank") or 0) % 2 == 0:
            draw.rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + row_height), fill=LIGHT)
        row_font = _font(13, bold=is_downloader)
        row_color = PRIMARY if is_downloader else INK
        values = [
            row.get("rank"),
            row.get("actor_label"),
            f"@{row['github_username']}" if row.get("github_username") else "-",
            row.get("performance_total", row.get("total_actions", 0)),
            row.get("total_actions", 0),
            (
                f"{row.get('github_commits', 0)} update/{row.get('coding_score_units', row.get('github_commits', 0))} day"
                if row.get("github_commits") is not None else "-"
            ),
            feature_text,
            _date_label(row.get("last_action_at")),
        ]
        for column_index, (value, (_label, x, width)) in enumerate(zip(values, columns)):
            if column_index == 6:
                for line_index, line in enumerate(feature_lines):
                    draw.text((x + 7, y + 8 + line_index * 15), line, font=feature_font, fill=row_color)
            else:
                draw.text((x + 7, y + 14), _fit(draw, value, row_font, width - 10), font=row_font, fill=row_color)
        draw.line((MARGIN, y + row_height, PAGE_WIDTH - MARGIN, y + row_height), fill=BORDER, width=1)
        y += row_height

    _draw_footer(draw, "Skor = Aksi Admin + (hari aktif Coding x 10). Semua commit pada hari yang sama bernilai 1 hari.")
    return page


def _draw_personal_page(
    personal: Dict[str, Any],
    downloader: Dict[str, Any],
    *,
    period_label: str,
    generated_at: datetime,
    page_number: int,
    filters_label: str,
) -> Image.Image:
    page, draw = _new_page()
    y = _draw_header(
        draw,
        heading="REKAP PERFORMA PRIBADI",
        period_label=period_label,
        generated_at=generated_at,
        page_number=page_number,
    )
    name = _clean(downloader.get("full_name") or downloader.get("email"), "Admin")
    email = _clean(downloader.get("email"))
    draw.rounded_rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + 105), radius=14, fill="#f1f6ff", outline=BORDER, width=2)
    draw.text((MARGIN + 22, y + 18), name, font=_font(21, bold=True), fill=INK)
    draw.text((MARGIN + 22, y + 57), email, font=_font(15), fill=MUTED)
    draw.text((PAGE_WIDTH - MARGIN - 20, y + 25), f"ID Admin: {downloader.get('id') or '-'}", font=_font(14), fill=MUTED, anchor="ra")
    draw.text((PAGE_WIDTH - MARGIN - 20, y + 56), _fit(draw, filters_label, _font(13), 520), font=_font(13), fill=MUTED, anchor="ra")
    y += 135

    summary = personal.get("summary") or {}
    total_actions = int(summary.get("total_actions") or 0)
    active_action_days = len(personal.get("daily_series") or [])
    coding_days = int(personal.get("github_coding_days") or 0)
    coding_commits = int(personal.get("github_commits") or 0)
    coding_points = int(personal.get("coding_points") or coding_days * 10)
    performance_total = int(personal.get("performance_total") or total_actions + coding_points)

    draw.rounded_rectangle((MARGIN, y, MARGIN + 300, y + 138), radius=14, fill="#eaf2ff", outline="#b7d2fb", width=2)
    draw.text((MARGIN + 20, y + 16), "TOTAL SKOR", font=_font(14, bold=True), fill="#194f9b")
    draw.text((MARGIN + 20, y + 48), str(performance_total), font=_font(42, bold=True), fill=PRIMARY)
    rank = personal.get("organization_rank")
    rank_label = f"Peringkat #{rank}" if rank else "Belum masuk leaderboard"
    draw.text((MARGIN + 20, y + 108), rank_label, font=_font(14), fill=MUTED)

    breakdown_x = MARGIN + 325
    draw.rounded_rectangle((breakdown_x, y, PAGE_WIDTH - MARGIN, y + 138), radius=14, fill=LIGHT, outline=BORDER, width=2)
    draw.text((breakdown_x + 20, y + 16), "PERHITUNGAN SKOR", font=_font(14, bold=True), fill=INK)
    draw.text((breakdown_x + 20, y + 50), f"Aksi Admin                 {total_actions:,} poin", font=_font(16), fill=INK)
    draw.text((breakdown_x + 20, y + 82), f"Coding: {coding_days:,} hari x 10       {coding_points:,} poin", font=_font(16), fill=INK)
    draw.line((breakdown_x + 500, y + 25, breakdown_x + 500, y + 113), fill=BORDER, width=2)
    draw.text((breakdown_x + 530, y + 45), "Coding Update/Day", font=_font(13), fill=MUTED)
    draw.text((breakdown_x + 530, y + 76), f"{coding_commits:,} / {coding_days:,} day", font=_font(19, bold=True), fill=PRIMARY)
    y += 165

    metrics = [
        ("Aksi Admin", f"{total_actions:,}"),
        ("Hari Aktif Admin", f"{active_action_days:,}"),
        ("Rata-rata Aksi/Hari", f"{(total_actions / active_action_days):.1f}" if active_action_days else "0"),
        ("Fitur Aktif", f"{int(summary.get('total_features') or 0):,}"),
    ]
    card_gap = 15
    card_width = (PAGE_WIDTH - 2 * MARGIN - (len(metrics) - 1) * card_gap) // len(metrics)
    for index, (label, value) in enumerate(metrics):
        x = MARGIN + index * (card_width + card_gap)
        draw.rounded_rectangle((x, y, x + card_width, y + 94), radius=12, fill=LIGHT, outline=BORDER, width=2)
        draw.text((x + 15, y + 14), label, font=_font(12), fill=MUTED)
        draw.text((x + 15, y + 47), _fit(draw, value, _font(20, bold=True), card_width - 30), font=_font(20, bold=True), fill=PRIMARY)
    y += 118

    line_stats = personal.get("github_line_stats") or {}
    additions = int(line_stats.get("additions") or 0)
    deletions = int(line_stats.get("deletions") or 0)
    changed_lines = int(line_stats.get("changed_lines") or 0)
    measured = int(line_stats.get("measured_commits") or 0)
    total_commits = int(line_stats.get("total_commits") or 0)
    draw.rounded_rectangle(
        (MARGIN, y, PAGE_WIDTH - MARGIN, y + 92),
        radius=12, fill="#eef7f1", outline="#bfd8c7", width=2,
    )
    draw.text((MARGIN + 18, y + 14), "PERUBAHAN BARIS SOURCE CODE", font=_font(14, bold=True), fill="#146c43")
    draw.text((MARGIN + 18, y + 48), f"+{additions:,} ditambah", font=_font(16, bold=True), fill="#198754")
    draw.text((MARGIN + 260, y + 48), f"-{deletions:,} dihapus", font=_font(16, bold=True), fill="#dc3545")
    draw.text((MARGIN + 500, y + 48), f"{changed_lines:,} total berubah", font=_font(16, bold=True), fill=INK)
    draw.text(
        (PAGE_WIDTH - MARGIN - 18, y + 50),
        f"Cakupan {measured}/{total_commits} commit",
        font=_font(12), fill=MUTED, anchor="ra",
    )
    y += 116

    section_font = _font(17, bold=True)
    item_font = _font(13)
    column_width = (PAGE_WIDTH - 2 * MARGIN - 40) // 3
    column_x = [MARGIN, MARGIN + column_width + 20, MARGIN + 2 * (column_width + 20)]
    draw.text((column_x[0], y), "Per Fitur", font=section_font, fill=INK)
    draw.text((column_x[1], y), "Per Aksi", font=section_font, fill=INK)
    draw.text((column_x[2], y), "Per Target", font=section_font, fill=INK)
    y += 35
    feature_rows = personal.get("top_features") or []
    action_rows = personal.get("top_actions") or []
    target_rows = personal.get("top_targets") or []
    for index in range(10):
        values = [
            (feature_rows[index].get("feature_label"), feature_rows[index].get("count")) if index < len(feature_rows) else None,
            (action_rows[index].get("action"), action_rows[index].get("count")) if index < len(action_rows) else None,
            (target_rows[index].get("target_type"), target_rows[index].get("count")) if index < len(target_rows) else None,
        ]
        for x, value in zip(column_x, values):
            if value:
                label, count = value
                percentage = (int(count or 0) / total_actions * 100) if total_actions else 0
                text = f"{label or '-'}: {int(count or 0):,} ({percentage:.1f}%)"
                draw.text((x + 8, y), _fit(draw, text, item_font, column_width - 16), font=item_font, fill=INK)
        y += 28

    y += 20
    draw.rounded_rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + 74), radius=10, fill="#fff8e6", outline="#ead49b", width=2)
    earliest_label = _date_label(summary.get("earliest_action_at"))
    draw.text((MARGIN + 18, y + 13), "Aktivitas pertama", font=_font(12), fill=MUTED)
    draw.text((MARGIN + 18, y + 38), earliest_label, font=_font(15, bold=True), fill=INK)
    latest_label = _date_label(summary.get("latest_action_at"))
    draw.text((MARGIN + 390, y + 13), "Aktivitas terakhir", font=_font(12), fill=MUTED)
    draw.text((MARGIN + 390, y + 38), latest_label, font=_font(15, bold=True), fill=INK)

    _draw_footer(draw, "Rekap pribadi dibuat otomatis untuk akun admin yang mengunduh dokumen ini.")
    return page


def _draw_activity_page(
    personal: Dict[str, Any],
    downloader: Dict[str, Any],
    *,
    period_label: str,
    generated_at: datetime,
    page_number: int,
) -> Image.Image:
    page, draw = _new_page()
    y = _draw_header(
        draw,
        heading="AKTIVITAS TERBARU DALAM PERIODE",
        period_label=period_label,
        generated_at=generated_at,
        page_number=page_number,
    )
    detail_rows = personal.get("detail_rows") or []
    detail_total = int(personal.get("detail_total") or len(detail_rows))
    page_limit = 33
    shown_rows = detail_rows[:page_limit]
    name = _clean(downloader.get("full_name") or downloader.get("email"), "Admin")
    info = f"Admin: {name}  |  Menampilkan {len(shown_rows)} dari {detail_total:,} aktivitas terbaru"
    draw.rounded_rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + 62), radius=10, fill="#eaf2ff")
    draw.text((MARGIN + 18, y + 20), _fit(draw, info, _font(14, bold=True), 1060), font=_font(14, bold=True), fill="#194f9b")
    y += 82

    columns = [
        ("Waktu", MARGIN, 170),
        ("Fitur", MARGIN + 170, 190),
        ("Aksi", MARGIN + 360, 230),
        ("Target", MARGIN + 590, 510),
    ]
    draw.rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + 42), fill="#dce9fb")
    for label, x, _width in columns:
        draw.text((x + 7, y + 12), label, font=_font(13, bold=True), fill=INK)
    y += 44
    if not shown_rows:
        draw.text((MARGIN + 8, y + 18), "Belum ada aktivitas pada periode ini.", font=_font(14), fill=MUTED)
    row_height = 39
    row_font = _font(11)
    for index, row in enumerate(shown_rows):
        if index % 2:
            draw.rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + row_height), fill=LIGHT)
        values = [
            _date_label(row.get("created_at")),
            row.get("feature_label"),
            row.get("action"),
            row.get("target_name"),
        ]
        for value, (_label, x, width) in zip(values, columns):
            draw.text((x + 7, y + 11), _fit(draw, value, row_font, width - 14), font=row_font, fill=INK)
        draw.line((MARGIN, y + row_height, PAGE_WIDTH - MARGIN, y + row_height), fill=BORDER, width=1)
        y += row_height

    _draw_footer(draw, f"Aktivitas diurutkan dari yang terbaru. Maksimal {page_limit} aktivitas ditampilkan pada halaman ini.")
    return page


def build_admin_performance_pdf(
    *,
    leaderboard: Iterable[Dict[str, Any]],
    personal: Dict[str, Any],
    downloader: Dict[str, Any],
    period_label: str,
    filters_label: str,
    generated_at: datetime,
    feature_options: Dict[str, str],
) -> io.BytesIO:
    ranked = []
    downloader_id = int(downloader.get("id") or 0)
    for rank, row in enumerate(leaderboard, start=1):
        item = dict(row)
        item["rank"] = rank
        ranked.append(item)

    pages: List[Image.Image] = []
    page_size = 25
    leaderboard_chunks = [ranked[index : index + page_size] for index in range(0, len(ranked), page_size)] or [[]]
    pages.append(
        _draw_leaderboard_page(
            leaderboard_chunks[0],
            downloader_id=downloader_id,
            feature_options=feature_options,
            period_label=period_label,
            generated_at=generated_at,
            page_number=1,
            filters_label=filters_label,
            continuation=False,
        )
    )
    pages.append(
        _draw_personal_page(
            personal,
            downloader,
            period_label=period_label,
            generated_at=generated_at,
            page_number=2,
            filters_label=filters_label,
        )
    )
    pages.append(
        _draw_activity_page(
            personal,
            downloader,
            period_label=period_label,
            generated_at=generated_at,
            page_number=3,
        )
    )
    for index, rows in enumerate(leaderboard_chunks[1:], start=4):
        pages.append(
            _draw_leaderboard_page(
                rows,
                downloader_id=downloader_id,
                feature_options=feature_options,
                period_label=period_label,
                generated_at=generated_at,
                page_number=index,
                filters_label=filters_label,
                continuation=True,
            )
        )

    output = io.BytesIO()
    pages[0].save(
        output,
        format="PDF",
        resolution=150.0,
        save_all=True,
        append_images=pages[1:],
        title=f"Laporan Performa Admin - {period_label}",
        author="ASKA Dashboard",
        subject="Bukti laporan kerja admin",
    )
    output.seek(0)
    return output
