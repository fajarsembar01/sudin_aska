import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from flask import Flask, render_template
from jinja2 import FileSystemLoader

from dashboard.pengaturan import routes


class BackupHistoryTests(unittest.TestCase):
    path = '/dashboard/pengaturan/history-back-up'

    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-only'
        self.app.config['TESTING'] = True
        self.app.register_blueprint(routes.pengaturan_bp)
        for endpoint in ('auth.login', 'auth.logout', 'portal.home', 'portal.sekolah_home'):
            self.app.add_url_rule('/' + endpoint.replace('.', '/'), endpoint, lambda: '')
        self.client = self.app.test_client()
        self.now = datetime(2026, 10, 23, 0, 5, tzinfo=timezone(timedelta(hours=7)))
        self.user = {'id': 99, 'role': 'admin', 'full_name': 'Admin Satu', 'email': 'admin@example.com'}
        self.history = {'entries': [], 'total': 0, 'page': 1, 'pages': 1}
        self.route_user = self.start_patch('current_user', return_value=self.user)
        auth_patch = patch('dashboard.auth.current_user', return_value=self.user)
        self.auth_user = auth_patch.start()
        self.addCleanup(auth_patch.stop)
        self.clock = self.start_patch('current_jakarta_time', return_value=self.now)
        self.claim = self.start_patch('claim_admin_backup', return_value={'id': 12})
        self.audit = self.start_patch('record_admin_action')
        self.status = self.start_patch(
            'get_admin_backup_status', return_value={'own_claim': None, 'total_today': 0})
        self.fetch = self.start_patch('fetch_admin_backup_history', return_value=self.history)
        self.render = self.start_patch('render_template', return_value='history')

    def start_patch(self, name, **kwargs):
        item = patch.object(routes, name, **kwargs)
        value = item.start()
        self.addCleanup(item.stop)
        return value

    def flashes(self):
        with self.client.session_transaction() as session:
            return session.get('_flashes', [])

    def test_claim_uses_logged_in_admin_and_jakarta_date_ignoring_form_values(self):
        # Jakarta is already October 23 while UTC is still October 22.
        self.assertEqual(self.now.astimezone(timezone.utc).date(), date(2026, 10, 22))
        response = self.client.post(self.path, data={
            'action': 'claim_backup', 'admin_user_id': '7', 'admin_id': '7',
            'backup_date': '2000-01-01', 'claimed_at': '2000-01-01T12:00:00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location.split('?')[0], self.path)
        self.claim.assert_called_once_with(
            admin_user_id=99, backup_date=date(2026, 10, 23), claimed_at=self.now)
        self.audit.assert_called_once()
        audit = self.audit.call_args.kwargs
        self.assertEqual(audit['user_id'], 99)
        self.assertEqual(audit['feature_key'], 'backup_history')
        self.assertEqual(audit['action'], 'CREATE')
        self.assertEqual(audit['target_type'], 'BACKUP_CLAIM')
        self.assertEqual(audit['target_id'], 12)
        self.assertIn('23/10/2026', audit['target_name'])
        self.assertEqual(audit['metadata']['backup_date'], '2026-10-23')
        self.assertTrue(any(category == 'success' for category, _ in self.flashes()))

    def test_duplicate_claim_does_not_create_another_audit_event(self):
        self.claim.return_value = None
        response = self.client.post(self.path, data={'action': 'claim_backup'})
        self.assertEqual(response.status_code, 302)
        self.claim.assert_called_once()
        self.audit.assert_not_called()
        self.assertTrue(self.flashes())

    def test_unknown_action_does_not_write(self):
        response = self.client.post(self.path, data={'action': 'delete_claim', 'id': 12})
        self.assertEqual(response.status_code, 302)
        self.claim.assert_not_called()
        self.audit.assert_not_called()
        self.assertTrue(any(category == 'warning' for category, _ in self.flashes()))

    def test_default_history_uses_current_month_and_own_daily_status(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.status.assert_called_once_with(admin_user_id=99, backup_date=date(2026, 10, 23))
        self.fetch.assert_called_once_with(
            start=date(2026, 10, 1), end=date(2026, 11, 1), page=1, page_size=20)
        self.render.assert_called_once()
        self.assertEqual(self.render.call_args.args[0], 'pengaturan/backup_history.html')
        context = self.render.call_args.kwargs
        self.assertEqual(context['today'], date(2026, 10, 23))
        self.assertEqual(context['selected_month'], '2026-10')
        self.assertEqual(context['today_status'], {'own_claim': None, 'total_today': 0})
        self.assertEqual(context['history'], self.history)

    def test_december_filter_ends_at_next_january_and_preserves_page(self):
        response = self.client.get(self.path + '?month=2025-12&page=3')
        self.assertEqual(response.status_code, 200)
        self.fetch.assert_called_once_with(
            start=date(2025, 12, 1), end=date(2026, 1, 1), page=3, page_size=20)
        self.assertEqual(self.render.call_args.kwargs['selected_month'], '2025-12')
        # Browsing an old month must not change which date can be claimed today.
        self.status.assert_called_once_with(admin_user_id=99, backup_date=date(2026, 10, 23))

    def test_invalid_month_falls_back_to_current_month(self):
        for month in ('invalid', '2026-13'):
            with self.subTest(month=month):
                self.fetch.reset_mock()
                response = self.client.get(self.path, query_string={'month': month})
                self.assertEqual(response.status_code, 200)
                self.fetch.assert_called_once_with(
                    start=date(2026, 10, 1), end=date(2026, 11, 1), page=1, page_size=20)
                self.assertEqual(self.render.call_args.kwargs['selected_month'], '2026-10')
                self.assertTrue(any(category == 'warning' for category, _ in self.flashes()))

    def test_invalid_or_negative_page_is_clamped_to_first_page(self):
        for page in ('invalid', '0', '-3'):
            with self.subTest(page=page):
                self.fetch.reset_mock()
                response = self.client.get(self.path, query_string={'page': page})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.fetch.call_args.kwargs['page'], 1)

    def test_unauthenticated_get_and_post_redirect_to_login_without_data_access(self):
        self.auth_user.return_value = None
        self.route_user.return_value = None
        for method in ('get', 'post'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.path)
                self.assertEqual(response.status_code, 302)
                self.assertIn('/auth/login', response.location)
        self.claim.assert_not_called()
        self.status.assert_not_called()
        self.fetch.assert_not_called()

    def test_non_admin_roles_cannot_view_or_claim(self):
        for role in ('coordinator', 'staff', 'sekolah'):
            self.auth_user.return_value = {'id': 7, 'role': role}
            self.route_user.return_value = self.auth_user.return_value
            for method in ('get', 'post'):
                with self.subTest(role=role, method=method):
                    response = getattr(self.client, method)(
                        self.path, data={'action': 'claim_backup'})
                    self.assertEqual(response.status_code, 302)
        self.claim.assert_not_called()
        self.status.assert_not_called()
        self.fetch.assert_not_called()
        self.audit.assert_not_called()

    def use_actual_template(self):
        dashboard_dir = Path(__file__).resolve().parents[1]
        self.app.jinja_loader = FileSystemLoader([
            str(dashboard_dir / 'templates'),
            str(dashboard_dir / 'portal' / 'templates'),
            str(dashboard_dir / 'pengaturan' / 'templates'),
        ])

        def template_url(endpoint, **values):
            path = self.path if endpoint == 'pengaturan.backup_history' else '/' + endpoint.replace('.', '/')
            return path + ('?' + urlencode(values) if values else '')

        self.app.jinja_env.globals.update(url_for=template_url, csrf_token=lambda: 'test-csrf')
        self.app.jinja_env.filters['jakarta'] = lambda value, fmt: value.strftime(fmt)
        self.app.context_processor(lambda: {'current_user': self.user})
        self.render.side_effect = render_template

    def test_full_template_renders_empty_history_and_claim_form(self):
        self.use_actual_template()
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="themeToggle"', html)
        self.assertIn('History Back Up', html)
        self.assertIn('Belum ada klaim back up pada bulan ini.', html)
        self.assertIn('Saya sudah back up data hari ini', html)
        self.assertIn('name="action" value="claim_backup"', html)
        self.assertIn('name="csrf_token" value="test-csrf"', html)

    def test_full_template_renders_claimed_status_history_and_month_pagination(self):
        self.use_actual_template()
        claim = {'id': 12, 'admin_user_id': 99, 'backup_date': self.now.date(),
                 'claimed_at': self.now, 'full_name': '<Admin Satu>', 'email': 'admin@example.com'}
        self.status.return_value = {'own_claim': claim, 'total_today': 2}
        self.fetch.return_value = {'entries': [claim], 'total': 21, 'page': 1, 'pages': 2}
        response = self.client.get(self.path + '?month=2026-10')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Sudah diklaim hari ini', html)
        self.assertNotIn('name="action" value="claim_backup"', html)
        self.assertIn('2 admin sudah mengklaim hari ini.', html)
        self.assertIn('&lt;Admin Satu&gt;', html)
        self.assertIn('admin@example.com', html)
        self.assertIn('23/10/2026', html)
        self.assertIn('00:05:00', html)
        self.assertIn('month=2026-10&amp;page=2', html)


if __name__ == '__main__':
    unittest.main()
