"""Query helpers for Daftar Tamu dashboard."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from dashboard.db_access import get_cursor


SORT_OPTIONS = {
    "visits_desc": "visit_count DESC, last_visit_date DESC NULLS LAST, school_name ASC",
    "visits_asc": "visit_count ASC, last_visit_date DESC NULLS LAST, school_name ASC",
    "last_visit_desc": "last_visit_date DESC NULLS LAST, visit_count DESC, school_name ASC",
    "last_visit_asc": "last_visit_date ASC NULLS FIRST, visit_count DESC, school_name ASC",
    "name_asc": "school_name ASC",
    "name_desc": "school_name DESC",
}

DEFAULT_SORT = "visits_desc"

_ROLLUP_CTE = """
WITH filtered_visits AS (
    SELECT v.*
    FROM daftar_tamu_visits v
    WHERE (%s::date IS NULL OR v.visit_date >= %s::date)
      AND (%s::date IS NULL OR v.visit_date <= %s::date)
),
school_rollup AS (
    SELECT
        s.id AS school_id,
        s.npsn,
        s.name AS school_name,
        s.jenjang,
        s.kecamatan,
        s.kelurahan,
        s.alamat,
        COALESCE(s.latitude, latest.latitude) AS latitude,
        COALESCE(s.longitude, latest.longitude) AS longitude,
        COUNT(fv.id) AS visit_count,
        MAX(fv.visit_date) AS last_visit_date,
        latest.guest_name AS last_guest_name,
        latest.guest_institution AS last_guest_institution,
        latest.photo_path AS last_photo_path
    FROM daftar_tamu_schools s
    LEFT JOIN filtered_visits fv ON fv.school_id = s.id
    LEFT JOIN LATERAL (
        SELECT
            fv2.guest_name,
            fv2.guest_institution,
            fv2.photo_path,
            fv2.latitude,
            fv2.longitude
        FROM filtered_visits fv2
        WHERE fv2.school_id = s.id
        ORDER BY fv2.visit_date DESC, fv2.id DESC
        LIMIT 1
    ) latest ON TRUE
    WHERE s.active = TRUE
    GROUP BY
        s.id,
        s.npsn,
        s.name,
        s.jenjang,
        s.kecamatan,
        s.kelurahan,
        s.alamat,
        s.latitude,
        s.longitude,
        latest.guest_name,
        latest.guest_institution,
        latest.photo_path,
        latest.latitude,
        latest.longitude
)
"""


def _build_search(search_query: Optional[str]) -> tuple[str, str]:
    query = (search_query or "").strip()
    return query, f"%{query}%"


def ensure_daftar_tamu_seed_data() -> None:
    """Insert dummy schools and visits when daftar tamu tables are empty."""
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT COUNT(*) AS total FROM daftar_tamu_schools")
        total_schools = int(cur.fetchone()["total"] or 0)
        if total_schools > 0:
            return

        schools = [
            ("317102001", "SDN Tugu Utara 01", "SD", "Jl. Sungai Tiram No. 15", "Koja", "Tugu Utara", -6.122195, 106.907911),
            ("317102002", "SDN Lagoa 05", "SD", "Jl. Laksda Yos Sudarso No. 20", "Koja", "Lagoa", -6.116012, 106.901732),
            ("317102003", "SMPN 174 Jakarta", "SMP", "Jl. Walang Baru No. 8", "Koja", "Waru", -6.113342, 106.912110),
            ("317103001", "SDN Rorotan 03", "SD", "Jl. Rorotan V No. 11", "Cilincing", "Rorotan", -6.100791, 106.953943),
            ("317103002", "SMPN 289 Jakarta", "SMP", "Jl. Cakung Drain No. 45", "Cilincing", "Semper Timur", -6.107951, 106.932455),
            ("317103003", "SMKN 36 Jakarta", "SMK", "Jl. Semper Barat Raya No. 65", "Cilincing", "Semper Barat", -6.120341, 106.928444),
            ("317104001", "SDN Pegangsaan Dua 04", "SD", "Jl. Kelapa Nias Raya Blok NA", "Kelapa Gading", "Pegangsaan Dua", -6.162901, 106.905511),
            ("317104002", "SMPN 123 Jakarta", "SMP", "Jl. Boulevard Raya No. 22", "Kelapa Gading", "Kelapa Gading Timur", -6.156880, 106.903212),
            ("317104003", "SMAN 13 Jakarta", "SMA", "Jl. Kelapa Cengkir No. 10", "Kelapa Gading", "Kelapa Gading Barat", -6.157221, 106.892845),
            ("317105001", "SDN Sunter Agung 09", "SD", "Jl. Danau Sunter Utara No. 5", "Tanjung Priok", "Sunter Agung", -6.140891, 106.872332),
            ("317105002", "SMPN 30 Jakarta", "SMP", "Jl. Warakas VII No. 12", "Tanjung Priok", "Warakas", -6.128341, 106.885299),
            ("317105003", "SMKN 55 Jakarta", "SMK", "Jl. Yos Sudarso Km 18", "Tanjung Priok", "Kebon Bawang", -6.123500, 106.889377),
        ]

        for school in schools:
            cur.execute(
                """
                INSERT INTO daftar_tamu_schools
                    (npsn, name, jenjang, alamat, kecamatan, kelurahan, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                school,
            )

        cur.execute("SELECT id, npsn, latitude, longitude FROM daftar_tamu_schools")
        school_map = {row["npsn"]: dict(row) for row in cur.fetchall()}

        cur.execute("SELECT id FROM dashboard_users WHERE role = 'admin' ORDER BY id LIMIT 1")
        admin_row = cur.fetchone()
        created_by = admin_row["id"] if admin_row else None

        visits = [
            ("317102001", date(2026, 2, 1), "Tim Sudin Pendidikan JU2", "Rahmat Hidayat", "Monitoring kebersihan area kelas", "Kunjungan rutin awal bulan."),
            ("317102001", date(2025, 12, 19), "Inspektorat Wilayah", "Nisa Purnama", "Verifikasi tindak lanjut aduan", "Perlu follow-up dokumen."),
            ("317102002", date(2026, 1, 28), "Tim Sudin Pendidikan JU2", "Siti Aisyah", "Pembinaan UKS", "Dokumentasi lengkap."),
            ("317102003", date(2025, 10, 5), "Lembaga Mitra Pendidikan", "Arif Prabowo", "Sosialisasi program literasi", "Belum ada kunjungan lanjutan."),
            ("317103001", date(2026, 1, 15), "Tim Sudin Pendidikan JU2", "Dewi Sartika", "Evaluasi kesiapan PPDB", "Perlu cek ruang kelas tambahan."),
            ("317103002", date(2025, 11, 23), "Dinas Kesehatan", "Yuni Kartika", "Pemeriksaan sanitasi sekolah", "Skor sanitasi cukup baik."),
            ("317103002", date(2026, 1, 5), "Tim Sudin Pendidikan JU2", "M. Irfan", "Pendampingan administrasi sekolah", "Butuh pelatihan operator."),
            ("317103003", date(2025, 12, 8), "Tim Sudin Pendidikan JU2", "Nur Aini", "Monitoring fasilitas laboratorium", "Perlu pengadaan alat praktikum."),
            ("317104001", date(2026, 1, 10), "Lembaga Akreditasi Sekolah", "Herman Saputra", "Validasi kesiapan akreditasi", "Data pendukung sudah lengkap."),
            ("317104001", date(2025, 9, 30), "Tim Sudin Pendidikan JU2", "Siti Rahma", "Monitoring mutu pembelajaran", "Rencana kunjungan ulang triwulan I."),
            ("317104002", date(2026, 1, 30), "Tim Sudin Pendidikan JU2", "Budi Santoso", "Pendampingan sarpras", "Perlu catatan plafon ruang guru."),
            ("317104003", date(2025, 8, 14), "Kejaksaan Negeri", "Lani Kusuma", "Sosialisasi anti korupsi", "Selesai tepat waktu."),
            ("317105001", date(2026, 2, 3), "Tim Sudin Pendidikan JU2", "Rizki Maulana", "Pemantauan kesiapan ujian", "Kondisi sekolah sangat siap."),
            ("317105001", date(2025, 11, 1), "Dinas Lingkungan Hidup", "Prita Melati", "Evaluasi bank sampah sekolah", "Diusulkan program lanjutan."),
            ("317105002", date(2025, 12, 27), "Tim Sudin Pendidikan JU2", "Anita Wulandari", "Pembinaan manajemen sekolah", "Perlu monitoring 60 hari."),
            ("317105002", date(2026, 1, 18), "BPKD DKI", "Farhan Akbar", "Monitoring administrasi BOS", "Dokumen lengkap."),
        ]

        for npsn, visit_date, institution, guest_name, purpose, notes in visits:
            school = school_map.get(npsn)
            if not school:
                continue
            latitude = float(school["latitude"]) if school.get("latitude") is not None else None
            longitude = float(school["longitude"]) if school.get("longitude") is not None else None
            cur.execute(
                """
                INSERT INTO daftar_tamu_visits (
                    school_id,
                    visit_date,
                    guest_name,
                    guest_institution,
                    purpose,
                    notes,
                    photo_path,
                    latitude,
                    longitude,
                    created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    school["id"],
                    visit_date,
                    guest_name,
                    institution,
                    purpose,
                    notes,
                    "/static/logo/logo.png",
                    latitude,
                    longitude,
                    created_by,
                ),
            )


def fetch_dashboard_summary(date_from: Optional[date] = None, date_to: Optional[date] = None) -> Dict[str, Any]:
    """Fetch top-level summary stats for admin dashboard."""
    cutoff = date.today() - timedelta(days=30)
    params: List[Any] = [date_from, date_from, date_to, date_to, cutoff]
    query = (
        _ROLLUP_CTE
        + """
    SELECT
        (SELECT COUNT(*) FROM school_rollup) AS total_schools,
        (SELECT COALESCE(SUM(visit_count), 0) FROM school_rollup) AS total_visits,
        (SELECT COUNT(*) FROM school_rollup WHERE visit_count > 0) AS visited_schools,
        (SELECT COUNT(*) FROM school_rollup WHERE visit_count = 0) AS unvisited_schools,
        (SELECT COUNT(*) FROM school_rollup WHERE visit_count = 0 OR last_visit_date < %s::date) AS attention_schools,
        (SELECT MAX(last_visit_date) FROM school_rollup) AS latest_visit_date,
        (SELECT COUNT(*) FROM filtered_visits
            WHERE visit_date >= date_trunc('month', CURRENT_DATE)::date) AS visits_this_month
    """
    )

    with get_cursor() as cur:
        cur.execute(query, params)
        row = dict(cur.fetchone() or {})

    return {
        "total_schools": int(row.get("total_schools") or 0),
        "total_visits": int(row.get("total_visits") or 0),
        "visited_schools": int(row.get("visited_schools") or 0),
        "unvisited_schools": int(row.get("unvisited_schools") or 0),
        "attention_schools": int(row.get("attention_schools") or 0),
        "latest_visit_date": row.get("latest_visit_date"),
        "visits_this_month": int(row.get("visits_this_month") or 0),
    }


def fetch_school_rankings(
    *,
    page: int = 1,
    per_page: int = 10,
    sort_key: str = DEFAULT_SORT,
    search_query: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch school rankings with search, sorting, and pagination."""
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 500))
    offset = (safe_page - 1) * safe_per_page

    safe_sort = sort_key if sort_key in SORT_OPTIONS else DEFAULT_SORT
    order_sql = SORT_OPTIONS[safe_sort]
    query_text, like_query = _build_search(search_query)

    base_params: List[Any] = [date_from, date_from, date_to, date_to]
    search_params: List[Any] = [query_text, like_query, like_query, like_query, like_query]

    count_query = (
        _ROLLUP_CTE
        + """
    SELECT COUNT(*) AS total
    FROM school_rollup
    WHERE (
        %s = ''
        OR school_name ILIKE %s
        OR npsn ILIKE %s
        OR COALESCE(kecamatan, '') ILIKE %s
        OR COALESCE(kelurahan, '') ILIKE %s
    )
    """
    )

    data_query = (
        _ROLLUP_CTE
        + f"""
    SELECT
        school_id,
        npsn,
        school_name,
        jenjang,
        kecamatan,
        kelurahan,
        alamat,
        latitude,
        longitude,
        visit_count,
        last_visit_date,
        last_guest_name,
        last_guest_institution,
        last_photo_path
    FROM school_rollup
    WHERE (
        %s = ''
        OR school_name ILIKE %s
        OR npsn ILIKE %s
        OR COALESCE(kecamatan, '') ILIKE %s
        OR COALESCE(kelurahan, '') ILIKE %s
    )
    ORDER BY {order_sql}
    LIMIT %s OFFSET %s
    """
    )

    with get_cursor() as cur:
        cur.execute(count_query, base_params + search_params)
        count_row = cur.fetchone()
        total_rows = int(dict(count_row).get("total") or 0) if count_row else 0

        cur.execute(data_query, base_params + search_params + [safe_per_page, offset])
        rows = [dict(row) for row in cur.fetchall()]

    today = date.today()
    for index, row in enumerate(rows, start=offset + 1):
        row["rank"] = index
        row["visit_count"] = int(row.get("visit_count") or 0)
        if row.get("latitude") is not None:
            row["latitude"] = float(row["latitude"])
        if row.get("longitude") is not None:
            row["longitude"] = float(row["longitude"])
        last_visit = row.get("last_visit_date")
        row["days_since_visit"] = (today - last_visit).days if last_visit else None

    return rows, total_rows


def fetch_map_data(
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Fetch map points for visit distribution."""
    query = (
        _ROLLUP_CTE
        + f"""
    SELECT
        school_id,
        npsn,
        school_name,
        jenjang,
        kecamatan,
        kelurahan,
        latitude,
        longitude,
        visit_count,
        last_visit_date,
        last_guest_name,
        last_guest_institution
    FROM school_rollup
    ORDER BY {SORT_OPTIONS[DEFAULT_SORT]}
    """
    )

    with get_cursor() as cur:
        cur.execute(query, [date_from, date_from, date_to, date_to])
        rows = [dict(row) for row in cur.fetchall()]

    cutoff = date.today() - timedelta(days=30)
    payload: List[Dict[str, Any]] = []
    for row in rows:
        lat = row.get("latitude")
        lng = row.get("longitude")
        if lat is None or lng is None:
            continue

        visit_count = int(row.get("visit_count") or 0)
        last_visit = row.get("last_visit_date")
        if visit_count == 0:
            level = "unvisited"
        elif last_visit and last_visit >= cutoff:
            level = "recent"
        else:
            level = "stale"

        payload.append(
            {
                "school_id": row.get("school_id"),
                "school_name": row.get("school_name"),
                "npsn": row.get("npsn"),
                "jenjang": row.get("jenjang"),
                "kecamatan": row.get("kecamatan"),
                "kelurahan": row.get("kelurahan"),
                "latitude": float(lat),
                "longitude": float(lng),
                "visit_count": visit_count,
                "last_visit_date": last_visit.isoformat() if last_visit else None,
                "last_guest_name": row.get("last_guest_name"),
                "last_guest_institution": row.get("last_guest_institution"),
                "level": level,
            }
        )
    return payload


def fetch_unvisited_schools(
    *,
    limit: int = 8,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Fetch schools with zero visits in the selected period."""
    safe_limit = max(1, min(limit, 100))
    query = (
        _ROLLUP_CTE
        + """
    SELECT
        school_id,
        npsn,
        school_name,
        jenjang,
        kecamatan,
        kelurahan
    FROM school_rollup
    WHERE visit_count = 0
    ORDER BY school_name ASC
    LIMIT %s
    """
    )
    with get_cursor() as cur:
        cur.execute(query, [date_from, date_from, date_to, date_to, safe_limit])
        return [dict(row) for row in cur.fetchall()]


def fetch_recent_visits(
    *,
    limit: int = 10,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Fetch latest visit records for side panel."""
    safe_limit = max(1, min(limit, 100))
    query = """
    SELECT
        v.id,
        v.visit_date,
        v.guest_name,
        v.guest_institution,
        v.purpose,
        v.photo_path,
        s.id AS school_id,
        s.name AS school_name,
        s.npsn,
        s.jenjang
    FROM daftar_tamu_visits v
    JOIN daftar_tamu_schools s ON s.id = v.school_id
    WHERE s.active = TRUE
      AND (%s::date IS NULL OR v.visit_date >= %s::date)
      AND (%s::date IS NULL OR v.visit_date <= %s::date)
    ORDER BY v.visit_date DESC, v.id DESC
    LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(query, [date_from, date_from, date_to, date_to, safe_limit])
        return [dict(row) for row in cur.fetchall()]
