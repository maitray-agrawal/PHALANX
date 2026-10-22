"""Unit tests for pure domain models and rules."""

from datetime import datetime

import pytest

from app.domain.models import (
    DecisionOutcome,
    Money,
    TransactionIntent,
    escalate_decision,
)


def test_money_valid_construction() -> None:
    m = Money(amount_minor=1050, currency="USD")
    assert m.amount_minor == 1050
    assert m.currency == "USD"


def test_money_negative_amount_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        Money(amount_minor=-100, currency="USD")


def test_money_invalid_currency_rejected() -> None:
    with pytest.raises(ValueError, match="3-letter uppercase"):
        Money(amount_minor=100, currency="usd")
    with pytest.raises(ValueError, match="3-letter uppercase"):
        Money(amount_minor=100, currency="US")


def test_money_addition() -> None:
    m1 = Money(amount_minor=500, currency="USD")
    m2 = Money(amount_minor=750, currency="USD")
    total = m1.add(m2)
    assert total.amount_minor == 1250
    assert total.currency == "USD"


def test_money_addition_mismatched_currency_fails() -> None:
    m1 = Money(amount_minor=500, currency="USD")
    m2 = Money(amount_minor=500, currency="EUR")
    with pytest.raises(ValueError, match="Cannot add different currencies"):
        m1.add(m2)


def test_transaction_intent_requires_utc_timezone() -> None:
    naive_dt = datetime(2026, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        TransactionIntent(
            agent_id="agent-01",
            recipient_id="merchant-99",
            money=Money(amount_minor=100, currency="USD"),
            purpose="API payment",
            idempotency_key="key-123",
            occurred_at_utc=naive_dt,
        )


def test_escalation_rules() -> None:
    # Anomaly signal can raise severity:
    assert (
        escalate_decision(DecisionOutcome.ALLOW, DecisionOutcome.STEP_UP) == DecisionOutcome.STEP_UP
    )
    assert escalate_decision(DecisionOutcome.ALLOW, DecisionOutcome.DENY) == DecisionOutcome.DENY
    assert escalate_decision(DecisionOutcome.STEP_UP, DecisionOutcome.DENY) == DecisionOutcome.DENY

    # Anomaly signal can NEVER lower severity:
    assert escalate_decision(DecisionOutcome.DENY, DecisionOutcome.ALLOW) == DecisionOutcome.DENY
    assert escalate_decision(DecisionOutcome.DENY, DecisionOutcome.STEP_UP) == DecisionOutcome.DENY
    assert (
        escalate_decision(DecisionOutcome.STEP_UP, DecisionOutcome.ALLOW) == DecisionOutcome.STEP_UP
    )

    # None signal preserves base decision:
    assert escalate_decision(DecisionOutcome.ALLOW, None) == DecisionOutcome.ALLOW
    assert escalate_decision(DecisionOutcome.STEP_UP, None) == DecisionOutcome.STEP_UP
    assert escalate_decision(DecisionOutcome.DENY, None) == DecisionOutcome.DENY


def test_transaction_intent_validations() -> None:
    from datetime import UTC

    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    money = Money(amount_minor=100, currency="USD")

    with pytest.raises(ValueError, match="agent_id cannot be blank"):
        TransactionIntent(
            agent_id="   ",
            recipient_id="recip",
            money=money,
            purpose="test",
            idempotency_key="key",
            occurred_at_utc=now,
        )

    with pytest.raises(ValueError, match="recipient_id cannot be blank"):
        TransactionIntent(
            agent_id="agent",
            recipient_id="",
            money=money,
            purpose="test",
            idempotency_key="key",
            occurred_at_utc=now,
        )

    with pytest.raises(ValueError, match="idempotency_key cannot be blank"):
        TransactionIntent(
            agent_id="agent",
            recipient_id="recip",
            money=money,
            purpose="test",
            idempotency_key="",
            occurred_at_utc=now,
        )

    with pytest.raises(ValueError, match="whitespace-only"):
        TransactionIntent(
            agent_id="agent",
            recipient_id="recip",
            money=money,
            purpose="test",
            idempotency_key="key",
            occurred_at_utc=now,
            invoice_reference="   ",
        )


def test_mandate_model_invariants_and_signable() -> None:
    from datetime import UTC, timedelta

    from app.domain.canonical_json import canonical_digest
    from app.domain.mandates import Mandate
    from app.domain.models import PolicyEvaluationResult
    from app.domain.state_machine import InvalidStateTransitionError, RequestState

    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
    naive = datetime(2026, 10, 22, 12, 0, 0)

    # Naive timezone rejected
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        Mandate(
            mandate_id="m1",
            version=1,
            principal_id="p",
            agent_id="a",
            single_limit_minor=100,
            instant_threshold_minor=50,
            lifetime_budget_minor=500,
            currency="USD",
            valid_from_utc=naive,
            valid_until_utc=now,
            key_id="k",
        )

    # Threshold > single limit rejected
    with pytest.raises(
        ValueError, match="instant_threshold_minor cannot exceed single_limit_minor"
    ):
        Mandate(
            mandate_id="m2",
            version=1,
            principal_id="p",
            agent_id="a",
            single_limit_minor=100,
            instant_threshold_minor=200,
            lifetime_budget_minor=500,
            currency="USD",
            valid_from_utc=now,
            valid_until_utc=now + timedelta(days=1),
            key_id="k",
        )

    # Lifetime budget < single limit rejected
    with pytest.raises(ValueError, match="lifetime_budget_minor cannot be less than"):
        Mandate(
            mandate_id="m3",
            version=1,
            principal_id="p",
            agent_id="a",
            single_limit_minor=200,
            instant_threshold_minor=50,
            lifetime_budget_minor=100,
            currency="USD",
            valid_from_utc=now,
            valid_until_utc=now + timedelta(days=1),
            key_id="k",
        )

    # valid_until <= valid_from rejected
    with pytest.raises(ValueError, match="strictly after"):
        Mandate(
            mandate_id="m4",
            version=1,
            principal_id="p",
            agent_id="a",
            single_limit_minor=100,
            instant_threshold_minor=50,
            lifetime_budget_minor=500,
            currency="USD",
            valid_from_utc=now,
            valid_until_utc=now,
            key_id="k",
        )

    # Mandate with require_invoice_reference=True
    m_inv = Mandate(
        mandate_id="m5",
        version=1,
        principal_id="p",
        agent_id="a",
        single_limit_minor=100,
        instant_threshold_minor=50,
        lifetime_budget_minor=500,
        currency="USD",
        valid_from_utc=now,
        valid_until_utc=now + timedelta(days=1),
        key_id="k",
        require_invoice_reference=True,
    )
    d = m_inv.to_signable_dict()
    assert d["require_invoice_reference"] is True

    # Canonical digest test
    digest = canonical_digest({"b": 2, "a": 1})
    assert len(digest) == 64

    # InvalidStateTransitionError with custom reason string
    err = InvalidStateTransitionError(
        RequestState.CLOSED, RequestState.RECEIVED, reason="custom rejection reason"
    )
    assert "custom rejection reason" in str(err)

    # PolicyEvaluationResult
    res = PolicyEvaluationResult(
        outcome=DecisionOutcome.ALLOW,
        reasons=("pre-approved",),
        escalated_from=None,
    )
    assert res.outcome == DecisionOutcome.ALLOW
