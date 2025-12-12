"""
Generate an idempotent SQL import script for portal_kecamatan -> portal_kelurahan
-> portal_schools using the bundled Excel master data.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

# Map Excel sheet names to their kecamatan names
SHEET_KECAMATAN_MAP = {
    "CILINCING": "CILINCING",
    "KOJA": "KOJA",
    "KLP. GADING": "KELAPA GADING",
}

BASE_DIR = Path(__file__).resolve().parents[2]
EXCEL_PATH = BASE_DIR / "contoh" / "DAFTAR SEKOLAH NEGERI & SWASTA DI JAKARTA UTARA II.xlsx"
OUTPUT_PATH = BASE_DIR / "contoh" / "portal_school_import.sql"

# Optional short codes for kecamatan (used only for metadata)
KECAMATAN_CODES = {
    "CILINCING": "CLC",
    "KOJA": "KOJ",
    "KELAPA GADING": "KPG",
}


def detect_jenjang(name: str) -> str:
    """Detect jenjang (education level) from school name."""
    upper = name.upper()
    if any(tag in upper for tag in ("MTSN", "MTSS", "MTS")):
        return "MTS"
    if any(tag in upper for tag in ("MIN", "MIS", "MI")):
        return "MI"
    if any(tag in upper for tag in ("MAN", "MAS", "MA")):
        return "MA"
    if any(tag in upper for tag in ("SMAN", "SMAS", "SMA", "SMKN", "SMKS", "SMK")):
        return "SMA"
    if any(tag in upper for tag in ("SMPN", "SMPS", "SMP")):
        return "SMP"
    if any(tag in upper for tag in ("SDN", "SDS", "SD")):
        return "SD"
    if "TK" in upper:
        return "TK"
    return "SD"


def normalize_npsn(value) -> str | None:
    """Return NPSN as zero-padded string or None when missing/invalid."""
    if pd.isna(value):
        return None

    # Numeric inputs from Excel often come as float/int
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return str(value).zfill(8)

    raw = str(value).strip()
    if not raw or raw.lower() == "nan":
        return None

    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]

    if raw.isdigit() and len(raw) < 8:
        raw = raw.zfill(8)

    return raw


def sql_literal(value: str | None) -> str:
    """Render a Python value as SQL literal."""
    if value is None:
        return "NULL"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def load_master_data() -> Tuple[Dict[str, List[str]], List[Dict[str, str]]]:
    """Read Excel and return kelurahan per kecamatan + cleaned school rows."""
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"Excel source not found at {EXCEL_PATH}")

    kelurahan_map: Dict[str, set] = {kecamatan: set() for kecamatan in SHEET_KECAMATAN_MAP.values()}
    schools_by_npsn: Dict[str, Dict[str, str]] = {}

    for sheet_name, kecamatan_name in SHEET_KECAMATAN_MAP.items():
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)
        for _, row in df.iterrows():
            npsn = normalize_npsn(row.get("NPSN"))
            name_raw = row.get("Nama Satuan Pendidikan")
            name = str(name_raw).strip() if pd.notna(name_raw) else None

            if not npsn or not name:
                continue

            alamat_raw = row.get("Alamat")
            alamat = str(alamat_raw).strip() if pd.notna(alamat_raw) else None

            kel_raw = row.get("Kelurahan")
            kelurahan = str(kel_raw).strip() if pd.notna(kel_raw) else None

            status_raw = row.get("Status", "NEGERI")
            status = str(status_raw).strip().upper() or "NEGERI"
            if status not in ("NEGERI", "SWASTA"):
                status = "NEGERI" if "NEGERI" in status else "SWASTA"

            jenjang = detect_jenjang(name)

            if kelurahan:
                kelurahan_map[kecamatan_name].add(kelurahan)

            schools_by_npsn[npsn] = {
                "npsn": npsn,
                "name": name,
                "jenjang": jenjang,
                "alamat": alamat,
                "kelurahan": kelurahan or "",
                "kecamatan": kecamatan_name,
                "status": status,
            }

    kelurahan_sorted = {k: sorted(list(v)) for k, v in kelurahan_map.items()}
    school_rows = list(schools_by_npsn.values())
    return kelurahan_sorted, school_rows


def build_schema_sql() -> str:
    """Return SQL DDL for required tables and indexes."""
    return """
-- Schema (idempotent)
CREATE TABLE IF NOT EXISTS portal_kecamatan (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portal_kelurahan (
    id SERIAL PRIMARY KEY,
    kecamatan_id INTEGER NOT NULL REFERENCES portal_kecamatan(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kecamatan_id, name)
);

CREATE TABLE IF NOT EXISTS portal_schools (
    id SERIAL PRIMARY KEY,
    npsn TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    jenjang TEXT NOT NULL DEFAULT 'SD',
    alamat TEXT,
    user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
    metadata JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'NEGERI',
    kelurahan_id INTEGER REFERENCES portal_kelurahan(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_portal_kecamatan_name ON portal_kecamatan (name);
CREATE INDEX IF NOT EXISTS idx_portal_kelurahan_kecamatan ON portal_kelurahan (kecamatan_id);
CREATE INDEX IF NOT EXISTS idx_portal_schools_npsn ON portal_schools (npsn);
""".strip()


def build_kecamatan_sql() -> Iterable[str]:
    """Yield INSERT statements for kecamatan."""
    seen = set()
    for name in SHEET_KECAMATAN_MAP.values():
        if name in seen:
            continue
        seen.add(name)
        code = KECAMATAN_CODES.get(name)
        yield (
            "INSERT INTO portal_kecamatan (name, code) "
            f"VALUES ({sql_literal(name)}, {sql_literal(code)}) "
            "ON CONFLICT (name) DO UPDATE SET code = EXCLUDED.code;"
        )


def build_kelurahan_sql(kelurahan_map: Dict[str, List[str]]) -> Iterable[str]:
    """Yield INSERT statements for kelurahan with FK to kecamatan."""
    for kecamatan, kel_list in kelurahan_map.items():
        for kel_name in kel_list:
            yield (
                "INSERT INTO portal_kelurahan (kecamatan_id, name, code)\n"
                f"SELECT k.id, {sql_literal(kel_name)}, NULL\n"
                "FROM portal_kecamatan k\n"
                f"WHERE k.name = {sql_literal(kecamatan)}\n"
                "ON CONFLICT (kecamatan_id, name) DO UPDATE SET code = EXCLUDED.code;"
            )


def build_school_sql(school_rows: List[Dict[str, str]]) -> Iterable[str]:
    """Yield INSERT ... SELECT statements for portal_schools."""
    for row in sorted(school_rows, key=lambda r: (r["kecamatan"], r["kelurahan"], r["name"])):
        yield (
            "INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan_id, status, active, updated_at)\n"
            f"SELECT {sql_literal(row['npsn'])}, {sql_literal(row['name'])}, "
            f"{sql_literal(row['jenjang'])}, {sql_literal(row['alamat'])}, "
            "l.id, "
            f"{sql_literal(row['status'])}, TRUE, NOW()\n"
            "FROM portal_kelurahan l\n"
            "JOIN portal_kecamatan k ON k.id = l.kecamatan_id\n"
            f"WHERE l.name = {sql_literal(row['kelurahan'])} AND k.name = {sql_literal(row['kecamatan'])}\n"
            "ON CONFLICT (npsn) DO UPDATE SET\n"
            "  name = EXCLUDED.name,\n"
            "  jenjang = EXCLUDED.jenjang,\n"
            "  alamat = EXCLUDED.alamat,\n"
            "  kelurahan_id = EXCLUDED.kelurahan_id,\n"
            "  status = EXCLUDED.status,\n"
            "  updated_at = NOW();"
        )


def build_sql_file(kelurahan_map: Dict[str, List[str]], school_rows: List[Dict[str, str]]) -> str:
    """Assemble the final SQL script."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = [
        "-- Portal school + kelurahan/kecamatan import",
        f"-- Source file : {EXCEL_PATH.name}",
        f"-- Generated   : {now}",
        f"-- Total       : {len(school_rows)} schools, {sum(len(v) for v in kelurahan_map.values())} kelurahan, {len(set(SHEET_KECAMATAN_MAP.values()))} kecamatan",
        "-- Safe to re-run: uses ON CONFLICT upserts; existing rows are updated, missing rows stay untouched.",
        "",
        "BEGIN;",
        build_schema_sql(),
        "",
        "-- Kecamatan",
        *build_kecamatan_sql(),
        "",
        "-- Kelurahan (linked to kecamatan by name)",
        *build_kelurahan_sql(kelurahan_map),
        "",
        "-- Schools (linked via kelurahan -> kecamatan)",
        *build_school_sql(school_rows),
        "COMMIT;",
        "",
    ]
    return "\n".join(header)


def main() -> None:
    kelurahan_map, school_rows = load_master_data()
    sql_blob = build_sql_file(kelurahan_map, school_rows)
    OUTPUT_PATH.write_text(sql_blob, encoding="utf-8")
    print(f"SQL written to {OUTPUT_PATH}")
    print(f"Schools   : {len(school_rows)}")
    print(f"Kelurahan : {sum(len(v) for v in kelurahan_map.values())}")
    print(f"Kecamatan : {len(set(SHEET_KECAMATAN_MAP.values()))}")


if __name__ == "__main__":
    main()
