"""Routes for the Laporan (Form Reports) system."""
from __future__ import annotations

import io
import json
import uuid
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

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
    save_answer,
    save_file,
    get_submission_with_answers,
    list_school_submissions,
    list_form_submissions,
    export_form_xlsx,
    list_all_schools_simple,
    fetch_laporan_kpi_schools,
    can_school_access_form,
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
CHOICE_FIELD_TYPES = {"radio", "checkbox", "dropdown"}
FORMULA_OPERATORS = {"add", "subtract", "multiply", "divide"}
FORMULA_SOURCE_TYPES = {"number", "rating", "formula"}
DISPLAY_ONLY_FIELD_TYPES = {"header", "info"}
REPEAT_POLICIES = {"once", "multiple", "daily", "weekly", "monthly"}
PERIODIC_REPEAT_POLICIES = {"daily", "weekly", "monthly"}
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
ALLOWED_FIELD_TYPES = {
    "text",
    "textarea",
    "radio",
    "checkbox",
    "dropdown",
    "file",
    "date",
    "time",
    "number",
    "rating",
    "email",
    "header",
    "info",
    "formula",
}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_EXTENSIONS


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


def _normalize_field_key(raw: str) -> str:
    clean = "".join(ch for ch in (raw or "").strip() if ch.isalnum() or ch in {"_", "-"})
    return clean[:80] if clean else f"f_{uuid.uuid4().hex[:12]}"


def _normalize_field_ref(raw: str) -> str:
    clean = "".join(ch for ch in (raw or "").strip() if ch.isalnum() or ch in {"_", "-"})
    return clean[:80]


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
        repeat_state = _build_repeat_state(f, school["id"], now)
        dl = _form_deadline_for_request(f, now)
        f["is_expired"] = bool(dl and dl < now)
        f["deadline_str"] = _format_datetime_id(dl)
        f["already_submitted"] = repeat_state["already_submitted"]
        f["can_fill"] = (
            (not f["is_expired"] or f.get("allow_late"))
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

    now = datetime.now(JAKARTA_TZ)
    repeat_state = _build_repeat_state(form, school["id"], now)
    # Cek expired
    dl = _form_deadline_for_request(form, now)
    form["deadline_str"] = _format_datetime_id(dl)
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

    now = datetime.now(JAKARTA_TZ)
    repeat_state = _build_repeat_state(form, school["id"], now)
    # Cek expired
    dl = _form_deadline_for_request(form, now)
    form["deadline_str"] = _format_datetime_id(dl)
    is_late = False
    late_days = 0
    if dl:
        if dl < now:
            if not form.get("allow_late"):
                flash("Deadline form ini sudah berakhir.", "warning")
                return redirect(url_for("laporan.sekolah_laporan_list"))
            is_late = True
            late_days = (now - dl).days

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
        if ftype == "file":
            uploaded = request.files.getlist(f"field_{fid}[]")
            if not any(uf.filename for uf in uploaded):
                errors.append(f"Field '{f['label']}' wajib diisi.")
        elif ftype == "checkbox":
            vals = request.form.getlist(f"field_{fid}[]")
            if not vals:
                errors.append(f"Field '{f['label']}' wajib dipilih.")
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

    for f in fields:
        ftype = f["field_type"]
        fid = f["id"]

        if ftype == "file":
            uploaded_files = request.files.getlist(f"field_{fid}[]")
            valid_files = [uf for uf in uploaded_files if uf.filename and _allowed_file(uf.filename)]
            if not valid_files:
                continue
            file_names = [uf.filename for uf in valid_files]
            answer_id = save_answer(submission_id, fid, None, answer_json=file_names)
            for uf in valid_files:
                ext = uf.filename.rsplit(".", 1)[-1].lower()
                saved_name = f"{uuid.uuid4().hex}.{ext}"
                save_path = school_upload_dir / saved_name
                uf.save(str(save_path))
                rel_path = f"{school['id']}/{form_id}/{saved_name}"
                save_file(
                    answer_id,
                    rel_path,
                    uf.filename,
                    uf.content_type or "",
                    save_path.stat().st_size,
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

        else:
            val = request.form.get(f"field_{fid}", "").strip()
            save_answer(submission_id, fid, val)

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

    submissions = list_school_submissions(school["id"])
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

    return render_template(
        "laporan/sekolah/detail.html",
        submission=sub,
        school=school,
    )


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
                    target_school_ids=[],
                    fields=[],
                )

        user = current_user()
        created = create_form(
            title=title,
            description=description,
            target_scope=target_scope,
            target_jenjang=target_jenjang if target_scope == "jenjang" else None,
            allow_multiple=allow_multiple,
            allow_late=allow_late,
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

        fields = _parse_fields_from_form()
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
                    target_school_ids=existing_target_ids,
                    fields=existing_fields,
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
        fields = _parse_fields_from_form()
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


@laporan_bp.route("/admin/<int:form_id>/jawaban")
@role_required("admin")
def admin_laporan_answers(form_id: int) -> Response:
    """Admin: lihat semua jawaban yang masuk untuk form ini."""
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))
    _annotate_repeat_form(form, datetime.now(JAKARTA_TZ))

    fields = get_form_fields(form_id)
    submissions = list_form_submissions(form_id)

    # Enrich submissions with their answers
    detailed = []
    for sub in submissions:
        sub_detail = get_submission_with_answers(sub["id"])
        if sub_detail:
            detailed.append(sub_detail)
    analytics = _build_laporan_analytics(fields, detailed)

    return render_template(
        "laporan/admin/answers.html",
        form=form,
        fields=fields,
        submissions=detailed,
        analytics=analytics,
    )


@laporan_bp.route("/admin/<int:form_id>/export")
@role_required("admin")
def admin_laporan_export(form_id: int) -> Response:
    """Admin: export semua jawaban ke Excel."""
    form = get_form(form_id)
    if not form:
        flash("Form tidak ditemukan.", "danger")
        return redirect(url_for("laporan.admin_laporan_list"))

    filename, xlsx_bytes = export_form_xlsx(form_id)
    return send_file(
        io.BytesIO(xlsx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


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
