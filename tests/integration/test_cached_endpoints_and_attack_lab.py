"""Integration tests for cached PayPal-style endpoints and adversarial attack lab.

Tests:
1. GET /v1/overview: exactly 3 values, authentication, Cache-Control: no-store.
2. GET /v1/activity: cursor pagination, limit bounds, and item fields.
3. GET /v1/receipts/{id} and GET /v1/receipts/{id}/verify: cryptographic receipts.
4. POST /v1/attack-lab/run: disabled when DEMO_MODE=false; runs 6 canned attacks.
5. Caching: ETag / If-None-Match (304), Vary: Authorization, immutable static assets.
"""

from typing import Any

from fastapi import status
from fastapi.testclient import TestClient

from app.infrastructure.config import settings


def test_overview_three_values_and_caching(
    client: TestClient,
    agent_token: str,
) -> None:
    """GET /v1/overview returns exactly three values and enforces no-store caching."""
    # 1. Unauthenticated request must fail
    unauth = client.get("/v1/overview")
    assert unauth.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. Authenticated request succeeds
    resp = client.get("/v1/overview", headers={"Authorization": f"Bearer {agent_token}"})
    assert resp.status_code == status.HTTP_200_OK

    data: dict[str, Any] = resp.json()
    # Must have exactly 3 values
    assert set(data.keys()) == {
        "remaining_authority",
        "pending_approval_count",
        "last_activity",
    }
    assert isinstance(data["remaining_authority"], int)
    assert isinstance(data["pending_approval_count"], int)
    assert data["last_activity"] is None or isinstance(data["last_activity"], str)

    # Caching assertions
    cache_control = resp.headers.get("cache-control", "")
    assert "no-store" in cache_control
    vary = resp.headers.get("vary", "")
    assert "Authorization" in vary


def test_activity_feed_pagination_and_fields(
    client: TestClient,
    agent_token: str,
) -> None:
    """GET /v1/activity returns paginated activity feed with all required fields."""
    # Make a couple of transactions to ensure ledger events exist
    for i in range(2):
        client.post(
            "/v1/payment-requests",
            json={
                "agent_id": "agent-auto-1",
                "recipient_id": "vendor-paypal-sandbox-1",
                "amount_minor": 1000 + i * 500,
                "currency": "USD",
                "purpose": f"Activity feed seed payment {i}",
                "idempotency_key": f"activity_seed_tx_{i}_{id(client)}",
            },
            headers={"Authorization": f"Bearer {agent_token}"},
        )

    # 1. First page with limit 1
    resp1 = client.get(
        "/v1/activity?limit=1",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp1.status_code == status.HTTP_200_OK
    data1 = resp1.json()
    assert len(data1["items"]) == 1
    assert data1["has_more"] is True
    assert data1["next_cursor"] is not None

    item1 = data1["items"][0]
    required_keys = {
        "receipt_id",
        "decision",
        "amount",
        "payee",
        "reason_code",
        "provider_state",
        "timestamp_utc",
    }
    assert required_keys.issubset(set(item1.keys()))
    assert item1["receipt_id"].startswith("rcpt_")

    # 2. Next page with cursor
    cursor = data1["next_cursor"]
    resp2 = client.get(
        f"/v1/activity?cursor={cursor}&limit=1",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp2.status_code == status.HTTP_200_OK
    data2 = resp2.json()
    assert len(data2["items"]) == 1
    assert data2["items"][0]["receipt_id"] != item1["receipt_id"]


def test_receipts_and_public_verification(
    client: TestClient,
    agent_token: str,
) -> None:
    """GET /v1/receipts/{id} and public GET /v1/receipts/{id}/verify."""
    # 1. Create a payment to generate a receipt
    tx_resp = client.post(
        "/v1/payment-requests",
        json={
            "agent_id": "agent-auto-1",
            "recipient_id": "vendor-paypal-sandbox-1",
            "amount_minor": 2500,
            "currency": "USD",
            "purpose": "Receipt generation transaction",
            "idempotency_key": f"receipt_gen_tx_{id(client)}",
        },
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert tx_resp.status_code == status.HTTP_200_OK
    event_id = tx_resp.json()["event_id"]
    receipt_id = f"rcpt_{event_id}"

    # 2. Retrieve receipt (requires auth)
    unauth_rcpt = client.get(f"/v1/receipts/{receipt_id}")
    assert unauth_rcpt.status_code == status.HTTP_401_UNAUTHORIZED

    rcpt_resp = client.get(
        f"/v1/receipts/{receipt_id}",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert rcpt_resp.status_code == status.HTTP_200_OK
    rcpt_data = rcpt_resp.json()
    assert rcpt_data["receipt_id"] == receipt_id
    assert rcpt_data["intent_digest"] is not None
    assert rcpt_data["mandate_id"] == "mandate_default_sandbox"
    assert rcpt_data["mandate_version"] >= 1
    assert rcpt_data["decision"] == "ALLOW"
    assert any(
        "pre-authorized" in str(r).lower() or "PRE_AUTHORIZED" in str(r)
        for r in rcpt_data["reason_codes"]
    )
    assert rcpt_data["ledger_sequence"] >= 1
    assert rcpt_data["hash_chain_proof"]["is_valid"] is True
    assert rcpt_data["hash_chain_proof"]["event_hash"] is not None

    # 3. Public verification endpoint (no auth required)
    pub_verify = client.get(f"/v1/receipts/{receipt_id}/verify")
    assert pub_verify.status_code == status.HTTP_200_OK
    pub_data = pub_verify.json()
    assert pub_data["status"] == "PASS"
    assert pub_data["is_valid"] is True
    assert pub_data["receipt_id"] == receipt_id
    assert pub_data["broken_block"] is None
    assert "verified" in pub_data["message"].lower()

    # 4. Unknown receipt verification returns 404
    missing_verify = client.get("/v1/receipts/rcpt_nonexistent_9999/verify")
    assert missing_verify.status_code == status.HTTP_404_NOT_FOUND


def test_mandate_etag_and_conditional_caching(
    client: TestClient,
    agent_token: str,
) -> None:
    """GET /v1/mandates/{id} returns ETag and handles If-None-Match with 304."""
    # 1. First fetch returns 200 with ETag
    resp1 = client.get(
        "/v1/mandates/mandate_default_sandbox",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp1.status_code == status.HTTP_200_OK
    etag = resp1.headers.get("etag")
    assert etag is not None
    assert etag.startswith('"') and etag.endswith('"')

    # 2. Subsequent request with matching If-None-Match returns 304 Not Modified
    resp2 = client.get(
        "/v1/mandates/mandate_default_sandbox",
        headers={
            "Authorization": f"Bearer {agent_token}",
            "If-None-Match": etag,
        },
    )
    assert resp2.status_code == status.HTTP_304_NOT_MODIFIED
    assert resp2.headers.get("etag") == etag

    # 3. Request with mismatched If-None-Match returns full 200 OK
    resp3 = client.get(
        "/v1/mandates/mandate_default_sandbox",
        headers={
            "Authorization": f"Bearer {agent_token}",
            "If-None-Match": '"mismatched_etag_value"',
        },
    )
    assert resp3.status_code == status.HTTP_200_OK


def test_attack_lab_disabled_by_default(
    client: TestClient,
    agent_token: str,
) -> None:
    """POST /v1/attack-lab/run returns 404 when DEMO_MODE is false."""
    original_demo = settings.demo_mode
    try:
        settings.demo_mode = False
        resp = client.post(
            "/v1/attack-lab/run",
            headers={"Authorization": f"Bearer {agent_token}"},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
    finally:
        settings.demo_mode = original_demo


def test_attack_lab_execution_when_demo_mode_active(
    client: TestClient,
    agent_token: str,
) -> None:
    """POST /v1/attack-lab/run executes 6 canned attacks safely without contacting PayPal."""
    original_demo = settings.demo_mode
    try:
        settings.demo_mode = True
        resp = client.post(
            "/v1/attack-lab/run",
            headers={"Authorization": f"Bearer {agent_token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["attacks_run"] == 6
        assert data["all_defended"] is True

        attack_names = [r["attack_name"] for r in data["results"]]
        assert "prompt_injection" in attack_names
        assert "payee_swap" in attack_names
        assert "amount_tamper_after_approval" in attack_names
        assert "replay" in attack_names
        assert "forged_webhook" in attack_names
        assert "agent_self_approval" in attack_names

        for r in data["results"]:
            assert r["blocked"] is True
            assert r["reached_paypal"] is False
            assert r["reason_code"] is not None
            assert len(r["reason_code"]) > 0
    finally:
        settings.demo_mode = original_demo


def test_static_asset_caching_headers(
    client: TestClient,
) -> None:
    """Static assets under /assets/* are immutable; index.html and / are no-cache."""
    # Test index / root route
    root_resp = client.get("/")
    assert "no-cache" in root_resp.headers.get("cache-control", "")

    # Test asset route
    asset_resp = client.get("/assets/vendor.a1b2c3d4.js")
    # Even if 404 because file not on disk during test, middleware applies headers
    cc = asset_resp.headers.get("cache-control", "")
    assert "immutable" in cc
    assert "max-age=31536000" in cc
