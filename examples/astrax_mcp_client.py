"""AstraX Autonomous Financial Agent - MCP Integration Example.

Demonstrates an AstraX procurement / operations agent connecting to PHALANX
using the official Model Context Protocol (MCP) Python interface.

Invariants demonstrated:
1. Agent identity authentication via short-lived role token.
2. Querying mandate status without exposing internal keys or private configuration.
3. Submitting payment requests that evaluate deterministically against policy.
4. Handling ALLOW decisions (receiving payout reference).
5. Handling STEP_UP decisions (receiving human approval reference; agent cannot approve).
6. Absolute zero credential exposure.
"""

import asyncio
import json
import logging

from app.infrastructure.tokens import Role, create_role_token
from app.mcp.server import mcp_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [AstraX-Agent] %(message)s")
logger = logging.getLogger("astrax.agent")


async def run_astrax_agent() -> None:
    logger.info("Initializing AstraX Procurement Agent (agent-auto-1)...")

    # 1. Obtain signed agent role token
    agent_token = create_role_token(
        role=Role.AGENT,
        principal_id="org_astra_corp",
        agent_id="agent-auto-1",
        expires_in_seconds=3600,
    )
    logger.info("Agent identity established with signed token.")

    # 2. Query mandate status via MCP
    logger.info("Step 1: Inspecting operational mandate limits via get_mandate_status...")
    mandate_res = await mcp_server.call_tool(
        "get_mandate_status",
        {
            "mandate_id": "mandate_default_astra",
            "auth_token": agent_token,
        },
    )
    mandate_data = json.loads(mandate_res[0].text)
    logger.info(
        "Active Mandate: %s (Status: %s, Single Limit: $%0.2f, Remaining: $%0.2f)",
        mandate_data["mandate_id"],
        mandate_data["status"],
        mandate_data["single_limit_minor"] / 100,
        mandate_data["remaining_budget_minor"] / 100,
    )

    # 3. Request 1: Pre-authorized SaaS Subscription ($15.00) -> ALLOW
    logger.info("Step 2: Requesting pre-authorized recurring server hosting ($15.00 USD)...")
    req_allow = await mcp_server.call_tool(
        "request_payment",
        {
            "agent_id": "agent-auto-1",
            "recipient_id": "vendor-paypal-sandbox-1",
            "amount_minor": 1500,
            "currency": "USD",
            "purpose": "Monthly server hosting payment",
            "idempotency_key": "astrax_tx_allow_001",
            "auth_token": agent_token,
        },
    )
    allow_data = json.loads(req_allow[0].text)
    logger.info(
        "Authorization Decision: %s [Payout ID: %s, Request ID: %s]",
        allow_data["decision"],
        allow_data["payout_id"],
        allow_data["request_id"],
    )
    assert allow_data["decision"] == "ALLOW"
    assert allow_data["payout_id"] is not None

    # 4. Request 2: High-Value Server Upgrade ($1,200.00) -> STEP_UP
    logger.info("Step 3: Requesting high-value hardware allocation ($1,200.00 USD)...")
    req_stepup = await mcp_server.call_tool(
        "request_payment",
        {
            "agent_id": "agent-auto-1",
            "recipient_id": "vendor-paypal-sandbox-1",
            "amount_minor": 120000,
            "currency": "USD",
            "purpose": "Dedicated GPU server upgrade",
            "idempotency_key": "astrax_tx_stepup_001",
            "auth_token": agent_token,
        },
    )
    stepup_data = json.loads(req_stepup[0].text)
    logger.info(
        "Authorization Decision: %s [Request ID: %s, Reasons: %s]",
        stepup_data["decision"],
        stepup_data["request_id"],
        stepup_data["reasons"],
    )
    assert stepup_data["decision"] == "STEP_UP"
    assert stepup_data["payout_id"] is None
    logger.info(
        "Step-Up pending human supervisor approval. Reference: %s (Canonical Digest: %s)",
        stepup_data["request_id"],
        stepup_data["intent_digest"][:16],
    )

    logger.info("AstraX Procurement Agent completed workflow with zero security exceptions.")


if __name__ == "__main__":
    asyncio.run(run_astrax_agent())
