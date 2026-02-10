#!/usr/bin/env python3
"""Generate kecerdasan/Detail_Sekolah.md from portal_schools data.

Default filters:
- status = NEGERI
- jenjang NOT IN {MI, MTS, MAN, MA}
- active_only = True

Usage:
  python scripts/generate_detail_sekolah_md.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
dashboard_path = ROOT / "dashboard"
if str(dashboard_path) not in sys.path:
    sys.path.insert(0, str(dashboard_path))

from db_access import get_cursor

DEFAULT_EXCLUDE_JENJANG = {"MI", "MTS", "MAN", "MA"}
DEFAULT_STATUS = "NEGERI"


def _normalize_meta(meta: Any) -> Dict[str, Any]:
    if not meta:
        return {}
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, list):
        merged: Dict[str, Any] = {}
        for item in meta:
            if isinstance(item, dict):
                merged.update(item)
        return merged
    if isinstance(meta, str):
        try:
            parsed = json.loads(meta)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _format_social(meta: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key, label in (
        ("instagram", "Instagram"),
        ("tiktok", "TikTok"),
        ("youtube", "YouTube"),
        ("telegram", "Telegram"),
        ("wa_channel", "WhatsApp Channel"),
    ):
        value = (meta.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    return " | ".join(parts) if parts else "Belum tersedia"


def _format_phone(meta: Dict[str, Any]) -> str:
    school_phone = (meta.get("school_phone") or "").strip()
    coordinator_phone = (meta.get("coordinator_phone") or "").strip()
    parts: List[str] = []
    if school_phone:
        parts.append(f"Sekolah: {school_phone}")
    if coordinator_phone and coordinator_phone != school_phone:
        parts.append(f"Operator: {coordinator_phone}")
    return " | ".join(parts) if parts else "Belum tersedia"


def _format_empty_seats(meta: Dict[str, Any]) -> str:
    empty_total = meta.get("empty_seats")
    empty_by_grade = meta.get("empty_seats_by_grade") or {}
    if isinstance(empty_by_grade, str):
        try:
            empty_by_grade = json.loads(empty_by_grade)
        except Exception:
            empty_by_grade = {}
    if not isinstance(empty_by_grade, dict):
        empty_by_grade = {}

    def _to_int(val: Any) -> Optional[int]:
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    if empty_total is None:
        values = [_to_int(v) for v in empty_by_grade.values()]
        values = [v for v in values if v is not None]
        if values:
            empty_total = sum(values)

    per_grade = ""
    if empty_by_grade:
        items: List[Tuple[int, Any]] = []
        non_numeric: List[Tuple[str, Any]] = []
        for k, v in empty_by_grade.items():
            try:
                items.append((int(k), v))
            except (TypeError, ValueError):
                non_numeric.append((str(k), v))
        items.sort(key=lambda x: x[0])
        non_numeric.sort(key=lambda x: x[0])
        formatted = [f"{k}: {v}" for k, v in items] + [f"{k}: {v}" for k, v in non_numeric]
        per_grade = ", ".join(formatted)

    if empty_total is None and not per_grade:
        return "Belum tersedia"
    if empty_total is None:
        return f"Per kelas: {per_grade}"
    if per_grade:
        return f"{empty_total} (Per kelas: {per_grade})"
    return str(empty_total)


def _clean_value(value: Any) -> str:
    clean = (value or "").strip()
    return clean if clean else "Belum tersedia"


def fetch_schools(
    *,
    status: str,
    exclude_jenjang: Iterable[str],
    active_only: bool = True,
) -> List[Dict[str, Any]]:
    exclude = {j.upper().strip() for j in exclude_jenjang if j}
    exclude_clause = ""
    params: List[Any] = [status]
    if exclude:
        placeholders = ", ".join(["%s"] * len(exclude))
        exclude_clause = f"AND UPPER(s.jenjang) NOT IN ({placeholders})"
        params.extend(sorted(exclude))

    active_clause = "AND s.active = TRUE" if active_only else ""

    query = f"""
        SELECT s.npsn, s.name, s.jenjang, s.alamat, s.status, s.metadata
        FROM portal_schools s
        WHERE s.status = %s
        {active_clause}
        {exclude_clause}
        ORDER BY s.jenjang, s.name
    """
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def build_markdown(schools: List[Dict[str, Any]]) -> str:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in schools:
        grouped[(row.get("jenjang") or "-").strip()].append(row)

    preferred_order = ["PAUD", "TK", "SD", "SMP", "SMA", "SMK", "SLB", "LAINNYA"]

    def _jenjang_sort_key(value: str) -> Tuple[int, int, str]:
        if value in preferred_order:
            return (0, preferred_order.index(value), value)
        return (1, 999, value)

    lines: List[str] = ["# Daftar Sekolah JU(Jakarta Utara) 2"]

    for jenjang in sorted(grouped.keys(), key=_jenjang_sort_key):
        lines.append("")
        lines.append(f"## {jenjang}")
        for school in grouped[jenjang]:
            name = (school.get("name") or "").strip() or "(Nama belum tersedia)"
            meta = _normalize_meta(school.get("metadata"))
            lines.append("")
            lines.append(f"### {name}")
            lines.append(f"- **NPSN**: {_clean_value(school.get('npsn'))}")
            lines.append(f"- **Alamat**: {_clean_value(school.get('alamat'))}")
            lines.append(f"- **Website**: {_clean_value(meta.get('website'))}")
            lines.append(f"- **Sosial Media**: {_format_social(meta)}")
            lines.append(f"- **Nomor Telepon**: {_format_phone(meta)}")
            lines.append(f"- **Email**: {_clean_value(meta.get('cs_email') or meta.get('email'))}")
            lines.append(f"- **Bangku Kosong**: {_format_empty_seats(meta)}")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Detail_Sekolah.md from portal_schools")
    parser.add_argument(
        "--output",
        default="kecerdasan/Detail_Sekolah.md",
        help="Output markdown path",
    )
    parser.add_argument(
        "--status",
        default=DEFAULT_STATUS,
        help="School status filter (default: NEGERI)",
    )
    parser.add_argument(
        "--exclude-jenjang",
        default=",".join(sorted(DEFAULT_EXCLUDE_JENJANG)),
        help="Comma-separated jenjang to exclude (default: MI,MTS,MAN,MA)",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include inactive schools",
    )
    args = parser.parse_args()

    exclude = [j.strip() for j in args.exclude_jenjang.split(",") if j.strip()]
    schools = fetch_schools(
        status=args.status,
        exclude_jenjang=exclude,
        active_only=not args.include_inactive,
    )
    content = build_markdown(schools)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
