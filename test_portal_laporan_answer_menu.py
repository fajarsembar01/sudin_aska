from __future__ import annotations

from flask import Flask

from dashboard.portal import routes


def test_staff_with_access_gets_answer_report_card_on_oss(monkeypatch):
    app = Flask(__name__)
    user = {
        "id": 17,
        "role": "staff",
        "full_name": "Staff Uji",
        "email": "staff@example.com",
    }
    monkeypatch.setattr(routes, "current_user", lambda: user)
    monkeypatch.setattr(routes, "_require_profile_photo_redirect", lambda _user: None)
    monkeypatch.setattr(routes, "_staff_can_view_laporan_answers", lambda _user: True)
    monkeypatch.setattr(routes, "url_for", lambda endpoint, **_values: f"/{endpoint}")
    monkeypatch.setattr(
        routes,
        "render_template",
        lambda _template, **context: context,
    )

    with app.test_request_context("/"):
        response = routes.home.__wrapped__()

    report_cards = [
        card for card in response["cards"] if card["title"] == "Jawaban Laporan"
    ]
    assert len(report_cards) == 1
    assert report_cards[0]["href"] == "/laporan.admin_laporan_list"


def test_staff_without_access_does_not_get_answer_report_card_on_oss(monkeypatch):
    app = Flask(__name__)
    user = {
        "id": 18,
        "role": "staff",
        "full_name": "Staff Tanpa Akses",
        "email": "staff2@example.com",
    }
    monkeypatch.setattr(routes, "current_user", lambda: user)
    monkeypatch.setattr(routes, "_require_profile_photo_redirect", lambda _user: None)
    monkeypatch.setattr(routes, "_staff_can_view_laporan_answers", lambda _user: False)
    monkeypatch.setattr(routes, "url_for", lambda endpoint, **_values: f"/{endpoint}")
    monkeypatch.setattr(
        routes,
        "render_template",
        lambda _template, **context: context,
    )

    with app.test_request_context("/"):
        response = routes.home.__wrapped__()

    assert all(card["title"] != "Jawaban Laporan" for card in response["cards"])
