from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dashboard.db_access import get_cursor


SOCIAL_KEYS = (
    ("Instagram", "instagram"),
    ("TikTok", "tiktok"),
    ("YouTube", "youtube"),
    ("Telegram", "telegram"),
    ("WA Channel", "wa_channel"),
)

PHONE_KEYS = (
    ("Sekolah", "school_phone"),
    ("Operator", "coordinator_phone"),
    ("Fax", "fax"),
)


def _normalize_metadata(raw_metadata: Any) -> dict[str, Any]:
    if isinstance(raw_metadata, dict):
        return raw_metadata
    return {}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"-", "--", "0", "n/a", "na", "null", "none"}:
        return ""
    return text


def _escape_md_cell(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return "-"
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _combine_unique(values: list[str]) -> str:
    seen: set[str] = set()
    unique_values: list[str] = []
    for item in values:
        cleaned = _clean_text(item)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_values.append(cleaned)
    return "; ".join(unique_values)


def _format_social_media(metadata: dict[str, Any]) -> str:
    parts: list[str] = []
    for label, key in SOCIAL_KEYS:
        value = _clean_text(metadata.get(key))
        if value:
            parts.append(f"{label}: {value}")
    return _combine_unique(parts) or "-"


def _format_phone(metadata: dict[str, Any]) -> str:
    parts: list[str] = []
    for label, key in PHONE_KEYS:
        value = _clean_text(metadata.get(key))
        if value:
            parts.append(f"{label}: {value}")
    return _combine_unique(parts) or "-"


def _format_email(metadata: dict[str, Any], school_user_emails: str) -> str:
    values: list[str] = []
    cs_email = _clean_text(metadata.get("cs_email"))
    if cs_email:
        values.append(cs_email)

    for email in _clean_text(school_user_emails).split(";"):
        email = email.strip()
        if email:
            values.append(email)

    return _combine_unique(values) or "-"


def _to_number_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    text = str(value).strip()
    if not text:
        return ""
    try:
        parsed = float(text)
        if parsed.is_integer():
            return str(int(parsed))
        return str(parsed)
    except ValueError:
        return text


def _format_empty_seats(metadata: dict[str, Any]) -> str:
    total_text = _to_number_text(metadata.get("empty_seats"))
    by_grade = metadata.get("empty_seats_by_grade")

    grade_parts: list[str] = []
    if isinstance(by_grade, dict):
        sortable: list[tuple[str, str]] = []
        for key, value in by_grade.items():
            key_text = str(key).strip()
            val_text = _to_number_text(value)
            if not key_text or not val_text:
                continue
            sortable.append((key_text, val_text))

        def _sort_key(item: tuple[str, str]) -> tuple[int, str]:
            key_text = item[0]
            return (0, f"{int(key_text):03d}") if key_text.isdigit() else (1, key_text.lower())

        for key_text, val_text in sorted(sortable, key=_sort_key):
            grade_parts.append(f"K{key_text}: {val_text}")

    if total_text and grade_parts:
        return f"{total_text} ({'; '.join(grade_parts)})"
    if total_text:
        return total_text
    if grade_parts:
        return "; ".join(grade_parts)
    return "-"


def fetch_school_directory_rows() -> list[dict[str, Any]]:
    query = """
        SELECT
            s.id,
            s.npsn,
            s.name,
            s.jenjang,
            s.alamat,
            s.metadata,
            string_agg(DISTINCT du.email, '; ' ORDER BY du.email) AS school_user_emails
        FROM portal_schools s
        LEFT JOIN dashboard_users du
            ON du.school_id = s.id
           AND du.role = 'sekolah'
        WHERE s.active = TRUE
          AND UPPER(TRIM(s.status)) = 'NEGERI'
          AND UPPER(COALESCE(TRIM(s.jenjang), '')) NOT IN ('MI', 'MTS')
          AND UPPER(COALESCE(TRIM(s.name), '')) NOT LIKE 'MAN %'
        GROUP BY s.id, s.npsn, s.name, s.jenjang, s.alamat, s.metadata
        ORDER BY s.jenjang, s.name, s.npsn
    """

    with get_cursor() as cur:
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def build_detail_sekolah_markdown(rows: list[dict[str, Any]]) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    lines.append("# Daftar Sekolah")
    lines.append("")
    lines.append(
        "Sumber data: `portal_schools` (alamat + metadata profil) dan `dashboard_users` (email akun sekolah)."
    )
    lines.append(f"Diperbarui pada: {generated_at}")
    lines.append(f"Total sekolah: {len(rows)}")
    lines.append("")
    lines.append(
        "> Filter: `status = NEGERI`, `jenjang bukan MI/MTS`, dan `nama sekolah tidak diawali MAN`."
    )
    lines.append("")
    current_jenjang = None

    for row in rows:
        metadata = _normalize_metadata(row.get("metadata"))
        website = _clean_text(metadata.get("website")) or "-"
        bangku_kosong = _format_empty_seats(metadata)
        sosial_media = _format_social_media(metadata)
        nomor_telepon = _format_phone(metadata)
        email = _format_email(metadata, _clean_text(row.get("school_user_emails")))
        jenjang = _clean_text(row.get("jenjang")) or "LAINNYA"

        if jenjang != current_jenjang:
            current_jenjang = jenjang
            lines.append(f"## Jenjang Sekolah: {current_jenjang}")
            lines.append("")

        school_name = _clean_text(row.get("name")) or "Nama Sekolah Tidak Tersedia"
        lines.append(f"### {school_name}")
        lines.append(f"- NPSN: {_escape_md_cell(row.get('npsn'))}")
        lines.append(f"- Jenjang: {_escape_md_cell(row.get('jenjang'))}")
        lines.append(f"- Alamat: {_escape_md_cell(row.get('alamat'))}")
        lines.append(f"- Bangku Kosong: {_escape_md_cell(bangku_kosong)}")
        lines.append(f"- Website: {_escape_md_cell(website)}")
        lines.append(f"- Sosial Media: {_escape_md_cell(sosial_media)}")
        lines.append(f"- Nomor Telepon: {_escape_md_cell(nomor_telepon)}")
        lines.append(f"- Email: {_escape_md_cell(email)}")
        lines.append("")

    lines.append("")
    return "\n".join(lines)


def export_detail_sekolah_markdown(output_path: str | Path) -> int:
    rows = fetch_school_directory_rows()
    markdown_content = build_detail_sekolah_markdown(rows)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown_content, encoding="utf-8")
    return len(rows)
