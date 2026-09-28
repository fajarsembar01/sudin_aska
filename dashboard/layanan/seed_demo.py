"""Create clearly marked, repeatable demo records without changing access grants.

Run: python -m dashboard.layanan.seed_demo --owner-id <authorized-staff-id>
"""
import argparse
from datetime import timedelta

from dashboard.db_access import get_cursor
from .queries import FIELDS, has_layanan_access
from .routes import today

BATCH = 'LAYANAN-DEMO-V1'


def seed(owner_id):
    if not has_layanan_access(owner_id):
        raise ValueError('Pilih akun staf yang sudah memiliki akses Layanan.')
    names = ['Fajar', 'Alya', 'Bima', 'Citra', 'Dimas', 'Eka', 'Farah', 'Gilang']
    kinds = ['ijazah', 'skpi', 'legalisasi', 'mutasi']
    statuses = ['dicatat', 'diproses', 'selesai', 'diserahkan']
    inserted = []
    with get_cursor(commit=True) as cur:
        cur.execute('SELECT pg_advisory_xact_lock(731982604)')
        cur.execute('''SELECT id, name FROM portal_schools WHERE active=TRUE
                       ORDER BY jenjang, name LIMIT 8''')
        schools = [dict(row) for row in cur.fetchall()]
        if len(schools) < 2:
            raise ValueError('Minimal dua sekolah terdaftar diperlukan untuk contoh mutasi.')
        for i in range(32):
            number = f'{BATCH}-{i + 1:03d}'
            cur.execute('SELECT id FROM layanan_records WHERE letter_number=%s', (number,))
            if cur.fetchone():
                continue
            student = i % len(names)
            origin = schools[(student + i // 8) % len(schools)]
            destination = schools[(student + i // 8 + 1) % len(schools)]
            kind = kinds[i % 4]
            status = statuses[(i // 4) % 4]
            service_date = today() - timedelta(days=31 - i)
            data = dict(
                service_type=kind, service_date=service_date,
                student_name=f'UJI COBA - {names[student]}',
                school_origin=origin['name'], school_origin_id=origin['id'],
                nisn=f'990000000{student + 1}',
                diploma_number=f'DEMO-IJAZAH-{student + 1:03d}' if kind != 'mutasi' else None,
                letter_code='DEMO-MUTASI' if kind == 'mutasi' else None,
                letter_number=number,
                school_destination=destination['name'] if kind == 'mutasi' else None,
                transfer_direction=('masuk' if i // 4 % 2 == 0 else 'keluar') if kind == 'mutasi' else None,
                grade='VII' if kind == 'mutasi' else None,
                notes=f'[{BATCH}] DATA UJI COBA, bukan layanan atau identitas siswa sebenarnya. Contoh untuk mencoba pencarian, perubahan status, cetak, dan ekspor. Sekolah dipilih dari database untuk simulasi.',
                status=status,
                recipient_name=f'UJI COBA - Penerima {names[student]}' if status == 'diserahkan' else None,
                received_date=service_date if status == 'diserahkan' else None,
            )
            cur.execute(f"INSERT INTO layanan_records ({', '.join(FIELDS)}, created_by, updated_by) VALUES ({', '.join(['%s'] * (len(FIELDS) + 2))}) RETURNING id",
                        [data.get(field) for field in FIELDS] + [owner_id, owner_id])
            inserted.append(cur.fetchone()[0])
    return inserted


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-id', type=int, required=True)
    args = parser.parse_args()
    ids = seed(args.owner_id)
    print(f'{len(ids)} catatan UJI COBA ditambahkan. ID: {ids}')
