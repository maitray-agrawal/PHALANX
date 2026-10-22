"""Ledger adapter implementing LedgerPort."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from threading import Lock

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
    """Thread-safe append-only in-memory ledger adapter for tests and local dev."""

    def __init__(self) -> None:
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
            payload = (
                f"{self._counter}:{intent.agent_id}:{intent.recipient_id}:"
                f"{intent.money.amount_minor}:{intent.money.currency}:{intent.idempotency_key}:"
                f"{recorded_at_utc.isoformat()}"
            )
            event_id = f"evt_{hashlib.sha256(payload.encode()).hexdigest()[:16]}"
            entry = LedgerEntry(
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
            self._entries.append(entry)
            return event_id

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        with self._lock:
            return tuple(self._entries)
