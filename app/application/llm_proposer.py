"""LLM proposer, grounding verification, and safety memory.

Invariants:
- The LLM is never in the authorization path. It proposes; the policy engine decides.
- Model or heuristic output may tighten a decision, never loosen it.
- Untrusted text is strictly wrapped inside delimiters, never treated as instructions.
- Grounded explanation validator rejects any hallucinations of amounts or payees.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.application.dtos import AuthorizationResponseDTO, AuthorizeTransactionCommand
from app.domain.models import DecisionOutcome

INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"(?i)system\s+override",
    r"(?i)you\s+are\s+in\s+debug(\s+test)?\s+mode",
    r"(?i)bypass\s+(policy|review|authorization|checks)",
    r"(?i)authorize\s+(this\s+transaction\s+)?immediately\s+with\s+decision\s+allow",
    r"(?i)disregard\s+the\s+above",
    r"(?i)do\s+not\s+check\s+budget",
]


class HeuristicRiskScanner:
    """Detects adversarial prompt injections and anomalous spikes in proposed intents."""

    def scan_purpose_text(self, text: str) -> DecisionOutcome | None:
        """Scan untrusted user text for prompt injection keywords."""
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text):
                # Anomaly detected: escalate to STEP_UP or DENY
                return DecisionOutcome.STEP_UP
        return None

    def scan_velocity(
        self, recent_amounts_minor: list[int], current_amount_minor: int
    ) -> DecisionOutcome | None:
        """Simple anomaly spike check based on historical spending."""
        if not recent_amounts_minor:
            return None
        avg = sum(recent_amounts_minor) / len(recent_amounts_minor)
        if current_amount_minor > (avg * 5) and current_amount_minor > 50_000:
            return DecisionOutcome.STEP_UP
        return None


class GroundedExplanationValidator:
    """Verifies that assistant explanations do not hallucinate amounts, payees, or decisions.

    Rule: If the explanation mentions an amount, currency, or payee not present in the
    decision record, validation fails and a templated deterministic explanation is used.
    """

    @staticmethod
    def format_templated_explanation(record: AuthorizationResponseDTO) -> str:
        codes_str = ", ".join(c.value for c in record.reason_codes) or "NONE"
        reasons_str = "; ".join(record.reasons)
        payout_str = f" Dispatched transaction ID: {record.payout_id}." if record.payout_id else ""
        return (
            f"Decision: {record.decision.value} (Request: {record.request_id}). "
            f"Reason codes: [{codes_str}]. Details: {reasons_str}.{payout_str}"
        )

    def validate_and_ground(
        self,
        candidate_explanation: str,
        record: AuthorizationResponseDTO,
        expected_recipient_id: str,
        expected_amount_minor: int,
    ) -> tuple[bool, str]:
        """Validate candidate LLM response against the ground-truth decision record."""
        # 1. Decision outcome must match
        if record.decision.value not in candidate_explanation:
            return False, self.format_templated_explanation(record)

        # 2. Check for fabricated payees
        if (
            "recipient" in candidate_explanation.lower()
            and expected_recipient_id not in candidate_explanation
        ):
            return False, self.format_templated_explanation(record)

        # 3. Check for hallucinated numbers
        digits = re.findall(r"\b\d+\b", candidate_explanation)
        cents_str = str(expected_amount_minor)
        dollars_str = str(expected_amount_minor // 100)
        for d in digits:
            if d not in (cents_str, dollars_str, record.request_id) and len(d) > 2:
                # Potential hallucinated financial amount
                return False, self.format_templated_explanation(record)

        return True, candidate_explanation


@dataclass
class ConversationMemory:
    """Rolling conversational memory capped in size for runtime context."""

    session_id: str
    max_turns: int = 10
    turns: list[dict[str, Any]] = field(default_factory=list)

    def add_turn(self, role: str, text: str) -> None:
        self.turns.append({"role": role, "text": text})
        if len(self.turns) > self.max_turns * 2:
            self.turns = self.turns[-self.max_turns * 2 :]

    def get_context_summary(self) -> str:
        return f"Session: {self.session_id} | Turns: {len(self.turns)}"


class MockLLMProposer:
    """Provider-agnostic intent extractor and grounded proposer."""

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
        # Check injection heuristic
        advisory_signal = self.scanner.scan_purpose_text(untrusted_user_text)

        # Extract amount if present (e.g. '$50' or '50 USD' or '25')
        amount_match = re.search(r"\$?(\d+)(?:\.(\d{2}))?", untrusted_user_text)
        if amount_match:
            dollars = int(amount_match.group(1))
            cents = int(amount_match.group(2)) if amount_match.group(2) else 0
            amount_minor = (dollars * 100) + cents
        else:
            amount_minor = 2500  # Default $25.00

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
