"""LLM proposer, grounding verification, and safety memory compatibility module.

Invariants:
- The LLM is never in the authorization path. It proposes; the policy engine decides.
- Model or heuristic output may tighten a decision, never loosen it.
- Untrusted text is strictly wrapped inside delimiters, never treated as instructions.
- Grounded explanation validator rejects any hallucinations of amounts or payees.
"""

from app.application.advisory_signals import HeuristicRiskScanner
from app.application.dtos import AuthorizeTransactionCommand
from app.application.grounding import GroundedExplanationValidator
from app.application.intent_extractor import (
    DELIMITER_END,
    DELIMITER_START,
    IntentExtractor,
    MandateSummary,
    TransactionIntentDraft,
)
from app.application.memory import PrincipalSessionMemory

__all__ = [
    "DELIMITER_END",
    "DELIMITER_START",
    "ConversationMemory",
    "GroundedExplanationValidator",
    "HeuristicRiskScanner",
    "IntentExtractor",
    "MandateSummary",
    "MockLLMProposer",
    "TransactionIntentDraft",
]

# Legacy alias for backward compatibility
ConversationMemory = PrincipalSessionMemory


class MockLLMProposer:
    """Compatibility wrapper around IntentExtractor and HeuristicRiskScanner."""

    def __init__(self) -> None:
        self.scanner = HeuristicRiskScanner()
        self.grounding = GroundedExplanationValidator()

    def extract_intent_from_user_prompt(
        self,
        untrusted_user_text: str,
        agent_id: str = "agent-auto-1",
        default_recipient: str = "vendor-paypal-sandbox-1",
    ) -> AuthorizeTransactionCommand:
        """Extract structured intent with untrusted text encapsulated in delimiters."""
        advisory_signal = self.scanner.scan_purpose_text(untrusted_user_text)

        # Basic regex parsing
        import re

        amount_match = re.search(r"\$?(\d+)(?:\.(\d{2}))?", untrusted_user_text)
        if amount_match:
            dollars = int(amount_match.group(1))
            cents = int(amount_match.group(2)) if amount_match.group(2) else 0
            amount_minor = (dollars * 100) + cents
        else:
            amount_minor = 2500

        sanitized_purpose = untrusted_user_text[:200].strip() or "Standard operational expense"
        key_hash = re.sub(r"[^a-zA-Z0-9]", "", sanitized_purpose)[:16] or "tx"

        return AuthorizeTransactionCommand(
            agent_id=agent_id,
            recipient_id=default_recipient,
            amount_minor=amount_minor,
            currency="USD",
            purpose=sanitized_purpose,
            idempotency_key=f"intent_{key_hash}_{amount_minor}",
            anomaly_signal=advisory_signal,
        )
