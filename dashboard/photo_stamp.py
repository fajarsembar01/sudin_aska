"""Shared live photo stamping helpers for attendance and follow-up flows."""

from __future__ import annotations

import base64
import io
import textwrap
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from utils import to_jakarta


def decode_data_url_image(photo_data_url: str) -> bytes:
    value = (photo_data_url or "").strip()
    if not value:
        raise ValueError("Foto belum diambil.")
    if "," in value:
        _, encoded = value.split(",", 1)
    else:
        encoded = value
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Format foto live tidak valid.") from exc


def _get_text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, spacing: int) -> tuple[int, int, int, int]:
    if hasattr(draw, "multiline_textbbox"):
        return draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    width, height = draw.multiline_textsize(text, font=font, spacing=spacing)
    return (0, 0, width, height)


def _wrap_text(text: str, max_chars: int) -> list[str]:
    if not text:
        return []
    return textwrap.wrap(text, width=max_chars) or [text]


def stamp_live_photo(
    *,
    source_bytes: bytes,
    latitude: float,
    longitude: float,
    captured_at: datetime,
    school_label: Optional[str],
    upload_root: Path,
    relative_root: str,
    file_prefix: str,
) -> dict:
    upload_root.mkdir(parents=True, exist_ok=True)

    token = uuid.uuid4().hex
    raw_filename = f"{file_prefix}_raw_{token}.jpg"
    stamped_filename = f"{file_prefix}_{token}.jpg"
    raw_path = upload_root / raw_filename
    stamped_path = upload_root / stamped_filename

    try:
        base = Image.open(io.BytesIO(source_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError("Foto tidak dapat diproses.") from exc

    base.save(raw_path, format="JPEG", quality=90, optimize=True)
    base_rgba = base.convert("RGBA")
    width, height = base_rgba.size
    margin = max(12, int(width * 0.02))
    font = ImageFont.load_default()
    spacing = 4
    max_chars = max(24, int(width / 18))

    local_dt = to_jakarta(captured_at) or captured_at
    lines = [
        f"Waktu: {local_dt.strftime('%d %b %Y %H:%M')} WIB",
        f"GPS: {latitude:.5f}, {longitude:.5f}",
    ]
    if school_label:
        lines.extend(_wrap_text(f"Sekolah: {school_label}", max_chars))
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

    overlay = Image.new("RGBA", base_rgba.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle([box_left, box_top, box_right, box_bottom], fill=(0, 0, 0, int(255 * 0.5)))
    base_rgba = Image.alpha_composite(base_rgba, overlay)
    draw = ImageDraw.Draw(base_rgba)
    draw.multiline_text(
        (box_left + pad, box_top + pad),
        text,
        fill=(255, 255, 255, 230),
        font=font,
        spacing=spacing,
    )

    base_rgba.convert("RGB").save(stamped_path, format="JPEG", quality=88, optimize=True)
    relative_root_norm = relative_root.strip("/").replace("\\", "/")
    return {
        "raw_path": f"{relative_root_norm}/{raw_filename}",
        "stamped_path": f"{relative_root_norm}/{stamped_filename}",
        "map_provider": "none",
        "map_error": None,
    }

