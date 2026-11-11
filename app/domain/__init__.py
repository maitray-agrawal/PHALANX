"""Pure domain layer for PHALANX.

Guarantees:
- Zero I/O, no network, no clock calls, no randomness.
- Imports nothing from app.api, app.application, or app.infrastructure.
"""

from app.domain.models import (
    DecisionOutcome,
    Money,
    PolicyEvaluationResult,
    TransactionIntent,
    escalate_decision,
)
from app.domain.money_outcome import (
    EXPLICIT_COMPLETED_STATUSES,
    EXPLICIT_TERMINAL_FAILURE_STATUSES,
    MoneyOutcome,
    money_outcome,
)
from app.domain.ports import ClockPort, LedgerPort

__all__ = [
    "ClockPort",
    "DecisionOutcome",
    "EXPLICIT_COMPLETED_STATUSES",
    "EXPLICIT_TERMINAL_FAILURE_STATUSES",
    "LedgerPort",
    "Money",
    "MoneyOutcome",
    "PolicyEvaluationResult",
    "TransactionIntent",
    "escalate_decision",
    "money_outcome",
]
