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
    """
    if result is None:
        return False
    if getattr(result, "business_rejection", False) is True:
        return True
    details = result.details if isinstance(result.details, dict) else {}
    if details.get("business_rejection") is True:
        return True
    if (
        getattr(result, "business_rejection", None) is False
        and details.get("business_rejection") is False
    ):
        return False

    status_upper = (result.status or "").upper()
    AMBIGUOUS_OR_TRANSIENT = {
        "RECONCILE",
        "LOOKUP_FAILED",
        "TIMEOUT",
        "NETWORK_ERROR",
        "CONNECTION_ERROR",
        "PROCESSING",
        "PENDING",
        "UNKNOWN",
        "ERROR",
        "CAPTURE_AMBIGUOUS",
        "TOKEN_ERROR",
    }
    if status_upper in AMBIGUOUS_OR_TRANSIENT:
        return False

    http_st = details.get("http_status")
    if http_st in (408, 429, 500, 502, 503, 504):
        return False

    CONFIRMED_REJECTION_STATUSES = {
        "DENIED",
        "REJECTED",
        "PAYOUT_REJECTED",
        "CANCELED",
        "EXPIRED",
        "VOIDED",
        "NOT_FOUND",
        "RESOURCE_NOT_FOUND",
    }
    details_str = str(details).lower()
    is_not_found = (
        details.get("http_status") == 404
        or details.get("name") in ("RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID")
        or "not found" in details_str
    )
    if status_upper in CONFIRMED_REJECTION_STATUSES or is_not_found:
        return True

    return bool(
        status_upper == "FAILED"
        and (
            getattr(result, "business_rejection", False) is True
            or details.get("business_rejection") is True
            or (isinstance(http_st, int) and 400 <= http_st < 500 and http_st not in (408, 429))
        )
    )


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
