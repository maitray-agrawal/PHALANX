"""Unit tests for PHALANX MCP server."""

from app.mcp.server import PhalanxMcpServer


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

    # 2. Query mandate status
    mandate_info = server.get_mandate_status("mandate_default_astra")
    assert mandate_info["status"] == "ACTIVE"
    assert mandate_info["single_limit_minor"] == 500_000

    # 3. Verify ledger
    ledger_verify = server.verify_ledger()
    assert ledger_verify["is_valid"] is True
    assert ledger_verify["total_events"] >= 1
