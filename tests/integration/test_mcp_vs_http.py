"""Verification suite proving identical decisions between MCP and HTTP endpoints.

Requirement: VERIFY: identical decisions to HTTP for identical inputs.
Tests parity across:
1. Pre-authorized transaction within limits (ALLOW).
2. High-value transaction exceeding instant threshold (STEP_UP).
3. Transaction exceeding mandate single limit (DENY).
4. Transaction with currency mismatch (DENY).
5. Idempotency replay with identical key and digest.
6. Mandate status query parity.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.domain.policy import PolicyReasonCode
from app.infrastructure.tokens import Role, create_role_token
from app.main import app
from app.mcp.server import mcp_server


@pytest.fixture
def agent_token() -> str:
    return create_role_token(
        role=Role.AGENT,
        principal_id="org_astra_corp",
        agent_id="agent-auto-1",
    )


@pytest.fixture
def http_client() -> TestClient:
    return TestClient(app)


@pytest.mark.asyncio
async def test_parity_pre_authorized_spend_allow(
    http_client: TestClient,
    agent_token: str,
) -> None:
    """Pre-authorized spend ($15.00) yields identical ALLOW decision on MCP and HTTP."""
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "vendor-paypal-sandbox-1",
        "amount_minor": 1500,
        "currency": "USD",
        "purpose": "Monthly server hosting payment",
        "idempotency_key": "parity_allow_001",
    }

    # 1. Execute via HTTP (/api/v1/authorize)
    http_resp = http_client.post(
        "/api/v1/authorize",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert http_resp.status_code == 200
    http_data = http_resp.json()

    # 2. Execute identical request via MCP
    mcp_payload = dict(payload)
    mcp_payload["idempotency_key"] = "parity_allow_001_mcp"  # unique key for fresh evaluation
    mcp_payload["auth_token"] = agent_token
    mcp_res = await mcp_server.call_tool("request_payment", mcp_payload)
    mcp_data = json.loads(mcp_res[0].text)

    # 3. Assert identical decision properties
    assert mcp_data["decision"] == http_data["decision"] == "ALLOW"
    assert mcp_data["intent_digest"] is not None
    assert http_data["intent_digest"] is not None
    assert mcp_data["payout_id"] is not None
    assert http_data["payout_id"] is not None
    assert (
        mcp_data["reason_codes"]
        == http_data["reason_codes"]
        == [PolicyReasonCode.PRE_AUTHORIZED.value]
    )


@pytest.mark.asyncio
async def test_parity_instant_threshold_exceeded_step_up(
    http_client: TestClient,
    agent_token: str,
) -> None:
    """High-value request ($1,200.00) yields identical STEP_UP decision on MCP and HTTP."""
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "vendor-paypal-sandbox-1",
        "amount_minor": 120000,
        "currency": "USD",
        "purpose": "High capacity server upgrade",
        "idempotency_key": "parity_stepup_001",
    }

    # 1. Execute via HTTP
    http_resp = http_client.post(
        "/api/v1/authorize",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert http_resp.status_code == 200
    http_data = http_resp.json()

    # 2. Execute via MCP
    mcp_payload = dict(payload)
    mcp_payload["idempotency_key"] = "parity_stepup_001_mcp"
    mcp_payload["auth_token"] = agent_token
    mcp_res = await mcp_server.call_tool("request_payment", mcp_payload)
    mcp_data = json.loads(mcp_res[0].text)

    # 3. Assert identical decision properties
    assert mcp_data["decision"] == http_data["decision"] == "STEP_UP"
    assert mcp_data["payout_id"] is None
    assert http_data["payout_id"] is None
    assert mcp_data["request_id"].startswith("req_")
    assert http_data["request_id"].startswith("req_")
    assert PolicyReasonCode.INSTANT_THRESHOLD_EXCEEDED.value in mcp_data["reason_codes"]
    assert PolicyReasonCode.INSTANT_THRESHOLD_EXCEEDED.value in http_data["reason_codes"]


@pytest.mark.asyncio
async def test_parity_single_limit_exceeded_deny(
    http_client: TestClient,
    agent_token: str,
) -> None:
    """Request exceeding single transaction cap ($6,000.00) yields identical DENY."""
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "vendor-paypal-sandbox-1",
        "amount_minor": 600000,
        "currency": "USD",
        "purpose": "Procure datacenter rack",
        "idempotency_key": "parity_deny_single_001",
    }

    # 1. Execute via HTTP
    http_resp = http_client.post(
        "/api/v1/authorize",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert http_resp.status_code == 200
    http_data = http_resp.json()

    # 2. Execute via MCP
    mcp_payload = dict(payload)
    mcp_payload["idempotency_key"] = "parity_deny_single_001_mcp"
    mcp_payload["auth_token"] = agent_token
    mcp_res = await mcp_server.call_tool("request_payment", mcp_payload)
    mcp_data = json.loads(mcp_res[0].text)

    # 3. Assert identical decision properties
    assert mcp_data["decision"] == http_data["decision"] == "DENY"
    assert mcp_data["payout_id"] is None
    assert http_data["payout_id"] is None
    assert PolicyReasonCode.SINGLE_LIMIT_EXCEEDED.value in mcp_data["reason_codes"]
    assert PolicyReasonCode.SINGLE_LIMIT_EXCEEDED.value in http_data["reason_codes"]


@pytest.mark.asyncio
async def test_parity_currency_mismatch_deny(
    http_client: TestClient,
    agent_token: str,
) -> None:
    """Currency mismatch (EUR vs USD mandate) yields identical DENY."""
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "vendor-paypal-sandbox-1",
        "amount_minor": 1000,
        "currency": "EUR",
        "purpose": "European cloud server invoice",
        "idempotency_key": "parity_currency_001",
    }

    # 1. HTTP
    http_resp = http_client.post(
        "/api/v1/authorize",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    http_data = http_resp.json()

    # 2. MCP
    mcp_payload = dict(payload)
    mcp_payload["idempotency_key"] = "parity_currency_001_mcp"
    mcp_payload["auth_token"] = agent_token
    mcp_res = await mcp_server.call_tool("request_payment", mcp_payload)
    mcp_data = json.loads(mcp_res[0].text)

    assert mcp_data["decision"] == http_data["decision"] == "DENY"
    assert PolicyReasonCode.CURRENCY_MISMATCH.value in mcp_data["reason_codes"]
    assert PolicyReasonCode.CURRENCY_MISMATCH.value in http_data["reason_codes"]


@pytest.mark.asyncio
async def test_parity_idempotent_duplicate_replay(
    http_client: TestClient,
    agent_token: str,
) -> None:
    """Duplicate requests with same idempotency key return identical cached decisions."""
    key = "parity_idempotent_key_replay"
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "vendor-paypal-sandbox-1",
        "amount_minor": 1500,
        "currency": "USD",
        "purpose": "Idempotent payment test",
        "idempotency_key": key,
    }

    # 1. First execution via HTTP
    resp1 = http_client.post(
        "/api/v1/authorize",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    data1 = resp1.json()

    # 2. Second execution via MCP with same key & body
    mcp_payload = dict(payload)
    mcp_payload["auth_token"] = agent_token
    res2 = await mcp_server.call_tool("request_payment", mcp_payload)
    data2 = json.loads(res2[0].text)

    # Must return exact same decision and digest
    assert data1["decision"] == data2["decision"] == "ALLOW"
    assert data1["intent_digest"] == data2["intent_digest"]


@pytest.mark.asyncio
async def test_parity_mandate_status_query(
    http_client: TestClient,
    agent_token: str,
) -> None:
    """get_mandate_status returns identical parameters to GET /v1/mandates/{id}."""
    mandate_id = "mandate_default_astra"

    # 1. HTTP
    http_resp = http_client.get(
        f"/v1/mandates/{mandate_id}",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert http_resp.status_code == 200
    http_mandate = http_resp.json()

    # 2. MCP
    mcp_res = await mcp_server.call_tool(
        "get_mandate_status",
        {
            "mandate_id": mandate_id,
            "auth_token": agent_token,
        },
    )
    mcp_mandate = json.loads(mcp_res[0].text)

    # 3. Assert exact parameter equality
    assert mcp_mandate["mandate_id"] == http_mandate["mandate_id"]
    assert mcp_mandate["version"] == http_mandate["version"]
    assert mcp_mandate["status"] == http_mandate["status"]
    assert mcp_mandate["single_limit_minor"] == http_mandate["single_limit_minor"]
    assert mcp_mandate["instant_threshold_minor"] == http_mandate["instant_threshold_minor"]
    assert mcp_mandate["lifetime_budget_minor"] == http_mandate["lifetime_budget_minor"]
    assert mcp_mandate["currency"] == http_mandate["currency"]
    assert mcp_mandate["allowed_payees"] == http_mandate["allowed_payees"]
