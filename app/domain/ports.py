"""Ports (protocols) for domain and application layers."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.models import PolicyEvaluationResult, TransactionIntent


@runtime_checkable
class ClockPort(Protocol):
    """Port for time provision. Guarantees injected UTC timestamps."""

    def now_utc(self) -> datetime:
        """Return the current UTC timestamp."""
        ...


@runtime_checkable
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


@dataclass(frozen=True)
class PaymentResult:
    """Outcome of a payment rail execution."""

    success: bool
    transaction_id: str
    status: str
    details: dict[str, Any]


@runtime_checkable
class PaymentRail(Protocol):
    """Port for external payment rail integration (PayPal Sandbox, FakeRail)."""

    def pay(self, intent: TransactionIntent) -> PaymentResult:
        """Execute payment on external rail."""
        ...

    def lookup(self, transaction_id: str) -> PaymentResult:
        """Query external transaction status."""
        ...

    def normalize_error(self, raw_error: Any) -> str:
        """Translate third-party rail errors into standard domain failure reasons."""
        ...

    def verify_webhook(self, headers: dict[str, str], body_bytes: bytes) -> bool:
        """Verify authenticity of inbound webhook event signatures."""
        ...
