"""Integration tests for the step-up human approval flow."""

from fastapi import status
from fastapi.testclient import TestClient


def test_full_step_up_and_approval_flow(client: TestClient) -> None:
    # 1. Submit an intent exceeding the $500 instant threshold ($1,000)
    req_payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "vendor-paypal-sandbox-1",
        "amount_minor": 100_000,  # $1,000.00
        "currency": "USD",
        "purpose": "Monthly subscription renewal",
        "idempotency_key": "stepup-tx-001",
    }
    resp = client.post("/v1/payment-requests", json=req_payload)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["decision"] == "STEP_UP"
    assert data["payout_id"] is None
    request_id = data["request_id"]
    intent_digest = data["intent_digest"]

    # 2. Agent tries to approve its own transaction -> Must be rejected with 403 Forbidden!
    agent_approve = client.post(
        f"/v1/approvals/{request_id}",
        json={
            "expected_digest": intent_digest,
            "decision": "ALLOW",
            "reason": "Agent approving itself",
        },
        headers={"X-Phalanx-Role": "agent"},
    )
    assert agent_approve.status_code == status.HTTP_403_FORBIDDEN

    # 3. Approver approves with mutated digest -> Must be rejected (Tamper detected)
    tampered_approve = client.post(
        f"/v1/approvals/{request_id}",
        json={
            "expected_digest": "0" * 64,  # Fake digest
            "decision": "ALLOW",
            "reason": "Approving with mismatched digest",
        },
        headers={"X-Phalanx-Role": "approver"},
    )
    assert tampered_approve.status_code == status.HTTP_400_BAD_REQUEST
    assert "digest mismatch" in tampered_approve.json()["detail"].lower()

    # 4. Valid human supervisor approval with matching digest -> ALLOW and dispatched!
    valid_approve = client.post(
        f"/v1/approvals/{request_id}",
        json={
            "expected_digest": intent_digest,
            "decision": "ALLOW",
            "reason": "Approved by CFO after invoice review",
        },
        headers={"X-Phalanx-Role": "approver"},
    )
    assert valid_approve.status_code == status.HTTP_200_OK
    approved_data = valid_approve.json()
    assert approved_data["decision"] == "ALLOW"
    assert approved_data["payout_id"] is not None

    # 5. Verify the ledger chain contains both events and is cryptographically intact
    verify_resp = client.get("/v1/ledger/verify")
    assert verify_resp.status_code == status.HTTP_200_OK
    verify_data = verify_resp.json()
    assert verify_data["is_valid"] is True
    assert verify_data["total_events"] >= 2
