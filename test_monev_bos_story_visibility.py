from __future__ import annotations

from flask import Flask

from dashboard.monev_bos import routes


def test_school_can_view_another_schools_active_story(monkeypatch):
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 10, "role": "sekolah"})

    assert routes._can_view_school_post_photo({
        "school_user_id": 20,
        "is_public": False,
        "is_active_story": True,
    }) is True


def test_school_cannot_view_another_schools_expired_private_story(monkeypatch):
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 10, "role": "sekolah"})

    assert routes._can_view_school_post_photo({
        "school_user_id": 20,
        "is_public": False,
        "is_active_story": False,
    }) is False


def test_school_story_explore_only_requests_shared_posts(monkeypatch):
    app = Flask(__name__)
    calls = []
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 10, "role": "sekolah"})
    monkeypatch.setattr(
        routes.queries,
        "list_school_posts",
        lambda **kwargs: calls.append(kwargs) or [],
    )
    monkeypatch.setattr(routes, "render_template", lambda template, **context: (template, context))

    with app.test_request_context("/monev-bos/posts?q=komputer"):
        template, context = routes.school_posts_explore.__wrapped__()

    assert template == "monev_bos/social/posts.html"
    assert context["posts"] == []
    assert calls == [{"search_query": "komputer", "shared_only": True, "limit": 300}]
