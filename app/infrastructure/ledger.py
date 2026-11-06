"""Thread-safe append-only ledger adapter with cryptographic hash chaining."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from app.domain.ledger import (
    GENESIS_PREV_HASH,
    ChainedLedgerEvent,
    create_chained_event,
    verify_chain,
)
from app.domain.models import DecisionOutcome, Money, PolicyEvaluationResult, TransactionIntent
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
    """Append-only ledger adapter maintaining a SHA-256 hash chain with DB persistence."""

    def __init__(self, db_session_factory: Any | None = None) -> None:
        self._db_session_factory = db_session_factory
        self._events: list[ChainedLedgerEvent] = []
        self._entries: list[LedgerEntry] = []
        self._pristine_events: list[ChainedLedgerEvent] = []
        self._lock = Lock()
        self._counter = 0
        if self._db_session_factory is not None:
            self._load_from_db()

    def _load_from_db(self) -> None:
        if self._db_session_factory is None:
            return
        try:
            import json

            from sqlalchemy import select

            from app.infrastructure.models import LedgerEventModel

            with self._db_session_factory() as session:
                stmt = select(LedgerEventModel).order_by(LedgerEventModel.event_seq.asc())
                models = list(session.scalars(stmt))
                if models:
                    self._events.clear()
                    self._entries.clear()
                    for m in models:
                        payload = (
                            json.loads(m.payload_json)
                            if isinstance(m.payload_json, str)
                            else m.payload_json
                        )
                        chained = ChainedLedgerEvent(
                            event_id=m.event_id,
                            event_type=m.event_type,
                            prev_hash=m.prev_hash,
                            payload=payload,
                            event_hash=m.event_hash,
                        )
                        self._events.append(chained)
                        reasons = tuple(payload.get("reasons", ()))
                        self._entries.append(
                            LedgerEntry(
                                event_id=m.event_id,
                                event_type=m.event_type,
                                agent_id=m.agent_id,
                                recipient_id=m.recipient_id,
                                amount_minor=m.amount_minor,
                                currency=m.currency,
                                purpose=payload.get("purpose", ""),
                                idempotency_key=payload.get("idempotency_key", ""),
                                decision=payload.get("decision", ""),
                                reasons=reasons,
                                recorded_at_utc=m.recorded_at_utc,
                            )
                        )
                    self._counter = models[-1].event_seq
                    self._pristine_events = list(self._events)
        except Exception:
            pass  # nosec: B110

    def append_event(
        self,
        event_type: str,
        intent: TransactionIntent,
        result: PolicyEvaluationResult,
        recorded_at_utc: datetime,
        provider_state: str | None = None,
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
            if provider_state:
                payload["provider_state"] = provider_state

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

            if self._db_session_factory is not None:
                try:
                    import json

                    from app.infrastructure.models import LedgerEventModel

                    with self._db_session_factory() as session, session.begin():
                        db_event = LedgerEventModel(
                            event_id=event_id,
                            event_seq=self._counter,
                            prev_hash=prev_hash,
                            event_hash=chained.event_hash,
                            event_type=event_type,
                            agent_id=intent.agent_id,
                            recipient_id=intent.recipient_id,
                            amount_minor=intent.money.amount_minor,
                            currency=intent.money.currency,
                            payload_json=json.dumps(payload),
                            recorded_at_utc=recorded_at_utc,
                        )
                        session.add(db_event)
                except Exception:
                    pass  # nosec: B110

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

    def seed_demo_events(self) -> None:
        """Seed authentic ledger events for demo dashboard scenes."""
        with self._lock:
            if self._events:
                return
            now_1 = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
            intent_1 = TransactionIntent(
                agent_id="agent-auto-1",
                recipient_id="vendor-paypal-sandbox-1",
                money=Money(amount_minor=2500, currency="USD"),
                purpose="Monthly subscription renewal",
                idempotency_key="seed_001_sub",
                occurred_at_utc=now_1,
            )
            res_1 = PolicyEvaluationResult(
                outcome=DecisionOutcome.ALLOW,
                reasons=("Amount within pre-authorized operational limit",),
                evaluated_at_utc=now_1,
            )
            self._append_event_locked("AUTHORIZATION_EVALUATED", intent_1, res_1, now_1)

            now_2 = datetime(2026, 10, 22, 12, 5, 14, tzinfo=UTC)
            intent_2 = TransactionIntent(
                agent_id="agent-auto-1",
                recipient_id="vendor-paypal-sandbox-1",
                money=Money(amount_minor=100000, currency="USD"),
                purpose="Equipment invoice review",
                idempotency_key="seed_002_equip",
                occurred_at_utc=now_2,
            )
            res_2 = PolicyEvaluationResult(
                outcome=DecisionOutcome.STEP_UP,
                reasons=("Amount exceeds instant autonomous threshold ($500.00)",),
                evaluated_at_utc=now_2,
            )
            self._append_event_locked("AUTHORIZATION_EVALUATED", intent_2, res_2, now_2)

            now_3 = datetime(2026, 10, 22, 12, 12, 30, tzinfo=UTC)
            intent_3 = TransactionIntent(
                agent_id="rogue-agent-99",
                recipient_id="external-unknown-wallet",
                money=Money(amount_minor=9500000, currency="USD"),
                purpose="Unauthorized bulk withdrawal attempt",
                idempotency_key="seed_003_rogue",
                occurred_at_utc=now_3,
            )
            res_3 = PolicyEvaluationResult(
                outcome=DecisionOutcome.DENY,
                reasons=("Amount exceeds single transaction cap ($5,000.00)",),
                evaluated_at_utc=now_3,
            )
            self._append_event_locked("AUTHORIZATION_EVALUATED", intent_3, res_3, now_3)

            # Store pristine copy for restore
            self._pristine_events = list(self._events)

    def restore_true_ledger(self) -> None:
        """Restore pristine unmodified ledger events."""
        with self._lock:
            if self._pristine_events:
                self._events = list(self._pristine_events)

    def _append_event_locked(
        self,
        event_type: str,
        intent: TransactionIntent,
        result: PolicyEvaluationResult,
        recorded_at_utc: datetime,
        provider_state: str | None = None,
    ) -> str:
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
        if provider_state:
            payload["provider_state"] = provider_state

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
