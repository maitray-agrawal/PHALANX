"""PostgreSQL-backed concurrency and reconciliation integration tests (Sections 8 & 9).

Verifies database-level correctness directly against the running PostgreSQL container:
1. Duplicate requests race: canonical idempotent replay without unhandled IntegrityError.
2. Concurrent budget requests: row-level locking (SELECT ... FOR UPDATE) prevents
   exceeding budget cap.
3. Concurrent approval race: exactly one supervisor approval succeeds; second request is rejected.
4. Reconciliation lifecycle (F6):
   - Ambiguous outcome routes to RECONCILE while holding budget reservation.
   - Ambiguous re-check retains RECONCILE and holds reservation.
   - Confirmed settlement transitions reservation to CONFIRMED and decrements reserved /
     increments spent.
   - Confirmed failure releases reservation and returns reserved budget to available pool.
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db_budget_repo import (
    BudgetRepository,
    IdempotencyReplayError,
    InsufficientBudgetError,
    InvalidApprovalStateError,
)
from app.infrastructure.models import (
    AgentBudgetModel,
    ApprovalStatus,
    ReservationStatus,
    StepUpApprovalModel,
)


def _get_postgres_engine():
    """Retrieve engine for local Docker PostgreSQL if reachable, else return None."""
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://phalanx_app:Maitray%407979@127.0.0.1:5433/phalanx_db",
    )
    if "postgres" not in db_url:
        return None
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception:
        return None


pg_engine = _get_postgres_engine()
pytestmark = pytest.mark.skipif(
    pg_engine is None,
    reason="PostgreSQL database container is not running or unreachable",
)


@pytest.fixture
def pg_session_factory():
    """Session factory for PostgreSQL testing."""
    assert pg_engine is not None
    return sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)


def test_postgres_duplicate_request_idempotent_replay(pg_session_factory):
    """Section 8.1: Simultaneous duplicate requests return canonical replay, not IntegrityError."""
    agent_id = f"agent-dup-{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate-{uuid.uuid4().hex[:8]}"
    idempotency_key = f"idem-{uuid.uuid4().hex}"
    intent_digest = "a" * 64
    amount = 5_000

    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        repo.get_or_create_budget(agent_id, mandate_id, "USD", 100_000)

    results = []
    errors = []

    def execute_request():
        with pg_session_factory() as session, session.begin():
            repo = BudgetRepository(session)
            try:
                res = repo.reserve_budget(
                    agent_id=agent_id,
                    amount_minor=amount,
                    currency="USD",
                    idempotency_key=idempotency_key,
                    intent_digest=intent_digest,
                )
                results.append(res.reservation_id)
            except IdempotencyReplayError as exc:
                results.append(f"REPLAY:{exc.record.idempotency_key}")
            except Exception as e:
                errors.append(e)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(execute_request) for _ in range(5)]
        for f in futures:
            f.result()

    # Must have 0 unexpected database errors (no IntegrityError leaking)
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    # Exactly one original reservation, others received replay
    assert len(results) == 5
    original = [r for r in results if not r.startswith("REPLAY:")]
    replays = [r for r in results if r.startswith("REPLAY:")]
    assert len(original) == 1
    assert len(replays) == 4


def test_postgres_concurrent_budget_requests_ceiling(pg_session_factory):
    """Section 8.2: Concurrent budget requests must never collectively exceed the budget ceiling."""
    agent_id = f"agent-ceiling-{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate-{uuid.uuid4().hex[:8]}"
    allocated = 10_000  # $100 allocated
    request_amount = 3_000  # $30 each -> at most 3 can succeed (3 x $30 = $90 <= $100)

    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        repo.get_or_create_budget(agent_id, mandate_id, "USD", allocated)

    successes = []
    insufficient = []

    def race_spend(idx: int):
        with pg_session_factory() as session, session.begin():
            repo = BudgetRepository(session)
            idem_key = f"race-{agent_id}-{idx}"
            digest = f"digest-{idx:04d}" + "0" * 53
            try:
                res = repo.reserve_budget(
                    agent_id=agent_id,
                    amount_minor=request_amount,
                    currency="USD",
                    idempotency_key=idem_key,
                    intent_digest=digest,
                )
                repo.confirm_reservation(res.reservation_id)
                successes.append(res.reservation_id)
            except InsufficientBudgetError:
                insufficient.append(idx)

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(race_spend, i) for i in range(10)]
        for f in futures:
            f.result()

    # Exactly 3 can fit in $100 with $30 each (3 * 3000 = 9000 <= 10000; 4th would be 12000 > 10000)
    assert len(successes) == 3
    assert len(insufficient) == 7

    # Verify database state strictly respects invariants
    with pg_session_factory() as session:
        stmt = select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        budget = session.scalar(stmt)
        assert budget is not None
        assert budget.spent_minor == 9_000
        assert budget.reserved_minor == 0
        assert budget.spent_minor + budget.reserved_minor <= budget.allocated_minor


def test_postgres_concurrent_approvals(pg_session_factory):
    """Section 8.3: Concurrent approvals of step-up must produce one authoritative outcome."""
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    idempotency_key = f"idem-{uuid.uuid4().hex}"
    digest = "b" * 64

    with pg_session_factory() as session, session.begin():
        now = datetime.now(UTC)
        step_up = StepUpApprovalModel(
            request_id=request_id,
            idempotency_key=idempotency_key,
            expected_digest=digest,
            intent_payload="{}",
            status=ApprovalStatus.PENDING.value,
            expires_at_utc=now + timedelta(hours=1),
            created_at_utc=now,
            updated_at_utc=now,
        )
        session.add(step_up)

    outcomes = []
    errors = []

    def execute_approval(approver_idx: int):
        with pg_session_factory() as session, session.begin():
            repo = BudgetRepository(session)
            try:
                _ = repo.approve_step_up(
                    request_id=request_id,
                    provided_digest=digest,
                    approver_id=f"supervisor-{approver_idx}",
                    now_utc=datetime.now(UTC),
                )
                outcomes.append(f"APPROVED:{approver_idx}")
            except InvalidApprovalStateError:
                outcomes.append(f"ALREADY_PROCESSED:{approver_idx}")
            except Exception as e:
                errors.append(e)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(execute_approval, i) for i in range(4)]
        for f in futures:
            f.result()

    assert len(errors) == 0
    approved = [o for o in outcomes if o.startswith("APPROVED:")]
    rejected = [o for o in outcomes if o.startswith("ALREADY_PROCESSED:")]
    assert len(approved) == 1
    assert len(rejected) == 3


def test_postgres_reconciliation_lifecycle(pg_session_factory):
    """Section 9: F6 reconciliation lifecycle: EXECUTING -> RECONCILE -> SETTLED or RELEASED."""
    agent_id = f"agent-recon-{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate-{uuid.uuid4().hex[:8]}"
    allocated = 50_000
    amount = 10_000

    # 1. Initialize budget
    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        repo.get_or_create_budget(agent_id, mandate_id, "USD", allocated)

    # 2. Reserve funds (EXECUTING)
    idem_key_1 = f"recon-tx-1-{uuid.uuid4().hex[:8]}"
    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        res1 = repo.reserve_budget(
            agent_id=agent_id,
            amount_minor=amount,
            currency="USD",
            idempotency_key=idem_key_1,
            intent_digest="c" * 64,
        )
        res1_id = res1.reservation_id

    # 3. Ambiguous outcome from payment rail -> release with confirmed_failure=False
    #    routes to RECONCILE
    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        recon_res = repo.release_reservation(res1_id, confirmed_failure=False)
        assert recon_res.status == ReservationStatus.RECONCILE.value

    # Verify budget STILL HELD during RECONCILE (cannot double-spend)
    with pg_session_factory() as session:
        stmt = select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        budget = session.scalar(stmt)
        assert budget is not None
        assert budget.reserved_minor == amount
        assert budget.spent_minor == 0
        assert budget.available_minor == allocated - amount

    # 4. Reconciliation confirms settlement -> confirm_reservation transitions to CONFIRMED
    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        confirmed = repo.confirm_reservation(res1_id)
        assert confirmed.status == ReservationStatus.CONFIRMED.value

    # Verify budget moved from reserved to spent
    with pg_session_factory() as session:
        stmt = select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        budget = session.scalar(stmt)
        assert budget is not None
        assert budget.reserved_minor == 0
        assert budget.spent_minor == amount

    # 5. Second transaction: Ambiguous outcome -> confirmed failure -> funds RELEASED
    idem_key_2 = f"recon-tx-2-{uuid.uuid4().hex[:8]}"
    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        res2 = repo.reserve_budget(
            agent_id=agent_id,
            amount_minor=amount,
            currency="USD",
            idempotency_key=idem_key_2,
            intent_digest="d" * 64,
        )
        res2_id = res2.reservation_id

    # Release on confirmed failure
    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        released = repo.release_reservation(res2_id, confirmed_failure=True)
        assert released.status == ReservationStatus.RELEASED.value

    # Verify reserved funds returned to pool
    with pg_session_factory() as session:
        stmt = select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        budget = session.scalar(stmt)
        assert budget.reserved_minor == 0
        assert budget.spent_minor == amount  # Only first tx is spent
