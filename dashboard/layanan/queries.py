from pathlib import Path
from dashboard.db_access import get_cursor

FIELDS = ('service_type', 'service_date', 'student_name', 'school_origin',
          'diploma_number', 'nisn', 'letter_code', 'letter_number',
          'school_destination', 'transfer_direction', 'grade', 'notes',
          'status', 'recipient_name', 'received_date', 'school_origin_id',
          'school_destination_id')


def list_origin_schools():
    """Include inactive schools for historical service registers."""
    with get_cursor() as cur:
        cur.execute('SELECT id, name, npsn, active FROM portal_schools ORDER BY name, npsn')
        return [dict(row) for row in cur.fetchall()]


def get_origin_school(school_id):
    with get_cursor() as cur:
        cur.execute('SELECT id, name FROM portal_schools WHERE id = %s', (school_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def ensure_schema():
    with get_cursor(commit=True) as cur:
        cur.execute(Path(__file__).with_name('schema.sql').read_text())


def _record_filter(filters):
    clauses, params = [], []
    for key in ('service_type', 'status'):
        if filters.get(key):
            clauses.append(f'r.{key} = %s')
            params.append(filters[key])
    for key, operator in (('start', '>='), ('end', '<=')):
        if filters.get(key):
            clauses.append(f'r.service_date {operator} %s')
            params.append(filters[key])
    if filters.get('q'):
        clauses.append("concat_ws(' ', r.student_name, r.school_origin, r.school_destination, r.diploma_number, r.nisn, r.letter_number, r.id::text) ILIKE %s")
        term = filters['q'].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        params.append('%' + term + '%')
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    return where, params


def summarize_records(filters):
    where, params = _record_filter(filters)
    with get_cursor() as cur:
        cur.execute('''SELECT r.service_type, r.status, count(*) AS total
                       FROM layanan_records r''' + where + ' GROUP BY r.service_type, r.status', params)
        return [dict(row) for row in cur.fetchall()]


def list_records(filters, page=1, export=False):
    where, params = _record_filter(filters)
    with get_cursor() as cur:
        cur.execute('SELECT count(*) FROM layanan_records r' + where, params)
        total = cur.fetchone()[0]
        sql = '''SELECT r.*, u.full_name AS officer_name FROM layanan_records r
                 LEFT JOIN dashboard_users u ON u.id = r.created_by'''
        sql += where + ' ORDER BY r.service_date DESC, r.id DESC'
        if not export:
            sql += ' LIMIT 25 OFFSET %s'
            params.append((page - 1) * 25)
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()], total


def get_record(record_id):
    with get_cursor() as cur:
        cur.execute('SELECT * FROM layanan_records WHERE id = %s', (record_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def save_record(data, user, record_id=None, version=None):
    values = [data.get(field) or None for field in FIELDS]
    with get_cursor(commit=True) as cur:
        if record_id is None:
            cur.execute(f"INSERT INTO layanan_records ({', '.join(FIELDS)}, created_by, updated_by) VALUES ({', '.join(['%s'] * (len(FIELDS) + 2))}) RETURNING id",
                        values + [user['id'], user['id']])
        else:
            assignments = ', '.join(f'{field} = %s' for field in FIELDS)
            cur.execute(f'''UPDATE layanan_records SET {assignments}, updated_by = %s,
                            updated_at = NOW(), version = version + 1
                            WHERE id = %s AND version = %s
                            AND (created_by = %s OR %s) RETURNING id''',
                        values + [user['id'], record_id, version, user['id'], user['role'] == 'admin'])
        row = cur.fetchone()
        return row[0] if row else None


def update_record_status(record_id, data, user, version):
    """Update workflow fields only; keep student and document data untouched."""
    with get_cursor(commit=True) as cur:
        cur.execute('''UPDATE layanan_records
                       SET status = %s, recipient_name = %s, received_date = %s,
                           updated_by = %s, updated_at = NOW(), version = version + 1
                       WHERE id = %s AND version = %s
                         AND (created_by = %s OR %s)
                       RETURNING id''',
                    (data['status'], data['recipient_name'] or None, data['received_date'] or None,
                     user['id'], record_id, version, user['id'], user['role'] == 'admin'))
        return cur.fetchone() is not None


def has_layanan_access(user_id):
    with get_cursor() as cur:
        cur.execute('''SELECT 1 FROM layanan_access a
                       JOIN dashboard_users u ON u.id = a.user_id
                       WHERE a.user_id = %s AND u.account_status = 'approved'
                       AND u.role IN ('staff', 'pengawas', 'kasi', 'operator')''', (user_id,))
        return cur.fetchone() is not None


def list_layanan_access_staff():
    with get_cursor() as cur:
        cur.execute('''SELECT u.id, u.full_name, u.email, u.nip, u.jabatan, u.role,
                              u.account_status, (a.user_id IS NOT NULL) AS has_access,
                              a.granted_at, grantor.full_name AS granted_by_name
                       FROM dashboard_users u
                       LEFT JOIN layanan_access a ON a.user_id = u.id
                       LEFT JOIN dashboard_users grantor ON grantor.id = a.granted_by
                       WHERE u.role IN ('staff', 'pengawas', 'kasi', 'operator')
                          OR a.user_id IS NOT NULL
                       ORDER BY COALESCE(u.full_name, u.email), u.id''')
        return [dict(row) for row in cur.fetchall()]


def set_layanan_access(user_id, *, enabled, granted_by):
    """Change one account without overwriting another admin's selections."""
    with get_cursor(commit=True) as cur:
        cur.execute('''SELECT role, account_status FROM dashboard_users
                       WHERE id = %s FOR UPDATE''', (user_id,))
        user = cur.fetchone()
        if not user:
            raise ValueError('Akun tidak ditemukan.')
        if enabled:
            if user['role'] not in ('staff', 'pengawas', 'kasi', 'operator') or user['account_status'] != 'approved':
                raise ValueError('Akses hanya dapat diberikan kepada akun staf yang telah disetujui.')
            cur.execute('''INSERT INTO layanan_access (user_id, granted_by) VALUES (%s, %s)
                           ON CONFLICT (user_id) DO NOTHING''', (user_id, granted_by))
        else:
            cur.execute('DELETE FROM layanan_access WHERE user_id = %s', (user_id,))


def search_students_by_nisn(prefix):
    """Reuse the latest recorded identity per NISN, preserving leading zeros."""
    with get_cursor() as cur:
        cur.execute('''SELECT recent.nisn, recent.student_name, s.id AS school_origin_id,
                              s.name AS school_origin
                       FROM (
                           SELECT DISTINCT ON (nisn) nisn, student_name, school_origin_id
                           FROM layanan_records WHERE nisn LIKE %s
                           ORDER BY nisn, updated_at DESC, id DESC
                           LIMIT 10
                       ) recent
                       LEFT JOIN portal_schools s ON s.id = recent.school_origin_id
                       ORDER BY recent.nisn''', (prefix + '%',))
        return [dict(row) for row in cur.fetchall()]
