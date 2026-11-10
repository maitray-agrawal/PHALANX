"""Integration tests for Invoice Agent API endpoints."""

from starlette.testclient import TestClient

from app.application.invoice_agent import (
    SAMPLE_INVOICE_A,
    SAMPLE_INVOICE_B,
    SAMPLE_INVOICE_C,
)


def test_get_invoice_samples(client: TestClient) -> None:
    """Verify built-in sample invoices endpoint returns all 3 samples."""
    resp = client.get("/v1/invoice-agent/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    sample_ids = [s["id"] for s in data]
    assert "sample_a" in sample_ids
    assert "sample_b" in sample_ids
    assert "sample_c" in sample_ids


def test_process_invoice_sample_a_allow(client: TestClient, agent_token: str) -> None:
    """Verify processing Sample A results in ALLOW and returns complete lifecycle payload."""
    resp = client.post(
        "/v1/invoice-agent/process",
        json={"invoice_text": SAMPLE_INVOICE_A["text"], "force_fallback": True},
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "ALLOW"
    assert data["extraction"]["amount_minor"] == 2500
    assert data["extraction"]["account"] == "vendor-paypal-sandbox-1"
    assert "authorization_request" in data
    assert "ledger_event" in data
    assert data["is_live"] is False
    assert "RECORDED" in data["status_label"]


def test_process_invoice_sample_b_step_up(client: TestClient, agent_token: str) -> None:
    """Verify processing Sample B results in STEP_UP and request_state PENDING_APPROVAL."""
    resp = client.post(
        "/v1/invoice-agent/process",
        json={"invoice_text": SAMPLE_INVOICE_B["text"], "force_fallback": True},
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "STEP_UP"
    assert data["request_state"] == "PENDING_APPROVAL"
    assert data["extraction"]["amount_minor"] == 75000


def test_process_invoice_sample_c_injection_blocked(client: TestClient, agent_token: str) -> None:
    """Verify processing Sample C (prompt injection) results in DENY and funds blocked."""
    resp = client.post(
        "/v1/invoice-agent/process",
        json={"invoice_text": SAMPLE_INVOICE_C["text"], "force_fallback": True},
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "DENY"
    assert data["request_state"] == "DENIED"
    assert "attacker-fraud-99@shadybank.com" in data["extraction"]["account"]
