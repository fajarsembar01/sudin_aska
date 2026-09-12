from types import SimpleNamespace

import pytest

from dashboard.call_center import routes


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    account = {"bridge_key": "main", "http_port": 3100, "client_id": "cc-main"}
    monkeypatch.setattr(routes, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(routes, "_cc_systemd_service", lambda: "aska-wa-cc")
    monkeypatch.setattr(routes, "_systemd_service_active", lambda service: False)
    monkeypatch.setattr(routes, "_wait_cc_port_free", lambda account: None)
    return account


def test_instance_service_preferred_and_legacy_only_for_main(monkeypatch):
    monkeypatch.setattr(routes, "_cc_systemd_service", lambda: "aska-wa-cc")
    monkeypatch.setattr(routes, "_systemd_service_exists", lambda service: True)
    assert routes._cc_account_service({"bridge_key": "main"}) == "aska-wa-cc@main.service"
    assert routes._cc_account_service({"bridge_key": "aska"}) == "aska-wa-cc@aska.service"
    monkeypatch.setattr(routes, "_systemd_service_exists", lambda service: service == "aska-wa-cc.service")
    assert routes._cc_account_service({"bridge_key": "main"}) == "aska-wa-cc.service"
    assert routes._cc_account_service({"bridge_key": "aska"}) is None


def test_generate_qr_stops_main_before_reset_without_spawning(monkeypatch, bridge):
    monkeypatch.setattr(routes, "_systemd_service_exists", lambda service: True)
    paths = routes._cc_runtime_paths(bridge)
    paths["session"].mkdir()
    (paths["session"] / "auth").write_text("session")
    aska_session = paths["root"] / ".wa_cc_session_aska"
    aska_session.mkdir()
    (aska_session / "auth").write_text("keep")
    actions = []

    def control(action, service):
        assert service == "aska-wa-cc@main.service"
        assert paths["session"].exists() == (action == "stop")
        actions.append(action)

    monkeypatch.setattr(routes, "_control_cc_service", control)
    monkeypatch.setattr(routes.subprocess, "Popen", lambda *a, **kw: pytest.fail("Duplicate npm process"))
    result = routes._restart_cc_bridge(bridge, reset_session=True)
    assert actions == ["stop", "start"]
    assert result["managed_by"] == "systemd"
    assert (aska_session / "auth").read_text() == "keep"


def test_stop_failure_preserves_session_and_does_not_spawn(monkeypatch, bridge):
    monkeypatch.setattr(routes, "_systemd_service_exists", lambda service: True)
    paths = routes._cc_runtime_paths(bridge)
    paths["session"].mkdir()
    auth = paths["session"] / "auth"
    auth.write_text("keep")

    def denied(*args):
        raise RuntimeError("permission denied")

    monkeypatch.setattr(routes, "_control_cc_service", denied)
    monkeypatch.setattr(routes.subprocess, "Popen", lambda *a, **kw: pytest.fail("Unsafe fallback"))
    with pytest.raises(RuntimeError, match="permission denied"):
        routes._restart_cc_bridge(bridge)
    assert auth.read_text() == "keep"


def test_busy_port_preserves_session(monkeypatch, bridge):
    monkeypatch.setattr(routes, "_systemd_service_exists", lambda service: False)
    paths = routes._cc_runtime_paths(bridge)
    paths["session"].mkdir()

    def occupied(account):
        raise RuntimeError("Port 3100 masih dipakai")

    monkeypatch.setattr(routes, "_wait_cc_port_free", occupied)
    with pytest.raises(RuntimeError, match="3100"):
        routes._restart_cc_bridge(bridge)
    assert paths["session"].exists()


def test_concurrent_control_rejected_per_account(bridge):
    with routes._cc_bridge_control_lock(bridge):
        with pytest.raises(RuntimeError, match="sedang diproses"):
            with routes._cc_bridge_control_lock(bridge):
                pytest.fail("Concurrent reset allowed")
        with routes._cc_bridge_control_lock({"bridge_key": "aska"}):
            pass


def test_systemd_template_instance_detected_by_load_state(monkeypatch):
    def run(command, **kwargs):
        assert command == ["systemctl", "show", "--property=LoadState", "--value", "aska-wa-cc@main.service"]
        return SimpleNamespace(returncode=0, stdout="loaded\n")

    monkeypatch.setattr(routes.subprocess, "run", run)
    assert routes._systemd_service_exists("aska-wa-cc@main.service")


def test_main_control_also_stops_active_legacy_service(monkeypatch, bridge):
    monkeypatch.setattr(routes, "_systemd_service_exists", lambda service: True)
    monkeypatch.setattr(routes, "_systemd_service_active", lambda service: service == "aska-wa-cc.service")
    actions = []
    monkeypatch.setattr(routes, "_control_cc_service", lambda *args: actions.append(args))
    routes._stop_existing_bridge(bridge)
    assert actions == [("stop", "aska-wa-cc@main.service"), ("stop", "aska-wa-cc.service")]


def test_nonroot_service_control_fails_without_subprocess_fallback(monkeypatch):
    monkeypatch.setattr(routes.os, "geteuid", lambda: 1000)

    def run(command, **kwargs):
        assert command == ["sudo", "-n", "systemctl", "stop", "aska-wa-cc@main.service"]
        return SimpleNamespace(returncode=1, stderr="permission denied", stdout="")

    monkeypatch.setattr(routes.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="permission denied"):
        routes._control_cc_service("stop", "aska-wa-cc@main.service")
