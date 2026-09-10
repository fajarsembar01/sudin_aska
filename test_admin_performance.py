from __future__ import annotations

import io
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from flask import Flask

from dashboard import queries
from dashboard import routes as main_routes
from dashboard.pengaturan import routes as pengaturan_routes
from dashboard.pengaturan.admin_performance_pdf import build_admin_performance_pdf
from dashboard.pengaturan import github_performance


def test_laporan_autosave_is_excluded_from_admin_performance(monkeypatch):
    now = datetime.now(timezone.utc)

    class FakeCursor:
        def __init__(self):
            self.query = ""

        def execute(self, query, _params=None):
            self.query = " ".join(query.split())

        def fetchall(self):
            if "'dashboard_admin_action_logs' AS source" not in self.query:
                return []
            return [
                {
                    "source": "dashboard_admin_action_logs",
                    "feature_key": "laporan",
                    "created_at": now,
                    "actor_user_id": 1,
                    "actor_name": "Admin",
                    "actor_email": "admin@example.com",
                    "actor_label": "Admin",
                    "action": "AUTOSAVE",
                    "target_type": "LAPORAN_FORM",
                    "target_id": 10,
                    "target_name": "Draft",
                    "detail_text": "",
                },
                {
                    "source": "dashboard_admin_action_logs",
                    "feature_key": "laporan",
                    "created_at": now,
                    "actor_user_id": 1,
                    "actor_name": "Admin",
                    "actor_email": "admin@example.com",
                    "actor_label": "Admin",
                    "action": "PUBLISH",
                    "target_type": "LAPORAN_FORM",
                    "target_id": 10,
                    "target_name": "Laporan",
                    "detail_text": "",
                },
            ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(queries, "get_cursor", lambda **_kwargs: FakeCursor())

    events = queries.fetch_admin_activity_events()

    assert [event["action"] for event in events] == ["PUBLISH"]


def test_laporan_autosave_is_not_counted_in_performance_totals(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        queries,
        "fetch_admin_activity_events",
        lambda **_kwargs: [
            {
                "feature_key": "laporan",
                "created_at": now,
                "actor_user_id": 1,
                "actor_label": "Admin",
                "actor_name": "Admin",
                "actor_email": "admin@example.com",
                "action": "PUBLISH",
                "target_type": "LAPORAN_FORM",
                "search_text": "laporan admin publish",
            }
        ],
    )

    result = queries.fetch_admin_performance_data(feature_key="laporan")

    assert result["summary"]["total_actions"] == 1
    assert result["summary"]["earliest_action_at"] == now
    assert result["summary"]["latest_action_at"] == now
    assert result["feature_counts"]["laporan"] == 1
    assert result["top_actions"] == [{"action": "PUBLISH", "count": 1}]


def test_activity_dates_are_applied_to_every_source_query(monkeypatch):
    calls = []

    class FakeCursor:
        def execute(self, query, params=None):
            calls.append((" ".join(query.split()), tuple(params or ())))

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(queries, "get_cursor", lambda **_kwargs: FakeCursor())
    start = datetime(2026, 9, 1, 14, 30)
    end = datetime(2026, 9, 30, 18, 45)

    queries.fetch_admin_activity_events(start=start, end=end)

    assert len(calls) == 11
    for sql, params in calls:
        assert "admin_performance_date_filter" not in sql
        assert ">= %s" in sql and "< %s" in sql
        assert params == (datetime(2026, 9, 1), datetime(2026, 10, 1))


@pytest.mark.parametrize(
    "query_string,expected_scope,expected_start,expected_end",
    [
        ("", "month", datetime(2026, 9, 1), datetime(2026, 9, 30)),
        (
            "?period_scope=month&month=2026-02",
            "month",
            datetime(2026, 2, 1),
            datetime(2026, 2, 28),
        ),
        (
            "?period_scope=year&year=2025",
            "year",
            datetime(2025, 1, 1),
            datetime(2025, 12, 31),
        ),
        ("?period_scope=all", "all", None, None),
    ],
)
def test_admin_performance_period_scope(
    monkeypatch, query_string, expected_scope, expected_start, expected_end
):
    app = Flask(__name__)
    captured = {}

    def fake_fetch(**kwargs):
        captured["fetch"] = kwargs
        return {}

    monkeypatch.setattr(
        pengaturan_routes,
        "current_jakarta_time",
        lambda: datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        pengaturan_routes, "fetch_admin_performance_data", fake_fetch
    )
    monkeypatch.setattr(
        pengaturan_routes,
        "_github_performance_context",
        lambda _period: {
            "repository": "fajarsembar01/sudin_aska",
            "period_key": "all",
            "snapshots": {},
            "accounts": [],
            "last_synced_at": None,
        },
    )
    monkeypatch.setattr(
        pengaturan_routes, "get_commit_daily_series", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        pengaturan_routes,
        "get_commit_line_totals",
        lambda *_args, **_kwargs: {
            "additions": 0,
            "deletions": 0,
            "changed_lines": 0,
            "measured_commits": 0,
            "total_commits": 0,
            "missing_commits": 0,
        },
    )
    monkeypatch.setattr(
        pengaturan_routes,
        "render_template",
        lambda _template, **context: context["performance"],
    )

    with app.test_request_context(
        "/dashboard/pengaturan/admin-performance" + query_string
    ):
        performance = pengaturan_routes.admin_performance.__wrapped__()

    assert captured["fetch"]["start"] == expected_start
    assert captured["fetch"]["end"] == expected_end
    assert performance["period_scope"] == expected_scope
    assert performance["selected_month"]
    assert performance["selected_year"] == (
        2025 if expected_scope == "year" else 2026
    )


def test_old_admin_performance_url_redirects_with_filters():
    app = Flask(__name__)
    app.add_url_rule(
        "/dashboard/pengaturan/admin-performance",
        endpoint="pengaturan.admin_performance",
        view_func=lambda: "",
    )
    with app.test_request_context(
        "/overview/admin-performance?period_scope=year&year=2025"
    ):
        response = main_routes.admin_performance.__wrapped__()

    assert response.status_code == 302
    assert response.location.endswith(
        "/dashboard/pengaturan/admin-performance?period_scope=year&year=2025"
    )


def test_complete_leaderboard_includes_zero_activity_admins():
    rows = pengaturan_routes._complete_admin_leaderboard(
        [
            {
                "actor_user_id": 1,
                "actor_label": "Admin Aktif",
                "total_actions": 4,
                "feature_counts": {"panbers": 4},
            },
            {
                "actor_user_id": 3,
                "actor_label": "Admin Nonaktif",
                "total_actions": 20,
                "feature_counts": {"panbers": 20},
            },
        ],
        [
            {"id": 1, "full_name": "Admin Aktif", "email": "a@example.com"},
            {"id": 2, "full_name": "Admin Nol", "email": "b@example.com"},
        ],
    )

    assert [row["actor_user_id"] for row in rows] == [1, 2]
    assert rows[1]["total_actions"] == 0


def test_leaderboard_rank_uses_actions_plus_ten_points_per_coding_update():
    rows = pengaturan_routes._score_admin_leaderboard(
        [
            {
                "actor_user_id": 1,
                "actor_label": "Rajin Coding",
                "total_actions": 2,
                "github_commits": 3,
            },
            {
                "actor_user_id": 2,
                "actor_label": "Rajin ASKA",
                "total_actions": 20,
                "github_commits": 0,
            },
            {
                "actor_user_id": 3,
                "actor_label": "Tanpa Aktivitas",
                "total_actions": 0,
                "github_commits": 0,
            },
        ]
    )

    assert [row["actor_user_id"] for row in rows] == [1, 2, 3]
    assert rows[0]["coding_points"] == 30
    assert rows[0]["performance_total"] == 32
    assert rows[2]["performance_total"] == 0


def test_leaderboard_uses_active_coding_days_for_score():
    rows = pengaturan_routes._score_admin_leaderboard(
        [{
            "actor_user_id": 1,
            "actor_label": "Admin Coding",
            "total_actions": 4,
            "github_commits": 9,
            "github_coding_days": 2,
        }]
    )

    assert rows[0]["coding_score_units"] == 2
    assert rows[0]["coding_points"] == 20
    assert rows[0]["performance_total"] == 24


def test_markdown_is_excluded_from_code_line_counts():
    assert github_performance._is_code_path("dashboard/routes.py") is True
    assert github_performance._is_code_path("templates/page.html") is True
    assert github_performance._is_code_path("README.md") is False
    assert github_performance._is_code_path("docs/CHANGELOG.MD") is False


def test_pdf_ignores_selected_admin_and_uses_logged_in_admin(monkeypatch):
    app = Flask(__name__)
    source_events = [{"id": "shared"}]
    calls = []

    def fake_performance(**kwargs):
        calls.append(kwargs)
        return {
            "feature_options": {"all": "Semua Fitur"},
            "leaderboard": [
                {
                    "actor_user_id": 7,
                    "actor_label": "Pengunduh",
                    "total_actions": 1,
                    "feature_counts": {"panbers": 1},
                }
            ],
            "summary": {},
            "top_actions": [],
            "top_targets": [],
            "top_features": [],
            "detail_rows": [],
        }

    monkeypatch.setattr(
        pengaturan_routes,
        "current_jakarta_time",
        lambda: datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        pengaturan_routes, "current_user", lambda: {"id": 7, "full_name": "Pengunduh", "email": "p@example.com"}
    )
    monkeypatch.setattr(
        pengaturan_routes,
        "fetch_admin_activity_events",
        lambda **_kwargs: source_events,
    )
    monkeypatch.setattr(
        pengaturan_routes, "fetch_admin_performance_data", fake_performance
    )
    monkeypatch.setattr(
        pengaturan_routes,
        "list_admin_users",
        lambda: [{"id": 7, "full_name": "Pengunduh", "email": "p@example.com"}],
    )
    monkeypatch.setattr(
        pengaturan_routes,
        "_github_performance_context",
        lambda _period: {
            "repository": "fajarsembar01/sudin_aska",
            "snapshots": {},
            "accounts": [],
            "last_synced_at": None,
        },
    )
    build_pdf = Mock(return_value=io.BytesIO(b"%PDF-test"))
    monkeypatch.setattr(pengaturan_routes, "build_admin_performance_pdf", build_pdf)

    with app.test_request_context(
        "/dashboard/pengaturan/admin-performance/pdf?admin_id=999&period_scope=month&month=2026-09"
    ):
        response = pengaturan_routes.admin_performance_pdf.__wrapped__()

    assert [call["admin_id"] for call in calls] == [None, 7]
    assert all(call["source_events"] is source_events for call in calls)
    assert build_pdf.call_args.kwargs["downloader"]["id"] == 7
    assert response.mimetype == "application/pdf"
    assert "performa-admin-2026-09-7.pdf" in response.headers["Content-Disposition"]
    assert response.headers["Cache-Control"] == "private, no-store"


def test_performance_pdf_has_leaderboard_personal_and_activity_pages():
    output = build_admin_performance_pdf(
        leaderboard=[
            {
                "actor_user_id": 1,
                "actor_label": "Admin Satu",
                "actor_email": "satu@example.com",
                "total_actions": 3,
                "feature_counts": {"panbers": 3},
                "last_action_at": datetime(2026, 9, 8, 10, 0),
            }
        ],
        personal={
            "summary": {"total_actions": 3, "total_features": 1},
            "top_actions": [{"action": "UPDATE", "count": 3}],
            "top_targets": [{"target_type": "SCHOOL", "count": 3}],
            "top_features": [{"feature_label": "PANBERSS", "count": 3}],
            "detail_rows": [],
        },
        downloader={"id": 1, "full_name": "Admin Satu", "email": "satu@example.com"},
        period_label="September 2026",
        filters_label="Fitur: Semua | Aksi: Semua | Target: Semua",
        generated_at=datetime(2026, 9, 8, 12, 0),
        feature_options={"panbers": "PANBERSS"},
    ).getvalue()

    assert output.startswith(b"%PDF")
    assert b"/Count 3" in output
    assert len(output) > 50_000


def test_github_commit_batches_are_bounded_and_use_last_sync(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'[{"sha":"abc","html_url":"https://github.com/x/y/commit/abc","commit":{"message":"Fix","author":{"date":"2026-09-08T10:00:00Z"}}}]'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(github_performance, "urlopen", fake_urlopen)
    last_sync = datetime(2026, 9, 1, tzinfo=timezone.utc)
    batches = list(
        github_performance.fetch_commit_batches(
            "https://github.com/fajarsembar01/sudin_aska",
            "fajarsembar01",
            since=last_sync,
        )
    )

    assert batches[0][0]["sha"] == "abc"
    assert "author=fajarsembar01" in captured["url"]
    assert "per_page=100" in captured["url"]
    assert "since=2026-09-01" in captured["url"]
    assert captured["timeout"] == 12


def test_duplicate_github_username_cannot_be_mapped_to_two_admins():
    with pytest.raises(ValueError, match="satu admin"):
        github_performance.save_admin_github_accounts(
            [
                {"id": 1, "github_username": "same-user"},
                {"id": 2, "github_username": "SAME-USER"},
            ]
        )


def test_github_sync_route_uses_incremental_service(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    app.add_url_rule(
        "/dashboard/pengaturan/admin-performance",
        endpoint="pengaturan.admin_performance",
        view_func=lambda: "",
    )
    requested = []
    monkeypatch.setattr(
        pengaturan_routes,
        "current_jakarta_time",
        lambda: datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(pengaturan_routes, "current_user", lambda: {"id": 9})
    monkeypatch.setattr(
        pengaturan_routes, "get_system_setting", lambda *_args: "fajarsembar01/sudin_aska"
    )
    monkeypatch.setattr(
        pengaturan_routes,
        "list_admin_github_accounts",
        lambda: [{"id": 3, "full_name": "Admin Git", "github_username": "admin-git"}],
    )

    def fake_sync(repository, username, **kwargs):
        requested.append((repository, username, kwargs))
        return {"inserted": 2, "initial": False}

    monkeypatch.setattr(pengaturan_routes, "sync_admin_commits", fake_sync)
    hydrated = []
    monkeypatch.setattr(
        pengaturan_routes,
        "hydrate_commit_line_stats",
        lambda repository, username, **kwargs: hydrated.append(
            (repository, username, kwargs)
        ) or {"updated": 2},
    )

    with app.test_request_context(
        "/dashboard/pengaturan/admin-performance/github-sync",
        method="POST",
        data={"period_scope": "year", "year": "2025"},
    ):
        response = pengaturan_routes.admin_performance_github_sync.__wrapped__()

    assert response.status_code == 302
    assert requested == [
        (
            "fajarsembar01/sudin_aska",
            "admin-git",
            {"synced_by": 9, "author_email": ""},
        )
    ]
    assert hydrated == [
        (
            "fajarsembar01/sudin_aska",
            "admin-git",
            {"start": None, "end": None},
        )
    ]


def test_incremental_sync_starts_at_last_successful_sync(monkeypatch):
    last_sync = datetime(2026, 8, 31, 17, 0, tzinfo=timezone.utc)
    captured = {}
    states = []
    monkeypatch.setattr(github_performance, "get_last_sync", lambda *_args: last_sync)

    def fake_batches(_repository, _username, *, since, author_identity):
        captured["since"] = since
        captured["author_identity"] = author_identity
        yield [{"sha": "new", "committed_at": "2026-09-01T01:00:00Z"}]

    monkeypatch.setattr(github_performance, "fetch_commit_batches", fake_batches)
    monkeypatch.setattr(github_performance, "_save_commit_batch", lambda *_args: 1)
    monkeypatch.setattr(
        github_performance,
        "_save_sync_state",
        lambda *args, **kwargs: states.append((args, kwargs)),
    )

    result = github_performance.sync_admin_commits(
        "fajarsembar01/sudin_aska", "Admin-Git", synced_by=9
    )

    assert captured["since"] == last_sync
    assert captured["author_identity"] == "admin-git"
    assert result["inserted"] == 1
    assert result["initial"] is False
    assert states[-1][1]["error"] is None


def test_initial_sync_checks_username_and_all_author_emails(monkeypatch):
    identities = []
    monkeypatch.setattr(github_performance, "get_last_sync", lambda *_args: None)

    def fake_batches(_repository, _username, *, since, author_identity):
        identities.append((since, author_identity))
        return iter(())

    monkeypatch.setattr(github_performance, "fetch_commit_batches", fake_batches)
    monkeypatch.setattr(github_performance, "_save_sync_state", lambda *_args, **_kwargs: None)

    result = github_performance.sync_admin_commits(
        "fajarsembar01/sudin_aska",
        "Admin-Git",
        synced_by=9,
        author_email="one@computer.local, two@computer.local",
    )

    assert identities == [
        (None, "admin-git"),
        (None, "one@computer.local"),
        (None, "two@computer.local"),
    ]
    assert result["initial"] is True


def test_line_stats_only_count_source_code_paths():
    assert github_performance._is_code_path("dashboard/routes.py") is True
    assert github_performance._is_code_path("templates/page.html") is True
    assert github_performance._is_code_path("node_modules/pkg/index.js") is False
    assert github_performance._is_code_path("uploads/report.json") is False
    assert github_performance._is_code_path("data/export.csv") is False
