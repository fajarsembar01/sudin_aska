from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Flask, session
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader

from dashboard import queries, user_management
from dashboard.pengaturan.routes import pengaturan_bp
from dashboard.portal import routes as portal_routes

ROOT = Path(__file__).parent
URL = '/dashboard/pengaturan/users'


def account(user_id=1, status='approved'):
    return dict(id=user_id, full_name=f'User {user_id}', email=f'u{user_id}@example.invalid',
                role='staff', account_status=status, created_at=None, school_name=None,
                school_operator_phone=None, school_phone=None, whatsapp_number=None)


class Cursor:
    def __init__(self, total=123, pending_count=73):
        self.total = total
        self.pending_count = pending_count
        self.calls = []

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=()): self.calls.append((' '.join(sql.split()), params))
    def fetchone(self):
        return {'total': self.pending_count if len(self.calls) == 3 else self.total}
    def fetchall(self): return [account()]


@pytest.mark.parametrize('requested,expected,offset', [(2, 2, 50), (999, 3, 100), (-10, 1, 0)])
def test_database_page_is_bounded_and_clamped(monkeypatch, requested, expected, offset):
    cur = Cursor()
    monkeypatch.setattr(queries, 'get_cursor', lambda: cur)
    result = queries.fetch_dashboard_users_page(page=requested, per_page=10000)
    assert result['page'] == expected
    assert result['total'] == 123
    assert result['pending_count'] == 73
    assert cur.calls[1][1][-2:] == (50, offset)
    assert 'ORDER BY u.created_at DESC, u.id DESC LIMIT %s OFFSET %s' in cur.calls[1][0]
    assert "IS DISTINCT FROM 'pending'" in cur.calls[0][0]


def test_search_and_filters_applied_before_count_and_limit(monkeypatch):
    cur = Cursor()
    monkeypatch.setattr(queries, 'get_cursor', lambda: cur)
    queries.fetch_dashboard_users_page(search="Sekolah 100%_O'Brien", role='sekolah', status='approved')
    for sql, params in cur.calls[:2]:
        assert 'ILIKE %s' in sql and 'u.role = %s' in sql and 'u.account_status = %s' in sql
        assert 's.npsn' in sql and "s.metadata->>'coordinator_phone'" in sql
        assert "O'Brien" not in sql
        assert params[:3] == ('sekolah', 'approved', "%Sekolah 100\\%\\_O'Brien%")


def test_pending_page_ignores_nonpending_status(monkeypatch):
    cur = Cursor(total=0)
    monkeypatch.setattr(queries, 'get_cursor', lambda: cur)
    result = queries.fetch_dashboard_users_page(pending=True, status='approved', page=5)
    assert result['page'] == result['pages'] == 1
    assert "u.account_status = 'pending'" in cur.calls[1][0]
    assert 'approved' not in cur.calls[1][1]


def test_preview_accounts_are_filtered_and_paginated_in_database(monkeypatch):
    cur = Cursor(total=120)
    monkeypatch.setattr(queries, 'get_cursor', lambda: cur)
    result = queries.fetch_preview_accounts_page(
        page=2,
        per_page=500,
        search='Sekolah 100%_A',
        pinned_ids=[99, '100', 'bad'],
    )
    assert result['page'] == 2
    assert result['per_page'] == 50
    assert result['pages'] == 3
    count_sql, count_params = cur.calls[0]
    page_sql, page_params = cur.calls[1]
    assert "u.role = ANY(%s)" in count_sql
    assert "u.account_status = 'approved'" in count_sql
    assert "u.merged_to IS NULL" in count_sql
    assert 'ILIKE %s' in count_sql
    assert count_params == (
        ['staff', 'coordinator', 'sekolah'],
        '%Sekolah 100\\%\\_A%',
    )
    assert 'CASE WHEN u.id = ANY(%s) THEN 0 ELSE 1 END' in page_sql
    assert page_params[-3:] == ([99, 100], 50, 50)


@pytest.mark.parametrize(
    'overrides,allowed',
    [
        ({}, True),
        ({'role': 'admin'}, False),
        ({'account_status': 'pending'}, False),
        ({'merged_to': 9}, False),
    ],
)
def test_preview_target_lookup_fetches_only_requested_user(monkeypatch, overrides, allowed):
    row = account(7000)
    row.update(overrides)
    detail = Mock(return_value=row)
    monkeypatch.setattr(portal_routes, 'get_dashboard_user_detail', detail)
    result = portal_routes._find_preview_target(7000)
    assert bool(result) is allowed
    detail.assert_called_once_with(7000)


def test_preview_workspace_uses_page_result_and_keeps_off_page_target(app, monkeypatch):
    fetch = Mock(return_value=dict(
        users=[account(i) for i in range(51, 101)],
        total=5000,
        page=2,
        pages=100,
        per_page=50,
    ))
    monkeypatch.setattr(portal_routes, 'fetch_preview_accounts_page', fetch)
    monkeypatch.setattr(portal_routes, 'list_preview_pins', lambda _: [80])
    monkeypatch.setattr(portal_routes, '_find_preview_target', lambda user_id: account(user_id))
    captured = {}

    def fake_render(template, **context):
        captured.update(template=template, **context)
        return 'ok'

    monkeypatch.setattr(portal_routes, 'render_template', fake_render)
    with app.test_request_context('/dashboard/pengaturan/preview-akun?page=2&q=Sekolah'):
        session['user'] = dict(id=7, role='admin', full_name='Admin')
        session[portal_routes._PREVIEW_TARGET_SESSION_KEY] = account(7000)
        response = portal_routes._render_preview_accounts()
    assert response == 'ok'
    assert captured['template'] == 'portal/admin/preview_workspace.html'
    assert len(captured['preview_users']) == 50
    assert captured['preview_target']['id'] == 7000
    assert captured['preview_search'] == 'Sekolah'
    assert captured['preview_pagination']['page'] == 2
    fetch.assert_called_once_with(page=2, search='Sekolah', pinned_ids=[80])


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test-only'
    app.register_blueprint(pengaturan_bp)
    app.add_url_rule('/login', 'auth.login', lambda: 'login')
    app.add_url_rule('/portal/', 'portal.home', lambda: 'portal')
    app.add_url_rule('/schools/search', 'portal.search_schools_api', lambda: '')
    app.add_url_rule('/admin/select-role', 'main.admin_select_role', lambda: 'admin')
    app.jinja_loader = ChoiceLoader([
        DictLoader({'pengaturan/base_pengaturan.html': '{% block content %}{% endblock %}{% block scripts %}{% endblock %}'}),
        FileSystemLoader(str(ROOT / 'dashboard/portal/templates')),
    ])
    app.jinja_env.globals['csrf_token'] = lambda: 'test-csrf'
    app.jinja_env.filters['jakarta'] = lambda value, *args: str(value)
    monkeypatch.setattr(portal_routes, 'current_user', lambda: session.get('user'))
    monkeypatch.setattr(user_management, 'list_kecamatan', lambda: [])
    monkeypatch.setattr(user_management, 'fetch_activity_logs', lambda **kwargs: [])
    monkeypatch.setattr(user_management, 'fetch_dashboard_users_page', lambda **kwargs: dict(
        users=[account(i, 'pending' if kwargs.get('pending') else 'approved') for i in range(51, 101)],
        total=5000, page=kwargs.get('page', 1), pages=100, per_page=50, pending_count=73))
    return app


def login(client, role='admin'):
    with client.session_transaction() as state:
        state['user'] = dict(id=7, role=role, full_name='Admin')


@pytest.mark.parametrize('tab,needle', [('list', 'user-row="true"'), ('verify', 'id="pending-user-')])
def test_template_renders_only_page_and_preserves_navigation(app, tab, needle):
    client = app.test_client()
    login(client)
    response = client.get(URL + f'?tab={tab}&page=2&q=User&role=staff')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count(needle) == 50
    assert 'Halaman 2 dari 100' in html
    assert 'page=3' in html and 'q=User' in html and 'role=staff' in html
    assert 'data-count="73"' in html
    assert 'loadUserAction(51, "edit")' in html
    assert "editUser({" not in html
    assert html.count('<option value="51">') == 0  # No eager merge account lists.
    assert len(response.data) < 500_000


def test_detail_not_found_and_lookup_preserve_access_control(app, monkeypatch):
    detail = Mock(return_value=account(7000))
    monkeypatch.setattr(user_management, 'get_dashboard_user_detail', detail)
    client = app.test_client()
    assert client.get(URL + '?lookup=detail&user_id=7000').status_code == 302
    login(client, 'staff')
    assert client.get(URL + '?lookup=detail&user_id=7000').status_code == 302
    detail.assert_not_called()
    login(client)
    response = client.get(URL + '?lookup=detail&user_id=7000')
    assert response.json['user']['id'] == 7000
    assert response.headers['Cache-Control'] == 'no-store'
    detail.return_value = None
    assert client.get(URL + '?lookup=detail&user_id=99999').status_code == 404
    assert client.get(URL + '?lookup=detail&user_id=bad').status_code == 404


def test_detail_query_explicit_fields_and_single_user(monkeypatch):
    cur = Cursor()
    cur.fetchone = lambda: account(7000)
    monkeypatch.setattr(queries, 'get_cursor', lambda: cur)
    assert queries.get_dashboard_user_detail(7000)['id'] == 7000
    sql, params = cur.calls[0]
    assert 'WHERE u.id = %s' in sql and params == (7000,)
    assert 'password' not in sql and 'u.*' not in sql


def test_merge_lookup_searches_database_with_status_and_limit(app, monkeypatch):
    fetch = Mock(return_value=dict(users=[account(7000)], total=200))
    monkeypatch.setattr(user_management, 'fetch_dashboard_users_page', fetch)
    client = app.test_client()
    login(client)
    response = client.get(URL + '?lookup=merge&status=not_registered&q=OutsidePage')
    assert response.status_code == 200
    assert response.json['users'][0]['id'] == 7000
    fetch.assert_called_once_with(search='OutsidePage', status='not_registered', per_page=20)
    assert client.get(URL + '?lookup=merge&status=pending').status_code == 400


@pytest.mark.parametrize('action', ['create', 'update', 'verify', 'reset_password', 'merge'])
def test_existing_mutations_remain_available(app, monkeypatch, action):
    create = Mock(return_value=7000)
    monkeypatch.setattr(user_management, 'create_dashboard_user', create)
    update = Mock(return_value=True)
    merge = Mock(return_value={})
    monkeypatch.setattr(user_management, 'update_dashboard_user', update)
    monkeypatch.setattr(user_management, 'merge_dashboard_users', merge)
    monkeypatch.setattr(user_management, 'get_dashboard_user_profile', lambda _: account(7000))
    monkeypatch.setattr(user_management, 'log_activity', lambda *args, **kwargs: None)
    monkeypatch.setattr(user_management, 'notify_verification_status_update', lambda *args, **kwargs: None)
    client = app.test_client()
    login(client)
    response = client.post(URL + '?tab=verify&page=2', data=dict(
        action=action, user_id='7000', full_name='Updated', email='u@example.invalid',
        role='staff', account_status='approved', old_user_id='8000', new_user_id='7000',
        password='test-password' if action == 'create' else ''),
        headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200
    if action == 'create':
        assert create.call_args.kwargs['email'] == 'u@example.invalid'
    elif action == 'merge':
        merge.assert_called_once_with(8000, 7000, merged_by=7)
    else:
        assert update.call_args.kwargs['user_id'] == 7000
        if action == 'reset_password': assert update.call_args.kwargs['password_hash'].startswith('pbkdf2:sha256:')
        if action == 'verify': assert response.json['success'] is True


def test_preview_mode_cannot_mutate_or_search_merge(app, monkeypatch):
    monkeypatch.setattr(portal_routes, '_is_preview_read_only_session', lambda: True)
    client = app.test_client()
    login(client)
    assert client.get(URL + '?lookup=merge&status=approved').status_code == 403
    response = client.post(URL, data={'action': 'merge'}, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 403
