"""Unit tests for cryptographic ledger hash chaining and tamper detection."""

from datetime import UTC, datetime

from app.domain.ledger import (
    GENESIS_PREV_HASH,
    ChainedLedgerEvent,
    create_chained_event,
    verify_chain,
)
from app.domain.models import DecisionOutcome, Money, PolicyEvaluationResult, TransactionIntent
from app.infrastructure.ledger import InMemoryLedgerAdapter


def test_hash_chain_creation_and_verification() -> None:
    event_1 = create_chained_event(
        event_id="evt_001",
        event_type="AUTH",
        prev_hash=GENESIS_PREV_HASH,
        payload={"amount": 100, "status": "ALLOW"},
    )
    assert event_1.prev_hash == GENESIS_PREV_HASH
    assert event_1.is_valid_link() is True

    event_2 = create_chained_event(
        event_id="evt_002",
        event_type="AUTH",
        prev_hash=event_1.event_hash,
        payload={"amount": 250, "status": "ALLOW"},
    )
    assert event_2.prev_hash == event_1.event_hash
    assert event_2.is_valid_link() is True

    valid, msg, broken_idx = verify_chain([event_1, event_2])
    assert valid is True
    assert broken_idx is None
    assert "Verified chain of 2 events" in msg


def test_hash_chain_detects_tampered_payload() -> None:
    event_1 = create_chained_event(
        event_id="evt_001",
        event_type="AUTH",
        prev_hash=GENESIS_PREV_HASH,
        payload={"amount": 100, "status": "ALLOW"},
    )
    # Attacker stealthily modifies amount to 999999 in payload without updating event_hash
    tampered_event = ChainedLedgerEvent(
        event_id=event_1.event_id,
        event_type=event_1.event_type,
        prev_hash=event_1.prev_hash,
        payload={"amount": 999999, "status": "ALLOW"},
        event_hash=event_1.event_hash,
    )

    valid, msg, broken_idx = verify_chain([tampered_event])
    assert valid is False
    assert broken_idx == 0
    assert "hash mismatch" in msg


def test_in_memory_ledger_adapter_tamper_detection() -> None:
    adapter = InMemoryLedgerAdapter()
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)

    intent = TransactionIntent(
        agent_id="agent_1",
        recipient_id="vendor_1",
        money=Money(amount_minor=5000, currency="USD"),
        purpose="Renewal",
        idempotency_key="tx-ledger-1",
        occurred_at_utc=now,
    )
    res = PolicyEvaluationResult(outcome=DecisionOutcome.ALLOW, evaluated_at_utc=now)

    adapter.append_event("TEST_EVENT", intent, res, now)
    valid, _, _ = adapter.verify_integrity()
    assert valid is True

    # Simulate database row tampering
    adapter.tamper_for_testing(index=0, new_amount=99999999)
    tampered_valid, msg, broken_idx = adapter.verify_integrity()
    assert tampered_valid is False
    assert broken_idx == 0
    assert "Tampered payload" in msg or "hash mismatch" in msg
