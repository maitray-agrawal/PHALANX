"""Post-run SQL and API invariant verification script for PHALANX.

Verifies the 4 critical security and accounting invariants:
1. spent_minor + reserved_minor <= allocated_minor across all agent budgets.
2. Exactly one payment per idempotency key (no duplicate executions).
3. Ledger cryptographic hash chain verifies with zero broken links or tampered payloads.
4. No orphan reservations (all reservations confirmed, released, or actively held).
"""

import os
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text

from app.domain.ledger import ChainedLedgerEvent, verify_chain
from app.infrastructure.config import settings


def get_db_engine():
    db_url = os.getenv("DATABASE_URL", settings.database_url)
    return create_engine(db_url)


def check_invariants() -> dict[str, Any]:
    engine = get_db_engine()
    results: dict[str, Any] = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "passed": True,
        "violations": [],
        "metrics": {},
    }

    with engine.connect() as conn:
        # Invariant 1: spent + reserved never exceeds allocated
        budget_query = text("""
            SELECT agent_id, mandate_id, allocated_minor, spent_minor, reserved_minor
            FROM agent_budgets;
        """)
        budgets = conn.execute(budget_query).fetchall()
        results["metrics"]["budgets_checked"] = len(budgets)

        for b in budgets:
            total_committed = b.spent_minor + b.reserved_minor
            if total_committed > b.allocated_minor:
                results["passed"] = False
                results["violations"].append(
                    f"Invariant 1 VIOLATION: Budget for agent '{b.agent_id}' exceeded! "
                    f"Spent ({b.spent_minor}) + Reserved ({b.reserved_minor}) = "
                    f"{total_committed} > Allocated ({b.allocated_minor})"
                )
            if b.spent_minor < 0 or b.reserved_minor < 0:
                results["passed"] = False
                results["violations"].append(
                    f"Invariant 1 VIOLATION: Negative balance in budget for agent '{b.agent_id}'! "
                    f"Spent: {b.spent_minor}, Reserved: {b.reserved_minor}"
                )

        # Invariant 2: Exactly one payment per idempotency key
        idem_query = text("""
            SELECT idempotency_key, COUNT(*) as cnt
            FROM idempotency_records
            GROUP BY idempotency_key
            HAVING COUNT(*) > 1;
        """)
        dup_idems = conn.execute(idem_query).fetchall()
        total_idems = conn.execute(text("SELECT COUNT(*) FROM idempotency_records;")).scalar() or 0
        results["metrics"]["idempotency_keys_checked"] = total_idems

        if dup_idems:
            results["passed"] = False
            for d in dup_idems:
                results["violations"].append(
                    f"Invariant 2 VIOLATION: Duplicate '{d.idempotency_key}' found {d.cnt}x!"
                )

        # Invariant 3: Ledger cryptographic hash chain verifies
        ledger_query = text("""
            SELECT event_seq, event_id, event_type, prev_hash, event_hash, payload_json
            FROM ledger_events
            ORDER BY event_seq ASC;
        """)
        events_raw = conn.execute(ledger_query).fetchall()
        results["metrics"]["ledger_events_checked"] = len(events_raw)

        import json

        events: list[ChainedLedgerEvent] = []
        for row in events_raw:
            payload = (
                json.loads(row.payload_json)
                if isinstance(row.payload_json, str)
                else row.payload_json
            )
            events.append(
                ChainedLedgerEvent(
                    event_id=row.event_id,
                    event_type=row.event_type,
                    prev_hash=row.prev_hash,
                    payload=payload,
                    event_hash=row.event_hash,
                )
            )

        is_valid, msg, broken_idx = verify_chain(events)
        results["metrics"]["chain_valid"] = is_valid
        results["metrics"]["chain_message"] = msg
        if not is_valid:
            results["passed"] = False
            results["violations"].append(
                f"Invariant 3 VIOLATION: Ledger hash chain broken at index {broken_idx}: {msg}"
            )

        # Invariant 4: No orphan reservations
        res_query = text("""
            SELECT reservation_id, agent_id, status, amount_minor, created_at_utc, updated_at_utc
            FROM budget_reservations
            WHERE status = 'PENDING';
        """)
        pending_res = conn.execute(res_query).fetchall()
        total_res = conn.execute(text("SELECT COUNT(*) FROM budget_reservations;")).scalar() or 0
        results["metrics"]["total_reservations"] = total_res
        results["metrics"]["pending_reservations"] = len(pending_res)

        # Cross-verify: reserved_minor on each budget must exactly match sum of PENDING reservations
        for b in budgets:
            sum_pending = (
                conn.execute(
                    text(
                        "SELECT COALESCE(SUM(amount_minor), 0) FROM budget_reservations "
                        "WHERE agent_id = :aid AND status = 'PENDING'"
                    ),
                    {"aid": b.agent_id},
                ).scalar()
                or 0
            )
            if sum_pending != b.reserved_minor:
                results["passed"] = False
                results["violations"].append(
                    f"Invariant 4 VIOLATION: Reserved mismatch on '{b.agent_id}': "
                    f"budget.reserved={b.reserved_minor} != sum(PENDING)={sum_pending}"
                )

        # Check for lingering pending reservations older than 60 seconds
        now = datetime.now(UTC)
        orphan_count = 0
        for r in pending_res:
            created = (
                r.created_at_utc.replace(tzinfo=UTC)
                if r.created_at_utc.tzinfo is None
                else r.created_at_utc
            )
            age_sec = (now - created).total_seconds()
            if age_sec > 60.0:
                orphan_count += 1
                results["violations"].append(
                    f"Invariant 4 VIOLATION: Orphan '{r.reservation_id}' ({r.agent_id}) "
                    f"created {age_sec:.1f}s ago and still PENDING!"
                )
        results["metrics"]["orphan_reservations"] = orphan_count
        if orphan_count > 0:
            results["passed"] = False

    return results


def print_report(results: dict[str, Any]) -> None:
    print("=" * 70)
    print("PHALANX INVARIANT INTEGRITY REPORT")
    print(f"Timestamp: {results['timestamp_utc']}")
    print("-" * 70)
    m = results["metrics"]
    print(f"Budgets Audited:          {m.get('budgets_checked', 0)}")
    print(f"Idempotency Records:      {m.get('idempotency_keys_checked', 0)}")
    print(
        f"Ledger Blocks Verified:   {m.get('ledger_events_checked', 0)} "
        f"({m.get('chain_message', '')})"
    )
    print(
        f"Reservations Audited:     {m.get('total_reservations', 0)} "
        f"(Active/Pending: {m.get('pending_reservations', 0)}, "
        f"Orphan: {m.get('orphan_reservations', 0)})"
    )
    print("-" * 70)

    if results["passed"]:
        print("RESULT: ALL 4 INVARIANTS SATISFIED (PASS)")
        print("1. spent + reserved <= allocated:          VALID")
        print("2. exactly one payment per key:            VALID")
        print("3. ledger cryptographic hash chain:        VALID")
        print("4. zero orphan reservations:               VALID")
    else:
        print("RESULT: INVARIANT VIOLATIONS DETECTED (FAIL)")
        for v in results["violations"]:
            print(f"  [X] {v}")
    print("=" * 70)


if __name__ == "__main__":
    res = check_invariants()
    print_report(res)
    sys.exit(0 if res["passed"] else 1)
