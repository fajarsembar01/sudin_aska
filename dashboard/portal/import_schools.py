"""
Import schools data from Excel file.
Run: python -m dashboard.portal.import_schools
"""

from __future__ import annotations

import os
import re
import sys

# Add parent directory to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import pandas as pd

from dashboard.db_access import get_cursor
from dashboard.schema import ensure_dashboard_schema

# Mapping sheet names to kecamatan names
SHEET_KECAMATAN_MAP = {
    "CILINCING": "CILINCING",
    "KOJA": "KOJA",
    "KLP. GADING": "KELAPA GADING",
}


def detect_jenjang(name: str) -> str:
    """Detect jenjang (education level) from school name."""
    name_upper = name.upper()

    if re.search(r"\b(MTSN|MTSS|MTS)\b", name_upper):
        return "MTS"
    if re.search(r"\b(MIN|MIS|MI)\b", name_upper):
        return "MI"
    if re.search(r"\b(MAN|MAS|MA)\b", name_upper):
        return "MA"
    if re.search(r"\b(SMAN|SMAS|SMA|SMKN|SMKS|SMK)\b", name_upper):
        return "SMA"
    if re.search(r"\b(SMPN|SMPS|SMP)\b", name_upper):
        return "SMP"
    if re.search(r"\b(SDN|SDS|SD)\b", name_upper):
        return "SD"
    if re.search(r"\bTK\b", name_upper):
        return "TK"

    return "SD"


def seed_kecamatan():
    """Insert kecamatan data."""
    kecamatan_data = [
        ("CILINCING", "CLC"),
        ("KOJA", "KOJ"),
        ("KELAPA GADING", "KPG"),
    ]

    with get_cursor(commit=True) as cur:
        for name, code in kecamatan_data:
            cur.execute(
                """
                INSERT INTO portal_kecamatan (name, code)
                VALUES (%s, %s)
                ON CONFLICT (name) DO UPDATE SET code = EXCLUDED.code
                RETURNING id
                """,
                (name, code),
            )
        print(f"✅ Seeded {len(kecamatan_data)} kecamatan records")


def get_kecamatan_id_map() -> dict:
    """Get mapping of kecamatan name to id."""
    with get_cursor() as cur:
        cur.execute("SELECT id, name FROM portal_kecamatan")
        return {row["name"]: row["id"] for row in cur.fetchall()}


def seed_kelurahan_from_excel(excel_path: str, kecamatan_map: dict) -> dict:
    """Parse unique kelurahan per kecamatan from Excel and insert."""
    kelurahan_data = {}  # {kecamatan_id: [(kelurahan_name, ...)]}

    for sheet_name, kecamatan_name in SHEET_KECAMATAN_MAP.items():
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        except Exception as e:
            print(f"  ❌ Error reading sheet {sheet_name}: {e}")
            continue

        kecamatan_id = kecamatan_map.get(kecamatan_name)
        if not kecamatan_id:
            continue

        if kecamatan_id not in kelurahan_data:
            kelurahan_data[kecamatan_id] = set()

        for kel in df["Kelurahan"].dropna().unique():
            kel_clean = str(kel).strip()
            if kel_clean and kel_clean != "nan":
                kelurahan_data[kecamatan_id].add(kel_clean)

    # Insert kelurahan records
    kelurahan_id_map = {}  # {(kecamatan_id, kelurahan_name): kelurahan_id}

    with get_cursor(commit=True) as cur:
        total = 0
        for kecamatan_id, kelurahan_names in kelurahan_data.items():
            for kel_name in kelurahan_names:
                cur.execute(
                    """
                    INSERT INTO portal_kelurahan (kecamatan_id, name)
                    VALUES (%s, %s)
                    ON CONFLICT (kecamatan_id, name) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    (kecamatan_id, kel_name),
                )
                kelurahan_id_map[(kecamatan_id, kel_name)] = cur.fetchone()["id"]
                total += 1
        print(f"✅ Seeded {total} kelurahan records")

    return kelurahan_id_map


def clear_schools():
    """Delete all existing schools for fresh import."""
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM portal_schools")
        print("🗑️  Cleared existing schools")


def import_schools_from_excel():
    """Import schools from Excel file."""
    excel_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "contoh",
        "DAFTAR SEKOLAH NEGERI & SWASTA DI JAKARTA UTARA II.xlsx",
    )

    if not os.path.exists(excel_path):
        print(f"❌ File not found: {excel_path}")
        return

    print(f"📖 Reading Excel file: {excel_path}")

    # Seed kecamatan first
    seed_kecamatan()
    kecamatan_map = get_kecamatan_id_map()

    # Seed kelurahan from Excel data
    kelurahan_id_map = seed_kelurahan_from_excel(excel_path, kecamatan_map)

    # Clear existing schools for fresh import
    clear_schools()

    total_inserted = 0

    with get_cursor(commit=True) as cur:
        for sheet_name, kecamatan_name in SHEET_KECAMATAN_MAP.items():
            print(f"\n📋 Processing sheet: {sheet_name} -> {kecamatan_name}")

            try:
                df = pd.read_excel(excel_path, sheet_name=sheet_name)
            except Exception as e:
                print(f"  ❌ Error reading sheet: {e}")
                continue

            kecamatan_id = kecamatan_map.get(kecamatan_name)
            if not kecamatan_id:
                print(f"  ❌ Kecamatan not found: {kecamatan_name}")
                continue

            for idx, row in df.iterrows():
                npsn = str(row.get("NPSN", "")).strip()
                name = str(row.get("Nama Satuan Pendidikan", "")).strip()
                alamat = str(row.get("Alamat", "")).strip() or None
                kelurahan_text = str(row.get("Kelurahan", "")).strip() or None
                status = str(row.get("Status", "NEGERI")).strip().upper()

                if not npsn or not name or npsn == "nan" or name == "nan":
                    continue

                # Detect jenjang from school name
                jenjang = detect_jenjang(name)

                # Normalize status
                if status not in ("NEGERI", "SWASTA"):
                    status = "NEGERI" if "NEGERI" in status.upper() else "SWASTA"

                # Get kelurahan_id from map
                kelurahan_id = (
                    kelurahan_id_map.get((kecamatan_id, kelurahan_text))
                    if kelurahan_text
                    else None
                )

                # Insert school
                cur.execute(
                    """
                    INSERT INTO portal_schools 
                        (npsn, name, jenjang, alamat, kelurahan_id, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (npsn) DO UPDATE SET
                        name = EXCLUDED.name,
                        jenjang = EXCLUDED.jenjang,
                        alamat = EXCLUDED.alamat,
                        kelurahan_id = EXCLUDED.kelurahan_id,
                        status = EXCLUDED.status,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (npsn, name, jenjang, alamat, kelurahan_id, status),
                )
                total_inserted += 1

            print(f"  ✅ Processed {len(df)} rows from {sheet_name}")

    print(f"\n✅ Import complete!")
    print(f"   - Total schools: {total_inserted}")


if __name__ == "__main__":
    # Ensure schema exists
    ensure_dashboard_schema()

    print("🚀 Starting school data import...")
    import_schools_from_excel()
