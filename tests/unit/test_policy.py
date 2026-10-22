"""Unit tests for the deterministic pure policy engine."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.mandates import Mandate, MandateStatus
from app.domain.models import (
    DecisionOutcome,
    Money,
    TransactionIntent,
)
from app.domain.policy import (
    PolicyDecision,
    PolicyReasonCode,
    PolicyState,
    evaluate_policy,
)


@pytest.fixture
def baseline_mandate() -> Mandate:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    return Mandate(
        mandate_id="mandate_base",
        version=1,
        principal_id="principal_1",
        agent_id="agent_1",
        single_limit_minor=100_000,  # $1,000 max single
        instant_threshold_minor=20_000,  # $200 instant threshold
        lifetime_budget_minor=500_000,  # $5,000 lifetime budget
        currency="USD",
        allowed_payees=("vendor_paypal_1", "vendor_cloud_2"),
        allowed_purposes=("Hosting", "Subscription"),
        valid_from_utc=now - timedelta(days=1),
        valid_until_utc=now + timedelta(days=30),
        status=MandateStatus.ACTIVE,
        key_id="key_test_123",
        signature="fake_sig_123",
    )


@pytest.fixture
def empty_state() -> PolicyState:
    return PolicyState(
        lifetime_spent_minor=0,
        rolling_24h_spent_minor=0,
        idempotency_records={},
    )


def test_policy_allow_under_instant_threshold(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=15_000, currency="USD"),  # $150 <= $200
        purpose="Hosting",
        idempotency_key="tx-001",
        occurred_at_utc=now,
    )
    decision = evaluate_policy(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.ALLOW
    assert PolicyReasonCode.PRE_AUTHORIZED in decision.reason_codes


def test_policy_step_up_above_instant_threshold(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=50_000, currency="USD"),  # $500 > $200 but <= $1000
        purpose="Hosting",
        idempotency_key="tx-002",
        occurred_at_utc=now,
    )
    decision = evaluate_policy(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.STEP_UP
    assert PolicyReasonCode.INSTANT_THRESHOLD_EXCEEDED in decision.reason_codes


def test_policy_deny_above_single_limit(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=150_000, currency="USD"),  # $1,500 > $1000
        purpose="Hosting",
        idempotency_key="tx-003",
        occurred_at_utc=now,
    )
    decision = evaluate_policy(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.SINGLE_LIMIT_EXCEEDED in decision.reason_codes


def test_policy_deny_unauthorized_payee(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="attacker_unknown_wallet",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-004",
        occurred_at_utc=now,
    )
    decision = evaluate_policy(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.PAYEE_UNAUTHORIZED in decision.reason_codes


def test_policy_deny_unauthorized_purpose(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Gambling",
        idempotency_key="tx-005",
        occurred_at_utc=now,
    )
    decision = evaluate_policy(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.PURPOSE_UNAUTHORIZED in decision.reason_codes


def test_policy_deny_lifetime_budget_exceeded(baseline_mandate: Mandate) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    # Mandate cap is 500,000; already spent 490,000; requesting 15,000 -> 505,000 > cap
    state = PolicyState(
        lifetime_spent_minor=490_000,
        rolling_24h_spent_minor=490_000,
        idempotency_records={},
    )
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=15_000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-006",
        occurred_at_utc=now,
    )
    decision = evaluate_policy(intent, baseline_mandate, state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.LIFETIME_BUDGET_EXCEEDED in decision.reason_codes


def test_policy_asymmetric_escalation_only_raises(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=15_000, currency="USD"),  # base would be ALLOW
        purpose="Hosting",
        idempotency_key="tx-007",
        occurred_at_utc=now,
    )
    # Advisory signal recommends STEP_UP
    escalated = evaluate_policy(
        intent,
        baseline_mandate,
        empty_state,
        now,
        advisory_signal=DecisionOutcome.STEP_UP,
    )
    assert escalated.outcome == DecisionOutcome.STEP_UP
    assert escalated.escalated_from == DecisionOutcome.ALLOW

    # An advisory signal recommending ALLOW cannot downgrade a hard DENY
    deny_intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="unauthorized_vendor",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-008",
        occurred_at_utc=now,
    )
    cannot_downgrade: PolicyDecision = evaluate_policy(
        deny_intent,
        baseline_mandate,
        empty_state,
        now,
        advisory_signal=DecisionOutcome.ALLOW,
    )
    assert cannot_downgrade.outcome == DecisionOutcome.DENY
