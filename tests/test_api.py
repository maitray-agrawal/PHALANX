"""API integration tests."""

from fastapi import status
from fastapi.testclient import TestClient


def test_api_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "timestamp_utc" in data


def test_api_authorize_endpoint(client: TestClient) -> None:
    payload = {
        "agent_id": "finance-bot-42",
        "recipient_id": "vendor-99",
        "amount_minor": 1500,
        "currency": "USD",
        "purpose": "Server hosting fees",
        "idempotency_key": "tx-key-42",
    }
    response = client.post("/api/v1/authorize", json=payload)
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
    response = client.post("/api/v1/authorize", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
