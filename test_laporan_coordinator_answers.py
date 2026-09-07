from __future__ import annotations

from flask import Flask

from dashboard import auth
from dashboard.laporan import routes


def _set_user(monkeypatch, role: str) -> None:
    user = {"id": 17, "role": role, "full_name": "Pengguna Uji"}
    monkeypatch.setattr(auth, "current_user", lambda: user)
    monkeypatch.setattr(routes, "current_user", lambda: user)


def test_coordinator_can_open_admin_report_list_in_read_only_mode(monkeypatch):
    app = Flask(__name__)
    captured = {}
    _set_user(monkeypatch, "coordinator")
    monkeypatch.setattr(
        routes,
        "list_all_forms",
        lambda include_inactive: [
            {"id": 1, "status": "draft"},
            {"id": 2, "status": "published"},
        ],
    )
    monkeypatch.setattr(routes, "_annotate_repeat_form", lambda *_args: None)
    monkeypatch.setattr(routes, "_build_form_share_caption", lambda *_args: "")
    monkeypatch.setattr(
        routes,
        "render_template",
        lambda template, **context: captured.update(
            template=template, context=context
        )
        or context,
    )

    with app.test_request_context("/laporan/admin"):
        response = routes.admin_laporan_list()

    assert captured["template"] == "laporan/admin/list.html"
    assert response["read_only"] is True
    assert [form["id"] for form in response["forms"]] == [2]


def test_authorized_staff_can_open_report_answers_list(monkeypatch):
    app = Flask(__name__)
    _set_user(monkeypatch, "staff")
    monkeypatch.setattr(routes, "has_laporan_answer_access", lambda _user_id: True)
    monkeypatch.setattr(
        routes,
        "list_all_forms",
        lambda include_inactive: [
            {"id": 1, "status": "draft"},
            {"id": 2, "status": "published"},
        ],
    )
    monkeypatch.setattr(routes, "_annotate_repeat_form", lambda *_args: None)
    monkeypatch.setattr(routes, "_build_form_share_caption", lambda *_args: "")
    monkeypatch.setattr(
        routes, "render_template", lambda _template, **context: context
    )

    with app.test_request_context("/laporan/admin"):
        response = routes.admin_laporan_list()

    assert response["read_only"] is True
    assert [form["id"] for form in response["forms"]] == [2]


def test_staff_without_grant_cannot_open_report_answers_list(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    _set_user(monkeypatch, "staff")
    monkeypatch.setattr(routes, "has_laporan_answer_access", lambda _user_id: False)
    monkeypatch.setattr(
        routes,
        "list_all_forms",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not load forms")),
    )
    monkeypatch.setattr(
        routes,
        "url_for",
        lambda endpoint, **_values: (
            "/laporan/staff" if endpoint == "laporan.staff_laporan_list" else "/"
        ),
    )

    with app.test_request_context("/laporan/admin"):
        response = routes.admin_laporan_list()

    assert response.status_code == 302
    assert response.headers["Location"] == "/laporan/staff"


def test_admin_can_save_staff_report_answer_access(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    _set_user(monkeypatch, "admin")
    saved = []
    monkeypatch.setattr(
        routes,
        "replace_laporan_answer_access",
        lambda user_ids, granted_by: saved.append((user_ids, granted_by)) or len(user_ids),
    )
    monkeypatch.setattr(routes, "_record_laporan_admin_action", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        routes,
        "url_for",
        lambda endpoint, **_values: (
            "/laporan/admin/akses-jawaban"
            if endpoint == "laporan.admin_laporan_answer_access"
            else "/"
        ),
    )

    with app.test_request_context(
        "/laporan/admin/akses-jawaban",
        method="POST",
        data={"user_ids[]": ["12", "18"]},
    ):
        response = routes.admin_laporan_answer_access()

    assert saved == [([12, 18], 17)]
    assert response.status_code == 302
    assert response.headers["Location"] == "/laporan/admin/akses-jawaban"


def test_coordinator_staff_landing_redirects_to_report_answers(monkeypatch):
    app = Flask(__name__)
    _set_user(monkeypatch, "coordinator")
    monkeypatch.setattr(
        routes,
        "url_for",
        lambda endpoint, **_values: (
            "/laporan/admin"
            if endpoint == "laporan.admin_laporan_list"
            else f"/{endpoint}"
        ),
    )

    with app.test_request_context("/laporan/staff"):
        response = routes.staff_laporan_list()

    assert response.status_code == 302
    assert response.headers["Location"] == "/laporan/admin"


def test_coordinator_can_open_report_answers_in_read_only_mode(monkeypatch):
    app = Flask(__name__)
    captured = {}
    _set_user(monkeypatch, "coordinator")
    monkeypatch.setattr(routes, "sync_no_submissions", lambda _form_id: None)
    monkeypatch.setattr(
        routes,
        "get_form",
        lambda form_id: {
            "id": form_id,
            "status": "published",
            "repeat_policy": "once",
        },
    )
    monkeypatch.setattr(routes, "_annotate_repeat_form", lambda *_args: None)
    monkeypatch.setattr(routes, "get_form_fields", lambda _form_id: [])
    monkeypatch.setattr(routes, "list_form_submissions", lambda _form_id: [])
    monkeypatch.setattr(
        routes,
        "get_form_target_schools",
        lambda _form: [
            {
                "id": 20,
                "jenjang": "SD",
                "kecamatan_name": "KOJA",
                "status": "NEGERI",
            }
        ],
    )
    monkeypatch.setattr(
        routes,
        "render_template",
        lambda template, **context: captured.update(
            template=template, context=context
        )
        or context,
    )

    with app.test_request_context("/laporan/admin/2/jawaban"):
        response = routes.admin_laporan_answers(2)

    assert captured["template"] == "laporan/admin/answers.html"
    assert response["read_only"] is True
    assert response["export_filter_jenjangs"] == ["SD"]
    assert response["export_filter_kecamatans"] == ["KOJA"]
    assert response["export_filter_school_statuses"] == ["NEGERI"]


def test_admin_report_list_keeps_management_mode_and_drafts(monkeypatch):
    app = Flask(__name__)
    _set_user(monkeypatch, "admin")
    monkeypatch.setattr(
        routes,
        "list_all_forms",
        lambda include_inactive: [{"id": 1, "status": "draft"}],
    )
    monkeypatch.setattr(routes, "_annotate_repeat_form", lambda *_args: None)
    monkeypatch.setattr(
        routes, "render_template", lambda _template, **context: context
    )

    with app.test_request_context("/laporan/admin"):
        response = routes.admin_laporan_list()

    assert response["read_only"] is False
    assert [form["id"] for form in response["forms"]] == [1]
