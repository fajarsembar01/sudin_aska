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


def test_activity_duplicate_lookup_is_scoped_to_open_report_and_fund(monkeypatch):
    executed = {}

    class FakeCursor:
        def execute(self, query, params):
            executed["query"] = " ".join(query.split())
            executed["params"] = params

        def fetchall(self):
            return [
                {
                    "id": 23,
                    "activity_name": "Pelaksanaan Ekstrakurikuler",
                    "bku_number": "BKU/001/2026",
                    "account_code": "5.1.02",
                    "realized_amount": 1250000,
                    "vendor_name": "Budi",
                    "item_name": "Honor instruktur",
                    "status": "pending",
                }
            ]

    class FakeCursorContext:
        def __enter__(self):
            return FakeCursor()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(routes.queries, "get_cursor", lambda **_kwargs: FakeCursorContext())

    matches = routes.queries.find_activity_duplicate_matches_for_data(
        7,
        "BOS",
        {
            "activity_name": "  Pelaksanaan   Ekstrakurikuler ",
            "bku_number": "BKU-001-2026",
        },
    )

    assert executed["params"] == (7, "BOS")
    assert "WHERE report_id = %s AND fund_source = %s" in executed["query"]
    assert matches[0]["duplicate_fields"] == ["Nama kegiatan", "No. BKU"]


def test_school_duplicate_activity_requires_kegiatan_berbeda_confirmation(monkeypatch):
    app = Flask(__name__)
    created = []
    _configure_activity_route(monkeypatch, None)
    monkeypatch.setattr(routes, "_resolve_school_report_vendors", lambda _values: ([], [], None))
    monkeypatch.setattr(
        routes.queries,
        "find_activity_duplicate_matches_for_data",
        lambda *_args, **_kwargs: [{"id": 23, "duplicate_fields": ["Nama kegiatan"]}],
    )
    monkeypatch.setattr(
        routes.queries,
        "create_activity",
        lambda *args: created.append(args) or 24,
    )

    with app.test_request_context(
        "/monev-bos/sekolah/activities?period_id=2&fund_source=BOS",
        method="POST",
        data={
            "action": "add_activity",
            "fund_source": "BOS",
            "activity_name": "Pelaksanaan Ekstrakurikuler",
            "bku_number": "BKU/001/2026",
            "realized_amount": "1.250.000",
        },
    ):
        response = routes.sekolah_activities.__wrapped__()

    assert created == []
    assert response == "/activities?period_id=2&fund_source=BOS"


def test_school_can_confirm_duplicate_activity_is_different(monkeypatch):
    app = Flask(__name__)
    created = []
    _configure_activity_route(monkeypatch, None)
    monkeypatch.setattr(routes, "_resolve_school_report_vendors", lambda _values: ([], [], None))
    monkeypatch.setattr(
        routes.queries,
        "find_activity_duplicate_matches_for_data",
        lambda *_args, **_kwargs: [{"id": 23, "duplicate_fields": ["Nama kegiatan"]}],
    )
    monkeypatch.setattr(
        routes.queries,
        "create_activity",
        lambda *args: created.append(args) or 24,
    )
    monkeypatch.setattr(routes.queries, "set_activity_vendors", lambda *_args: None)

    with app.test_request_context(
        "/monev-bos/sekolah/activities?period_id=2&fund_source=BOS",
        method="POST",
        data={
            "action": "add_activity",
            "fund_source": "BOP",
            "activity_name": "Pelaksanaan Ekstrakurikuler",
            "bku_number": "BKU/001/2026",
            "realized_amount": "1.250.000",
            "duplicate_confirmation": "kegiatan berbeda",
        },
    ):
        response = routes.sekolah_activities.__wrapped__()

    assert created[0][0:2] == (7, "BOS")
    assert response == "/activities?period_id=2&fund_source=BOS"
