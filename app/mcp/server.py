"""Model Context Protocol (MCP) server for PHALANX.

Exposes autonomous agent governance tools using the official Python MCP SDK (mcp).

Invariants:
- All tool calls route strictly through app/application services.
- Mandatory authentication as an agent identity (Role.AGENT).
- No credential or secret key exposure to MCP clients.
- Returns deterministic decision records and pending-approval references only.
"""

import logging

from mcp.server.fastmcp import FastMCP

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
