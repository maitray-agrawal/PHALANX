"""Runtime conversational memory and deterministic knowledge base.

Invariants (Manual 43, 44):
- Session memory is strictly scoped to the authenticated principal.
- Rolling session summary is updated every turn and capped in character length.
- Preserves the last N turns for local conversational context.
- Knowledge base is 100% deterministic, queried strictly by key.
- Outside the knowledge base, the system returns 'I do not know.' Never hallucinates facts.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

UNKNOWN_RESPONSE = "I do not know."


@dataclass(frozen=True)
class ConversationTurn:
    role: str  # "user" or "assistant"
    content: str
    timestamp_utc: datetime


@dataclass
class PrincipalSessionMemory:
    """Rolling session memory scoped to a specific principal."""

    session_id: str
    principal_id: str
    max_turns: int = 5
    max_summary_chars: int = 500
    turns: list[ConversationTurn] = field(default_factory=list)
    rolling_summary: str = ""

    def add_turn(self, role: str, content: str) -> None:
        """Add a conversation turn, update rolling summary, and truncate history."""
        now = datetime.now(UTC)
        turn = ConversationTurn(role=role, content=content, timestamp_utc=now)
        self.turns.append(turn)

        # Truncate to last N turns
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

        # Update rolling summary
        snippet = f"[{role.upper()}]: {content[:80]}"
        new_summary = snippet if not self.rolling_summary else f"{self.rolling_summary} | {snippet}"

        if len(new_summary) > self.max_summary_chars:
            new_summary = new_summary[-self.max_summary_chars :]
        self.rolling_summary = new_summary

    def get_context_snapshot(self) -> dict[str, Any]:
        """Return structured context for LLM prompt assembly."""
        return {
            "session_id": self.session_id,
            "principal_id": self.principal_id,
            "rolling_summary": self.rolling_summary,
            "recent_turns": [{"role": t.role, "content": t.content} for t in self.turns],
        }


class DeterministicKnowledgeBase:
    """Key-addressable ground-truth knowledge repository. Outside it: 'I do not know.'"""

    def __init__(self) -> None:
        self._faq: dict[str, str] = {
            "step_up": (
                "A step-up approval occurs when a transaction exceeds the instant threshold, "
                "velocity cap, or triggers an anomaly signal. A human approver belonging to the "
                "mandate's principal must approve it."
            ),
            "minor_units": (
                "All monetary amounts in PHALANX are stored as integer minor units (e.g. cents). "
                "For USD, 100 minor units equals $1.00. Floating point arithmetic is prohibited."
            ),
            "ledger": (
                "The PHALANX ledger is an append-only cryptographic hash chain. "
                "Each event references the previous event's SHA-256 hash. "
                "The database role forbids UPDATE and DELETE."
            ),
            "mandate_seal": (
                "Mandates are signed with Ed25519 over RFC 8785 canonical JSON. The signature is "
                "an integrity seal ensuring limits and payees have not been tampered with."
            ),
        }

        self._policy_spec: str = (
            "PHALANX evaluates policies in Strict Deterministic Precedence:\n"
            "1. Mandate Active & In-Window\n"
            "2. Payee in Allowed List\n"
            "3. Purpose in Allowed List\n"
            "4. Single Transaction Limit\n"
            "5. Lifetime Budget Cap\n"
            "6. Instant Auto-Approval Threshold\n"
            "7. Advisory Anomaly Signals (can only escalate ALLOW->STEP_UP->DENY)"
        )

        self._mandate_summaries: dict[str, str] = {}
        self._recent_decisions: dict[str, list[str]] = {}

    def register_mandate_summary(self, principal_id: str, summary_text: str) -> None:
        """Register deterministic active mandate parameters for a principal."""
        self._mandate_summaries[principal_id] = summary_text

    def register_decision_record(self, principal_id: str, decision_summary: str) -> None:
        """Register recent decision summaries for a principal."""
        if principal_id not in self._recent_decisions:
            self._recent_decisions[principal_id] = []
        self._recent_decisions[principal_id].append(decision_summary)
        if len(self._recent_decisions[principal_id]) > 5:
            self._recent_decisions[principal_id].pop(0)

    def lookup_by_key(self, key: str, principal_id: str = "default_principal") -> str:
        """Deterministic key lookup. Returns 'I do not know.' if key is not found."""
        k = key.lower().strip()
        if k == "policy_spec":
            return self._policy_spec
        if k == "mandate_summary":
            return self._mandate_summaries.get(
                principal_id, "No active mandate summary registered."
            )
        if k == "recent_decisions":
            recs = self._recent_decisions.get(principal_id, [])
            return "\n".join(recs) if recs else "No recent decisions recorded."
        if k in self._faq:
            return self._faq[k]
        return UNKNOWN_RESPONSE

    def answer_query(self, query: str, principal_id: str = "default_principal") -> str:
        """Query knowledge base.

        If query cannot be resolved to a known key, returns 'I do not know.'
        """
        q = query.lower()
        if "policy" in q or "precedence" in q or "rules" in q:
            return self.lookup_by_key("policy_spec", principal_id)
        if "mandate" in q and ("limit" in q or "active" in q or "summary" in q):
            return self.lookup_by_key("mandate_summary", principal_id)
        if "recent" in q and "decision" in q:
            return self.lookup_by_key("recent_decisions", principal_id)
        if "step up" in q or "approval" in q:
            return self.lookup_by_key("step_up", principal_id)
        if "minor unit" in q or "cent" in q or "integer" in q:
            return self.lookup_by_key("minor_units", principal_id)
        if "ledger" in q or "hash chain" in q:
            return self.lookup_by_key("ledger", principal_id)
        if "seal" in q or "ed25519" in q:
            return self.lookup_by_key("mandate_seal", principal_id)

        # Strict adherence to truthfulness boundary: Outside knowledge base, say 'I do not know.'
        return UNKNOWN_RESPONSE
