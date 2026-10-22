"""Comprehensive unit tests for the deterministic pure policy engine.

Includes:
- Table-driven tests per individual rule
- Table-driven tests per precedence pair (Rules 1 through 10)
- Boundary value analysis (cap - 1, cap, cap + 1 minor units)
- Advisory escalation guard function matrix
- Hypothesis property test: 'a failed hard constraint is never ALLOW'
- Request lifecycle state machine allowable and forbidden transition tests (Gate 56.17)
"""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.mandates import Mandate, MandateStatus
from app.domain.models import (
    DecisionOutcome,
    Money,
    TransactionIntent,
    guard_advisory_escalation,
)
from app.domain.policy import (
    PolicyReasonCode,
    PolicyState,
    evaluate,
)
from app.domain.state_machine import (
    InvalidStateTransitionError,
    RequestState,
    can_transition,
    transition_request_state,
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


# ---------------------------------------------------------------------------
# 1. Table-driven tests per individual rule
# ---------------------------------------------------------------------------


def test_rule_1_idempotency_replay_returns_cached_decision(
    baseline_mandate: Mandate,
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    state = PolicyState(
        lifetime_spent_minor=0,
        rolling_24h_spent_minor=0,
        idempotency_records={"tx-idem-1": ("digest_abc", DecisionOutcome.STEP_UP)},
    )
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-idem-1",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, state, now, intent_digest="digest_abc")
    assert decision.outcome == DecisionOutcome.STEP_UP
    assert PolicyReasonCode.IDEMPOTENCY_REPLAY in decision.reason_codes


def test_rule_1_idempotency_mismatch_denies(baseline_mandate: Mandate) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    state = PolicyState(
        lifetime_spent_minor=0,
        rolling_24h_spent_minor=0,
        idempotency_records={"tx-idem-2": ("original_digest", DecisionOutcome.ALLOW)},
    )
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-idem-2",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, state, now, intent_digest="tampered_digest")
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.IDEMPOTENCY_MISMATCH in decision.reason_codes


def test_rule_2_mandate_inactive_denies(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    revoked_mandate = baseline_mandate.revoke()
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-r2",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, revoked_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.MANDATE_INACTIVE in decision.reason_codes


def test_rule_3_mandate_premature_denies(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = baseline_mandate.valid_from_utc - timedelta(days=2)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-r3-premature",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.MANDATE_NOT_YET_VALID in decision.reason_codes


def test_rule_3_mandate_expired_denies(baseline_mandate: Mandate, empty_state: PolicyState) -> None:
    now = baseline_mandate.valid_until_utc + timedelta(days=2)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-r3-expired",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.MANDATE_EXPIRED in decision.reason_codes


def test_rule_4_currency_mismatch_denies(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="EUR"),
        purpose="Hosting",
        idempotency_key="tx-r4",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.CURRENCY_MISMATCH in decision.reason_codes


def test_rule_5_payee_unauthorized_denies(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="rogue_payee",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-r5",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.PAYEE_UNAUTHORIZED in decision.reason_codes


def test_rule_6_purpose_unauthorized_denies(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="CryptocurrencySpeculation",
        idempotency_key="tx-r6",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.PURPOSE_UNAUTHORIZED in decision.reason_codes


def test_rule_7_invoice_reference_required_denies_when_missing(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    mandate_with_invoice = baseline_mandate.model_copy(update={"require_invoice_reference": True})

    # Missing invoice reference
    intent_missing = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-r7-missing",
        occurred_at_utc=now,
        invoice_reference=None,
    )
    decision_missing = evaluate(intent_missing, mandate_with_invoice, empty_state, now)
    assert decision_missing.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.INVOICE_REFERENCE_REQUIRED in decision_missing.reason_codes

    # Present invoice reference succeeds
    intent_present = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-r7-present",
        occurred_at_utc=now,
        invoice_reference="INV-2026-001",
    )
    decision_present = evaluate(intent_present, mandate_with_invoice, empty_state, now)
    assert decision_present.outcome == DecisionOutcome.ALLOW


def test_rule_8_lifetime_budget_exceeded_denies(baseline_mandate: Mandate) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    state = PolicyState(
        lifetime_spent_minor=495_000,
        rolling_24h_spent_minor=495_000,
        idempotency_records={},
    )
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=10_000, currency="USD"),  # 495k + 10k = 505k > 500k
        purpose="Hosting",
        idempotency_key="tx-r8",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.LIFETIME_BUDGET_EXCEEDED in decision.reason_codes


def test_rule_9_single_limit_exceeded_denies(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=100_001, currency="USD"),  # 100,001 > 100,000 cap
        purpose="Hosting",
        idempotency_key="tx-r9",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.SINGLE_LIMIT_EXCEEDED in decision.reason_codes


def test_rule_10_instant_threshold_exceeded_steps_up(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=20_001, currency="USD"),  # 20,001 > 20,000 threshold
        purpose="Hosting",
        idempotency_key="tx-r10",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.STEP_UP
    assert PolicyReasonCode.INSTANT_THRESHOLD_EXCEEDED in decision.reason_codes


# ---------------------------------------------------------------------------
# 2. Table-driven tests per precedence pair
# ---------------------------------------------------------------------------


def test_precedence_rule1_over_rule2(baseline_mandate: Mandate) -> None:
    """Rule 1 (Idempotency Mismatch) takes precedence over Rule 2 (Mandate Inactive)."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    revoked = baseline_mandate.revoke()
    state = PolicyState(
        lifetime_spent_minor=0,
        rolling_24h_spent_minor=0,
        idempotency_records={"idem-pair-1": ("digest_original", DecisionOutcome.ALLOW)},
    )
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="idem-pair-1",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, revoked, state, now, intent_digest="tampered_digest")
    assert decision.outcome == DecisionOutcome.DENY
    assert decision.reason_codes == (PolicyReasonCode.IDEMPOTENCY_MISMATCH,)


def test_precedence_rule2_over_rule3(baseline_mandate: Mandate, empty_state: PolicyState) -> None:
    """Rule 2 (Mandate Inactive) takes precedence over Rule 3 (Expired)."""
    revoked = baseline_mandate.revoke()
    expired_time = baseline_mandate.valid_until_utc + timedelta(days=10)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="pair-2-3",
        occurred_at_utc=expired_time,
    )
    decision = evaluate(intent, revoked, empty_state, expired_time)
    assert decision.reason_codes == (PolicyReasonCode.MANDATE_INACTIVE,)


def test_precedence_rule3_over_rule4(baseline_mandate: Mandate, empty_state: PolicyState) -> None:
    """Rule 3 (Expired) takes precedence over Rule 4 (Currency Mismatch)."""
    expired_time = baseline_mandate.valid_until_utc + timedelta(days=5)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="EUR"),  # Currency mismatch + expired
        purpose="Hosting",
        idempotency_key="pair-3-4",
        occurred_at_utc=expired_time,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, expired_time)
    assert decision.reason_codes == (PolicyReasonCode.MANDATE_EXPIRED,)


def test_precedence_rule4_over_rule5(baseline_mandate: Mandate, empty_state: PolicyState) -> None:
    """Rule 4 (Currency Mismatch) takes precedence over Rule 5 (Payee Unauthorized)."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="unauthorized_payee",
        money=Money(amount_minor=1000, currency="GBP"),
        purpose="Hosting",
        idempotency_key="pair-4-5",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.reason_codes == (PolicyReasonCode.CURRENCY_MISMATCH,)


def test_precedence_rule5_over_rule6(baseline_mandate: Mandate, empty_state: PolicyState) -> None:
    """Rule 5 (Payee Unauthorized) takes precedence over Rule 6 (Purpose Unauthorized)."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="unauthorized_payee",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="UnauthorizedPurpose",
        idempotency_key="pair-5-6",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.reason_codes == (PolicyReasonCode.PAYEE_UNAUTHORIZED,)


def test_precedence_rule6_over_rule7(baseline_mandate: Mandate, empty_state: PolicyState) -> None:
    """Rule 6 (Purpose Unauthorized) takes precedence over Rule 7 (Invoice Missing)."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    mandate_req_inv = baseline_mandate.model_copy(update={"require_invoice_reference": True})
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="ForbiddenPurpose",
        idempotency_key="pair-6-7",
        occurred_at_utc=now,
        invoice_reference=None,  # missing invoice too
    )
    decision = evaluate(intent, mandate_req_inv, empty_state, now)
    assert decision.reason_codes == (PolicyReasonCode.PURPOSE_UNAUTHORIZED,)


def test_precedence_rule7_over_rule8(baseline_mandate: Mandate) -> None:
    """Rule 7 (Invoice Missing) takes precedence over Rule 8 (Lifetime Budget Exceeded)."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    mandate_req_inv = baseline_mandate.model_copy(update={"require_invoice_reference": True})
    state = PolicyState(
        lifetime_spent_minor=500_000,
        rolling_24h_spent_minor=500_000,
        idempotency_records={},
    )
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="pair-7-8",
        occurred_at_utc=now,
        invoice_reference=None,
    )
    decision = evaluate(intent, mandate_req_inv, state, now)
    assert decision.reason_codes == (PolicyReasonCode.INVOICE_REFERENCE_REQUIRED,)


def test_precedence_rule8_over_rule9(baseline_mandate: Mandate) -> None:
    """Rule 8 (Lifetime Budget Exceeded) takes precedence over Rule 9 (Single Limit)."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    state = PolicyState(
        lifetime_spent_minor=450_000,  # budget is 500,000
        rolling_24h_spent_minor=450_000,
        idempotency_records={},
    )
    # Requesting 150,000 (exceeds single limit 100,000 AND lifetime budget 450k + 150k > 500k)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=150_000, currency="USD"),
        purpose="Hosting",
        idempotency_key="pair-8-9",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, state, now)
    assert decision.reason_codes == (PolicyReasonCode.LIFETIME_BUDGET_EXCEEDED,)


def test_precedence_rule9_over_rule10(baseline_mandate: Mandate, empty_state: PolicyState) -> None:
    """Rule 9 (Single Limit Exceeded) produces DENY instead of STEP_UP from Rule 10."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    # 150,000 is > instant_threshold (20,000) and > single_limit (100,000)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=150_000, currency="USD"),
        purpose="Hosting",
        idempotency_key="pair-9-10",
        occurred_at_utc=now,
    )
    decision = evaluate(intent, baseline_mandate, empty_state, now)
    assert decision.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.SINGLE_LIMIT_EXCEEDED in decision.reason_codes


# ---------------------------------------------------------------------------
# 3. Boundary Value Analysis (cap - 1, cap, cap + 1 minor units)
# ---------------------------------------------------------------------------


def test_boundary_instant_threshold(baseline_mandate: Mandate, empty_state: PolicyState) -> None:
    """Boundary test around instant threshold ($200.00 = 20,000 minor units)."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    thresh = baseline_mandate.instant_threshold_minor

    # Threshold - 1 minor unit ($199.99) -> ALLOW
    d_under = evaluate(
        TransactionIntent(
            agent_id="agent_1",
            recipient_id="vendor_paypal_1",
            money=Money(amount_minor=thresh - 1, currency="USD"),
            purpose="Hosting",
            idempotency_key="b-under",
            occurred_at_utc=now,
        ),
        baseline_mandate,
        empty_state,
        now,
    )
    assert d_under.outcome == DecisionOutcome.ALLOW
    assert PolicyReasonCode.PRE_AUTHORIZED in d_under.reason_codes

    # Exact threshold ($200.00) -> ALLOW (rule: amount > threshold triggers step-up)
    d_exact = evaluate(
        TransactionIntent(
            agent_id="agent_1",
            recipient_id="vendor_paypal_1",
            money=Money(amount_minor=thresh, currency="USD"),
            purpose="Hosting",
            idempotency_key="b-exact",
            occurred_at_utc=now,
        ),
        baseline_mandate,
        empty_state,
        now,
    )
    assert d_exact.outcome == DecisionOutcome.ALLOW
    assert PolicyReasonCode.PRE_AUTHORIZED in d_exact.reason_codes

    # Threshold + 1 minor unit ($200.01) -> STEP_UP
    d_over = evaluate(
        TransactionIntent(
            agent_id="agent_1",
            recipient_id="vendor_paypal_1",
            money=Money(amount_minor=thresh + 1, currency="USD"),
            purpose="Hosting",
            idempotency_key="b-over",
            occurred_at_utc=now,
        ),
        baseline_mandate,
        empty_state,
        now,
    )
    assert d_over.outcome == DecisionOutcome.STEP_UP
    assert PolicyReasonCode.INSTANT_THRESHOLD_EXCEEDED in d_over.reason_codes


def test_boundary_single_limit(baseline_mandate: Mandate, empty_state: PolicyState) -> None:
    """Boundary test around single limit cap ($1,000.00 = 100,000 minor units)."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    cap = baseline_mandate.single_limit_minor

    # Cap - 1 ($999.99) -> STEP_UP
    d_under = evaluate(
        TransactionIntent(
            agent_id="agent_1",
            recipient_id="vendor_paypal_1",
            money=Money(amount_minor=cap - 1, currency="USD"),
            purpose="Hosting",
            idempotency_key="b-cap-under",
            occurred_at_utc=now,
        ),
        baseline_mandate,
        empty_state,
        now,
    )
    assert d_under.outcome == DecisionOutcome.STEP_UP

    # Exact cap ($1,000.00) -> STEP_UP
    d_exact = evaluate(
        TransactionIntent(
            agent_id="agent_1",
            recipient_id="vendor_paypal_1",
            money=Money(amount_minor=cap, currency="USD"),
            purpose="Hosting",
            idempotency_key="b-cap-exact",
            occurred_at_utc=now,
        ),
        baseline_mandate,
        empty_state,
        now,
    )
    assert d_exact.outcome == DecisionOutcome.STEP_UP

    # Cap + 1 ($1,000.01) -> DENY
    d_over = evaluate(
        TransactionIntent(
            agent_id="agent_1",
            recipient_id="vendor_paypal_1",
            money=Money(amount_minor=cap + 1, currency="USD"),
            purpose="Hosting",
            idempotency_key="b-cap-over",
            occurred_at_utc=now,
        ),
        baseline_mandate,
        empty_state,
        now,
    )
    assert d_over.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.SINGLE_LIMIT_EXCEEDED in d_over.reason_codes


def test_boundary_lifetime_budget(baseline_mandate: Mandate) -> None:
    """Boundary test around lifetime budget cap ($5,000.00 = 500,000 minor units)."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    spent = 490_000
    state = PolicyState(
        lifetime_spent_minor=spent,
        rolling_24h_spent_minor=spent,
        idempotency_records={},
    )
    remaining = baseline_mandate.lifetime_budget_minor - spent  # 10,000 remaining

    # Remaining - 1 minor unit (9,999) -> within budget -> ALLOW
    d_under = evaluate(
        TransactionIntent(
            agent_id="agent_1",
            recipient_id="vendor_paypal_1",
            money=Money(amount_minor=remaining - 1, currency="USD"),
            purpose="Hosting",
            idempotency_key="b-life-under",
            occurred_at_utc=now,
        ),
        baseline_mandate,
        state,
        now,
    )
    assert d_under.outcome == DecisionOutcome.ALLOW

    # Exact remaining (10,000) -> exactly fills budget -> ALLOW
    d_exact = evaluate(
        TransactionIntent(
            agent_id="agent_1",
            recipient_id="vendor_paypal_1",
            money=Money(amount_minor=remaining, currency="USD"),
            purpose="Hosting",
            idempotency_key="b-life-exact",
            occurred_at_utc=now,
        ),
        baseline_mandate,
        state,
        now,
    )
    assert d_exact.outcome == DecisionOutcome.ALLOW

    # Remaining + 1 minor unit (10,001) -> exceeds budget -> DENY
    d_over = evaluate(
        TransactionIntent(
            agent_id="agent_1",
            recipient_id="vendor_paypal_1",
            money=Money(amount_minor=remaining + 1, currency="USD"),
            purpose="Hosting",
            idempotency_key="b-life-over",
            occurred_at_utc=now,
        ),
        baseline_mandate,
        state,
        now,
    )
    assert d_over.outcome == DecisionOutcome.DENY
    assert PolicyReasonCode.LIFETIME_BUDGET_EXCEEDED in d_over.reason_codes


# ---------------------------------------------------------------------------
# 4. Advisory Escalation Guard Matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base", "advisory", "expected"),
    [
        (DecisionOutcome.ALLOW, None, DecisionOutcome.ALLOW),
        (DecisionOutcome.ALLOW, DecisionOutcome.ALLOW, DecisionOutcome.ALLOW),
        (DecisionOutcome.ALLOW, DecisionOutcome.STEP_UP, DecisionOutcome.STEP_UP),
        (DecisionOutcome.ALLOW, DecisionOutcome.DENY, DecisionOutcome.DENY),
        (DecisionOutcome.STEP_UP, None, DecisionOutcome.STEP_UP),
        (DecisionOutcome.STEP_UP, DecisionOutcome.ALLOW, DecisionOutcome.STEP_UP),  # No softening!
        (DecisionOutcome.STEP_UP, DecisionOutcome.STEP_UP, DecisionOutcome.STEP_UP),
        (DecisionOutcome.STEP_UP, DecisionOutcome.DENY, DecisionOutcome.DENY),
        (DecisionOutcome.DENY, None, DecisionOutcome.DENY),
        (DecisionOutcome.DENY, DecisionOutcome.ALLOW, DecisionOutcome.DENY),  # No softening!
        (DecisionOutcome.DENY, DecisionOutcome.STEP_UP, DecisionOutcome.DENY),  # No softening!
        (DecisionOutcome.DENY, DecisionOutcome.DENY, DecisionOutcome.DENY),
    ],
)
def test_advisory_escalation_guard_matrix(
    base: DecisionOutcome,
    advisory: DecisionOutcome | None,
    expected: DecisionOutcome,
) -> None:
    """Verify complete guard function matrix: signals can only raise severity, never soften."""
    assert guard_advisory_escalation(base, advisory) == expected


# ---------------------------------------------------------------------------
# 5. Hypothesis Property: A failed hard constraint is never ALLOW
# ---------------------------------------------------------------------------


@given(
    amount=st.integers(min_value=1, max_value=2_000_000),
    currency=st.sampled_from(["USD", "EUR", "GBP", "JPY"]),
    payee=st.sampled_from(["vendor_paypal_1", "rogue_wallet_x", "unknown_merchant"]),
    purpose=st.sampled_from(["Hosting", "Subscription", "UnauthorizedCategory", "Fraud"]),
    already_spent=st.integers(min_value=0, max_value=600_000),
    advisory=st.sampled_from(
        [None, DecisionOutcome.ALLOW, DecisionOutcome.STEP_UP, DecisionOutcome.DENY]
    ),
)
def test_hypothesis_failed_hard_constraint_is_never_allow(
    amount: int,
    currency: str,
    payee: str,
    purpose: str,
    already_spent: int,
    advisory: DecisionOutcome | None,
) -> None:
    """Hypothesis Property: Whenever any hard constraint is breached, outcome is NEVER ALLOW."""
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    mandate = Mandate(
        mandate_id="mandate_prop",
        version=1,
        principal_id="principal_1",
        agent_id="agent_1",
        single_limit_minor=100_000,  # $1,000
        instant_threshold_minor=20_000,  # $200
        lifetime_budget_minor=500_000,  # $5,000
        currency="USD",
        allowed_payees=("vendor_paypal_1",),
        allowed_purposes=("Hosting", "Subscription"),
        valid_from_utc=now - timedelta(days=1),
        valid_until_utc=now + timedelta(days=30),
        status=MandateStatus.ACTIVE,
        key_id="key_test_123",
        signature="fake_sig_123",
    )
    state = PolicyState(
        lifetime_spent_minor=already_spent,
        rolling_24h_spent_minor=already_spent,
        idempotency_records={},
    )
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id=payee,
        money=Money(amount_minor=amount, currency=currency),
        purpose=purpose,
        idempotency_key="prop-tx-001",
        occurred_at_utc=now,
    )

    decision = evaluate(intent, mandate, state, now, advisory_signal=advisory)

    hard_constraint_failed = (
        currency != "USD"
        or payee not in mandate.allowed_payees
        or purpose not in mandate.allowed_purposes
        or (already_spent + amount > mandate.lifetime_budget_minor)
        or (amount > mandate.single_limit_minor)
        or (advisory in (DecisionOutcome.STEP_UP, DecisionOutcome.DENY))
    )

    if hard_constraint_failed:
        assert decision.outcome != DecisionOutcome.ALLOW


# ---------------------------------------------------------------------------
# 6. Request Lifecycle State Machine Tests (Gate 56.17)
# ---------------------------------------------------------------------------


def test_state_machine_valid_autonomous_flow() -> None:
    """Test valid lifecycle flow for autonomous pre-authorized payment."""
    s = RequestState.RECEIVED
    s = transition_request_state(s, RequestState.EVALUATING)
    s = transition_request_state(s, RequestState.AUTHORIZED)
    s = transition_request_state(s, RequestState.EXECUTING)
    s = transition_request_state(s, RequestState.SETTLED)
    s = transition_request_state(s, RequestState.CLOSED)
    assert s.is_terminal is True


def test_state_machine_valid_human_step_up_flow() -> None:
    """Test valid lifecycle flow for human step-up review and approval."""
    s = RequestState.RECEIVED
    s = transition_request_state(s, RequestState.EVALUATING)
    s = transition_request_state(s, RequestState.PENDING_APPROVAL)
    s = transition_request_state(s, RequestState.APPROVED)
    s = transition_request_state(s, RequestState.AUTHORIZED)
    s = transition_request_state(s, RequestState.EXECUTING)
    s = transition_request_state(s, RequestState.SETTLED)
    s = transition_request_state(s, RequestState.CLOSED)
    assert s.is_terminal is True


def test_state_machine_valid_human_rejection_flow() -> None:
    """Test valid lifecycle flow for human step-up rejection."""
    s = RequestState.RECEIVED
    s = transition_request_state(s, RequestState.EVALUATING)
    s = transition_request_state(s, RequestState.PENDING_APPROVAL)
    s = transition_request_state(s, RequestState.REJECTED)
    s = transition_request_state(s, RequestState.CLOSED)
    assert s.is_terminal is True


def test_state_machine_valid_hard_denial_flow() -> None:
    """Test valid lifecycle flow for policy hard denial."""
    s = RequestState.RECEIVED
    s = transition_request_state(s, RequestState.EVALUATING)
    s = transition_request_state(s, RequestState.DENIED)
    s = transition_request_state(s, RequestState.CLOSED)
    assert s.is_terminal is True


@pytest.mark.parametrize(
    ("current", "illegal_target"),
    [
        (RequestState.CLOSED, RequestState.RECEIVED),  # Cannot reopen terminal state
        (RequestState.CLOSED, RequestState.EVALUATING),
        (RequestState.DENIED, RequestState.AUTHORIZED),  # Cannot resurrect denied request
        (RequestState.DENIED, RequestState.EXECUTING),
        (RequestState.SETTLED, RequestState.PENDING_APPROVAL),  # Cannot step up settled payment
        (RequestState.EXECUTING, RequestState.PENDING_APPROVAL),
        (RequestState.RECEIVED, RequestState.SETTLED),  # Cannot skip evaluation/authorization
        (RequestState.PENDING_APPROVAL, RequestState.EXECUTING),  # Must approve before executing
    ],
)
def test_state_machine_rejects_invalid_transitions(
    current: RequestState,
    illegal_target: RequestState,
) -> None:
    """Verify state machine strictly rejects illegal state transition paths."""
    assert can_transition(current, illegal_target) is False
    with pytest.raises(InvalidStateTransitionError, match="Invalid request lifecycle transition"):
        transition_request_state(current, illegal_target)


def test_policy_escalation_in_evaluation(
    baseline_mandate: Mandate, empty_state: PolicyState
) -> None:
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_paypal_1",
        money=Money(amount_minor=1000, currency="USD"),
        purpose="Hosting",
        idempotency_key="tx-esc-test",
        occurred_at_utc=now,
    )
    # Base decision is ALLOW; advisory signal escalates to STEP_UP
    decision = evaluate(
        intent,
        baseline_mandate,
        empty_state,
        now,
        advisory_signal=DecisionOutcome.STEP_UP,
    )
    assert decision.outcome == DecisionOutcome.STEP_UP
    assert decision.escalated_from == DecisionOutcome.ALLOW
    assert PolicyReasonCode.RISK_ESCALATED in decision.reason_codes
