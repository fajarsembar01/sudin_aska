from pathlib import Path

import pytest
from flask import Flask, session

from dashboard.monev_bos import routes
from dashboard.monev_bos import monev_bos_bp
from dashboard.monev_bos.external_photos import (
    access_token_matches,
    generate_access_token,
    validate_external_identity,
    validate_external_nip,
)


def test_external_access_token_is_always_six_digits():
    tokens = {generate_access_token() for _ in range(100)}
    assert tokens
    assert all(len(token) == 6 and token.isdigit() for token in tokens)


@pytest.mark.parametrize(
    ("name", "nip", "is_valid"),
    [
        ("Siti Aminah", "198705122010012001", True),
        ("", "198705122010012001", False),
        ("Siti Aminah", "19870512201001200", False),
        ("Siti Aminah", "19870512201001200A", False),
    ],
)
def test_external_teacher_identity_requires_name_and_18_digit_nip(name, nip, is_valid):
    assert (not validate_external_identity(name, nip)) is is_valid


def test_external_access_token_comparison_rejects_wrong_format_or_value():
    assert access_token_matches("001234", "001234")
    assert not access_token_matches("1234", "001234")
    assert not access_token_matches("001235", "001234")
    assert not access_token_matches("abcdef", "abcdef")


def test_external_nip_can_be_validated_without_requesting_teacher_name():
    assert validate_external_nip("198705122010012001") == []
    assert validate_external_nip("19870512201001200A")


def test_external_capture_template_does_not_request_teacher_name_again():
    template = Path(
        "dashboard/monev_bos/templates/monev_bos/social/external_photo_capture.html"
    ).read_text(encoding="utf-8")
    assert 'name="teacher_name"' not in template
    assert 'name="teacher_nip"' in template


def test_token_attempts_are_rate_limited_after_five_failures():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    with app.test_request_context("/foto-eksternal/example"):
        for _ in range(5):
            routes._record_external_photo_token_failure("example")
        assert routes._external_photo_token_is_rate_limited("example")
        assert session["external_photo_attempt:example"]["count"] == 5


def test_external_capture_opens_photo_step_only_after_identity_verification(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(monev_bos_bp)
    monkeypatch.setattr(
        routes.queries,
        "get_external_photo_link",
        lambda public_id: {
            "id": 8,
            "public_id": public_id,
            "school_user_id": 10,
            "access_token": "004321",
            "is_active": True,
        },
    )
    monkeypatch.setattr(
        routes.queries,
        "get_external_photo_teacher",
        lambda school_user_id, nip: {
            "id": 21,
            "school_user_id": school_user_id,
            "full_name": "Siti Aminah",
            "nip": nip,
        },
    )
    monkeypatch.setattr(
        routes,
        "render_template",
        lambda template, **context: context["current_step"],
    )
    client = app.test_client()

    initial = client.get("/monev-bos/foto-eksternal/sample")
    assert initial.get_data(as_text=True) == "identity"

    verified = client.post(
        "/monev-bos/foto-eksternal/sample",
        data={
            "action": "verify_identity",
            "teacher_nip": "198705122010012001",
            "access_token": "004321",
        },
    )
    assert verified.status_code == 302
    assert "step=photo" in verified.headers["Location"]

    photo_step = client.get(verified.headers["Location"])
    assert photo_step.get_data(as_text=True) == "photo"


def test_wrong_token_does_not_open_external_photo_step(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(monev_bos_bp)
    monkeypatch.setattr(
        routes.queries,
        "get_external_photo_link",
        lambda public_id: {
            "id": 8,
            "public_id": public_id,
            "school_user_id": 10,
            "access_token": "004321",
            "is_active": True,
        },
    )
    monkeypatch.setattr(
        routes,
        "render_template",
        lambda template, **context: context["current_step"],
    )
    client = app.test_client()

    response = client.post(
        "/monev-bos/foto-eksternal/sample",
        data={
            "action": "verify_identity",
            "teacher_nip": "198705122010012001",
            "access_token": "999999",
        },
    )
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "identity"
    with client.session_transaction() as saved_session:
        assert "external_photo_verified:sample" not in saved_session


def test_unregistered_nip_does_not_open_external_photo_step(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(monev_bos_bp)
    monkeypatch.setattr(
        routes.queries,
        "get_external_photo_link",
        lambda public_id: {
            "id": 8,
            "public_id": public_id,
            "school_user_id": 10,
            "access_token": "004321",
            "is_active": True,
        },
    )
    monkeypatch.setattr(routes.queries, "get_external_photo_teacher", lambda school_user_id, nip: None)
    monkeypatch.setattr(
        routes,
        "render_template",
        lambda template, **context: context["current_step"],
    )
    client = app.test_client()
    response = client.post(
        "/monev-bos/foto-eksternal/sample",
        data={
            "action": "verify_identity",
            "teacher_nip": "198705122010012001",
            "access_token": "004321",
        },
    )
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "identity"
    with client.session_transaction() as saved_session:
        assert "external_photo_verified:sample" not in saved_session


def test_schema_creates_external_links_before_posts_and_includes_identity_columns():
    schema = Path("dashboard/schema.py").read_text(encoding="utf-8")
    statements = schema[schema.index("def ensure_monev_bos_schema") :]
    assert statements.index("_MONEV_BOS_EXTERNAL_PHOTO_LINKS_SQL") < statements.index(
        "_MONEV_BOS_SCHOOL_POSTS_SQL"
    )
    assert "external_photographer_name" in schema
    assert "external_photographer_nip" in schema
    assert "monev_bos_external_photo_teachers" in schema
