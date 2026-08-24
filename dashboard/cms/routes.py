"""Routes untuk Content Management System (CMS)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable

from flask import Blueprint, jsonify, render_template, request, url_for
from werkzeug.utils import secure_filename

from dashboard.auth import current_user, role_required
from dashboard.db_access import get_cursor
from dashboard.schema import ensure_cms_artikel_schema, ensure_cms_publication_schema

cms_bp = Blueprint("cms", __name__, url_prefix="/cms", template_folder="templates")

# Configuration
UPLOADS_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
PORTAL_UPLOAD_ROOT = UPLOADS_ROOT / "portal"
CMS_UPLOAD_ROOT = PORTAL_UPLOAD_ROOT / "cms"
UPLOAD_PROFIL = CMS_UPLOAD_ROOT / "profil_instansi"
UPLOAD_ARTIKEL_ROOT = CMS_UPLOAD_ROOT / "artikel"
UPLOAD_ARTIKEL_THUMBNAILS = UPLOAD_ARTIKEL_ROOT / "thumbnails"
UPLOAD_ARTIKEL_ATTACHMENTS = UPLOAD_ARTIKEL_ROOT / "attachments"
UPLOAD_PENGUMUMAN_ROOT = CMS_UPLOAD_ROOT / "pengumuman"
UPLOAD_PENGUMUMAN_THUMBNAILS = UPLOAD_PENGUMUMAN_ROOT / "thumbnails"
UPLOAD_PENGUMUMAN_ATTACHMENTS = UPLOAD_PENGUMUMAN_ROOT / "attachments"
UPLOAD_GALERI_ROOT = CMS_UPLOAD_ROOT / "galeri"
UPLOAD_GALERI_THUMBNAILS = UPLOAD_GALERI_ROOT / "thumbnails"
UPLOAD_GALERI_IMAGES = UPLOAD_GALERI_ROOT / "images"
for _path in (
    UPLOAD_PROFIL,
    UPLOAD_ARTIKEL_THUMBNAILS,
    UPLOAD_ARTIKEL_ATTACHMENTS,
    UPLOAD_PENGUMUMAN_THUMBNAILS,
    UPLOAD_PENGUMUMAN_ATTACHMENTS,
    UPLOAD_GALERI_THUMBNAILS,
    UPLOAD_GALERI_IMAGES,
):
    _path.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_ATTACHMENT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "txt",
    "csv",
    "zip",
    "rar",
    "jpg",
    "jpeg",
    "png",
    "webp",
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ARTICLE_CATEGORIES = (
    "Berita Utama",
    "Pendidikan",
    "Kegiatan",
    "Pengumuman",
    "Opini",
    "Informasi",
)
_CMS_ARTIKEL_SCHEMA_READY = False
_CMS_PUBLICATION_SCHEMA_READY = False


def allowed_file(filename):
    """Check if file extension is allowed."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


def _allowed_attachment_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_ATTACHMENT_EXTENSIONS
    )


def _safe_client_filename(raw_name: str | None) -> str:
    return Path((raw_name or "").strip()).name


def _get_file_size(file_storage) -> int:
    if getattr(file_storage, "content_length", None):
        return int(file_storage.content_length)

    stream = getattr(file_storage, "stream", None)
    if stream is None:
        return 0

    try:
        current_position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(current_position)
        return int(size)
    except Exception:
        return 0


def _build_db_upload_path(uploaded_path: Path) -> str:
    relative_path = uploaded_path.resolve().relative_to(UPLOADS_ROOT.resolve())
    return (
        PurePosixPath("uploads") / PurePosixPath(relative_path.as_posix())
    ).as_posix()


def _resolve_stored_upload_path(stored_path: str | None) -> Path | None:
    normalized = str(stored_path or "").replace("\\", "/").strip()
    if not normalized.startswith("uploads/"):
        return None

    relative = PurePosixPath(normalized[len("uploads/") :].lstrip("/"))
    if relative.is_absolute() or ".." in relative.parts:
        return None

    target_path = (UPLOADS_ROOT / relative.as_posix()).resolve()
    try:
        target_path.relative_to(UPLOADS_ROOT.resolve())
    except ValueError:
        return None
    return target_path


def _delete_stored_file(stored_path: str | None) -> None:
    target_path = _resolve_stored_upload_path(stored_path)
    if target_path and target_path.is_file():
        try:
            target_path.unlink(missing_ok=True)
        except OSError:
            pass


def _build_upload_url(stored_path: str | None) -> str | None:
    normalized = str(stored_path or "").replace("\\", "/").strip()
    if not normalized.startswith("uploads/portal/"):
        return None

    target_path = _resolve_stored_upload_path(normalized)
    if not target_path or not target_path.is_file():
        return None

    relative = normalized[len("uploads/portal/") :].lstrip("/")
    if not relative:
        return None
    return url_for("portal.uploaded_file", filename=relative)


def _save_uploaded_asset(
    file_storage,
    *,
    upload_dir: Path,
    prefix: str,
    max_size: int,
    validator,
    label: str,
) -> tuple[str, str]:
    original_name = _safe_client_filename(getattr(file_storage, "filename", ""))
    if not original_name:
        raise ValueError(f"{label} tidak valid.")
    if not validator(original_name):
        raise ValueError(f"Format {label.lower()} tidak didukung.")

    file_size = _get_file_size(file_storage)
    if max_size and file_size > max_size:
        raise ValueError(f"{label} terlalu besar.")

    safe_name = secure_filename(original_name)
    if not safe_name:
        safe_name = f"{prefix}{Path(original_name).suffix.lower()}"
    stored_name = secure_filename(f"{prefix}_{os.urandom(8).hex()}_{safe_name}")
    destination = upload_dir / stored_name
    file_storage.save(destination)
    return original_name, _build_db_upload_path(destination)


def _current_author_name() -> str:
    user = current_user() or {}
    return (user.get("full_name") or user.get("email") or "Admin").strip() or "Admin"


def _ensure_artikel_schema() -> None:
    global _CMS_ARTIKEL_SCHEMA_READY
    if _CMS_ARTIKEL_SCHEMA_READY:
        return

    try:
        ensure_cms_artikel_schema()
    except Exception as exc:
        message = str(exc)
        if "pg_type_typname_nsp_index" not in message or "cms_artikel" not in message:
            raise
    _CMS_ARTIKEL_SCHEMA_READY = True


def _ensure_publication_schema() -> None:
    global _CMS_PUBLICATION_SCHEMA_READY
    if _CMS_PUBLICATION_SCHEMA_READY:
        return
    ensure_cms_publication_schema()
    _CMS_PUBLICATION_SCHEMA_READY = True


def _parse_date_field(name: str, label: str):
    raw_value = (request.form.get(name) or "").strip()
    if not raw_value:
        raise ValueError(f"{label} wajib diisi.")
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Format {label.lower()} tidak valid.") from exc


def _publication_status() -> tuple[str, str]:
    status = "Aktif" if request.form.get("statusAktif") == "Aktif" else "Tidak Aktif"
    publication = (
        "Published"
        if request.form.get("statusPublikasi") == "Published"
        else "Draft"
    )
    return status, publication


def _save_file_entries(
    files,
    *,
    upload_dir: Path,
    prefix: str,
    validator,
    max_size: int,
    label: str,
) -> list[dict]:
    entries: list[dict] = []
    for file_storage in files:
        if not _safe_client_filename(getattr(file_storage, "filename", "")):
            continue
        original_name, stored_path = _save_uploaded_asset(
            file_storage,
            upload_dir=upload_dir,
            prefix=prefix,
            max_size=max_size,
            validator=validator,
            label=label,
        )
        entries.append(
            {
                "id": os.urandom(6).hex(),
                "name": original_name,
                "path": stored_path,
            }
        )
    return entries


def _json_list(value) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except (TypeError, ValueError):
            pass
    return []


def _serialize_media_entries(value) -> list[dict]:
    return [
        {**entry, "url": _build_upload_url(entry.get("path"))}
        for entry in _json_list(value)
    ]


def _stored_media_entries(value) -> list[dict]:
    return [
        {
            "id": entry.get("id") or os.urandom(6).hex(),
            "name": entry.get("name") or Path(entry.get("path") or "file").name,
            "path": entry.get("path"),
        }
        for entry in _json_list(value)
        if entry.get("path")
    ]


def _parse_int_list(values: Iterable[str]) -> list[int]:
    parsed: list[int] = []
    for value in values:
        try:
            parsed.append(int(value))
        except (TypeError, ValueError):
            continue
    return parsed


def _parse_artikel_payload(*, require_thumbnail: bool) -> dict:
    judul = (request.form.get("judul") or "").strip()
    kategori = (request.form.get("kategori") or "").strip()
    deskripsi = request.form.get("deskripsi") or ""
    tanggal_raw = (request.form.get("tanggal") or "").strip()
    penulis = (request.form.get("penulis") or "").strip() or _current_author_name()
    status = "Aktif" if request.form.get("statusAktif") == "Aktif" else "Tidak Aktif"
    status_publikasi = (
        "Published" if request.form.get("statusPublikasi") == "Published" else "Draft"
    )
    thumbnail = request.files.get("thumbnail")
    lampiran = [
        file
        for file in request.files.getlist("lampiran")
        if _safe_client_filename(file.filename)
    ]

    if not judul:
        raise ValueError("Judul artikel wajib diisi.")
    if kategori not in ARTICLE_CATEGORIES:
        raise ValueError("Kategori artikel tidak valid.")
    if not deskripsi.strip():
        raise ValueError("Isi artikel wajib diisi.")
    if not tanggal_raw:
        raise ValueError("Tanggal publikasi wajib diisi.")

    try:
        tanggal_publikasi = datetime.strptime(tanggal_raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Format tanggal publikasi tidak valid.") from exc

    has_thumbnail = thumbnail and _safe_client_filename(thumbnail.filename)
    if require_thumbnail and not has_thumbnail:
        raise ValueError("Thumbnail wajib diunggah.")

    return {
        "judul": judul,
        "kategori": kategori,
        "deskripsi": deskripsi,
        "tanggal_publikasi": tanggal_publikasi,
        "penulis": penulis,
        "status": status,
        "status_publikasi": status_publikasi,
        "thumbnail": thumbnail if has_thumbnail else None,
        "lampiran": lampiran,
        "hapus_file_ids": _parse_int_list(request.form.getlist("hapus_file_ids")),
    }


def _serialize_artikel_file(row: dict) -> dict:
    file_path = row.get("file_path")
    return {
        "id": row.get("id"),
        "name": row.get("file_name"),
        "path": file_path,
        "url": _build_upload_url(file_path),
    }


def _serialize_artikel_row(row: dict, attachments: list[dict]) -> dict:
    tanggal_obj = row.get("tanggal_publikasi")
    tanggal_input = tanggal_obj.isoformat() if tanggal_obj else ""
    tanggal_display = tanggal_obj.strftime("%d %b %Y") if tanggal_obj else "-"
    thumbnail_path = row.get("thumbnail_path")

    return {
        "id": row.get("id"),
        "judul": row.get("judul"),
        "kategori": row.get("kategori"),
        "tanggal": tanggal_input,
        "tanggal_input": tanggal_input,
        "tanggal_display": tanggal_display,
        "deskripsi": row.get("deskripsi") or "",
        "thumbnail": Path(thumbnail_path).name if thumbnail_path else "",
        "thumbnail_path": thumbnail_path,
        "thumbnail_url": _build_upload_url(thumbnail_path),
        "penulis": row.get("penulis") or "-",
        "status": row.get("status") or "Tidak Aktif",
        "status_publikasi": row.get("status_publikasi") or "Draft",
        "files": attachments,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _fetch_artikel_files(cur, artikel_ids: list[int]) -> dict[int, list[dict]]:
    if not artikel_ids:
        return {}

    cur.execute(
        """
        SELECT id, artikel_id, file_name, file_path, created_at
        FROM cms_artikel_files
        WHERE artikel_id = ANY(%s)
        ORDER BY id ASC
        """,
        (artikel_ids,),
    )

    grouped: dict[int, list[dict]] = {}
    for row in cur.fetchall():
        record = dict(row)
        grouped.setdefault(record["artikel_id"], []).append(
            _serialize_artikel_file(record)
        )
    return grouped


def _fetch_all_artikel() -> list[dict]:
    _ensure_artikel_schema()
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, judul, kategori, tanggal_publikasi, deskripsi, thumbnail_path,
                   penulis, status, status_publikasi, created_at, updated_at
            FROM cms_artikel
            ORDER BY tanggal_publikasi DESC, created_at DESC, id DESC
            """)
        rows = [dict(row) for row in cur.fetchall()]
        attachments = _fetch_artikel_files(cur, [row["id"] for row in rows])

    return [_serialize_artikel_row(row, attachments.get(row["id"], [])) for row in rows]


def _fetch_artikel_by_id(artikel_id: int) -> dict | None:
    _ensure_artikel_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, judul, kategori, tanggal_publikasi, deskripsi, thumbnail_path,
                   penulis, status, status_publikasi, created_at, updated_at
            FROM cms_artikel
            WHERE id = %s
            LIMIT 1
            """,
            (artikel_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        article = dict(row)
        attachments = _fetch_artikel_files(cur, [artikel_id])

    return _serialize_artikel_row(article, attachments.get(artikel_id, []))


def _get_profil_instansi():
    """Ambil profil instansi terbaru."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM cms_profil_instansi ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()

    if not row:
        return None

    return dict(row)


def _serialize_public_profil_instansi(profil: dict | None) -> dict:
    """Bangun payload profil yang stabil untuk landing page publik."""
    profil = profil or {}
    updated_at = profil.get("updated_at")

    return {
        "deskripsi_utama": profil.get("cms_deskripsi_utama") or "",
        "visi": profil.get("cms_visi") or "",
        "misi": profil.get("cms_misi") or "",
        "tugas_fungsi": profil.get("cms_tugas_fungsi") or "",
        "motto_pelayanan": profil.get("cms_motto_pelayanan") or "",
        "struktur_organisasi_url": _build_upload_url(
            profil.get("cms_struktur_organisasi")
        ),
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def _save_profil_instansi(data):
    """Simpan atau update profil instansi."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cms_profil_instansi 
            (cms_deskripsi_utama, cms_visi, cms_misi, cms_tugas_fungsi, cms_motto_pelayanan, cms_struktur_organisasi, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            """,
            (
                data.get("cms_deskripsi_utama"),
                data.get("cms_visi"),
                data.get("cms_misi"),
                data.get("cms_tugas_fungsi"),
                data.get("cms_motto_pelayanan"),
                data.get("cms_struktur_organisasi"),
            ),
        )


@cms_bp.route("/")
@role_required("admin")
def dashboard():
    """Halaman dashboard utama CMS."""

    # Dummy summary stats
    dummy_stats = {
        "total_layanan": 12,
        "layanan_aktif": 10,
        "total_artikel": 45,
        "pengumuman_aktif": 5,
        "total_galeri": 24,
        "visitor_today": 128,
        "visitor_month": 3450,
    }

    # Dummy chart data (misal: statistik kunjungan bulanan)
    chart_kunjungan = {
        "labels": ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun"],
        "data": [2100, 2400, 2200, 2800, 3100, 3450],
    }

    # Dummy recent items
    recent_activities = [
        {
            "time": "10 menit yang lalu",
            "user": "Admin Server",
            "action": "Menambahkan artikel baru",
            "item": "Sosialisasi Program...",
        },
        {
            "time": "2 jam yang lalu",
            "user": "Humas Sudin RU2",
            "action": "Menyimpan draft pengumuman",
            "item": "Pendataan KJP Plus...",
        },
        {
            "time": "Kemarin, 14:30",
            "user": "Admin Server",
            "action": "Mengupload galeri foto",
            "item": "Peringatan Hari Guru...",
        },
    ]

    # Dummy Draft Data
    drafts = {
        "artikel": [
            {"judul": "Persiapan Ujian Nasional 2024", "tanggal": "Belum Dipublikasi"},
            {"judul": "Kegiatan Pramuka Kwarcab", "tanggal": "Belum Dipublikasi"},
        ],
        "pengumuman": [
            {"judul": "Revisi Jadwal Lomba OSN", "tanggal": "Belum Dipublikasi"}
        ],
        "galeri": [
            {"judul": "Pelatihan Guru Penggerak", "tanggal": "Belum Dipublikasi"},
            {"judul": "Rapat Kerja Tahunan 2024", "tanggal": "Belum Dipublikasi"},
        ],
    }

    return render_template(
        "cms/index.html",
        stats=dummy_stats,
        chart_kunjungan=chart_kunjungan,
        recent_activities=recent_activities,
        drafts=drafts,
    )


@cms_bp.route("/profil", methods=["GET", "POST"])
@role_required("admin")
def profil():
    """Halaman untuk mengelola profil instansi."""

    if request.method == "POST":
        try:
            # Get form data
            cms_deskripsi_utama = request.form.get("cms_deskripsi_utama", "")
            cms_visi = request.form.get("cms_visi", "")
            cms_misi = request.form.get("cms_misi", "")
            cms_motto_pelayanan = request.form.get("cms_motto_pelayanan", "")
            cms_tugas_fungsi = request.form.get("cms_tugas_fungsi", "")

            # Get existing profil for old file references
            existing_profil = _get_profil_instansi()

            # Handle gambar struktur organisasi
            cms_struktur_organisasi = None
            if "cms_struktur_organisasi" in request.files:
                file = request.files["cms_struktur_organisasi"]
                if file and file.filename and allowed_file(file.filename):
                    if _get_file_size(file) > MAX_IMAGE_SIZE:
                        return (
                            jsonify(
                                {
                                    "success": False,
                                    "error": "File struktur organisasi terlalu besar",
                                }
                            ),
                            400,
                        )

                    filename = secure_filename(
                        f"struktur_organisasi_{os.urandom(8).hex()}_{file.filename}"
                    )
                    filepath = UPLOAD_PROFIL / filename
                    file.save(filepath)
                    cms_struktur_organisasi = (
                        f"uploads/portal/cms/profil_instansi/{filename}"
                    )
                else:
                    cms_struktur_organisasi = (
                        existing_profil.get("cms_struktur_organisasi")
                        if existing_profil
                        else None
                    )
            else:
                cms_struktur_organisasi = (
                    existing_profil.get("cms_struktur_organisasi")
                    if existing_profil
                    else None
                )

            # Save data
            data = {
                "cms_deskripsi_utama": cms_deskripsi_utama,
                "cms_visi": cms_visi,
                "cms_misi": cms_misi,
                "cms_motto_pelayanan": cms_motto_pelayanan,
                "cms_struktur_organisasi": cms_struktur_organisasi,
                "cms_tugas_fungsi": cms_tugas_fungsi,
            }

            _save_profil_instansi(data)

            return jsonify(
                {"success": True, "message": "Profil instansi berhasil disimpan"}
            )

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # GET request - load existing data
    profil_data = _get_profil_instansi()

    return render_template("cms/profil_instansi.html", profil=profil_data or {})


@cms_bp.route("/api/public/profil", methods=["GET"])
def public_profil():
    """Endpoint baca-saja untuk menampilkan profil CMS pada landing page."""
    profil_data = _get_profil_instansi()
    return jsonify(
        {
            "success": True,
            "data": _serialize_public_profil_instansi(profil_data),
        }
    )


def _get_informasi_publik():
    """Ambil informasi publik terbaru."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM cms_informasi_publik ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()

    if not row:
        return None

    return dict(row)


def _save_informasi_publik(data):
    """Simpan atau update informasi publik."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cms_informasi_publik 
            (cms_jaminan_pelayanan, cms_keamanan_keselamatan, cms_kompensasi_pelayanan, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            """,
            (
                data.get("cms_jaminan_pelayanan"),
                data.get("cms_keamanan_keselamatan"),
                data.get("cms_kompensasi_pelayanan"),
            ),
        )


@cms_bp.route("/informasi-publik", methods=["GET", "POST"])
@role_required("admin")
def informasi_publik():
    """Halaman untuk mengelola informasi publik."""

    if request.method == "POST":
        try:
            jaminan_pelayanan = request.form.get("cms_jaminan_pelayanan", "")
            keamanan_keselamatan = request.form.get("cms_keamanan_keselamatan", "")
            kompensasi_pelayanan = request.form.get("cms_kompensasi_pelayanan", "")

            data = {
                "cms_jaminan_pelayanan": jaminan_pelayanan,
                "cms_keamanan_keselamatan": keamanan_keselamatan,
                "cms_kompensasi_pelayanan": kompensasi_pelayanan,
            }

            _save_informasi_publik(data)

            return jsonify(
                {"success": True, "message": "Informasi publik berhasil disimpan"}
            )

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    info_data = _get_informasi_publik()

    return render_template("cms/informasi_publik.html", info=info_data or {})


# ---- Layanan Publik CRUD ----

UPLOAD_LAYANAN = CMS_UPLOAD_ROOT / "layanan_publik"
UPLOAD_LAYANAN.mkdir(parents=True, exist_ok=True)
ALLOWED_DOC_EXTENSIONS = {"pdf", "doc", "docx"}


def _allowed_doc(filename):
    """Check if file extension is allowed for documents."""
    return (
        "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_DOC_EXTENSIONS
    )


def _list_layanan_publik(limit=None, offset=None):
    """Ambil data layanan publik dengan pagination."""
    with get_cursor() as cur:
        sql = "SELECT * FROM cms_layanan_publik ORDER BY id ASC"
        params = []
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        if offset is not None:
            sql += " OFFSET %s"
            params.append(offset)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def _count_layanan_publik():
    """Hitung total data layanan publik."""
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cms_layanan_publik")
        res = cur.fetchone()
    return res[0] if res else 0


def _get_layanan_by_id(layanan_id):
    """Ambil satu layanan publik by ID."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM cms_layanan_publik WHERE id = %s", (layanan_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def _save_uploaded_files(files):
    """Save uploaded files and return metadata list."""
    import uuid

    file_entries = []
    for f in files:
        if f and f.filename and _allowed_doc(f.filename):
            file_id = uuid.uuid4().hex[:12]
            safe_name = secure_filename(f.filename)
            stored_name = f"{file_id}_{safe_name}"
            filepath = UPLOAD_LAYANAN / stored_name
            f.save(filepath)
            file_entries.append(
                {
                    "id": file_id,
                    "name": safe_name,
                    "path": f"uploads/portal/cms/layanan_publik/{stored_name}",
                    "size": os.path.getsize(filepath),
                }
            )
    return file_entries


@cms_bp.route("/layanan-publik")
@role_required("admin")
def layanan_publik():
    """Halaman untuk mengelola layanan publik."""
    page = request.args.get("page", 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    total_items = _count_layanan_publik()
    data = _list_layanan_publik(limit=per_page, offset=offset)

    total_pages = (total_items + per_page - 1) // per_page

    # Parse cms_files JSON if it's a string
    for item in data:
        if isinstance(item.get("cms_files"), str):
            item["cms_files"] = json.loads(item["cms_files"])

    pagination = {
        "current_page": page,
        "total_pages": total_pages,
        "total_items": total_items,
        "per_page": per_page,
        "start_index": offset + 1 if total_items > 0 else 0,
        "end_index": min(offset + per_page, total_items),
    }

    return render_template(
        "cms/layanan_publik.html", layanan=data, pagination=pagination
    )


@cms_bp.route("/layanan-publik/tambah", methods=["POST"])
@role_required("admin")
def layanan_publik_tambah():
    """Tambah layanan publik baru."""
    try:
        nama = request.form.get("cms_nama_layanan", "").strip()
        deskripsi = request.form.get("cms_deskripsi", "").strip()
        icon = request.form.get("cms_icon", "bi-star").strip()
        status = request.form.get("cms_status", "Aktif").strip()
        if not nama:
            return jsonify({"success": False, "error": "Nama layanan wajib diisi"}), 400

        # Handle file uploads
        uploaded = request.files.getlist("cms_files")
        file_entries = _save_uploaded_files(uploaded)

        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO cms_layanan_publik
                (cms_nama_layanan, cms_deskripsi, cms_icon, cms_status, cms_files, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW(), NOW())
                """,
                (nama, deskripsi, icon, status, json.dumps(file_entries)),
            )
        return jsonify(
            {"success": True, "message": "Layanan publik berhasil ditambahkan"}
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@cms_bp.route("/layanan-publik/<int:layanan_id>/edit", methods=["POST"])
@role_required("admin")
def layanan_publik_edit(layanan_id):
    """Update layanan publik."""
    try:
        existing = _get_layanan_by_id(layanan_id)
        if not existing:
            return jsonify({"success": False, "error": "Layanan tidak ditemukan"}), 404

        nama = request.form.get("cms_nama_layanan", "").strip()
        deskripsi = request.form.get("cms_deskripsi", "").strip()
        icon = request.form.get("cms_icon", "bi-star").strip()
        status = request.form.get("cms_status", "Aktif").strip()
        if not nama:
            return jsonify({"success": False, "error": "Nama layanan wajib diisi"}), 400

        # Existing files — remove deleted ones
        existing_files = existing.get("cms_files", [])
        if isinstance(existing_files, str):
            existing_files = json.loads(existing_files)

        deleted_ids = request.form.getlist("deleted_file_ids")
        kept_files = []
        for f in existing_files:
            if f.get("id") in deleted_ids:
                # Delete physical file
                try:
                    phys = Path(__file__).parent.parent.parent / f.get("path", "")
                    if phys.exists():
                        phys.unlink()
                except Exception:
                    pass
            else:
                kept_files.append(f)

        # Handle new file uploads
        uploaded = request.files.getlist("cms_files")
        new_entries = _save_uploaded_files(uploaded)
        all_files = kept_files + new_entries

        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE cms_layanan_publik
                SET cms_nama_layanan = %s, cms_deskripsi = %s, cms_icon = %s,
                    cms_status = %s, cms_files = %s::jsonb, updated_at = NOW()
                WHERE id = %s
                """,
                (nama, deskripsi, icon, status, json.dumps(all_files), layanan_id),
            )
        return jsonify(
            {"success": True, "message": "Layanan publik berhasil diperbarui"}
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@cms_bp.route("/layanan-publik/<int:layanan_id>/hapus", methods=["POST"])
@role_required("admin")
def layanan_publik_hapus(layanan_id):
    """Hapus layanan publik."""
    try:
        existing = _get_layanan_by_id(layanan_id)
        if not existing:
            return jsonify({"success": False, "error": "Layanan tidak ditemukan"}), 404

        # Delete physical files
        files = existing.get("cms_files", [])
        if isinstance(files, str):
            files = json.loads(files)
        for f in files:
            try:
                phys = Path(__file__).parent.parent.parent / f.get("path", "")
                if phys.exists():
                    phys.unlink()
            except Exception:
                pass

        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM cms_layanan_publik WHERE id = %s", (layanan_id,))
        return jsonify({"success": True, "message": "Layanan publik berhasil dihapus"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@cms_bp.route("/artikel", methods=["GET", "POST"])
@role_required("admin")
def artikel():
    """Halaman untuk mengelola artikel (media & publikasi)."""

    if request.method == "POST":
        _ensure_artikel_schema()
        try:
            payload = _parse_artikel_payload(require_thumbnail=True)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        actor = current_user() or {}
        actor_id = actor.get("id")
        saved_paths: list[str] = []

        try:
            thumbnail_path = None
            if payload["thumbnail"] is not None:
                _, thumbnail_path = _save_uploaded_asset(
                    payload["thumbnail"],
                    upload_dir=UPLOAD_ARTIKEL_THUMBNAILS,
                    prefix="artikel_thumb",
                    max_size=MAX_IMAGE_SIZE,
                    validator=allowed_file,
                    label="Thumbnail",
                )
                saved_paths.append(thumbnail_path)

            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    INSERT INTO cms_artikel
                    (judul, kategori, tanggal_publikasi, deskripsi, thumbnail_path, penulis, status, status_publikasi, created_by, updated_by, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (
                        payload["judul"],
                        payload["kategori"],
                        payload["tanggal_publikasi"],
                        payload["deskripsi"],
                        thumbnail_path,
                        payload["penulis"],
                        payload["status"],
                        payload["status_publikasi"],
                        actor_id,
                        actor_id,
                    ),
                )
                artikel_id = int(cur.fetchone()["id"])

                for attachment in payload["lampiran"]:
                    original_name, stored_path = _save_uploaded_asset(
                        attachment,
                        upload_dir=UPLOAD_ARTIKEL_ATTACHMENTS,
                        prefix=f"artikel_file_{artikel_id}",
                        max_size=MAX_ATTACHMENT_SIZE,
                        validator=_allowed_attachment_file,
                        label="Lampiran",
                    )
                    saved_paths.append(stored_path)
                    cur.execute(
                        """
                        INSERT INTO cms_artikel_files (artikel_id, file_name, file_path, created_at)
                        VALUES (%s, %s, %s, NOW())
                        """,
                        (artikel_id, original_name, stored_path),
                    )

            return jsonify(
                {
                    "success": True,
                    "message": "Artikel berhasil ditambahkan.",
                    "artikel_id": artikel_id,
                }
            )

        except ValueError as exc:
            for stored_path in saved_paths:
                _delete_stored_file(stored_path)
            return jsonify({"success": False, "error": str(exc)}), 400
        except Exception as exc:
            for stored_path in saved_paths:
                _delete_stored_file(stored_path)
            return jsonify({"success": False, "error": str(exc)}), 500

    artikel_list = _fetch_all_artikel()
    return render_template(
        "cms/artikel.html",
        artikel=artikel_list,
        kategori_options=ARTICLE_CATEGORIES,
        default_penulis=_current_author_name(),
    )


@cms_bp.route("/artikel/<int:artikel_id>/update", methods=["POST"])
@role_required("admin")
def update_artikel(artikel_id: int):
    """Update artikel yang sudah ada."""

    existing = _fetch_artikel_by_id(artikel_id)
    if not existing:
        return jsonify({"success": False, "error": "Artikel tidak ditemukan."}), 404
    _ensure_artikel_schema()

    try:
        payload = _parse_artikel_payload(require_thumbnail=False)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    actor = current_user() or {}
    actor_id = actor.get("id")
    saved_paths: list[str] = []
    cleanup_paths: list[str] = []

    try:
        thumbnail_path = existing.get("thumbnail_path")
        if payload["thumbnail"] is not None:
            _, thumbnail_path = _save_uploaded_asset(
                payload["thumbnail"],
                upload_dir=UPLOAD_ARTIKEL_THUMBNAILS,
                prefix=f"artikel_thumb_{artikel_id}",
                max_size=MAX_IMAGE_SIZE,
                validator=allowed_file,
                label="Thumbnail",
            )
            saved_paths.append(thumbnail_path)
            if existing.get("thumbnail_path"):
                cleanup_paths.append(existing["thumbnail_path"])

        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE cms_artikel
                SET judul = %s,
                    kategori = %s,
                    tanggal_publikasi = %s,
                    deskripsi = %s,
                    thumbnail_path = %s,
                    penulis = %s,
                    status = %s,
                    status_publikasi = %s,
                    updated_by = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    payload["judul"],
                    payload["kategori"],
                    payload["tanggal_publikasi"],
                    payload["deskripsi"],
                    thumbnail_path,
                    payload["penulis"],
                    payload["status"],
                    payload["status_publikasi"],
                    actor_id,
                    artikel_id,
                ),
            )

            if payload["hapus_file_ids"]:
                cur.execute(
                    """
                    SELECT id, file_path
                    FROM cms_artikel_files
                    WHERE artikel_id = %s AND id = ANY(%s)
                    """,
                    (artikel_id, payload["hapus_file_ids"]),
                )
                removable_files = [dict(row) for row in cur.fetchall()]
                if removable_files:
                    cleanup_paths.extend(
                        row["file_path"]
                        for row in removable_files
                        if row.get("file_path")
                    )
                    cur.execute(
                        """
                        DELETE FROM cms_artikel_files
                        WHERE artikel_id = %s AND id = ANY(%s)
                        """,
                        (artikel_id, [row["id"] for row in removable_files]),
                    )

            for attachment in payload["lampiran"]:
                original_name, stored_path = _save_uploaded_asset(
                    attachment,
                    upload_dir=UPLOAD_ARTIKEL_ATTACHMENTS,
                    prefix=f"artikel_file_{artikel_id}",
                    max_size=MAX_ATTACHMENT_SIZE,
                    validator=_allowed_attachment_file,
                    label="Lampiran",
                )
                saved_paths.append(stored_path)
                cur.execute(
                    """
                    INSERT INTO cms_artikel_files (artikel_id, file_name, file_path, created_at)
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (artikel_id, original_name, stored_path),
                )

        for stored_path in cleanup_paths:
            _delete_stored_file(stored_path)

        return jsonify(
            {
                "success": True,
                "message": "Artikel berhasil diperbarui.",
                "artikel_id": artikel_id,
            }
        )

    except ValueError as exc:
        for stored_path in saved_paths:
            _delete_stored_file(stored_path)
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        for stored_path in saved_paths:
            _delete_stored_file(stored_path)
        return jsonify({"success": False, "error": str(exc)}), 500


@cms_bp.route("/artikel/<int:artikel_id>/delete", methods=["POST"])
@role_required("admin")
def delete_artikel(artikel_id: int):
    """Hapus artikel beserta seluruh lampirannya."""

    existing = _fetch_artikel_by_id(artikel_id)
    if not existing:
        return jsonify({"success": False, "error": "Artikel tidak ditemukan."}), 404
    _ensure_artikel_schema()

    cleanup_paths = []
    if existing.get("thumbnail_path"):
        cleanup_paths.append(existing["thumbnail_path"])
    cleanup_paths.extend(
        file["path"] for file in existing.get("files", []) if file.get("path")
    )

    try:
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM cms_artikel WHERE id = %s", (artikel_id,))

        for stored_path in cleanup_paths:
            _delete_stored_file(stored_path)

        return jsonify(
            {
                "success": True,
                "message": "Artikel berhasil dihapus.",
                "artikel_id": artikel_id,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


def _serialize_pengumuman(row: dict) -> dict:
    date_value = row.get("tanggal_publikasi")
    return {
        "id": row.get("id"),
        "judul": row.get("judul") or "",
        "kategori": row.get("kategori") or "Pengumuman",
        "tanggal": date_value.isoformat() if date_value else "",
        "deskripsi": row.get("deskripsi") or "",
        "thumbnail_path": row.get("thumbnail_path"),
        "thumbnail_url": _build_upload_url(row.get("thumbnail_path")),
        "penulis": row.get("penulis") or "-",
        "status": row.get("status") or "Tidak Aktif",
        "status_publikasi": row.get("status_publikasi") or "Draft",
        "files": _serialize_media_entries(row.get("files")),
    }


def _fetch_pengumuman(*, public_only: bool = False) -> list[dict]:
    _ensure_publication_schema()
    where_clause = ""
    if public_only:
        where_clause = "WHERE status = 'Aktif' AND status_publikasi = 'Published' AND tanggal_publikasi <= CURRENT_DATE"
    with get_cursor() as cur:
        cur.execute(
            f"SELECT * FROM cms_pengumuman {where_clause} "
            "ORDER BY tanggal_publikasi DESC, created_at DESC, id DESC"
        )
        return [_serialize_pengumuman(dict(row)) for row in cur.fetchall()]


def _get_pengumuman(pengumuman_id: int) -> dict | None:
    _ensure_publication_schema()
    with get_cursor() as cur:
        cur.execute("SELECT * FROM cms_pengumuman WHERE id = %s", (pengumuman_id,))
        row = cur.fetchone()
    return _serialize_pengumuman(dict(row)) if row else None


def _parse_pengumuman_form() -> dict:
    judul = (request.form.get("judul") or "").strip()
    deskripsi = request.form.get("deskripsi") or ""
    if not judul or not deskripsi.strip():
        raise ValueError("Judul dan isi pengumuman wajib diisi.")
    status, publication = _publication_status()
    return {
        "judul": judul,
        "kategori": (request.form.get("kategori") or "Pengumuman").strip(),
        "tanggal": _parse_date_field("tanggal", "Tanggal publikasi"),
        "deskripsi": deskripsi,
        "penulis": (request.form.get("penulis") or _current_author_name()).strip(),
        "status": status,
        "publication": publication,
    }


@cms_bp.route("/pengumuman", methods=["GET", "POST"])
@role_required("admin")
def pengumuman():
    """Kelola pengumuman persisten yang dapat dipublikasikan ke LP."""
    _ensure_publication_schema()
    if request.method == "POST":
        saved_paths: list[str] = []
        try:
            payload = _parse_pengumuman_form()
            thumbnail_path = None
            thumbnail = request.files.get("thumbnail")
            if thumbnail and _safe_client_filename(thumbnail.filename):
                _, thumbnail_path = _save_uploaded_asset(
                    thumbnail,
                    upload_dir=UPLOAD_PENGUMUMAN_THUMBNAILS,
                    prefix="pengumuman_thumb",
                    max_size=MAX_IMAGE_SIZE,
                    validator=allowed_file,
                    label="Thumbnail",
                )
                saved_paths.append(thumbnail_path)
            files = _save_file_entries(
                request.files.getlist("lampiran"),
                upload_dir=UPLOAD_PENGUMUMAN_ATTACHMENTS,
                prefix="pengumuman_file",
                validator=_allowed_attachment_file,
                max_size=MAX_ATTACHMENT_SIZE,
                label="Lampiran",
            )
            saved_paths.extend(item["path"] for item in files)
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """INSERT INTO cms_pengumuman
                    (judul, kategori, tanggal_publikasi, deskripsi, thumbnail_path,
                     penulis, status, status_publikasi, files)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                    (
                        payload["judul"], payload["kategori"], payload["tanggal"],
                        payload["deskripsi"], thumbnail_path, payload["penulis"],
                        payload["status"], payload["publication"], json.dumps(files),
                    ),
                )
            return jsonify({"success": True, "message": "Pengumuman berhasil ditambahkan."})
        except Exception as exc:
            for path in saved_paths:
                _delete_stored_file(path)
            status_code = 400 if isinstance(exc, ValueError) else 500
            return jsonify({"success": False, "error": str(exc)}), status_code

    return render_template(
        "cms/pengumuman.html",
        pengumuman=_fetch_pengumuman(),
        default_penulis=_current_author_name(),
    )


@cms_bp.route("/pengumuman/<int:pengumuman_id>/update", methods=["POST"])
@role_required("admin")
def update_pengumuman(pengumuman_id: int):
    existing = _get_pengumuman(pengumuman_id)
    if not existing:
        return jsonify({"success": False, "error": "Pengumuman tidak ditemukan."}), 404
    saved_paths: list[str] = []
    cleanup_paths: list[str] = []
    try:
        payload = _parse_pengumuman_form()
        thumbnail_path = existing.get("thumbnail_path")
        thumbnail = request.files.get("thumbnail")
        if thumbnail and _safe_client_filename(thumbnail.filename):
            _, thumbnail_path = _save_uploaded_asset(
                thumbnail,
                upload_dir=UPLOAD_PENGUMUMAN_THUMBNAILS,
                prefix=f"pengumuman_thumb_{pengumuman_id}",
                max_size=MAX_IMAGE_SIZE,
                validator=allowed_file,
                label="Thumbnail",
            )
            saved_paths.append(thumbnail_path)
            if existing.get("thumbnail_path"):
                cleanup_paths.append(existing["thumbnail_path"])
        new_files = _save_file_entries(
            request.files.getlist("lampiran"),
            upload_dir=UPLOAD_PENGUMUMAN_ATTACHMENTS,
            prefix=f"pengumuman_file_{pengumuman_id}",
            validator=_allowed_attachment_file,
            max_size=MAX_ATTACHMENT_SIZE,
            label="Lampiran",
        )
        saved_paths.extend(item["path"] for item in new_files)
        deleted_ids = set(request.form.getlist("hapus_file_ids"))
        kept_files = []
        for entry in _stored_media_entries(existing.get("files")):
            if str(entry.get("id")) in deleted_ids:
                cleanup_paths.append(entry["path"])
            else:
                kept_files.append(entry)
        files = kept_files + new_files
        with get_cursor(commit=True) as cur:
            cur.execute(
                """UPDATE cms_pengumuman SET judul=%s, kategori=%s,
                tanggal_publikasi=%s, deskripsi=%s, thumbnail_path=%s, penulis=%s,
                status=%s, status_publikasi=%s, files=%s::jsonb, updated_at=NOW()
                WHERE id=%s""",
                (
                    payload["judul"], payload["kategori"], payload["tanggal"],
                    payload["deskripsi"], thumbnail_path, payload["penulis"],
                    payload["status"], payload["publication"], json.dumps(files),
                    pengumuman_id,
                ),
            )
        for path in cleanup_paths:
            _delete_stored_file(path)
        return jsonify({"success": True, "message": "Pengumuman berhasil diperbarui."})
    except Exception as exc:
        for path in saved_paths:
            _delete_stored_file(path)
        status_code = 400 if isinstance(exc, ValueError) else 500
        return jsonify({"success": False, "error": str(exc)}), status_code


@cms_bp.route("/pengumuman/<int:pengumuman_id>/delete", methods=["POST"])
@role_required("admin")
def delete_pengumuman(pengumuman_id: int):
    existing = _get_pengumuman(pengumuman_id)
    if not existing:
        return jsonify({"success": False, "error": "Pengumuman tidak ditemukan."}), 404
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM cms_pengumuman WHERE id = %s", (pengumuman_id,))
    paths = [existing.get("thumbnail_path")]
    paths.extend(item.get("path") for item in existing.get("files", []))
    for path in paths:
        _delete_stored_file(path)
    return jsonify({"success": True, "message": "Pengumuman berhasil dihapus."})


def _serialize_galeri(row: dict) -> dict:
    date_value = row.get("tanggal_kegiatan")
    return {
        "id": row.get("id"),
        "nama_kegiatan": row.get("nama_kegiatan") or "",
        "tanggal": date_value.isoformat() if date_value else "",
        "thumbnail_path": row.get("thumbnail_path"),
        "thumbnail_url": _build_upload_url(row.get("thumbnail_path")),
        "gambar_kegiatan": _serialize_media_entries(row.get("gambar_kegiatan")),
        "penulis": row.get("penulis") or "-",
        "status": row.get("status") or "Tidak Aktif",
        "status_publikasi": row.get("status_publikasi") or "Draft",
    }


def _fetch_galeri(*, public_only: bool = False) -> list[dict]:
    _ensure_publication_schema()
    where_clause = ""
    if public_only:
        where_clause = "WHERE status = 'Aktif' AND status_publikasi = 'Published' AND tanggal_kegiatan <= CURRENT_DATE"
    with get_cursor() as cur:
        cur.execute(
            f"SELECT * FROM cms_galeri {where_clause} "
            "ORDER BY tanggal_kegiatan DESC, created_at DESC, id DESC"
        )
        return [_serialize_galeri(dict(row)) for row in cur.fetchall()]


def _get_galeri(galeri_id: int) -> dict | None:
    _ensure_publication_schema()
    with get_cursor() as cur:
        cur.execute("SELECT * FROM cms_galeri WHERE id = %s", (galeri_id,))
        row = cur.fetchone()
    return _serialize_galeri(dict(row)) if row else None


def _parse_galeri_form() -> dict:
    name = (request.form.get("nama_kegiatan") or "").strip()
    if not name:
        raise ValueError("Nama kegiatan wajib diisi.")
    status, publication = _publication_status()
    return {
        "name": name,
        "tanggal": _parse_date_field("tanggal", "Tanggal kegiatan"),
        "penulis": (request.form.get("penulis") or _current_author_name()).strip(),
        "status": status,
        "publication": publication,
    }


@cms_bp.route("/galeri-kegiatan", methods=["GET", "POST"])
@role_required("admin")
def galeri_kegiatan():
    """Kelola galeri persisten yang dapat dipublikasikan ke LP."""
    _ensure_publication_schema()
    if request.method == "POST":
        saved_paths: list[str] = []
        try:
            payload = _parse_galeri_form()
            thumbnail_path = None
            thumbnail = request.files.get("thumbnail")
            if thumbnail and _safe_client_filename(thumbnail.filename):
                _, thumbnail_path = _save_uploaded_asset(
                    thumbnail,
                    upload_dir=UPLOAD_GALERI_THUMBNAILS,
                    prefix="galeri_thumb",
                    max_size=MAX_IMAGE_SIZE,
                    validator=allowed_file,
                    label="Thumbnail",
                )
                saved_paths.append(thumbnail_path)
            images = _save_file_entries(
                request.files.getlist("gambar_kegiatan"),
                upload_dir=UPLOAD_GALERI_IMAGES,
                prefix="galeri_image",
                validator=allowed_file,
                max_size=MAX_IMAGE_SIZE,
                label="Gambar kegiatan",
            )
            saved_paths.extend(item["path"] for item in images)
            if not images:
                raise ValueError("Minimal satu gambar kegiatan wajib diunggah.")
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """INSERT INTO cms_galeri
                    (nama_kegiatan, tanggal_kegiatan, thumbnail_path, gambar_kegiatan,
                     penulis, status, status_publikasi)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)""",
                    (
                        payload["name"], payload["tanggal"], thumbnail_path,
                        json.dumps(images), payload["penulis"], payload["status"],
                        payload["publication"],
                    ),
                )
            return jsonify({"success": True, "message": "Galeri berhasil ditambahkan."})
        except Exception as exc:
            for path in saved_paths:
                _delete_stored_file(path)
            status_code = 400 if isinstance(exc, ValueError) else 500
            return jsonify({"success": False, "error": str(exc)}), status_code

    return render_template(
        "cms/galeri_kegiatan.html",
        galeri=_fetch_galeri(),
        default_penulis=_current_author_name(),
    )


@cms_bp.route("/galeri-kegiatan/<int:galeri_id>/update", methods=["POST"])
@role_required("admin")
def update_galeri(galeri_id: int):
    existing = _get_galeri(galeri_id)
    if not existing:
        return jsonify({"success": False, "error": "Galeri tidak ditemukan."}), 404
    saved_paths: list[str] = []
    cleanup_paths: list[str] = []
    try:
        payload = _parse_galeri_form()
        thumbnail_path = existing.get("thumbnail_path")
        thumbnail = request.files.get("thumbnail")
        if thumbnail and _safe_client_filename(thumbnail.filename):
            _, thumbnail_path = _save_uploaded_asset(
                thumbnail,
                upload_dir=UPLOAD_GALERI_THUMBNAILS,
                prefix=f"galeri_thumb_{galeri_id}",
                max_size=MAX_IMAGE_SIZE,
                validator=allowed_file,
                label="Thumbnail",
            )
            saved_paths.append(thumbnail_path)
            if existing.get("thumbnail_path"):
                cleanup_paths.append(existing["thumbnail_path"])
        new_images = _save_file_entries(
            request.files.getlist("gambar_kegiatan"),
            upload_dir=UPLOAD_GALERI_IMAGES,
            prefix=f"galeri_image_{galeri_id}",
            validator=allowed_file,
            max_size=MAX_IMAGE_SIZE,
            label="Gambar kegiatan",
        )
        saved_paths.extend(item["path"] for item in new_images)
        deleted_ids = set(request.form.getlist("hapus_gambar_ids"))
        kept_images = []
        for entry in _stored_media_entries(existing.get("gambar_kegiatan")):
            if str(entry.get("id")) in deleted_ids:
                cleanup_paths.append(entry["path"])
            else:
                kept_images.append(entry)
        images = kept_images + new_images
        if not images:
            raise ValueError("Galeri harus memiliki minimal satu foto kegiatan.")
        with get_cursor(commit=True) as cur:
            cur.execute(
                """UPDATE cms_galeri SET nama_kegiatan=%s, tanggal_kegiatan=%s,
                thumbnail_path=%s, gambar_kegiatan=%s::jsonb, penulis=%s, status=%s,
                status_publikasi=%s, updated_at=NOW() WHERE id=%s""",
                (
                    payload["name"], payload["tanggal"], thumbnail_path,
                    json.dumps(images), payload["penulis"], payload["status"],
                    payload["publication"], galeri_id,
                ),
            )
        for path in cleanup_paths:
            _delete_stored_file(path)
        return jsonify({"success": True, "message": "Galeri berhasil diperbarui."})
    except Exception as exc:
        for path in saved_paths:
            _delete_stored_file(path)
        status_code = 400 if isinstance(exc, ValueError) else 500
        return jsonify({"success": False, "error": str(exc)}), status_code


@cms_bp.route("/galeri-kegiatan/<int:galeri_id>/delete", methods=["POST"])
@role_required("admin")
def delete_galeri(galeri_id: int):
    existing = _get_galeri(galeri_id)
    if not existing:
        return jsonify({"success": False, "error": "Galeri tidak ditemukan."}), 404
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM cms_galeri WHERE id = %s", (galeri_id,))
    paths = [existing.get("thumbnail_path")]
    paths.extend(item.get("path") for item in existing.get("gambar_kegiatan", []))
    for path in paths:
        _delete_stored_file(path)
    return jsonify({"success": True, "message": "Galeri berhasil dihapus."})


def _serialize_public_information(info: dict | None) -> dict:
    info = info or {}
    updated_at = info.get("updated_at")
    return {
        "jaminan_pelayanan": info.get("cms_jaminan_pelayanan") or "",
        "keamanan_keselamatan": info.get("cms_keamanan_keselamatan") or "",
        "kompensasi_pelayanan": info.get("cms_kompensasi_pelayanan") or "",
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def _serialize_public_service(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "nama": row.get("cms_nama_layanan") or "",
        "deskripsi": row.get("cms_deskripsi") or "",
        "icon": row.get("cms_icon") or "bi-star",
        "files": _serialize_media_entries(row.get("cms_files")),
    }


def _public_articles() -> list[dict]:
    today = datetime.now().date().isoformat()
    result = []
    for article in _fetch_all_artikel():
        if article.get("status") != "Aktif":
            continue
        if article.get("status_publikasi") != "Published":
            continue
        if article.get("tanggal") and article["tanggal"] > today:
            continue
        result.append(
            {
                "id": article.get("id"),
                "judul": article.get("judul") or "",
                "kategori": article.get("kategori") or "Informasi",
                "tanggal": article.get("tanggal") or "",
                "deskripsi": article.get("deskripsi") or "",
                "thumbnail_url": article.get("thumbnail_url"),
                "penulis": article.get("penulis") or "-",
                "files": article.get("files") or [],
            }
        )
    return result


@cms_bp.route("/api/public/content", methods=["GET"])
def public_content():
    """Semua konten CMS yang layak ditampilkan pada landing page."""
    services = [
        _serialize_public_service(row)
        for row in _list_layanan_publik()
        if row.get("cms_status") == "Aktif"
    ]
    return jsonify(
        {
            "success": True,
            "data": {
                "profil": _serialize_public_profil_instansi(_get_profil_instansi()),
                "informasi_publik": _serialize_public_information(
                    _get_informasi_publik()
                ),
                "layanan": services,
                "artikel": _public_articles(),
                "pengumuman": _fetch_pengumuman(public_only=True),
                "galeri": _fetch_galeri(public_only=True),
            },
        }
    )
