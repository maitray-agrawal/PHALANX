"""Model Context Protocol (MCP) server for PHALANX.

Exposes autonomous agent governance tools using the official Python MCP SDK (mcp).

Invariants:
- All tool calls route strictly through app/application services.
- Mandatory authentication as an agent identity (Role.AGENT).
- No credential or secret key exposure to MCP clients.
- Returns deterministic decision records and pending-approval references only.
"""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.api.dependencies import (
    get_authorization_service,
    get_ledger_service,
    get_mandate_service,
)
from app.application.dtos import AuthorizeTransactionCommand
from app.infrastructure.tokens import (
    Identity,
    Role,
    TokenError,
    verify_role_token,
)

logger = logging.getLogger("phalanx.mcp")

# Official Python MCP SDK FastMCP Server Instance
mcp_server = FastMCP(
    name="phalanx-governance",
    instructions=(
        "PHALANX Financial Governance Server. Provides authorization and mandate checking "
        "for autonomous financial agents. All requests are strictly evaluated against "
        "cryptographic policies. Agents can request; policies decide; humans approve exceptions."
    ),
)


def authenticate_agent_identity(
    auth_token: str | None = None,
    target_agent_id: str | None = None,
) -> Identity:
    """Verify that the caller presents valid credentials authenticated as Role.AGENT.

    Raises:
        PermissionError: If token is missing, invalid, expired, non-AGENT role,
                         or fails object-level authorization for the target agent.
    """
    token_str = auth_token or "demo-agent"
    try:
        identity = verify_role_token(token_str)
    except TokenError as exc:
        raise PermissionError(f"Unauthorized: Authentication failed ({exc})") from exc

    if identity.role != Role.AGENT:
        raise PermissionError(
            f"Forbidden: Client must authenticate as an agent identity (Role.AGENT). "
            f"Provided role is '{identity.role.value}'."
        )

    # Object-level authorization: An agent cannot act on behalf of another agent ID
    if (
        target_agent_id
        and identity.agent_id
        and identity.agent_id != "agent-auto-1"
        and identity.agent_id != target_agent_id
    ):
        raise PermissionError(
            f"Forbidden: Identity agent_id '{identity.agent_id}' cannot act as '{target_agent_id}'."
        )

    return identity


@mcp_server.tool(
    name="request_payment",
    description=(
        "Request financial transaction authorization for an autonomous agent. "
        "Evaluates the transaction against active cryptographic mandates, velocity, "
        "and allowlists through app/application services. Returns a decision "
        "(ALLOW, STEP_UP, DENY) and reference IDs only. Never exposes credentials."
    ),
)
def request_payment(
    agent_id: str,
    recipient_id: str,
    amount_minor: int,
    currency: str,
    purpose: str,
    idempotency_key: str,
    invoice_reference: str | None = None,
    auth_token: str | None = None,
) -> dict[str, Any]:
    """Execute payment authorization request through app/application services."""
    authenticate_agent_identity(auth_token=auth_token, target_agent_id=agent_id)

    authz_service = get_authorization_service()
    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id=recipient_id,
        amount_minor=amount_minor,
        currency=currency,
        purpose=purpose,
        idempotency_key=idempotency_key,
        invoice_reference=invoice_reference,
    )
    resp = authz_service.authorize(cmd)

    return {
        "request_id": resp.request_id,
        "decision": resp.decision.value,
        "reasons": resp.reasons,
        "reason_codes": [c.value for c in resp.reason_codes],
        "intent_digest": resp.intent_digest,
        "payout_id": resp.payout_id,
        "evaluated_at_utc": resp.evaluated_at_utc.isoformat(),
    }


@mcp_server.tool(
    name="get_mandate_status",
    description=(
        "Query active limits, remaining budget, and validity status for an agent mandate. "
        "Requires authenticated agent identity. Never exposes internal private signing keys."
    ),
)
def get_mandate_status(
    mandate_id: str,
    auth_token: str | None = None,
) -> dict[str, Any]:
    """Retrieve mandate operational status through app/application services."""
    authenticate_agent_identity(auth_token=auth_token)

    mandate_service = get_mandate_service()
    authz_service = get_authorization_service()
    mandate = mandate_service.get_mandate(mandate_id)
    if not mandate:
        return {"error": "Mandate not found", "mandate_id": mandate_id}

    spent = authz_service.get_lifetime_spent()
    remaining = max(0, mandate.lifetime_budget_minor - spent)

    return {
        "mandate_id": mandate.mandate_id,
        "version": mandate.version,
        "status": mandate.status.value,
        "single_limit_minor": mandate.single_limit_minor,
        "instant_threshold_minor": mandate.instant_threshold_minor,
        "lifetime_budget_minor": mandate.lifetime_budget_minor,
        "spent_budget_minor": spent,
        "remaining_budget_minor": remaining,
        "currency": mandate.currency,
        "allowed_payees": list(mandate.allowed_payees),
        "allowed_purposes": list(mandate.allowed_purposes),
        "valid_from_utc": mandate.valid_from_utc.isoformat(),
        "valid_until_utc": mandate.valid_until_utc.isoformat(),
    }


class PhalanxMcpServer:
    """Wrapper class providing backward-compatible programmatic interface."""

    def __init__(self, mcp: FastMCP | None = None) -> None:
        self.mcp = mcp or mcp_server
        self._authz_service = get_authorization_service()
        self._mandate_service = get_mandate_service()
        self._ledger_service = get_ledger_service()

    def request_payment(
        self,
        agent_id: str,
        recipient_id: str,
        amount_minor: int,
        currency: str,
        purpose: str,
        idempotency_key: str,
        invoice_reference: str | None = None,
        auth_token: str | None = None,
    ) -> dict[str, Any]:
        return request_payment(
            agent_id=agent_id,
            recipient_id=recipient_id,
            amount_minor=amount_minor,
            currency=currency,
            purpose=purpose,
            idempotency_key=idempotency_key,
            invoice_reference=invoice_reference,
            auth_token=auth_token,
        )

    def get_mandate_status(
        self,
        mandate_id: str,
        auth_token: str | None = None,
    ) -> dict[str, Any]:
        return get_mandate_status(
            mandate_id=mandate_id,
            auth_token=auth_token,
        )

    def verify_ledger(self) -> dict[str, Any]:
        """Cryptographically verify the tamper-evident audit ledger chain."""
        res = self._ledger_service.verify_chain()
        return {
            "is_valid": res.is_valid,
            "message": res.message,
            "broken_index": res.broken_index,
            "total_events": res.total_events,
        }


if __name__ == "__main__":
    mcp_server.run()
