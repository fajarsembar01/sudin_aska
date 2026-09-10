from datetime import date
from flask import Flask

from dashboard import queries as dashboard_queries
from dashboard.portal import queries, routes


class DraftCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), tuple(params)))

    def fetchall(self):
        return []


def test_draft_query_enforces_batch_limit_and_offset(monkeypatch):
    cursor = DraftCursor()
    monkeypatch.setattr(queries, "get_cursor", lambda: cursor)

    queries.list_draft_assessments(limit=5000, offset=-10)

    sql, params = cursor.calls[0]
    assert "LIMIT %s OFFSET %s" in sql
    assert params[-2:] == (200, 0)


def test_draft_analysis_batches_inputs_and_only_keeps_requested_page(monkeypatch):
    app = Flask(__name__)
    app.add_url_rule(
        "/admin/drafts",
        endpoint="portal.admin_draft_analysis",
        view_func=lambda: "",
    )
    rows = [
        {
            "id": item_id,
            "school_id": 1,
            "staff_id": 7,
            "school_jenjang": "SD",
            "school_name": f"Sekolah {item_id}",
            "staff_name": "Staff Uji",
            "created_at": None,
            "updated_at": None,
        }
        for item_id in range(1, 231)
    ]
    batch_calls = []

    def fetch_batch(**kwargs):
        batch_calls.append((kwargs["limit"], kwargs["offset"], kwargs["period_id"]))
        start = kwargs["offset"]
        return rows[start : start + kwargs["limit"]]

    input_calls = []

    def fetch_inputs(ids):
        input_calls.append(list(ids))
        return {"scores": {}, "photos": {}, "notes": {}}

    monkeypatch.setattr(
        routes,
        "list_periods",
        lambda: [
            {
                "id": 9,
                "name": "September 2026",
                "start_date": date(2026, 9, 1),
                "is_active": True,
            }
        ],
    )
    monkeypatch.setattr(routes, "list_draft_assessments", fetch_batch)
    monkeypatch.setattr(routes, "get_draft_assessment_inputs", fetch_inputs)
    monkeypatch.setattr(routes, "list_school_rooms", lambda _school_id: [])
    monkeypatch.setattr(routes, "list_draft_assessment_staff_options", lambda **_kwargs: [])
    monkeypatch.setattr(dashboard_queries, "get_monev_teams", lambda: [])
    captured = {}

    def fake_render(template, **context):
        captured.update(template=template, **context)
        return "ok"

    monkeypatch.setattr(routes, "render_template", fake_render)

    with app.test_request_context("/admin/drafts?page=2&state=empty"):
        response = routes.admin_draft_analysis.__wrapped__()

    assert response == "ok"
    assert batch_calls == [(100, 0, 9), (100, 100, 9), (100, 200, 9)]
    assert [len(ids) for ids in input_calls] == [100, 100, 30]
    assert [row["id"] for row in captured["drafts"]] == list(range(26, 51))
    assert captured["all_draft_count"] == 230
    assert captured["summary"]["empty"] == 230
    assert captured["total_pages"] == 10
    assert "page=3" in captured["next_page_url"]
    assert "state=empty" in captured["next_page_url"]


def test_incremental_summary_matches_existing_summary():
    rows = [
        {
            "id": 1,
            "draft_state": "empty",
            "is_filled": False,
            "staff_id": 7,
            "staff_name": "B",
            "age_days": 3,
        },
        {
            "id": 2,
            "draft_state": "ready",
            "is_filled": True,
            "staff_id": 8,
            "staff_name": "A",
            "age_days": 5,
        },
    ]
    accumulator = routes._new_draft_analysis_summary()
    for row in rows:
        routes._accumulate_draft_analysis_summary(accumulator, row)

    assert routes._finalize_draft_analysis_summary(accumulator) == (
        routes._summarize_draft_analysis(rows)
    )
