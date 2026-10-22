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
