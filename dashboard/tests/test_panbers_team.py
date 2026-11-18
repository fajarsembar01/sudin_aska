"""Panberss team regression tests; database fixtures are always rolled back."""
import json
import os
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch
from flask import Flask
from dashboard.portal import queries, routes, team_assessments as team, team_routes
from dashboard.db_access import get_cursor


class ModeFilterTests(unittest.TestCase):
    def test_mode_filter_is_parameterized_and_combined_has_no_restriction(self):
        app = Flask(__name__)
        for mode in ['individual', 'team', 'all', "team' OR 1=1"]:
            with self.subTest(mode=mode), app.test_request_context('/?assessment_mode=' + mode):
                clauses, params = [], []
                queries._apply_period_filter(clauses, params, period_id=7, column='a.period_id')
                if mode in {'individual', 'team'}:
                    self.assertEqual(clauses, ['a.assessment_mode = %s', 'a.period_id = %s'])
                    self.assertEqual(params, [mode, 7])
                else:
                    self.assertEqual(params, [7])

    def test_login_keeps_team_mode_and_explicit_draft_link(self):
        app = Flask(__name__); app.secret_key = 'test'
        app.add_url_rule('/login', 'auth.login', lambda: 'login')
        app.register_blueprint(routes.portal_bp)
        with patch.object(routes, 'current_user', return_value=None):
            response = app.test_client().get('/portal/assess/7?mode=team&assessment_id=9')
        from urllib.parse import urlparse, parse_qs
        self.assertEqual(response.status_code, 302)
        self.assertEqual(parse_qs(urlparse(response.location).query)['next'],
                         ['/portal/assess/7?mode=team&assessment_id=9'])


@unittest.skipUnless(os.getenv('PANBERS_TEAM_DB_TEST') == '1', 'Opt-in PostgreSQL tests; all writes rolled back')
class TeamDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.context = get_cursor()
        self.cur = self.context.__enter__()
        self.addCleanup(self.close_transaction)
        @contextmanager
        def transaction_cursor(commit=False):
            yield self.cur
        for module in [team, queries, routes, team_routes]:
            p = patch.object(module, 'get_cursor', transaction_cursor)
            p.start(); self.addCleanup(p.stop)
        token = uuid.uuid4().hex
        self.users = []
        for index in range(4):
            self.cur.execute("""INSERT INTO dashboard_users (email, full_name, password_hash, role)
                VALUES (%s, %s, 'unused-test', 'staff') RETURNING id""", (f'{token}-{index}@panbers.test', f'Test member {index}'))
            self.users.append({'id': self.cur.fetchone()['id'], 'role':'staff', 'email':f'{token}-{index}@panbers.test'})
        self.owner, self.member, self.outsider, self.old_member = self.users
        self.cur.execute("INSERT INTO portal_schools (npsn, name, user_id) VALUES (%s, %s, %s) RETURNING id", (token[:8], 'Team Test School', self.outsider['id']))
        self.school = self.cur.fetchone()['id']
        self.cur.execute("UPDATE dashboard_users SET school_id = %s WHERE id = %s", (self.school, self.outsider['id']))
        self.cur.execute("INSERT INTO monev_bos_teams (name, leader_id) VALUES ('Team Test', %s) RETURNING id", (self.owner['id'],))
        self.team_id = self.cur.fetchone()['id']
        self.cur.execute('INSERT INTO monev_bos_team_members (team_id, staff_id) VALUES (%s, %s)', (self.team_id, self.member['id']))
        self.cur.execute("INSERT INTO monev_bos_teams (name, leader_id) VALUES ('Older Team', %s) RETURNING id", (self.old_member['id'],))
        self.old_team = self.cur.fetchone()['id']
        for tw, tid in [(1, self.old_team), (2, self.team_id)]:
            self.cur.execute("INSERT INTO monev_bos_periods (year, tw, start_date, end_date, is_active) VALUES (9998, %s, '2026-01-01', '2026-12-31', TRUE) RETURNING id", (tw,))
            pid = self.cur.fetchone()['id']
            self.cur.execute('INSERT INTO monev_bos_assignments (team_id, school_id, period_id) VALUES (%s, %s, %s)', (tid, self.outsider['id'], pid))
        self.cur.execute('INSERT INTO portal_team_assessment_settings (school_id, enabled) VALUES (%s, TRUE)', (self.school,))
        self.cur.execute('UPDATE portal_assessment_periods SET is_active = FALSE WHERE is_active = TRUE')
        self.cur.execute("INSERT INTO portal_assessment_periods (name, start_date, end_date, is_active) VALUES ('Final period test', '2026-11-01', '2026-11-30', TRUE) RETURNING id")
        self.period_id = self.cur.fetchone()['id']
        self.cur.execute('INSERT INTO portal_rooms (name) VALUES (%s) RETURNING id', ('Test '+token,))
        room_type = self.cur.fetchone()['id']
        self.cur.execute('INSERT INTO portal_aspects (room_id, name, is_required) VALUES (%s, %s, TRUE) RETURNING id', (room_type, 'Test aspect'))
        self.aspect = self.cur.fetchone()['id']
        self.cur.execute('INSERT INTO portal_school_rooms (school_id, room_id) VALUES (%s, %s) RETURNING id', (self.school, room_type))
        self.room = self.cur.fetchone()['id']
        self.draft = team.get_or_create_draft(self.school, self.owner)

    def close_transaction(self):
        self.cur.connection.rollback()
        self.context.__exit__(None, None, None)

    def test_newest_assignment_wins_before_membership_check(self):
        self.assertEqual(team.assignment_for(self.school, self.member)['team_id'], self.team_id)
        self.assertIsNone(team.assignment_for(self.school, self.old_member))
        self.assertIsNone(team.assignment_for(self.school, self.outsider))

    def test_shared_draft_and_individual_draft_are_separate(self):
        other = team.get_or_create_draft(self.school, self.member)
        individual = queries.create_assessment(self.school, self.owner['id'])
        self.assertEqual(other['id'], self.draft['id'])
        self.assertNotEqual(individual['id'], self.draft['id'])
        self.assertIsNone(individual['period_id'])
        self.assertEqual(queries.get_active_assessment(self.school, self.owner['id'])['id'], individual['id'])

    def test_individual_assignment_card_keeps_unperiodized_draft_visible(self):
        queries.assign_staff_to_school(self.owner['id'], self.school, self.owner['id'])
        individual = queries.create_assessment(self.school, self.owner['id'])
        schools = queries.get_staff_assigned_schools(self.owner['id'], period_id=self.period_id)
        self.assertEqual(schools[0]['draft_assessment_id'], individual['id'])
        self.assertNotEqual(schools[0]['draft_assessment_id'], self.draft['id'])

    def test_member_can_save_and_stale_same_field_conflicts(self):
        version = team.save_field(self.draft['id'], self.room, f'score:{self.aspect}', 4, 0, self.member)
        self.assertEqual(version, 1)
        with self.assertRaises(team.TeamConflict):
            team.save_field(self.draft['id'], self.room, f'score:{self.aspect}', 2, 0, self.owner)
        self.assertEqual(team.state(self.draft['id'], self.owner)['scores'][0]['score'], 4)
        self.assertEqual(team.save_field(self.draft['id'], self.room, 'note', 'Independent field', 0, self.owner), 1)
        self.assertEqual(len(team.contributors(self.draft['id'])), 2)

    def test_invalid_room_aspect_and_score_cannot_be_saved(self):
        for room,field,value in [(self.room+999999,'note','bad'), (self.room,'score:99999999',3), (self.room,f'score:{self.aspect}',9)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                team.save_field(self.draft['id'],room,field,value,0,self.member)

    def test_outsider_cannot_write_read_or_create(self):
        with self.assertRaises(PermissionError):
            team.save_field(self.draft['id'], self.room, 'note', 'forbidden', 0, self.outsider)
        with self.assertRaises(PermissionError):
            team.state(self.draft['id'], self.outsider)
        with self.assertRaises(PermissionError):
            team.get_or_create_draft(self.school, self.outsider)

    def test_presence_is_per_tab_and_expires(self):
        snapshot = team.state(self.draft['id'], self.member, 'tab-a', self.room)
        self.assertEqual(snapshot['presence'][0]['user_id'], self.member['id'])
        snapshot = team.state(self.draft['id'], self.member, 'tab-b', self.room)
        self.assertEqual(len(snapshot['presence']), 2)
        self.cur.execute("UPDATE portal_assessment_presence SET seen_at = NOW() - INTERVAL '1 minute' WHERE assessment_id = %s", (self.draft['id'],))
        self.assertEqual(team.state(self.draft['id'], self.owner)['presence'], [])

    def test_assignment_change_revokes_old_member_and_keeps_draft(self):
        self.cur.execute('DELETE FROM monev_bos_team_members WHERE team_id = %s AND staff_id = %s', (self.team_id, self.member['id']))
        self.assertFalse(team.can_access(self.member, self.draft, edit=True))
        self.assertEqual(team.get_or_create_draft(self.school, self.owner)['id'], self.draft['id'])

    def test_any_member_can_submit_to_active_period_and_snapshot_is_preserved(self):
        self.assertTrue(queries.submit_assessment(self.draft['id'], actor=self.member))
        final = queries.get_assessment_by_id(self.draft['id'])
        self.assertEqual(final['period_id'], self.period_id)
        self.assertEqual(final['submitted_by'], self.member['id'])
        self.assertTrue(final['period_locked'])
        self.cur.execute('DELETE FROM monev_bos_team_members WHERE team_id = %s', (self.team_id,))
        self.assertTrue(team.can_access(self.member, final))
        with self.assertRaises(team.TeamConflict):
            team.save_field(final['id'], self.room, 'note', 'late write', 0, self.owner)
        self.assertFalse(queries.submit_assessment(final['id'], actor=self.owner))

    def test_reopened_final_preserves_original_period_and_team_snapshot(self):
        self.assertTrue(queries.submit_assessment(self.draft['id'], actor=self.member))
        final = queries.get_assessment_by_id(self.draft['id'])
        self.assertTrue(queries.reopen_assessment(final['id']))
        self.cur.execute('UPDATE portal_assessment_periods SET is_active = FALSE WHERE id = %s', (self.period_id,))
        self.assertTrue(queries.submit_assessment(final['id'], actor=self.owner))
        resubmitted = queries.get_assessment_by_id(final['id'])
        self.assertEqual(resubmitted['period_id'], final['period_id'])
        self.assertEqual(resubmitted['team_members_snapshot'], final['team_members_snapshot'])

    def test_live_state_post_requires_csrf_and_rejects_invalid_payload(self):
        from flask_wtf import CSRFProtect
        from flask_wtf.csrf import generate_csrf
        app = Flask(__name__); app.secret_key = 'test'; app.register_blueprint(routes.portal_bp)
        CSRFProtect(app)
        app.add_url_rule('/token', 'token', lambda: generate_csrf())
        client = app.test_client()
        token = client.get('/token').get_data(as_text=True)
        url = f'/portal/assessment/{self.draft["id"]}/team-state'
        with patch.object(routes,'current_user',return_value=self.member), patch.object(team_routes,'current_user',return_value=self.member):
            self.assertEqual(client.post(url,json={'client_id':'tab'}).status_code,400)
            response = client.post(url,json={'client_id':'tab','school_room_id':self.room},headers={'X-CSRFToken':token})
            self.assertEqual(response.status_code,200)
            self.assertEqual(client.post(url,json=['invalid'],headers={'X-CSRFToken':token}).status_code,400)

    def test_reopen_approval_does_not_collide_with_another_shared_draft(self):
        self.assertTrue(queries.submit_assessment(self.draft['id'], actor=self.owner))
        request = queries.create_reopen_request(self.draft['id'], self.owner['id'])
        other = team.get_or_create_draft(self.school, self.member)
        self.assertFalse(team.approve_reopen(self.draft['id'], request['id'], self.owner['id'], None))
        self.assertEqual(queries.get_latest_reopen_request(self.draft['id'])['status'], 'pending')
        self.assertEqual(queries.get_assessment_by_id(self.draft['id'])['status'], 'submitted')
        self.assertTrue(queries.submit_assessment(other['id'], actor=self.member))
        self.assertTrue(team.approve_reopen(self.draft['id'], request['id'], self.owner['id'], None))
        self.assertEqual(queries.get_assessment_by_id(self.draft['id'])['status'], 'draft')

    def test_no_active_period_blocks_final_and_keeps_draft(self):
        self.cur.execute('UPDATE portal_assessment_periods SET is_active = FALSE WHERE id = %s', (self.period_id,))
        with self.assertRaises(ValueError):
            queries.submit_assessment(self.draft['id'], actor=self.owner)
        self.assertEqual(queries.get_assessment_by_id(self.draft['id'])['status'], 'draft')

    def test_active_period_changes_at_final_not_draft_creation(self):
        self.cur.execute('UPDATE portal_assessment_periods SET is_active = FALSE WHERE id = %s', (self.period_id,))
        self.cur.execute("INSERT INTO portal_assessment_periods (name, start_date, end_date, is_active) VALUES ('Next test period', '2026-12-01', '2026-12-31', TRUE) RETURNING id")
        new_period = self.cur.fetchone()['id']
        with self.assertRaises(ValueError):
            queries.submit_assessment(self.draft['id'], actor=self.owner, expected_period_id=self.period_id)
        self.assertTrue(queries.submit_assessment(self.draft['id'], actor=self.owner, expected_period_id=new_period))
        self.assertEqual(queries.get_assessment_by_id(self.draft['id'])['period_id'], new_period)

    def test_multiple_final_results_and_mode_statistics(self):
        ids=[]
        for user in [self.owner, self.member]:
            draft=team.get_or_create_draft(self.school,user)
            self.assertTrue(queries.submit_assessment(draft['id'],actor=user));ids.append(draft['id'])
        individual=queries.create_assessment(self.school,self.owner['id'])
        self.assertTrue(queries.submit_assessment(individual['id'],actor=self.owner))
        self.assertNotEqual(ids[0],ids[1])
        app=Flask(__name__)
        for mode,count in [('team',2),('individual',1),('all',3)]:
            with app.test_request_context('/?assessment_mode='+mode):
                stats=queries.fetch_portal_stats(period_id=self.period_id)
                self.assertEqual(stats['assessments']['submitted'],count)
                exported=queries.fetch_export_data(group_by='staff', period_id=self.period_id)
                self.assertEqual(sum(r['Jumlah Penilaian'] for r in exported), count)
                if mode == 'team':
                    self.assertEqual(len(exported), 1)
                exported_school=queries.fetch_export_data(group_by='school', period_id=self.period_id)
                self.assertEqual(exported_school[0]['Jumlah Penilaian'], count)
                recent=queries.list_recent_assessments(period_id=self.period_id)
                self.assertEqual(len(recent),1) # one latest result per school in the existing overview

    def test_photo_conflict_and_actual_uploader(self):
        photo=queries.save_assessment_photo(self.draft['id'],self.room,'uploads/portal/test.jpg',actor=self.member,base_version=0)
        with self.assertRaises(team.TeamConflict):
            queries.save_assessment_photo(self.draft['id'],self.room,'uploads/portal/other.jpg',actor=self.owner,base_version=0)
        self.assertEqual(queries.get_assessment_photos(self.draft['id'])[0]['uploader_email'],self.member['email'])
        self.assertTrue(queries.delete_photo(photo['id'],self.draft['id'],self.room,actor=self.owner,base_version=1))

    def test_score_api_requires_team_membership_and_versions(self):
        app=Flask(__name__);app.secret_key='test';app.register_blueprint(routes.portal_bp)
        client=app.test_client()
        payload={'assessment_id':self.draft['id'],'school_room_id':self.room,'aspect_id':self.aspect,'score':4,'base_version':0}
        with patch.object(routes,'current_user',return_value=self.member):
            response=client.post(f'/portal/assess/{self.school}/score',json=payload)
            self.assertEqual(response.status_code,200,response.get_data(as_text=True))
            response=client.post(f'/portal/assess/{self.school}/score',json=payload)
            self.assertEqual(response.status_code,409)
        with patch.object(routes,'current_user',return_value=self.outsider):
            self.assertEqual(client.post(f'/portal/assess/{self.school}/score',json=payload).status_code,403)


if __name__=='__main__':
    unittest.main()
