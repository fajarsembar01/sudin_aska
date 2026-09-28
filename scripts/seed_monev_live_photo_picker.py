#!/usr/bin/env python3
"""Seed varied private Foto Live records for testing the activity photo picker."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from dashboard.db_access import get_cursor


TARGET_EMAIL = "sdnsemperbarat01@gmail.com"
TARGET_COUNT = 100
TITLE_MARKER = "DUMMY-UJI-PICKER"
REPO_ROOT = Path(__file__).resolve().parents[1]
PHOTO_DIR = REPO_ROOT / "dashboard/static/uploads/monev_bos/stories"

CATEGORIES = (
    "Literasi Pagi",
    "Praktik Sains",
    "Senam Bersama",
    "Kerja Bakti",
    "Pembelajaran Matematika",
    "Kegiatan Pramuka",
    "Pentas Seni",
    "Pemeriksaan Kesehatan",
    "Rapat Komite",
    "Pelatihan Guru",
    "Perawatan Taman",
    "Distribusi Buku",
    "Kelas Komputer",
    "Upacara Bendera",
    "Kantin Sehat",
    "Lomba Kebersihan",
    "Pembinaan Karakter",
    "Olahraga Siswa",
    "Kunjungan Perpustakaan",
    "Simulasi Mitigasi Bencana",
)

LOCATIONS = (
    "Ruang Kelas 1A",
    "Ruang Kelas 2B",
    "Ruang Kelas 3A",
    "Ruang Kelas 4B",
    "Ruang Kelas 5A",
    "Ruang Kelas 6B",
    "Perpustakaan Sekolah",
    "Laboratorium IPA",
    "Laboratorium Komputer",
    "Lapangan Utama",
    "Aula Sekolah",
    "Taman Literasi",
    "UKS",
    "Kantin Sekolah",
    "Ruang Guru",
)

PALETTES = (
    ("#0F766E", "#CCFBF1", "#F0FDFA"),
    ("#1D4ED8", "#DBEAFE", "#EFF6FF"),
    ("#7C3AED", "#EDE9FE", "#F5F3FF"),
    ("#B45309", "#FEF3C7", "#FFFBEB"),
    ("#BE123C", "#FFE4E6", "#FFF1F2"),
    ("#047857", "#D1FAE5", "#ECFDF5"),
    ("#C2410C", "#FFEDD5", "#FFF7ED"),
    ("#0369A1", "#E0F2FE", "#F0F9FF"),
)


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _draw_dummy_photo(index: int, title: str, location: str, date_label: str, output_path: Path) -> tuple[int, str]:
    primary, secondary, background = PALETTES[(index - 1) % len(PALETTES)]
    image = Image.new("RGB", (720, 540), background)
    draw = ImageDraw.Draw(image)

    # A distinct, photo-like test card per record. Shapes vary by index so the
    # gallery is useful for scanning selection and lazy-loading behaviour.
    draw.rectangle((0, 0, 720, 96), fill=primary)
    draw.rounded_rectangle((36, 128, 684, 462), radius=28, fill=secondary, outline=primary, width=4)
    for step in range(6):
        x = 72 + ((index * 47 + step * 103) % 570)
        y = 170 + ((index * 31 + step * 61) % 190)
        radius = 18 + ((index + step * 7) % 30)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=primary)
    draw.rectangle((72, 350, 648, 426), fill=background)

    draw.text((36, 25), f"FOTO LIVE UJI #{index:03d}", font=_font(32, bold=True), fill="white")
    draw.text((92, 365), title, font=_font(22, bold=True), fill=primary)
    draw.text((92, 402), f"{location}  •  {date_label}", font=_font(17), fill=primary)
    draw.text((36, 495), "SDN SEMPER BARAT 01  •  DATA DUMMY PICKER", font=_font(16, bold=True), fill=primary)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="JPEG", quality=76, optimize=True)
    content = output_path.read_bytes()
    return len(content), hashlib.sha256(content).hexdigest()


def main() -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, email, role
            FROM dashboard_users
            WHERE LOWER(email) = LOWER(%s)
            """,
            (TARGET_EMAIL,),
        )
        user = cur.fetchone()
    if not user:
        raise SystemExit(f"User {TARGET_EMAIL} tidak ditemukan.")
    if user["role"] != "sekolah":
        raise SystemExit(f"User {TARGET_EMAIL} bukan akun sekolah.")

    school_user_id = int(user["id"])
    user_photo_dir = PHOTO_DIR / str(school_user_id)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT title
            FROM monev_bos_school_posts
            WHERE school_user_id = %s
              AND deleted_at IS NULL
              AND title LIKE %s
            """,
            (school_user_id, f"{TITLE_MARKER} %"),
        )
        existing_titles = {row["title"] for row in cur.fetchall()}

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    created_files: list[Path] = []
    records: list[dict] = []
    for index in range(1, TARGET_COUNT + 1):
        category = CATEGORIES[(index - 1) % len(CATEGORIES)]
        location = LOCATIONS[(index * 7 - 1) % len(LOCATIONS)]
        class_number = ((index - 1) % 6) + 1
        session = ((index - 1) // 6) + 1
        title = f"{TITLE_MARKER} {index:03d} · {category} Kelas {class_number} Sesi {session:02d}"
        if title in existing_titles:
            continue

        # Pukul 10.00 WIB pada hari yang berbeda untuk setiap record. Ini membuat
        # pengurutan tanggal mudah diverifikasi tanpa tanggal ganda akibat lintas zona waktu.
        created_at = now.replace(hour=3, minute=(index * 7) % 60) - timedelta(days=index - 1)
        story_expires_at = created_at + timedelta(days=7 + (index % 4))
        latitude = -6.1218000 + ((index % 17) * 0.000071)
        longitude = 106.9229000 + ((index % 19) * 0.000067)
        accuracy = 3.5 + ((index * 13) % 95) / 10
        filename = f"dummy_uji_picker_{index:03d}.jpg"
        absolute_path = user_photo_dir / filename
        file_size, photo_hash = _draw_dummy_photo(
            index,
            category,
            location,
            created_at.astimezone().strftime("%d/%m/%Y"),
            absolute_path,
        )
        if not 0 < file_size <= 204800:
            raise RuntimeError(f"Ukuran foto dummy #{index} tidak valid: {file_size} byte")
        created_files.append(absolute_path)
        records.append(
            {
                "index": index,
                "title": title,
                "photo_path": f"static/uploads/monev_bos/stories/{school_user_id}/{filename}",
                "photo_size": file_size,
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
                "location": f"{location} · Zona {chr(65 + (index % 5))}",
                "created_at": created_at,
                "story_expires_at": story_expires_at,
                "photo_hash": photo_hash,
            }
        )

    try:
        with get_cursor(commit=True) as cur:
            for record in records:
                cur.execute(
                    """
                    INSERT INTO monev_bos_school_posts
                        (school_user_id, title, photo_path, photo_size, latitude, longitude,
                         location_accuracy, location_text, created_by, created_at,
                         story_expires_at, is_public, photo_sha256)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s)
                    RETURNING id
                    """,
                    (
                        school_user_id,
                        record["title"],
                        record["photo_path"],
                        record["photo_size"],
                        record["latitude"],
                        record["longitude"],
                        record["accuracy"],
                        record["location"],
                        school_user_id,
                        record["created_at"],
                        record["story_expires_at"],
                        record["photo_hash"],
                    ),
                )
                post_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO monev_bos_story_audit_logs
                        (post_id, school_user_id, actor_id, action, details, created_at)
                    VALUES (%s, %s, %s, 'CREATE', %s::jsonb, %s)
                    """,
                    (
                        post_id,
                        school_user_id,
                        school_user_id,
                        json.dumps(
                            {
                                "title": record["title"],
                                "location_text": record["location"],
                                "source": "dummy_picker_test",
                                "seed_index": record["index"],
                            }
                        ),
                        record["created_at"],
                    ),
                )
    except Exception:
        for path in created_files:
            path.unlink(missing_ok=True)
        raise

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS dummy_count, MIN(created_at) AS oldest, MAX(created_at) AS newest,
                   COUNT(DISTINCT title) AS distinct_titles,
                   COUNT(DISTINCT created_at::date) AS distinct_dates,
                   COUNT(DISTINCT location_text) AS distinct_locations
            FROM monev_bos_school_posts
            WHERE school_user_id = %s
              AND deleted_at IS NULL
              AND title LIKE %s
            """,
            (school_user_id, f"{TITLE_MARKER} %"),
        )
        summary = dict(cur.fetchone())

    print(f"User: {TARGET_EMAIL} (id={school_user_id})")
    print(f"Ditambahkan sekarang: {len(records)} foto")
    print(f"Ringkasan dummy: {summary}")


if __name__ == "__main__":
    main()
