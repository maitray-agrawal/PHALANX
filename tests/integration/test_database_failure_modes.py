"""Integration tests verifying database failure modes, readiness rejection, and boot safety."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_authorization_service, get_ledger
from app.infrastructure.config import settings
from app.infrastructure.database import reset_database
from app.main import create_app
from scripts.boot import run_boot


def test_boot_fails_when_database_down_at_startup(monkeypatch) -> None:
    """Boot sequence must fail and exit non-zero when database is unreachable at startup."""
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+psycopg://phalanx_app:invalid@127.0.0.1:54399/unreachable_db",
    )
    monkeypatch.setattr(
        settings,
        "secret_key",
        "test-secret-key-at-least-32-bytes-long-for-boot-failure-testing",
    )
    reset_database()
    try:
        success = run_boot()
        assert success is False, "Boot must fail (exit non-zero) when database is unreachable"
    finally:
        reset_database()


def test_readiness_fails_when_database_down_after_startup(monkeypatch) -> None:
    """Readiness probe (/readyz) must return 503 when database connection fails after startup."""
    monkeypatch.setattr(
        settings,
        "secret_key",
        "test-secret-key-at-least-32-bytes-long-for-readiness-testing",
    )
    app = create_app()
    client = TestClient(app)

    # Simulate database going down after boot
    with patch(
        "app.api.routes.check_database_readiness",
        return_value=(False, "database unreachable: ConnectionRefusedError"),
    ):
        resp = client.get("/readyz")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert "ConnectionRefusedError" in data["database"]


def test_dependencies_fail_when_database_unreachable_outside_test_mode(monkeypatch) -> None:
    """Outside test/fake mode, PostgreSQL is mandatory and dependencies fail."""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "payment_rail", "paypal")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PAYMENT_RAIL", "paypal")

    # Clear lru caches
    get_authorization_service.cache_clear()
    get_ledger.cache_clear()

    with (
        patch(
            "app.infrastructure.database.check_database_readiness",
            return_value=(False, "database unreachable: ConnectionRefusedError"),
        ),
        pytest.raises(RuntimeError, match="PostgreSQL database is mandatory"),
    ):
        get_authorization_service()

    # Reset cache
    get_authorization_service.cache_clear()
    get_ledger.cache_clear()
