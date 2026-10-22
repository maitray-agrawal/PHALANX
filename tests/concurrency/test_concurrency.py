"""Concurrency and money-safety integration tests.

Tests manual 56.13:
- 50 parallel requests racing one budget.
- Duplicate key and body (idempotent replay).
- Duplicate key different body (idempotency mismatch error).
- Replayed approval (invalid approval state).
- Edited intent after approval (digest mismatch).
- Expired approval window (approval expired).
- Modified and deleted ledger rows fail verification.
- Trigger enforces append-only ledger_events (UPDATE and DELETE raise).
- Release only on confirmed failure (UNKNOWN outcome routes to RECONCILE, never releases funds).
- 20 consecutive runs of the 50-request race to verify zero flakiness.
"""

import hashlib
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.domain.models import DecisionOutcome, Money, PolicyEvaluationResult, TransactionIntent
from app.infrastructure.db_budget_repo import (
    ApprovalDigestMismatchError,
    ApprovalExpiredError,
    BudgetRepository,
    IdempotencyMismatchError,
    IdempotencyReplayError,
    InsufficientBudgetError,
    InvalidApprovalStateError,
)
from app.infrastructure.db_ledger_repo import DatabaseLedgerAdapter
from app.infrastructure.db_schema import create_schema
from app.infrastructure.models import (
    AgentBudgetModel,
    ApprovalStatus,
    BudgetReservationModel,
    ReservationStatus,
)


@pytest.fixture
def db_session_factory():
    """Create a temporary SQLite database with WAL mode and immutability triggers."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_engine(
        f"sqlite:///{db_path}?timeout=30.0",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def do_connect(dbapi_connection, _connection_record):
        # Disable pysqlite's implicit BEGIN to allow BEGIN IMMEDIATE
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    @event.listens_for(engine, "begin")
    def do_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    create_schema(engine)

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield Session, engine

    engine.dispose()
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError:
        pass


def _create_dummy_intent(
    agent_id: str = "agent_test",
    amount_minor: int = 100,
    seq: int = 0,
) -> TransactionIntent:
    return TransactionIntent(
        agent_id=agent_id,
        recipient_id="vendor_paypal",
        money=Money(amount_minor=amount_minor, currency="USD"),
        purpose="SAAS_SUBSCRIPTION",
        invoice_reference=f"INV-{seq}",
        idempotency_key=f"idem_{agent_id}_{seq}",
        occurred_at_utc=datetime.now(UTC),
    )


def _create_dummy_result(
    outcome: DecisionOutcome = DecisionOutcome.ALLOW,
) -> PolicyEvaluationResult:
    return PolicyEvaluationResult(
        outcome=outcome,
        reasons=("ALLOW_WITHIN_BOUNDS",),
    )


def test_fifty_parallel_requests_racing_one_budget(db_session_factory) -> None:
    """50 parallel requests race to reserve from a 1000-minor-unit budget.

    Each request asks for 100 minor units.
    Exactly 10 must succeed (10 * 100 = 1000).
    Exactly 40 must fail with InsufficientBudgetError.
    Total reserved must equal 1000, and available must equal 0.
    No overdrafts, no race condition leaks.
    """
    Session, _ = db_session_factory
    agent_id = "agent_race_1"

    # Seed budget: 1000 minor units ($10.00)
    with Session() as session, session.begin():
        session.add(
            AgentBudgetModel(
                agent_id=agent_id,
                mandate_id="man_001",
                currency="USD",
                allocated_minor=1000,
                spent_minor=0,
                reserved_minor=0,
            )
        )

    successes = []
    failures = []

    def attempt_reservation(index: int):
        with Session() as session:
            repo = BudgetRepository(session)
            idem_key = f"key_{index}_{uuid.uuid4().hex[:6]}"
            intent_digest = hashlib.sha256(idem_key.encode("utf-8")).hexdigest()
            try:
                with session.begin():
                    res = repo.reserve_budget(
                        agent_id=agent_id,
                        amount_minor=100,
                        currency="USD",
                        idempotency_key=idem_key,
                        intent_digest=intent_digest,
                    )
                return ("SUCCESS", res.reservation_id)
            except InsufficientBudgetError as e:
                return ("FAIL", str(e))
            except Exception as e:
                return ("ERROR", type(e).__name__ + ": " + str(e))

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(attempt_reservation, i) for i in range(50)]
        for f in futures:
            status, detail = f.result()
            if status == "SUCCESS":
                successes.append(detail)
            elif status == "FAIL":
                failures.append(detail)
            else:
                pytest.fail(f"Unexpected error during race: {detail}")

    assert len(successes) == 10, f"Expected exactly 10 successes, got {len(successes)}"
    assert len(failures) == 40, f"Expected exactly 40 failures, got {len(failures)}"

    # Verify final budget state
    with Session() as session:
        b = session.query(AgentBudgetModel).filter_by(agent_id=agent_id).one()
        assert b.allocated_minor == 1000
        assert b.spent_minor == 0
        assert b.reserved_minor == 1000
        assert b.available_minor == 0


def test_twenty_consecutive_race_runs(db_session_factory) -> None:
    """Verify concurrency safety across 20 consecutive runs without flakiness."""
    Session, _ = db_session_factory

    def make_worker(cur_agent_id: str, cur_run_idx: int):
        def worker(req_idx: int):
            with Session() as session:
                repo = BudgetRepository(session)
                idem_key = f"r_{cur_run_idx}_{req_idx}_{uuid.uuid4().hex[:4]}"
                digest = hashlib.sha256(idem_key.encode("utf-8")).hexdigest()
                try:
                    with session.begin():
                        repo.reserve_budget(
                            agent_id=cur_agent_id,
                            amount_minor=50,
                            currency="USD",
                            idempotency_key=idem_key,
                            intent_digest=digest,
                        )
                    return True
                except InsufficientBudgetError:
                    return False

        return worker

    for run_idx in range(20):
        agent_id = f"agent_run_{run_idx}"
        with Session() as session, session.begin():
            session.add(
                AgentBudgetModel(
                    agent_id=agent_id,
                    mandate_id=f"man_{run_idx}",
                    currency="USD",
                    allocated_minor=500,
                    spent_minor=0,
                    reserved_minor=0,
                )
            )

        worker = make_worker(agent_id, run_idx)

        with ThreadPoolExecutor(max_workers=25) as executor:
            results = list(executor.map(worker, range(25)))

        success_count = sum(1 for r in results if r is True)
        fail_count = sum(1 for r in results if r is False)

        assert success_count == 10, f"Run {run_idx}: expected 10 successes, got {success_count}"
        assert fail_count == 15, f"Run {run_idx}: expected 15 failures, got {fail_count}"

        with Session() as session:
            b = session.query(AgentBudgetModel).filter_by(agent_id=agent_id).one()
            assert b.reserved_minor == 500
            assert b.available_minor == 0


def test_idempotency_duplicate_key_same_body(db_session_factory) -> None:
    """Duplicate key with matching body raises IdempotencyReplayError with cached record."""
    Session, _ = db_session_factory

    key = "idem_key_001"
    digest = hashlib.sha256(b'{"amount":100,"agent":"agent_1"}').hexdigest()

    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            # First check: returns None (not seen before)
            assert repo.check_idempotency(key, digest) is None

            # Save idempotency record
            repo.record_decision(
                idempotency_key=key,
                agent_id="agent_1",
                intent_digest=digest,
                decision="ALLOW",
                response_payload='{"status":"ALLOWED"}',
            )

    # Second check with same key and digest: raises IdempotencyReplayError
    with Session() as session:
        repo = BudgetRepository(session)
        with pytest.raises(IdempotencyReplayError) as exc_info:
            repo.check_idempotency(key, digest)

        record = exc_info.value.record
        assert record is not None
        assert record.idempotency_key == key
        assert record.decision == "ALLOW"
        assert record.intent_digest == digest


def test_idempotency_duplicate_key_different_body(db_session_factory) -> None:
    """Duplicate key with DIFFERENT body digest must raise IdempotencyMismatchError."""
    Session, _ = db_session_factory

    key = "idem_key_002"
    digest_original = hashlib.sha256(b'{"amount":100}').hexdigest()
    digest_tampered = hashlib.sha256(b'{"amount":999}').hexdigest()

    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            repo.record_decision(
                idempotency_key=key,
                agent_id="agent_1",
                intent_digest=digest_original,
                decision="ALLOW",
                response_payload='{"status":"ALLOWED"}',
            )

    # Replay with altered body
    with Session() as session:
        repo = BudgetRepository(session)
        with pytest.raises(IdempotencyMismatchError) as exc_info:
            repo.check_idempotency(key, digest_tampered)

        assert "mutated parameters" in str(exc_info.value)


def test_step_up_approval_and_replay(db_session_factory) -> None:
    """Step-up approval works once; replayed approval raises InvalidApprovalStateError."""
    Session, _ = db_session_factory

    intent_digest = hashlib.sha256(b'{"vendor":"Acme Corp","amount":5000}').hexdigest()
    request_id = "req_step_up_1"
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=15)

    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            repo.create_step_up_approval(
                request_id=request_id,
                idempotency_key="key_step_1",
                expected_digest=intent_digest,
                intent_payload='{"vendor":"Acme Corp","amount":5000}',
                expires_at_utc=expires_at,
            )

    # Approve once
    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            approved_record = repo.approve_step_up(
                request_id=request_id,
                provided_digest=intent_digest,
                approver_id="human_supervisor@astrax.io",
                now_utc=now + timedelta(minutes=1),
            )
        assert approved_record.status == ApprovalStatus.APPROVED.value
        assert approved_record.approver_id == "human_supervisor@astrax.io"

    # Replay approval -> must raise InvalidApprovalStateError
    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            with pytest.raises(InvalidApprovalStateError) as exc_info:
                repo.approve_step_up(
                    request_id=request_id,
                    provided_digest=intent_digest,
                    approver_id="human_supervisor@astrax.io",
                    now_utc=now + timedelta(minutes=2),
                )
            assert "already in state 'APPROVED'" in str(exc_info.value)


def test_step_up_edited_intent_after_approval(db_session_factory) -> None:
    """If intent is edited after approval request, verification raises
    ApprovalDigestMismatchError.
    """
    Session, _ = db_session_factory

    original_digest = hashlib.sha256(b'{"action":"transfer","to":"safe_vendor"}').hexdigest()
    edited_digest = hashlib.sha256(b'{"action":"transfer","to":"attacker_account"}').hexdigest()
    request_id = "req_step_up_2"
    now = datetime.now(UTC)

    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            repo.create_step_up_approval(
                request_id=request_id,
                idempotency_key="key_step_2",
                expected_digest=original_digest,
                intent_payload='{"action":"transfer","to":"safe_vendor"}',
                expires_at_utc=now + timedelta(minutes=10),
            )

    # Attempting to approve using the edited intent digest fails
    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            with pytest.raises(ApprovalDigestMismatchError) as exc_info:
                repo.approve_step_up(
                    request_id=request_id,
                    provided_digest=edited_digest,
                    approver_id="human_supervisor@astrax.io",
                    now_utc=now + timedelta(minutes=1),
                )
            assert "Provided digest" in str(exc_info.value)


def test_step_up_expired_approval(db_session_factory) -> None:
    """Approval attempt after expires_at raises ApprovalExpiredError."""
    Session, _ = db_session_factory

    intent_digest = hashlib.sha256(b'{"action":"test"}').hexdigest()
    request_id = "req_step_up_3"
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=5)

    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            repo.create_step_up_approval(
                request_id=request_id,
                idempotency_key="key_step_3",
                expected_digest=intent_digest,
                intent_payload='{"action":"test"}',
                expires_at_utc=expires_at,
            )

    # Attempt approve at now + 6 minutes (expired)
    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            with pytest.raises(ApprovalExpiredError) as exc_info:
                repo.approve_step_up(
                    request_id=request_id,
                    provided_digest=intent_digest,
                    approver_id="supervisor",
                    now_utc=now + timedelta(minutes=6),
                )
            assert "expired at" in str(exc_info.value)


def test_budget_release_confirmed_failure_vs_unknown(db_session_factory) -> None:
    """Release ONLY on confirmed failure. UNKNOWN outcome goes to RECONCILE, never released."""
    Session, _ = db_session_factory
    agent_id = "agent_rel_test"

    with Session() as session, session.begin():
        session.add(
            AgentBudgetModel(
                agent_id=agent_id,
                mandate_id="man_rel",
                currency="USD",
                allocated_minor=1000,
                spent_minor=0,
                reserved_minor=0,
            )
        )

    # 1. Reserve 200 minor units
    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            res1 = repo.reserve_budget(
                agent_id=agent_id,
                amount_minor=200,
                currency="USD",
                idempotency_key="res_key_1",
                intent_digest="digest_1",
            )
            res1_id = res1.reservation_id

    with Session() as session:
        b = session.query(AgentBudgetModel).filter_by(agent_id=agent_id).one()
        assert b.reserved_minor == 200
        assert b.available_minor == 800

    # 2. Release on confirmed failure -> funds restored
    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            repo.release_reservation(
                reservation_id=res1_id,
                confirmed_failure=True,
            )

    with Session() as session:
        b = session.query(AgentBudgetModel).filter_by(agent_id=agent_id).one()
        assert b.reserved_minor == 0
        assert b.available_minor == 1000
        r = session.query(BudgetReservationModel).filter_by(reservation_id=res1_id).one()
        assert r.status == ReservationStatus.RELEASED.value

    # 3. Reserve 300 minor units
    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            res2 = repo.reserve_budget(
                agent_id=agent_id,
                amount_minor=300,
                currency="USD",
                idempotency_key="res_key_2",
                intent_digest="digest_2",
            )
            res2_id = res2.reservation_id

    with Session() as session:
        b = session.query(AgentBudgetModel).filter_by(agent_id=agent_id).one()
        assert b.reserved_minor == 300
        assert b.available_minor == 700

    # 4. Release on UNKNOWN outcome (confirmed_failure=False, e.g. network timeout)
    # MUST transition to RECONCILE and funds MUST NOT be released!
    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            repo.release_reservation(
                reservation_id=res2_id,
                confirmed_failure=False,
            )

    with Session() as session:
        b = session.query(AgentBudgetModel).filter_by(agent_id=agent_id).one()
        # Reserved minor STILL 300 (not returned to available pool!)
        assert b.reserved_minor == 300
        assert b.available_minor == 700
        r = session.query(BudgetReservationModel).filter_by(reservation_id=res2_id).one()
        assert r.status == ReservationStatus.RECONCILE.value


def test_budget_confirm_settlement(db_session_factory) -> None:
    """Settling a reservation moves reserved_minor into spent_minor."""
    Session, _ = db_session_factory
    agent_id = "agent_settle_test"

    with Session() as session, session.begin():
        session.add(
            AgentBudgetModel(
                agent_id=agent_id,
                mandate_id="man_settle",
                currency="USD",
                allocated_minor=1000,
                spent_minor=0,
                reserved_minor=0,
            )
        )

    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            res = repo.reserve_budget(
                agent_id=agent_id,
                amount_minor=450,
                currency="USD",
                idempotency_key="res_key_settle",
                intent_digest="digest_settle",
            )
            res_id = res.reservation_id

    with Session() as session:
        repo = BudgetRepository(session)
        with session.begin():
            repo.confirm_reservation(res_id)

    with Session() as session:
        b = session.query(AgentBudgetModel).filter_by(agent_id=agent_id).one()
        assert b.allocated_minor == 1000
        assert b.spent_minor == 450
        assert b.reserved_minor == 0
        assert b.available_minor == 550
        r = session.query(BudgetReservationModel).filter_by(reservation_id=res_id).one()
        assert r.status == ReservationStatus.CONFIRMED.value


def test_ledger_append_and_chain_verification(db_session_factory) -> None:
    """Ledger events chain cryptographic hashes correctly."""
    Session, _ = db_session_factory

    now = datetime.now(UTC)
    with Session() as session:
        ledger = DatabaseLedgerAdapter(session)
        with session.begin():
            for i in range(5):
                intent = _create_dummy_intent(amount_minor=100 * (i + 1), seq=i)
                result = _create_dummy_result()
                ledger.append_event(
                    event_type="DECISION_RECORDED",
                    intent=intent,
                    result=result,
                    recorded_at_utc=now + timedelta(seconds=i),
                )

    with Session() as session:
        ledger = DatabaseLedgerAdapter(session)
        is_valid, msg = ledger.verify_chain()
        assert is_valid is True
        assert "5 events verified" in msg


def test_ledger_tampered_payload_detected(db_session_factory) -> None:
    """Tampering with an existing ledger row payload causes verification to fail."""
    Session, engine = db_session_factory

    now = datetime.now(UTC)
    with Session() as session:
        ledger = DatabaseLedgerAdapter(session)
        with session.begin():
            for i in range(4):
                intent = _create_dummy_intent(amount_minor=100 * (i + 1), seq=i)
                result = _create_dummy_result()
                ledger.append_event(
                    event_type="PAYMENT_SUBMITTED",
                    intent=intent,
                    result=result,
                    recorded_at_utc=now + timedelta(seconds=i),
                )

    # Disable trigger temporarily to simulate raw disk/DB compromise tampering
    with engine.connect() as conn:
        conn.execute(text("DROP TRIGGER IF EXISTS trg_no_update_ledger;"))
        conn.execute(
            text("UPDATE ledger_events SET payload_json = :val WHERE event_seq = 2"),
            {"val": '{"amount":999999}'},
        )
        conn.commit()

    with Session() as session:
        ledger = DatabaseLedgerAdapter(session)
        is_valid, msg = ledger.verify_chain()
        assert is_valid is False
        assert "Event hash mismatch" in msg
        assert "row modified" in msg


def test_ledger_deleted_row_detected(db_session_factory) -> None:
    """Deleting a row causes sequence gap and chain verification failure."""
    Session, engine = db_session_factory

    now = datetime.now(UTC)
    with Session() as session:
        ledger = DatabaseLedgerAdapter(session)
        with session.begin():
            for i in range(4):
                intent = _create_dummy_intent(amount_minor=100 * (i + 1), seq=i)
                result = _create_dummy_result()
                ledger.append_event(
                    event_type="PAYMENT_SUBMITTED",
                    intent=intent,
                    result=result,
                    recorded_at_utc=now + timedelta(seconds=i),
                )

    # Disable trigger temporarily to simulate raw deletion compromise
    with engine.connect() as conn:
        conn.execute(text("DROP TRIGGER IF EXISTS trg_no_delete_ledger;"))
        conn.execute(text("DELETE FROM ledger_events WHERE event_seq = 2;"))
        conn.commit()

    with Session() as session:
        ledger = DatabaseLedgerAdapter(session)
        is_valid, msg = ledger.verify_chain()
        assert is_valid is False
        assert "Sequence gap detected" in msg
        assert "expected seq 2, got 3" in msg


def test_ledger_database_triggers_prevent_update_and_delete(db_session_factory) -> None:
    """Database triggers raise and reject UPDATE and DELETE on ledger_events."""
    Session, engine = db_session_factory

    with Session() as session:
        ledger = DatabaseLedgerAdapter(session)
        with session.begin():
            intent = _create_dummy_intent(amount_minor=50, seq=1)
            result = _create_dummy_result()
            ledger.append_event(
                event_type="INIT",
                intent=intent,
                result=result,
                recorded_at_utc=datetime.now(UTC),
            )

    # Attempt UPDATE -> trigger must abort
    with engine.connect() as conn:
        with pytest.raises(Exception) as exc_info:
            conn.execute(
                text("UPDATE ledger_events SET agent_id = 'malicious' WHERE event_seq = 1;")
            )
            conn.commit()
        assert "ledger_events is append-only" in str(exc_info.value).lower()

    # Attempt DELETE -> trigger must abort
    with engine.connect() as conn:
        with pytest.raises(Exception) as exc_info:
            conn.execute(text("DELETE FROM ledger_events WHERE event_seq = 1;"))
            conn.commit()
        assert "ledger_events is append-only" in str(exc_info.value).lower()
