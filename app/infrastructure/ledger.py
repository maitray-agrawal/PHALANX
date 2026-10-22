"""Thread-safe append-only ledger adapter with cryptographic hash chaining."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from app.domain.ledger import (
    GENESIS_PREV_HASH,
    ChainedLedgerEvent,
    create_chained_event,
    verify_chain,
)
from app.domain.models import PolicyEvaluationResult, TransactionIntent
from app.domain.ports import LedgerPort


@dataclass(frozen=True)
class LedgerEntry:
    """Immutable ledger record."""

    event_id: str
    event_type: str
    agent_id: str
    recipient_id: str
    amount_minor: int
    currency: str
    purpose: str
    idempotency_key: str
    decision: str
    reasons: tuple[str, ...]
    recorded_at_utc: datetime


class InMemoryLedgerAdapter(LedgerPort):
    """Thread-safe append-only ledger adapter maintaining a SHA-256 hash chain."""

    def __init__(self) -> None:
        self._events: list[ChainedLedgerEvent] = []
        self._entries: list[LedgerEntry] = []
        self._lock = Lock()
        self._counter = 0

    def append_event(
        self,
        event_type: str,
        intent: TransactionIntent,
        result: PolicyEvaluationResult,
        recorded_at_utc: datetime,
    ) -> str:
        with self._lock:
            self._counter += 1
            key_hash = hashlib.sha256(intent.idempotency_key.encode()).hexdigest()[:8]
            event_id = f"evt_{self._counter:06d}_{key_hash}"
            prev_hash = self._events[-1].event_hash if self._events else GENESIS_PREV_HASH

            payload: dict[str, Any] = {
                "agent_id": intent.agent_id,
                "recipient_id": intent.recipient_id,
                "amount_minor": intent.money.amount_minor,
                "currency": intent.money.currency,
                "purpose": intent.purpose,
                "idempotency_key": intent.idempotency_key,
                "decision": result.outcome.value,
                "reasons": list(result.reasons),
                "recorded_at_utc": recorded_at_utc.isoformat(),
            }

            chained = create_chained_event(
                event_id=event_id,
                event_type=event_type,
                prev_hash=prev_hash,
                payload=payload,
            )
            self._events.append(chained)
            self._entries.append(
                LedgerEntry(
                    event_id=event_id,
                    event_type=event_type,
                    agent_id=intent.agent_id,
                    recipient_id=intent.recipient_id,
                    amount_minor=intent.money.amount_minor,
                    currency=intent.money.currency,
                    purpose=intent.purpose,
                    idempotency_key=intent.idempotency_key,
                    decision=result.outcome.value,
                    reasons=result.reasons,
                    recorded_at_utc=recorded_at_utc,
                )
            )
            return event_id

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        with self._lock:
            return tuple(self._entries)

    def get_all_events(self) -> list[ChainedLedgerEvent]:
        with self._lock:
            return list(self._events)

    def verify_integrity(self) -> tuple[bool, str, int | None]:
        with self._lock:
            return verify_chain(self._events)

    def tamper_for_testing(self, index: int, new_amount: int) -> None:
        """Testing hook to simulate illicit SQL database tampering."""
        with self._lock:
            if 0 <= index < len(self._events):
                orig = self._events[index]
                mutated_payload = dict(orig.payload)
                mutated_payload["amount_minor"] = new_amount
                # We modify the payload without updating the hash, simulating tampering!
                tampered = ChainedLedgerEvent(
                    event_id=orig.event_id,
                    event_type=orig.event_type,
                    prev_hash=orig.prev_hash,
                    payload=mutated_payload,
                    event_hash=orig.event_hash,
                )
                self._events[index] = tampered
