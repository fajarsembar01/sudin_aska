"""Shared Panberss assessments; membership follows effective Monev assignments."""
import json
from dashboard.db_access import get_cursor

# Resolve the newest ACTIVE assignment before checking membership, so an older
# team cannot retain access when a newer active assignment belongs to another team.
EFFECTIVE_ASSIGNMENTS = """
    SELECT DISTINCT ON (school.id) school.id AS school_id, school.name AS school_name,
           school.npsn, school.jenjang, a.team_id, t.name AS team_name, t.leader_id,
           p.id AS monev_period_id, p.year, p.tw,
           COALESCE(setting.enabled, TRUE) AS enabled
    FROM monev_bos_assignments a
    JOIN monev_bos_periods p ON p.id = a.period_id AND p.is_active = TRUE
    JOIN monev_bos_teams t ON t.id = a.team_id
    JOIN dashboard_users account ON account.id = a.school_id
    JOIN LATERAL (
        SELECT ps.* FROM portal_schools ps
        WHERE ps.id = account.school_id OR ps.user_id = account.id
        ORDER BY CASE WHEN ps.id = account.school_id THEN 0 ELSE 1 END, ps.id
        LIMIT 1
    ) school ON school.active = TRUE
    LEFT JOIN portal_team_assessment_settings setting ON setting.school_id = school.id
    ORDER BY school.id, p.year DESC, p.tw DESC, p.id DESC, a.id DESC
"""
MEMBERSHIP = """(e.leader_id = %s OR EXISTS (
    SELECT 1 FROM monev_bos_team_members tm WHERE tm.team_id = e.team_id AND tm.staff_id = %s
))"""


class TeamConflict(ValueError):
    pass


def list_assignments(user=None, include_disabled=False, cur=None):
    where, params = [], []
    if not include_disabled:
        where.append('e.enabled = TRUE')
    if user and user.get('role') != 'admin':
        where.append(MEMBERSHIP)
        params.extend([user['id'], user['id']])
    query = 'WITH effective AS (' + EFFECTIVE_ASSIGNMENTS + ') SELECT e.* FROM effective e'
    if where:
        query += ' WHERE ' + ' AND '.join(where)
    query += ' ORDER BY e.school_name'
    if cur is not None:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
    with get_cursor() as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def assignment_for(school_id, user, cur=None):
    return next((a for a in list_assignments(user, cur=cur) if a['school_id'] == school_id), None)


def can_access(user, assessment, edit=False, cur=None):
    if not user or user.get('role') not in {'admin', 'staff', 'coordinator'}:
        return False
    if user.get('role') == 'admin':
        return True
    if assessment.get('status') == 'draft':
        assignment = assignment_for(assessment['school_id'], user, cur=cur)
        return bool(assignment and (not assessment.get('period_locked')
                    or assignment['team_id'] == assessment.get('monev_team_id')))
    if edit:
        return False
    return any(m.get('id') == user['id'] for m in assessment.get('team_members_snapshot', []))


def member_snapshot(cur, team_id):
    cur.execute("""SELECT id, full_name AS name FROM dashboard_users
        WHERE id IN (SELECT leader_id FROM monev_bos_teams WHERE id = %s
                     UNION SELECT staff_id FROM monev_bos_team_members WHERE team_id = %s)
        ORDER BY id""", (team_id, team_id))
    return [dict(row) for row in cur.fetchall()]


def get_or_create_draft(school_id, user):
    with get_cursor(commit=True) as cur:
        # One shared draft per school, independent of who opens it or when.
        cur.execute('SELECT id FROM portal_schools WHERE id = %s FOR UPDATE', (school_id,))
        if not cur.fetchone():
            raise ValueError('Sekolah tidak ditemukan.')
        assignment = assignment_for(school_id, user, cur=cur)
        if not assignment:
            raise PermissionError('Sekolah ini bukan penugasan tim Panberss Anda.')
        cur.execute("SELECT * FROM portal_assessments WHERE school_id = %s AND assessment_mode = 'team' AND status = 'draft' FOR UPDATE", (school_id,))
        draft = cur.fetchone()
        if draft:
            if draft['period_locked']:
                if not can_access(user, dict(draft), edit=True, cur=cur):
                    raise PermissionError('Draft ini adalah hasil lama yang dibuka ulang untuk tim asalnya.')
                return dict(draft)
            cur.execute('UPDATE portal_assessments SET monev_team_id = %s, team_name_snapshot = %s WHERE id = %s RETURNING *',
                        (assignment['team_id'], assignment['team_name'], draft['id']))
        else:
            cur.execute("""INSERT INTO portal_assessments
                (school_id, staff_id, assessment_mode, monev_team_id, team_name_snapshot, score_scale_max)
                VALUES (%s, %s, 'team', %s, %s, 5) RETURNING *""",
                (school_id, user['id'], assignment['team_id'], assignment['team_name']))
        return dict(cur.fetchone())


def list_history(user):
    where = "a.assessment_mode = 'team' AND a.status <> 'draft'"
    params = []
    if user.get('role') != 'admin':
        where += ' AND a.team_members_snapshot @> %s::jsonb'
        params.append(json.dumps([{'id': user['id']}]))
    with get_cursor() as cur:
        cur.execute("""SELECT a.id, a.status, a.team_name_snapshot, a.submitted_at,
            s.name AS school_name, p.name AS period_name
            FROM portal_assessments a JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN portal_assessment_periods p ON p.id = a.period_id WHERE """ + where +
            ' ORDER BY a.submitted_at DESC LIMIT 100', params)
        return [dict(row) for row in cur.fetchall()]


def save_field(assessment_id, room_id, field_key, value, base_version, user):
    """Compare-and-set a single field under the same row lock used by submit."""
    if type(base_version) is not int or base_version < 0:
        raise TeamConflict('Versi isian tidak valid. Sinkronkan halaman terlebih dahulu.')
    with get_cursor(commit=True) as cur:
        cur.execute('SELECT * FROM portal_assessments WHERE id = %s FOR UPDATE', (assessment_id,))
        row = cur.fetchone()
        if not row or row['status'] != 'draft':
            raise TeamConflict('Penilaian sudah dikirim. Perubahan tidak disimpan.')
        assessment = dict(row)
        if not can_access(user, assessment, edit=True, cur=cur):
            raise PermissionError('Penugasan tim Anda sudah berubah. Perubahan tidak disimpan.')
        cur.execute('SELECT id FROM portal_school_rooms WHERE id = %s AND school_id = %s', (room_id, assessment['school_id']))
        if not cur.fetchone():
            raise ValueError('Ruangan tidak sesuai sekolah.')
        cur.execute('SELECT version FROM portal_assessment_field_versions WHERE assessment_id = %s AND school_room_id = %s AND field_key = %s', (assessment_id, room_id, field_key))
        current = cur.fetchone()
        version = current['version'] if current else 0
        if version != base_version:
            raise TeamConflict('Isian ini sudah diubah anggota lain. Pilihan Anda belum disimpan; periksa versi terbaru lalu pilih kembali.')
        if field_key == 'note':
            cur.execute('SELECT notes AS value FROM portal_assessment_room_details WHERE assessment_id = %s AND school_room_id = %s', (assessment_id, room_id))
            previous = cur.fetchone()
            if not isinstance(value, str) or len(value) > 10000:
                raise ValueError('Catatan maksimal 10.000 karakter.')
            cur.execute("""INSERT INTO portal_assessment_room_details (assessment_id, school_room_id, notes)
                VALUES (%s, %s, %s) ON CONFLICT (assessment_id, school_room_id)
                DO UPDATE SET notes = EXCLUDED.notes, updated_at = NOW()""", (assessment_id, room_id, value))
        else:
            aspect_id = int(field_key.split(':')[1])
            cur.execute('SELECT score AS value FROM portal_assessment_scores WHERE assessment_id = %s AND school_room_id = %s AND aspect_id = %s', (assessment_id, room_id, aspect_id))
            previous = cur.fetchone()
            if type(value) is not int or not 1 <= value <= (assessment.get('score_scale_max') or 5):
                raise ValueError('Nilai di luar rentang penilaian.')
            cur.execute("""SELECT 1 FROM portal_school_rooms sr JOIN portal_aspects a ON a.room_id = sr.room_id
                WHERE sr.id = %s AND a.id = %s AND a.active = TRUE
                  AND (a.is_required = TRUE OR EXISTS (SELECT 1 FROM portal_school_room_aspects selected
                       WHERE selected.school_room_id = sr.id AND selected.aspect_id = a.id))""", (room_id, aspect_id))
            if not cur.fetchone():
                raise ValueError('Aspek tidak sesuai ruangan.')
            cur.execute("""INSERT INTO portal_assessment_scores (assessment_id, school_room_id, aspect_id, score)
                VALUES (%s, %s, %s, %s) ON CONFLICT (assessment_id, school_room_id, aspect_id)
                DO UPDATE SET score = EXCLUDED.score, updated_at = NOW()""", (assessment_id, room_id, aspect_id, value))
        cur.execute("""INSERT INTO portal_assessment_field_versions (assessment_id, school_room_id, field_key, version, edited_by)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT (assessment_id, school_room_id, field_key)
            DO UPDATE SET version = EXCLUDED.version, edited_by = EXCLUDED.edited_by, updated_at = NOW()""",
            (assessment_id, room_id, field_key, version + 1, user['id']))
        if not previous or previous['value'] != value:
            record_event(cur, assessment_id, room_id, field_key, user['id'])
        cur.execute('UPDATE portal_assessments SET updated_at = NOW() WHERE id = %s', (assessment_id,))
        return version + 1


def state(assessment_id, user, client_id=None, room_id=None):
    with get_cursor(commit=True) as cur:
        cur.execute('SELECT * FROM portal_assessments WHERE id = %s FOR SHARE', (assessment_id,))
        row = cur.fetchone()
        if not row or row['assessment_mode'] != 'team' or not can_access(user, dict(row), cur=cur):
            raise PermissionError('Anda tidak memiliki akses ke penilaian tim ini.')
        assessment = dict(row)
        if client_id and assessment['status'] == 'draft':
            if room_id:
                cur.execute('SELECT id FROM portal_school_rooms WHERE id = %s AND school_id = %s', (room_id, assessment['school_id']))
                if not cur.fetchone():
                    raise ValueError('Ruangan tidak sesuai sekolah.')
            cur.execute("""INSERT INTO portal_assessment_presence (assessment_id, user_id, client_id, school_room_id)
                VALUES (%s, %s, %s, %s) ON CONFLICT (assessment_id, user_id, client_id)
                DO UPDATE SET school_room_id = EXCLUDED.school_room_id, seen_at = NOW()""", (assessment_id, user['id'], client_id, room_id))
        cur.execute("DELETE FROM portal_assessment_presence WHERE assessment_id = %s AND seen_at < NOW() - INTERVAL '45 seconds'", (assessment_id,))
        cur.execute('SELECT school_room_id, aspect_id, score FROM portal_assessment_scores WHERE assessment_id = %s', (assessment_id,))
        scores = [dict(r) for r in cur.fetchall()]
        cur.execute('SELECT school_room_id, notes FROM portal_assessment_room_details WHERE assessment_id = %s', (assessment_id,))
        notes = [dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT v.school_room_id, v.field_key, v.version, v.edited_by, u.full_name AS editor_name
            FROM portal_assessment_field_versions v LEFT JOIN dashboard_users u ON u.id = v.edited_by
            WHERE v.assessment_id = %s""", (assessment_id,))
        versions = [dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT p.school_room_id, p.user_id, u.full_name AS name FROM portal_assessment_presence p
            JOIN dashboard_users u ON u.id = p.user_id WHERE p.assessment_id = %s""", (assessment_id,))
        presence = [dict(r) for r in cur.fetchall()]
        cur.execute('SELECT id, school_room_id, photo_path, captured_at, latitude, longitude FROM portal_assessment_photos WHERE assessment_id = %s ORDER BY captured_at DESC NULLS LAST', (assessment_id,))
        photos = [dict(r) for r in cur.fetchall()]
        # A room is complete when every required (or explicitly selected) active
        # aspect has a score. The latest score editor is the attribution source;
        # merely opening a room only updates presence.
        cur.execute("""SELECT sr.id AS school_room_id, r.name AS room_name,
                COALESCE(required.total, 0) AS required_count,
                COALESCE(required.total, 0) - COALESCE(scored.total, 0) AS remaining,
                editor.editor_name AS last_editor
            FROM portal_school_rooms sr JOIN portal_rooms r ON r.id = sr.room_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS total FROM portal_aspects a
                WHERE a.room_id = sr.room_id AND a.active = TRUE
                  AND (a.is_required = TRUE OR EXISTS (
                    SELECT 1 FROM portal_school_room_aspects selected
                    WHERE selected.school_room_id = sr.id AND selected.aspect_id = a.id))
            ) required ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS total FROM portal_assessment_scores s
                JOIN portal_aspects a ON a.id = s.aspect_id AND a.active = TRUE
                WHERE s.assessment_id = %s AND s.school_room_id = sr.id
                  AND (a.is_required = TRUE OR EXISTS (
                    SELECT 1 FROM portal_school_room_aspects selected
                    WHERE selected.school_room_id = sr.id AND selected.aspect_id = a.id))
            ) scored ON TRUE
            LEFT JOIN LATERAL (
                SELECT u.full_name AS editor_name FROM portal_assessment_team_events e
                JOIN dashboard_users u ON u.id = e.user_id
                WHERE e.assessment_id = %s AND e.school_room_id = sr.id
                  AND e.field_key LIKE 'score:%%'
                ORDER BY e.created_at DESC, e.id DESC LIMIT 1
            ) editor ON TRUE
            WHERE sr.school_id = %s AND r.active = TRUE""",
            (assessment_id, assessment_id, assessment['school_id']))
        room_status = [dict(r) for r in cur.fetchall()]
        return {'status': assessment['status'], 'scores': scores, 'notes': notes,
                'versions': versions, 'presence': presence, 'photos': photos,
                'room_status': room_status}


def record_event(cur, assessment_id, room_id, field, user_id):
    cur.execute("""INSERT INTO portal_assessment_team_events
        (assessment_id, school_room_id, field_key, user_id) VALUES (%s, %s, %s, %s)""",
        (assessment_id, room_id, field, user_id))


def check_photo_write(cur, assessment_id, room_id, user, base_version):
    cur.execute('SELECT * FROM portal_assessments WHERE id = %s FOR UPDATE', (assessment_id,))
    row = cur.fetchone()
    if not row or row['status'] != 'draft':
        raise TeamConflict('Penilaian sudah dikirim. Foto tidak diubah.')
    if row['assessment_mode'] != 'team':
        return None
    if not user or not can_access(user, dict(row), edit=True, cur=cur):
        raise PermissionError('Penugasan tim berubah. Foto tidak diubah.')
    cur.execute('SELECT id FROM portal_school_rooms WHERE id = %s AND school_id = %s', (room_id, row['school_id']))
    if not cur.fetchone():
        raise ValueError('Ruangan tidak sesuai sekolah.')
    cur.execute("SELECT version FROM portal_assessment_field_versions WHERE assessment_id = %s AND school_room_id = %s AND field_key = 'photo'", (assessment_id, room_id))
    version_row = cur.fetchone()
    version = version_row['version'] if version_row else 0
    if type(base_version) is not int or base_version != version:
        raise TeamConflict('Foto ruangan sudah diperbarui anggota lain. Periksa foto terbaru sebelum mencoba kembali.')
    return version + 1


def record_photo_write(cur, assessment_id, room_id, version, user, field="photo"):
    if version is None:
        return
    cur.execute("""INSERT INTO portal_assessment_field_versions (assessment_id, school_room_id, field_key, version, edited_by)
        VALUES (%s, %s, 'photo', %s, %s) ON CONFLICT (assessment_id, school_room_id, field_key)
        DO UPDATE SET version = EXCLUDED.version, edited_by = EXCLUDED.edited_by, updated_at = NOW()""", (assessment_id, room_id, version, user['id']))
    record_event(cur, assessment_id, room_id, field, user['id'])


def contributors(assessment_id):
    with get_cursor() as cur:
        cur.execute("""SELECT u.full_name AS name, COUNT(*) AS edits, COUNT(DISTINCT e.school_room_id) AS rooms,
            MAX(e.created_at) AS last_edit FROM portal_assessment_team_events e
            LEFT JOIN dashboard_users u ON u.id = e.user_id
            WHERE e.assessment_id = %s GROUP BY e.user_id, u.full_name ORDER BY MIN(e.created_at)""", (assessment_id,))
        return [dict(r) for r in cur.fetchall()]


def reopen_with_cursor(cur, assessment_id):
    cur.execute('SELECT school_id, assessment_mode FROM portal_assessments WHERE id = %s', (assessment_id,))
    row = cur.fetchone()
    if not row:
        return False
    if row['assessment_mode'] == 'team':
        cur.execute('SELECT id FROM portal_schools WHERE id = %s FOR UPDATE', (row['school_id'],))
        cur.execute("SELECT id FROM portal_assessments WHERE school_id = %s AND assessment_mode = 'team' AND status = 'draft' AND id <> %s", (row['school_id'], assessment_id))
        if cur.fetchone():
            return False
    cur.execute("UPDATE portal_assessments SET status = 'draft', submitted_at = NULL WHERE id = %s RETURNING id", (assessment_id,))
    return cur.fetchone() is not None


def approve_reopen(assessment_id, request_id, reviewer_id, note):
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT id FROM portal_assessment_reopen_requests WHERE id = %s AND assessment_id = %s AND status = 'pending' FOR UPDATE", (request_id, assessment_id))
        if not cur.fetchone() or not reopen_with_cursor(cur, assessment_id):
            return False
        cur.execute("""UPDATE portal_assessment_reopen_requests SET status = 'approved', reviewer_id = %s,
            reviewer_note = %s, reviewed_at = NOW() WHERE id = %s""", (reviewer_id, note, request_id))
        return True
