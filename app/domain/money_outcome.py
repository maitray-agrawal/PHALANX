"""Pure domain money outcome decisions for financial reservation lifecycle.

Zero I/O, no clock, no network, no outer layer imports.
Enforces that:
1. SETTLE is returned ONLY for explicit provider completed status (e.g. COMPLETED, SUCCESS).
2. RELEASE is returned ONLY for explicit provider terminal failure status
   (e.g. FAILED, DENIED, REJECTED, VOIDED, CANCELED, CANCELLED, EXPIRED, DECLINED).
3. Everything else (unknown strings, lookup errors, timeouts, 408, 429, 5xx, network errors, empty values) returns HOLD.
"""

from enum import Enum


class MoneyOutcome(str, Enum):
    """Explicit financial outcome for a budget reservation."""

    HOLD = "HOLD"
    SETTLE = "SETTLE"
    RELEASE = "RELEASE"


EXPLICIT_COMPLETED_STATUSES: frozenset[str] = frozenset({"COMPLETED", "SUCCESS"})

EXPLICIT_TERMINAL_FAILURE_STATUSES: frozenset[str] = frozenset(
    {
        "FAILED",
        "DENIED",
        "REJECTED",
        "VOIDED",
        "CANCELED",
        "CANCELLED",
        "EXPIRED",
        "DECLINED",
    }
)

TRANSIENT_OR_AMBIGUOUS_STATUSES: frozenset[str] = frozenset(
    {
        "RECONCILE",
        "LOOKUP_FAILED",
        "TIMEOUT",
        "NETWORK_ERROR",
        "CONNECTION_ERROR",
        "ERROR",
        "UNKNOWN",
    }
)


def money_outcome(
    source: str,
    provider_status: str | None,
    *,
    business_rejection: bool | None = None,
) -> MoneyOutcome:
    """Pure domain function deciding the financial money outcome for a payment intent.

    Args:
        source: Site or origin of the event (e.g. 'authorize', 'capture_order',
                'reconcile', 'resolve_needs_review', 'webhook')
        provider_status: Raw provider status string from the payment rail or lookup
        business_rejection: Whether provider explicitly returned a business terminal rejection.
                            If explicitly False, release is rejected and HOLD is returned.

    Returns:
        MoneyOutcome.SETTLE: Confirmed settlement; budget confirmed spent.
        MoneyOutcome.RELEASE: Confirmed terminal business rejection; reserved funds returned to budget.
        MoneyOutcome.HOLD: Ambiguous, timeout, transient error, network failure, or unknown;
                           funds remain strictly held.
    """
    _ = source
    if provider_status is None:
        return MoneyOutcome.HOLD

    status_norm = str(provider_status).strip().upper()

    if status_norm in EXPLICIT_COMPLETED_STATUSES:
        return MoneyOutcome.SETTLE

    # A token failure, 5xx, 408, 429, or LOOKUP_FAILED is NEVER a business rejection
    if status_norm in TRANSIENT_OR_AMBIGUOUS_STATUSES:
        return MoneyOutcome.HOLD

    # If explicitly marked as NOT a business rejection, fail closed and hold
    if business_rejection is False:
        return MoneyOutcome.HOLD

    if business_rejection is True or status_norm in EXPLICIT_TERMINAL_FAILURE_STATUSES:
        return MoneyOutcome.RELEASE

    return MoneyOutcome.HOLD
