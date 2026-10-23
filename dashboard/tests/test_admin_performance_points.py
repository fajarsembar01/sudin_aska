import io
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import Flask

from dashboard import queries
from dashboard.pengaturan import routes


WIB = timezone(timedelta(hours=7))


def activity(feature, target, *, actor=1, day=23, month=10, action='CREATE', source=None):
    return queries._normalize_admin_performance_event({
        'source': source or feature,
        'feature_key': feature,
        'target_type': target,
        'action': action,
        'actor_user_id': actor,
        'actor_name': f'Admin {actor}',
        'actor_email': f'admin{actor}@example.com',
        'target_id': day,
        'target_name': f'{feature} {day}',
        'created_at': datetime(2026, month, day, 9, tzinfo=WIB),
    })


def mixed_activities():
    return [
        activity('monev_bos', 'MONEV_REPORT', day=20),
        activity('backup_history', 'BACKUP_CLAIM', action='CLAIM', source='admin_backup_claims'),
        activity('meeting_attendance', 'MEETING_ATTENDANCE', day=22,
                 action='ATTEND', source='admin_meeting_attendance'),
        activity('meeting_attendance', 'MEETING', day=22),
        activity('backup_history', 'BACKUP_CLAIM', actor=2,
                 action='CLAIM', source='admin_backup_claims'),
        activity('meeting_attendance', 'MEETING_ATTENDANCE', actor=2, month=9, day=30,
                 action='ATTEND', source='admin_meeting_attendance'),
    ]


class AdminPerformancePointsTests(unittest.TestCase):
    def test_ordinary_action_backup_and_attendance_total_eleven_points_for_three_events(self):
        data = queries.fetch_admin_performance_data(source_events=mixed_activities()[:3])
        self.assertEqual(data['summary']['total_actions'], 3)
        self.assertEqual(data['summary']['action_points'], 11)
        self.assertEqual(data['summary']['feature_points'], {
            'monev_bos': 1, 'backup_history': 5, 'meeting_attendance': 5,
        })
        row = data['leaderboard'][0]
        self.assertEqual(row['actor_user_id'], 1)
        self.assertEqual(row['total_actions'], 3)
        self.assertEqual(row['action_points'], 11)
        self.assertEqual(row['feature_points'], data['summary']['feature_points'])
        self.assertEqual([event['points'] for event in data['detail_rows']], [1, 5, 5])

    def test_meeting_management_audit_does_not_count_as_attendance_or_points(self):
        data = queries.fetch_admin_performance_data(source_events=[
            activity('meeting_attendance', 'MEETING', action=action)
            for action in ('CREATE', 'UPDATE', 'DELETE')
        ])
        self.assertEqual(data['summary']['total_actions'], 0)
        self.assertEqual(data['summary']['action_points'], 0)
        self.assertEqual(data['leaderboard'], [])

    def test_creator_gets_one_activity_separate_from_attendance_and_repeated_saves(self):
        events = [
            activity('meeting_creation', 'MEETING', source='admin_meetings'),
            activity('meeting_attendance', 'MEETING_ATTENDANCE', action='ATTEND',
                     source='admin_meeting_attendance'),
        ]
        events.extend(activity('meeting_attendance', 'MEETING', action=action,
                               source='dashboard_admin_action_logs')
                      for action in ('CREATE', 'UPDATE', 'UPDATE', 'DELETE'))
        data = queries.fetch_admin_performance_data(source_events=events)
        row = data['leaderboard'][0]
        self.assertEqual(row['total_actions'], 2)
        self.assertEqual(row['action_points'], 6)
        self.assertEqual(row['feature_counts'], {'meeting_creation': 1, 'meeting_attendance': 1})
        self.assertEqual(row['feature_points'], {'meeting_creation': 1, 'meeting_attendance': 5})
        creator_only = queries.fetch_admin_performance_data(source_events=events, feature_key='meeting_creation')
        self.assertEqual(creator_only['summary']['total_actions'], 1)
        self.assertEqual(creator_only['summary']['action_points'], 1)

    def test_one_meeting_with_management_and_repeated_saves_counts_one_attendance(self):
        events = [activity('meeting_attendance', 'MEETING', action=action,
                           source='dashboard_admin_action_logs')
                  for action in ('CREATE', 'UPDATE', 'DELETE')]
        events.extend(activity('meeting_attendance', 'MEETING_ATTENDANCE', action='UPDATE',
                               source='dashboard_admin_action_logs') for _ in range(3))
        events.append(activity('meeting_attendance', 'MEETING_ATTENDANCE', action='ATTEND',
                               source='admin_meeting_attendance'))
        data = queries.fetch_admin_performance_data(source_events=events)
        self.assertEqual(data['summary']['total_actions'], 1)
        self.assertEqual(data['summary']['action_points'], 5)
        self.assertEqual(data['leaderboard'][0]['feature_counts'], {'meeting_attendance': 1})

    def test_audit_copies_do_not_double_count_canonical_claim_and_attendance(self):
        events = mixed_activities()[:3]
        events.extend([
            activity('backup_history', 'BACKUP_CLAIM', source='dashboard_admin_action_logs'),
            activity('meeting_attendance', 'MEETING_ATTENDANCE', day=22,
                     action='SAVE', source='dashboard_admin_action_logs'),
        ])
        data = queries.fetch_admin_performance_data(source_events=events)
        self.assertEqual(data['summary']['total_actions'], 3)
        self.assertEqual(data['summary']['action_points'], 11)
        self.assertNotIn('dashboard_admin_action_logs', {
            event['source'] for event in data['detail_rows']
        })

    def test_feature_admin_and_period_filters_each_apply_to_points_and_event_counts(self):
        cases = [
            ({'feature_key': 'backup_history'}, 2, 10),
            ({'admin_id': 2}, 2, 10),
            ({'start': datetime(2026, 10, 1), 'end': datetime(2026, 10, 31)}, 4, 16),
            ({'start': datetime(2026, 10, 23), 'end': datetime(2026, 10, 23)}, 2, 10),
            ({'feature_key': 'meeting_attendance', 'admin_id': 1,
              'start': datetime(2026, 10, 1), 'end': datetime(2026, 10, 31)}, 1, 5),
        ]
        for filters, expected_count, expected_points in cases:
            with self.subTest(filters=filters):
                data = queries.fetch_admin_performance_data(source_events=mixed_activities(), **filters)
                self.assertEqual(data['summary']['total_actions'], expected_count)
                self.assertEqual(data['summary']['action_points'], expected_points)
                self.assertEqual(sum(row['action_points'] for row in data['leaderboard']), expected_points)
                self.assertEqual(sum(row['total_actions'] for row in data['leaderboard']), expected_count)

    def test_weighted_actions_rank_above_a_larger_number_of_ordinary_actions(self):
        events = [activity('monev_bos', 'MONEV_REPORT', actor=1, day=day) for day in range(1, 9)]
        events.extend([
            activity('backup_history', 'BACKUP_CLAIM', actor=2, action='CLAIM', source='admin_backup_claims'),
            activity('meeting_attendance', 'MEETING_ATTENDANCE', actor=2,
                     action='ATTEND', source='admin_meeting_attendance'),
        ])
        data = queries.fetch_admin_performance_data(source_events=events)
        self.assertEqual([row['actor_user_id'] for row in data['leaderboard']], [2, 1])
        scored = routes._score_admin_leaderboard(data['leaderboard'])
        self.assertEqual([row['actor_user_id'] for row in scored], [2, 1])
        self.assertEqual([row['performance_total'] for row in scored], [10, 8])

    def test_coding_days_add_ten_points_to_weighted_actions(self):
        rows = [
            {'actor_user_id': 1, 'actor_label': 'Admin 1', 'total_actions': 8,
             'action_points': 8, 'github_coding_days': 0, 'github_commits': 100},
            {'actor_user_id': 2, 'actor_label': 'Admin 2', 'total_actions': 2,
             'action_points': 10, 'github_coding_days': 1, 'github_commits': 100},
            {'actor_user_id': 3, 'actor_label': 'Admin 3', 'total_actions': 1,
             'action_points': 5, 'github_coding_days': 2, 'github_commits': 100},
        ]
        original = deepcopy(rows)
        scored = routes._score_admin_leaderboard(rows)
        self.assertEqual([row['actor_user_id'] for row in scored], [3, 2, 1])
        self.assertEqual([row['performance_total'] for row in scored], [25, 20, 8])
        self.assertEqual([row['coding_points'] for row in scored], [20, 10, 0])
        self.assertEqual(rows, original)

    def test_score_preserves_explicit_zero_and_falls_back_for_legacy_rows(self):
        scored = routes._score_admin_leaderboard([
            {'actor_user_id': 1, 'total_actions': 7, 'github_coding_days': 0},
            {'actor_user_id': 2, 'total_actions': 50, 'action_points': 0, 'github_coding_days': 0},
        ])
        self.assertEqual([row['performance_total'] for row in scored], [7, 0])
        self.assertEqual([row['action_points'] for row in scored], [7, 0])

    def test_empty_filtered_report_has_zero_points(self):
        data = queries.fetch_admin_performance_data(source_events=mixed_activities(), admin_id=999)
        self.assertEqual(data['summary']['total_actions'], 0)
        self.assertEqual(data['summary']['action_points'], 0)
        self.assertEqual(data['leaderboard'], [])


class AdminPerformancePdfPointsTests(unittest.TestCase):
    def test_personal_pdf_matches_weighted_leaderboard_and_authenticated_admin(self):
        app = Flask(__name__)
        app.secret_key = 'test-only'
        app.config['TESTING'] = True
        app.register_blueprint(routes.pengaturan_bp)
        user = {'id': 1, 'role': 'admin', 'full_name': 'Admin 1', 'email': 'admin1@example.com'}
        accounts = [
            {'id': 1, 'full_name': 'Admin 1', 'email': 'admin1@example.com'},
            {'id': 2, 'full_name': 'Admin 2', 'email': 'admin2@example.com'},
        ]
        github = {'repository': 'owner/repo', 'snapshots': {
            1: {'coding_day_count': 2, 'commit_count': 100, 'github_username': None},
            2: {'coding_day_count': 0, 'commit_count': 0, 'github_username': None},
        }}
        events = mixed_activities()
        with patch.object(routes, 'current_user', return_value=user), \
             patch('dashboard.auth.current_user', return_value=user), \
             patch.object(routes, 'current_jakarta_time', return_value=datetime(2026, 10, 23, 10, tzinfo=WIB)), \
             patch.object(routes, 'fetch_admin_activity_events', return_value=events), \
             patch.object(routes, 'fetch_admin_performance_data', wraps=queries.fetch_admin_performance_data) as aggregate, \
             patch.object(routes, 'list_admin_users', return_value=accounts), \
             patch.object(routes, '_github_performance_context', return_value=github), \
             patch.object(routes, 'build_admin_performance_pdf', return_value=io.BytesIO(b'%PDF-test')) as build:
            response = app.test_client().get(
                '/dashboard/pengaturan/admin-performance/pdf?month=2026-10&admin_id=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertEqual([call.kwargs['admin_id'] for call in aggregate.call_args_list], [None, 1])
        pdf = build.call_args.kwargs
        personal = pdf['personal']
        own_row = next(row for row in pdf['leaderboard'] if row['actor_user_id'] == 1)
        self.assertEqual(personal['summary']['total_actions'], 3)
        self.assertEqual(personal['action_points'], 11)
        self.assertEqual(personal['coding_points'], 20)
        self.assertEqual(personal['performance_total'], 31)
        self.assertEqual(own_row['performance_total'], personal['performance_total'])
        self.assertEqual(personal['organization_rank'], 1)
        self.assertEqual(pdf['leaderboard'][1]['performance_total'], 5)


class AdminPerformanceEvidenceTests(unittest.TestCase):
    def test_three_backup_claims_render_in_one_card_with_dates_and_total_points(self):
        from PIL import ImageDraw
        from dashboard.pengaturan import admin_performance_pdf as pdf

        events = [activity('backup_history', 'BACKUP_CLAIM', day=day,
                           source='admin_backup_claims') for day in (21, 22, 23)]
        grouped = pdf._summarize_backup_activities(events)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]['points'], 15)
        self.assertEqual(len(grouped[0]['backup_entries']), 3)

        labels = []
        original_text = ImageDraw.ImageDraw.text
        def capture(draw, xy, value, *args, **kwargs):
            labels.append(str(value))
            return original_text(draw, xy, value, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, 'text', capture):
            pages = pdf._draw_backup_attendance_pages(
                {'backup_attendance_rows': events}, period_label='Oktober 2026',
                generated_at=events[-1]['created_at'], first_page_number=3)
        self.assertEqual(len(pages), 1)
        self.assertEqual(labels.count('Klaim Back Up - 3 kali'), 1)
        self.assertIn('15 poin', labels)
        self.assertTrue(any(all(date in label for date in ('21/10/2026', '22/10/2026', '23/10/2026'))
                            for label in labels))

    def test_evidence_contains_all_matching_activities_beyond_recent_limit(self):
        events = [activity('backup_history', 'BACKUP_CLAIM', source='admin_backup_claims')
                  for _ in range(60)]
        data = queries.fetch_admin_performance_data(source_events=events, detail_limit=50)
        self.assertEqual(len(data['detail_rows']), 50)
        self.assertEqual(len(data['backup_attendance_rows']), 60)
        other_admin = queries.fetch_admin_performance_data(source_events=events, admin_id=2)
        self.assertEqual(other_admin['backup_attendance_rows'], [])

    def test_grouping_keeps_all_data_and_does_not_merge_different_meetings(self):
        from dashboard.pengaturan import admin_performance_pdf as pdf
        creation = activity('meeting_creation', 'MEETING', source='admin_meetings')
        attendance = activity('meeting_attendance', 'MEETING_ATTENDANCE', source='admin_meeting_attendance')
        attendance['detail_text'] = '{"meeting_id":23,"attendance_status":"present"}'
        other = activity('meeting_creation', 'MEETING', day=22, source='admin_meetings')
        events = [creation, attendance, other]
        original = deepcopy(events)
        grouped = pdf._group_meeting_activities(events)
        self.assertEqual(len(grouped), 2)
        self.assertEqual(grouped[0]['creation_activity'], creation)
        self.assertEqual(grouped[0]['created_at'], attendance['created_at'])
        self.assertEqual(grouped[1], other)
        self.assertEqual(events, original)

    def test_attendance_photo_and_labeled_jakarta_timestamps_render(self):
        import tempfile
        from pathlib import Path
        from PIL import Image, ImageDraw
        from dashboard.pengaturan import admin_performance_pdf as pdf
        with tempfile.TemporaryDirectory() as temporary:
            photo_path = Path(temporary) / 'meeting.png'
            Image.new('RGB', (800, 400), (20, 120, 180)).save(photo_path)
            event = activity('meeting_attendance', 'MEETING_ATTENDANCE', action='ATTEND',
                             source='admin_meeting_attendance')
            event.update(photo_path=str(photo_path), attendance_recorded_at=datetime(2026, 10, 23, 2, 15, tzinfo=timezone.utc),
                         detail_text='{"attendance_status":"late","meeting_id":23}')
            text = []
            original = ImageDraw.ImageDraw.text
            def capture(draw, xy, value, *args, **kwargs):
                text.append(str(value))
                return original(draw, xy, value, *args, **kwargs)
            with patch.object(ImageDraw.ImageDraw, 'text', capture):
                pages = pdf._draw_backup_attendance_pages({'backup_attendance_rows': [event]},
                    period_label='Oktober', generated_at=event['created_at'], first_page_number=4, attendance_only=True)
            self.assertGreater(sum(count for count, color in pages[0].getcolors(3000000) if color == (20, 120, 180)), 10000)
            self.assertTrue(any('Absensi dicatat: 23/10/2026 09:15 WIB' in line for line in text))
            self.assertTrue(any('Status: Terlambat' in line for line in text))
            import re
            report = queries.fetch_admin_performance_data(source_events=[
                activity('backup_history', 'BACKUP_CLAIM', source='admin_backup_claims'),
                event,
                activity('meeting_creation', 'MEETING', source='admin_meetings'),
            ])
            with patch.object(ImageDraw.ImageDraw, 'text', capture):
                document = pdf.build_admin_performance_pdf(
                    leaderboard=[], personal=report, downloader={'id': 1, 'full_name': 'Admin 1'},
                    period_label='Oktober', generated_at=event['created_at'], filters_label='Semua',
                    feature_options=report['feature_options'])
            self.assertIn('Aktivitas pertama', text)
            self.assertIn('Aktivitas terakhir', text)
            self.assertIn('DOKUMENTASI ABSENSI RAPAT', text)
            self.assertTrue(any('Pembuat meeting:' in line and '(1 poin)' in line for line in text))
            self.assertEqual(len(re.findall(rb'/Type\s*/Page\b', document.getvalue())), 4)
            text.clear()
            many = [{**event, 'target_name': f'Rapat {index}',
                     'created_at': event['created_at'] + timedelta(days=index)} for index in range(5)]
            with patch.object(ImageDraw.ImageDraw, 'text', capture):
                evidence = pdf._draw_backup_attendance_pages({'backup_attendance_rows': many},
                    period_label='Oktober', generated_at=event['created_at'], first_page_number=3,
                    attendance_only=True)
            self.assertEqual(len(evidence), 1)
            single_photo_area = sum(count for count, color in pages[0].getcolors(3000000) if color == (20, 120, 180))
            four_photo_area = sum(count for count, color in evidence[0].getcolors(3000000) if color == (20, 120, 180))
            self.assertGreater(single_photo_area, (four_photo_area / 4) * 2)

            self.assertEqual([line for line in text if line.startswith('Rapat ')],
                             ['Rapat 4', 'Rapat 3', 'Rapat 2', 'Rapat 1'])
            self.assertTrue(any('4 dari 5 absensi' in line for line in text))
            event['photo_path'] = str(Path(temporary) / 'missing.jpg')
            self.assertTrue(pdf._draw_backup_attendance_pages({'backup_attendance_rows':[event]},
                period_label='Oktober', generated_at=event['created_at'], first_page_number=4, attendance_only=True))


class MeetingPhotoActivityTests(unittest.TestCase):
    def test_pdf_photo_falls_back_to_labeled_dummy_when_original_is_missing(self):
        from PIL import Image, ImageDraw
        from dashboard.pengaturan import admin_performance_pdf as pdf

        original = routes.MEETING_PHOTO_ROOT / '12' / 'server-only.jpg'
        with patch.object(routes, '_meeting_photo_path', return_value=original):
            photo, is_dummy = routes._performance_meeting_photo('12/server-only.jpg')
        self.assertTrue(is_dummy)
        self.assertEqual(photo, routes.MEETING_DUMMY_PHOTO)
        self.assertTrue(photo.is_file())

        event = activity('meeting_attendance', 'MEETING_ATTENDANCE',
                         action='ATTEND', source='admin_meeting_attendance')
        event.update(photo_path=str(photo), photo_is_dummy=True)
        labels = []
        original_text = ImageDraw.ImageDraw.text
        def capture(draw, xy, value, *args, **kwargs):
            labels.append(str(value))
            return original_text(draw, xy, value, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, 'text', capture):
            page = pdf._draw_attendance_page({'backup_attendance_rows': [event]},
                period_label='Oktober', generated_at=event['created_at'], page_number=3)
        self.assertIsInstance(page, Image.Image)
        self.assertIn('FOTO DUMMY', labels)
        self.assertTrue(any('foto asli tidak tersedia' in label for label in labels))

    def test_pdf_photo_prefers_existing_original(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary) / 'meeting.jpg'
            original.write_bytes(b'photo')
            with patch.object(routes, '_meeting_photo_path', return_value=original):
                photo, is_dummy = routes._performance_meeting_photo('12/meeting.jpg')
            self.assertEqual(photo, original)
            self.assertFalse(is_dummy)

    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-only'
        self.app.config['TESTING'] = True
        self.app.register_blueprint(routes.pengaturan_bp)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['user'] = {'id': 7, 'role': 'admin'}
        for name, value in (
            ('get_admin_meeting', {'id': 12, 'title': 'Rapat Koordinasi', 'photo_path': None}),
            ('_meeting_attendance_is_closed', False),
            ('_save_meeting_photo', '12/new-photo.jpg'),
            ('update_admin_meeting_documentation', True),
            ('_meeting_photo_path', None),
        ):
            item = patch.object(routes, name, return_value=value)
            setattr(self, name, item.start())
            self.addCleanup(item.stop)
        item = patch.object(routes, 'record_admin_action')
        self.audit = item.start()
        self.addCleanup(item.stop)

    def post(self):
        return self.client.post('/dashboard/pengaturan/absensi-meeting/foto',
            data={'meeting_id': '12', 'admin_user_id': '999'})

    def test_saved_photo_credits_the_signed_in_photographer_one_point(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
        self.audit.assert_called_once()
        event = self.audit.call_args.kwargs
        self.assertEqual(event['user_id'], 7)
        self.assertEqual(event['feature_key'], 'meeting_photo')
        self.assertEqual(event['action'], 'CAPTURE')
        self.assertEqual(event['target_id'], 12)
        self.assertEqual(event['metadata']['photo_path'], '12/new-photo.jpg')
        self.assertEqual(datetime.fromisoformat(event['metadata']['captured_at']).utcoffset(), timedelta(hours=7))
        normalized = queries._normalize_admin_performance_event({
            **event, 'source': 'dashboard_admin_action_logs', 'actor_user_id': event['user_id']})
        report = queries.fetch_admin_performance_data(source_events=[normalized])
        self.assertEqual(report['summary']['total_actions'], 1)
        self.assertEqual(report['summary']['action_points'], 1)
        self.assertEqual(report['leaderboard'][0]['actor_user_id'], 7)
        self.assertEqual(report['leaderboard'][0]['feature_counts'], {'meeting_photo': 1})

    def test_failed_or_closed_capture_does_not_record_activity(self):
        self._meeting_attendance_is_closed.return_value = True
        self.assertEqual(self.post().status_code, 403)
        self._meeting_attendance_is_closed.return_value = False
        self._save_meeting_photo.side_effect = ValueError('Foto tidak valid')
        self.assertEqual(self.post().status_code, 400)
        self._save_meeting_photo.side_effect = None
        self._save_meeting_photo.return_value = None
        self.assertEqual(self.post().status_code, 400)
        self._save_meeting_photo.return_value = '12/new-photo.jpg'
        self.update_admin_meeting_documentation.return_value = False
        self.assertEqual(self.post().status_code, 404)
        self.audit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
