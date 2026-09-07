"""Persisted, immediately revocable access for call center operators."""
from functools import wraps

from flask import abort, g, jsonify, redirect, request, url_for

from ..auth import current_user
from ..db_access import get_cursor

_SCHEMA_READY = False


def ensure_access_schema():
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with get_cursor(commit=True) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cc_staff_access (
                user_id INTEGER PRIMARY KEY REFERENCES dashboard_users(id) ON DELETE CASCADE,
                granted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    _SCHEMA_READY = True


def can_answer_call_center():
    user = current_user() or {}
    if user.get('role') == 'admin':
        return True
    if user.get('role') not in {'staff', 'coordinator'} or not user.get('id'):
        return False
    if 'cc_can_answer' not in g:
        ensure_access_schema()
        with get_cursor() as cur:
            cur.execute("""
                SELECT 1 FROM cc_staff_access a
                JOIN dashboard_users u ON u.id = a.user_id
                WHERE a.user_id = %s AND u.role IN ('staff', 'coordinator')
                  AND COALESCE(u.account_status, 'approved') = 'approved'
            """, (user['id'],))
            g.cc_can_answer = cur.fetchone() is not None
    return g.cc_can_answer


def operator_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            if '/api/' in request.path:
                return jsonify(error='Silakan login terlebih dahulu.'), 401
            return redirect(url_for('auth.login', next=request.path))
        if not can_answer_call_center():
            if '/api/' in request.path:
                return jsonify(error='Anda belum memiliki akses Call Center.'), 403
            abort(403, description='Anda belum memiliki akses Call Center.')
        return view(*args, **kwargs)
    return wrapped


def list_staff_access():
    ensure_access_schema()
    with get_cursor() as cur:
        cur.execute("""
            SELECT u.id, u.full_name, u.email, u.role,
                   COALESCE(u.account_status, 'approved') AS account_status,
                   a.user_id IS NOT NULL AS has_access, a.granted_at
            FROM dashboard_users u
            LEFT JOIN cc_staff_access a ON a.user_id = u.id
            WHERE u.role IN ('staff', 'coordinator') OR a.user_id IS NOT NULL
            ORDER BY a.user_id IS NOT NULL DESC, LOWER(u.full_name), u.id
        """)
        return [dict(row) for row in cur.fetchall()]


def update_staff_access(user_ids, *, grant, actor_id):
    ensure_access_schema()
    if not user_ids:
        raise ValueError('Pilih minimal satu staf.')
    with get_cursor(commit=True) as cur:
        cur.execute("""
            SELECT id, role, COALESCE(account_status, 'approved') AS account_status
            FROM dashboard_users WHERE id = ANY(%s) FOR UPDATE
        """, (sorted(user_ids),))
        users = cur.fetchall()
        if len(users) != len(user_ids) or (grant and any(
            row['role'] not in {'staff', 'coordinator'} or row['account_status'] != 'approved'
            for row in users
        )):
            raise ValueError('Akses hanya dapat diberikan kepada staf atau koordinator dengan akun yang disetujui.')
        for user_id in sorted(user_ids):
            if grant:
                cur.execute("""
                    INSERT INTO cc_staff_access (user_id, granted_by) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, actor_id))
            else:
                cur.execute('DELETE FROM cc_staff_access WHERE user_id = %s', (user_id,))
