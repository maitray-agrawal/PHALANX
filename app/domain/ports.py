"""Ports (protocols) for domain and application layers."""

from datetime import datetime
from typing import Protocol

from app.domain.models import PolicyEvaluationResult, TransactionIntent


class ClockPort(Protocol):
    """Port for time provision. Guarantees injected UTC timestamps."""

    def now_utc(self) -> datetime:
        """Return the current UTC timestamp."""
        ...


class LedgerPort(Protocol):
    """Port for append-only audit trail storage."""

    def append_event(
        self,
        event_type: str,
        intent: TransactionIntent,
        result: PolicyEvaluationResult,
        recorded_at_utc: datetime,
    ) -> str:
        """Record an immutable ledger event and return event_id."""
        ...
