"""API integration tests."""

from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient

from app.infrastructure.tokens import Role, create_role_token


def test_api_healthz_endpoint(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


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
        principal_id="principal_astra_treasury",
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


def test_api_rejects_extra_fields_strictly(client: TestClient) -> None:
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
        headers={"Authorization": "Bearer demo-agent"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.headers["content-type"] == "application/problem+json"


def test_admin_reset_with_admin_token(client: TestClient) -> None:
    """Verify admin reset succeeds with X-Admin-Token header."""
    resp = client.post(
        "/v1/admin/reset",
        headers={"X-Admin-Token": "phalanx-admin-demo-key"},
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


def test_admin_reset_with_principal_role(client: TestClient) -> None:
    """Verify admin reset succeeds with principal role token."""
    resp = client.post(
        "/v1/admin/reset",
        headers={"Authorization": "Bearer demo-principal"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == "reset_completed"


def test_request_id_header_propagated(client: TestClient) -> None:
    """Verify X-Request-ID header is generated or preserved on responses."""
    resp = client.get("/healthz", headers={"X-Request-ID": "custom-req-id-12345"})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.headers.get("X-Request-ID") == "custom-req-id-12345"
