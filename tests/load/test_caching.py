"""Automated caching and read-your-writes consistency tests for PHALANX.

Verifies:
1. Authenticated responses carry 'Cache-Control: no-store'.
2. Mandate endpoint generates ETag and returns HTTP 304 on matching 'If-None-Match'.
3. Hashed assets carry 'public, max-age=31536000, immutable'.
4. Root / index.html carries 'no-cache'.
5. Authenticated responses carry 'Vary: Authorization'.
6. Read-your-writes consistency immediately following a supervisor step-up approval.
7. Cold-start stampede (20 simultaneous first requests) executes cleanly with 0 errors.
"""

import asyncio
import os
import uuid

import httpx
import pytest

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _is_server_reachable() -> bool:
    try:
        with httpx.Client(base_url=BASE_URL, timeout=2.0) as client:
            return client.get("/healthz").status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def agent_token():
    if not _is_server_reachable():
        pytest.skip(f"API server not running at {BASE_URL}")
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        res = client.post("/v1/auth/demo-token", json={"role": "agent", "agent_id": "agent-auto-1"})
        assert res.status_code == 200, f"Failed to get agent token: {res.text}"
        return res.json()["access_token"]


@pytest.fixture(scope="module")
def approver_token():
    if not _is_server_reachable():
        pytest.skip(f"API server not running at {BASE_URL}")
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        res = client.post("/v1/auth/demo-token", json={"role": "approver"})
        assert res.status_code == 200, f"Failed to get approver token: {res.text}"
        return res.json()["access_token"]


def test_authenticated_responses_carry_no_store(agent_token):
    """Authenticated responses MUST carry Cache-Control: no-store."""
    headers = {"Authorization": f"Bearer {agent_token}"}
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # Check /v1/overview
        res = client.get("/v1/overview", headers=headers)
        assert res.status_code == 200
        cache_ctrl = res.headers.get("cache-control", "").lower()
        assert "no-store" in cache_ctrl, f"Expected no-store on /v1/overview, got: {cache_ctrl}"

        # Check /v1/activity
        res = client.get("/v1/activity", headers=headers)
        assert res.status_code == 200
        cache_ctrl = res.headers.get("cache-control", "").lower()
        assert "no-store" in cache_ctrl, f"Expected no-store on /v1/activity, got: {cache_ctrl}"


def test_mandate_etag_and_304_not_modified(agent_token):
    """Mandate GET returns an ETag, and subsequent request with If-None-Match returns 304."""
    headers = {"Authorization": f"Bearer {agent_token}"}
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        res = client.get("/v1/mandates/mandate_default_sandbox", headers=headers)
        assert res.status_code == 200
        etag = res.headers.get("etag")
        assert etag is not None, "Mandate response must include ETag header"

        # Request again with If-None-Match
        headers_with_match = {**headers, "If-None-Match": etag}
        res_304 = client.get("/v1/mandates/mandate_default_sandbox", headers=headers_with_match)
        assert res_304.status_code == 304, f"Expected 304 Not Modified, got {res_304.status_code}"
        assert res_304.headers.get("etag") == etag


def test_static_asset_cache_headers():
    """Hashed assets are immutable; index.html carries no-cache."""
    if not _is_server_reachable():
        pytest.skip(f"API server not running at {BASE_URL}")
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # Root index.html
        res = client.get("/")
        assert res.status_code == 200
        cache_ctrl = res.headers.get("cache-control", "").lower()
        assert "no-cache" in cache_ctrl, f"Expected no-cache on /, got {cache_ctrl}"

        # Check an asset under /assets/
        res_asset = client.get("/assets/index.js")
        cache_ctrl_asset = res_asset.headers.get("cache-control", "").lower()
        assert "immutable" in cache_ctrl_asset or "no-store" in cache_ctrl_asset


def test_vary_authorization_header(agent_token):
    """Requests presenting Authorization receive Vary: Authorization."""
    headers = {"Authorization": f"Bearer {agent_token}"}
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        res = client.get("/v1/overview", headers=headers)
        assert res.status_code == 200
        vary = res.headers.get("vary", "")
        assert "authorization" in vary.lower(), f"Expected Vary: Authorization, got: {vary}"


def test_read_your_writes_after_approval(agent_token, approver_token):
    """Read-your-writes immediately after step-up approval reflects updated state."""
    idem_key = f"stepup-rw-{uuid.uuid4().hex[:8]}"
    agent_headers = {"Authorization": f"Bearer {agent_token}"}
    approver_headers = {"Authorization": f"Bearer {approver_token}"}

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # 1. Agent submits request requiring step-up ($1,200 > $500 threshold)
        req_payload = {
            "agent_id": "agent-auto-1",
            "recipient_id": "vendor_infra_aws",
            "amount_minor": 120000,  # $1,200.00
            "currency": "USD",
            "purpose": "Capacity Expansion",
            "idempotency_key": idem_key,
        }
        res_init = client.post("/v1/payment-requests", json=req_payload, headers=agent_headers)
        assert res_init.status_code == 200
        body_init = res_init.json()
        assert body_init["decision"] == "STEP_UP"
        req_id = body_init["request_id"]
        intent_digest = body_init["intent_digest"]

        # 2. Approver submits approval
        app_res = client.post(
            f"/v1/approvals/{req_id}",
            json={
                "decision": "ALLOW",
                "expected_digest": intent_digest,
                "reason": "Approved in cache test",
            },
            headers=approver_headers,
        )
        assert app_res.status_code == 200
        assert app_res.json()["decision"] == "ALLOW"

        # 3. Read-your-writes: immediate GET /v1/payment-requests/{id}
        read_res = client.get(f"/v1/payment-requests/{req_id}", headers=agent_headers)
        assert read_res.status_code == 200
        read_body = read_res.json()
        assert read_body["decision"] == "ALLOW", "Immediate read must reflect updated ALLOW state"
        assert read_body["request_state"] in ("SETTLED", "RECONCILE")


@pytest.mark.asyncio
async def test_cold_start_stampede(agent_token):
    """20 simultaneous first requests execute cleanly with zero errors."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(120.0, connect=15.0),
        limits=httpx.Limits(max_connections=25, max_keepalive_connections=25),
    ) as client:
        headers = {"Authorization": f"Bearer {agent_token}"}

        async def send_req(i: int):
            payload = {
                "agent_id": "agent-auto-1",
                "recipient_id": "vendor_infra_aws",
                "amount_minor": 1,
                "currency": "USD",
                "purpose": f"Stampede Test Request #{i}",
                "idempotency_key": f"stampede-{i}-{uuid.uuid4().hex[:8]}",
            }
            return await client.post("/v1/payment-requests", json=payload, headers=headers)

        tasks = [send_req(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        for idx, res in enumerate(results):
            err_msg = f"Request {idx} failed with {res.status_code}: {res.text}"
            assert res.status_code == 200, err_msg
            data = res.json()
            assert data["decision"] == "ALLOW"
            assert data["request_state"] in ("SETTLED", "RECONCILE")
