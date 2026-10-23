"""Compact PDF report for the Admin Performance dashboard."""

from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from PIL import Image, ImageDraw, ImageFont, ImageOps
from utils import to_jakarta


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
        ("Aksi", MARGIN + 445, 70),
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
        action_points = int(row.get("action_points", row.get("total_actions", 0)) or 0)
        coding_days = int(row.get("coding_score_units", row.get("github_commits", 0)) or 0)
        coding_points = int(row.get("coding_points", coding_days * 10) or 0)
        values = [
            row.get("rank"),
            row.get("actor_label"),
            f"@{row['github_username']}" if row.get("github_username") else "-",
            row.get("performance_total", action_points + coding_points),
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

    _draw_footer(draw, "Skor = aktivitas lain x 1 + klaim back up x 5 + kehadiran rapat x 5 + hari aktif Coding x 10. Commit satu tanggal dihitung 1 hari.")
    return page


def _draw_personal_page(
    personal: Dict[str, Any],
    downloader: Dict[str, Any],
    *,
    period_label: str,
    generated_at: datetime,
    page_number: int,
    filters_label: str,
) -> tuple[Image.Image, int]:
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
    action_points = int(personal.get("action_points", summary.get("action_points", total_actions)) or 0)
    active_action_days = len(personal.get("daily_series") or [])
    coding_days = int(personal.get("github_coding_days") or 0)
    coding_commits = int(personal.get("github_commits") or 0)
    coding_points = int(personal.get("coding_points") or coding_days * 10)
    performance_total = int(personal.get("performance_total", action_points + coding_points) or 0)

    draw.rounded_rectangle((MARGIN, y, MARGIN + 300, y + 138), radius=14, fill="#eaf2ff", outline="#b7d2fb", width=2)
    draw.text((MARGIN + 20, y + 16), "TOTAL SKOR", font=_font(14, bold=True), fill="#194f9b")
    draw.text((MARGIN + 20, y + 48), str(performance_total), font=_font(42, bold=True), fill=PRIMARY)
    rank = personal.get("organization_rank")
    rank_label = f"Peringkat #{rank}" if rank else "Belum masuk leaderboard"
    draw.text((MARGIN + 20, y + 108), rank_label, font=_font(14), fill=MUTED)

    breakdown_x = MARGIN + 325
    draw.rounded_rectangle((breakdown_x, y, PAGE_WIDTH - MARGIN, y + 138), radius=14, fill=LIGHT, outline=BORDER, width=2)
    draw.text((breakdown_x + 20, y + 16), "PERHITUNGAN SKOR", font=_font(14, bold=True), fill=INK)
    draw.text((breakdown_x + 20, y + 50), f"Poin Aktivitas              {action_points:,} poin", font=_font(16), fill=INK)
    draw.text((breakdown_x + 20, y + 82), f"Coding: {coding_days:,} hari x 10       {coding_points:,} poin", font=_font(16), fill=INK)
    draw.text((breakdown_x + 20, y + 111), "Back up & hadir rapat: 5 poin; aktivitas lain: 1 poin.", font=_font(12), fill=MUTED)
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
    for index in range(min(10, max(len(feature_rows), len(action_rows), len(target_rows)))):
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

    y += 12
    draw.rounded_rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + 64), radius=10, fill="#fff8e6", outline="#ead49b", width=2)
    for x, label, value in (
        (MARGIN + 18, "Aktivitas pertama", summary.get("earliest_action_at")),
        (MARGIN + 570, "Aktivitas terakhir", summary.get("latest_action_at")),
    ):
        draw.text((x, y + 10), label, font=_font(12), fill=MUTED)
        draw.text((x, y + 33), _date_label(to_jakarta(value)) + (" WIB" if value else ""), font=_font(15, bold=True), fill=INK)
    _draw_footer(draw, "Rekap pribadi dan rincian bukti kerja untuk akun admin yang mengunduh dokumen ini.")
    return page, y + 84


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


def _group_meeting_activities(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Combine creation and attendance for the same meeting without changing credit."""
    creations = {entry.get("target_id"): entry for entry in entries
                 if entry.get("feature_key") == "meeting_creation" and entry.get("target_id") is not None}
    grouped = []
    matched = set()
    for entry in entries:
        if entry.get("feature_key") == "meeting_attendance":
            try:
                metadata = json.loads(entry.get("detail_text") or "{}")
            except (ValueError, TypeError):
                metadata = {}
            creation = creations.get(metadata.get("meeting_id"))
            if creation:
                entry = {**entry, "creation_activity": creation}
                matched.add(creation["target_id"])
        grouped.append(entry)
    return [entry for entry in grouped if not (
        entry.get("feature_key") == "meeting_creation" and entry.get("target_id") in matched
    )]


def _summarize_backup_activities(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace individual backup cards with one summary for the filtered period."""
    backups = [entry for entry in entries if entry.get("feature_key") == "backup_history"]
    if not backups:
        return entries
    ordered = sorted(backups, key=lambda entry: entry["created_at"].timestamp() if entry.get("created_at") else 0,
                     reverse=True)
    summary = {
        "feature_key": "backup_summary",
        "backup_entries": ordered,
        "points": sum(entry.get("points", 5) for entry in backups),
    }
    result = []
    inserted = False
    for entry in entries:
        if entry.get("feature_key") == "backup_history":
            if not inserted:
                result.append(summary)
                inserted = True
        else:
            result.append(entry)
    return result


def _backup_date_lines(entries, *, max_width: int, max_lines: int = 18):
    font = _font(14)
    dates = [_date_label(to_jakarta(entry.get("created_at"))) for entry in entries]
    lines = []
    line = ""
    shown = 0
    for date in dates:
        candidate = f"{line}, {date}" if line else date
        if line and font.getlength(candidate) > max_width:
            lines.append(line)
            if len(lines) >= max_lines:
                break
            line = date
        else:
            line = candidate
        shown += 1
    else:
        if line:
            lines.append(line)
    return lines, len(dates) - shown


def _draw_attendance_page(personal, *, period_label, generated_at, page_number):
    """Fit the latest four attendance records on a single adaptive photo page."""
    page, draw = _new_page()
    y = _draw_header(draw, heading="DOKUMENTASI ABSENSI RAPAT", period_label=period_label,
                     generated_at=generated_at, page_number=page_number)
    all_entries = [entry for entry in _group_meeting_activities(personal.get("backup_attendance_rows") or [])
                   if entry.get("feature_key") == "meeting_attendance"]
    entries = sorted(all_entries, key=lambda entry: entry["created_at"].timestamp() if entry.get("created_at") else 0, reverse=True)[:4]
    draw.text((MARGIN, y), f"Menampilkan {len(entries)} dari {len(all_entries)} absensi terbaru sesuai filter. Semua waktu dalam WIB.", font=_font(14), fill=MUTED)
    top, gap = y + 45, 20
    width, available = PAGE_WIDTH - 2 * MARGIN, PAGE_HEIGHT - 100 - (y + 45)
    rows = 1 if len(entries) <= 1 else 2
    cell_height = (available - gap * (rows - 1)) // rows
    for index, entry in enumerate(entries):
        # One fills the page; two stack; three use a wide first row; four use 2x2.
        columns = 2 if len(entries) == 4 or (len(entries) == 3 and index > 0) else 1
        row = index // 2 if len(entries) == 4 else (1 if len(entries) == 3 and index > 0 else index)
        column = index % 2 if len(entries) == 4 else (index - 1 if len(entries) == 3 and index > 0 else 0)
        cell_width = (width - gap * (columns - 1)) // columns
        left = MARGIN + column * (cell_width + gap)
        cy = top + row * (cell_height + gap)
        draw.rounded_rectangle((left, cy, left + cell_width, cy + cell_height), radius=12, fill=LIGHT, outline=BORDER, width=2)
        x = left + 18
        creation = entry.get("creation_activity")
        points = entry.get("points", 5) + (creation.get("points", 1) if creation else 0)
        draw.text((x, cy + 14), f"Absensi {index + 1}", font=_font(18, bold=True), fill=PRIMARY)
        draw.text((left + cell_width - 18, cy + 16), f"{points} poin", font=_font(16, bold=True), fill=PRIMARY, anchor="ra")
        draw.text((x, cy + 48), _fit(draw, entry.get("target_name"), _font(17, bold=True), cell_width - 36), font=_font(17, bold=True), fill=INK)
        draw.text((x, cy + 78), f"Waktu rapat: {_date_label(to_jakarta(entry.get('created_at')))} WIB", font=_font(13), fill=INK)
        try:
            metadata = json.loads(entry.get("detail_text") or "{}")
        except (ValueError, TypeError):
            metadata = {}
        status = {"present": "Hadir", "late": "Terlambat"}.get(metadata.get("attendance_status"), "Hadir")
        draw.text((x, cy + 104), f"Status: {status} ({entry.get('points', 5)} poin)", font=_font(13), fill=INK)
        draw.text((x, cy + 130), f"Absensi dicatat: {_date_label(to_jakarta(entry.get('attendance_recorded_at')))} WIB", font=_font(13), fill=INK)
        if creation:
            draw.text((x, cy + 156), f"Pembuat meeting: {_date_label(to_jakarta(creation.get('created_at')))} WIB ({creation.get('points', 1)} poin)", font=_font(13), fill=INK)
        photo = None
        if entry.get("photo_path"):
            try:
                with Image.open(entry["photo_path"]) as original:
                    photo = ImageOps.exif_transpose(original).convert("RGB")
                photo = ImageOps.contain(photo, (cell_width - 36, cell_height - 222), Image.Resampling.LANCZOS)
            except (OSError, ValueError):
                photo = None
        caption = ("FOTO DUMMY - foto asli tidak tersedia di lingkungan ini" if entry.get("photo_is_dummy") and photo
                   else "Foto dokumentasi rapat" if photo else "Foto dokumentasi rapat belum tersedia.")
        draw.text((x, cy + 182), caption, font=_font(12, bold=bool(entry.get("photo_is_dummy"))),
                  fill=PRIMARY if entry.get("photo_is_dummy") else MUTED)
        if photo:
            image_top = cy + 210 + (cell_height - 222 - photo.height) // 2
            image_left = left + (cell_width - photo.width) // 2
            page.paste(photo, (image_left, image_top))
            if entry.get("photo_is_dummy"):
                label = "FOTO DUMMY"
                label_font = _font(22, bold=True)
                label_width = draw.textbbox((0, 0), label, font=label_font)[2]
                draw.rounded_rectangle((image_left + 12, image_top + 12,
                                        image_left + label_width + 40, image_top + 52),
                                       radius=8, fill=(255, 255, 255))
                draw.text((image_left + 26, image_top + 18), label,
                          font=label_font, fill=PRIMARY)
    if not entries:
        draw.text((MARGIN, top + 20), "Belum ada absensi rapat sesuai periode dan filter laporan.", font=_font(16), fill=MUTED)
    _draw_footer(draw, "Maksimal 4 absensi terakhir. Foto ditampilkan utuh; ukuran menyesuaikan jumlah absensi.")
    return page


def _draw_backup_attendance_pages(
    personal: Dict[str, Any], *, period_label: str, generated_at: datetime,
    first_page_number: int, initial_page: Image.Image | None = None, initial_y: int = 0,
    attendance_only: bool = False,
) -> List[Image.Image]:
    """Render every filtered backup/meeting activity, including attendance photos."""
    if attendance_only:
        return [_draw_attendance_page(personal, period_label=period_label,
            generated_at=generated_at, page_number=first_page_number)]
    pages = [initial_page] if initial_page is not None else []
    page = initial_page
    draw = ImageDraw.Draw(page) if page is not None else None
    y = initial_y if page is not None else PAGE_HEIGHT
    if page is not None:
        draw.text((MARGIN, y), "RINCIAN BACK UP DAN PEMBUATAN MEETING (WIB)", font=_font(17, bold=True), fill=PRIMARY)
        y += 40
    entries = _group_meeting_activities(personal.get("backup_attendance_rows") or [])
    entries = [entry for entry in entries if (entry.get("feature_key") == "meeting_attendance") == attendance_only]
    total_attendance = len(entries)
    if attendance_only:
        entries = sorted(entries, key=lambda entry: entry["created_at"].timestamp() if entry.get("created_at") else 0, reverse=True)[:4]
        if not entries:
            return []
    else:
        entries = _summarize_backup_activities(entries)
    items_on_page = 0
    for entry in entries or [None]:
        photo = None
        if entry and entry.get("feature_key") == "meeting_attendance" and entry.get("photo_path"):
            try:
                with Image.open(entry["photo_path"]) as original:
                    photo = ImageOps.exif_transpose(original).convert("RGB")
                photo.thumbnail((1060, 420) if attendance_only else (380, 260), Image.Resampling.LANCZOS)
            except (OSError, ValueError):
                photo = None
        is_attendance = entry and entry.get("feature_key") == "meeting_attendance"
        is_backup_summary = entry and entry.get("feature_key") == "backup_summary"
        creation = entry.get("creation_activity") if entry else None
        backup_lines, hidden_backups = _backup_date_lines(
            entry["backup_entries"], max_width=PAGE_WIDTH - 2 * MARGIN - 40
        ) if is_backup_summary else ([], 0)
        height = (130 + len(backup_lines) * 24 + (25 if hidden_backups else 0)) if is_backup_summary else max(
            215 if creation else 185 if is_attendance else 155,
            photo.height + (230 if attendance_only else 60) if photo else 0)
        if y + height > PAGE_HEIGHT - 100 or (attendance_only and items_on_page >= 2):
            page, draw = _new_page()
            y = _draw_header(draw, heading="DOKUMENTASI ABSENSI RAPAT" if attendance_only else "RINCIAN BACK UP DAN PEMBUATAN MEETING",
                             period_label=period_label, generated_at=generated_at,
                             page_number=first_page_number + len(pages))
            pages.append(page)
            items_on_page = 0
            note = f"Menampilkan {len(entries)} dari {total_attendance} absensi terbaru sesuai filter. Semua waktu dalam WIB." if attendance_only else "Rincian pribadi sesuai periode dan filter laporan. Semua waktu dalam WIB."
            draw.text((MARGIN, y), note, font=_font(14), fill=MUTED)
            y += 45
            _draw_footer(draw, "Klaim back up dan kehadiran: 5 poin per aktivitas. Pembuatan meeting: 1 poin.")
        if entry is None:
            draw.text((MARGIN, y + 15), "Tidak ada rincian back up atau pembuatan meeting lain sesuai filter.", font=_font(16), fill=MUTED)
            continue
        draw.rounded_rectangle((MARGIN, y, PAGE_WIDTH - MARGIN, y + height), radius=12, fill=LIGHT, outline=BORDER, width=2)
        x = MARGIN + 20
        feature = entry.get("feature_key")
        if is_backup_summary:
            backups = entry["backup_entries"]
            draw.text((x, y + 15), f"Klaim Back Up - {len(backups)} kali", font=_font(18, bold=True), fill=PRIMARY)
            draw.text((PAGE_WIDTH - MARGIN - 20, y + 17), f"{entry['points']} poin", font=_font(16, bold=True), fill=PRIMARY, anchor="ra")
            draw.text((x, y + 50), "Tanggal dan waktu klaim (WIB):", font=_font(15, bold=True), fill=INK)
            for line_number, line in enumerate(backup_lines):
                draw.text((x, y + 78 + line_number * 24), line, font=_font(14), fill=INK)
            if hidden_backups:
                draw.text((x, y + 78 + len(backup_lines) * 24),
                          f"+{hidden_backups} klaim lainnya; tertua {_date_label(to_jakarta(backups[-1].get('created_at')))} WIB",
                          font=_font(14), fill=MUTED)
            y += height + 20
            items_on_page += 1
            continue
        label = {"backup_history": "Klaim Back Up", "meeting_attendance": "Kehadiran Rapat", "meeting_creation": "Pembuatan Meeting"}.get(feature, "Aktivitas")
        if creation:
            label = "Absensi Meeting - Pembuat dan Kehadiran"
        draw.text((x, y + 15), label, font=_font(18, bold=True), fill=PRIMARY)
        points = entry.get('points', 5) + (creation.get('points', 1) if creation else 0)
        draw.text((PAGE_WIDTH - MARGIN - 20, y + 17), f"{points} poin", font=_font(16, bold=True), fill=PRIMARY, anchor="ra")
        text_width = 1040 - (photo.width + 25 if photo and not attendance_only else 0)
        draw.text((x, y + 50), _fit(draw, entry.get("target_name"), _font(17, bold=True), text_width), font=_font(17, bold=True), fill=INK)
        timestamp = _date_label(to_jakarta(entry.get("created_at")))
        time_label = "Waktu rapat" if is_attendance else "Waktu klaim" if feature == "backup_history" else "Dibuat pada"
        draw.text((x, y + 83), f"{time_label}: {timestamp} WIB", font=_font(15), fill=INK)
        if is_attendance:
            try:
                metadata = json.loads(entry.get("detail_text") or "{}")
            except (ValueError, TypeError):
                metadata = {}
            status = {"present": "Hadir", "late": "Terlambat"}.get(metadata.get("attendance_status"), "Hadir")
            draw.text((x, y + 112), f"Status: {status} ({entry.get('points', 5)} poin)", font=_font(14), fill=INK)
            draw.text((x, y + 138), f"Absensi dicatat: {_date_label(to_jakarta(entry.get('attendance_recorded_at')))} WIB", font=_font(14), fill=INK)
            if creation:
                draw.text((x, y + 163), f"Pembuat meeting: {_date_label(to_jakarta(creation.get('created_at')))} WIB ({creation.get('points', 1)} poin)", font=_font(14), fill=INK)
            draw.text((x, y + (190 if creation else 163)), "Foto dokumentasi rapat" if photo else "Foto dokumentasi rapat belum tersedia.", font=_font(13), fill=MUTED)
        else:
            draw.text((x, y + 118), "Sudah back up data pada tanggal tersebut." if feature == "backup_history" else "Satu aktivitas untuk pembuat meeting.", font=_font(14), fill=MUTED)
        if photo:
            photo_x = (PAGE_WIDTH - photo.width) // 2 if attendance_only else PAGE_WIDTH - MARGIN - photo.width - 15
            page.paste(photo, (photo_x, y + 210 if attendance_only else y + 45))
        y += height + 20
        items_on_page += 1
    return pages


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
    personal_page, content_bottom = _draw_personal_page(
        personal, downloader, period_label=period_label, generated_at=generated_at,
        page_number=2, filters_label=filters_label,
    )
    personal_pages = _draw_backup_attendance_pages(
        personal, period_label=period_label, generated_at=generated_at,
        first_page_number=3, initial_page=personal_page, initial_y=content_bottom,
    )
    pages.append(personal_pages[0])
    pages.append(_draw_attendance_page(
        personal, period_label=period_label, generated_at=generated_at, page_number=3,
    ))
    pages.extend(personal_pages[1:])
    pages.append(
        _draw_activity_page(
            personal,
            downloader,
            period_label=period_label,
            generated_at=generated_at,
            page_number=len(pages) + 1,
        )
    )
    for rows in leaderboard_chunks[1:]:
        pages.append(
            _draw_leaderboard_page(
                rows,
                downloader_id=downloader_id,
                feature_options=feature_options,
                period_label=period_label,
                generated_at=generated_at,
                page_number=len(pages) + 1,
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
