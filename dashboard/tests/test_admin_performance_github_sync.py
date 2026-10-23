import io
import json
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from flask import Flask
from jinja2 import Environment
from werkzeug.datastructures import MultiDict

from dashboard.pengaturan import routes
from dashboard.pengaturan import github_performance as github


class AdminPerformanceGitHubSyncTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-only'
        self.app.register_blueprint(routes.pengaturan_bp)
        self.client = self.app.test_client()
        self.accounts = [
            dict(id=1, full_name='Admin Satu', github_username='one'),
            dict(id=2, full_name='Admin Dua', github_username='two'),
            dict(id=3, full_name='Belum Terhubung', github_username=None),
        ]
        self.patches = [
            patch.object(routes, 'current_user', return_value={'id': 99, 'role': 'admin'}),
            patch('dashboard.auth.current_user', return_value={'id': 99, 'role': 'admin'}),
            patch.object(routes, 'get_system_setting', return_value='owner/repo'),
            patch.object(routes, 'list_admin_github_accounts', return_value=self.accounts),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def post(self, ids):
        data = MultiDict([('sync_admin_ids', value) for value in ids])
        data.update({'feature': 'all', 'period_scope': 'month', 'month': '2026-10',
                     'quarter': '4', 'year': '2026', 'admin_id': '1'})
        return self.client.post('/dashboard/pengaturan/admin-performance/github-sync', data=data)

    def messages(self):
        with self.client.session_transaction() as session:
            return ' '.join(message for _category, message in session.get('_flashes', []))

    def test_sync_only_selected_admin_and_preserve_report_filters(self):
        with patch.object(routes, 'sync_admin_commits', return_value={'inserted': 3}) as sync, \
             patch.object(routes, 'hydrate_commit_line_stats') as hydrate:
            response = self.post(['2', '2'])
        sync.assert_called_once_with('owner/repo', 'two', synced_by=99, author_email='')
        hydrate.assert_called_once_with('owner/repo', 'two', start=None, end=None)
        self.assertEqual(response.status_code, 302)
        self.assertIn('month=2026-10', response.location)
        self.assertIn('admin_id=1', response.location)
        self.assertIn('1 admin; 3 commit', self.messages())

    def test_empty_invalid_or_unmapped_selection_never_calls_github(self):
        for ids in ([], ['invalid'], ['3'], ['999'], ['1', '999']):
            with self.subTest(ids=ids), patch.object(routes, 'sync_admin_commits') as sync:
                self.assertEqual(self.post(ids).status_code, 302)
                sync.assert_not_called()

    def test_shared_limit_or_bad_token_stops_remaining_admins(self):
        for error_type in (github.GitHubRateLimitError, github.GitHubAuthenticationError):
            with self.subTest(error_type=error_type), \
                 patch.object(routes, 'sync_admin_commits', side_effect=error_type('Coba nanti')) as sync, \
                 patch.object(routes, 'hydrate_commit_line_stats') as hydrate:
                self.post(['1', '2'])
                sync.assert_called_once()
                hydrate.assert_not_called()
                self.assertIn('1 admin terpilih belum diproses', self.messages())

    def test_account_specific_failure_continues_other_selected_admin(self):
        with patch.object(routes, 'sync_admin_commits', side_effect=[RuntimeError('Tidak ditemukan'), {'inserted': 1}]) as sync, \
             patch.object(routes, 'hydrate_commit_line_stats'):
            self.post(['1', '2'])
        self.assertEqual(sync.call_count, 2)
        self.assertIn('1 admin; 1 commit', self.messages())

    def test_picker_renders_only_connected_accounts(self):
        source = Path('dashboard/templates/admin_performance.html').read_text()
        start = source.index('<div class="collapse" id="codingSync">')
        end = source.index('<div class="collapse" id="codingSettings">', start)
        env = Environment(autoescape=True)
        env.filters['jakarta'] = str
        html = env.from_string(source[start:end]).render(
            performance={'github': {'accounts': self.accounts}, 'selected_admin_id': 2},
            csrf_token=lambda: '', url_for=lambda *args: '/sync')
        self.assertIn('id="syncAdmin1"', html)
        self.assertIn('id="syncAdmin2" checked', html)
        self.assertNotIn('id="syncAdmin3"', html)


class GitHubHttpErrorTests(unittest.TestCase):
    def error(self, status, headers=None, message=''):
        response_headers = Message()
        for key, value in (headers or {}).items():
            response_headers[key] = value
        return HTTPError('https://api.github.com/test', status, 'Error', response_headers,
                         io.BytesIO(json.dumps({'message': message}).encode()))

    def test_rate_limit_reset_is_shown_in_jakarta_time(self):
        error = github._github_http_error(self.error(403, {
            'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '0'}))
        self.assertIsInstance(error, github.GitHubRateLimitError)
        self.assertIn('01/01/1970 07:00:00 WIB', str(error))

    def test_secondary_limit_and_retry_after(self):
        error = github._github_http_error(self.error(429, {'Retry-After': '60'}))
        self.assertIsInstance(error, github.GitHubRateLimitError)
        self.assertIn('60 detik', str(error))
        self.assertIsInstance(github._github_http_error(self.error(
            403, message='You have exceeded a secondary rate limit.')), github.GitHubRateLimitError)

    def test_access_denied_is_distinct_from_rate_limit(self):
        error = github._github_http_error(self.error(403, message='Resource not accessible'))
        self.assertNotIsInstance(error, github.GitHubRateLimitError)
        self.assertIn('izin', str(error))
        self.assertIsInstance(github._github_http_error(self.error(401)), github.GitHubAuthenticationError)

    def test_both_request_paths_propagate_rate_limit(self):
        for request in (
            lambda: github._request_commit_page('owner/repo', 'one', since=None, page=1),
            lambda: github._request_github_json('https://api.github.com/test'),
        ):
            with self.subTest(request=request), patch.object(github, 'urlopen', side_effect=self.error(429)):
                with self.assertRaises(github.GitHubRateLimitError):
                    request()

    def test_failed_sync_keeps_checkpoint_and_records_error(self):
        with patch.object(github, 'get_last_sync', return_value=None), \
             patch.object(github, 'fetch_commit_batches', side_effect=github.GitHubRateLimitError('Limit')), \
             patch.object(github, '_save_sync_state') as save:
            with self.assertRaises(github.GitHubRateLimitError):
                github.sync_admin_commits('owner/repo', 'one', synced_by=99)
        self.assertIsNone(save.call_args.kwargs['synced_at'])
        self.assertEqual(save.call_args.kwargs['error'], 'Limit')


if __name__ == '__main__':
    unittest.main()
