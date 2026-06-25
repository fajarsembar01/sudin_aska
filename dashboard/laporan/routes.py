"""Routes for the Laporan (Form Reports) system."""
from __future__ import annotations

import io
import json
import uuid
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    from PIL import Image as _PilImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from psycopg2.errors import UniqueViolation

from ..auth import current_user, role_required
from ..portal.routes import _fetch_user_school
from ..portal.routes import inject_permissions as portal_inject_permissions
from ..schema import ensure_laporan_schema
from ..db_access import get_cursor
from .queries import (
    list_all_forms,
    get_form,
    get_form_fields,
    get_form_target_school_ids,
    list_forms_for_school,
    create_form,
    update_form,
    delete_form,
    set_form_targets,
    replace_form_fields,
    school_has_submitted,
    school_has_submitted_for_period,
    create_submission,
    update_submission_status,
    save_answer,
    replace_answer_files,
    save_file,
    get_submission_with_answers,
    delete_submitted_submission,
    delete_empty_submitted_submissions,
    list_school_submissions,
    get_last_submission_answers,
    list_form_submissions,
    export_form_xlsx,
    export_no_submissions_xlsx,
    list_all_schools_simple,
    fetch_laporan_kpi_schools,
    can_school_access_form,
    set_form_paused,
)

_LAPORAN_SCHEMA_READY = False

laporan_bp = Blueprint(
    "laporan",
    __name__,
    url_prefix="/laporan",
    template_folder="templates",
)


@laporan_bp.context_processor
def inject_laporan_context():
    """Inject permissions + user_school so base_laporan.html (which extends base_portal.html) works correctly."""
    context = portal_inject_permissions() or {}
    context["laporan_date_input_value"] = _format_date_input_value
    context["laporan_very_late_hours_value"] = _very_late_after_hours_value
    context["laporan_no_submission_hours_value"] = _no_submission_hours_value
    context["laporan_no_submission_minutes_value"] = _no_submission_minutes_value
    context["laporan_selected_no_submission_jenjangs"] = _selected_no_submission_jenjangs
    context["laporan_selected_no_submission_statuses"] = _selected_no_submission_statuses
    user = current_user() or {}
    if user.get("role") == "sekolah":
        try:
            context["user_school"] = _fetch_user_school(user.get("id"))
        except Exception:
            context["user_school"] = None
    return context


@laporan_bp.before_request
def ensure_laporan_schema_before_request() -> None:
    """Keep Laporan routes usable when a deployment has not run the latest migration yet."""
    global _LAPORAN_SCHEMA_READY
    if _LAPORAN_SCHEMA_READY:
        return None
    try:
        ensure_laporan_schema()
        _LAPORAN_SCHEMA_READY = True
    except Exception:
        current_app.logger.exception("Failed to ensure laporan schema")
    return None

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
UPLOAD_FOLDER = Path(__file__).parent.parent.parent / "uploads" / "laporan"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "pdf", "doc", "docx", "xls", "xlsx"}
ALLOWED_DOC_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
IMAGE_COMPRESS_QUALITY = 75   # JPEG quality for compressed images (0-95)
IMAGE_MAX_DIMENSION = 1920    # Max width or height in pixels
CHOICE_FIELD_TYPES = {"radio", "checkbox", "dropdown"}
FORMULA_OPERATORS = {"add", "subtract", "multiply", "divide"}
FORMULA_SOURCE_TYPES = {"number", "rating", "formula"}
DISPLAY_ONLY_FIELD_TYPES = {"header", "info"}
FILE_UPLOAD_FIELD_TYPES = {"file", "upload_dokumen", "upload_gambar"}
REPEAT_POLICIES = {"once", "multiple", "daily", "weekly", "monthly"}
PERIODIC_REPEAT_POLICIES = {"daily", "weekly", "monthly"}
DEFAULT_VERY_LATE_AFTER_MINUTES = 3 * 60
MONTH_NAMES_ID = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}
DAY_NAMES_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
ALLOWED_FIELD_TYPES = {
    "text",
    "textarea",
    "radio",
    "checkbox",
    "dropdown",
    "file",
    "upload_dokumen",
    "upload_gambar",
    "date",
    "time",
    "number",
    "rating",
    "email",
    "header",
    "info",
    "link",
    "formula",
}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_EXTENSIONS


def _allowed_doc(filename: str) -> bool:
    """Hanya izinkan file dokumen (PDF, DOC, DOCX, XLS, XLSX)."""
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_DOC_EXTENSIONS


def _allowed_image(filename: str) -> bool:
    """Hanya izinkan file gambar (JPG, PNG, WEBP, GIF)."""
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _compress_and_save_image(file_storage, save_path: Path) -> int:
    """Kompres gambar dan simpan ke disk. Mengembalikan ukuran file hasil kompresi.
    
    Menggunakan Pillow untuk:
    - Mengubah ukuran gambar jika melebihi IMAGE_MAX_DIMENSION
    - Mengompresi ke JPEG dengan kualitas IMAGE_COMPRESS_QUALITY
    - Gambar GIF/PNG dengan transparansi dikonversi ke WebP agar hemat storage
    """
    if not _PIL_AVAILABLE:
        # Fallback: simpan langsung tanpa kompresi
        file_storage.save(str(save_path))
        return save_path.stat().st_size

    try:
        img_bytes = file_storage.read()
        file_storage.seek(0)  # reset stream
        img = _PilImage.open(io.BytesIO(img_bytes))

        # Konversi mode yang tidak kompatibel
        original_format = img.format or "JPEG"
        has_alpha = img.mode in ("RGBA", "LA", "PA") or (
            img.mode == "P" and "transparency" in img.info
        )

        # Resize jika terlalu besar
        w, h = img.size
        if w > IMAGE_MAX_DIMENSION or h > IMAGE_MAX_DIMENSION:
            ratio = min(IMAGE_MAX_DIMENSION / w, IMAGE_MAX_DIMENSION / h)
            new_w, new_h = int(w * ratio), int(h * ratio)
            img = img.resize((new_w, new_h), _PilImage.LANCZOS)

        # Tentukan format output
        ext = save_path.suffix.lower().lstrip(".")
        if ext in {"jpg", "jpeg"}:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(str(save_path), format="JPEG", quality=IMAGE_COMPRESS_QUALITY, optimize=True)
        elif ext == "webp":
            img.save(str(save_path), format="WEBP", quality=IMAGE_COMPRESS_QUALITY, method=6)
        elif ext == "png":
            if has_alpha and img.mode != "RGBA":
                img = img.convert("RGBA")
            elif not has_alpha and img.mode != "RGB":
                img = img.convert("RGB")
            img.save(str(save_path), format="PNG", optimize=True)
        elif ext == "gif":
            # GIF: simpan as-is (animasi dll) – kompresi minimal
            img.save(str(save_path), format="GIF")
        else:
            # Fallback ke JPEG
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(str(save_path), format="JPEG", quality=IMAGE_COMPRESS_QUALITY, optimize=True)

        return save_path.stat().st_size
    except Exception:
        current_app.logger.exception("Gagal mengompresi gambar, menyimpan tanpa kompresi")
        file_storage.seek(0)
        file_storage.save(str(save_path))
        return save_path.stat().st_size


def _cleanup_submission_files(file_paths: list[str]) -> None:
    upload_root = UPLOAD_FOLDER.resolve()
    for rel_path in file_paths or []:
        try:
            target_path = (UPLOAD_FOLDER / rel_path).resolve()
            target_path.relative_to(upload_root)
        except (OSError, ValueError):
            current_app.logger.warning("Skipping unsafe laporan file cleanup path: %s", rel_path)
            continue
        try:
            if target_path.is_file():
                target_path.unlink()
        except OSError:
            current_app.logger.exception("Failed to delete laporan upload file: %s", target_path)


def _parse_deadline(raw: str) -> Optional[datetime]:
    if not raw or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip())
    except ValueError:
        return None


def _parse_repeat_until_date(raw: str) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        selected_date = date.fromisoformat(text)
    except ValueError:
        return _parse_deadline(text)
    return datetime.combine(selected_date, time(23, 59, 59), tzinfo=JAKARTA_TZ)


def _parse_time_value(raw: Optional[str]) -> Optional[time]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return time.fromisoformat(text)
    except ValueError:
        return None


def _parse_int_value(raw: Optional[str], minimum: int, maximum: int) -> Optional[int]:
    try:
        value = int((raw or "").strip())
    except ValueError:
        return None
    if value < minimum or value > maximum:
        return None
    return value


def _as_jakarta_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=JAKARTA_TZ)
    return value.astimezone(JAKARTA_TZ)


def _format_date_id(value: date) -> str:
    return f"{value.day:02d} {MONTH_NAMES_ID[value.month]} {value.year}"


def _format_datetime_id(value: Optional[datetime]) -> Optional[str]:
    jakarta_value = _as_jakarta_datetime(value)
    if not jakarta_value:
        return None
    return f"{_format_date_id(jakarta_value.date())} {jakarta_value:%H:%M}"


def _format_late_duration(minutes: int, *, cap_minutes: Optional[int] = None) -> str:
    minutes = max(int(minutes or 0), 0)
    if cap_minutes and minutes > cap_minutes:
        return f"lebih dari {_format_late_duration(cap_minutes)}"
    if minutes == 0:
        return "kurang dari 1 menit"
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} jam")
    if mins:
        parts.append(f"{mins} menit")
    return " ".join(parts) if parts else "kurang dari 1 menit"


def _late_minutes_from_submission(submission: dict) -> int:
    raw = submission.get("late_minutes")
    if raw is None:
        raw = (submission.get("late_days") or 0) * 24 * 60
    try:
        minutes = max(int(raw or 0), 0)
    except (TypeError, ValueError):
        minutes = 0

    if submission.get("is_late") and minutes == 0:
        submitted_at = submission.get("submitted_at")
        if submitted_at:
            submitted_at_jkt = _as_jakarta_datetime(submitted_at)
            policy = submission.get("form_repeat_policy") or "once"
            if policy in PERIODIC_REPEAT_POLICIES:
                form_mock = {
                    "repeat_deadline_time": submission.get("form_repeat_deadline_time"),
                    "repeat_deadline_day": submission.get("form_repeat_deadline_day")
                }
                deadline = _period_deadline_at(policy, submitted_at_jkt.date(), form_mock)
            else:
                deadline = _as_jakarta_datetime(submission.get("form_deadline_at"))

            if deadline and submitted_at_jkt > deadline:
                late_delta = submitted_at_jkt - deadline
                minutes = max(int((late_delta.total_seconds() + 59) // 60), 1)

    return minutes


def _annotate_late_submission(submission: dict) -> None:
    late_minutes = _late_minutes_from_submission(submission)
    threshold = _very_late_after_minutes(submission)
    submission["late_minutes"] = late_minutes
    submission["late_duration_label"] = _format_late_duration(late_minutes, cap_minutes=threshold)
    submission["is_very_late"] = bool(
        submission.get("is_late") and late_minutes > threshold
    )


def _very_late_after_minutes(form_or_submission: Optional[dict]) -> int:
    if form_or_submission:
        try:
            value = int(form_or_submission.get("very_late_after_minutes") or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return DEFAULT_VERY_LATE_AFTER_MINUTES


def _very_late_after_hours_value(form: Optional[dict]) -> str:
    minutes = _very_late_after_minutes(form)
    if minutes % 60 == 0:
        return str(minutes // 60)
    return f"{minutes / 60:.2f}".rstrip("0").rstrip(".")


def _parse_very_late_after_minutes() -> int:
    raw = (request.form.get("very_late_after_hours") or "").strip().replace(",", ".")
    try:
        hours = float(raw)
    except ValueError:
        return DEFAULT_VERY_LATE_AFTER_MINUTES
    if hours <= 0:
        return DEFAULT_VERY_LATE_AFTER_MINUTES
    minutes = int(round(hours * 60))
    return min(max(minutes, 1), 30 * 24 * 60)


def _no_submission_after_minutes(form: Optional[dict]) -> Optional[int]:
    if form:
        try:
            value = int(form.get("no_submission_after_minutes") or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def _no_submission_hours_value(form: Optional[dict]) -> str:
    minutes = _no_submission_after_minutes(form)
    return "" if minutes is None else str(minutes // 60)


def _no_submission_minutes_value(form: Optional[dict]) -> str:
    minutes = _no_submission_after_minutes(form)
    return "" if minutes is None else str(minutes % 60)


def _selected_no_submission_jenjangs(form: Optional[dict]) -> list[str]:
    raw = (form or {}).get("no_submission_jenjangs") or ""
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _selected_no_submission_statuses(form: Optional[dict]) -> list[str]:
    raw = (form or {}).get("no_submission_statuses") or ""
    return [item.strip().upper() for item in str(raw).split(",") if item.strip()]


def _parse_no_submission_after_minutes() -> Optional[int]:
    try:
        hours = int((request.form.get("no_submission_after_hours") or "0").strip() or 0)
    except ValueError:
        hours = 0
    try:
        minutes = int((request.form.get("no_submission_after_minutes") or "0").strip() or 0)
    except ValueError:
        minutes = 0
    total = max(hours, 0) * 60 + min(max(minutes, 0), 59)
    return min(total, 30 * 24 * 60) if total > 0 else None


def _parse_no_submission_jenjangs() -> Optional[str]:
    values = []
    seen = set()
    for raw in request.form.getlist("no_submission_jenjangs[]"):
        value = raw.strip()
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return ",".join(values) if values else None


def _parse_no_submission_statuses() -> Optional[str]:
    raw = (request.form.get("no_submission_statuses") or "").strip().upper()
    if raw in ("NEGERI", "SWASTA"):
        return raw
    # Default: NEGERI jika tidak ada pilihan (form baru atau tidak dipilih)
    if not raw:
        return "NEGERI"
    return None  # nilai kosong eksplisit = semua


def _available_jenjangs(schools: list[dict]) -> list[str]:
    values = sorted({(school.get("jenjang") or "").strip() for school in schools if (school.get("jenjang") or "").strip()})
    return values or ["SD", "SMP"]


def _school_subject_to_no_submission(form: dict, school: Optional[dict]) -> bool:
    selected_jenjangs = set(_selected_no_submission_jenjangs(form))
    if selected_jenjangs:
        if not (school and (school.get("jenjang") or "").strip() in selected_jenjangs):
            return False
    selected_statuses = set(_selected_no_submission_statuses(form))
    if selected_statuses:
        school_status = (school.get("status") or "").strip().upper() if school else ""
        if school_status not in selected_statuses:
            return False
    return True



def _form_no_submission_cutoff(form: dict, now: datetime) -> Optional[datetime]:
    after_minutes = _no_submission_after_minutes(form)
    if after_minutes is None:
        return None
    deadline = _form_deadline_for_request(form, now)
    if not deadline:
        return None
    return deadline + timedelta(minutes=after_minutes)


def _form_no_submission_cutoff_for_submission(form: dict, submission: dict, now: datetime) -> Optional[datetime]:
    after_minutes = _no_submission_after_minutes(form)
    if after_minutes is None:
        return None
    deadline = _form_deadline_for_submission(form, submission, now)
    if not deadline:
        return None
    return deadline + timedelta(minutes=after_minutes)


def sync_no_submissions(form_id: int, now: Optional[datetime] = None) -> None:
    if now is None:
        now = datetime.now(JAKARTA_TZ)

    form = get_form(form_id)
    if not form or not form.get("is_active") or form.get("is_paused") or form.get("status") != "published":
        return

    after_minutes = _no_submission_after_minutes(form)
    if after_minutes is None or after_minutes <= 0:
        return

    policy = _form_repeat_policy(form)
    created_at = form.get("created_at")
    if not created_at:
        return

    closed_periods = {}  # key -> label
    if policy == "once":
        deadline_at = _as_jakarta_datetime(form.get("deadline_at"))
        if deadline_at:
            cutoff = deadline_at + timedelta(minutes=after_minutes)
            if now > cutoff:
                closed_periods[None] = None
    else:
        # periodic
        repeat_until_at = _as_jakarta_datetime(form.get("repeat_until_at"))
        curr_date = created_at.astimezone(JAKARTA_TZ).date()
        end_date = now.date()
        
        limit_start_date = max(curr_date, (now - timedelta(days=90)).date())
        
        while limit_start_date <= end_date:
            ctx = _current_period_context(policy, datetime.combine(limit_start_date, time(12, 0), tzinfo=JAKARTA_TZ), form)
            if ctx.get("key") and ctx.get("deadline_at"):
                if repeat_until_at and ctx["deadline_at"] > repeat_until_at:
                    pass
                else:
                    cutoff = ctx["deadline_at"] + timedelta(minutes=after_minutes)
                    if now > cutoff:
                        closed_periods[ctx["key"]] = ctx["label"]
            limit_start_date += timedelta(days=1)

    if not closed_periods:
        return

    target_scope = form.get("target_scope") or "all"
    target_jenjang = form.get("target_jenjang")
    
    schools = []
    with get_cursor() as cur:
        if target_scope == "all":
            cur.execute("SELECT id, name, npsn, jenjang, status, metadata FROM portal_schools WHERE active=TRUE")
            schools = [dict(r) for r in cur.fetchall()]
        elif target_scope == "jenjang":
            cur.execute("SELECT id, name, npsn, jenjang, status, metadata FROM portal_schools WHERE active=TRUE AND jenjang = %s", (target_jenjang,))
            schools = [dict(r) for r in cur.fetchall()]
        elif target_scope == "specific":
            cur.execute(
                """
                SELECT sc.id, sc.name, sc.npsn, sc.jenjang, sc.status, sc.metadata 
                FROM portal_schools sc
                JOIN laporan_form_targets ft ON ft.school_id = sc.id
                WHERE sc.active=TRUE AND ft.form_id = %s
                """,
                (form_id,),
            )
            schools = [dict(r) for r in cur.fetchall()]

    eligible_school_ids = {s["id"] for s in schools if _school_subject_to_no_submission(form, s)}
    with get_cursor(commit=True) as cur:
        if eligible_school_ids:
            cur.execute(
                """
                DELETE FROM laporan_submissions 
                WHERE form_id = %s AND status = 'no_submission' AND school_id NOT IN %s
                """,
                (form_id, tuple(eligible_school_ids))
            )
        else:
            cur.execute(
                """
                DELETE FROM laporan_submissions 
                WHERE form_id = %s AND status = 'no_submission'
                """,
                (form_id,)
            )

    existing_subs = {}  # (school_id, period_key) -> (sub_id, status)
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, school_id, repeat_period_key, status FROM laporan_submissions WHERE form_id = %s",
            (form_id,),
        )
        for r in cur.fetchall():
            existing_subs[(r["school_id"], r["repeat_period_key"])] = (r["id"], r["status"])

    inserts = []
    updates = []
    for school in schools:
        if not _school_subject_to_no_submission(form, school):
            continue
        
        for period_key, period_label in closed_periods.items():
            lookup_key = (school["id"], period_key)
            if lookup_key in existing_subs:
                sub_id, status = existing_subs[lookup_key]
                if status == "draft":
                    updates.append(sub_id)
            else:
                inserts.append((form_id, school["id"], "no_submission", period_key, period_label))

    if inserts or updates:
        with get_cursor(commit=True) as cur:
            if updates:
                cur.execute(
                    "UPDATE laporan_submissions SET status = 'no_submission', updated_at = NOW() WHERE id = ANY(%s)",
                    (updates,)
                )
            if inserts:
                cur.executemany(
                    """
                    INSERT INTO laporan_submissions (
                        form_id, school_id, status, repeat_period_key, repeat_period_label, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    """,
                    inserts
                )


def _target_label(form: dict) -> str:
    if form.get("target_scope") == "all":
        return "Semua Sekolah"
    if form.get("target_scope") == "jenjang":
        return f"Jenjang {form.get('target_jenjang') or '-'}"
    return "Sekolah Tertentu"


def _share_repeat_label(form: dict) -> str:
    policy = _form_repeat_policy(form)
    label = form.get("repeat_policy_label") or _repeat_policy_label(policy)
    deadline_time = _format_time_value(form.get("repeat_deadline_time"))
    deadline_day = form.get("repeat_deadline_day")
    detail = ""
    if policy == "daily" and deadline_time:
        detail = f" dengan batas pengisian setiap hari pukul {deadline_time} WIB"
    elif policy == "weekly" and deadline_day is not None and deadline_time:
        day_index = max(0, min(int(deadline_day), 6))
        detail = f" dengan batas pengisian setiap minggu pada hari {DAY_NAMES_ID[day_index]} pukul {deadline_time} WIB"
    elif policy == "monthly" and deadline_day is not None and deadline_time:
        detail = f" dengan batas pengisian setiap bulan pada tanggal {int(deadline_day)} pukul {deadline_time} WIB"

    until_detail = ""
    if policy in PERIODIC_REPEAT_POLICIES and form.get("repeat_until_at"):
        until_label = _format_date_id_from_datetime(form.get("repeat_until_at"))
        if until_label:
            until_detail = f" hingga {until_label}"
    return f"{label}{detail}{until_detail}"


def _build_form_share_caption(form: dict, now: datetime) -> str:
    deadline = _form_deadline_for_request(form, now)
    no_submission_cutoff = _form_no_submission_cutoff(form, now)
    fill_url = url_for("laporan.sekolah_laporan_fill", form_id=form["id"], _external=True)
    lines = [
        "Yth. Bapak/Ibu Operator Sekolah,",
        "",
        "Mohon kesediaannya untuk mengisi form laporan berikut:",
        f"Judul: {form.get('title') or '-'}",
    ]
    if form.get("description"):
        lines.append(f"Keterangan: {form['description']}")
    lines.extend(
        [
            f"Target: {_target_label(form)}",
            f"Pengisian: {_share_repeat_label(form)}",
        ]
    )
    if form.get("current_period_label"):
        lines.append(f"Periode: {form['current_period_label']}")
    if deadline:
        lines.append(f"Deadline: {_format_datetime_id(deadline)} WIB")
    if no_submission_cutoff:
        lines.append(f"Batas tidak mengumpulkan: {_format_datetime_id(no_submission_cutoff)} WIB")
    lines.extend(
        [
            "",
            f"Link pengisian: {fill_url}",
            "",
            "Mohon Bapak/Ibu dapat mengisi sebelum batas waktu yang ditentukan. Terima kasih.",
        ]
    )
    return "\n".join(lines)


def _format_date_id_from_datetime(value: Optional[datetime]) -> Optional[str]:
    jakarta_value = _as_jakarta_datetime(value)
    if not jakarta_value:
        return None
    return _format_date_id(jakarta_value.date())


def _format_date_input_value(value: Optional[datetime]) -> str:
    jakarta_value = _as_jakarta_datetime(value)
    if not jakarta_value:
        return ""
    return jakarta_value.strftime("%Y-%m-%d")


def _format_time_value(value) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        parsed = _parse_time_value(value)
        return parsed.strftime("%H:%M") if parsed else None
    return value.strftime("%H:%M")


def _parse_repeat_policy(raw: Optional[str], allow_multiple_raw: Optional[str] = None) -> str:
    policy = (raw or "").strip()
    if policy in REPEAT_POLICIES:
        return policy
    return "multiple" if allow_multiple_raw == "1" else "once"


def _form_repeat_policy(form: dict) -> str:
    policy = (form.get("repeat_policy") or "").strip()
    if policy in REPEAT_POLICIES:
        return policy
    return "multiple" if form.get("allow_multiple") else "once"


def _repeat_policy_label(policy: str) -> str:
    labels = {
        "once": "Sekali isi",
        "multiple": "Bisa diisi ulang kapan saja",
        "daily": "Diisi ulang per hari",
        "weekly": "Diisi ulang per minggu",
        "monthly": "Diisi ulang per bulan",
    }
    return labels.get(policy, labels["once"])


def _period_deadline_at(policy: str, current: date, form: Optional[dict]) -> Optional[datetime]:
    if not form or policy not in PERIODIC_REPEAT_POLICIES:
        return None

    deadline_time = form.get("repeat_deadline_time")
    if isinstance(deadline_time, str):
        deadline_time = _parse_time_value(deadline_time)
    if not deadline_time:
        return None

    if policy == "daily":
        deadline_date = current
    elif policy == "weekly":
        deadline_day = form.get("repeat_deadline_day")
        if deadline_day is None:
            return None
        deadline_day = max(0, min(int(deadline_day), 6))
        start = current - timedelta(days=current.weekday())
        deadline_date = start + timedelta(days=deadline_day)
    elif policy == "monthly":
        deadline_day = form.get("repeat_deadline_day")
        if deadline_day is None:
            return None
        last_day = monthrange(current.year, current.month)[1]
        deadline_date = current.replace(day=max(1, min(int(deadline_day), last_day)))
    else:
        return None

    return datetime.combine(deadline_date, deadline_time, tzinfo=JAKARTA_TZ)


def _current_period_context(policy: str, now: datetime, form: Optional[dict] = None) -> dict:
    current = now.date()
    if policy == "daily":
        return {
            "key": f"daily:{current:%Y-%m-%d}",
            "label": f"Harian: {_format_date_id(current)}",
            "deadline_at": _period_deadline_at(policy, current, form),
        }
    if policy == "weekly":
        start = current - timedelta(days=current.weekday())
        end = start + timedelta(days=6)
        iso_year, iso_week, _ = current.isocalendar()
        return {
            "key": f"weekly:{iso_year}-W{iso_week:02d}",
            "label": f"Mingguan: {_format_date_id(start)} - {_format_date_id(end)}",
            "deadline_at": _period_deadline_at(policy, current, form),
        }
    if policy == "monthly":
        return {
            "key": f"monthly:{current:%Y-%m}",
            "label": f"Bulanan: {MONTH_NAMES_ID[current.month]} {current.year}",
            "deadline_at": _period_deadline_at(policy, current, form),
        }
    return {"key": None, "label": None, "deadline_at": None}


def _annotate_repeat_form(form: dict, now: datetime) -> dict:
    policy = _form_repeat_policy(form)
    repeat_until_at = _as_jakarta_datetime(form.get("repeat_until_at"))
    period = _current_period_context(policy, now, form)
    repeat_closed = policy in PERIODIC_REPEAT_POLICIES and repeat_until_at is not None and repeat_until_at < now
    period_deadline_at = _as_jakarta_datetime(period.get("deadline_at"))

    form["repeat_policy"] = policy
    form["allow_multiple"] = policy != "once"
    form["repeat_policy_label"] = _repeat_policy_label(policy)
    form["current_period_key"] = period.get("key")
    form["current_period_label"] = period.get("label")
    form["period_deadline_at"] = period_deadline_at
    form["period_deadline_str"] = _format_datetime_id(period_deadline_at)
    form["period_is_expired"] = period_deadline_at is not None and period_deadline_at < now
    form["repeat_deadline_time_str"] = _format_time_value(form.get("repeat_deadline_time"))
    form["repeat_until_str"] = _format_date_id_from_datetime(repeat_until_at)
    form["repeat_closed"] = repeat_closed
    return period


def _build_repeat_state(form: dict, school_id: int, now: datetime) -> dict:
    period = _annotate_repeat_form(form, now)
    policy = form["repeat_policy"]

    if policy == "multiple":
        already_submitted = school_has_submitted(form["id"], school_id)
        blocked_by_submission = False
    elif policy in PERIODIC_REPEAT_POLICIES:
        already_submitted = school_has_submitted_for_period(form["id"], school_id, period.get("key") or "")
        blocked_by_submission = already_submitted
    else:
        already_submitted = school_has_submitted(form["id"], school_id)
        blocked_by_submission = already_submitted

    return {
        "policy": policy,
        "period": period,
        "already_submitted": already_submitted,
        "blocked_by_submission": blocked_by_submission,
        "repeat_closed": form.get("repeat_closed", False),
    }


def _parse_repeat_settings_from_request() -> tuple[str, bool, Optional[datetime], Optional[time], Optional[int]]:
    repeat_policy = _parse_repeat_policy(
        request.form.get("repeat_policy"),
        request.form.get("allow_multiple"),
    )
    allow_multiple = repeat_policy != "once"
    repeat_until_at = None
    repeat_deadline_time = None
    repeat_deadline_day = None
    if repeat_policy in PERIODIC_REPEAT_POLICIES:
        repeat_until_at = _parse_repeat_until_date(
            request.form.get("repeat_until_date") or request.form.get("repeat_until_at", "")
        )
        repeat_deadline_time = _parse_time_value(request.form.get("repeat_deadline_time"))
        if repeat_policy == "weekly":
            repeat_deadline_day = _parse_int_value(request.form.get("repeat_deadline_weekday"), 0, 6)
        elif repeat_policy == "monthly":
            repeat_deadline_day = _parse_int_value(request.form.get("repeat_deadline_month_day"), 1, 31)
    return repeat_policy, allow_multiple, repeat_until_at, repeat_deadline_time, repeat_deadline_day


def _form_deadline_for_request(form: dict, now: datetime) -> Optional[datetime]:
    policy = _form_repeat_policy(form)
    if policy in PERIODIC_REPEAT_POLICIES:
        if "period_deadline_at" not in form:
            _annotate_repeat_form(form, now)
        return _as_jakarta_datetime(form.get("period_deadline_at"))
    return _as_jakarta_datetime(form.get("deadline_at"))


def _form_deadline_for_submission(form: dict, submission: dict, now: datetime) -> Optional[datetime]:
    policy = _form_repeat_policy(form)
    if policy not in PERIODIC_REPEAT_POLICIES:
        return _as_jakarta_datetime(form.get("deadline_at"))

    period_key = submission.get("repeat_period_key") or ""
    period_date = None
    try:
        if policy == "daily" and period_key.startswith("daily:"):
            period_date = date.fromisoformat(period_key.split(":", 1)[1])
        elif policy == "weekly" and period_key.startswith("weekly:"):
            iso_text = period_key.split(":", 1)[1]
            iso_year, iso_week = iso_text.split("-W", 1)
            period_date = date.fromisocalendar(int(iso_year), int(iso_week), 1)
        elif policy == "monthly" and period_key.startswith("monthly:"):
            year_text, month_text = period_key.split(":", 1)[1].split("-", 1)
            period_date = date(int(year_text), int(month_text), 1)
    except (ValueError, TypeError):
        period_date = None

    if period_date is None:
        submitted_at = _as_jakarta_datetime(submission.get("submitted_at"))
        period_date = submitted_at.date() if submitted_at else now.date()
    return _as_jakarta_datetime(_period_deadline_at(policy, period_date, form))


def _answers_by_field_id(submission: dict) -> dict[int, dict]:
    return {
        int(answer["field_id"]): answer
        for answer in submission.get("answers") or []
        if answer.get("field_id") is not None
    }


def _submission_edit_state(form: Optional[dict], submission: dict, school: Optional[dict], now: datetime) -> dict:
    state = {
        "can_edit": False,
        "edit_after_deadline": False,
        "edit_deadline_str": None,
        "edit_cutoff_str": None,
        "edit_disabled_reason": "Riwayat ini tidak bisa diedit.",
    }
    if not form:
        state["edit_disabled_reason"] = "Form tidak ditemukan."
        return state
    if submission.get("status") != "submitted":
        state["edit_disabled_reason"] = "Hanya laporan terkirim yang bisa diedit."
        return state
    if not form.get("is_active") or form.get("status") != "published":
        state["edit_disabled_reason"] = "Form sudah tidak aktif."
        return state
    if form.get("is_paused"):
        state["edit_disabled_reason"] = "Form sedang dipause oleh admin."
        return state
    if school and not can_school_access_form(form["id"], school["id"], school.get("jenjang")):
        state["edit_disabled_reason"] = "Sekolah tidak memiliki akses ke form ini."
        return state

    _annotate_repeat_form(form, now)
    deadline = _form_deadline_for_submission(form, submission, now)
    cutoff = _form_no_submission_cutoff_for_submission(form, submission, now)
    state["edit_after_deadline"] = bool(deadline and deadline < now)
    state["edit_deadline_str"] = _format_datetime_id(deadline)
    state["edit_cutoff_str"] = _format_datetime_id(cutoff)

    if form.get("repeat_closed"):
        state["edit_disabled_reason"] = "Masa pengisian form sudah berakhir."
        return state
    if cutoff and now > cutoff and _school_subject_to_no_submission(form, school):
        state["edit_disabled_reason"] = "Batas tidak mengumpulkan sudah lewat."
        return state
    if deadline and deadline < now and not form.get("allow_late"):
        state["edit_disabled_reason"] = "Deadline form sudah berakhir."
        return state

    state["can_edit"] = True
    state["edit_disabled_reason"] = None
    return state


def _repeat_deadline_errors(
    repeat_policy: str,
    repeat_deadline_time: Optional[time],
    repeat_deadline_day: Optional[int],
) -> list[str]:
    if repeat_policy not in PERIODIC_REPEAT_POLICIES:
        return []
    errors = []
    if not repeat_deadline_time:
        errors.append("Jam deadline periode wajib diisi.")
    if repeat_policy == "weekly" and repeat_deadline_day is None:
        errors.append("Hari deadline mingguan wajib dipilih.")
    if repeat_policy == "monthly" and repeat_deadline_day is None:
        errors.append("Tanggal deadline bulanan wajib diisi.")
    return errors


def _field_publish_errors(fields: list[dict]) -> list[str]:
    errors = []
    if not any(field.get("field_type") not in DISPLAY_ONLY_FIELD_TYPES for field in fields):
        errors.append("Form wajib memiliki minimal satu pertanyaan yang bisa dijawab sekolah.")
    for field in fields:
        if field.get("field_type") == "link" and field.get("required"):
            options = field.get("options_json") if isinstance(field.get("options_json"), dict) else {}
            if not options.get("url"):
                errors.append(f"Link wajib '{field.get('label')}' harus memiliki URL yang valid.")
    return errors


def _normalize_field_key(raw: str) -> str:
    clean = "".join(ch for ch in (raw or "").strip() if ch.isalnum() or ch in {"_", "-"})
    return clean[:80] if clean else f"f_{uuid.uuid4().hex[:12]}"


def _normalize_field_ref(raw: str) -> str:
    clean = "".join(ch for ch in (raw or "").strip() if ch.isalnum() or ch in {"_", "-"})
    return clean[:80]


def _normalize_link_url(raw: str) -> str:
    clean = (raw or "").strip()
    if not clean:
        return ""
    if "://" not in clean:
        clean = f"https://{clean}"
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return clean


def _parse_fields_from_form() -> list[dict]:
    """Parse dynamic field data from the form editor POST body."""
    fields = []
    field_ids = request.form.getlist("field_id[]")
    used_keys: set[str] = set()
    
    for i, fid in enumerate(field_ids):
        field_key = _normalize_field_key(fid)
        if field_key in used_keys:
            field_key = f"{field_key}_{uuid.uuid4().hex[:6]}"
        used_keys.add(field_key)

        label = request.form.get(f"field_label_{fid}", "").strip()
        if not label:
            continue
        ftype = request.form.get(f"field_type_{fid}", "text")
        if ftype not in ALLOWED_FIELD_TYPES:
            ftype = "text"
        # Alias: 'file' lama tetap didukung, tipe baru diproses normal
        
        # Checkbox for required: since it's a checkbox, if it exists in form it's 'on', else absent.
        # But for robustness we can check if it exists in a getlist or simple get.
        required = request.form.get(f"field_required_{fid}") == "on"
        
        options = None
        if ftype in CHOICE_FIELD_TYPES:
            options_raw = request.form.getlist(f"field_options_{fid}[]")
            options = [o.strip() for o in options_raw if o.strip()]
        elif ftype == "formula":
            required = False
            operator = request.form.get(f"field_formula_operator_{fid}", "subtract")
            if operator not in FORMULA_OPERATORS:
                operator = "subtract"
            options = {
                "left_key": _normalize_field_ref(request.form.get(f"field_formula_left_{fid}", "")),
                "operator": operator,
                "right_key": _normalize_field_ref(request.form.get(f"field_formula_right_{fid}", "")),
            }
        elif ftype == "link":
            options = {
                "url": _normalize_link_url(request.form.get(f"field_link_url_{fid}", "")),
                "button_text": request.form.get(f"field_link_text_{fid}", "").strip() or "Buka Link",
            }
        elif ftype in DISPLAY_ONLY_FIELD_TYPES:
            required = False
        
        fields.append(
            {
                "field_key": field_key,
                "label": label,
                "field_type": ftype,
                "options_json": options if options else None,
                "required": required,
                "sort_order": i,
            }
        )
    return fields


def _parse_number(raw) -> float:
    text = str(raw or "").strip()
    if not text:
        return 0.0
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _format_formula_number(value: float) -> str:
    if abs(value - round(value)) < 0.0000001:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _calculate_formula_value(field: dict, values_by_key: dict[str, str]) -> str:
    config = field.get("options_json") if isinstance(field.get("options_json"), dict) else {}
    left = _parse_number(values_by_key.get(config.get("left_key", "")))
    right = _parse_number(values_by_key.get(config.get("right_key", "")))
    operator = config.get("operator") or "subtract"

    if operator == "add":
        result = left + right
    elif operator == "multiply":
        result = left * right
    elif operator == "divide":
        result = left / right if right else 0.0
    else:
        result = left - right
    return _format_formula_number(result)


def _answer_values_for_analytics(field: dict, answer: Optional[dict]) -> list[str]:
    if not answer:
        return []
    ftype = field.get("field_type")
    if ftype == "checkbox":
        raw = answer.get("answer_json")
        if isinstance(raw, list):
            return [str(v) for v in raw if str(v).strip()]
        text = answer.get("answer_text") or ""
        return [v.strip() for v in text.split(",") if v.strip()]
    if ftype == "file":
        return [f.get("original_name") or "" for f in answer.get("files") or [] if f.get("original_name")]
    text = str(answer.get("answer_text") or "").strip()
    return [text] if text else []


def _build_laporan_analytics(fields: list[dict], submissions: list[dict]) -> list[dict]:
    total_submissions = len(submissions)
    analytics = []

    for field in fields:
        ftype = field.get("field_type")
        if ftype in DISPLAY_ONLY_FIELD_TYPES:
            continue

        filled_count = 0
        option_counts: dict[str, int] = {}
        numeric_values = []
        samples = []
        file_count = 0

        choices = field.get("options_json") if isinstance(field.get("options_json"), list) else []
        for choice in choices:
            option_counts[str(choice)] = 0

        for submission in submissions:
            answers_map = {a.get("field_id"): a for a in submission.get("answers") or []}
            answer = answers_map.get(field.get("id"))
            values = _answer_values_for_analytics(field, answer)
            if values:
                filled_count += 1

            if ftype in CHOICE_FIELD_TYPES:
                for value in values:
                    option_counts[value] = option_counts.get(value, 0) + 1
            elif ftype in FORMULA_SOURCE_TYPES:
                for value in values:
                    numeric_values.append(_parse_number(value))
            elif ftype == "file":
                file_count += len(values)
            elif values and len(samples) < 5:
                samples.append(values[0])

        choice_total = sum(option_counts.values()) or 1
        analytics.append(
            {
                "field": field,
                "response_count": filled_count,
                "empty_count": max(total_submissions - filled_count, 0),
                "response_rate": round((filled_count / total_submissions) * 100) if total_submissions else 0,
                "option_counts": [
                    {
                        "label": label,
                        "count": count,
                        "percent": round((count / choice_total) * 100) if choice_total else 0,
                    }
                    for label, count in option_counts.items()
                ],
                "numeric": {
                    "count": len(numeric_values),
                    "avg": _format_formula_number(sum(numeric_values) / len(numeric_values)) if numeric_values else None,
                    "min": _format_formula_number(min(numeric_values)) if numeric_values else None,
                    "max": _format_formula_number(max(numeric_values)) if numeric_values else None,
                    "sum": _format_formula_number(sum(numeric_values)) if numeric_values else None,
                },
                "file_count": file_count,
                "samples": samples,
            }
        )
    return analytics


# ═══════════════════════════════════════════════════════
# SEKOLAH ROUTES
# ═══════════════════════════════════════════════════════


@laporan_bp.route("/sekolah")
@role_required("sekolah")
def sekolah_laporan_list() -> Response:
    """Daftar form laporan yang tersedia untuk sekolah ini."""
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung dengan sekolah. Hubungi admin.", "warning")
        return redirect(url_for("portal.sekolah_home"))

    forms = list_forms_for_school(school["id"], jenjang=school.get("jenjang"))
    now = datetime.now(JAKARTA_TZ)
    for f in forms:
        sync_no_submissions(f["id"], now)

    for f in forms:
        repeat_state = _build_repeat_state(f, school["id"], now)
        dl = _form_deadline_for_request(f, now)
        f["is_expired"] = bool(dl and dl < now)
        f["deadline_str"] = _format_datetime_id(dl)
        f["deadline_iso"] = dl.isoformat() if dl else None
        f["already_submitted"] = repeat_state["already_submitted"]
        no_submission_cutoff = _form_no_submission_cutoff(f, now)
        f["no_submission_cutoff_str"] = _format_datetime_id(no_submission_cutoff)
        f["is_no_submission"] = bool(
            no_submission_cutoff
            and now > no_submission_cutoff
            and not repeat_state["already_submitted"]
            and _school_subject_to_no_submission(f, school)
        )
        f["can_fill"] = (
            not f.get("is_paused")
            and (not f["is_expired"] or f.get("allow_late"))
            and not f["is_no_submission"]
            and not repeat_state["repeat_closed"]
            and not repeat_state["blocked_by_submission"]
        )

    return render_template(
        "laporan/sekolah/list.html",
        school=school,
        forms=forms,
        now=now,
    )


@laporan_bp.route("/sekolah/<int:form_id>")
@role_required("sekolah")
def sekolah_laporan_fill(form_id: int) -> Response:
    """Halaman isi form laporan."""
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung dengan sekolah.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    form = get_form(form_id)
    if not form or not form.get("is_active"):
        flash("Form tidak ditemukan atau sudah tidak aktif.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_list"))
        
    if not can_school_access_form(form_id, school["id"], school.get("jenjang")):
        flash("Sekolah Anda tidak memiliki akses ke form ini.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    if form.get("is_paused"):
        flash("Pengisian form ini sedang dipause oleh admin.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    now = datetime.now(JAKARTA_TZ)
    repeat_state = _build_repeat_state(form, school["id"], now)
    # Cek expired
    dl = _form_deadline_for_request(form, now)
    form["deadline_str"] = _format_datetime_id(dl)
    form["deadline_iso"] = dl.isoformat() if dl else None
    no_submission_cutoff = _form_no_submission_cutoff(form, now)
    if (
        no_submission_cutoff
        and now > no_submission_cutoff
        and not repeat_state["already_submitted"]
        and _school_subject_to_no_submission(form, school)
    ):
        flash("Waktu pengisian form ini sudah melewati batas tidak mengumpulkan.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))
    if dl:
        if dl < now and not form.get("allow_late"):
            flash("Deadline form ini sudah berakhir.", "warning")
            return redirect(url_for("laporan.sekolah_laporan_list"))

    if repeat_state["repeat_closed"]:
        flash("Masa pengisian ulang form ini sudah berakhir.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))
    if repeat_state["blocked_by_submission"]:
        if repeat_state["policy"] in PERIODIC_REPEAT_POLICIES and form.get("current_period_label"):
            flash(f"Anda sudah mengisi form ini untuk {form['current_period_label']}.", "info")
        else:
            flash("Anda sudah mengisi form ini.", "info")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    fields = get_form_fields(form_id)
    return render_template(
        "laporan/sekolah/fill.html",
        form=form,
        fields=fields,
        school=school,
        already_submitted=repeat_state["already_submitted"],
        repeat_state=repeat_state,
    )


@laporan_bp.route("/sekolah/<int:form_id>/previous-answers")
@role_required("sekolah")
def sekolah_laporan_previous_answers(form_id: int) -> Response:
    """API: Ambil jawaban submission terakhir sekolah di form ini (untuk prefill periode baru)."""
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        return jsonify({"ok": False, "message": "Akun belum terhubung dengan sekolah."}), 403

    form = get_form(form_id)
    if not form or not form.get("is_active"):
        return jsonify({"ok": False, "message": "Form tidak ditemukan."}), 404

    if not can_school_access_form(form_id, school["id"], school.get("jenjang")):
        return jsonify({"ok": False, "message": "Akses ditolak."}), 403

    if form.get("is_paused"):
        return jsonify({"ok": False, "message": "Pengisian form ini sedang dipause oleh admin."}), 423

    # Hanya untuk form periodik
    if form.get("repeat_policy") not in ("daily", "weekly", "monthly"):
        return jsonify({"ok": False, "message": "Fitur ini hanya tersedia untuk form periodik."}), 400

    result = get_last_submission_answers(form_id, school["id"])
    if not result:
        return jsonify({"ok": False, "message": "Belum ada data dari periode sebelumnya."}), 404

    return jsonify({
        "ok": True,
        "period_label": result["period_label"],
        "answers": result["answers"],
    })


@laporan_bp.route("/sekolah/<int:form_id>/submit", methods=["POST"])
@role_required("sekolah")
def sekolah_laporan_submit(form_id: int) -> Response:
    """Kirim jawaban form laporan."""
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung dengan sekolah.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    form = get_form(form_id)
    if not form or not form.get("is_active"):
        flash("Form tidak valid.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    if not can_school_access_form(form_id, school["id"], school.get("jenjang")):
        flash("Sekolah Anda tidak memiliki akses ke form ini.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    if form.get("is_paused"):
        flash("Pengisian form ini sedang dipause oleh admin.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    now = datetime.now(JAKARTA_TZ)
    repeat_state = _build_repeat_state(form, school["id"], now)
    # Cek expired
    dl = _form_deadline_for_request(form, now)
    form["deadline_str"] = _format_datetime_id(dl)
    no_submission_cutoff = _form_no_submission_cutoff(form, now)
    if (
        no_submission_cutoff
        and now > no_submission_cutoff
        and not repeat_state["already_submitted"]
        and _school_subject_to_no_submission(form, school)
    ):
        flash("Waktu pengisian form ini sudah melewati batas tidak mengumpulkan.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))
    is_late = False
    late_days = 0
    late_minutes = 0
    if dl:
        if dl < now:
            if not form.get("allow_late"):
                flash("Deadline form ini sudah berakhir.", "warning")
                return redirect(url_for("laporan.sekolah_laporan_list"))
            is_late = True
            late_delta = now - dl
            late_days = late_delta.days
            late_minutes = max(int((late_delta.total_seconds() + 59) // 60), 1)

    if repeat_state["repeat_closed"]:
        flash("Masa pengisian ulang form ini sudah berakhir.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))
    if repeat_state["blocked_by_submission"]:
        if repeat_state["policy"] in PERIODIC_REPEAT_POLICIES and form.get("current_period_label"):
            flash(f"Anda sudah mengisi form ini untuk {form['current_period_label']}.", "info")
        else:
            flash("Anda sudah mengisi form ini.", "info")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    fields = get_form_fields(form_id)
    if not any(f["field_type"] not in DISPLAY_ONLY_FIELD_TYPES for f in fields):
        flash("Form ini belum memiliki pertanyaan yang bisa diisi. Hubungi admin.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    submitted_values_by_key = {}
    for f in fields:
        key = f.get("field_key")
        if not key or f["field_type"] not in {"number", "rating"}:
            continue
        submitted_values_by_key[key] = request.form.get(f"field_{f['id']}", "").strip()

    # Validasi required fields
    errors = []
    for f in fields:
        if not f.get("required"):
            continue
        ftype = f["field_type"]
        fid = f["id"]
        if ftype in FILE_UPLOAD_FIELD_TYPES:
            uploaded = request.files.getlist(f"field_{fid}[]")
            if not any(uf.filename for uf in uploaded):
                errors.append(f"Field '{f['label']}' wajib diisi.")
        elif ftype == "checkbox":
            vals = request.form.getlist(f"field_{fid}[]")
            if not vals:
                errors.append(f"Field '{f['label']}' wajib dipilih.")
        elif ftype == "link":
            val = request.form.get(f"field_{fid}", "").strip()
            if val != "clicked":
                errors.append(f"Link '{f['label']}' wajib dibuka terlebih dahulu.")
        elif ftype == "formula" or ftype in DISPLAY_ONLY_FIELD_TYPES:
            # These are display only, no value expected
            pass
        else:
            val = request.form.get(f"field_{fid}", "").strip()
            if not val:
                errors.append(f"Field '{f['label']}' wajib diisi.")

    if errors:
        for err in errors:
            flash(err, "warning")
        return redirect(url_for("laporan.sekolah_laporan_fill", form_id=form_id))

    # Buat submission
    try:
        sub = create_submission(
            form_id,
            school["id"],
            user["id"],
            is_late=is_late,
            late_days=late_days,
            late_minutes=late_minutes,
            repeat_period_key=repeat_state["period"].get("key"),
            repeat_period_label=repeat_state["period"].get("label"),
        )
    except UniqueViolation:
        if repeat_state["policy"] in PERIODIC_REPEAT_POLICIES and form.get("current_period_label"):
            flash(f"Anda sudah mengisi form ini untuk {form['current_period_label']}.", "info")
        else:
            flash("Anda sudah mengisi form ini.", "info")
        return redirect(url_for("laporan.sekolah_laporan_list"))
    submission_id = sub["id"]

    # Simpan jawaban per field
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    school_upload_dir = UPLOAD_FOLDER / str(school["id"]) / str(form_id)
    school_upload_dir.mkdir(parents=True, exist_ok=True)
    saved_rel_paths = []
    try:
        for f in fields:
            ftype = f["field_type"]
            fid = f["id"]

            if ftype in FILE_UPLOAD_FIELD_TYPES:
                uploaded_files = request.files.getlist(f"field_{fid}[]")
                # Filter sesuai tipe field
                if ftype == "upload_dokumen":
                    valid_files = [uf for uf in uploaded_files if uf.filename and _allowed_doc(uf.filename)]
                elif ftype == "upload_gambar":
                    valid_files = [uf for uf in uploaded_files if uf.filename and _allowed_image(uf.filename)]
                else:
                    valid_files = [uf for uf in uploaded_files if uf.filename and _allowed_file(uf.filename)]
                if not valid_files:
                    continue
                file_names = [uf.filename for uf in valid_files]
                answer_id = save_answer(submission_id, fid, None, answer_json=file_names)
                for uf in valid_files:
                    ext = uf.filename.rsplit(".", 1)[-1].lower()
                    saved_name = f"{uuid.uuid4().hex}.{ext}"
                    save_path = school_upload_dir / saved_name
                    if ftype == "upload_gambar":
                        file_size = _compress_and_save_image(uf, save_path)
                    else:
                        uf.save(str(save_path))
                        file_size = save_path.stat().st_size
                    rel_path = f"{school['id']}/{form_id}/{saved_name}"
                    saved_rel_paths.append(rel_path)
                    save_file(
                        answer_id,
                        rel_path,
                        uf.filename,
                        uf.content_type or "",
                        file_size,
                    )

            elif ftype == "checkbox":
                vals = request.form.getlist(f"field_{fid}[]")
                save_answer(submission_id, fid, ", ".join(vals), answer_json=vals)

            elif ftype == "rating":
                val = request.form.get(f"field_{fid}", "").strip()
                save_answer(submission_id, fid, val)

            elif ftype == "formula":
                val = _calculate_formula_value(f, submitted_values_by_key)
                save_answer(submission_id, fid, val)
                if f.get("field_key"):
                    submitted_values_by_key[f["field_key"]] = val

            elif ftype == "link":
                val = request.form.get(f"field_{fid}", "").strip()
                if val == "clicked":
                    save_answer(submission_id, fid, "Dibuka")

            else:
                val = request.form.get(f"field_{fid}", "").strip()
                save_answer(submission_id, fid, val)
    except Exception:
        current_app.logger.exception("Failed to save laporan answers for submission %s", submission_id)
        deleted = delete_submitted_submission(form_id, submission_id)
        db_file_paths = (deleted or {}).get("file_paths") or []
        _cleanup_submission_files(list(db_file_paths) + saved_rel_paths)
        flash("Jawaban gagal disimpan. Silakan coba kirim ulang.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_fill", form_id=form_id))

    flash("Laporan berhasil dikirim! Terima kasih.", "success")
    return redirect(url_for("laporan.sekolah_laporan_list"))


@laporan_bp.route("/sekolah/riwayat")
@role_required("sekolah")
def sekolah_laporan_history() -> Response:
    """Riwayat pengiriman laporan milik sekolah ini."""
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung dengan sekolah.", "warning")
        return redirect(url_for("portal.sekolah_home"))

    forms = list_forms_for_school(school["id"], jenjang=school.get("jenjang"))
    now = datetime.now(JAKARTA_TZ)
    for f in forms:
        sync_no_submissions(f["id"], now)

    submissions = list_school_submissions(school["id"])
    for submission in submissions:
        _annotate_late_submission(submission)
        if submission.get("status") == "submitted":
            form = get_form(submission["form_id"])
            edit_state = _submission_edit_state(form, submission, school, now)
            submission.update(edit_state)
    return render_template(
        "laporan/sekolah/history.html",
        school=school,
        submissions=submissions,
    )


@laporan_bp.route("/sekolah/riwayat/<int:submission_id>")
@role_required("sekolah")
def sekolah_laporan_detail(submission_id: int) -> Response:
    """Detail jawaban yang pernah dikirim sekolah ini."""
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    sub = get_submission_with_answers(submission_id)
    if not sub or sub.get("school_id") != school["id"]:
        flash("Laporan tidak ditemukan atau bukan milik sekolah Anda.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_history"))
    _annotate_late_submission(sub)
    form = get_form(sub["form_id"])
    sub.update(_submission_edit_state(form, sub, school, datetime.now(JAKARTA_TZ)))

    return render_template(
        "laporan/sekolah/detail.html",
        submission=sub,
        school=school,
    )


@laporan_bp.route("/sekolah/riwayat/<int:submission_id>/edit", methods=["GET", "POST"])
@role_required("sekolah")
def sekolah_laporan_edit_submission(submission_id: int) -> Response:
    """Edit an existing submitted laporan history row."""
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_list"))

    sub = get_submission_with_answers(submission_id)
    if not sub or sub.get("school_id") != school["id"]:
        flash("Laporan tidak ditemukan atau bukan milik sekolah Anda.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_history"))
    if sub.get("status") != "submitted":
        flash("Riwayat ini tidak bisa diedit.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_detail", submission_id=submission_id))

    form = get_form(sub["form_id"])
    if not form or not form.get("is_active"):
        flash("Form tidak ditemukan atau sudah tidak aktif.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_history"))
    if form.get("is_paused"):
        flash("Pengisian form ini sedang dipause oleh admin.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_detail", submission_id=submission_id))
    if not can_school_access_form(form["id"], school["id"], school.get("jenjang")):
        flash("Sekolah Anda tidak memiliki akses ke form ini.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_history"))

    now = datetime.now(JAKARTA_TZ)
    edit_state = _submission_edit_state(form, sub, school, now)
    if not edit_state["can_edit"]:
        flash(edit_state["edit_disabled_reason"] or "Riwayat ini tidak bisa diedit.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_detail", submission_id=submission_id))

    dl = _form_deadline_for_submission(form, sub, now)
    form["deadline_str"] = _format_datetime_id(dl)
    form["deadline_iso"] = dl.isoformat() if dl else None
    form["current_period_label"] = sub.get("repeat_period_label") or form.get("current_period_label")
    edit_after_deadline = edit_state["edit_after_deadline"]
    fields = get_form_fields(form["id"])
    existing_answers = _answers_by_field_id(sub)

    if request.method == "GET":
        return render_template(
            "laporan/sekolah/fill.html",
            form=form,
            fields=fields,
            school=school,
            already_submitted=True,
            repeat_state={"policy": _form_repeat_policy(form), "period": {}},
            edit_mode=True,
            submission=sub,
            existing_answers=existing_answers,
            edit_after_deadline=edit_after_deadline,
            edit_deadline_str=edit_state.get("edit_deadline_str"),
            edit_cutoff_str=edit_state.get("edit_cutoff_str"),
        )

    if not any(f["field_type"] not in DISPLAY_ONLY_FIELD_TYPES for f in fields):
        flash("Form ini belum memiliki pertanyaan yang bisa diisi. Hubungi admin.", "warning")
        return redirect(url_for("laporan.sekolah_laporan_detail", submission_id=submission_id))

    submitted_values_by_key = {}
    for f in fields:
        key = f.get("field_key")
        if not key or f["field_type"] not in {"number", "rating"}:
            continue
        submitted_values_by_key[key] = request.form.get(f"field_{f['id']}", "").strip()

    errors = []
    for f in fields:
        if not f.get("required"):
            continue
        ftype = f["field_type"]
        fid = f["id"]
        existing = existing_answers.get(fid)
        if ftype == "file":
            uploaded = request.files.getlist(f"field_{fid}[]")
            has_existing_files = bool(existing and existing.get("files"))
            if not has_existing_files and not any(uf.filename for uf in uploaded):
                errors.append(f"Field '{f['label']}' wajib diisi.")
        elif ftype == "checkbox":
            vals = request.form.getlist(f"field_{fid}[]")
            if not vals:
                errors.append(f"Field '{f['label']}' wajib dipilih.")
        elif ftype == "link":
            val = request.form.get(f"field_{fid}", "").strip()
            if val != "clicked":
                errors.append(f"Link '{f['label']}' wajib dibuka terlebih dahulu.")
        elif ftype == "formula" or ftype in DISPLAY_ONLY_FIELD_TYPES:
            pass
        else:
            val = request.form.get(f"field_{fid}", "").strip()
            if not val:
                errors.append(f"Field '{f['label']}' wajib diisi.")

    if errors:
        for err in errors:
            flash(err, "warning")
        return redirect(url_for("laporan.sekolah_laporan_edit_submission", submission_id=submission_id))

    is_late = False
    late_days = 0
    late_minutes = 0
    if dl and dl < now:
        is_late = True
        late_delta = now - dl
        late_days = late_delta.days
        late_minutes = max(int((late_delta.total_seconds() + 59) // 60), 1)

    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    school_upload_dir = UPLOAD_FOLDER / str(school["id"]) / str(form["id"])
    school_upload_dir.mkdir(parents=True, exist_ok=True)
    saved_rel_paths = []
    try:
        for f in fields:
            ftype = f["field_type"]
            fid = f["id"]

            if ftype in FILE_UPLOAD_FIELD_TYPES:
                uploaded_files = request.files.getlist(f"field_{fid}[]")
                # Filter sesuai tipe field
                if ftype == "upload_dokumen":
                    valid_files = [uf for uf in uploaded_files if uf.filename and _allowed_doc(uf.filename)]
                elif ftype == "upload_gambar":
                    valid_files = [uf for uf in uploaded_files if uf.filename and _allowed_image(uf.filename)]
                else:
                    valid_files = [uf for uf in uploaded_files if uf.filename and _allowed_file(uf.filename)]
                if not valid_files:
                    continue
                existing = existing_answers.get(fid)
                old_paths = [file_info.get("file_path") for file_info in (existing.get("files") if existing else []) if file_info.get("file_path")]
                file_names = [uf.filename for uf in valid_files]
                answer_id = save_answer(submission_id, fid, None, answer_json=file_names)
                replace_answer_files(answer_id, old_paths)
                _cleanup_submission_files(old_paths)
                for uf in valid_files:
                    ext = uf.filename.rsplit(".", 1)[-1].lower()
                    saved_name = f"{uuid.uuid4().hex}.{ext}"
                    save_path = school_upload_dir / saved_name
                    if ftype == "upload_gambar":
                        file_size = _compress_and_save_image(uf, save_path)
                    else:
                        uf.save(str(save_path))
                        file_size = save_path.stat().st_size
                    rel_path = f"{school['id']}/{form['id']}/{saved_name}"
                    saved_rel_paths.append(rel_path)
                    save_file(
                        answer_id,
                        rel_path,
                        uf.filename,
                        uf.content_type or "",
                        file_size,
                    )

            elif ftype == "checkbox":
                vals = request.form.getlist(f"field_{fid}[]")
                save_answer(submission_id, fid, ", ".join(vals), answer_json=vals)
            elif ftype == "rating":
                val = request.form.get(f"field_{fid}", "").strip()
                save_answer(submission_id, fid, val)
            elif ftype == "formula":
                val = _calculate_formula_value(f, submitted_values_by_key)
                save_answer(submission_id, fid, val)
                if f.get("field_key"):
                    submitted_values_by_key[f["field_key"]] = val
            elif ftype == "link":
                val = request.form.get(f"field_{fid}", "").strip()
                if val == "clicked":
                    save_answer(submission_id, fid, "Dibuka")
            else:
                val = request.form.get(f"field_{fid}", "").strip()
                save_answer(submission_id, fid, val)

        update_submission_status(
            submission_id,
            user["id"],
            is_late=is_late,
            late_days=late_days,
            late_minutes=late_minutes,
        )
    except Exception:
        current_app.logger.exception("Failed to update laporan submission %s", submission_id)
        _cleanup_submission_files(saved_rel_paths)
        flash("Perubahan jawaban gagal disimpan. Silakan coba lagi.", "danger")
        return redirect(url_for("laporan.sekolah_laporan_edit_submission", submission_id=submission_id))

    flash("Perubahan laporan berhasil disimpan.", "success")
    return redirect(url_for("laporan.sekolah_laporan_detail", submission_id=submission_id))


# ═══════════════════════════════════════════════════════
# ADMIN ROUTES
# ═══════════════════════════════════════════════════════


@laporan_bp.route("/admin")
@role_required("admin")
def admin_laporan_list() -> Response:
    """Admin: daftar semua form laporan."""
    forms = list_all_forms(include_inactive=True)
    now = datetime.now(JAKARTA_TZ)
    for form in forms:
        _annotate_repeat_form(form, now)
        if form.get("status") != "draft":
            form["share_caption"] = _build_form_share_caption(form, now)
    return render_template("laporan/admin/list.html", forms=forms)


@laporan_bp.route("/admin/buat", methods=["GET", "POST"])
@role_required("admin")
def admin_laporan_create() -> Response:
    """Admin: buat form laporan baru."""
    all_schools = list_all_schools_simple()

    if request.method == "GET":
        user = current_user()
        draft = create_form(
            title="Draft Form Laporan",
            description="",
            target_scope="all",
            target_jenjang=None,
            allow_multiple=False,
            allow_late=False,
            very_late_after_minutes=DEFAULT_VERY_LATE_AFTER_MINUTES,
            no_submission_after_minutes=None,
            no_submission_jenjangs=None,
            no_submission_statuses=None,
            is_active=False,
            deadline_at=None,
            created_by=user["id"],
            status="draft",
            repeat_policy="once",
            repeat_until_at=None,
            repeat_deadline_time=None,
            repeat_deadline_day=None,
        )
        flash("Draft form baru dibuat. Lanjutkan pengisian lalu simpan draft atau terbitkan.", "info")
        return redirect(url_for("laporan.admin_laporan_edit", form_id=draft["id"]))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        target_scope = request.form.get("target_scope", "all")
        target_jenjang = request.form.get("target_jenjang", "").strip() or None
        (
            repeat_policy,
            allow_multiple,
            repeat_until_at,
            repeat_deadline_time,
            repeat_deadline_day,
        ) = _parse_repeat_settings_from_request()
        allow_late = request.form.get("allow_late") == "1"
        very_late_after_minutes = _parse_very_late_after_minutes()
        no_submission_after_minutes = _parse_no_submission_after_minutes()
        no_submission_jenjangs = _parse_no_submission_jenjangs()
        no_submission_statuses = _parse_no_submission_statuses()
        is_active = request.form.get("is_active") == "1"
        deadline_raw = request.form.get("deadline_at", "").strip()
        deadline_at = _parse_deadline(deadline_raw)
        specific_school_ids = [int(x) for x in request.form.getlist("target_schools[]") if x.isdigit()]
        form_action = request.form.get("form_action", "publish")
        status = "draft" if form_action == "save_draft" else "published"
        if status == "draft":
            title = title or "Draft Form Laporan"
            is_active = False

        if status == "published" and not title:
            flash("Judul form wajib diisi.", "warning")
            return render_template(
                "laporan/admin/form_editor.html",
                form=None,
                all_schools=all_schools,
                available_jenjangs=_available_jenjangs(all_schools),
                target_school_ids=[],
                fields=[],
            )
        if status == "published":
            repeat_errors = _repeat_deadline_errors(repeat_policy, repeat_deadline_time, repeat_deadline_day)
            if repeat_errors:
                for err in repeat_errors:
                    flash(err, "warning")
                return render_template(
                    "laporan/admin/form_editor.html",
                    form=None,
                    all_schools=all_schools,
                    available_jenjangs=_available_jenjangs(all_schools),
                    target_school_ids=[],
                    fields=[],
                )
        fields = _parse_fields_from_form()
        if status == "published":
            field_errors = _field_publish_errors(fields)
            if field_errors:
                for err in field_errors:
                    flash(err, "warning")
                return render_template(
                    "laporan/admin/form_editor.html",
                    form=None,
                    all_schools=all_schools,
                    available_jenjangs=_available_jenjangs(all_schools),
                    target_school_ids=[],
                    fields=fields,
                )

        user = current_user()
        created = create_form(
            title=title,
            description=description,
            target_scope=target_scope,
            target_jenjang=target_jenjang if target_scope == "jenjang" else None,
            allow_multiple=allow_multiple,
            allow_late=allow_late,
            very_late_after_minutes=very_late_after_minutes,
            no_submission_after_minutes=no_submission_after_minutes,
            no_submission_jenjangs=no_submission_jenjangs,
            no_submission_statuses=no_submission_statuses,
            is_active=is_active,
            deadline_at=deadline_at,
            created_by=user["id"],
            status=status,
            repeat_policy=repeat_policy,
            repeat_until_at=repeat_until_at,
            repeat_deadline_time=repeat_deadline_time,
            repeat_deadline_day=repeat_deadline_day,
        )
        form_id = created["id"]

        if target_scope == "specific" and specific_school_ids:
            set_form_targets(form_id, specific_school_ids)

        if fields:
            replace_form_fields(form_id, fields)

        if status == "draft":
            flash("Draft form berhasil disimpan.", "success")
            return redirect(url_for("laporan.admin_laporan_edit", form_id=form_id))

        flash(f"Form '{title}' berhasil diterbitkan!", "success")
        return redirect(url_for("laporan.admin_laporan_list"))

    return render_template(
        "laporan/admin/form_editor.html",
        form=None,
        all_schools=all_schools,
        available_jenjangs=_available_jenjangs(all_schools),
        target_school_ids=[],
        fields=[],
    )


@laporan_bp.route("/admin/<int:form_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def admin_laporan_edit(form_id: int) -> Response:
    """Admin: edit form laporan yang sudah ada."""
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))

    all_schools = list_all_schools_simple()
    existing_fields = get_form_fields(form_id)
    existing_target_ids = get_form_target_school_ids(form_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        target_scope = request.form.get("target_scope", "all")
        target_jenjang = request.form.get("target_jenjang", "").strip() or None
        (
            repeat_policy,
            allow_multiple,
            repeat_until_at,
            repeat_deadline_time,
            repeat_deadline_day,
        ) = _parse_repeat_settings_from_request()
        allow_late = request.form.get("allow_late") == "1"
        very_late_after_minutes = _parse_very_late_after_minutes()
        no_submission_after_minutes = _parse_no_submission_after_minutes()
        no_submission_jenjangs = _parse_no_submission_jenjangs()
        no_submission_statuses = _parse_no_submission_statuses()
        is_active = request.form.get("is_active") == "1"
        deadline_raw = request.form.get("deadline_at", "").strip()
        deadline_at = _parse_deadline(deadline_raw)
        specific_school_ids = [int(x) for x in request.form.getlist("target_schools[]") if x.isdigit()]
        form_action = request.form.get("form_action", "publish")
        status = "draft" if form_action == "save_draft" else "published"
        if status == "draft":
            title = title or "Draft Form Laporan"
            is_active = False

        if status == "published" and not title:
            flash("Judul form wajib diisi.", "warning")
            return render_template(
                "laporan/admin/form_editor.html",
                form=form,
                all_schools=all_schools,
                available_jenjangs=_available_jenjangs(all_schools),
                target_school_ids=existing_target_ids,
                fields=existing_fields,
            )
        if status == "published":
            repeat_errors = _repeat_deadline_errors(repeat_policy, repeat_deadline_time, repeat_deadline_day)
            if repeat_errors:
                for err in repeat_errors:
                    flash(err, "warning")
                return render_template(
                    "laporan/admin/form_editor.html",
                    form=form,
                    all_schools=all_schools,
                    available_jenjangs=_available_jenjangs(all_schools),
                    target_school_ids=existing_target_ids,
                    fields=existing_fields,
                )
        fields = _parse_fields_from_form()
        if status == "published":
            field_errors = _field_publish_errors(fields)
            if field_errors:
                for err in field_errors:
                    flash(err, "warning")
                return render_template(
                    "laporan/admin/form_editor.html",
                    form=form,
                    all_schools=all_schools,
                    available_jenjangs=_available_jenjangs(all_schools),
                    target_school_ids=existing_target_ids,
                    fields=fields,
                )

        user = current_user()
        update_form(
            form_id=form_id,
            title=title,
            description=description,
            target_scope=target_scope,
            target_jenjang=target_jenjang if target_scope == "jenjang" else None,
            allow_multiple=allow_multiple,
            allow_late=allow_late,
            very_late_after_minutes=very_late_after_minutes,
            no_submission_after_minutes=no_submission_after_minutes,
            no_submission_jenjangs=no_submission_jenjangs,
            no_submission_statuses=no_submission_statuses,
            is_active=is_active,
            deadline_at=deadline_at,
            updated_by=user["id"],
            status=status,
            repeat_policy=repeat_policy,
            repeat_until_at=repeat_until_at,
            repeat_deadline_time=repeat_deadline_time,
            repeat_deadline_day=repeat_deadline_day,
        )

        set_form_targets(form_id, specific_school_ids if target_scope == "specific" else [])
        replace_form_fields(form_id, fields)

        if status == "draft":
            flash("Draft form berhasil disimpan.", "success")
            return redirect(url_for("laporan.admin_laporan_edit", form_id=form_id))

        flash("Form berhasil diterbitkan." if form.get("status") == "draft" else "Form berhasil diperbarui.", "success")
        return redirect(url_for("laporan.admin_laporan_list"))

    return render_template(
        "laporan/admin/form_editor.html",
        form=form,
        all_schools=all_schools,
        available_jenjangs=_available_jenjangs(all_schools),
        target_school_ids=existing_target_ids,
        fields=existing_fields,
    )


@laporan_bp.route("/admin/<int:form_id>/autosave", methods=["POST"])
@role_required("admin")
def admin_laporan_autosave(form_id: int) -> Response:
    """Autosave draft laporan form without publishing it."""
    form = get_form(form_id)
    if not form:
        return jsonify({"ok": False, "message": "Form tidak ditemukan."}), 404
    if form.get("status") != "draft":
        return jsonify({"ok": False, "message": "Autosave hanya untuk draft."}), 400

    title = request.form.get("title", "").strip() or "Draft Form Laporan"
    description = request.form.get("description", "").strip()
    target_scope = request.form.get("target_scope", "all")
    target_jenjang = request.form.get("target_jenjang", "").strip() or None
    (
        repeat_policy,
        allow_multiple,
        repeat_until_at,
        repeat_deadline_time,
        repeat_deadline_day,
    ) = _parse_repeat_settings_from_request()
    allow_late = request.form.get("allow_late") == "1"
    very_late_after_minutes = _parse_very_late_after_minutes()
    no_submission_after_minutes = _parse_no_submission_after_minutes()
    no_submission_jenjangs = _parse_no_submission_jenjangs()
    no_submission_statuses = _parse_no_submission_statuses()
    deadline_at = _parse_deadline(request.form.get("deadline_at", "").strip())
    specific_school_ids = [int(x) for x in request.form.getlist("target_schools[]") if x.isdigit()]
    user = current_user()

    update_form(
        form_id=form_id,
        title=title,
        description=description,
        target_scope=target_scope,
        target_jenjang=target_jenjang if target_scope == "jenjang" else None,
        allow_multiple=allow_multiple,
        allow_late=allow_late,
        very_late_after_minutes=very_late_after_minutes,
        no_submission_after_minutes=no_submission_after_minutes,
        no_submission_jenjangs=no_submission_jenjangs,
        no_submission_statuses=no_submission_statuses,
        is_active=False,
        deadline_at=deadline_at,
        updated_by=user["id"],
        status="draft",
        repeat_policy=repeat_policy,
        repeat_until_at=repeat_until_at,
        repeat_deadline_time=repeat_deadline_time,
        repeat_deadline_day=repeat_deadline_day,
    )

    set_form_targets(form_id, specific_school_ids if target_scope == "specific" else [])
    replace_form_fields(form_id, _parse_fields_from_form())

    return jsonify(
        {
            "ok": True,
            "message": "Draft tersimpan otomatis.",
            "saved_at": datetime.now(JAKARTA_TZ).strftime("%H:%M:%S"),
        }
    )


@laporan_bp.route("/admin/<int:form_id>/preview")
@role_required("admin")
def admin_laporan_preview(form_id: int) -> Response:
    """Admin: preview form exactly as the school fill page sees it."""
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))

    now = datetime.now(JAKARTA_TZ)
    _annotate_repeat_form(form, now)
    dl = _form_deadline_for_request(form, now)
    form["deadline_str"] = _format_datetime_id(dl)
    form["deadline_iso"] = dl.isoformat() if dl else None
    fields = get_form_fields(form_id)
    preview_school = {
        "id": 0,
        "name": "Contoh Tampilan Sekolah",
        "npsn": "PREVIEW",
        "jenjang": form.get("target_jenjang") or "SD",
    }

    return render_template(
        "laporan/sekolah/fill.html",
        form=form,
        fields=fields,
        school=preview_school,
        already_submitted=False,
        repeat_state={"policy": form.get("repeat_policy"), "period": {}},
        preview_mode=True,
    )


@laporan_bp.route("/admin/<int:form_id>/jawaban")
@role_required("admin")
def admin_laporan_answers(form_id: int) -> Response:
    """Admin: lihat semua jawaban yang masuk untuk form ini."""
    sync_no_submissions(form_id)
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))
    _annotate_repeat_form(form, datetime.now(JAKARTA_TZ))

    is_periodic = form.get("repeat_policy") in PERIODIC_REPEAT_POLICIES
    filter_period = request.args.get("period") or request.args.get("date")

    # Determine default filter period
    if is_periodic:
        curr_key = form.get("current_period_key")
        if not filter_period:
            filter_period = curr_key
    else:
        filter_period = "all"

    fields = get_form_fields(form_id)
    submissions = list_form_submissions(form_id)

    # Gather all unique periods
    periods = {}
    if is_periodic:
        curr_key = form.get("current_period_key")
        curr_label = form.get("current_period_label")
        if curr_key and curr_label:
            periods[curr_key] = curr_label
        for sub in submissions:
            pk = sub.get("repeat_period_key")
            pl = sub.get("repeat_period_label")
            if pk and pl:
                periods[pk] = pl

    sorted_periods = sorted(periods.items(), key=lambda x: x[0], reverse=True)

    # Filter submissions by period key if periodic and not "all"
    if is_periodic and filter_period != "all":
        submissions = [s for s in submissions if s.get("repeat_period_key") == filter_period]

    # Enrich submissions with their answers
    detailed = []
    for sub in submissions:
        sub_detail = get_submission_with_answers(sub["id"])
        if sub_detail:
            _annotate_late_submission(sub_detail)
            detailed.append(sub_detail)
    empty_submitted_count = sum(
        1
        for sub in detailed
        if sub.get("status") == "submitted" and not sub.get("answers")
    )
    analytics = _build_laporan_analytics(fields, detailed)

    return render_template(
        "laporan/admin/answers.html",
        form=form,
        fields=fields,
        submissions=detailed,
        analytics=analytics,
        filter_period=filter_period,
        periods=sorted_periods,
        is_periodic=is_periodic,
        empty_submitted_count=empty_submitted_count,
    )


@laporan_bp.route("/admin/<int:form_id>/jawaban/delete-empty", methods=["POST"])
@role_required("admin")
def admin_laporan_delete_empty_submissions(form_id: int) -> Response:
    """Admin: delete empty submitted rows so affected schools can submit again."""
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))

    filter_period = request.args.get("period") or request.form.get("period") or "all"
    period_key = filter_period if filter_period and filter_period != "all" else None
    deleted_count = delete_empty_submitted_submissions(form_id, period_key)
    if deleted_count:
        flash(f"{deleted_count} riwayat terkirim kosong berhasil dihapus. Sekolah terkait dapat mengisi ulang jika form masih dibuka.", "success")
    else:
        flash("Tidak ada riwayat terkirim kosong untuk dihapus.", "info")
    return redirect(url_for("laporan.admin_laporan_answers", form_id=form_id, period=filter_period))


@laporan_bp.route("/admin/<int:form_id>/jawaban/<int:submission_id>/delete", methods=["POST"])
@role_required("admin")
def admin_laporan_delete_submission(form_id: int, submission_id: int) -> Response:
    """Admin: delete one submitted history row so the school can submit again."""
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))

    filter_period = request.args.get("period") or request.form.get("period") or "all"
    deleted = delete_submitted_submission(form_id, submission_id)
    if not deleted:
        flash("Riwayat isian tidak ditemukan atau bukan jawaban terkirim.", "warning")
        return redirect(url_for("laporan.admin_laporan_answers", form_id=form_id, period=filter_period))

    _cleanup_submission_files(deleted.get("file_paths") or [])
    school_name = deleted.get("school_name") or "sekolah"
    period_label = deleted.get("repeat_period_label")
    period_text = f" untuk {period_label}" if period_label else ""
    flash(
        f"Riwayat isian {school_name}{period_text} berhasil dihapus. Sekolah dapat mengisi lagi jika form masih dibuka.",
        "success",
    )
    return redirect(url_for("laporan.admin_laporan_answers", form_id=form_id, period=filter_period))


@laporan_bp.route("/admin/<int:form_id>/export")
@role_required("admin")
def admin_laporan_export(form_id: int) -> Response:
    """Admin: export semua jawaban ke Excel."""
    sync_no_submissions(form_id)
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))

    filter_period = request.args.get("period") or request.args.get("date") or "all"
    filename, xlsx_bytes = export_form_xlsx(form_id, filter_period)
    return send_file(
        io.BytesIO(xlsx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@laporan_bp.route("/admin/<int:form_id>/export-no-submission")
@role_required("admin")
def admin_laporan_export_no_submission(form_id: int) -> Response:
    """Admin: export list sekolah yang tidak mengumpulkan ke Excel."""
    sync_no_submissions(form_id)
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))

    filter_period = request.args.get("period") or request.args.get("date") or "all"
    filename, xlsx_bytes = export_no_submissions_xlsx(form_id, filter_period)
    return send_file(
        io.BytesIO(xlsx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@laporan_bp.route("/admin/<int:form_id>/pause", methods=["POST"])
@role_required("admin")
def admin_laporan_pause(form_id: int) -> Response:
    """Admin: pause/unpause school submissions for a published form."""
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))
    if form.get("status") == "draft":
        flash("Draft belum bisa dipause karena belum diterbitkan.", "warning")
        return redirect(url_for("laporan.admin_laporan_list"))

    user = current_user()
    should_pause = not bool(form.get("is_paused"))
    set_form_paused(form_id, should_pause, user["id"])

    if should_pause:
        flash(f"Form '{form['title']}' dipause. Sekolah tidak bisa mengisi sampai admin unpause.", "success")
    else:
        flash(f"Form '{form['title']}' di-unpause. Sekolah dapat mengisi lagi sesuai status dan deadline form.", "success")
    return redirect(url_for("laporan.admin_laporan_list"))


@laporan_bp.route("/admin/<int:form_id>/delete", methods=["POST"])
@role_required("admin")
def admin_laporan_delete(form_id: int) -> Response:
    """Admin: hapus form beserta semua datanya."""
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))

    delete_form(form_id)
    label = "Draft" if form.get("status") == "draft" else "Form"
    flash(f"{label} '{form['title']}' berhasil dihapus.", "success")
    return redirect(url_for("laporan.admin_laporan_list"))


@laporan_bp.route("/uploads/<path:filepath>")
@role_required("sekolah", "admin", "coordinator")
def laporan_serve_file(filepath: str) -> Response:
    """Serve uploaded laporan files securely."""
    from pathlib import PurePosixPath
    from flask import send_from_directory, abort

    file_path = PurePosixPath(filepath)
    if ".." in file_path.parts:
        abort(403)
    target_path = UPLOAD_FOLDER / filepath
    if not target_path.is_file():
        abort(404)
    return send_file(target_path)


@laporan_bp.route("/admin/kpi")
@role_required("admin")
def admin_laporan_kpi() -> Response:
    """Admin: lihat KPI ketepatan waktu pengisian form per sekolah."""
    kpi_data = fetch_laporan_kpi_schools()
    return render_template(
        "laporan/admin/kpi.html",
        kpi_data=kpi_data,
    )
