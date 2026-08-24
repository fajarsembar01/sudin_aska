from __future__ import annotations

from datetime import datetime, timezone

from dashboard import queries


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
        lambda: [
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
    assert result["feature_counts"]["laporan"] == 1
    assert result["top_actions"] == [{"action": "PUBLISH", "count": 1}]
