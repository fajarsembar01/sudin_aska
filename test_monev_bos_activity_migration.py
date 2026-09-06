from __future__ import annotations

import os
import sys

from flask import Flask


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.monev_bos import routes


def test_school_bku_number_requires_exactly_three_digits():
    assert routes._school_bku_number("001") == ("001", None)
    assert routes._school_bku_number("01")[1] is not None
    assert routes._school_bku_number("B01")[1] is not None
    assert routes._school_bku_number("0001")[1] is not None


def _configure_activity_route(monkeypatch, activity, report_status="draft"):
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 10, "role": "sekolah"})
    monkeypatch.setattr(routes.queries, "get_active_periods", lambda: [{"id": 2}])
    monkeypatch.setattr(
        routes.queries,
        "get_school_report",
        lambda school_id, period_id: {"id": 7, "school_id": school_id, "status": report_status},
    )
    monkeypatch.setattr(routes.queries, "get_activity_by_id", lambda activity_id: activity)
    monkeypatch.setattr(routes, "flash", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        routes,
        "url_for",
        lambda _endpoint, **values: f"/activities?period_id={values['period_id']}&fund_source={values['fund_source']}",
    )
    monkeypatch.setattr(routes, "redirect", lambda location: location)


def test_school_can_delete_pending_activity_while_report_is_in_review(monkeypatch):
    app = Flask(__name__)
    deleted = []
    _configure_activity_route(
        monkeypatch,
        {"id": 23, "report_id": 7, "fund_source": "BOS", "status": "pending"},
        report_status="in_review",
    )
    monkeypatch.setattr(routes.queries, "delete_activity", lambda activity_id: deleted.append(activity_id))

    with app.test_request_context(
        "/monev-bos/sekolah/activities?period_id=2&fund_source=BOS",
        method="POST",
        data={"action": "delete_activity", "activity_id": "23"},
    ):
        routes.sekolah_activities.__wrapped__()

    assert deleted == [23]


def test_school_can_edit_pending_activity_while_report_is_submitted(monkeypatch):
    app = Flask(__name__)
    updated = []
    _configure_activity_route(
        monkeypatch,
        {"id": 23, "report_id": 7, "fund_source": "BOS", "status": "pending"},
        report_status="submitted",
    )
    monkeypatch.setattr(routes.queries, "get_activity_post_links", lambda _activity_id: [])
    monkeypatch.setattr(routes.queries, "count_valid_field_photos", lambda _activity_id: 0)
    monkeypatch.setattr(routes.queries, "update_activity", lambda activity_id, data: updated.append((activity_id, data)))
    monkeypatch.setattr(routes.queries, "set_activity_vendors", lambda *_args: None)
    monkeypatch.setattr(routes.queries, "update_activity_audit", lambda *_args: None)

    with app.test_request_context(
        "/monev-bos/sekolah/activities?period_id=2&fund_source=BOS",
        method="POST",
        data={
            "action": "edit_activity",
            "activity_id": "23",
            "activity_name": "Belanja ATK diperbarui",
            "bku_number": "001",
            "realized_amount": "100000",
        },
    ):
        routes.sekolah_activities.__wrapped__()

    assert updated[0][0] == 23
    assert updated[0][1]["activity_name"] == "Belanja ATK diperbarui"


def test_school_cannot_delete_activity_from_completed_report(monkeypatch):
    app = Flask(__name__)
    deleted = []
    _configure_activity_route(
        monkeypatch,
        {"id": 23, "report_id": 7, "fund_source": "BOS", "status": "pending"},
        report_status="completed",
    )
    monkeypatch.setattr(routes.queries, "delete_activity", lambda activity_id: deleted.append(activity_id))

    with app.test_request_context(
        "/monev-bos/sekolah/activities?period_id=2&fund_source=BOS",
        method="POST",
        data={"action": "delete_activity", "activity_id": "23"},
    ):
        routes.sekolah_activities.__wrapped__()

    assert deleted == []


def test_school_cannot_delete_valid_activity(monkeypatch):
    app = Flask(__name__)
    deleted = []
    _configure_activity_route(
        monkeypatch,
        {"id": 23, "report_id": 7, "fund_source": "BOS", "status": "valid"},
        report_status="submitted",
    )
    monkeypatch.setattr(routes.queries, "delete_activity", lambda activity_id: deleted.append(activity_id))

    with app.test_request_context(
        "/monev-bos/sekolah/activities?period_id=2&fund_source=BOS",
        method="POST",
        data={"action": "delete_activity", "activity_id": "23"},
    ):
        routes.sekolah_activities.__wrapped__()

    assert deleted == []


def test_school_cannot_mutate_activity_from_another_report():
    report = {"id": 7, "status": "submitted"}
    activity = {"id": 23, "report_id": 99, "status": "pending"}

    assert routes._school_activity_mutation_error(report, activity) is not None


def test_school_cannot_mutate_activity_from_completed_with_notes_report():
    report = {"id": 7, "status": "completed_with_notes"}
    activity = {"id": 23, "report_id": 7, "status": "pending"}

    assert routes._school_activity_mutation_error(report, activity) is not None


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


def test_activity_duplicate_lookup_allows_repeated_name_when_bku_is_different(monkeypatch):
    class FakeCursor:
        def execute(self, _query, _params):
            pass

        def fetchall(self):
            return [
                {
                    "id": 23,
                    "activity_name": "Pelaksanaan Ekstrakurikuler",
                    "bku_number": "BKU/002/2026",
                    "account_code": "5.1.02",
                    "realized_amount": 1250000,
                    "vendor_name": "Budi",
                    "item_name": "Honor instruktur",
                    "status": "pending",
                },
                {
                    "id": 24,
                    "activity_name": "Pembelian Alat Tulis",
                    "bku_number": "BKU-001-2026",
                    "account_code": "5.1.02",
                    "realized_amount": 500000,
                    "vendor_name": "Toko Maju",
                    "item_name": "ATK",
                    "status": "pending",
                },
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
            "activity_name": "Pelaksanaan Ekstrakurikuler",
            "bku_number": "BKU/001/2026",
        },
    )

    assert [match["id"] for match in matches] == [24]
    assert matches[0]["duplicate_fields"] == ["No. BKU"]


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
            "bku_number": "001",
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
            "bku_number": "001",
            "realized_amount": "1.250.000",
            "duplicate_confirmation": "kegiatan berbeda",
        },
    ):
        response = routes.sekolah_activities.__wrapped__()

    assert created[0][0:2] == (7, "BOS")
    assert response == "/activities?period_id=2&fund_source=BOS"
