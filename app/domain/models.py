"""Pure domain models for PHALANX.

Invariants:
- Zero I/O, no clock access (time is injected), no randomness.
- Money is represented strictly as integer minor units.
- Decisions can be escalated (ALLOW -> STEP_UP -> DENY), never downgraded.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DecisionOutcome(str, Enum):
    """Authorization decision outcome.

    Hierarchy of severity: ALLOW < STEP_UP < DENY.
    Signals can only raise severity, never lower it.
    """

    ALLOW = "ALLOW"
    STEP_UP = "STEP_UP"
    DENY = "DENY"

    @property
    def severity(self) -> int:
        match self:
            case DecisionOutcome.ALLOW:
                return 1
            case DecisionOutcome.STEP_UP:
                return 2
            case DecisionOutcome.DENY:
                return 3


def guard_advisory_escalation(
    base: DecisionOutcome,
    heuristic_or_ml_recommendation: DecisionOutcome | None,
) -> DecisionOutcome:
    """Enforce one-way asymmetric escalation guard.

    Crucial invariant: Advisory signals can ONLY raise severity (ALLOW -> STEP_UP -> DENY),
    never lower or soften it.
    """
    if heuristic_or_ml_recommendation is None:
        return base

    if heuristic_or_ml_recommendation.severity > base.severity:
        return heuristic_or_ml_recommendation
    return base


# Backward compatibility alias
escalate_decision = guard_advisory_escalation


@dataclass(frozen=True)
class Money:
    """Immutable monetary representation in integer minor units (e.g. cents)."""

    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if self.amount_minor < 0:
            raise ValueError(f"Amount in minor units cannot be negative: {self.amount_minor}")
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError(f"Currency must be 3-letter uppercase ISO code: {self.currency}")

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            msg = f"Cannot add different currencies: {self.currency} and {other.currency}"
            raise ValueError(msg)
        return Money(amount_minor=self.amount_minor + other.amount_minor, currency=self.currency)


@dataclass(frozen=True)
class TransactionIntent:
    """Financial transaction requested by an autonomous agent."""

    agent_id: str
    recipient_id: str
    money: Money
    purpose: str
    idempotency_key: str
    occurred_at_utc: datetime
    invoice_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("agent_id cannot be blank")
        if not self.recipient_id.strip():
            raise ValueError("recipient_id cannot be blank")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key cannot be blank")
        if self.occurred_at_utc.tzinfo is None:
            raise ValueError("occurred_at_utc must be timezone-aware UTC")
        if self.invoice_reference is not None and not self.invoice_reference.strip():
            raise ValueError("invoice_reference cannot be whitespace-only")


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Immutable evaluation output from the pure policy engine."""

    outcome: DecisionOutcome
    reasons: tuple[str, ...] = field(default_factory=tuple)
    escalated_from: DecisionOutcome | None = None
    evaluated_at_utc: datetime = field(default_factory=lambda: datetime.min)
