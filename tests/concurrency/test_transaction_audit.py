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
    InsufficientBudgetError,
    InvalidApprovalStateError,
)
from app.infrastructure.db_schema import create_schema
from app.infrastructure.models import (
    AgentBudgetModel,
    ReservationStatus,
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


class ConfigurableRail(PaymentRail):
    def __init__(
        self,
        pay_result: PaymentResult,
        lookup_result: PaymentResult | None = None,
    ) -> None:
        self.pay_result = pay_result
        self.lookup_result = lookup_result or pay_result
        self.dispatched: list[TransactionIntent] = []

    def pay(self, intent: TransactionIntent) -> PaymentResult:
        self.dispatched.append(intent)
        return self.pay_result

    def lookup(self, transaction_id: str) -> PaymentResult:
        _ = transaction_id
        return self.lookup_result

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
            allow_unregistered_payees=True,
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
            allow_unregistered_payees=True,
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


# -------------------------------------------------------------------------
# F6 Ambiguous Rail Outcome & Reconciliation Lifecycle Tests (10a - 10f)
# -------------------------------------------------------------------------
def test_f6_timeout_transitions_to_reconcile() -> None:
    """10a: Payment rail timeout must transition authorization lifecycle to RECONCILE."""
    rail = ConfigurableRail(
        pay_result=PaymentResult(
            success=False,
            transaction_id="",
            status="PAYOUT_EXCEPTION",
            details={"error": "ReadTimeout: connection to PayPal timed out"},
        )
    )
    clock = MockClock()
    mandates = MandateService(clock=clock)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-timeout",
            principal_id="principal-corp",
            agent_id="agent-timeout",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=500_000,
            valid_days=7,
            allow_unregistered_payees=True,
        )
    )
    authz = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=rail,
    )

    res = authz.authorize(
        AuthorizeTransactionCommand(
            agent_id="agent-timeout",
            recipient_id="vendor-timeout",
            amount_minor=10_000,
            currency="USD",
            purpose="Software subscription",
            idempotency_key="tx-timeout-1",
        )
    )

    assert res.decision == DecisionOutcome.ALLOW
    assert res.request_state == RequestState.RECONCILE
    assert authz.get_request_state(res.request_id) == RequestState.RECONCILE


def test_f6_5xx_ambiguous_outcome_transitions_to_reconcile() -> None:
    """10b: 5xx server error / gateway timeout must transition lifecycle to RECONCILE."""
    rail = ConfigurableRail(
        pay_result=PaymentResult(
            success=False,
            transaction_id="",
            status="PAYOUT_REJECTED",
            details={
                "error": "503 Service Unavailable: Downstream PayPal gateway timeout",
                "http_status": 503,
            },
        )
    )
    clock = MockClock()
    mandates = MandateService(clock=clock)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-5xx",
            principal_id="principal-corp",
            agent_id="agent-5xx",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=500_000,
            valid_days=7,
            allow_unregistered_payees=True,
        )
    )
    authz = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=rail,
    )

    res = authz.authorize(
        AuthorizeTransactionCommand(
            agent_id="agent-5xx",
            recipient_id="vendor-5xx",
            amount_minor=15_000,
            currency="USD",
            purpose="Hosting fee",
            idempotency_key="tx-5xx-1",
        )
    )

    assert res.decision == DecisionOutcome.ALLOW
    assert res.request_state == RequestState.RECONCILE
    assert authz.get_request_state(res.request_id) == RequestState.RECONCILE


def test_f6_reconcile_confirmed_success_transitions_to_confirmed(db_session_factory: Any) -> None:
    """10c: RECONCILE + confirmed success transitions reservation to CONFIRMED."""
    # 1. DatabaseBudgetRepository level
    with db_session_factory() as session, session.begin():
        session.add(
            AgentBudgetModel(
                agent_id="agent-recon-succ",
                mandate_id="man-succ",
                currency="USD",
                allocated_minor=100_000,
                spent_minor=0,
                reserved_minor=0,
            )
        )
        repo = BudgetRepository(session)
        res = repo.reserve_budget(
            agent_id="agent-recon-succ",
            amount_minor=20_000,
            currency="USD",
            idempotency_key="idemp-succ",
            intent_digest="digest-succ",
        )
        # Transition to RECONCILE (ambiguous outcome)
        res_reconcile = repo.release_reservation(res.reservation_id, confirmed_failure=False)
        assert res_reconcile.status == ReservationStatus.RECONCILE.value

        # Reconcile with confirmed success
        res_confirmed = repo.reconcile_reservation(res.reservation_id, rail_status="SUCCESS")
        assert res_confirmed.status == ReservationStatus.CONFIRMED.value

    with db_session_factory() as session:
        budget = session.query(AgentBudgetModel).filter_by(agent_id="agent-recon-succ").one()
        assert budget.spent_minor == 20_000
        assert budget.reserved_minor == 0

    # 2. AuthorizationService level
    clock = MockClock()
    mandates = MandateService(clock=clock)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="m-recon-succ-svc",
            principal_id="p-corp",
            agent_id="agent-succ-svc",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=500_000,
            valid_days=7,
            allow_unregistered_payees=True,
        )
    )
    rail = ConfigurableRail(
        pay_result=PaymentResult(
            success=False,
            transaction_id="tx_succ_01",
            status="PAYOUT_EXCEPTION",
            details={"error": "Connection reset by peer"},
        ),
        lookup_result=PaymentResult(
            success=True,
            transaction_id="tx_succ_01",
            status="SUCCESS",
            details={"batch_status": "SUCCESS"},
        ),
    )
    authz = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=rail,
    )
    resp = authz.authorize(
        AuthorizeTransactionCommand(
            agent_id="agent-succ-svc",
            recipient_id="vendor-1",
            amount_minor=25_000,
            currency="USD",
            purpose="Reconcile success test",
            idempotency_key="k-succ-svc-1",
        )
    )
    assert resp.request_state == RequestState.RECONCILE
    reconciled_state = authz.reconcile(resp.request_id, rail_status="SUCCESS")
    assert reconciled_state == RequestState.SETTLED
    assert authz.get_request_state(resp.request_id) == RequestState.SETTLED


def test_f6_reconcile_confirmed_failure_transitions_to_released(db_session_factory: Any) -> None:
    """10d: RECONCILE + confirmed failure transitions reservation to RELEASED."""
    # 1. DatabaseBudgetRepository level
    with db_session_factory() as session, session.begin():
        session.add(
            AgentBudgetModel(
                agent_id="agent-recon-fail",
                mandate_id="man-fail",
                currency="USD",
                allocated_minor=100_000,
                spent_minor=0,
                reserved_minor=0,
            )
        )
        repo = BudgetRepository(session)
        res = repo.reserve_budget(
            agent_id="agent-recon-fail",
            amount_minor=30_000,
            currency="USD",
            idempotency_key="idemp-fail",
            intent_digest="digest-fail",
        )
        repo.release_reservation(res.reservation_id, confirmed_failure=False)

        # Reconcile with confirmed failure
        res_released = repo.reconcile_reservation(res.reservation_id, rail_status="FAILED")
        assert res_released.status == ReservationStatus.RELEASED.value

    with db_session_factory() as session:
        budget = session.query(AgentBudgetModel).filter_by(agent_id="agent-recon-fail").one()
        assert budget.spent_minor == 0
        assert budget.reserved_minor == 0

    # 2. AuthorizationService level
    clock = MockClock()
    mandates = MandateService(clock=clock)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="m-recon-fail-svc",
            principal_id="p-corp",
            agent_id="agent-fail-svc",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=500_000,
            valid_days=7,
            allow_unregistered_payees=True,
        )
    )
    rail = ConfigurableRail(
        pay_result=PaymentResult(
            success=False,
            transaction_id="tx_fail_01",
            status="PAYOUT_EXCEPTION",
            details={"error": "Network timeout"},
        )
    )
    authz = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=rail,
    )
    resp = authz.authorize(
        AuthorizeTransactionCommand(
            agent_id="agent-fail-svc",
            recipient_id="vendor-1",
            amount_minor=35_000,
            currency="USD",
            purpose="Reconcile failure test",
            idempotency_key="k-fail-svc-1",
        )
    )
    assert resp.request_state == RequestState.RECONCILE
    assert authz.get_lifetime_spent("agent-fail-svc") == 35_000

    reconciled_state = authz.reconcile(resp.request_id, rail_status="FAILED")
    assert reconciled_state == RequestState.FAILED
    assert authz.get_request_state(resp.request_id) == RequestState.FAILED
    # Released: lifetime spent deducted back to 0
    assert authz.get_lifetime_spent("agent-fail-svc") == 0


def test_f6_reconcile_still_unknown_remains_reconcile(db_session_factory: Any) -> None:
    """10e: RECONCILE + still unknown remains RECONCILE and holds reservation."""
    # 1. DatabaseBudgetRepository level
    with db_session_factory() as session, session.begin():
        session.add(
            AgentBudgetModel(
                agent_id="agent-recon-unknown",
                mandate_id="man-unknown",
                currency="USD",
                allocated_minor=100_000,
                spent_minor=0,
                reserved_minor=0,
            )
        )
        repo = BudgetRepository(session)
        res = repo.reserve_budget(
            agent_id="agent-recon-unknown",
            amount_minor=18_000,
            currency="USD",
            idempotency_key="idemp-unknown",
            intent_digest="digest-unknown",
        )
        repo.release_reservation(res.reservation_id, confirmed_failure=False)

        # Reconcile with still unknown status
        res_still = repo.reconcile_reservation(res.reservation_id, rail_status="PROCESSING")
        assert res_still.status == ReservationStatus.RECONCILE.value

    with db_session_factory() as session:
        budget = session.query(AgentBudgetModel).filter_by(agent_id="agent-recon-unknown").one()
        # Budget remains held in reserved_minor
        assert budget.reserved_minor == 18_000
        assert budget.spent_minor == 0

    # 2. AuthorizationService level
    clock = MockClock()
    mandates = MandateService(clock=clock)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="m-recon-unk-svc",
            principal_id="p-corp",
            agent_id="agent-unk-svc",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=500_000,
            valid_days=7,
            allow_unregistered_payees=True,
        )
    )
    rail = ConfigurableRail(
        pay_result=PaymentResult(
            success=False,
            transaction_id="tx_unk_01",
            status="PAYOUT_EXCEPTION",
            details={"error": "Gateway timeout"},
        )
    )
    authz = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=rail,
    )
    resp = authz.authorize(
        AuthorizeTransactionCommand(
            agent_id="agent-unk-svc",
            recipient_id="vendor-1",
            amount_minor=20_000,
            currency="USD",
            purpose="Reconcile still unknown test",
            idempotency_key="k-unk-svc-1",
        )
    )
    assert resp.request_state == RequestState.RECONCILE
    reconciled_state = authz.reconcile(resp.request_id, rail_status="UNKNOWN")
    assert reconciled_state == RequestState.RECONCILE
    assert authz.get_request_state(resp.request_id) == RequestState.RECONCILE
    assert authz.get_lifetime_spent("agent-unk-svc") == 20_000


def test_f6_ambiguous_outcome_does_not_release_budget(db_session_factory: Any) -> None:
    """10f: Ambiguous outcome must NOT release budget reservation, blocking double-spend."""
    # 1. DatabaseBudgetRepository level
    with db_session_factory() as session, session.begin():
        session.add(
            AgentBudgetModel(
                agent_id="agent-budget-hold",
                mandate_id="man-hold",
                currency="USD",
                allocated_minor=50_000,
                spent_minor=0,
                reserved_minor=0,
            )
        )
        repo = BudgetRepository(session)
        res = repo.reserve_budget(
            agent_id="agent-budget-hold",
            amount_minor=40_000,
            currency="USD",
            idempotency_key="idemp-hold-1",
            intent_digest="digest-hold-1",
        )
        # Release on ambiguous outcome (confirmed_failure=False)
        repo.release_reservation(res.reservation_id, confirmed_failure=False)

    with db_session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        # Budget is 50,000; 40,000 is HELD in RECONCILE.
        # An attempt to reserve 20,000 MUST fail with InsufficientBudgetError!
        with pytest.raises(InsufficientBudgetError):
            repo.reserve_budget(
                agent_id="agent-budget-hold",
                amount_minor=20_000,
                currency="USD",
                idempotency_key="idemp-hold-2",
                intent_digest="digest-hold-2",
            )

    # 2. AuthorizationService level
    clock = MockClock()
    mandates = MandateService(clock=clock)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="m-hold-svc",
            principal_id="p-corp",
            agent_id="agent-hold-svc",
            single_limit_minor=50_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=60_000,  # 60,000 budget cap
            valid_days=7,
            allow_unregistered_payees=True,
        )
    )
    rail = ConfigurableRail(
        pay_result=PaymentResult(
            success=False,
            transaction_id="tx_hold_01",
            status="PAYOUT_EXCEPTION",
            details={"error": "504 Gateway Timeout"},
        )
    )
    authz = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=rail,
    )
    res1 = authz.authorize(
        AuthorizeTransactionCommand(
            agent_id="agent-hold-svc",
            recipient_id="vendor-1",
            amount_minor=45_000,
            currency="USD",
            purpose="First tx hitting ambiguous outcome",
            idempotency_key="k-hold-1",
        )
    )
    assert res1.decision == DecisionOutcome.ALLOW
    assert res1.request_state == RequestState.RECONCILE
    # 45,000 spent out of 60,000 budget
    assert authz.get_lifetime_spent("agent-hold-svc") == 45_000

    # Second request of 30,000 exceeds 60,000 cap because 45,000 is still held!
    res2 = authz.authorize(
        AuthorizeTransactionCommand(
            agent_id="agent-hold-svc",
            recipient_id="vendor-2",
            amount_minor=30_000,
            currency="USD",
            purpose="Second tx should exceed held budget",
            idempotency_key="k-hold-2",
        )
    )
    assert res2.decision == DecisionOutcome.DENY
    assert "Lifetime budget cap exceeded" in res2.reasons[0]


# -------------------------------------------------------------------------
# R2.2 & R2.3: Concurrent Duplicate Idempotency & Database Budget Tests
# -------------------------------------------------------------------------
def test_r2_2_concurrent_duplicate_idempotency(db_session_factory: Any) -> None:
    """R2.2: Two concurrent identical requests must result in exactly one reservation,
    one payment rail dispatch, and the second receiving replay without raw IntegrityError.
    """
    import threading

    from app.domain.policy import PolicyReasonCode

    clock = MockClock()
    mandates = MandateService(clock=clock)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-r22",
            principal_id="principal-r22",
            agent_id="agent-r22",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=200_000,
            valid_days=7,
            allow_unregistered_payees=True,
        )
    )
    rail = MockPaymentRail()
    authz = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=rail,
        db_session_factory=db_session_factory,
    )

    barrier = threading.Barrier(2)
    responses: list[Any] = []
    exceptions: list[Exception] = []

    def worker() -> None:
        try:
            barrier.wait()
            cmd = AuthorizeTransactionCommand(
                agent_id="agent-r22",
                recipient_id="vendor-r22",
                amount_minor=30_000,
                currency="USD",
                purpose="Procurement batch",
                idempotency_key="key-r22-concurrent-1",
            )
            res = authz.authorize(cmd)
            responses.append(res)
        except Exception as e:
            exceptions.append(e)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # 1. No raw IntegrityError or unhandled database exceptions
    unexpected_exceptions = [e for e in exceptions if getattr(e, "status_code", None) != 409]
    assert len(unexpected_exceptions) == 0, (
        f"Unexpected exceptions during concurrent execution: {exceptions}"
    )
    assert len(responses) + len(exceptions) == 2
    assert len(responses) >= 1

    # 2. Executed callers receive an ALLOW decision
    assert all(r.decision == DecisionOutcome.ALLOW for r in responses)

    # 3. Exactly one payment rail dispatch executed
    assert len(rail.dispatched) == 1

    # 4. If second caller finished after completion, marked replay; if concurrent, returned 409
    if len(responses) == 2:
        replay_count = sum(
            1 for r in responses if PolicyReasonCode.IDEMPOTENCY_REPLAY in r.reason_codes
        )
        assert replay_count == 1
    else:
        assert len(exceptions) == 1
        assert getattr(exceptions[0], "status_code", None) == 409
        assert "currently executing" in str(getattr(exceptions[0], "detail", ""))

    # 5. Exactly one budget deduction recorded (30,000, not double 60,000)
    assert authz.get_lifetime_spent("agent-r22") == 30_000


def test_r2_3_persistent_database_budget_accounting(db_session_factory: Any) -> None:
    """R2.3: Authoritative lifetime/mandate budget accounting across service instances,
    surviving restarts, and enforcing cap under concurrent requests.
    """
    import threading

    clock = MockClock()
    mandates = MandateService(clock=clock)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-r23",
            principal_id="principal-r23",
            agent_id="agent-r23",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=100_000,  # Cap: $1,000
            valid_days=7,
            allow_unregistered_payees=True,
        )
    )

    # 1. Service instance A spends $400 (40,000 minor)
    authz_A = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=MockPaymentRail(),
        db_session_factory=db_session_factory,
    )
    res_A = authz_A.authorize(
        AuthorizeTransactionCommand(
            agent_id="agent-r23",
            recipient_id="vendor-r23",
            amount_minor=40_000,
            currency="USD",
            purpose="Instance A spend",
            idempotency_key="key-r23-instA",
        )
    )
    assert res_A.decision == DecisionOutcome.ALLOW
    assert authz_A.get_lifetime_spent("agent-r23") == 40_000

    # 2. Service instance B (separate service instance connected to same DB) sees the same $400
    authz_B = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=MockPaymentRail(),
        db_session_factory=db_session_factory,
    )
    assert authz_B.get_lifetime_spent("agent-r23") == 40_000

    # 3. Restart (simulating process restart) still sees the same $400
    authz_restarted = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=MockPaymentRail(),
        db_session_factory=db_session_factory,
    )
    assert authz_restarted.get_lifetime_spent("agent-r23") == 40_000

    # 4. Concurrent requests cannot exceed mandate:
    # Cap is 100,000. 40,000 already spent, so 60,000 remains.
    # Two concurrent requests of 40,000 each (total 80,000 > 60,000) are issued across instances.
    # Exactly one must succeed with ALLOW and the other must be DENIED!
    concurrent_results: list[DecisionOutcome] = []

    def worker(key_suffix: str) -> None:
        res = authz_B.authorize(
            AuthorizeTransactionCommand(
                agent_id="agent-r23",
                recipient_id="vendor-r23",
                amount_minor=40_000,
                currency="USD",
                purpose=f"Concurrent spend {key_suffix}",
                idempotency_key=f"key-r23-conc-{key_suffix}",
            )
        )
        concurrent_results.append(res.decision)

    t1 = threading.Thread(target=worker, args=("1",))
    t2 = threading.Thread(target=worker, args=("2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # One ALLOW, one DENY
    decisions = sorted([d.value for d in concurrent_results])
    assert decisions == ["ALLOW", "DENY"]
    # Total spent in database is exactly 80,000 (40,000 original + 40,000 successful concurrent)
    assert authz_restarted.get_lifetime_spent("agent-r23") == 80_000


def test_idempotency_replay_processing_raises_409_conflict(db_session_factory: Any) -> None:
    """Gate 3C: When an idempotency replay encounters a 'PROCESSING' or non-terminal record,
    services.py must return HTTP 409 Conflict ('Transaction currently executing')
    instead of defaulting to DecisionOutcome.ALLOW.
    """
    from fastapi import HTTPException

    from app.application.services import compute_intent_digest
    from app.infrastructure.models import IdempotencyModel

    clock = MockClock()
    mandates = MandateService(clock=clock)
    mandates.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-409",
            principal_id="principal-409",
            agent_id="agent-409",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=200_000,
            valid_days=7,
            allow_unregistered_payees=True,
        )
    )

    cmd = AuthorizeTransactionCommand(
        agent_id="agent-409",
        recipient_id="vendor-409",
        amount_minor=10_000,
        currency="USD",
        purpose="In-flight batch execution",
        idempotency_key="key-409-in-flight",
    )
    digest = compute_intent_digest(
        agent_id=cmd.agent_id,
        recipient_id=cmd.recipient_id,
        amount_minor=cmd.amount_minor,
        currency=cmd.currency,
        purpose=cmd.purpose,
        idempotency_key=cmd.idempotency_key,
    )

    # Seed an idempotency record in PROCESSING state in the database
    with db_session_factory() as session, session.begin():
        session.add(
            IdempotencyModel(
                idempotency_key=cmd.idempotency_key,
                agent_id=cmd.agent_id,
                intent_digest=digest,
                decision="PROCESSING",
                response_payload="",
                created_at_utc=clock.now_utc(),
            )
        )

    authz = AuthorizationService(
        clock=clock,
        ledger=MemoryLedger(),
        mandate_service=mandates,
        payment_rail=MockPaymentRail(),
        db_session_factory=db_session_factory,
    )

    # Calling authorize with the same key while PROCESSING must raise HTTP 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        authz.authorize(cmd)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Transaction currently executing"
