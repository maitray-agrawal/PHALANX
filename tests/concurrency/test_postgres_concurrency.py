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

from app.application.dtos import CreateMandateCommand
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
    db_password = os.getenv("POSTGRES_PASSWORD", "")
    default_url = (
        f"postgresql+psycopg://phalanx_app:{db_password}@127.0.0.1:5433/phalanx_db"
        if db_password
        else "postgresql+psycopg://phalanx_app@127.0.0.1:5433/phalanx_db"
    )
    db_url = os.getenv("DATABASE_URL", default_url)
    if "postgres" not in db_url:
        return None
    try:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
        )
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


def test_postgres_restart_persistence_budgets_idempotency_approvals_ledger(pg_session_factory):
    """Verify persistence of budgets, idempotency, approvals, and ledger across service restart."""
    from app.application.dtos import AuthorizeTransactionCommand
    from app.application.services import AuthorizationService, MandateService
    from app.domain.models import DecisionOutcome
    from app.infrastructure.clock import SystemUtcClock
    from app.infrastructure.db_ledger_repo import DatabaseLedgerAdapter
    from app.infrastructure.paypal import FakePaymentRail

    clock = SystemUtcClock()
    mandate_svc = MandateService(clock=clock)
    ledger_1 = DatabaseLedgerAdapter(session_factory=pg_session_factory)
    rail_1 = FakePaymentRail()

    service_1 = AuthorizationService(
        clock=clock,
        ledger=ledger_1,
        mandate_service=mandate_svc,
        payment_rail=rail_1,
        db_session_factory=pg_session_factory,
    )

    agent_id = f"agent-persist-{uuid.uuid4().hex[:8]}"
    mandate = mandate_svc.create_mandate(
        CreateMandateCommand(
            mandate_id=f"mandate-{agent_id}",
            principal_id="demo-principal",
            agent_id=agent_id,
            single_limit_minor=100_000,
            instant_threshold_minor=100_000,
            lifetime_budget_minor=100_000,
            allow_unregistered_payees=True,
        )
    )

    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        repo.get_or_create_budget(
            agent_id=agent_id,
            mandate_id=mandate.mandate_id,
            currency="USD",
            allocated_minor=100_000,
        )

    # 1. Authorize transaction on instance 1 ($25.00 -> 2,500 minor units)
    idem_key = f"idem-persist-{uuid.uuid4().hex}"
    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-persist-1",
        amount_minor=2_500,
        currency="USD",
        purpose="Persistent subscription payment",
        idempotency_key=idem_key,
    )
    resp_1 = service_1.authorize(cmd)
    assert resp_1.decision == DecisionOutcome.ALLOW
    assert resp_1.event_id != ""

    # 2. Simulate complete service shutdown & restart (new instance, new ledger adapter)
    del service_1
    del ledger_1

    ledger_2 = DatabaseLedgerAdapter(session_factory=pg_session_factory)
    service_2 = AuthorizationService(
        clock=clock,
        ledger=ledger_2,
        mandate_service=mandate_svc,
        payment_rail=FakePaymentRail(),
        db_session_factory=pg_session_factory,
    )

    # Verify budget spent persisted
    assert service_2.get_lifetime_spent(agent_id) == 2_500

    # Verify idempotency decision replay persisted
    resp_replay = service_2.authorize(cmd)
    assert resp_replay.decision == DecisionOutcome.ALLOW
    assert "Idempotency match" in resp_replay.reasons[0]

    # Verify ledger integrity persisted
    is_valid, msg = ledger_2.verify_chain()
    assert is_valid is True
    assert "events verified" in msg


def test_postgres_two_service_instances_sharing_budget(pg_session_factory):
    """Verify that two independent service instances share a single authoritative budget."""
    from app.application.dtos import AuthorizeTransactionCommand
    from app.application.services import AuthorizationService, MandateService
    from app.domain.models import DecisionOutcome
    from app.infrastructure.clock import SystemUtcClock
    from app.infrastructure.db_ledger_repo import DatabaseLedgerAdapter
    from app.infrastructure.paypal import FakePaymentRail

    clock = SystemUtcClock()
    mandate_svc = MandateService(clock=clock)
    agent_id = f"agent-share-{uuid.uuid4().hex[:8]}"
    mandate = mandate_svc.create_mandate(
        CreateMandateCommand(
            mandate_id=f"mandate-{agent_id}",
            principal_id="demo-principal",
            agent_id=agent_id,
            single_limit_minor=100_000,
            instant_threshold_minor=100_000,
            lifetime_budget_minor=10_000,
            allow_unregistered_payees=True,
        )
    )

    # Seed budget with $100.00 (10,000 minor units)
    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        repo.get_or_create_budget(
            agent_id=agent_id,
            mandate_id=mandate.mandate_id,
            currency="USD",
            allocated_minor=10_000,
        )

    # Spin up two concurrent service instances connected to the same PostgreSQL DB
    instance_a = AuthorizationService(
        clock=clock,
        ledger=DatabaseLedgerAdapter(session_factory=pg_session_factory),
        mandate_service=mandate_svc,
        payment_rail=FakePaymentRail(),
        db_session_factory=pg_session_factory,
    )
    instance_b = AuthorizationService(
        clock=clock,
        ledger=DatabaseLedgerAdapter(session_factory=pg_session_factory),
        mandate_service=mandate_svc,
        payment_rail=FakePaymentRail(),
        db_session_factory=pg_session_factory,
    )

    # Instance A spends $60.00 (6,000 minor units) -> ALLOW
    cmd_a = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-share-a",
        amount_minor=6_000,
        currency="USD",
        purpose="Instance A spend",
        idempotency_key=f"share-a-{uuid.uuid4().hex}",
    )
    res_a = instance_a.authorize(cmd_a)
    assert res_a.decision == DecisionOutcome.ALLOW

    # Instance B immediately observes the spent budget
    assert instance_b.get_lifetime_spent(agent_id) == 6_000

    # Instance B attempts to spend $50.00 (60 + 50 = 110 > 100) -> DENY
    cmd_b_fail = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-share-b",
        amount_minor=5_000,
        currency="USD",
        purpose="Instance B overspend",
        idempotency_key=f"share-b-fail-{uuid.uuid4().hex}",
    )
    res_b_fail = instance_b.authorize(cmd_b_fail)
    assert res_b_fail.decision == DecisionOutcome.DENY

    # Instance B spends the exact remaining $40.00 (4,000 minor units) -> ALLOW
    cmd_b_ok = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-share-b",
        amount_minor=4_000,
        currency="USD",
        purpose="Instance B exact spend",
        idempotency_key=f"share-b-ok-{uuid.uuid4().hex}",
    )
    res_b_ok = instance_b.authorize(cmd_b_ok)
    assert res_b_ok.decision == DecisionOutcome.ALLOW

    # Both instances reflect total spent of exactly 10,000 minor units
    assert instance_a.get_lifetime_spent(agent_id) == 10_000
    assert instance_b.get_lifetime_spent(agent_id) == 10_000


def test_postgres_50_parallel_requests_on_one_budget(pg_session_factory):
    """Verify 50 parallel requests on one budget strictly respect database constraints."""
    from app.application.dtos import AuthorizeTransactionCommand
    from app.application.services import AuthorizationService, MandateService
    from app.domain.models import DecisionOutcome
    from app.infrastructure.clock import SystemUtcClock
    from app.infrastructure.db_ledger_repo import DatabaseLedgerAdapter
    from app.infrastructure.paypal import FakePaymentRail

    clock = SystemUtcClock()
    mandate_svc = MandateService(clock=clock)
    agent_id = f"agent-parallel-{uuid.uuid4().hex[:8]}"
    mandate = mandate_svc.create_mandate(
        CreateMandateCommand(
            mandate_id=f"mandate-{agent_id}",
            principal_id="demo-principal",
            agent_id=agent_id,
            single_limit_minor=100_000,
            instant_threshold_minor=100_000,
            lifetime_budget_minor=50_000,
            allow_unregistered_payees=True,
        )
    )

    # Total allocated budget: $500.00 (50,000 minor units)
    # Each request: $20.00 (2,000 minor units)
    # Exactly 25 requests should succeed (25 * 2,000 = 50,000)
    # The remaining 25 requests must be DENIED (LIFETIME_BUDGET_EXCEEDED)
    with pg_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        repo.get_or_create_budget(
            agent_id=agent_id,
            mandate_id=mandate.mandate_id,
            currency="USD",
            allocated_minor=50_000,
        )

    service = AuthorizationService(
        clock=clock,
        ledger=DatabaseLedgerAdapter(session_factory=pg_session_factory),
        mandate_service=mandate_svc,
        payment_rail=FakePaymentRail(),
        db_session_factory=pg_session_factory,
    )

    decisions: list[DecisionOutcome] = []

    def run_auth(index: int) -> DecisionOutcome:
        cmd = AuthorizeTransactionCommand(
            agent_id=agent_id,
            recipient_id=f"vendor-p-{index}",
            amount_minor=2_000,
            currency="USD",
            purpose=f"Parallel request {index}",
            idempotency_key=f"parallel-req-{index}-{uuid.uuid4().hex}",
        )
        resp = service.authorize(cmd)
        return resp.decision

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(run_auth, i) for i in range(50)]
        for f in futures:
            decisions.append(f.result())

    allowed_count = sum(1 for d in decisions if d == DecisionOutcome.ALLOW)
    denied_count = sum(1 for d in decisions if d == DecisionOutcome.DENY)

    assert allowed_count == 25, f"Expected exactly 25 ALLOW, got {allowed_count}"
    assert denied_count == 25, f"Expected exactly 25 DENY, got {denied_count}"

    with pg_session_factory() as session:
        stmt = select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        budget = session.scalar(stmt)
        assert budget is not None
        assert budget.spent_minor == 50_000
        assert budget.reserved_minor == 0
        assert budget.available_minor == 0
