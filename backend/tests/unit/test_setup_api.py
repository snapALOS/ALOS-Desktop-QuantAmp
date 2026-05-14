import sqlite3

from fastapi.testclient import TestClient

from src.auth import api_key_manager
from src.api import server


def test_setup_status_is_public(monkeypatch):
    """The UI reads setup status before it knows whether to show login."""
    monkeypatch.setattr(
        server,
        "setup_status",
        lambda: {
            "ready": True,
            "state": "ready",
            "checks": [],
            "next_action": "ALOS is ready.",
        },
    )

    route = next(
        route
        for route in server.app.routes
        if getattr(route, "path", None) == "/api/setup/status"
    )
    assert route.dependant.dependencies == []

    response = TestClient(server.app).get("/api/setup/status")

    assert response.status_code == 200
    assert response.json()["state"] == "ready"


def test_original_admin_bootstrap_status_is_public(monkeypatch):
    class FakeManager:
        def original_admin_bootstrap_status(self):
            return {
                "users_exist": False,
                "active_admins": 0,
                "can_bootstrap": True,
            }

    monkeypatch.setattr(server, "get_api_key_manager", lambda: FakeManager())

    route = next(
        route
        for route in server.app.routes
        if getattr(route, "path", None) == "/auth/bootstrap/status"
    )
    assert route.dependant.dependencies == []

    response = TestClient(server.app).get("/auth/bootstrap/status")

    assert response.status_code == 200
    assert response.json()["can_bootstrap"] is True
    assert "data_dir" in response.json()


def test_original_admin_bootstrap_creates_first_admin(monkeypatch):
    class FakeManager:
        def create_original_admin(self, username: str = "admin", key_name=None):
            return {
                "api_key_id": "key_1",
                "api_key": "alos_test_key",
                "user": {
                    "user_id": "root_admin",
                    "username": username,
                    "role": "admin",
                },
            }

    monkeypatch.setattr(server, "get_api_key_manager", lambda: FakeManager())

    route = next(
        route
        for route in server.app.routes
        if getattr(route, "path", None) == "/auth/bootstrap/original-admin"
    )
    assert route.dependant.dependencies == []

    response = TestClient(server.app).post(
        "/auth/bootstrap/original-admin",
        json={"username": "shawn"},
    )

    assert response.status_code == 200
    assert response.json()["api_key"] == "alos_test_key"
    assert response.json()["user"]["username"] == "shawn"


def test_original_admin_bootstrap_rejects_existing_install(monkeypatch):
    class FakeManager:
        def create_original_admin(self, username: str = "admin", key_name=None):
            raise ValueError("Original admin has already been configured")

    monkeypatch.setattr(server, "get_api_key_manager", lambda: FakeManager())

    response = TestClient(server.app).post(
        "/auth/bootstrap/original-admin",
        json={"username": "admin"},
    )

    assert response.status_code == 409


def test_provider_validation_is_public_during_setup_recovery(monkeypatch):
    """A configured-but-not-ready provider must not deadlock setup recovery."""
    class FakeConfig:
        def is_configured(self):
            return True

    monkeypatch.setattr(server, "alos_config", FakeConfig())
    monkeypatch.setattr(
        server,
        "setup_status",
        lambda: {
            "ready": False,
            "state": "provider_invalid",
            "checks": [],
            "next_action": "Validate provider settings before running ALOS.",
        },
    )
    monkeypatch.setattr(
        server,
        "validate_provider_connection",
        lambda payload: {
            "ok": True,
            "provider": payload["llm_provider"],
            "model": payload["model_name"],
            "base_url": payload.get("base_url"),
            "api_key_set": True,
            "message": "Provider connection validated.",
        },
    )

    response = TestClient(server.app).post(
        "/api/setup/validate",
        json={
            "llm_provider": "nvidia",
            "api_key": "nvapi-valid-token",
            "model_name": "Moonshotai/kimi-k2-instruct",
            "base_url": "https://integrate.api.nvidia.com/v1",
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_auth_me_returns_full_user_from_api_key(monkeypatch):
    class FakeManager:
        def validate_api_key(self, api_key: str):
            assert api_key == "alos_test_key"
            return {
                "user_id": "root_admin",
                "username": "admin",
                "role": "admin",
            }

    monkeypatch.setattr(server, "get_api_key_manager", lambda: FakeManager())

    response = TestClient(server.app).get(
        "/auth/me",
        headers={"Authorization": "Bearer alos_test_key"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "root_admin",
        "username": "admin",
        "role": "admin",
    }


def test_original_admin_manager_creates_user_and_key_atomically(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"

    def connect():
        return sqlite3.connect(db_path)

    monkeypatch.setattr(api_key_manager, "get_db_connection", connect)

    manager = api_key_manager.APIKeyManager()
    result = manager.create_original_admin(username="review_admin")

    assert result["user"] == {
        "user_id": "root_admin",
        "username": "review_admin",
        "role": "admin",
    }
    assert result["api_key"].startswith("alos_")

    user_info = manager.validate_api_key(result["api_key"])

    assert user_info is not None
    assert user_info["user_id"] == "root_admin"
    assert user_info["username"] == "review_admin"
    assert user_info["role"] == "admin"

    with sqlite3.connect(db_path) as conn:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        key_count = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        audit_count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    assert user_count == 1
    assert key_count == 1
    assert audit_count >= 2

    try:
        manager.create_original_admin(username="second_admin")
    except ValueError as exc:
        assert "already been configured" in str(exc)
    else:
        raise AssertionError("second original-admin bootstrap should fail")
