from datetime import datetime

from dashboard.monev_bos import queries
from dashboard.monev_bos.staff_performance_pdf import (
    _leaderboard_window,
    build_staff_performance_pdf,
)


def test_staff_performance_score_and_rank(monkeypatch):
    class FakeCursor:
        def execute(self, _query, _params):
            pass

        def fetchall(self):
            return [
                {
                    "staff_id": 1,
                    "staff_name": "Staff Satu",
                    "total_actions": 10,
                    "validated_activities": 3,
                    "completed_reports": 1,
                    "uploaded_photos": 2,
                    "supporting_actions": 2,
                    "vendor_decisions": 2,
                    "active_days": 2,
                },
                {
                    "staff_id": 2,
                    "staff_name": "Staff Dua",
                    "total_actions": 5,
                    "validated_activities": 4,
                    "completed_reports": 0,
                    "uploaded_photos": 0,
                    "supporting_actions": 1,
                    "vendor_decisions": 0,
                    "active_days": 1,
                },
            ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(queries, "get_cursor", lambda **_kwargs: FakeCursor())

    rows = queries.list_staff_performance()

    assert [(row["staff_id"], row["score"], row["rank"]) for row in rows] == [
        (1, 10, 1),
        (2, 5, 2),
    ]


def test_staff_performance_pdf_contains_leaderboard_and_personal_page():
    now = datetime(2026, 9, 9, 12, 0)
    leaderboard = [
        {
            "rank": 1,
            "staff_id": 1,
            "staff_name": "Staff Satu",
            "staff_email": "staff@example.com",
            "score": 43,
            "validated_activities": 3,
            "completed_reports": 1,
            "uploaded_photos": 2,
            "active_days": 2,
            "last_action_at": now,
        }
    ]
    personal = {
        "summary": leaderboard[0],
        "action_counts": [{"action": "VALIDATE", "count": 3}],
        "recent_actions": [
            {
                "created_at": now,
                "school_name": "SDN Contoh",
                "action": "VALIDATE",
                "activity_name": "Kegiatan Contoh",
            }
        ],
    }

    output = build_staff_performance_pdf(
        leaderboard=leaderboard,
        personal=personal,
        downloader={"id": 1, "full_name": "Staff Satu", "email": "staff@example.com"},
        period_label="TW 3 Tahun 2026",
        generated_at=now,
    ).getvalue()

    assert output.startswith(b"%PDF")
    assert b"/Count 3" in output
    assert len(output) > 40_000


def test_pdf_leaderboard_window_centers_downloader_and_caps_at_twenty_five():
    rows = [{"staff_id": index, "rank": index} for index in range(1, 61)]

    middle = _leaderboard_window(rows, staff_id=30)
    near_top = _leaderboard_window(rows, staff_id=2)
    near_bottom = _leaderboard_window(rows, staff_id=59)

    assert [row["rank"] for row in middle] == list(range(18, 43))
    assert [row["rank"] for row in near_top] == list(range(1, 26))
    assert [row["rank"] for row in near_bottom] == list(range(36, 61))
