"""Unit tests for PHALANX official Python MCP SDK server."""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from app.infrastructure.tokens import Role, create_role_token
from app.mcp.server import PhalanxMcpServer, authenticate_agent_identity, mcp_server


def test_mcp_server_request_payment_and_verify_ledger() -> None:
    server = PhalanxMcpServer()

    # 1. Evaluate request
    result = server.request_payment(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=1200,
        currency="USD",
        purpose="Monthly subscription renewal",
        idempotency_key="mcp-tx-001",
    )
    assert result["decision"] == "ALLOW"
    assert result["payout_id"] is not None
    assert "secret" not in result
    assert "client_secret" not in result

    # 2. Query mandate status
    mandate_info = server.get_mandate_status("mandate_default_astra")
    assert mandate_info["status"] == "ACTIVE"
    assert mandate_info["single_limit_minor"] == 500_000
    assert "signing_key" not in mandate_info
    assert "private_key" not in mandate_info

    # 3. Verify ledger
    ledger_verify = server.verify_ledger()
    assert ledger_verify["is_valid"] is True
    assert ledger_verify["total_events"] >= 1


@pytest.mark.asyncio
async def test_fastmcp_call_tool_async_execution() -> None:
    """Verify official FastMCP tool execution via call_tool."""
    agent_token = create_role_token(
        role=Role.AGENT,
        principal_id="org_astra_corp",
        agent_id="agent-auto-1",
    )

    # Call get_mandate_status
    res = await mcp_server.call_tool(
        "get_mandate_status",
        {
            "mandate_id": "mandate_default_astra",
            "auth_token": agent_token,
        },
    )
    assert len(res) == 1
    data = json.loads(res[0].text)
    assert data["mandate_id"] == "mandate_default_astra"
    assert data["status"] == "ACTIVE"

    # Call request_payment (pre-authorized spend)
    tx_res = await mcp_server.call_tool(
        "request_payment",
        {
            "agent_id": "agent-auto-1",
            "recipient_id": "vendor-paypal-sandbox-1",
            "amount_minor": 2000,
            "currency": "USD",
            "purpose": "Cloud compute nodes",
            "idempotency_key": "mcp-async-tx-001",
            "auth_token": agent_token,
        },
    )
    assert len(tx_res) == 1
    tx_data = json.loads(tx_res[0].text)
    assert tx_data["decision"] == "ALLOW"
    assert tx_data["request_id"].startswith("req_")
    assert tx_data["payout_id"] is not None


def test_authenticate_agent_identity_enforces_agent_role() -> None:
    """Verify authenticate_agent_identity rejects non-agent or invalid tokens."""
    # 1. Valid agent token succeeds
    valid_agent = authenticate_agent_identity("demo-agent", "agent-auto-1")
    assert valid_agent.role == Role.AGENT

    # 2. Approver token rejected
    with pytest.raises(PermissionError, match="Client must authenticate as an agent identity"):
        authenticate_agent_identity("demo-approver", "agent-auto-1")

    # 3. Principal token rejected
    with pytest.raises(PermissionError, match="Client must authenticate as an agent identity"):
        authenticate_agent_identity("demo-principal", "agent-auto-1")

    # 4. Invalid token rejected
    with pytest.raises(PermissionError, match="Authentication failed"):
        authenticate_agent_identity("invalid.token.structure", "agent-auto-1")


@pytest.mark.asyncio
async def test_fastmcp_rejects_unauthorized_role_tokens() -> None:
    """Verify FastMCP call_tool raises error when caller uses non-agent token."""
    with pytest.raises(ToolError, match="Client must authenticate as an agent identity"):
        await mcp_server.call_tool(
            "request_payment",
            {
                "agent_id": "agent-auto-1",
                "recipient_id": "vendor-paypal-sandbox-1",
                "amount_minor": 1000,
                "currency": "USD",
                "purpose": "Testing unauthorized role",
                "idempotency_key": "unauth-role-001",
                "auth_token": "demo-approver",
            },
        )
