from __future__ import annotations

import os
import sys

from flask import Flask


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.monev_bos import routes


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, *_args):
        return False


def _configure_staff_action_route(monkeypatch):
    monkeypatch.setattr(
        routes,
        "current_user",
        lambda: {"id": 10, "role": "staff", "full_name": "Staff Uji"},
    )
    monkeypatch.setattr(
        routes.queries,
        "get_activity_by_id",
        lambda activity_id: {
            "id": activity_id,
            "report_id": 353,
            "activity_name": "Belanja alat",
            "status": "pending",
        },
    )
    monkeypatch.setattr(routes.queries, "add_audit_log", lambda *args: None)
    monkeypatch.setattr(routes, "flash", lambda *_args, **_kwargs: None)


def test_completed_with_notes_report_status_is_accepted(monkeypatch):
    app = Flask(__name__)
    statements = []

    class Cursor:
        def execute(self, query, params):
            statements.append((" ".join(query.split()), params))

    monkeypatch.setattr(
        routes,
        "current_user",
        lambda: {"id": 10, "role": "staff"},
    )
    monkeypatch.setattr(
        routes.queries,
        "get_report_by_id",
        lambda report_id: {"id": report_id, "school_name": "Sekolah Uji"},
    )
    monkeypatch.setattr(routes.queries, "get_cursor", lambda **_kwargs: _CursorContext(Cursor()))
    monkeypatch.setattr(routes.queries, "add_audit_log", lambda *args: None)
    monkeypatch.setattr(routes, "_record_monev_admin_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "flash", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "url_for", lambda *_args, **_kwargs: "/staff/verifikasi/353")
    monkeypatch.setattr(routes, "redirect", lambda location: location)

    with app.test_request_context(
        "/monev-bos/staff/verifikasi/353",
        method="POST",
        data={"action": "update_report_status", "status": "completed_with_notes"},
    ):
        response = routes.staff_audit_report.__wrapped__(353)

    assert response == "/staff/verifikasi/353"
    assert statements == [(
        "UPDATE monev_bos_reports SET status = %s, updated_at = NOW() WHERE id = %s",
        ("completed_with_notes", 353),
    )]


def test_staff_can_delete_staff_live_photo(monkeypatch):
    app = Flask(__name__)
    deleted_args = []
    removed_paths = []
    _configure_staff_action_route(monkeypatch)
    monkeypatch.setattr(
        routes.queries,
        "delete_staff_live_photo",
        lambda *args: deleted_args.append(args) or {
            "id": 91,
            "file_path": "static/uploads/monev_bos/353/44/live_photo/camera.jpg",
        },
    )
    monkeypatch.setattr(routes.os, "remove", lambda path: removed_paths.append(path))

    with app.test_request_context(
        "/monev-bos/staff/verifikasi/kegiatan/44",
        method="POST",
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        data={"action": "delete_staff_photo", "doc_id": "91", "report_id": "999"},
    ):
        response = routes.staff_audit_activity.__wrapped__(44)

    assert response.json["success"] is True
    assert deleted_args == [(44, 91, None)]
    assert removed_paths


def test_bulk_camera_photo_uses_shared_camera_processor(monkeypatch):
    app = Flask(__name__)
    saved = []
    _configure_staff_action_route(monkeypatch)
    monkeypatch.setattr(
        routes,
        "_save_camera_photo",
        lambda data, root, relative_dir: (
            "static/uploads/monev_bos/353/44/live_photo/camera.jpg",
            None,
        ),
    )
    monkeypatch.setattr(routes.os.path, "getsize", lambda _path: 12345)
    monkeypatch.setattr(
        routes.queries,
        "add_activity_doc",
        lambda *args: saved.append(args) or 91,
    )
    monkeypatch.setattr(routes, "_record_monev_admin_action", lambda *args, **kwargs: None)

    with app.test_request_context(
        "/monev-bos/staff/verifikasi/kegiatan/44",
        method="POST",
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        data={"action": "upload_photo", "live_photo_data": "data:image/jpeg;base64,AA=="},
    ):
        response = routes.staff_audit_activity.__wrapped__(44)

    assert response.json["success"] is True
    assert response.json["photo_id"] == 91
    assert saved[0][0:2] == (44, "live_photo")
