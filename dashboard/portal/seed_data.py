"""
Seed data script for Portal PANBERSS.
Run this script to insert dummy data for testing.

Usage:
    python -m dashboard.portal.seed_data
"""

from __future__ import annotations

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.db_access import get_cursor
from dashboard.schema import ensure_dashboard_schema


def seed_portal_data():
    """Insert dummy data for portal testing."""
    
    # Ensure schema exists
    ensure_dashboard_schema()
    
    # ===== Rooms and Aspects based on PANBERSS Instrument =====
    # Reference: INSTRUMEN PANBERSS (Penilaian Kebersihan Sekolah)
    
    rooms_data = [
        {
            "name": "Pintu Gerbang",
            "description": "Area pintu masuk utama sekolah",
            "category": "umum",
            "sort_order": 1,
            "aspects": ["Cat", "Kondisi", "Kerapian", "Kebersihan"]
        },
        {
            "name": "Pos Satpam",
            "description": "Ruang jaga keamanan",
            "category": "umum",
            "sort_order": 2,
            "aspects": ["Cat", "Kondisi", "Kerapian", "Kebersihan"]
        },
        {
            "name": "Halaman Sekolah",
            "description": "Area halaman dan taman sekolah",
            "category": "umum",
            "sort_order": 3,
            "aspects": ["Kondisi Paving/Aspal", "Kerapian Taman", "Kebersihan", "Drainase"]
        },
        {
            "name": "Ruang Kepala Sekolah",
            "description": "Ruang kerja kepala sekolah",
            "category": "akademik",
            "sort_order": 4,
            "aspects": ["Cat", "Kondisi Lantai", "Kondisi Plafon", "Kebersihan", "Kerapian", "Pencahayaan", "Ventilasi"]
        },
        {
            "name": "Ruang Guru",
            "description": "Ruang kerja guru",
            "category": "akademik",
            "sort_order": 5,
            "aspects": ["Cat", "Kondisi Lantai", "Kondisi Plafon", "Kebersihan", "Kerapian", "Pencahayaan", "Ventilasi"]
        },
        {
            "name": "Ruang Tata Usaha",
            "description": "Ruang administrasi sekolah",
            "category": "akademik",
            "sort_order": 6,
            "aspects": ["Cat", "Kondisi Lantai", "Kondisi Plafon", "Kebersihan", "Kerapian", "Pencahayaan"]
        },
        {
            "name": "Ruang Kelas",
            "description": "Ruang belajar mengajar siswa",
            "category": "akademik",
            "sort_order": 7,
            "aspects": ["Cat Dinding", "Kondisi Lantai", "Kondisi Plafon", "Papan Tulis", "Meja Kursi", "Kebersihan", "Ventilasi", "Pencahayaan"]
        },
        {
            "name": "Perpustakaan",
            "description": "Ruang baca dan koleksi buku",
            "category": "akademik",
            "sort_order": 8,
            "aspects": ["Cat", "Kondisi Lantai", "Kebersihan", "Kerapian Buku", "Pencahayaan", "Ventilasi"]
        },
        {
            "name": "Laboratorium IPA",
            "description": "Laboratorium Ilmu Pengetahuan Alam",
            "category": "akademik",
            "sort_order": 9,
            "aspects": ["Cat", "Kondisi Lantai", "Kebersihan", "Kerapian Alat", "Ventilasi", "Keamanan"]
        },
        {
            "name": "Laboratorium Komputer",
            "description": "Ruang praktik komputer",
            "category": "akademik",
            "sort_order": 10,
            "aspects": ["Cat", "Kondisi Lantai", "Kebersihan", "Kerapian", "AC/Pendingin", "Instalasi Listrik"]
        },
        {
            "name": "Ruang UKS",
            "description": "Unit Kesehatan Sekolah",
            "category": "fasilitas",
            "sort_order": 11,
            "aspects": ["Cat", "Kondisi Lantai", "Kebersihan", "Kelengkapan Obat", "Tempat Tidur", "Ventilasi"]
        },
        {
            "name": "Musholla/Tempat Ibadah",
            "description": "Tempat ibadah di sekolah",
            "category": "fasilitas",
            "sort_order": 12,
            "aspects": ["Cat", "Kondisi Lantai", "Kebersihan", "Kerapian", "Tempat Wudhu", "Ventilasi"]
        },
        {
            "name": "Kantin",
            "description": "Tempat makan dan jajan sekolah",
            "category": "fasilitas",
            "sort_order": 13,
            "aspects": ["Kondisi Bangunan", "Kebersihan", "Penataan", "Tempat Sampah", "Air Bersih"]
        },
        {
            "name": "Toilet Guru",
            "description": "Toilet khusus guru dan staf",
            "category": "sanitasi",
            "sort_order": 14,
            "aspects": ["Kebersihan", "Kondisi Kloset", "Air Bersih", "Ventilasi", "Tempat Cuci Tangan", "Sabun"]
        },
        {
            "name": "Toilet Siswa Laki-laki",
            "description": "Toilet untuk siswa laki-laki",
            "category": "sanitasi",
            "sort_order": 15,
            "aspects": ["Kebersihan", "Kondisi Kloset", "Air Bersih", "Ventilasi", "Tempat Cuci Tangan", "Sabun"]
        },
        {
            "name": "Toilet Siswa Perempuan",
            "description": "Toilet untuk siswa perempuan",
            "category": "sanitasi",
            "sort_order": 16,
            "aspects": ["Kebersihan", "Kondisi Kloset", "Air Bersih", "Ventilasi", "Tempat Cuci Tangan", "Sabun"]
        },
        {
            "name": "Tempat Cuci Tangan",
            "description": "Fasilitas cuci tangan di area sekolah",
            "category": "sanitasi",
            "sort_order": 17,
            "aspects": ["Kebersihan", "Kondisi Kran", "Air Bersih", "Sabun"]
        },
        {
            "name": "Tempat Sampah",
            "description": "Pengelolaan sampah sekolah",
            "category": "sanitasi",
            "sort_order": 18,
            "aspects": ["Pemilahan Sampah", "Kondisi Tempat Sampah", "Kebersihan Area", "TPS/Pengangkutan"]
        },
    ]
    
    with get_cursor(commit=True) as cur:
        # Insert rooms
        print("Inserting rooms and aspects...")
        for room_data in rooms_data:
            # Insert room
            cur.execute(
                """
                INSERT INTO portal_rooms (name, description, category, sort_order)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    sort_order = EXCLUDED.sort_order
                RETURNING id
                """,
                (room_data["name"], room_data["description"], room_data["category"], room_data["sort_order"])
            )
            room_id = cur.fetchone()[0]
            print(f"  Room: {room_data['name']} (ID: {room_id})")
            
            # Insert aspects
            for idx, aspect_name in enumerate(room_data["aspects"], 1):
                cur.execute(
                    """
                    INSERT INTO portal_aspects (room_id, name, sort_order)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (room_id, name) DO UPDATE SET sort_order = EXCLUDED.sort_order
                    """,
                    (room_id, aspect_name, idx)
                )
        
        # Insert test school: SDN Semper Barat 01
        print("\nInserting test school: SDN Semper Barat 01...")
        cur.execute(
            """
            INSERT INTO portal_schools (npsn, name, jenjang, alamat, kelurahan, kecamatan)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (npsn) DO UPDATE SET
                name = EXCLUDED.name,
                alamat = EXCLUDED.alamat,
                kelurahan = EXCLUDED.kelurahan,
                kecamatan = EXCLUDED.kecamatan
            RETURNING id
            """,
            ("20104001", "SDN Semper Barat 01", "SD", "Jl. Semper Barat Raya No. 1", "Semper Barat", "Cilincing")
        )
        school_id = cur.fetchone()[0]
        print(f"  School ID: {school_id}")
        
        # Assign all rooms to this school
        print("\nAssigning rooms to school...")
        cur.execute("SELECT id FROM portal_rooms WHERE active = TRUE ORDER BY sort_order")
        room_ids = [row[0] for row in cur.fetchall()]
        
        for room_id in room_ids:
            cur.execute(
                """
                INSERT INTO portal_school_rooms (school_id, room_id)
                VALUES (%s, %s)
                ON CONFLICT (school_id, room_id) DO NOTHING
                """,
                (school_id, room_id)
            )
        print(f"  Assigned {len(room_ids)} rooms to school")
        
        print("\n✅ Seed data inserted successfully!")
        print(f"   - {len(rooms_data)} rooms")
        print(f"   - {sum(len(r['aspects']) for r in rooms_data)} aspects")
        print(f"   - 1 test school (SDN Semper Barat 01)")


if __name__ == "__main__":
    seed_portal_data()
