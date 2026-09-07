from flask import Flask
import pytest

from dashboard.auth import auth_bp
from dashboard.call_center import call_center_bp, routes
from dashboard.call_center import access
from dashboard.portal import routes as portal_routes


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test-only'
    app.register_blueprint(auth_bp)
    app.register_blueprint(call_center_bp)
    monkeypatch.setattr(access, 'ensure_access_schema', lambda: None)
    return app


def login(client, role):
    with client.session_transaction() as session:
        session['user'] = {'id': 7, 'role': role}


def test_revoked_staff_denied_next_request(app, monkeypatch):
    permitted = [True]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args): pass
        def fetchone(self): return (1,) if permitted[0] else None
    monkeypatch.setattr(access, 'get_cursor', lambda: Cursor())
    monkeypatch.setattr(routes, 'fetch_cc_messages', lambda *args, **kwargs: [])
    client = app.test_client()
    login(client, 'staff')
    assert client.get('/call-center/api/messages/1').status_code == 200
    permitted[0] = False
    assert client.get('/call-center/api/messages/1').status_code == 403
    assert client.post('/call-center/api/send', json={}).status_code == 403


def test_unauthenticated_send_requires_login(app):
    assert app.test_client().post('/call-center/api/send', json={}).status_code == 401


def test_school_cannot_answer(app):
    client = app.test_client()
    login(client, 'sekolah')
    assert client.get('/call-center/api/messages/1').status_code == 403


def test_staff_cannot_manage_access(app, monkeypatch):
    # Existing role_required redirects unauthorized users to their portal home.
    monkeypatch.setattr('dashboard.auth.url_for', lambda *args, **kwargs: '/portal/')
    monkeypatch.setattr(routes, 'update_staff_access', lambda *args, **kwargs: pytest.fail('Unauthorized mutation'))
    client = app.test_client()
    login(client, 'staff')
    for path in ['/call-center/staff-access', '/call-center/settings/wa', '/call-center/settings/telegram', '/call-center/api/media-delete']:
        assert client.post(path, data={'action': 'grant', 'user_ids': '7'}).status_code == 302


def test_admin_can_grant_multiple_staff(app, monkeypatch):
    changes = []
    monkeypatch.setattr(routes, 'update_staff_access', lambda ids, **kwargs: changes.append((ids, kwargs)))
    client = app.test_client()
    login(client, 'admin')
    response = client.post('/call-center/staff-access', data={'action': 'grant', 'user_ids': ['2', '3', '2']})
    assert response.status_code == 302
    assert changes == [({2, 3}, {'grant': True, 'actor_id': 7})]


def test_invalid_action_does_not_mutate(app, monkeypatch):
    monkeypatch.setattr(routes, 'update_staff_access', lambda *args, **kwargs: pytest.fail('Invalid mutation'))
    client = app.test_client()
    login(client, 'admin')
    assert client.post('/call-center/staff-access', data={'action': 'invalid', 'user_ids': '2'}).status_code == 302


def test_staff_portal_shows_call_center_entry_when_access_granted(app, monkeypatch):
    monkeypatch.setattr(portal_routes, '_require_profile_photo_redirect', lambda _user: None)
    monkeypatch.setattr(access, 'can_answer_call_center', lambda: True)
    monkeypatch.setattr(portal_routes, '_staff_can_view_laporan_answers', lambda _user: False)
    monkeypatch.setattr(portal_routes, 'url_for', lambda endpoint, **_kwargs: '/' + endpoint)
    monkeypatch.setattr(portal_routes, 'render_template', lambda _template, **context: context)
    with app.test_request_context('/portal/'):
        from flask import session
        session['user'] = {'id': 7, 'role': 'staff', 'full_name': 'Staff Uji'}
        context = portal_routes.home.__wrapped__()

    call_center_cards = [card for card in context['cards'] if card['title'] == 'Call Center']
    assert len(call_center_cards) == 1
    assert call_center_cards[0]['href'] == '/call_center.inbox'


@pytest.mark.parametrize('users', [
    [{'id': 2, 'role': 'sekolah', 'account_status': 'approved'}],
    [{'id': 2, 'role': 'staff', 'account_status': 'suspended'}],
    [],
])
def test_grant_rejects_ineligible_users_atomically(monkeypatch, users):
    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, *args): statements.append(sql.strip())
        def fetchall(self): return users
    monkeypatch.setattr(access, 'ensure_access_schema', lambda: None)
    monkeypatch.setattr(access, 'get_cursor', lambda **kwargs: Cursor())
    with pytest.raises(ValueError):
        access.update_staff_access({2}, grant=True, actor_id=1)
    assert len(statements) == 1
    assert statements[0].startswith('SELECT')
