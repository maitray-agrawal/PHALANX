"""Database-backed append-only ledger adapter with cryptographic verification."""

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.canonical_json import canonical_json_bytes
from app.domain.ledger import GENESIS_PREV_HASH
from app.domain.models import PolicyEvaluationResult, TransactionIntent
from app.infrastructure.models import LedgerEventModel


class DatabaseLedgerAdapter:
    """Manages append-only ledger events with SHA-256 hash chaining and verification."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def append_event(
        self,
        event_type: str,
        intent: TransactionIntent,
        result: PolicyEvaluationResult,
        recorded_at_utc: datetime,
    ) -> str:
        """Append an event to the ledger, computing prev_hash and event_hash."""
        # 1. Fetch latest event sequence and hash
        latest_stmt = (
            select(LedgerEventModel)
            .order_by(LedgerEventModel.event_seq.desc())
            .limit(1)
        )
        latest = self.session.scalar(latest_stmt)

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
        canonical_bytes = canonical_json_bytes(payload_dict)
        canonical_str = canonical_bytes.decode("utf-8")

        # Hash chaining: event_hash = SHA256(prev_hash + canonical_payload)
        chain_material = f"{prev_hash}{canonical_str}".encode("utf-8")
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
        self.session.add(event)
        self.session.flush()
        return event_id

    def verify_chain(self) -> tuple[bool, str]:
        """Verify cryptographic integrity and sequence continuity across all historical events."""
        stmt = select(LedgerEventModel).order_by(LedgerEventModel.event_seq.asc())
        events = list(self.session.scalars(stmt))

        if not events:
            return True, "empty ledger is valid"

        expected_prev = GENESIS_PREV_HASH
        expected_seq = 1

        for ev in events:
            # 1. Sequence continuity check (detects row deletion)
            if ev.event_seq != expected_seq:
                return (
                    False,
                    f"Sequence gap detected: expected seq {expected_seq}, got {ev.event_seq} "
                    f"(row deleted)",
                )

            # 2. Previous hash link check
            if ev.prev_hash != expected_prev:
                return (
                    False,
                    f"Hash link broken at event '{ev.event_id}': expected prev_hash "
                    f"'{expected_prev}', got '{ev.prev_hash}'",
                )

            # 3. Payload integrity check (detects row modification)
            chain_material = f"{ev.prev_hash}{ev.payload_json}".encode("utf-8")
            recomputed_hash = hashlib.sha256(chain_material).hexdigest()
            if recomputed_hash != ev.event_hash:
                return (
                    False,
                    f"Event hash mismatch at '{ev.event_id}': recomputed '{recomputed_hash}' "
                    f"!= stored '{ev.event_hash}' (row modified)",
                )

            expected_prev = ev.event_hash
            expected_seq += 1

        return True, f"valid: {len(events)} events verified"
