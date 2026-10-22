"""Model Context Protocol (MCP) server for PHALANX.

Invariants:
- MCP entry points route strictly through app/application services.
- Authenticated strictly as agent role (cannot approve or access secret keys).
- Returns structured decision records and digests only.
"""

from typing import Any

from app.api.dependencies import (
    get_authorization_service,
    get_ledger_service,
    get_mandate_service,
)
from app.application.dtos import AuthorizeTransactionCommand


class PhalanxMcpServer:
    """MCP server wrapper exposing financial agent governance tools."""

    def __init__(self) -> None:
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
    ) -> dict[str, Any]:
        """Request financial transaction authorization for an autonomous agent."""
        cmd = AuthorizeTransactionCommand(
            agent_id=agent_id,
            recipient_id=recipient_id,
            amount_minor=amount_minor,
            currency=currency,
            purpose=purpose,
            idempotency_key=idempotency_key,
        )
        resp = self._authz_service.authorize(cmd)
        return {
            "request_id": resp.request_id,
            "decision": resp.decision.value,
            "reasons": resp.reasons,
            "reason_codes": [c.value for c in resp.reason_codes],
            "intent_digest": resp.intent_digest,
            "payout_id": resp.payout_id,
            "evaluated_at_utc": resp.evaluated_at_utc.isoformat(),
        }

    def get_mandate_status(self, mandate_id: str) -> dict[str, Any]:
        """Fetch mandate limits and validity status."""
        mandate = self._mandate_service.get_mandate(mandate_id)
        if not mandate:
            return {"error": "Mandate not found", "mandate_id": mandate_id}
        return {
            "mandate_id": mandate.mandate_id,
            "version": mandate.version,
            "status": mandate.status.value,
            "single_limit_minor": mandate.single_limit_minor,
            "instant_threshold_minor": mandate.instant_threshold_minor,
            "lifetime_budget_minor": mandate.lifetime_budget_minor,
            "currency": mandate.currency,
            "valid_from_utc": mandate.valid_from_utc.isoformat(),
            "valid_until_utc": mandate.valid_until_utc.isoformat(),
        }

    def verify_ledger(self) -> dict[str, Any]:
        """Cryptographically verify the tamper-evident audit ledger chain."""
        res = self._ledger_service.verify_chain()
        return {
            "is_valid": res.is_valid,
            "message": res.message,
            "broken_index": res.broken_index,
            "total_events": res.total_events,
        }
