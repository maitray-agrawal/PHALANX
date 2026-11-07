"""Database-backed append-only ledger adapter with cryptographic verification."""

import hashlib
import json
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from threading import RLock
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.canonical_json import canonical_json_bytes
from app.domain.ledger import (
    GENESIS_PREV_HASH,
    ChainedLedgerEvent,
)
from app.domain.ledger import (
    verify_chain as domain_verify_chain,
)
from app.domain.models import PolicyEvaluationResult, TransactionIntent
from app.domain.ports import LedgerPort
from app.infrastructure.models import LedgerEventModel


class DatabaseLedgerAdapter(LedgerPort):
    """Manages append-only ledger events with SHA-256 hash chaining and verification."""

    def __init__(
        self,
        session: Session | None = None,
        session_factory: Any | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self._lock = RLock()
        self._tampered_events: list[ChainedLedgerEvent] | None = None

    @contextmanager
    def _get_session(self) -> Generator[Session, None, None]:
        if self.session is not None:
            yield self.session
        elif self.session_factory is not None:
            with self.session_factory() as sess, sess.begin():
                yield sess
        else:
            raise RuntimeError("DatabaseLedgerAdapter requires a Session or session_factory")

    def append_event(
        self,
        event_type: str,
        intent: TransactionIntent,
        result: PolicyEvaluationResult,
        recorded_at_utc: datetime,
        provider_state: str | None = None,
    ) -> str:
        """Append an event to the ledger, computing prev_hash and event_hash."""
        with self._lock, self._get_session() as session:
            # 1. Fetch latest event sequence and hash
            latest_stmt = (
                select(LedgerEventModel).order_by(LedgerEventModel.event_seq.desc()).limit(1)
            )
            latest = session.scalar(latest_stmt)

            next_seq = (latest.event_seq + 1) if latest else 1
            prev_hash = latest.event_hash if latest else GENESIS_PREV_HASH

            key_hash = hashlib.sha256(intent.idempotency_key.encode("utf-8")).hexdigest()[:8]
            event_id = f"evt_{next_seq:06d}_{key_hash}"

            payload_dict: dict[str, Any] = {
                "event_id": event_id,
                "event_type": event_type,
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
                payload_dict["provider_state"] = provider_state
            canonical_bytes = canonical_json_bytes(payload_dict)
            canonical_str = canonical_bytes.decode("utf-8")

            # Hash chaining: event_hash = SHA256(prev_hash + canonical_payload)
            chain_material = f"{prev_hash}{canonical_str}".encode()
            event_hash = hashlib.sha256(chain_material).hexdigest()

            event = LedgerEventModel(
                event_id=event_id,
                event_seq=next_seq,
                prev_hash=prev_hash,
                event_hash=event_hash,
                event_type=event_type,
                agent_id=intent.agent_id,
                recipient_id=intent.recipient_id,
                amount_minor=intent.money.amount_minor,
                currency=intent.money.currency,
                payload_json=canonical_str,
                recorded_at_utc=recorded_at_utc,
            )
            session.add(event)
            session.flush()
            self._tampered_events = None
            return event_id

    def get_all_events(self) -> list[ChainedLedgerEvent]:
        """Retrieve all ledger events as chained domain events."""
        with self._lock:
            if self._tampered_events is not None:
                return list(self._tampered_events)

            with self._get_session() as session:
                stmt = select(LedgerEventModel).order_by(LedgerEventModel.event_seq.asc())
                models = list(session.scalars(stmt))
                events: list[ChainedLedgerEvent] = []
                for m in models:
                    payload = (
                        json.loads(m.payload_json)
                        if isinstance(m.payload_json, str)
                        else m.payload_json
                    )
                    events.append(
                        ChainedLedgerEvent(
                            event_id=m.event_id,
                            event_type=m.event_type,
                            prev_hash=m.prev_hash,
                            payload=payload,
                            event_hash=m.event_hash,
                        )
                    )
                return events

    def verify_integrity(self) -> tuple[bool, str, int | None]:
        """Cryptographically verify all events in sequence, returning broken index on tamper."""
        events = self.get_all_events()
        return domain_verify_chain(events)

    def verify_chain(self) -> tuple[bool, str]:
        """Verify cryptographic integrity and sequence continuity across all historical events."""
        with self._lock:
            if self._tampered_events is not None:
                is_valid, msg, _ = domain_verify_chain(self._tampered_events)
                return is_valid, msg

            with self._get_session() as session:
                stmt = select(LedgerEventModel).order_by(LedgerEventModel.event_seq.asc())
                events = list(session.scalars(stmt))

                if not events:
                    return True, "empty ledger is valid"

                expected_prev = GENESIS_PREV_HASH
                expected_seq = events[0].event_seq

                for ev in events:
                    # 1. Sequence continuity check (detects row deletion)
                    if ev.event_seq != expected_seq:
                        return (
                            False,
                            f"Sequence gap detected: expected seq {expected_seq}, "
                            f"got {ev.event_seq} (row deleted)",
                        )

                    # 2. Previous hash link check
                    if ev.prev_hash != expected_prev:
                        return (
                            False,
                            f"Hash link broken at event '{ev.event_id}': expected prev_hash "
                            f"'{expected_prev}', got '{ev.prev_hash}'",
                        )

                    # 3. Payload integrity check (detects row modification)
                    try:
                        parsed_payload = json.loads(ev.payload_json)
                        chain_material = ev.prev_hash.encode("ascii") + canonical_json_bytes(
                            parsed_payload
                        )
                    except Exception:
                        chain_material = f"{ev.prev_hash}{ev.payload_json}".encode()
                    recomputed_hash = hashlib.sha256(chain_material).hexdigest()
                    if recomputed_hash != ev.event_hash:
                        return (
                            False,
                            f"Event hash mismatch at '{ev.event_id}': "
                            f"recomputed '{recomputed_hash}' != stored '{ev.event_hash}' "
                            "(row modified)",
                        )

                    expected_prev = ev.event_hash
                    expected_seq += 1

                return True, f"valid: {len(events)} events verified"

    def tamper_for_testing(self, index: int = 1, new_amount: int = 99999999) -> None:
        """Simulate tampering with a historical block for auditor verification testing."""
        with self._lock:
            events = self.get_all_events()
            if 0 <= index < len(events):
                orig = events[index]
                mutated_payload = dict(orig.payload)
                mutated_payload["amount_minor"] = new_amount
                tampered = ChainedLedgerEvent(
                    event_id=orig.event_id,
                    event_type=orig.event_type,
                    prev_hash=orig.prev_hash,
                    payload=mutated_payload,
                    event_hash=orig.event_hash,
                )
                events[index] = tampered
                self._tampered_events = events

    def restore_true_ledger(self) -> None:
        """Restore pristine ledger state by invalidating tampered test cache."""
        with self._lock:
            self._tampered_events = None
