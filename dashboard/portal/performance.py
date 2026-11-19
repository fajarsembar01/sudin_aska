"""Panberss contributions, attributed to the account that saved each change."""
from datetime import date, datetime, time, timedelta, timezone
from flask import abort, render_template, request
from dashboard.auth import current_user
from dashboard.db_access import get_cursor
from .routes import portal_bp, _portal_access_required


def performance_data(mode, start, end, period_id, staff_id):
    clauses, params = ['e.user_id IS NOT NULL'], []
    if mode in {'team', 'individual'}:
        clauses.append('a.assessment_mode = %s'); params.append(mode)
    wib = timezone(timedelta(hours=7))
    if start:
        clauses.append('e.created_at >= %s')
        params.append(datetime.combine(start, time.min, wib))
    if end:
        clauses.append('e.created_at < %s')
        params.append(datetime.combine(end + timedelta(days=1), time.min, wib))
    if period_id:
        clauses.append('a.period_id = %s'); params.append(period_id)
    cte = """WITH activity AS (
        SELECT e.*, a.school_id, a.assessment_mode, a.status, a.period_id,
               s.name AS school_name, p.name AS period_name
        FROM portal_assessment_team_events e
        JOIN portal_assessments a ON a.id = e.assessment_id
        JOIN portal_schools s ON s.id = a.school_id
        LEFT JOIN portal_assessment_periods p ON p.id = a.period_id
        WHERE """ + ' AND '.join(clauses) + ') '
    with get_cursor() as cur:
        cur.execute(cte + """SELECT u.id AS staff_id, u.full_name,
            COUNT(e.id)::int AS actions,
            COUNT(DISTINCT e.assessment_id)::int AS assessments,
            COUNT(DISTINCT e.school_id)::int AS schools,
            COUNT(DISTINCT (e.assessment_id, e.school_room_id))
                FILTER (WHERE e.school_room_id IS NOT NULL)::int AS rooms,
            COUNT(DISTINCT (e.assessment_id, e.school_room_id, e.field_key))
                FILTER (WHERE e.field_key LIKE 'score:%%')::int AS scores,
            COUNT(DISTINCT (e.assessment_id, e.school_room_id))
                FILTER (WHERE e.field_key = 'note')::int AS notes,
            COUNT(DISTINCT (e.assessment_id, e.school_room_id))
                FILTER (WHERE e.field_key = 'photo')::int AS photos,
            COUNT(DISTINCT e.assessment_id)
                FILTER (WHERE e.field_key = 'submit')::int AS submissions,
            COUNT(DISTINCT e.assessment_id)
                FILTER (WHERE e.assessment_mode = 'team')::int AS team_assessments,
            COUNT(DISTINCT e.assessment_id)
                FILTER (WHERE e.assessment_mode = 'individual')::int AS individual_assessments,
            MAX(e.created_at) AS last_activity
            FROM dashboard_users u JOIN activity e ON e.user_id = u.id
            GROUP BY u.id, u.full_name
            ORDER BY (COUNT(DISTINCT (e.assessment_id, e.school_room_id, e.field_key))
                FILTER (WHERE e.field_key LIKE 'score:%%' OR e.field_key IN ('note', 'photo'))) DESC,
                submissions DESC, u.full_name, u.id""", params)
        leaderboard = [dict(row) for row in cur.fetchall()]
        cur.execute(cte + """SELECT e.*, r.name AS room_name,
            aspect.name AS aspect_name
            FROM activity e
            LEFT JOIN portal_school_rooms sr ON sr.id = e.school_room_id
            LEFT JOIN portal_rooms r ON r.id = sr.room_id
            LEFT JOIN portal_aspects aspect ON ('score:' || aspect.id::text) = e.field_key
            WHERE e.user_id = %s ORDER BY e.created_at DESC, e.id DESC LIMIT 100""",
            params + [staff_id])
        events = [dict(row) for row in cur.fetchall()]
    return leaderboard, events


@portal_bp.route('/staff/performance')
@_portal_access_required
def staff_performance():
    user = current_user() or {}
    if user.get('role') not in {'staff', 'admin', 'coordinator'}:
        abort(403)
    mode = request.args.get('assessment_mode', 'individual')
    if mode not in {'all', 'team', 'individual'}:
        abort(400, 'Mode penilaian tidak valid.')
    today = datetime.now(timezone(timedelta(hours=7))).date()
    try:
        start_raw = request.args.get('from', today.replace(day=1).isoformat())
        end_raw = request.args.get('to', today.isoformat())
        start = date.fromisoformat(start_raw) if start_raw else None
        end = date.fromisoformat(end_raw) if end_raw else None
        if start and end and start > end:
            raise ValueError()
        if end == date.max:
            raise ValueError()
    except ValueError:
        abort(400, 'Rentang tanggal tidak valid.')
    staff_id = request.args.get('staff_id', type=int) or user['id']
    if staff_id != user['id'] and user.get('role') != 'admin':
        abort(403)
    period_id = request.args.get('period_id', type=int)
    with get_cursor() as cur:
        cur.execute('SELECT id, name FROM portal_assessment_periods ORDER BY start_date DESC')
        periods = [dict(row) for row in cur.fetchall()]
    if period_id and period_id not in {p['id'] for p in periods}:
        abort(400, 'Periode tidak ditemukan.')
    leaderboard, events = performance_data(mode, start, end, period_id, staff_id)
    personal = next((row for row in leaderboard if row['staff_id'] == staff_id), None)
    return render_template('portal/staff/performance.html', leaderboard=leaderboard,
        events=events, personal=personal, selected_staff=staff_id, mode=mode,
        start=start_raw, end=end_raw, periods=periods, period_id=period_id)
