"""Media helpers for Call Center WhatsApp attachments."""

from __future__ import annotations

import base64
import hashlib
import io
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps
from werkzeug.utils import secure_filename

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - optional HEIC/HEIF support
    pass

try:
    from pypdf import PdfReader, PdfWriter
except Exception:  # pragma: no cover - optional dependency fallback
    PdfReader = None
    PdfWriter = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CC_MEDIA_ROOT = PROJECT_ROOT / "uploads" / "call_center"

_ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
    "image/bmp",
    "image/tiff",
}
_WEB_SAFE_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}
_ALLOWED_MIME_TYPES = {
    *_ALLOWED_IMAGE_MIME_TYPES,
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
}
_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain": ".txt",
    "text/csv": ".csv",
}
_MIME_ALLOWED_SUFFIXES = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/jpg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
    "image/heic": {".heic"},
    "image/heif": {".heif"},
    "image/bmp": {".bmp"},
    "image/tiff": {".tif", ".tiff"},
    "application/pdf": {".pdf"},
    "application/msword": {".doc"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        ".docx"
    },
    "application/vnd.ms-excel": {".xls"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "application/vnd.ms-powerpoint": {".ppt"},
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {
        ".pptx"
    },
    "text/plain": {".txt"},
    "text/csv": {".csv"},
}
_SUFFIX_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".jfif": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
}


def call_center_media_label(mime_type: Optional[str] = None) -> str:
    """Return a compact label for attachment-only messages."""
    clean_mime = (mime_type or "").strip().lower()
    if clean_mime.startswith("image/"):
        return "[Gambar]"
    if clean_mime.startswith("video/"):
        return "[Video]"
    if clean_mime.startswith("audio/"):
        return "[Audio]"
    if clean_mime == "application/pdf":
        return "[PDF]"
    if clean_mime:
        return "[Berkas]"
    return "[Media]"


def save_call_center_media(
    media_payload: Any,
    *,
    message_id: Optional[str] = None,
    max_image_bytes: Optional[int] = None,
    max_pdf_bytes: Optional[int] = None,
    max_file_bytes: Optional[int] = None,
) -> dict:
    """Persist a bridge media payload and return cc_messages media fields.

    The bridge sends base64 media data. Invalid, unsupported, or oversized media
    is ignored here so inbound message text can still be stored.
    """
    media_meta, _ = _save_call_center_media(
        media_payload,
        message_id=message_id,
        max_image_bytes=max_image_bytes,
        max_pdf_bytes=max_pdf_bytes,
        max_file_bytes=max_file_bytes,
    )
    return media_meta


def save_call_center_media_with_error(
    media_payload: Any,
    *,
    message_id: Optional[str] = None,
    max_image_bytes: Optional[int] = None,
    max_pdf_bytes: Optional[int] = None,
    max_file_bytes: Optional[int] = None,
) -> tuple[dict, Optional[str]]:
    """Persist admin-uploaded media and return a user-facing error on failure."""
    return _save_call_center_media(
        media_payload,
        message_id=message_id,
        max_image_bytes=max_image_bytes,
        max_pdf_bytes=max_pdf_bytes,
        max_file_bytes=max_file_bytes,
    )


def _save_call_center_media(
    media_payload: Any,
    *,
    message_id: Optional[str] = None,
    max_image_bytes: Optional[int] = None,
    max_pdf_bytes: Optional[int] = None,
    max_file_bytes: Optional[int] = None,
) -> tuple[dict, Optional[str]]:
    if not isinstance(media_payload, Mapping):
        return {}, None

    raw_data = str(media_payload.get("data") or "").strip()
    filename = _clean_client_filename(media_payload.get("filename"))
    mime_type = _normalize_mime_type(
        str(
            media_payload.get("mimetype")
            or media_payload.get("mime_type")
            or media_payload.get("media_mime_type")
            or ""
        ),
        filename,
    )
    if not raw_data:
        return {}, None
    if not mime_type or not _is_allowed_mime(mime_type):
        return {}, _unsupported_media_message()

    try:
        compact_data = re.sub(r"\s+", "", raw_data)
        content = base64.b64decode(compact_data, validate=True)
    except Exception:
        return {}, "Lampiran tidak bisa dibaca."

    if not content:
        return {}, "Lampiran kosong."
    raw_limit = _max_media_bytes()
    if raw_limit > 0 and len(content) > raw_limit:
        return (
            {},
            f"Ukuran lampiran maksimal {_format_bytes(raw_limit)} sebelum kompresi.",
        )

    if mime_type.startswith("image/"):
        # LIMIT DINONAKTIFKAN — aktifkan kembali jika diperlukan:
        # image_limit = _coerce_limit(max_image_bytes, _max_image_bytes())
        image_limit = max_image_bytes  # None = tanpa limit ukuran
        needs_conversion = mime_type not in _WEB_SAFE_IMAGE_MIME_TYPES
        if image_limit is not None and (len(content) > image_limit or needs_conversion):
            compressed = _compress_image_for_storage(
                content,
                force=needs_conversion,
                target_bytes=image_limit,
            )
            if not compressed or len(compressed) > image_limit:
                return (
                    {},
                    f"Gambar tidak bisa dikompres di bawah {_format_bytes(image_limit)}.",
                )
            content = compressed
            mime_type = "image/webp"
            media_payload = {
                **media_payload,
                "filename": _with_suffix(media_payload.get("filename"), ".webp"),
            }
        elif image_limit is None and needs_conversion:
            # Konversi format non-web-safe tanpa limit ukuran
            compressed = _compress_image_for_storage(
                content, force=True, target_bytes=None
            )
            if compressed:
                content = compressed
                mime_type = "image/webp"
                media_payload = {
                    **media_payload,
                    "filename": _with_suffix(media_payload.get("filename"), ".webp"),
                }
    elif mime_type == "application/pdf":
        # LIMIT DINONAKTIFKAN — aktifkan kembali jika diperlukan:
        # pdf_limit = _coerce_limit(max_pdf_bytes, _max_pdf_bytes())
        pdf_limit = max_pdf_bytes  # None = tanpa limit ukuran
        if pdf_limit is not None and len(content) > pdf_limit:
            compressed = _compress_pdf_for_storage(content, target_bytes=pdf_limit)
            if not compressed or len(compressed) > pdf_limit:
                return (
                    {},
                    f"PDF tidak bisa dikompres di bawah {_format_bytes(pdf_limit)}.",
                )
            content = compressed
    else:
        # LIMIT DINONAKTIFKAN — aktifkan kembali jika diperlukan:
        # file_limit = _coerce_limit(max_file_bytes, _max_file_bytes())
        file_limit = max_file_bytes  # None = tanpa limit ukuran
        if file_limit is not None and len(content) > file_limit:
            return (
                {},
                f"Dokumen selain gambar/PDF maksimal {_format_bytes(file_limit)}.",
            )

    ext = _extension_for_payload(media_payload, mime_type)
    stem_seed = (message_id or "").strip()
    if stem_seed:
        stem = hashlib.sha256(stem_seed.encode("utf-8")).hexdigest()[:24]
    else:
        stem = hashlib.sha256(content).hexdigest()[:24]
    stored_filename = f"{stem}{ext}"

    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    relative_dir = PurePosixPath(now.strftime("%Y/%m/%d"))
    target_dir = CC_MEDIA_ROOT / relative_dir.as_posix()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return {}, "Folder penyimpanan lampiran tidak bisa dibuat."
    target_path = target_dir / stored_filename

    if not target_path.exists():
        try:
            target_path.write_bytes(content)
        except OSError:
            return {}, "Lampiran gagal disimpan di server."

    client_filename = _clean_client_filename(media_payload.get("filename"))
    display_filename = client_filename or stored_filename
    relative_path = (relative_dir / stored_filename).as_posix()
    return {
        "media_path": relative_path,
        "media_mime_type": mime_type,
        "media_filename": display_filename,
        "media_size": len(content),
    }, None


def resolve_call_center_media_path(filename: str) -> Optional[Path]:
    """Resolve a stored media path, rejecting traversal and absolute paths."""
    normalized = (filename or "").replace("\\", "/").strip()
    requested = PurePosixPath(normalized)
    if not normalized or requested.is_absolute() or ".." in requested.parts:
        return None

    target_path = (CC_MEDIA_ROOT / requested.as_posix()).resolve()
    try:
        target_path.relative_to(CC_MEDIA_ROOT.resolve())
    except ValueError:
        return None
    return target_path


def _is_allowed_mime(mime_type: str) -> bool:
    # FILTER MIME DINONAKTIFKAN — aktifkan kembali jika diperlukan:
    # return mime_type in _ALLOWED_MIME_TYPES
    return bool(mime_type)  # Terima semua tipe MIME yang valid


def _normalize_mime_type(raw_mime_type: str, filename: str) -> str:
    mime_type = (raw_mime_type or "").split(";", 1)[0].strip().lower()
    if mime_type == "image/pjpeg":
        mime_type = "image/jpeg"
    elif mime_type == "image/x-png":
        mime_type = "image/png"
    elif mime_type == "application/x-pdf":
        mime_type = "application/pdf"

    suffix = Path(filename or "").suffix.lower()
    if suffix in _SUFFIX_MIME_TYPES and (
        not mime_type
        or mime_type == "application/octet-stream"
        or not _is_allowed_mime(mime_type)
        or (suffix == ".csv" and mime_type == "application/vnd.ms-excel")
    ):
        return _SUFFIX_MIME_TYPES[suffix]

    if mime_type and mime_type != "application/octet-stream":
        return mime_type

    guessed, _ = mimetypes.guess_type(filename or "")
    return (guessed or mime_type).strip().lower()


def _extension_for_payload(media_payload: Mapping[str, Any], mime_type: str) -> str:
    raw_filename = _clean_client_filename(media_payload.get("filename"))
    if raw_filename:
        suffix = Path(raw_filename).suffix.lower()
        if suffix and suffix in _MIME_ALLOWED_SUFFIXES.get(mime_type, set()):
            return suffix
    return (
        _MIME_EXTENSIONS.get(mime_type)
        or mimetypes.guess_extension(mime_type)
        or ".bin"
    )


def _clean_client_filename(raw_name: Any) -> str:
    clean = secure_filename(Path(str(raw_name or "").strip()).name)
    return clean[:180]


def _compress_image_for_storage(
    content: bytes,
    *,
    force: bool = False,
    target_bytes: Optional[int] = None,
) -> Optional[bytes]:
    if target_bytes is not None and len(content) <= target_bytes and not force:
        return None

    try:
        with Image.open(io.BytesIO(content)) as original:
            image = ImageOps.exif_transpose(original)
            image.load()
    except Exception:
        return None

    if getattr(image, "is_animated", False):
        try:
            image.seek(0)
        except Exception:
            pass

    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

    if target_bytes is None:
        output = io.BytesIO()
        try:
            image.save(output, format="WEBP", quality=82, method=6)
        except Exception:
            return None
        return output.getvalue()

    effective_target = target_bytes
    max_side = min(max(image.size), _max_image_side())
    best: Optional[bytes] = None

    while max_side >= 360:
        resized = _resize_to_max_side(image, max_side)
        if resized.mode not in {"RGB", "RGBA"}:
            resized = resized.convert("RGBA" if "A" in resized.getbands() else "RGB")

        for quality in (82, 72, 62, 52, 42, 32, 24):
            output = io.BytesIO()
            try:
                resized.save(output, format="WEBP", quality=quality, method=6)
            except Exception:
                return best

            candidate = output.getvalue()
            if best is None or len(candidate) < len(best):
                best = candidate
            if len(candidate) <= effective_target:
                return candidate

        max_side = int(max_side * 0.82)

    return best


def _resize_to_max_side(image: Image.Image, max_side: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image.copy()

    scale = max_side / float(longest)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _compress_pdf_for_storage(
    content: bytes, *, target_bytes: Optional[int] = None
) -> Optional[bytes]:
    target_bytes = target_bytes or _max_pdf_bytes()
    best = _rewrite_pdf_for_storage(content)
    if best and len(best) <= target_bytes:
        return best

    image_best = _compress_pdf_images_for_storage(content, target_bytes=target_bytes)
    if image_best and (best is None or len(image_best) < len(best)):
        best = image_best

    return best


def _rewrite_pdf_for_storage(content: bytes) -> Optional[bytes]:
    if PdfReader is None or PdfWriter is None:
        return None

    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        writer = PdfWriter()
        for page in reader.pages:
            try:
                page.compress_content_streams()
            except Exception:
                pass
            writer.add_page(page)
        writer.add_metadata({})
        try:
            writer.compress_identical_objects(
                remove_identicals=True, remove_orphans=True
            )
        except Exception:
            pass

        output = io.BytesIO()
        writer.write(output)
        candidate = output.getvalue()
    except Exception:
        return None

    if not candidate or len(candidate) >= len(content):
        return None
    return candidate


def _compress_pdf_images_for_storage(
    content: bytes, *, target_bytes: int
) -> Optional[bytes]:
    if PdfReader is None or PdfWriter is None:
        return None

    best: Optional[bytes] = None
    # More aggressive steps are intentionally last because they trade image
    # clarity for size only when the PDF is still above the configured limit.
    attempts = (
        (1.0, 70),
        (0.85, 64),
        (0.7, 58),
        (0.55, 50),
        (0.42, 44),
        (0.32, 38),
        (0.24, 32),
    )

    for scale, quality in attempts:
        candidate = _rewrite_pdf_with_image_options(
            content,
            scale=scale,
            quality=quality,
        )
        if not candidate or len(candidate) >= len(content):
            continue
        if best is None or len(candidate) < len(best):
            best = candidate
        if len(candidate) <= target_bytes:
            return candidate

    return best


def _rewrite_pdf_with_image_options(
    content: bytes,
    *,
    scale: float,
    quality: int,
) -> Optional[bytes]:
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        writer = PdfWriter()
        for page in reader.pages:
            try:
                page.compress_content_streams()
            except Exception:
                pass
            writer.add_page(page)

        replaced = 0
        for page in writer.pages:
            for image_file in list(page.images):
                try:
                    image = image_file.image
                    image.load()
                    replacement = _prepare_pdf_image(image, scale=scale)
                    image_file.replace(replacement, quality=quality, optimize=True)
                    replaced += 1
                except Exception:
                    continue

        if not replaced:
            return None
        writer.add_metadata({})
        try:
            writer.compress_identical_objects(
                remove_identicals=True, remove_orphans=True
            )
        except Exception:
            pass

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
    except Exception:
        return None


def _prepare_pdf_image(image: Image.Image, *, scale: float) -> Image.Image:
    if getattr(image, "is_animated", False):
        try:
            image.seek(0)
        except Exception:
            pass

    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        flattened = Image.new("RGB", rgba.size, (255, 255, 255))
        flattened.paste(rgba, mask=rgba.getchannel("A"))
        image = flattened
    elif image.mode != "RGB":
        image = image.convert("RGB")
    else:
        image = image.copy()

    if scale < 1:
        width, height = image.size
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        if new_size != image.size:
            image = image.resize(new_size, Image.Resampling.LANCZOS)

    return image


def _with_suffix(raw_name: Any, suffix: str) -> str:
    clean_name = _clean_client_filename(raw_name)
    if not clean_name:
        return ""
    return f"{Path(clean_name).stem}{suffix}"


def _unsupported_media_message() -> str:
    return (
        "Tipe lampiran belum didukung. Gunakan JPG/PNG/WebP/GIF/HEIC, PDF, "
        "DOC/DOCX, XLS/XLSX, PPT/PPTX, TXT, atau CSV."
    )


def _format_bytes(size: int) -> str:
    value = float(size or 0)
    for unit in ("B", "KB", "MB"):
        if value < 1024 or unit == "MB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} MB"


def _coerce_limit(value: Optional[int], default: int) -> int:
    try:
        if value is None:
            return max(1, int(default))
        return max(1, int(value))
    except (TypeError, ValueError):
        return max(1, int(default))


def _max_image_bytes() -> int:
    try:
        return max(1, int(os.getenv("ASKA_CC_IMAGE_MAX_BYTES", "102400")))
    except ValueError:
        return 100 * 1024


def _max_pdf_bytes() -> int:
    try:
        return max(1, int(os.getenv("ASKA_CC_PDF_MAX_BYTES", "307200")))
    except ValueError:
        return 300 * 1024


def _max_file_bytes() -> int:
    try:
        return max(1, int(os.getenv("ASKA_CC_FILE_MAX_BYTES", "307200")))
    except ValueError:
        return 300 * 1024


def _max_image_side() -> int:
    try:
        return max(360, int(os.getenv("ASKA_CC_IMAGE_MAX_SIDE", "1280")))
    except ValueError:
        return 1280


def _max_media_bytes() -> int:
    try:
        return max(0, int(os.getenv("ASKA_CC_MEDIA_MAX_BYTES", "0")))
    except ValueError:
        return 0
