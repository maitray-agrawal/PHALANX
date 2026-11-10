"""API integration tests."""

from typing import Any
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.infrastructure.config import settings
from app.infrastructure.tokens import Role, create_role_token


def test_api_healthz_endpoint(client: TestClient) -> None:
    """Liveness probe (/healthz) must return 200 OK without accessing the database."""
    with patch("app.api.routes.check_database_readiness") as mock_db:
        response = client.get("/healthz")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}
        mock_db.assert_not_called()


def test_api_readyz_endpoint_success(client: TestClient) -> None:
    with patch("app.api.routes.check_database_readiness", return_value=(True, "connected")):
        response = client.get("/readyz")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"


def test_api_readyz_endpoint_failure(client: TestClient) -> None:
    with patch(
        "app.api.routes.check_database_readiness",
        return_value=(False, "database unreachable: ConnectionRefusedError"),
    ):
        response = client.get("/readyz")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "not_ready"
        assert "unreachable" in data["database"]


def test_api_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "timestamp_utc" in data


def test_api_unauthenticated_call_returns_401(client: TestClient) -> None:
    """Security rule: Unauthenticated calls return 401 Unauthorized."""
    payload = {
        "agent_id": "finance-bot-42",
        "recipient_id": "vendor-99",
        "amount_minor": 1500,
        "currency": "USD",
        "purpose": "Server hosting fees",
        "idempotency_key": "tx-key-unauth",
    }
    response = client.post("/api/v1/authorize", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers["content-type"] == "application/problem+json"
    data = response.json()
    assert data["status"] == 401
    assert "Unauthorized" in data["title"]


def test_api_authorize_endpoint(client: TestClient) -> None:
    token = create_role_token(
        role=Role.AGENT,
        principal_id="principal_treasury",
        agent_id="agent-auto-1",
    )
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "vendor-99",
        "amount_minor": 1500,
        "currency": "USD",
        "purpose": "Server hosting fees",
        "idempotency_key": "tx-key-42",
    }
    response = client.post(
        "/api/v1/authorize",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision"] == "ALLOW"
    assert data["escalated"] is False
    assert data["event_id"].startswith("evt_")


def test_api_rejects_extra_fields_strictly(client: TestClient, agent_token: str) -> None:
    """Security rule: Strict Pydantic models with extra='forbid'."""
    payload = {
        "agent_id": "finance-bot-42",
        "recipient_id": "vendor-99",
        "amount_minor": 1500,
        "currency": "USD",
        "purpose": "Server hosting fees",
        "idempotency_key": "tx-key-42",
        "extra_unexpected_field": "exploit_attempt",
    }
    response = client.post(
        "/api/v1/authorize",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.headers["content-type"] == "application/problem+json"


def test_admin_reset_with_admin_token(client: TestClient) -> None:
    """Verify admin reset succeeds with X-Admin-Token header."""
    resp = client.post(
        "/v1/admin/reset",
        headers={"X-Admin-Token": settings.admin_token},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == "reset_completed"


def test_admin_reset_with_invalid_token_fails(client: TestClient) -> None:
    """Verify admin reset fails with invalid X-Admin-Token."""
    resp = client.post(
        "/v1/admin/reset",
        headers={"X-Admin-Token": "wrong-secret-token"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_admin_reset_with_principal_role(client: TestClient, principal_token: str) -> None:
    """Verify admin reset succeeds with principal role token."""
    resp = client.post(
        "/v1/admin/reset",
        headers={"Authorization": f"Bearer {principal_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == "reset_completed"


def test_admin_reset_requires_auth(client: TestClient) -> None:
    """Verify /v1/admin/reset requires authentication (returns 401 without credentials)."""
    resp = client.post("/v1/admin/reset")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authentication required" in resp.json().get("detail", "")


def test_admin_reset_disabled_in_production(
    client: TestClient, principal_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify /v1/admin/reset is strictly disabled when ENVIRONMENT=production."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    from app.infrastructure.config import settings

    monkeypatch.setattr(settings, "environment", "production")

    # Rejected even with valid admin token
    resp_token = client.post(
        "/v1/admin/reset",
        headers={"X-Admin-Token": settings.admin_token},
    )
    assert resp_token.status_code == status.HTTP_403_FORBIDDEN
    assert "disabled in production" in resp_token.json().get("detail", "").lower()

    # Rejected even with valid principal role Bearer token
    resp_bearer = client.post(
        "/v1/admin/reset",
        headers={"Authorization": f"Bearer {principal_token}"},
    )
    assert resp_bearer.status_code == status.HTTP_403_FORBIDDEN
    assert "disabled in production" in resp_bearer.json().get("detail", "").lower()


def test_request_id_header_propagated(client: TestClient) -> None:
    """Verify X-Request-ID header is generated or preserved on responses."""
    resp = client.get("/healthz", headers={"X-Request-ID": "custom-req-id-12345"})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.headers.get("X-Request-ID") == "custom-req-id-12345"


def test_reconcile_auditor_gets_403(client: TestClient, auditor_token: str) -> None:
    """Mutating endpoint /v1/reconcile/{id} strictly rejects Role.AUDITOR with 403."""
    resp = client.post(
        "/v1/reconcile/req_audit_test",
        json={"status": "COMPLETED"},
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_tamper_and_restore_auditor_gets_403(
    client: TestClient, auditor_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutating ledger endpoints strictly reject Role.AUDITOR with 403."""
    from app.infrastructure.config import settings

    monkeypatch.setattr(settings, "demo_mode", True)
    resp1 = client.post(
        "/v1/ledger/tamper",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert resp1.status_code == status.HTTP_403_FORBIDDEN

    resp2 = client.post(
        "/v1/ledger/restore",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert resp2.status_code == status.HTTP_403_FORBIDDEN


def test_reconcile_forged_completed_and_failed_bodies_change_nothing(
    client: TestClient,
    approver_token: str,
    test_authorization_service: Any,
    test_payment_rail: Any,
) -> None:
    """POST /v1/reconcile/{id} removes caller-supplied status entirely.
    Forged COMPLETED and FAILED bodies change nothing; real provider lookup dictates outcome.
    """
    from app.domain.state_machine import RequestState

    req_id = "req_forged_status_test"
    test_authorization_service._request_states[req_id] = RequestState.RECONCILE
    test_authorization_service._held_reservations[req_id] = {
        "state": RequestState.RECONCILE.value,
        "payout_id": "tx_lookup_test_404",
        "agent_id": "agent-auto-1",
    }
    # Payment rail lookup returns LOOKUP_FAILED (not completed)
    test_payment_rail.should_succeed = False
    test_payment_rail.status = "LOOKUP_FAILED"

    # Forged COMPLETED body must NOT settle the transaction
    resp_comp = client.post(
        f"/v1/reconcile/{req_id}",
        json={"status": "COMPLETED"},
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert resp_comp.status_code == status.HTTP_200_OK
    assert resp_comp.json()["state"] != "SETTLED"
    assert test_authorization_service.get_request_state(req_id) != RequestState.SETTLED

    # Forged FAILED body when rail is actually COMPLETED must NOT fail or release
    test_payment_rail.should_succeed = True
    test_payment_rail.status = "COMPLETED"
    resp_fail = client.post(
        f"/v1/reconcile/{req_id}",
        json={"status": "FAILED"},
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert resp_fail.status_code == status.HTTP_200_OK
    assert resp_fail.json()["state"] == "SETTLED"
    assert test_authorization_service.get_request_state(req_id) == RequestState.SETTLED


def test_reconcile_scheduled_endpoint_auth_and_rate_limits(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /v1/admin/reconcile-scheduled tests:
    - Missing or wrong secret -> 401 Unauthorized
    - Unconfigured secret -> 503 Service Unavailable
    - Valid secret -> 200 OK
    - Rate limit exceeded -> 429 Too Many Requests
    """
    from app.api.routes import _reconcile_scheduled_rate_limits
    from app.infrastructure.config import settings

    _reconcile_scheduled_rate_limits.clear()
    valid_secret = "scheduled-reconcile-super-secret-key-24chars"
    monkeypatch.setattr(settings, "reconcile_secret", valid_secret)

    # 1. Missing secret header -> 401
    resp_no_secret = client.post("/v1/admin/reconcile-scheduled")
    assert resp_no_secret.status_code == status.HTTP_401_UNAUTHORIZED
    assert "missing or invalid" in resp_no_secret.json()["detail"].lower()

    # 2. Wrong secret header -> 401
    resp_wrong = client.post(
        "/v1/admin/reconcile-scheduled",
        headers={"X-Reconcile-Secret": "wrong-secret-value-1234567890"},
    )
    assert resp_wrong.status_code == status.HTTP_401_UNAUTHORIZED

    # 3. Unconfigured / short secret -> 503
    monkeypatch.setattr(settings, "reconcile_secret", "short")
    resp_unconfigured = client.post(
        "/v1/admin/reconcile-scheduled",
        headers={"X-Reconcile-Secret": "short"},
    )
    assert resp_unconfigured.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    monkeypatch.setattr(settings, "reconcile_secret", valid_secret)

    # Clear rate limit counter before testing the rate limit progression
    _reconcile_scheduled_rate_limits.clear()

    # 4. Valid secret -> 5 allowed calls per minute
    for _ in range(5):
        resp_call = client.post(
            "/v1/admin/reconcile-scheduled",
            headers={"X-Reconcile-Secret": valid_secret},
        )
        assert resp_call.status_code == status.HTTP_200_OK
        assert resp_call.json()["status"] == "reconciliation_completed"

    # 5. 6th call exceeds the 5-per-minute cap -> 429 Too Many Requests
    resp_limited = client.post(
        "/v1/admin/reconcile-scheduled",
        headers={"X-Reconcile-Secret": valid_secret},
    )
    assert resp_limited.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "rate limit exceeded" in resp_limited.json()["detail"].lower()


def test_admin_reset_allowed_in_demo_environment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify /v1/admin/reset is permitted in demo environment with valid admin token."""
    from app.infrastructure.config import settings

    monkeypatch.setenv("ENVIRONMENT", "demo")
    monkeypatch.setattr(settings, "environment", "demo")

    resp = client.post(
        "/v1/admin/reset",
        headers={"X-Admin-Token": settings.admin_token},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == "reset_completed"
