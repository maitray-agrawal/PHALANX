"""Unit tests for PaymentRail protocol, FakePaymentRail, and PayPalPaymentRailAdapter."""

from datetime import UTC, datetime

from app.domain.models import Money, TransactionIntent
from app.domain.ports import PaymentRail
from app.infrastructure.paypal import FakePaymentRail, PayPalPaymentRailAdapter


def test_fake_payment_rail_records_dispatch() -> None:
    rail = FakePaymentRail(should_succeed=True)
    assert isinstance(rail, PaymentRail)

    intent = TransactionIntent(
        agent_id="agent-01",
        recipient_id="vendor-01",
        money=Money(amount_minor=5000, currency="USD"),
        purpose="Server subscription",
        idempotency_key="idemp-rail-001",
        occurred_at_utc=datetime.now(UTC),
    )

    res = rail.pay(intent)
    assert res.success is True
    assert res.transaction_id.startswith("sandbox_tx_")
    assert res.status == "COMPLETED"
    assert len(rail.dispatched_payments) == 1
    assert rail.dispatched_payments[0] == intent

    lookup_res = rail.lookup(res.transaction_id)
    assert lookup_res.success is True
    assert lookup_res.transaction_id == res.transaction_id


def test_fake_payment_rail_simulates_failure() -> None:
    rail = FakePaymentRail(should_succeed=False)
    intent = TransactionIntent(
        agent_id="agent-01",
        recipient_id="vendor-01",
        money=Money(amount_minor=5000, currency="USD"),
        purpose="Server subscription",
        idempotency_key="idemp-rail-002",
        occurred_at_utc=datetime.now(UTC),
    )
    res = rail.pay(intent)
    assert res.success is False
    assert res.status == "FAILED"
    assert "simulated_rail_failure" in rail.normalize_error(res.details)


def test_paypal_adapter_unconfigured_fallback() -> None:
    adapter = PayPalPaymentRailAdapter()
    assert isinstance(adapter, PaymentRail)

    intent = TransactionIntent(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        money=Money(amount_minor=1200, currency="USD"),
        purpose="Operational cloud hosting renewal",
        idempotency_key="idemp-rail-003",
        occurred_at_utc=datetime.now(UTC),
    )

    # When live env is unconfigured in local test runner, adapter safely uses fallback
    res = adapter.pay(intent)
    assert res.success is True
    assert res.transaction_id != ""
    assert "sandbox" in res.transaction_id or res.status in ("COMPLETED_SIMULATED", "SUCCESS")
