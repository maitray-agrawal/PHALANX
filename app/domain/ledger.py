"""Pure cryptographic hash chain logic for immutable audit ledgers.

Every block/event contains:
- event_id
- prev_hash (SHA-256 hex string of preceding event; '0'*64 for genesis)
- event_payload (canonical dict)
- hash (SHA-256 over prev_hash + canonical_json(event_payload))
"""

import hashlib
from dataclasses import dataclass
from typing import Any

from app.domain.canonical_json import canonical_json_bytes

GENESIS_PREV_HASH = "0" * 64


@dataclass(frozen=True)
class ChainedLedgerEvent:
    """Cryptographically linked audit record."""

    event_id: str
    event_type: str
    prev_hash: str
    payload: dict[str, Any]
    event_hash: str

    def calculate_expected_hash(self) -> str:
        """Compute SHA-256(prev_hash + canonical_json(payload))."""
        raw = self.prev_hash.encode("ascii") + canonical_json_bytes(self.payload)
        return hashlib.sha256(raw).hexdigest()

    def is_valid_link(self) -> bool:
        return self.event_hash == self.calculate_expected_hash()


def create_chained_event(
    event_id: str,
    event_type: str,
    prev_hash: str,
    payload: dict[str, Any],
) -> ChainedLedgerEvent:
    """Create a new chained ledger event with valid hash."""
    raw = prev_hash.encode("ascii") + canonical_json_bytes(payload)
    event_hash = hashlib.sha256(raw).hexdigest()
    return ChainedLedgerEvent(
        event_id=event_id,
        event_type=event_type,
        prev_hash=prev_hash,
        payload=payload,
        event_hash=event_hash,
    )


def verify_chain(
    events: list[ChainedLedgerEvent] | tuple[ChainedLedgerEvent, ...],
) -> tuple[bool, str, int | None]:
    """Verify that every event in the sequence has a valid link and points to the previous hash.

    Returns:
        tuple: (is_valid: bool, message: str, broken_index: int | None)
    """
    if not events:
        return True, "Chain is empty (valid)", None

    # Genesis check
    if events[0].prev_hash != GENESIS_PREV_HASH:
        return False, f"Genesis event has invalid prev_hash: {events[0].prev_hash}", 0

    if not events[0].is_valid_link():
        return False, f"Genesis event hash mismatch at event {events[0].event_id}", 0

    for idx in range(1, len(events)):
        current = events[idx]
        previous = events[idx - 1]

        # Check chain link
        if current.prev_hash != previous.event_hash:
            return (
                False,
                f"Broken chain at index {idx} ({current.event_id}): "
                f"prev_hash does not match preceding event hash",
                idx,
            )

        # Check internal payload hash integrity
        if not current.is_valid_link():
            return (
                False,
                f"Tampered payload at index {idx} ({current.event_id}): hash mismatch",
                idx,
            )

    return True, f"Verified chain of {len(events)} events", None
