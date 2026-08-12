from __future__ import annotations

import os
import sys

import pytest
from flask import Flask


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.monev_bos import routes


@pytest.mark.parametrize("vendor_type", ["vendor", "narsum"])
@pytest.mark.parametrize("status", ["pending", "verified"])
def test_school_can_attach_pending_or_verified_entry_from_any_school(monkeypatch, vendor_type, status):
    monkeypatch.setattr(
        routes.queries,
        "get_vendor_by_id",
        lambda vendor_id: {
            "id": vendor_id,
            "school_id": 99,
            "name": "Toko Maju" if vendor_type == "vendor" else "Budi Narasumber",
            "vendor_type": vendor_type,
            "status": status,
        },
    )

    vendor_id, vendor_name, error = routes._resolve_school_report_vendor("23")

    assert vendor_id == 23
    assert vendor_name
    assert error is None


def test_school_cannot_attach_rejected_entry(monkeypatch):
    monkeypatch.setattr(
        routes.queries,
        "get_vendor_by_id",
        lambda vendor_id: {
            "id": vendor_id,
            "school_id": 99,
            "name": "Entri Tidak Sah",
            "status": "rejected",
        },
    )

    vendor_id, vendor_name, error = routes._resolve_school_report_vendor("23")

    assert vendor_id is None
    assert vendor_name is None
    assert error


@pytest.mark.parametrize("vendor_type", ["vendor", "narsum"])
@pytest.mark.parametrize("vendor_status", ["pending", "rejected", None])
def test_staff_cannot_validate_unverified_vendor(monkeypatch, vendor_type, vendor_status):
    app = Flask(__name__)
    activity = {
        "id": 41,
        "report_id": 7,
        "activity_name": "Belanja kegiatan",
        "vendor_id": 23,
        "vendor_name": "Toko Maju" if vendor_type == "vendor" else "Budi Narasumber",
        "vendor_status": vendor_status,
    }
    update_calls = []
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 5, "role": "staff", "full_name": "Auditor"})
    monkeypatch.setattr(routes.queries, "get_activity_by_id", lambda activity_id: activity)
    monkeypatch.setattr(routes.queries, "update_activity_audit", lambda *args: update_calls.append(args))

    with app.test_request_context(
        "/staff/audit/activity/41",
        method="POST",
        data={"action": "validate", "status": "valid", "report_id": "7"},
        headers={"Accept": "application/json"},
    ):
        response, status_code = routes.staff_audit_activity.__wrapped__(41)

    assert status_code == 400
    assert response.get_json()["success"] is False
    assert update_calls == []


@pytest.mark.parametrize("vendor_type", ["vendor", "narsum"])
def test_staff_can_validate_verified_vendor(monkeypatch, vendor_type):
    app = Flask(__name__)
    activity = {
        "id": 41,
        "report_id": 7,
        "activity_name": "Belanja kegiatan",
        "vendor_id": 23,
        "vendor_name": "Toko Maju" if vendor_type == "vendor" else "Budi Narasumber",
        "vendor_status": "verified",
    }
    update_calls = []
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 5, "role": "staff", "full_name": "Auditor"})
    monkeypatch.setattr(routes.queries, "get_activity_by_id", lambda activity_id: activity)
    monkeypatch.setattr(routes.queries, "update_activity_audit", lambda *args: update_calls.append(args))
    monkeypatch.setattr(routes.queries, "list_checklists", lambda **kwargs: [])
    monkeypatch.setattr(routes.queries, "add_audit_log", lambda *args: None)

    with app.test_request_context(
        "/staff/audit/activity/41",
        method="POST",
        data={"action": "validate", "status": "valid", "report_id": "7"},
        headers={"Accept": "application/json"},
    ):
        response = routes.staff_audit_activity.__wrapped__(41)

    assert response.get_json()["success"] is True
    assert update_calls == [(41, "valid", "")]


def test_activity_without_vendor_does_not_require_vendor_verification():
    assert routes._activity_vendor_is_unverified(
        {"vendor_id": None, "vendor_name": None, "vendor_status": None}
    ) is False


def test_admin_vendor_filters_are_forwarded_to_query(monkeypatch):
    app = Flask(__name__)
    calls = []
    schools = [{"id": 42, "school_name": "SDN Contoh", "npsn": "12345678"}]
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 1, "role": "admin"})
    monkeypatch.setattr(
        routes.queries,
        "list_all_vendors_for_admin",
        lambda *args, **kwargs: calls.append((args, kwargs)) or [],
    )
    monkeypatch.setattr(routes.queries, "list_vendor_schools_for_admin", lambda: schools)
    monkeypatch.setattr(routes.queries, "get_master_banks", lambda: ["Bank DKI"])
    monkeypatch.setattr(routes, "render_template", lambda template, **context: (template, context))

    with app.test_request_context(
        "/monev-bos/admin/vendors?vendor_type=narsum&school_id=42&status=pending&q=pelatih"
    ):
        template, context = routes.admin_vendors.__wrapped__()

    assert template == "monev_bos/admin/admin_vendors.html"
    assert calls == [(('pending',), {
        "search_query": "pelatih",
        "vendor_type_filter": "narsum",
        "school_id_filter": 42,
    })]
    assert context["vendor_type_filter"] == "narsum"
    assert context["school_id_filter"] == 42
    assert context["vendor_schools"] == schools


def test_duplicate_vendor_detection_normalizes_identity_and_phone(monkeypatch):
    target = {
        "id": 1,
        "vendor_type": "vendor",
        "name": "CV. Maju   Bersama",
        "npwp": "01.234.567.8-901.000",
        "phone": "+62 812-3456-7890",
    }
    candidates = [
        target,
        {
            "id": 2,
            "school_id": 42,
            "school_name": "SDN Contoh",
            "vendor_type": "vendor",
            "name": "cv. maju bersama",
            "npwp": "012345678901000",
            "phone": "081234567890",
            "status": "verified",
        },
    ]

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            pass

        def fetchall(self):
            return candidates

    class FakeCursorContext:
        def __enter__(self):
            return FakeCursor()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(routes.queries, "get_cursor", lambda **_kwargs: FakeCursorContext())

    routes.queries.attach_vendor_duplicate_matches([target])

    assert len(target["duplicate_matches"]) == 1
    assert target["duplicate_matches"][0]["duplicate_fields"] == ["Nama vendor", "NPWP", "Kontak"]


def test_duplicate_vendor_requires_exact_confirmation(monkeypatch):
    app = Flask(__name__)
    updates = []
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 5, "role": "staff"})
    monkeypatch.setattr(routes.queries, "find_vendor_duplicate_matches", lambda vendor_id: [{"id": 9}])
    monkeypatch.setattr(routes.queries, "update_vendor_status", lambda *args, **kwargs: updates.append((args, kwargs)))
    monkeypatch.setattr(routes, "flash", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "url_for", lambda *_args, **_kwargs: "/monev-bos/admin/vendors")
    monkeypatch.setattr(routes, "redirect", lambda location: location)

    with app.test_request_context(
        "/monev-bos/admin/vendors?vendor_type=vendor",
        method="POST",
        data={"action": "verify_vendor", "vendor_id": "7", "duplicate_confirmation": "sudah dicek"},
    ):
        response = routes.admin_vendors.__wrapped__()

    assert response == "/monev-bos/admin/vendors"
    assert updates == []


def test_duplicate_vendor_confirmation_is_saved_and_logged(monkeypatch):
    app = Flask(__name__)
    updates = []
    logs = []
    duplicate = {"id": 9, "school_id": 42, "duplicate_fields": ["NPWP", "Kontak"]}
    monkeypatch.setattr(routes, "current_user", lambda: {"id": 5, "role": "staff"})
    monkeypatch.setattr(routes.queries, "find_vendor_duplicate_matches", lambda vendor_id: [duplicate])
    monkeypatch.setattr(
        routes.queries,
        "update_vendor_status",
        lambda *args, **kwargs: updates.append((args, kwargs)) or True,
    )
    monkeypatch.setattr(routes.queries, "get_vendor_by_id", lambda vendor_id: {
        "id": vendor_id,
        "name": "CV Maju",
        "vendor_type": "vendor",
    })
    monkeypatch.setattr(routes, "record_admin_action", lambda **kwargs: logs.append(kwargs))
    monkeypatch.setattr(routes, "flash", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "url_for", lambda *_args, **_kwargs: "/monev-bos/admin/vendors")
    monkeypatch.setattr(routes, "redirect", lambda location: location)

    with app.test_request_context(
        "/monev-bos/admin/vendors?vendor_type=vendor",
        method="POST",
        data={"action": "verify_vendor", "vendor_id": "7", "duplicate_confirmation": "  Vendor   Berbeda  "},
    ):
        response = routes.admin_vendors.__wrapped__()

    assert response == "/monev-bos/admin/vendors"
    assert updates == [((7, "verified", 5), {"verification_notes": "vendor berbeda"})]
    assert logs[0]["action"] == "VERIFY_DUPLICATE_OVERRIDE"
    assert logs[0]["metadata"]["duplicate_matches"][0]["matching_fields"] == ["NPWP", "Kontak"]
