import os
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from dashboard.monev_bos import monev_bos_bp, queries
from dashboard.monev_bos.collaborative_notes import merge_notes, text_changes, NotesConflict


class MergeTests(unittest.TestCase):
    def test_independent_changes_merge(self):
        base = "Dokumen lengkap.\nFoto perlu diperbaiki."
        first = base.replace("lengkap", "sudah lengkap")
        second = base.replace("diperbaiki", "dilengkapi")
        self.assertEqual(merge_notes(base, first, second),
                         "Dokumen sudah lengkap.\nFoto perlu dilengkapi.")

    def test_overlapping_changes_and_simultaneous_insert_rejected(self):
        for base, current, incoming in [("abc", "axc", "ayc"), ("", "Ani", "Budi"),
                                         ("abc", "ac", "aXbc")]:
            with self.subTest(base=base):
                with self.assertRaises(NotesConflict):
                    merge_notes(base, current, incoming)

    def test_identical_edits_are_idempotent(self):
        self.assertEqual(merge_notes("abc", "aXbc", "aXbc"), "aXbc")
        self.assertEqual(merge_notes("abc", "aXbc", "abc"), "aXbc")

    def test_changes_capture_authorable_part_and_line(self):
        changes = text_changes("Satu\nDua", "Satu\nTiga")
        self.assertEqual(changes[0]["line"], 2)
        self.assertEqual(changes[0]["before"], "Du")
        self.assertEqual(changes[0]["after"], "Tig")


class NotesEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "notes-test"
        self.app.register_blueprint(monev_bos_bp)
        self.client = self.app.test_client()
        self.url = "/monev-bos/staff/verifikasi/353/catatan"
        self.report_patch = patch.object(queries, "get_report_by_id", return_value={"id": 353})
        self.access_patch = patch.object(queries, "staff_can_audit_report", return_value=True)
        self.report_patch.start()
        self.access = self.access_patch.start()
        self.view_patch = patch.object(queries, "staff_can_view_report", return_value=False)
        self.view = self.view_patch.start()
        self.addCleanup(self.view_patch.stop)
        self.addCleanup(self.report_patch.stop)
        self.addCleanup(self.access_patch.stop)

    def login(self, role="staff"):
        with self.client.session_transaction() as session:
            session["user"] = {"id": 12, "role": role, "full_name": "Anggota A"}

    def test_login_and_assignment_required_for_read_write_history(self):
        self.assertEqual(self.client.get(self.url, headers={"Accept": "application/json"}).status_code, 401)
        self.login()
        self.access.return_value = False
        for url, method in [(self.url, "get"), (self.url, "post"), (self.url + "/history", "get")]:
            self.assertEqual(getattr(self.client, method)(url).status_code, 403)

    def test_admin_read_only(self):
        self.login("admin")
        with patch.object(queries, "get_report_notes", return_value={"content": "Tim", "version": 1}):
            result = self.client.get(self.url)
            self.assertFalse(result.json["can_edit"])
        self.assertEqual(self.client.post(self.url, json={"content": "x", "base_version": 1}).status_code, 403)

    def test_former_member_can_read_notes_history_but_cannot_write(self):
        self.login()
        self.access.return_value = False
        self.view.return_value = True
        with patch.object(queries, "get_report_notes", return_value={"content": "Riwayat tim", "version": 2}), \
                patch.object(queries, "get_report_notes_history", return_value=[]):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json["can_edit"])
            self.assertEqual(self.client.get(self.url + "/history").status_code, 200)
        self.assertEqual(self.client.post(self.url, json={"content": "ubah", "base_version": 2}).status_code, 403)
        self.assertEqual(self.client.post('/monev-bos/staff/verifikasi/353', data={"action": "update_report_status", "status": "completed"}).status_code, 403)

    def test_payload_validation_and_conflict(self):
        self.login()
        for payload in [{}, {"content": "x", "base_version": True},
                        {"content": "x" * 20001, "base_version": 0},
                        {"content": "x", "base_version": -1}, []]:
            self.assertEqual(self.client.post(self.url, json=payload).status_code, 400)
        with patch.object(queries, "save_report_notes", side_effect=NotesConflict("Bentrok")), \
                patch.object(queries, "get_report_notes", return_value={"content": "Tim", "version": 2}):
            response = self.client.post(self.url, json={"content": "Saya", "base_version": 1})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json["document"]["content"], "Tim")

    def test_csrf_protects_writes(self):
        CSRFProtect(self.app)
        self.login()
        self.assertEqual(self.client.post(self.url, json={"content": "x", "base_version": 0}).status_code, 400)


@unittest.skipUnless(os.getenv("MONEV_NOTES_DB_TEST") == "1", "Opt-in database test; all writes rolled back")
class NotesDatabaseTests(unittest.TestCase):
    def test_historical_access_survives_team_changes_without_granting_write_access(self):
        from dashboard.db_access import get_cursor
        with get_cursor() as cursor:
            @contextmanager
            def transaction_cursor(commit=False):
                yield cursor
            try:
                token = uuid.uuid4().hex
                users = []
                for index in range(6):
                    cursor.execute("""INSERT INTO dashboard_users(email, full_name, password_hash, role)
                        VALUES (%s, 'History test', 'unused-test', %s) RETURNING id""",
                        (f'{token}-{index}@monev.test', 'sekolah' if index == 5 else 'staff'))
                    users.append(cursor.fetchone()['id'])
                owner, member, replacement, new_member, outsider, school = users
                periods = []
                for tw in [1, 2]:
                    cursor.execute("""INSERT INTO monev_bos_periods(year, tw, start_date, end_date)
                        VALUES (9995, %s, '2026-01-01', '2026-12-31')
                        ON CONFLICT (year, tw) DO UPDATE SET year = EXCLUDED.year RETURNING id""", (tw,))
                    periods.append(cursor.fetchone()['id'])
                cursor.execute("INSERT INTO monev_bos_teams(name, leader_id) VALUES ('History test', %s) RETURNING id", (owner,))
                team_id = cursor.fetchone()['id']
                cursor.execute('INSERT INTO monev_bos_team_members(team_id, staff_id) VALUES (%s, %s)', (team_id, member))
                cursor.execute('INSERT INTO monev_bos_assignments(team_id, school_id, period_id) VALUES (%s, %s, %s)', (team_id, school, periods[0]))
                cursor.execute('INSERT INTO monev_bos_reports(school_id, period_id) VALUES (%s, %s) RETURNING id', (school, periods[0]))
                report = cursor.fetchone()['id']
                with patch.object(queries, 'get_cursor', transaction_cursor):
                    self.assertTrue(queries.staff_can_audit_report(member, report))
                    cursor.execute('UPDATE monev_bos_teams SET leader_id = %s WHERE id = %s', (replacement, team_id))
                    self.assertTrue(queries.staff_can_view_report(owner, report))
                    self.assertFalse(queries.staff_can_audit_report(owner, report))
                    cursor.execute('DELETE FROM monev_bos_team_members WHERE team_id = %s AND staff_id = %s', (team_id, member))
                    self.assertTrue(queries.staff_can_view_report(member, report))
                    self.assertFalse(queries.staff_can_audit_report(member, report))
                    cursor.execute('INSERT INTO monev_bos_team_members(team_id, staff_id) VALUES (%s, %s)', (team_id, new_member))
                    cursor.execute("INSERT INTO monev_bos_teams(name, leader_id) VALUES ('New history team', %s) RETURNING id", (new_member,))
                    next_team = cursor.fetchone()['id']
                    cursor.execute('UPDATE monev_bos_assignments SET team_id = %s WHERE school_id = %s AND period_id = %s', (next_team, school, periods[0]))
                    self.assertTrue(queries.staff_can_view_report(replacement, report))
                    self.assertFalse(queries.staff_can_audit_report(replacement, report))
                    cursor.execute('DELETE FROM monev_bos_teams WHERE id IN (%s, %s)', (team_id, next_team))
                    for user in [owner, member, replacement, new_member]:
                        self.assertTrue(queries.staff_can_view_report(user, report))
                        self.assertFalse(queries.staff_can_audit_report(user, report))
                        self.assertIn(report, [row['id'] for row in queries.list_staff_report_history(user)])
                    self.assertFalse(queries.staff_can_view_report(outsider, report))
                    # No historical access leaks into future periods/reports.
                    cursor.execute("INSERT INTO monev_bos_teams(name, leader_id) VALUES ('Future team', %s) RETURNING id", (new_member,))
                    future_team = cursor.fetchone()['id']
                    cursor.execute('INSERT INTO monev_bos_reports(school_id, period_id) VALUES (%s, %s) RETURNING id', (school, periods[1]))
                    future_report = cursor.fetchone()['id']
                    cursor.execute('INSERT INTO monev_bos_assignments(team_id, school_id, period_id) VALUES (%s, %s, %s)', (future_team, school, periods[1]))
                    self.assertTrue(queries.staff_can_view_report(new_member, future_report))
                    self.assertFalse(queries.staff_can_view_report(member, future_report))
            finally:
                cursor.connection.rollback()

    def test_revision_merge_history_and_rollback(self):
        from dashboard.db_access import get_cursor
        with get_cursor() as cursor:
            @contextmanager
            def transaction_cursor(commit=False):
                yield cursor
            try:
                cursor.execute("SELECT id, full_name, email FROM dashboard_users ORDER BY id LIMIT 2")
                authors = [dict(row) for row in cursor.fetchall()]
                cursor.execute("SELECT id FROM monev_bos_reports ORDER BY id LIMIT 1")
                report_id = cursor.fetchone()["id"]
                with patch.object(queries, "get_cursor", transaction_cursor):
                    initial = queries.get_report_notes(report_id)
                    seed = queries.save_report_notes(report_id, initial["version"], "Dokumen lengkap.\nFoto jelas.", authors[0])
                    first = queries.save_report_notes(report_id, seed["version"], "Dokumen belum lengkap.\nFoto jelas.", authors[0])
                    merged = queries.save_report_notes(report_id, seed["version"], "Dokumen lengkap.\nFoto kurang jelas.", authors[1])
                    self.assertEqual(merged["content"], "Dokumen belum lengkap.\nFoto kurang jelas.")
                    self.assertEqual(merged["version"], first["version"] + 1)
                    with self.assertRaises(NotesConflict):
                        queries.save_report_notes(report_id, seed["version"], "Dokumen sangat lengkap.\nFoto jelas.", authors[1])
                    history = queries.get_report_notes_history(report_id)
                    self.assertEqual(history[0]["author_id"], authors[1]["id"])
                    self.assertEqual(history[0]["changes"][0]["line"], 2)
                    self.assertNotIn("Dokumen", history[0]["changes"][0]["after"])
                    self.assertEqual(queries.get_report_notes(report_id)["content"], merged["content"])
                    page = queries.get_report_notes_history(report_id, merged["version"])
                    self.assertEqual(page[0]["version"], first["version"])
            finally:
                cursor.connection.rollback()


if __name__ == "__main__":
    unittest.main()
