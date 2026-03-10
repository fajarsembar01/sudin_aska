"""Helpers for guestbook photo processing."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from dashboard.photo_stamp import stamp_live_photo

UPLOAD_ROOT = Path(__file__).parent.parent.parent / "uploads" / "portal" / "daftar_tamu"


def stamp_guestbook_photo(
    *,
    file_storage,
    latitude: float,
    longitude: float,
    captured_at: datetime,
    school_label: Optional[str] = None,
) -> dict:
    """Save raw photo and return stamped photo paths."""
    file_storage.stream.seek(0)
    source_bytes = file_storage.stream.read()
    if not source_bytes:
        raise ValueError("Foto wajib diunggah.")
    return stamp_live_photo(
        source_bytes=source_bytes,
        latitude=latitude,
        longitude=longitude,
        captured_at=captured_at,
        school_label=school_label,
        upload_root=UPLOAD_ROOT,
        relative_root="uploads/portal/daftar_tamu",
        file_prefix="guest",
    )
