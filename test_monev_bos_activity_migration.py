from __future__ import annotations

import os
import sys

from flask import Flask


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.monev_bos import routes


def _configure_activity_route(monkeypatch, activity):
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 10, "role": "sekolah"})
    monkeypatch.setattr(routes.queries, "get_active_periods", lambda: [{"id": 2}])
    monkeypatch.setattr(
        routes.queries,
        "get_school_report",
        lambda school_id, period_id: {"id": 7, "school_id": school_id, "status": "draft"},
    )
    monkeypatch.setattr(routes.queries, "get_activity_by_id", lambda activity_id: activity)
    monkeypatch.setattr(routes, "flash", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        routes,
        "url_for",
        lambda _endpoint, **values: f"/activities?period_id={values['period_id']}&fund_source={values['fund_source']}",
    )
    monkeypatch.setattr(routes, "redirect", lambda location: location)


def test_school_can_move_activity_from_bos_to_bop(monkeypatch):
    app = Flask(__name__)
    moves = []
    _configure_activity_route(
        monkeypatch,
        {"id": 23, "report_id": 7, "fund_source": "BOS", "status": "pending"},
    )
    monkeypatch.setattr(
        routes.queries,
        "move_activity_fund_source",
        lambda *args: moves.append(args) or True,
    )

    with app.test_request_context(
        "/monev-bos/sekolah/activities?period_id=2&fund_source=BOS",
        method="POST",
        data={
            "action": "move_activity_fund_source",
            "activity_id": "23",
            "target_fund_source": "BOP",
        },
    ):
        response = routes.sekolah_activities.__wrapped__()

    assert moves == [(23, 7, "BOP", 10)]
    assert response == "/activities?period_id=2&fund_source=BOP"


def test_school_cannot_move_valid_activity(monkeypatch):
    app = Flask(__name__)
    moves = []
    _configure_activity_route(
        monkeypatch,
        {"id": 23, "report_id": 7, "fund_source": "BOS", "status": "valid"},
    )
    monkeypatch.setattr(
        routes.queries,
        "move_activity_fund_source",
        lambda *args: moves.append(args) or True,
    )

    with app.test_request_context(
        "/monev-bos/sekolah/activities?period_id=2&fund_source=BOS",
        method="POST",
        data={
            "action": "move_activity_fund_source",
            "activity_id": "23",
            "target_fund_source": "BOP",
        },
    ):
        routes.sekolah_activities.__wrapped__()

    assert moves == []


def test_move_activity_updates_source_and_records_history(monkeypatch):
    statements = []

    class FakeCursor:
        rowcount = 1

        def execute(self, query, params):
            statements.append((" ".join(query.split()), params))

        def fetchone(self):
            return {
                "id": 23,
                "report_id": 7,
                "fund_source": "BOS",
                "status": "pending",
                "activity_code": "001",
                "activity_name": "Belanja ATK",
                "realized_amount": 100000,
            }

    class FakeCursorContext:
        def __enter__(self):
            return FakeCursor()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(routes.queries, "get_cursor", lambda **_kwargs: FakeCursorContext())

    assert routes.queries.move_activity_fund_source(23, 7, "BOP", 10) is True
    assert "INSERT INTO monev_bos_activity_history" in statements[1][0]
    assert "UPDATE monev_bos_activities SET fund_source = %s" in statements[2][0]
    assert statements[2][1] == ("BOP", 23, 7)
