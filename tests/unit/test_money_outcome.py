"""Tests for pure domain money_outcome decision function (Production Gate 56.17 / T2c).

Verifies:
1. SETTLE returned only for explicit completed statuses (COMPLETED, SUCCESS).
2. RELEASE returned only for explicit terminal failure statuses
   (FAILED, DENIED, REJECTED, VOIDED, CANCELED, CANCELLED, EXPIRED, DECLINED).
3. HOLD returned for all ambiguous, transient, network, timeout, or unknown statuses.
4. Hypothesis property: Any arbitrary string outside the explicit sets returns HOLD.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.money_outcome import (
    EXPLICIT_COMPLETED_STATUSES,
    EXPLICIT_TERMINAL_FAILURE_STATUSES,
    MoneyOutcome,
    money_outcome,
)

SOURCES = ["authorize", "capture_order", "reconcile", "resolve_needs_review", "webhook"]


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("status", ["COMPLETED", "completed", "SUCCESS", "success"])
def test_explicit_completed_statuses_return_settle(source: str, status: str) -> None:
    """Explicit completed statuses must return SETTLE regardless of source."""
    assert money_outcome(source, status) == MoneyOutcome.SETTLE


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize(
    "status",
    [
        "FAILED",
        "failed",
        "DENIED",
        "denied",
        "REJECTED",
        "rejected",
        "VOIDED",
        "voided",
        "CANCELED",
        "canceled",
        "CANCELLED",
        "cancelled",
        "EXPIRED",
        "expired",
        "DECLINED",
        "declined",
    ],
)
def test_explicit_terminal_failure_statuses_return_release(source: str, status: str) -> None:
    """Explicit documented terminal failure statuses return RELEASE."""
    assert money_outcome(source, status) == MoneyOutcome.RELEASE


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize(
    "status",
    [
        "RECONCILE",
        "LOOKUP_FAILED",
        "TIMEOUT",
        "NETWORK_ERROR",
        "CONNECTION_ERROR",
        "ERROR",
        "UNKNOWN",
        "PENDING",
        "PROCESSING",
        "CREATED",
        "SAVED",
        "PAYER_ACTION_REQUIRED",
        "500",
        "503",
        "408",
        "429",
        "",
        "   ",
        None,
    ],
)
def test_ambiguous_and_transient_statuses_return_hold(source: str, status: str | None) -> None:
    """Any ambiguous, transient, error, or empty status must return HOLD."""
    assert money_outcome(source, status) == MoneyOutcome.HOLD


def test_business_rejection_overrides_non_transient() -> None:
    """Explicit business rejection flag releases unless status is transient error."""
    assert (
        money_outcome("reconcile", "CUSTOM_DENIAL", business_rejection=True) == MoneyOutcome.RELEASE
    )
    # Even with business_rejection=True, transient lookup errors MUST remain HOLD
    assert money_outcome("reconcile", "LOOKUP_FAILED", business_rejection=True) == MoneyOutcome.HOLD
    assert money_outcome("reconcile", "RECONCILE", business_rejection=True) == MoneyOutcome.HOLD
    assert money_outcome("reconcile", "TIMEOUT", business_rejection=True) == MoneyOutcome.HOLD


@given(
    source=st.text(min_size=1, max_size=30),
    status=st.text(min_size=0, max_size=50).filter(
        lambda s: s.strip().upper() not in EXPLICIT_COMPLETED_STATUSES
        and s.strip().upper() not in EXPLICIT_TERMINAL_FAILURE_STATUSES
    ),
)
def test_hypothesis_arbitrary_status_outside_explicit_sets_always_returns_hold(
    source: str, status: str
) -> None:
    """Hypothesis property: ANY status outside explicit sets strictly returns HOLD."""
    assert money_outcome(source, status) == MoneyOutcome.HOLD
