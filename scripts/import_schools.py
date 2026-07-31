#!/usr/bin/env python3
"""Script to import new schools from ALL sheets in Excel into the database."""

import os
import sys

# Add the project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd

from dashboard.db_access import get_cursor


def parse_jenjang(name: str) -> str:
    """Extract jenjang from school name. More comprehensive parsing."""
    name_upper = name.upper().strip()
    first_word = name_upper.split()[0] if name_upper.split() else ""

    # TK (Taman Kanak-kanak)
    if first_word in ("TK", "TK-PGRI", "TK.", "TKIT", "KB"):
        return "TK"

    # SD (Sekolah Dasar)
    if first_word in ("SD", "SDN", "SDS", "SDI", "SDIT"):
        return "SD"

    # MI (Madrasah Ibtidaiyah) - Islamic elementary
    if first_word in ("MI", "MIN", "MIS"):
        return "MI"

    # SMP (Sekolah Menengah Pertama)
    if first_word in ("SMP", "SMPN", "SMPS"):
        return "SMP"

    # MTS (Madrasah Tsanawiyah) - Islamic junior high
    if first_word in ("MTS", "MTSN", "MTSS"):
        return "MTS"

    # SMA (Sekolah Menengah Atas)
    if first_word in ("SMA", "SMAN", "SMAS"):
        return "SMA"

    # MA (Madrasah Aliyah) - Islamic senior high
    if first_word in ("MA", "MAN", "MAS", "MANS"):
        return "MA"

    # SMK (Sekolah Menengah Kejuruan)
    if first_word in ("SMK", "SMKN", "SMKS"):
        return "SMK"

    # SLB (Sekolah Luar Biasa) - Special needs
    if first_word in ("SLB", "SLBN", "SLBS"):
        return "SLB"

    return "LAINNYA"


def main():
    # Read ALL sheets from Excel file
    excel_path = ".Data_Sekolah_SudinJU2/update/update_daftar_sekolah.xlsx"
    all_sheets = pd.read_excel(excel_path, sheet_name=None)

    # Skip BERSOLEK sheet (different format)
    sheets_to_import = ["CILINCING", "KOJA", "KLP. GADING"]

    all_schools = []
    for sheet_name in sheets_to_import:
        if sheet_name in all_sheets:
            df = all_sheets[sheet_name]
            print(f"Sheet '{sheet_name}': {len(df)} schools")
            for _, row in df.iterrows():
                all_schools.append(
                    {
                        "npsn": str(row["NPSN"]),
                        "name": row["Nama Satuan Pendidikan"],
                        "status": row.get("Status", "SWASTA"),
                        "alamat": str(row.get("Alamat", "") or ""),
                        "kelurahan": str(row.get("Kelurahan", "") or "")
                        .upper()
                        .strip(),
                        "kecamatan": sheet_name,  # Sheet name is kecamatan
                    }
                )

    print(f"\nTotal schools from Excel: {len(all_schools)}")

    # Get existing NPSN
    with get_cursor() as cur:
        cur.execute("SELECT npsn FROM portal_schools")
        existing_npsn = set(str(row["npsn"]) for row in cur.fetchall())
    print(f"Found {len(existing_npsn)} existing schools in database")

    # Get kelurahan lookup
    with get_cursor() as cur:
        cur.execute("SELECT id, name FROM portal_kelurahan")
        kelurahan_rows = cur.fetchall()
        kelurahan_map = {row["name"].upper(): row["id"] for row in kelurahan_rows}

    # Filter new schools
    new_schools = []
    for s in all_schools:
        if s["npsn"] not in existing_npsn:
            new_schools.append(
                {
                    "npsn": s["npsn"],
                    "name": s["name"],
                    "jenjang": parse_jenjang(s["name"]),
                    "status": s["status"],
                    "alamat": s["alamat"],
                    "kelurahan_id": kelurahan_map.get(s["kelurahan"]),
                }
            )

    print(f"Found {len(new_schools)} new schools to insert")

    # Show jenjang distribution of new schools
    jenjang_count = {}
    for s in new_schools:
        jenjang_count[s["jenjang"]] = jenjang_count.get(s["jenjang"], 0) + 1
    print(f"Jenjang distribution: {jenjang_count}")

    if not new_schools:
        print("No new schools to insert.")
        return

    # Insert new schools one by one with separate transactions
    inserted = 0
    errors = []
    for school in new_schools:
        try:
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    INSERT INTO portal_schools (npsn, name, jenjang, status, alamat, kelurahan_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (npsn) DO NOTHING
                    RETURNING id
                """,
                    (
                        school["npsn"],
                        school["name"],
                        school["jenjang"],
                        school["status"],
                        school["alamat"],
                        school["kelurahan_id"],
                    ),
                )
                result = cur.fetchone()
                if result:
                    inserted += 1
                    print(
                        f"  Inserted: {school['npsn']} - {school['jenjang']} - {school['name'][:50]}"
                    )
        except Exception as e:
            errors.append(f"{school['npsn']}: {e}")

    print(f"\nDone! Inserted {inserted} new schools.")
    if errors:
        print(f"Errors ({len(errors)}):")
        for err in errors[:10]:
            print(f"  {err}")


if __name__ == "__main__":
    main()
