"""Failing tests demonstrating transaction boundary, locking, idempotency,
and state transition flaws.

These tests prove the findings identified during the security review of:
- Manual 56.13 (Single-Transaction Reservation & Money Safety)
- Manual 56.14 (Idempotency & Replay Protection)
- Manual 56.17 (Request Lifecycle State Machine)

DO NOT FIX THE UNDERLYING CODE PER AUDIT INSTRUCTIONS.
"""

import inspect
import os
import tempfile
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.dtos import ApprovalCommand, AuthorizeTransactionCommand, CreateMandateCommand
from app.application.services import AuthorizationService, MandateService
from app.domain.models import DecisionOutcome, TransactionIntent
from app.domain.ports import ClockPort, LedgerPort, PaymentRail, PaymentResult
from app.domain.state_machine import RequestState, can_transition
from app.infrastructure.db_budget_repo import (
    BudgetRepository,
    IdempotencyReplayError,
    InvalidApprovalStateError,
)
from app.infrastructure.db_schema import create_schema
from app.infrastructure.models import (
    AgentBudgetModel,
)


class MockClock(ClockPort):
    def __init__(self, start: datetime | None = None) -> None:
        self.t = start or datetime.now(UTC)

    def now_utc(self) -> datetime:
        return self.t


class MemoryLedger(LedgerPort):
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, event_type: str, intent: Any, result: Any, recorded_at_utc: Any) -> str:
        _ = recorded_at_utc
        eid = f"evt_{len(self.events) + 1:06d}"
        self.events.append(
            {"event_id": eid, "type": event_type, "intent": intent, "result": result}
        )
        return eid


class MockPaymentRail(PaymentRail):
    def __init__(self) -> None:
        self.dispatched: list[TransactionIntent] = []

    def pay(self, intent: TransactionIntent) -> PaymentResult:
        self.dispatched.append(intent)
        return PaymentResult(
            success=True,
            transaction_id=f"tx_{len(self.dispatched)}",
            status="COMPLETED",
            details={},
        )

    def lookup(self, transaction_id: str) -> PaymentResult:
        return PaymentResult(
            success=True,
            transaction_id=transaction_id,
            status="COMPLETED",
            details={},
        )

    def normalize_error(self, raw_error: Any) -> str:
        return str(raw_error)

    def verify_webhook(self, headers: dict[str, str], body_bytes: bytes) -> bool:
        _ = (headers, body_bytes)
        return True


@pytest.fixture
def db_session_factory() -> Any:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    create_schema(engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


# -------------------------------------------------------------------------
# Finding 1: Double Spend via Non-Idempotent Step-Up Retry
# -------------------------------------------------------------------------
def test_finding_1_double_spend_on_step_up_retry() -> None:
    """Proves that retrying an authorized step-up payment executes the payment a second time.

    File: app/application/services.py:620-660
    Vulnerability: execute_approval() dispatches payment but does not update
    _idempotency_records[key] from STEP_UP to ALLOW. Re-submitting the same
    request returns STEP_UP, recreates the pending step-up, and allows another approval.
    """
    clock = MockClock()
    ledger = MemoryLedger()
    rail = MockPaymentRail()
    mandates = MandateService(clock=clock)
    authz = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandates,
        payment_rail=rail,
    )

    # 1. First authorization: $1,000 exceeds $500 instant threshold -> STEP_UP
    cmd = AuthorizeTransactionCommand(
        agent_id="agent-auto-1",
        recipient_id="vendor-1",
        amount_minor=100_000,
        currency="USD",
        purpose="Server procurement",
        idempotency_key="key-step-up-double-spend",
    )
    res1 = authz.authorize(cmd)
    assert res1.decision == DecisionOutcome.STEP_UP

    # 2. Human supervisor approves -> payment dispatches (count = 1)
    appr_cmd = ApprovalCommand(
        request_id=res1.request_id,
        expected_digest=res1.intent_digest,
        decision=DecisionOutcome.ALLOW,
        reason="Approved by supervisor",
    )
    appr_res = authz.execute_approval(appr_cmd)
    assert appr_res.decision == DecisionOutcome.ALLOW
    assert len(rail.dispatched) == 1

    # 3. Client retries the request with identical idempotency key and body
    res2 = authz.authorize(cmd)

    # EXPECTED BEHAVIOR (Idempotency):
    # The retry must return the resolved ALLOW decision, NOT recreate a pending step-up!
    assert res2.decision == DecisionOutcome.ALLOW, (
        f"Expected cached ALLOW decision on retry, but got {res2.decision}"
    )
    # The approved request must not be in pending step-ups
    pending_ids = [p.request_id for p in authz.get_pending_step_ups()]
    assert res1.request_id not in pending_ids, (
        "Pending step-up queue should not contain duplicate request for "
        "already-approved transaction"
    )
    assert len(rail.dispatched) == 1, "Payment rail must not execute a second time on retry"


# -------------------------------------------------------------------------
# Finding 2: Double Spend & Lost Updates in confirm_reservation
# -------------------------------------------------------------------------
def test_finding_2_confirm_reservation_double_deduction(db_session_factory: Any) -> None:
    """Proves that confirm_reservation() has no state validation and double-deducts on replay.

    File: app/infrastructure/db_budget_repo.py:170-193
    Vulnerability: Calling confirm_reservation twice decrements reserved_minor twice
    and increments spent_minor twice, corrupting budget counters.
    """
    agent_id = "agent-confirm-race"

    with db_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        session.add(
            AgentBudgetModel(
                agent_id=agent_id,
                mandate_id="man-1",
                currency="USD",
                allocated_minor=1000,
                spent_minor=0,
                reserved_minor=0,
            )
        )
        res = repo.reserve_budget(
            agent_id=agent_id,
            amount_minor=200,
            currency="USD",
            idempotency_key="res-confirm-1",
            intent_digest="digest-1",
        )
        res_id = res.reservation_id

    # First confirmation: reserved 200 -> spent 200
    with db_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        repo.confirm_reservation(res_id)

    with db_session_factory() as session:
        b = session.query(AgentBudgetModel).filter_by(agent_id=agent_id).one()
        assert b.spent_minor == 200
        assert b.reserved_minor == 0

    # Second confirmation (replayed webhook / retry)
    # EXPECTED BEHAVIOR:
    # Must raise InvalidApprovalStateError or be idempotent without altering balances.
    with db_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        with pytest.raises(InvalidApprovalStateError, match="already in state 'CONFIRMED'"):
            repo.confirm_reservation(res_id)


# -------------------------------------------------------------------------
# Finding 3: Phantom Budget Leakage in release_reservation
# -------------------------------------------------------------------------
def test_finding_3_release_already_confirmed_reservation(db_session_factory: Any) -> None:
    """Proves that release_reservation() can release an already CONFIRMED reservation.

    File: app/infrastructure/db_budget_repo.py:194-230
    Vulnerability: release_reservation() does not check if reservation is CONFIRMED,
    allowing a settled transaction to be 'released' back into the budget pool.
    """
    agent_id = "agent-release-leak"

    with db_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        session.add(
            AgentBudgetModel(
                agent_id=agent_id,
                mandate_id="man-2",
                currency="USD",
                allocated_minor=1000,
                spent_minor=0,
                reserved_minor=0,
            )
        )
        res = repo.reserve_budget(
            agent_id=agent_id,
            amount_minor=300,
            currency="USD",
            idempotency_key="res-rel-1",
            intent_digest="digest-rel-1",
        )
        res_id = res.reservation_id
        repo.confirm_reservation(res_id)

    with db_session_factory() as session:
        b = session.query(AgentBudgetModel).filter_by(agent_id=agent_id).one()
        assert b.spent_minor == 300
        assert b.reserved_minor == 0

    # Attempt to release the already CONFIRMED reservation
    # EXPECTED BEHAVIOR:
    # Releasing an already settled/confirmed reservation must be rejected!
    with db_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        with pytest.raises(ValueError, match=r"Cannot release reservation .* in state 'CONFIRMED'"):
            repo.release_reservation(reservation_id=res_id, confirmed_failure=True)


# -------------------------------------------------------------------------
# Finding 4: Non-Idempotent Retry Crash in reserve_budget
# -------------------------------------------------------------------------
def test_finding_4_reserve_budget_integrity_error_on_retry(db_session_factory: Any) -> None:
    """Proves reserve_budget crashes with IntegrityError on client retry before decision recorded.

    File: app/infrastructure/db_budget_repo.py:124-126
    Vulnerability: check_idempotency only checks IdempotencyModel, not budget_reservations.
    A retry before record_decision triggers unhandled SQLite/PG IntegrityError.
    """
    agent_id = "agent-idem-crash"

    with db_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        session.add(
            AgentBudgetModel(
                agent_id=agent_id,
                mandate_id="man-3",
                currency="USD",
                allocated_minor=1000,
                spent_minor=0,
                reserved_minor=0,
            )
        )
        # First call reserves budget
        repo.reserve_budget(
            agent_id=agent_id,
            amount_minor=150,
            currency="USD",
            idempotency_key="key-idem-retry",
            intent_digest="digest-idem-1",
        )

    # Client retries with identical parameters (e.g. network hiccup before caller receives res)
    # EXPECTED BEHAVIOR:
    # Must raise IdempotencyReplayError or return existing reservation,
    # NOT crash with DB IntegrityError.
    with db_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        with pytest.raises(IdempotencyReplayError):
            repo.reserve_budget(
                agent_id=agent_id,
                amount_minor=150,
                currency="USD",
                idempotency_key="key-idem-retry",
                intent_digest="digest-idem-1",
            )


# -------------------------------------------------------------------------
# Finding 5: Cross-Agent Budget Collision in AuthorizationService
# -------------------------------------------------------------------------
def test_finding_5_cross_agent_budget_collision() -> None:
    """Proves AuthorizationService tracks spent budget globally rather than per-agent.

    File: app/application/services.py:377-378, 478-482
    Vulnerability: self._lifetime_spent is a single scalar. Agent 1's spending
    wrongfully depletes Agent 2's distinct mandate lifetime budget.
    """
    clock = MockClock()
    ledger = MemoryLedger()
    rail = MockPaymentRail()
    mandates = MandateService(clock=clock)
    authz = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandates,
        payment_rail=rail,
    )

    # Create two separate mandates for two different agents
    # Agent 1: $10,000 lifetime cap ($100 instant)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-agent-1",
            principal_id="principal-1",
            agent_id="agent-1",
            single_limit_minor=500_000,
            instant_threshold_minor=100_000,
            lifetime_budget_minor=1_000_000,
            currency="USD",
            allowed_payees=[],
            allowed_purposes=[],
            valid_days=30,
        )
    )
    # Agent 2: $2,000 lifetime cap ($100 instant)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-agent-2",
            principal_id="principal-1",
            agent_id="agent-2",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=200_000,
            currency="USD",
            allowed_payees=[],
            allowed_purposes=[],
            valid_days=30,
        )
    )

    # Agent 1 spends $3,000 via 3 instant payments of $900
    for i in range(3):
        res = authz.authorize(
            AuthorizeTransactionCommand(
                agent_id="agent-1",
                recipient_id="vendor-common",
                amount_minor=90_000,
                currency="USD",
                purpose=f"Agent 1 purchase {i}",
                idempotency_key=f"agent1-tx-{i}",
            )
        )
        assert res.decision == DecisionOutcome.ALLOW

    # Now Agent 2 requests $500 (instant payment, well within its $2,000 budget)
    res_agent_2 = authz.authorize(
        AuthorizeTransactionCommand(
            agent_id="agent-2",
            recipient_id="vendor-common",
            amount_minor=50_000,
            currency="USD",
            purpose="Agent 2 purchase",
            idempotency_key="agent2-tx-1",
        )
    )

    # EXPECTED BEHAVIOR:
    # Agent 2 has spent $0 of its $2,000 budget; $500 request MUST be ALLOWED.
    assert res_agent_2.decision == DecisionOutcome.ALLOW, (
        f"Agent 2 was denied due to Agent 1's spend! Reasons: {res_agent_2.reasons}"
    )


# -------------------------------------------------------------------------
# Finding 6: Missing RECONCILE State & Ambiguous Failure Transition
# -------------------------------------------------------------------------
def test_finding_6_missing_reconcile_state_in_lifecycle() -> None:
    """Proves RequestState lacks the RECONCILE state required by Manual 56.13 and 56.17.

    File: app/domain/state_machine.py:10-25
    Vulnerability: Manual 56.13 dictates ambiguous outcomes must transition to RECONCILE.
    RequestState lacks RECONCILE and EXECUTING can only transition to SETTLED or FAILED.
    """
    # Verify RECONCILE exists on RequestState enum
    reconcile_member = getattr(RequestState, "RECONCILE", None)
    assert reconcile_member is not None, (
        "RequestState lacks RECONCILE enum member required for ambiguous outcomes (Manual 56.13)"
    )
    assert can_transition(RequestState.EXECUTING, reconcile_member), (
        "State machine must permit transition from EXECUTING to RECONCILE upon ambiguous outcome"
    )


# -------------------------------------------------------------------------
# Finding 7: Missing Row Lock (FOR UPDATE) in approve_step_up
# -------------------------------------------------------------------------
def test_finding_7_missing_row_lock_on_step_up_approval() -> None:
    """Proves approve_step_up lacks row-level locking (SELECT ... FOR UPDATE).

    File: app/infrastructure/db_budget_repo.py:284-287
    Vulnerability: Unlike reserve_budget, approve_step_up executes a plain SELECT
    without with_for_update(). Two concurrent approvers can race past the PENDING check
    and approve the same request twice, causing double-disbursement.
    """
    from app.infrastructure.db_budget_repo import BudgetRepository

    src = inspect.getsource(BudgetRepository.approve_step_up)
    # The source code must include row-level locking with_for_update
    assert "with_for_update" in src, (
        "BudgetRepository.approve_step_up performs a naked SELECT without row-level lock, "
        "allowing concurrent approval races."
    )
