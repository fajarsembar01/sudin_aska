"""Team workspace and synchronization endpoints within the Panberss menu."""
from pathlib import PurePosixPath
from flask import has_request_context, abort, flash, jsonify, redirect, render_template, request, url_for
from dashboard.auth import current_user, role_required
from dashboard.db_access import get_cursor
from . import team_assessments as team
from .queries import get_active_period
from .routes import portal_bp, _portal_access_required


@portal_bp.route('/pilih-penilaian')
@_portal_access_required
def assessment_modes():
    user = current_user() or {}
    role = user.get('role')
    if role == 'sekolah':
        return redirect(url_for('portal.sekolah_home'))
    if role not in {'staff', 'admin', 'coordinator'}:
        abort(403)
    individual_endpoint = ('portal.staff_assignments' if role == 'staff' else
                           'portal.coordinator_assessments' if role == 'coordinator' else 'portal.schools')
    cards = [
        {'title': 'Penilaian Tim', 'description': 'Isi satu penilaian bersama anggota tim Monev.',
         'icon': 'bi-people', 'href': url_for('portal.team_workspace'), 'col_class': 'col-md-6 col-12'},
        {'title': 'Penilaian Individu', 'description': 'Isi penilaian pribadi sesuai penugasan akun Anda.',
         'icon': 'bi-person-check', 'href': url_for(individual_endpoint), 'col_class': 'col-md-6 col-12'},
    ]
    return render_template('portal/assessments/modes.html', page_title='Pilih Penilaian - PANBERSS',
        header_title='Penilaian Panberss', header_subtitle='Pilih penilaian Tim atau Individu',
        cards=cards, default_col_class='col-md-6 col-12', enable_odd_center=False,
        mobile_compact=True, show_logout=False,
        back_href=url_for('main.admin_select_role') if role == 'admin' else url_for('portal.home'),
        back_label='Kembali ke OSS')


@portal_bp.route('/penilaian-tim')
@_portal_access_required
def team_workspace():
    user = current_user() or {}
    if user.get('role') not in {'staff', 'admin', 'coordinator'}:
        abort(403)
    assignments = team.list_assignments(user)
    with get_cursor() as cur:
        cur.execute("SELECT id, school_id FROM portal_assessments WHERE assessment_mode = 'team' AND status = 'draft'")
        drafts = {r['school_id']: r['id'] for r in cur.fetchall()}
    return render_template('portal/teams/workspace.html', assignments=assignments,
        drafts=drafts, history=team.list_history(user), active_period=get_active_period())


@portal_bp.route('/admin/penugasan-tim', methods=['GET', 'POST'])
@role_required('admin')
def team_assignment_settings():
    assignments = team.list_assignments(include_disabled=True)
    if request.method == 'POST':
        selected = set(request.form.getlist('school_ids', type=int))
        allowed = {a['school_id'] for a in assignments}
        if not selected <= allowed:
            abort(400, 'Sekolah tidak sesuai penugasan Monev aktif.')
        with get_cursor(commit=True) as cur:
            for school_id in allowed:
                if school_id in selected:
                    # Enabled is the automatic default; only exclusions need storage.
                    cur.execute('DELETE FROM portal_team_assessment_settings WHERE school_id = %s', (school_id,))
                else:
                    cur.execute("""INSERT INTO portal_team_assessment_settings (school_id, enabled, updated_by)
                        VALUES (%s, FALSE, %s) ON CONFLICT (school_id) DO UPDATE
                        SET enabled = FALSE, updated_by = EXCLUDED.updated_by, updated_at = NOW()""",
                        (school_id, current_user()['id']))
        flash('Pengecualian Panberss disimpan. Penugasan Monev lainnya tersedia otomatis.', 'success')
        return redirect(url_for('portal.team_assignment_settings'))
    return render_template('portal/teams/settings.html', assignments=assignments, active_period=get_active_period())


@portal_bp.route('/assessment/<int:assessment_id>/team-state', methods=['GET', 'POST'])
@_portal_access_required
def team_state(assessment_id):
    payload = (request.get_json(silent=True) or {}) if request.method == 'POST' else {}
    if not isinstance(payload, dict):
        abort(400)
    client_id = payload.get('client_id')
    room_id = payload.get('school_room_id')
    if client_id is not None and (not isinstance(client_id, str) or not 1 <= len(client_id) <= 64):
        abort(400)
    if room_id is not None and (type(room_id) is not int or room_id <= 0):
        abort(400)
    try:
        result = team.state(assessment_id, current_user(), client_id, room_id)
    except PermissionError as exc:
        return jsonify(success=False, message=str(exc)), 403
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    for photo in result['photos']:
        photo['url'] = url_for('portal.uploaded_file', filename=PurePosixPath(photo.pop('photo_path')).name)
    result.update(success=True, view_url=url_for('portal.view_assessment', assessment_id=assessment_id))
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    return response


@portal_bp.url_defaults
def preserve_statistics_mode(endpoint, values):
    # Keep the mode on links to maps, rankings, galleries and exports as well.
    if not has_request_context() or 'assessment_mode' in values:
        return
    if any(word in endpoint for word in ('stats', 'ranking', 'map_data', 'photos', 'gallery', 'export')):
        mode = request.args.get('assessment_mode')
        if mode in {'all', 'individual', 'team'}:
            values['assessment_mode'] = mode
