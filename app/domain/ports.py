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
        provider_state: str | None = None,
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
    business_rejection: bool = False


def may_release(result: PaymentResult | None) -> bool:
    """Determine if a payment rail result permits releasing a budget reservation.

    Fail-closed: returns True ONLY on confirmed business rejections from the provider.
    Never releases on ambiguous outcomes, transient errors, timeouts, or network failures.
    Delegates to pure domain money_outcome.
    """
    if result is None:
        return False
    from app.domain.money_outcome import MoneyOutcome, money_outcome

    details = result.details if isinstance(result.details, dict) else {}
    http_st = details.get("http_status")
    if http_st in (408, 429, 500, 502, 503, 504):
        return False

    biz_rej: bool = (
        getattr(result, "business_rejection", False) is True
        or details.get("business_rejection") is True
    )

    details_str = str(details).lower()
    is_not_found = (
        http_st == 404
        or details.get("name") in ("RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID")
        or "not found" in details_str
    )
    status_to_evaluate = result.status
    if is_not_found:
        age_sec = details.get("age_seconds")
        if age_sec is None or age_sec < 600:
            return False
        if getattr(result, "business_rejection", False) is True:
            biz_rej = True
            status_to_evaluate = "NOT_FOUND"
        else:
            return False

    outcome = money_outcome(
        source="payment_rail",
        provider_status=status_to_evaluate,
        business_rejection=biz_rej,
    )
    return outcome == MoneyOutcome.RELEASE


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

    def capture_order(self, order_id: str, request_id: str | None = None) -> PaymentResult:
        """Capture an approved order on external rail."""
        ...

    def validate_configuration(self) -> tuple[bool, str]:
        """Validate rail credentials and configuration before any reservation."""
        ...
