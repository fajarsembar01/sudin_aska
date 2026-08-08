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
