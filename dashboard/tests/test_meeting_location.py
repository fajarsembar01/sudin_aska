import unittest
from datetime import date, datetime, time, timezone, timedelta
from unittest.mock import patch
from flask import Flask
from dashboard.pengaturan import routes
from dashboard.pengaturan.meeting_location import coordinates, distance_m, meeting_location, validate_attendance_location


class LocationTests(unittest.TestCase):
    def test_default_and_custom_radius(self):
        self.assertEqual(meeting_location({'latitude': '0', 'longitude': '0'}), (0, 0, 200))
        self.assertEqual(meeting_location({'latitude': '-6', 'longitude': '106', 'radius_m': '200'}), (-6, 106, 200))

    def test_invalid_points_and_radius(self):
        for lat, lng in [(None, None), ('nan', 1), (1, 'inf'), (91, 0), (0, -181)]:
            with self.subTest(lat=lat, lng=lng), self.assertRaises(ValueError):
                coordinates(lat, lng)
        for radius in ['0', '-1', '100001', 'nan', '2.5']:
            with self.subTest(radius=radius), self.assertRaises(ValueError):
                meeting_location({'latitude': '0', 'longitude': '0', 'radius_m': radius})

    def test_geofence_inside_outside_and_missing_point(self):
        meeting = {'latitude': 0, 'longitude': 0, 'radius_m': 500}
        self.assertEqual(validate_attendance_location(meeting, 0.004, 0), (0.004, 0))
        self.assertAlmostEqual(distance_m(0, 0, 0.004, 0), 444.78, places=2)
        with self.assertRaises(ValueError):
            validate_attendance_location(meeting, 0.005, 0)
        with self.assertRaises(ValueError):
            validate_attendance_location({}, 0, 0)


class AttendanceRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.app.register_blueprint(routes.pengaturan_bp)
        self.client = self.app.test_client()
        self.url = '/dashboard/pengaturan/absensi-meeting'
        self.meeting = {'id': 1, 'title': 'Test', 'latitude': 0, 'longitude': 0, 'radius_m': 500,
                        'meeting_date': date(2026, 11, 18), 'start_time': time(8)}
        for name, value in [('get_admin_meeting', self.meeting), ('_meeting_attendance_is_closed', False),
                            ('_meeting_attendance_deadline', None), ('list_admin_users', [{'id': 3}]),
                            ('list_admin_meeting_attendance', [{'admin_user_id': 3, 'attendance_status': 'unrecorded'}]),
                            ('save_admin_meeting_attendance', 1), ('update_admin_meeting_documentation', True),
                            ('current_jakarta_time', datetime(2026, 11, 18, 8, tzinfo=timezone(timedelta(hours=7)))),
                            ('record_admin_action', None), ('current_user', {'id': 3, 'role': 'admin'})]:
            p = patch.object(routes, name, return_value=value)
            setattr(self, name, p.start())
            self.addCleanup(p.stop)
        with self.client.session_transaction() as session:
            session['user'] = {'id': 3, 'role': 'admin'}

    def post_attendance(self, **extra):
        return self.client.post(self.url, data={'action': 'save_attendance', 'meeting_id': 1, 'status_3': 'present', **extra})

    def post_checkin(self, **extra):
        return self.client.post(self.url + '/hadir', data={
            'meeting_id': 1, 'latitude': '0.004', 'longitude': '0', **extra,
        })

    def test_autosave_only_saves_current_admin_and_preserves_documentation(self):
        response = self.post_checkin(admin_user_id='4', status='absent', notulen='overwrite')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
        self.assertEqual(response.json['recorded_time'], '08:00')
        entries = self.save_admin_meeting_attendance.call_args.kwargs['entries']
        self.assertEqual(entries, [{'admin_user_id': 3, 'attendance_status': 'present',
                                   'notes': '', 'latitude': 0.004, 'longitude': 0.0}])
        self.update_admin_meeting_documentation.assert_not_called()

    def test_autosave_validates_location_on_server(self):
        for point in ['', 'nan', '0.005']:
            response = self.post_checkin(latitude=point)
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json['success'])
        self.save_admin_meeting_attendance.assert_not_called()

    def test_autosave_rejects_closed_or_missing_meeting(self):
        self._meeting_attendance_is_closed.return_value = True
        self.assertEqual(self.post_checkin().status_code, 403)
        self.get_admin_meeting.return_value = None
        self.assertEqual(self.post_checkin().status_code, 404)
        self.save_admin_meeting_attendance.assert_not_called()

    def test_autosave_marks_late_on_server(self):
        self.current_jakarta_time.return_value = datetime(2026, 11, 18, 8, 1)
        self.assertEqual(self.post_checkin().json['status'], 'late')
        entry = self.save_admin_meeting_attendance.call_args.kwargs['entries'][0]
        self.assertEqual(entry['attendance_status'], 'late')

    def test_repeated_checkin_preserves_saved_status_time_and_notes(self):
        self.current_jakarta_time.return_value = datetime(2026, 11, 18, 9)
        self.list_admin_meeting_attendance.return_value = [{
            'admin_user_id': 3, 'attendance_status': 'present', 'notes': 'Existing note',
            'recorded_at': datetime(2026, 11, 18, 1, tzinfo=timezone.utc),
        }]
        response = self.post_checkin()
        self.assertEqual(response.json['status'], 'present')
        self.assertEqual(response.json['recorded_time'], '08:00')
        entry = self.save_admin_meeting_attendance.call_args.kwargs['entries'][0]
        self.assertEqual(entry['notes'], 'Existing note')

    def test_autosave_reports_failed_write(self):
        self.save_admin_meeting_attendance.return_value = 0
        response = self.post_checkin()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json['success'])

    def test_autosave_requires_admin(self):
        self.app.add_url_rule('/login', endpoint='auth.login', view_func=lambda: 'Login')
        with self.client.session_transaction() as session:
            session.clear()
        response = self.post_checkin()
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)
        self.save_admin_meeting_attendance.assert_not_called()

    def test_direct_post_without_location_or_outside_is_rejected(self):
        for data in [{}, {'latitude_3': '0.005', 'longitude_3': '0'}, {'latitude_3': 'nan', 'longitude_3': '0'}]:
            self.assertEqual(self.post_attendance(**data).status_code, 302)
            self.save_admin_meeting_attendance.assert_not_called()

    def test_valid_attendance_saves_coordinates(self):
        self.post_attendance(latitude_3='0.004', longitude_3='0')
        self.save_admin_meeting_attendance.assert_called_once()
        entry = self.save_admin_meeting_attendance.call_args.kwargs['entries'][0]
        self.assertEqual((entry['latitude'], entry['longitude']), (0.004, 0))

    def test_click_present_after_start_is_saved_as_late(self):
        self.current_jakarta_time.return_value = datetime(2026, 11, 18, 8, 0, 1, tzinfo=timezone(timedelta(hours=7)))
        self.post_attendance(latitude_3='0.004', longitude_3='0')
        self.assertEqual(self.save_admin_meeting_attendance.call_args.kwargs['entries'][0]['attendance_status'], 'late')

    def test_before_and_exact_start_remain_present(self):
        for hour, minute in [(7, 59), (8, 0)]:
            self.current_jakarta_time.return_value = datetime(2026, 11, 18, hour, minute, tzinfo=timezone(timedelta(hours=7)))
            self.post_attendance(latitude_3='0.004', longitude_3='0')
            self.assertEqual(self.save_admin_meeting_attendance.call_args.kwargs['entries'][0]['attendance_status'], 'present')

    def test_later_save_does_not_mark_existing_ontime_attendance_late(self):
        self.current_jakarta_time.return_value = datetime(2026, 11, 18, 9)
        self.list_admin_meeting_attendance.return_value = [{'admin_user_id': 3, 'attendance_status': 'present', 'latitude': 0, 'longitude': 0}]
        self.post_attendance()
        self.assertEqual(self.save_admin_meeting_attendance.call_args.kwargs['entries'][0]['attendance_status'], 'present')

    def test_permission_requires_no_location(self):
        self.post_attendance(status_3='permission')
        self.save_admin_meeting_attendance.assert_called_once()

    def test_existing_present_can_be_retained(self):
        self.list_admin_meeting_attendance.return_value = [{'admin_user_id': 3, 'attendance_status': 'present', 'latitude': 0, 'longitude': 0}]
        self.post_attendance()
        self.save_admin_meeting_attendance.assert_called_once()

    def test_cannot_mark_another_admin_present_or_late(self):
        self.list_admin_users.return_value = [{'id': 3}, {'id': 4}]
        for status in ['present', 'late']:
            with self.subTest(status=status):
                response = self.post_attendance(status_3='permission', status_4=status,
                                                latitude_4='0', longitude_4='0')
                self.assertEqual(response.status_code, 403)
                self.save_admin_meeting_attendance.assert_not_called()

    def test_other_admin_saved_attendance_is_preserved(self):
        self.list_admin_users.return_value = [{'id': 3}, {'id': 4}]
        self.list_admin_meeting_attendance.return_value = [
            {'admin_user_id': 3, 'attendance_status': 'unrecorded'},
            {'admin_user_id': 4, 'attendance_status': 'present', 'latitude': 0, 'longitude': 0},
        ]
        self.post_attendance(latitude_3='0', longitude_3='0', status_4='present')
        entries = self.save_admin_meeting_attendance.call_args.kwargs['entries']
        self.assertEqual([entry['admin_user_id'] for entry in entries], [3])

    def test_cannot_resubmit_other_admin_location_for_existing_attendance(self):
        self.list_admin_users.return_value = [{'id': 3}, {'id': 4}]
        self.list_admin_meeting_attendance.return_value = [
            {'admin_user_id': 4, 'attendance_status': 'present', 'latitude': 0, 'longitude': 0},
        ]
        response = self.post_attendance(status_3='permission', status_4='present', latitude_4='0', longitude_4='0')
        self.assertEqual(response.status_code, 403)
        self.save_admin_meeting_attendance.assert_not_called()

    def test_late_is_included_in_attended_total(self):
        self.list_admin_meeting_attendance.return_value = [
            {'admin_user_id': 3, 'attendance_status': 'present'},
            {'admin_user_id': 4, 'attendance_status': 'late'},
        ]
        with patch.object(routes, 'list_admin_meetings', return_value=[]), \
                patch.object(routes, 'list_meeting_location_favorites', return_value=[]), \
                patch.object(routes, 'render_template', return_value='OK') as render:
            self.assertEqual(self.client.get(self.url + '?meeting_id=1').status_code, 200)
            summary = render.call_args.kwargs['attendance_summary']
            self.assertEqual(summary['present'], 2)
            self.assertEqual(summary['late'], 1)

    def test_creation_requires_point_and_saves_favorite(self):
        payload = {'action': 'create_meeting', 'title': 'Rapat', 'meeting_date': '2026-11-18',
                   'start_time': '08:00', 'end_time': '15:00', 'location': 'Kantor', 'save_favorite': '1'}
        with patch.object(routes, 'create_admin_meeting', return_value=1) as create, \
                patch.object(routes, 'save_meeting_location_favorite') as favorite:
            self.client.post(self.url, data=payload)
            create.assert_not_called()
            self.client.post(self.url, data={**payload, 'latitude': '-6', 'longitude': '106'})
            self.assertEqual(create.call_args.kwargs['radius_m'], 200)
            self.assertEqual(favorite.call_args.kwargs['user_id'], 3)
            self.assertEqual(favorite.call_args.kwargs['name'], 'Kantor')


if __name__ == '__main__':
    unittest.main()
