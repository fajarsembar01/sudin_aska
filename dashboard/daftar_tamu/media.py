"""Helpers for guestbook photo processing."""

from __future__ import annotations

import io
import os
import textwrap
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib import request

from PIL import Image, ImageDraw, ImageFont

from utils import to_jakarta

UPLOAD_ROOT = Path(__file__).parent.parent.parent / "uploads" / "portal" / "daftar_tamu"
DEFAULT_STATIC_MAP_URL = "https://staticmap.openstreetmap.de/staticmap.php"
MAP_USER_AGENT = "ASKA-Guestbook/1.0"


def _build_map_url(lat: float, lon: float, width: int, height: int) -> str:
    base = os.getenv("GUESTBOOK_STATICMAP_URL") or DEFAULT_STATIC_MAP_URL
    zoom = os.getenv("GUESTBOOK_STATICMAP_ZOOM", "16")
    return (
        f"{base}?center={lat:.6f},{lon:.6f}"
        f"&zoom={zoom}"
        f"&size={width}x{height}"
        f"&maptype=mapnik"
        f"&markers={lat:.6f},{lon:.6f},red-pushpin"
    )


def _fetch_static_map(lat: float, lon: float, width: int, height: int) -> Image.Image:
    url = _build_map_url(lat, lon, width, height)
    req = request.Request(url, headers={"User-Agent": MAP_USER_AGENT})
    with request.urlopen(req, timeout=6) as resp:
        payload = resp.read()
    if not payload:
        raise ValueError("Map image kosong")
    return Image.open(io.BytesIO(payload)).convert("RGB")


def _build_placeholder_map(lat: float, lon: float, width: int, height: int, message: str) -> Image.Image:
    img = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    # draw simple grid
    step = max(20, width // 6)
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=(220, 220, 220))
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=(220, 220, 220))
    # crosshair
    cx, cy = width // 2, height // 2
    draw.line([(cx - 12, cy), (cx + 12, cy)], fill=(200, 30, 30), width=2)
    draw.line([(cx, cy - 12), (cx, cy + 12)], fill=(200, 30, 30), width=2)
    font = ImageFont.load_default()
    label = f"{message}\n{lat:.5f}, {lon:.5f}"
    draw.multiline_text((8, 8), label, fill=(80, 80, 80), font=font, spacing=3)
    return img


def _get_text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, spacing: int) -> tuple[int, int, int, int]:
    if hasattr(draw, "multiline_textbbox"):
        return draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    width, height = draw.multiline_textsize(text, font=font, spacing=spacing)
    return (0, 0, width, height)


def _wrap_text(text: str, max_chars: int) -> list[str]:
    if not text:
        return []
    return textwrap.wrap(text, width=max_chars) or [text]


def stamp_guestbook_photo(
    *,
    file_storage,
    latitude: float,
    longitude: float,
    captured_at: datetime,
    school_label: Optional[str] = None,
) -> dict:
    """Save raw photo and return stamped photo paths.

    Returns dict with: raw_path, stamped_path, map_provider
    """
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    token = uuid.uuid4().hex
    raw_filename = f"guest_raw_{token}.jpg"
    stamped_filename = f"guest_{token}.jpg"

    raw_path = UPLOAD_ROOT / raw_filename
    stamped_path = UPLOAD_ROOT / stamped_filename

    file_storage.save(raw_path)

    map_provider = "none"
    map_error = None
    try:
        base = Image.open(raw_path).convert("RGB")
        base_rgba = base.convert("RGBA")
        width, height = base_rgba.size

        margin = max(12, int(width * 0.02))

        font = ImageFont.load_default()
        spacing = 4
        max_chars = max(24, int(width / 18))

        local_dt = to_jakarta(captured_at) or captured_at
        time_label = local_dt.strftime("%d %b %Y %H:%M")

        lines = [
            f"Waktu: {time_label} WIB",
            f"GPS: {latitude:.5f}, {longitude:.5f}",
        ]
        if school_label:
            school_lines = _wrap_text(f"Sekolah: {school_label}", max_chars)
            lines.extend(school_lines)

        text = "\n".join(lines)

        draw = ImageDraw.Draw(base_rgba)
        bbox = _get_text_bbox(draw, text, font, spacing)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad = 8
        box_left = margin
        box_top = height - text_h - pad * 2 - margin
        box_right = box_left + text_w + pad * 2
        box_bottom = height - margin

        draw.rectangle(
            [box_left, box_top, box_right, box_bottom],
            fill=(0, 0, 0, 128),
        )
        draw.multiline_text(
            (box_left + pad, box_top + pad),
            text,
            fill=(255, 255, 255, 230),
            font=font,
            spacing=spacing,
        )

        final_img = base_rgba.convert("RGB")
        final_img.save(stamped_path, format="JPEG", quality=88, optimize=True)
    except Exception:
        if stamped_path.exists():
            stamped_path.unlink(missing_ok=True)
        if raw_path.exists():
            raw_path.unlink(missing_ok=True)
        raise

    return {
        "raw_path": f"uploads/portal/daftar_tamu/{raw_filename}",
        "stamped_path": f"uploads/portal/daftar_tamu/{stamped_filename}",
        "map_provider": map_provider,
        "map_error": map_error,
    }
