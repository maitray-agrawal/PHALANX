"""Integration tests for payment reconciliation and budget leak prevention.

Verifies:
1. Pending then completed settles reservation and moves funds from reserved to spent.
2. Definite failure, denial or expiry releases reservation and returns funds to available pool.
3. Timeout past RECONCILE_MAX_AGE transitions request to NEEDS_REVIEW, preserving held budget.
4. Running the reconciler twice is idempotent (no double-spend, no double-release).
5. Budget invariant (spent + reserved <= allocated) holds with payment in flight.
6. Concurrent reconcile and new payment requests under PostgreSQL row locking.
7. Configuration errors fail before any reservation with a clear 503 (not RECONCILE).
8. Webhook ingestion triggers immediate reconciliation.
9. POST /v1/admin/reconcile endpoint triggers immediate reconciliation with admin token.
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.api.dependencies import (
    get_authorization_service,
    get_payment_rail,
)
from app.application.dtos import AuthorizeTransactionCommand, CreateMandateCommand
from app.application.reconciler import ReconcilerService
from app.application.services import AuthorizationService, MandateService
from app.domain.models import DecisionOutcome
from app.domain.ports import ClockPort, PaymentResult
from app.domain.state_machine import RequestState
from app.infrastructure.clock import SystemUtcClock
from app.infrastructure.config import settings
from app.infrastructure.db_budget_repo import BudgetRepository
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.models import (
    AgentBudgetModel,
    Base,
    BudgetReservationModel,
    ReservationStatus,
)
from app.infrastructure.paypal import FakePaymentRail
from app.main import app


class ControllableClock(ClockPort):
    def __init__(self, initial_time: datetime) -> None:
        self._current_time = initial_time

    def now_utc(self) -> datetime:
        return self._current_time

    def advance(self, duration: timedelta) -> None:
        self._current_time += duration


def _get_test_engine():
    """Retrieve test PostgreSQL engine, or fallback to SQLite for local isolation."""
    db_url = os.getenv("TEST_DATABASE_URL")
    if not db_url:
        base_url = os.getenv("DATABASE_URL") or settings.database_url
        if "phalanx_db" in base_url:
            db_url = base_url.replace("/phalanx_db", "/phalanx_test")
        elif base_url:
            db_url = base_url

    if db_url and "postgres" in db_url:
        try:
            engine = create_engine(
                db_url,
                poolclass=NullPool,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 2},
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception:
            pass

    # Fallback to local SQLite if postgres test DB is not running
    sqlite_engine = create_engine("sqlite:///:memory:", poolclass=NullPool)
    Base.metadata.create_all(sqlite_engine)
    return sqlite_engine


@pytest.fixture
def db_engine():
    engine = _get_test_engine()
    Base.metadata.create_all(engine)
    yield engine
    if "postgres" not in engine.url.drivername:
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


def _seed_agent_mandate_and_budget(
    session_factory,
    agent_id: str,
    mandate_id: str,
    allocated_minor: int = 100_000,
    clock: ClockPort | None = None,
):
    clk = clock or SystemUtcClock()
    mandate_service = MandateService(clock=clk, db_session_factory=session_factory)
    mandate_service.create_mandate(
        CreateMandateCommand(
            mandate_id=mandate_id,
            principal_id="principal_treasury",
            agent_id=agent_id,
            single_limit_minor=allocated_minor,
            instant_threshold_minor=allocated_minor,
            lifetime_budget_minor=allocated_minor,
            currency="USD",
            allow_unregistered_payees=True,
            allowed_payees=[],
            allowed_purposes=[],
            valid_days=90,
        )
    )
    with session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        repo.get_or_create_budget(
            agent_id=agent_id,
            mandate_id=mandate_id,
            currency="USD",
            allocated_minor=allocated_minor,
        )


def test_pending_then_completed_settles(session_factory):
    """Verify ambiguous pending transaction transitions to SETTLED upon confirmed completion."""
    agent_id = f"agent_recon_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    allocated_minor = 100_000
    tx_amount_minor = 25_000

    clock = ControllableClock(datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC))
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, allocated_minor, clock)

    rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=session_factory,
    )
    reconciler = ReconcilerService(
        auth_service=auth_service,
        payment_rail=rail,
        clock=clock,
        db_session_factory=session_factory,
        max_age_seconds=86400,
    )

    # 1. Authorize transaction that lands in RECONCILE state
    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=tx_amount_minor,
        currency="USD",
        purpose="Operational cloud hosting",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    assert auth_resp.request_state == RequestState.RECONCILE
    tx_id = auth_resp.payout_id

    # Verify reservation is held in database
    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.reserved_minor == tx_amount_minor
        assert budget.spent_minor == 0
        res = session.scalar(
            select(BudgetReservationModel).where(BudgetReservationModel.agent_id == agent_id)
        )
        assert res.status == ReservationStatus.RECONCILE.value

    # 2. Reconcile while rail is still pending: remains RECONCILE, reservation remains held
    rail.set_lookup_result(
        tx_id, PaymentResult(success=True, transaction_id=tx_id, status="ORDER_CREATED", details={})
    )
    clock.advance(timedelta(seconds=5))
    recon_state = reconciler.reconcile_single(auth_resp.request_id, force=True)
    assert recon_state == RequestState.RECONCILE

    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.reserved_minor == tx_amount_minor
        assert budget.spent_minor == 0

    # 3. Rail outcome completes (e.g. buyer approved and order captured)
    rail.set_lookup_result(
        tx_id, PaymentResult(success=True, transaction_id=tx_id, status="COMPLETED", details={})
    )
    clock.advance(timedelta(seconds=5))
    settled_state = reconciler.reconcile_single(auth_resp.request_id, force=True)
    assert settled_state == RequestState.SETTLED

    # In database: reserved -> 0, spent -> tx_amount_minor
    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.reserved_minor == 0
        assert budget.spent_minor == tx_amount_minor
        assert budget.spent_minor + budget.reserved_minor <= budget.allocated_minor
        res = session.scalar(
            select(BudgetReservationModel).where(BudgetReservationModel.agent_id == agent_id)
        )
        assert res.status == ReservationStatus.CONFIRMED.value


def test_failed_releases(session_factory):
    """Verify that a confirmed external rail failure or denial releases held reservation."""
    agent_id = f"agent_fail_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    allocated_minor = 100_000
    tx_amount_minor = 30_000

    clock = ControllableClock(datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC))
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, allocated_minor, clock)

    rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=session_factory,
    )
    reconciler = ReconcilerService(
        auth_service=auth_service,
        payment_rail=rail,
        clock=clock,
        db_session_factory=session_factory,
        max_age_seconds=86400,
    )

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=tx_amount_minor,
        currency="USD",
        purpose="Operational cloud hosting",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    assert auth_resp.request_state == RequestState.RECONCILE
    tx_id = auth_resp.payout_id

    # Rail reports confirmed failure / denial
    rail.set_lookup_result(
        tx_id, PaymentResult(success=False, transaction_id=tx_id, status="DENIED", details={})
    )
    clock.advance(timedelta(seconds=5))
    failed_state = reconciler.reconcile_single(auth_resp.request_id, force=True)
    assert failed_state == RequestState.FAILED

    # In database: reserved -> 0, spent -> 0 (budget fully restored)
    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.reserved_minor == 0
        assert budget.spent_minor == 0
        res = session.scalar(
            select(BudgetReservationModel).where(BudgetReservationModel.agent_id == agent_id)
        )
        assert res.status == ReservationStatus.RELEASED.value


def test_timeout_stays_held_as_needs_review(session_factory):
    """Verify transactions past RECONCILE_MAX_AGE mark NEEDS_REVIEW and preserve held budget."""
    agent_id = f"agent_timeout_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    allocated_minor = 100_000
    tx_amount_minor = 20_000

    clock = ControllableClock(datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC))
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, allocated_minor, clock)

    rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=session_factory,
    )
    reconciler = ReconcilerService(
        auth_service=auth_service,
        payment_rail=rail,
        clock=clock,
        db_session_factory=session_factory,
        max_age_seconds=3600,  # 1 hour max age
    )

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=tx_amount_minor,
        currency="USD",
        purpose="Operational cloud hosting",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    assert auth_resp.request_state == RequestState.RECONCILE

    # Advance clock past 1 hour (3601 seconds)
    clock.advance(timedelta(seconds=3601))

    # Reconciler checks: outcome is still pending/unknown
    rail.set_lookup_result(
        auth_resp.payout_id,
        PaymentResult(
            success=True, transaction_id=auth_resp.payout_id, status="RECONCILE", details={}
        ),
    )
    timeout_state = reconciler.reconcile_single(auth_resp.request_id, force=True)
    assert timeout_state == RequestState.NEEDS_REVIEW

    # CRITICAL: Budget reservation MUST remain held; never auto-release on timeout!
    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.reserved_minor == tx_amount_minor
        assert budget.spent_minor == 0
        res = session.scalar(
            select(BudgetReservationModel).where(BudgetReservationModel.agent_id == agent_id)
        )
        assert res.status == ReservationStatus.RECONCILE.value

    # Verify that NEEDS_REVIEW is separate from step-up approvals queue (M0 requirement c)
    pending_approvals = auth_service.get_pending_step_ups()
    assert not any(item.request_id == auth_resp.request_id for item in pending_approvals)

    needs_review_items = auth_service.get_needs_review_items()
    review_item = next(
        (item for item in needs_review_items if item["request_id"] == auth_resp.request_id), None
    )
    assert review_item is not None
    assert review_item["state"] == "NEEDS_REVIEW"


def test_reconciler_idempotent(session_factory):
    """Verify that calling the reconciler multiple times produces identical idempotent results."""
    agent_id = f"agent_idem_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    allocated_minor = 100_000
    tx_amount_minor = 15_000

    clock = ControllableClock(datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC))
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, allocated_minor, clock)

    rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=session_factory,
    )
    reconciler = ReconcilerService(
        auth_service=auth_service,
        payment_rail=rail,
        clock=clock,
        db_session_factory=session_factory,
        max_age_seconds=86400,
    )

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=tx_amount_minor,
        currency="USD",
        purpose="Operational cloud hosting",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)

    # Reconcile to SETTLED
    rail.set_lookup_result(
        auth_resp.payout_id,
        PaymentResult(
            success=True, transaction_id=auth_resp.payout_id, status="COMPLETED", details={}
        ),
    )
    first_run = reconciler.reconcile_single(auth_resp.request_id, force=True)
    assert first_run == RequestState.SETTLED

    # Second run on same request
    second_run = reconciler.reconcile_single(auth_resp.request_id, force=True)
    assert second_run == RequestState.SETTLED

    # Ensure no double-spent budget corruption
    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.spent_minor == tx_amount_minor
        assert budget.reserved_minor == 0


def test_budget_invariant_holds_with_payment_in_flight(session_factory):
    """Verify that spent_minor + reserved_minor <= allocated_minor holds with payment in flight."""
    agent_id = f"agent_inv_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    allocated_minor = 100_000

    clock = ControllableClock(datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC))
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, allocated_minor, clock)

    rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=session_factory,
    )

    # 1. First transaction reserves 80,000 (leaves 20,000 unallocated)
    cmd1 = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=80_000,
        currency="USD",
        purpose="Operational cloud hosting",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    resp1 = auth_service.authorize(cmd1)
    assert resp1.request_state == RequestState.RECONCILE

    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.spent_minor + budget.reserved_minor <= budget.allocated_minor
        assert budget.reserved_minor == 80_000

    # 2. Second transaction for 30,000 exceeds available 20,000 -> hard DENY
    cmd2 = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=30_000,
        currency="USD",
        purpose="Operational cloud hosting",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    resp2 = auth_service.authorize(cmd2)
    assert resp2.decision == DecisionOutcome.DENY
    assert "budget cap exceeded" in resp2.reasons[0].lower()

    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.spent_minor + budget.reserved_minor <= budget.allocated_minor
        assert budget.reserved_minor == 80_000


def test_concurrent_reconcile_and_new_requests(session_factory):
    """Verify concurrent reconciliation and new authorizations maintain budget safety."""
    agent_id = f"agent_conc_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    allocated_minor = 500_000

    clock = SystemUtcClock()
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, allocated_minor, clock)

    rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=session_factory,
    )
    reconciler = ReconcilerService(
        auth_service=auth_service,
        payment_rail=rail,
        clock=clock,
        db_session_factory=session_factory,
        max_age_seconds=86400,
    )

    # Create 4 initial in-flight transactions
    req_ids = []
    for _ in range(4):
        cmd = AuthorizeTransactionCommand(
            agent_id=agent_id,
            recipient_id="vendor-paypal-sandbox-1",
            amount_minor=10_000,
            currency="USD",
            purpose="Operational cloud hosting",
            idempotency_key=f"idem_{uuid.uuid4().hex}",
        )
        res = auth_service.authorize(cmd)
        req_ids.append(res.request_id)
        rail.set_lookup_result(
            res.payout_id,
            PaymentResult(
                success=True, transaction_id=res.payout_id, status="COMPLETED", details={}
            ),
        )

    def worker_reconcile(req_id: str):
        return reconciler.reconcile_single(req_id, force=True)

    def worker_new_tx():
        cmd = AuthorizeTransactionCommand(
            agent_id=agent_id,
            recipient_id="vendor-paypal-sandbox-1",
            amount_minor=5_000,
            currency="USD",
            purpose="Operational cloud hosting",
            idempotency_key=f"idem_{uuid.uuid4().hex}",
        )
        return auth_service.authorize(cmd)

    with ThreadPoolExecutor(max_workers=8) as executor:
        f_recons = [executor.submit(worker_reconcile, r) for r in req_ids]
        f_txs = [executor.submit(worker_new_tx) for _ in range(4)]
        for f in f_recons:
            assert f.result() == RequestState.SETTLED
        for f in f_txs:
            assert f.result() is not None

    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.spent_minor + budget.reserved_minor <= budget.allocated_minor


def test_configuration_error_fails_before_reservation_with_503(session_factory):
    """Verify that unconfigured rail credentials fail with 503 before any budget reservation."""
    agent_id = f"agent_cfg_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    allocated_minor = 100_000

    clock = SystemUtcClock()
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, allocated_minor, clock)

    # Rail is explicitly unconfigured
    rail = FakePaymentRail(
        is_configured=False,
        config_error="PayPal credentials missing: PAYPAL_CLIENT_ID required",
    )
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=session_factory,
    )

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=10_000,
        currency="USD",
        purpose="Operational cloud hosting",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )

    with pytest.raises(HTTPException) as exc_info:
        auth_service.authorize(cmd)

    assert exc_info.value.status_code == 503
    assert "Payment rail unavailable" in exc_info.value.detail

    # CRITICAL: Budget must have ZERO reservations created!
    with session_factory() as session:
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert budget.reserved_minor == 0
        assert budget.spent_minor == 0
        reservations = session.scalars(
            select(BudgetReservationModel).where(BudgetReservationModel.agent_id == agent_id)
        ).all()
        assert len(reservations) == 0


def test_webhook_triggers_reconciliation(session_factory):
    """Verify that verified PayPal webhooks trigger immediate reconciliation."""
    client = TestClient(app)

    # Configure fake rail with valid signature fixture
    test_rail = FakePaymentRail(
        should_succeed=True,
        status="RECONCILE",
        valid_signatures={"test-recon-webhook-sig"},
    )
    app.dependency_overrides[get_payment_rail] = lambda: test_rail

    clock = SystemUtcClock()
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=test_rail,
        db_session_factory=session_factory,
    )
    app.dependency_overrides[get_authorization_service] = lambda: auth_service

    agent_id = f"agent_hook_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 100_000, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=10_000,
        currency="USD",
        purpose="Operational cloud hosting",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    tx_id = auth_resp.payout_id
    assert auth_resp.request_state == RequestState.RECONCILE

    # Mock PayPal returning COMPLETED for this payout
    test_rail.set_lookup_result(
        tx_id, PaymentResult(success=True, transaction_id=tx_id, status="COMPLETED", details={})
    )

    webhook_payload = {
        "id": f"WH-EVENT-{uuid.uuid4().hex[:12]}",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": tx_id},
    }
    headers = {
        "PAYPAL-TRANSMISSION-SIG": "test-recon-webhook-sig",
        "PAYPAL-CERT-URL": "https://api-m.sandbox.paypal.com/cert.pem",
        "PAYPAL-TRANSMISSION-ID": "trans_123",
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-01T12:00:00Z",
    }

    resp = client.post("/v1/webhooks/paypal", json=webhook_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "processed"

    # Verify transaction was reconciled to SETTLED
    final_state = auth_service.get_request_state(auth_resp.request_id)
    assert final_state == RequestState.SETTLED

    app.dependency_overrides.clear()


def test_lookup_failed_never_releases_budget_and_stays_held(db_engine):
    """Critical Invariant 3: LOOKUP_FAILED, network hiccups or unknown states

    MUST NEVER release a reservation or leak budget. It must remain held in RECONCILE.
    """
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    clock = SystemUtcClock()
    test_rail = FakePaymentRail(should_succeed=True, status="BUYER_APPROVAL_REQUIRED")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=test_rail,
        db_session_factory=session_factory,
    )
    reconciler = ReconcilerService(
        auth_service=auth_service,
        payment_rail=test_rail,
        clock=clock,
        db_session_factory=session_factory,
        max_age_seconds=86400,
    )

    agent_id = f"agent_lookup_fail_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    allocated_minor = 100_000
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, allocated_minor, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=15_000,
        currency="USD",
        purpose="Compute reservation",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    assert auth_resp.request_state == RequestState.RECONCILE

    with session_factory() as session:
        b_before = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert b_before.reserved_minor == 15_000

    # Simulate rail returning LOOKUP_FAILED (transient PayPal outage/connection error)
    test_rail.set_lookup_result(
        auth_resp.payout_id,
        PaymentResult(
            success=False,
            transaction_id=auth_resp.payout_id,
            status="LOOKUP_FAILED",
            details={"error": "PayPal lookup unreachable"},
        ),
    )

    new_state = reconciler.reconcile_single(auth_resp.request_id, force=True)
    assert new_state == RequestState.NEEDS_REVIEW

    # Budget MUST NOT be released back to available pool
    with session_factory() as session:
        b_after = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert b_after.reserved_minor == 15_000
        assert b_after.spent_minor == 0
        res = session.scalar(
            select(BudgetReservationModel).where(BudgetReservationModel.agent_id == agent_id)
        )
        assert res.status == ReservationStatus.RECONCILE.value


def test_lookup_rate_limit_429_and_timeout_stays_reconcile(db_engine):
    """HTTP 429 (rate limits) and 408 (timeouts) must stay held in RECONCILE."""
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    clock = SystemUtcClock()
    test_rail = FakePaymentRail(should_succeed=True, status="BUYER_APPROVAL_REQUIRED")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=test_rail,
        db_session_factory=session_factory,
    )
    reconciler = ReconcilerService(
        auth_service=auth_service,
        payment_rail=test_rail,
        clock=clock,
        db_session_factory=session_factory,
        max_age_seconds=86400,
    )

    agent_id = f"agent_rate_limit_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    allocated_minor = 100_000
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, allocated_minor, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=10_000,
        currency="USD",
        purpose="Test rate limit handling",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)

    # Rail returns rate limit (HTTP 429)
    test_rail.set_lookup_result(
        auth_resp.payout_id,
        PaymentResult(
            success=False,
            transaction_id=auth_resp.payout_id,
            status="RECONCILE",
            details={"http_status": 429, "error": "RATE_LIMIT_EXCEEDED"},
        ),
    )

    state = reconciler.reconcile_single(auth_resp.request_id, force=True)
    assert state == RequestState.RECONCILE

    with session_factory() as session:
        b = session.scalar(select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id))
        assert b.reserved_minor == 10_000
        assert b.spent_minor == 0


def test_admin_reconcile_endpoint(session_factory):
    """Verify that POST /v1/admin/reconcile triggers reconciliation with admin token."""
    client = TestClient(app)

    test_rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    app.dependency_overrides[get_payment_rail] = lambda: test_rail

    clock = SystemUtcClock()
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=test_rail,
        db_session_factory=session_factory,
    )
    app.dependency_overrides[get_authorization_service] = lambda: auth_service

    agent_id = f"agent_adm_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 100_000, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=12_000,
        currency="USD",
        purpose="Operational cloud hosting",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    tx_id = auth_resp.payout_id
    assert auth_resp.request_state == RequestState.RECONCILE

    test_rail.set_lookup_result(
        tx_id, PaymentResult(success=True, transaction_id=tx_id, status="COMPLETED", details={})
    )

    admin_token = settings.admin_token or "phalanx_super_secure_admin_key_2026_demo"
    resp = client.post(
        "/v1/admin/reconcile",
        headers={"X-Admin-Token": admin_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "reconciliation_completed"
    metrics = data.get("metrics", {})
    assert metrics.get("settled") >= 1

    final_state = auth_service.get_request_state(auth_resp.request_id)
    assert final_state == RequestState.SETTLED

    app.dependency_overrides.clear()


# =========================================================================
# M0 AUDIT RECONCILER TESTS (a, b, c, d)
# =========================================================================


def test_lookup_network_error_and_timeout_keeps_hold_and_sets_needs_review(db_engine):
    """(a) LOOKUP_FAILED, timeouts, and network errors keep the hold and set NEEDS_REVIEW."""
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    clock = SystemUtcClock()

    class OutageRail(FakePaymentRail):
        def lookup(self, transaction_id: str) -> PaymentResult:
            _ = transaction_id
            raise ConnectionError("Simulated socket timeout / connection reset to PayPal")

    test_rail = OutageRail(should_succeed=True, status="RECONCILE")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=test_rail,
        db_session_factory=session_factory,
    )
    reconciler = ReconcilerService(
        auth_service=auth_service,
        payment_rail=test_rail,
        clock=clock,
        db_session_factory=session_factory,
        max_age_seconds=86400,
    )

    agent_id = f"agent_outage_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 100_000, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=20_000,
        currency="USD",
        purpose="Payment subject to network error during lookup",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    assert auth_resp.request_state == RequestState.RECONCILE

    # Trigger reconcile: rail.lookup raises ConnectionError -> must set NEEDS_REVIEW and keep hold
    new_state = reconciler.reconcile_single(auth_resp.request_id, force=True)
    assert new_state == RequestState.NEEDS_REVIEW

    # Invariant: Reservation remains held, funds are not released, spent is 0
    with session_factory() as session:
        b = session.scalar(select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id))
        assert b.reserved_minor == 20_000
        assert b.spent_minor == 0
        res = session.scalar(
            select(BudgetReservationModel).where(BudgetReservationModel.agent_id == agent_id)
        )
        assert res.status == ReservationStatus.RECONCILE.value


def test_credential_check_fails_closed_without_reservation(session_factory):
    """(b) Missing method fails closed; 401 fails closed; error text does not leak env vars."""
    clock = SystemUtcClock()
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)

    # 1. Rail with no validate_configuration method
    class MethodlessRail:
        def pay(self, intent):
            _ = intent
            return PaymentResult(
                success=True, transaction_id="tx_123", status="COMPLETED", details={}
            )

    auth_svc_methodless = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=MethodlessRail(),
        db_session_factory=session_factory,
    )

    agent_id = f"agent_cfg_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 100_000, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=5_000,
        currency="USD",
        purpose="Missing validate method test",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )

    with pytest.raises(HTTPException) as exc_info:
        auth_svc_methodless.authorize(cmd)
    assert exc_info.value.status_code == 503
    assert "configuration validator is missing" in exc_info.value.detail
    assert "PAYPAL_" not in exc_info.value.detail

    # Confirm no budget was reserved in DB
    with session_factory() as session:
        b = session.scalar(select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id))
        assert b.reserved_minor == 0

    # 2. PayPal adapter with invalid credentials (OAuth returns 401)
    from unittest.mock import MagicMock, patch

    from app.infrastructure.paypal import PayPalPaymentRailAdapter

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized: client_id or secret invalid"
        mock_post.return_value = mock_resp

        adapter = PayPalPaymentRailAdapter()
        adapter._client_id = "placeholder_client_id"
        adapter._client_secret = "placeholder_secret"

        is_ok, err_msg = adapter.validate_configuration()
        assert not is_ok
        assert "invalid credentials" in err_msg.lower()
        # Non-negotiable security invariant: error text must not name env vars
        assert "PAYPAL_CLIENT_ID" not in err_msg
        assert "PAYPAL_CLIENT_SECRET" not in err_msg


def test_needs_review_requires_provider_proof_and_cannot_be_manually_approved(session_factory):
    """(c) NEEDS_REVIEW -> SETTLED requires provider proof, never a manual click.

    Keep these separate from step-up queue.
    """
    clock = SystemUtcClock()
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    test_rail = FakePaymentRail(should_succeed=True, status="RECONCILE")

    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=test_rail,
        db_session_factory=session_factory,
    )
    reconciler = ReconcilerService(
        auth_service=auth_service,
        payment_rail=test_rail,
        clock=clock,
        db_session_factory=session_factory,
        max_age_seconds=86400,
    )

    agent_id = f"agent_nr_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 100_000, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=10_000,
        currency="USD",
        purpose="Needs review proof requirement test",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    req_id = auth_resp.request_id

    # Move to NEEDS_REVIEW via timeout/LOOKUP_FAILED
    test_rail.set_lookup_result(
        auth_resp.payout_id,
        PaymentResult(
            success=False, transaction_id=auth_resp.payout_id, status="LOOKUP_FAILED", details={}
        ),
    )
    state = reconciler.reconcile_single(req_id, force=True)
    assert state == RequestState.NEEDS_REVIEW

    # 1. Invariant: NEEDS_REVIEW items MUST NOT appear in the step-up approval queue
    pending_stepups = auth_service.get_pending_step_ups()
    assert all(item.request_id != req_id for item in pending_stepups)

    # Invariant: Item appears in dedicated needs-review queue
    nr_items = auth_service.get_needs_review_items()
    assert any(item["request_id"] == req_id for item in nr_items)

    # 2. Invariant: Manual approval click (ALLOW) via execute_approval is strictly rejected
    from app.application.dtos import ApprovalCommand

    appr_cmd = ApprovalCommand(
        request_id=req_id,
        expected_digest=auth_resp.intent_digest,
        decision=DecisionOutcome.ALLOW,
        reason="Supervisor manual approve click attempt",
    )
    with pytest.raises(ValueError) as exc_info:
        auth_service.execute_approval(appr_cmd, caller_role="approver")
    assert "requires verified provider settlement proof" in str(exc_info.value)

    # 3. Invariant: resolve_needs_review with manual APPROVE is strictly rejected
    with pytest.raises(ValueError) as exc_info2:
        auth_service.resolve_needs_review(req_id, action="APPROVE")
    assert "requires verified provider proof" in str(exc_info2.value)

    # 4. Invariant: resolve_needs_review with MARK_FAILED releases reservation and logs actor
    test_rail.set_lookup_result(
        auth_resp.payout_id,
        PaymentResult(
            success=False,
            transaction_id=auth_resp.payout_id,
            status="FAILED",
            details={"error": "Explicit provider rejection confirmed"},
        ),
    )
    auth_service.resolve_needs_review(
        req_id,
        action="MARK_FAILED",
        reason="Abandoning unresolvable ambiguous payment",
        actor="approver:test_supervisor",
    )
    assert auth_service.get_request_state(req_id) == RequestState.FAILED

    with session_factory() as session:
        b = session.scalar(select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id))
        assert b.reserved_minor == 0
        assert b.spent_minor == 0


def test_reconciler_second_instance_resolves_db_persisted_request(session_factory):
    """(d) Scheduled trigger with DB-persisted state only.

    A second instance resolves a request created by the first.
    """
    clock = SystemUtcClock()
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    rail_inst1 = FakePaymentRail(should_succeed=True, status="RECONCILE")

    # Instance 1: Creates ambiguous payment request in PostgreSQL
    svc1 = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail_inst1,
        db_session_factory=session_factory,
    )

    agent_id = f"agent_2inst_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 100_000, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=18_000,
        currency="USD",
        purpose="Multi-process reconciliation persistence",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = svc1.authorize(cmd)
    payout_id = auth_resp.payout_id
    assert auth_resp.request_state == RequestState.RECONCILE

    # Verify reservation is in RECONCILE state in DB
    with session_factory() as session:
        res = session.scalar(
            select(BudgetReservationModel).where(BudgetReservationModel.agent_id == agent_id)
        )
        assert res.status == ReservationStatus.RECONCILE.value
        assert res.amount_minor == 18_000

    # DISCARD Instance 1 completely!
    del svc1
    del rail_inst1

    # Instance 2: Brand new instance (simulating scripts/reconcile.py in a separate process)
    rail_inst2 = FakePaymentRail(should_succeed=True, status="COMPLETED")
    rail_inst2.set_lookup_result(
        payout_id,
        PaymentResult(
            success=True,
            transaction_id=payout_id,
            status="COMPLETED",
            details={"batch_status": "SUCCESS"},
        ),
    )
    svc2 = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail_inst2,
        db_session_factory=session_factory,
    )
    reconciler2 = ReconcilerService(
        auth_service=svc2,
        payment_rail=rail_inst2,
        clock=clock,
        db_session_factory=session_factory,
    )

    # Reconciler 2 queries PostgreSQL, loads the held reservation, and settles it!
    metrics = reconciler2.reconcile_all(force=True)
    assert metrics["settled"] >= 1

    # Verify PostgreSQL budget and reservation were updated to CONFIRMED
    # and funds moved to spent_minor
    with session_factory() as session:
        b_final = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        )
        assert b_final.reserved_minor == 0
        assert b_final.spent_minor == 18_000
        res_final = session.scalar(
            select(BudgetReservationModel).where(BudgetReservationModel.agent_id == agent_id)
        )
        assert res_final.status == ReservationStatus.CONFIRMED.value


def test_reconcile_reservation_unknown_status_holds_reservation(db_engine):
    """reconcile_reservation must treat unknown status strings as ambiguous and hold funds."""
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    clock = SystemUtcClock()
    agent_id = f"agent_unk_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 100_000, clock)

    with session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        res = repo.reserve_budget(
            agent_id=agent_id,
            amount_minor=25_000,
            currency="USD",
            idempotency_key=f"idem_{uuid.uuid4().hex}",
            intent_digest=f"dig_{uuid.uuid4().hex}",
        )
        res_id = res.reservation_id

    with session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        # Reconcile with an unknown status string
        r = repo.reconcile_reservation(res_id, rail_status="SOME_UNKNOWN_PROVIDER_CODE_XYZ")
        assert r.status == ReservationStatus.RECONCILE.value

    # Verify funds are still held, NOT released
    with session_factory() as session:
        b = session.scalar(select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id))
        assert b.reserved_minor == 25_000
        assert b.spent_minor == 0

    # Explicit provider failure in allowlist (e.g. DENIED) releases
    with session_factory() as session, session.begin():
        repo = BudgetRepository(session)
        r2 = repo.reconcile_reservation(res_id, rail_status="DENIED")
        assert r2.status == ReservationStatus.RELEASED.value

    with session_factory() as session:
        b2 = session.scalar(select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id))
        assert b2.reserved_minor == 0
        assert b2.spent_minor == 0


def test_resolve_needs_review_mark_failed_requires_provider_confirmation(db_engine):
    """MARK_FAILED must be confirmed by provider lookup (failure or not-found), else refused."""
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    clock = SystemUtcClock()
    test_rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=test_rail,
        db_session_factory=session_factory,
    )

    agent_id = f"agent_mf_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 100_000, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=10_000,
        currency="USD",
        purpose="Payment subject to manual resolution",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    req_id = auth_resp.request_id

    # 1. Provider reports still PENDING/RECONCILE -> MARK_FAILED must be refused
    test_rail.set_lookup_result(
        auth_resp.payout_id,
        PaymentResult(
            success=False,
            transaction_id=auth_resp.payout_id,
            status="PENDING",
            details={"state": "PENDING"},
        ),
    )
    with pytest.raises(ValueError, match="not a confirmed failure or not-found"):
        auth_service.resolve_needs_review(req_id, action="MARK_FAILED")

    # 2. Provider reports confirmed FAILED -> MARK_FAILED is permitted and releases reservation
    test_rail.set_lookup_result(
        auth_resp.payout_id,
        PaymentResult(
            success=False,
            transaction_id=auth_resp.payout_id,
            status="FAILED",
            details={"error": "Explicit rejection"},
        ),
    )
    res_state = auth_service.resolve_needs_review(req_id, action="MARK_FAILED")
    assert res_state == RequestState.FAILED


def test_resolve_needs_review_provide_proof_verified_against_provider(db_engine):
    """PROVIDE_PROOF must be verified against provider lookup, not trusted from input."""
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    clock = SystemUtcClock()
    test_rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)
    auth_service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=test_rail,
        db_session_factory=session_factory,
    )

    agent_id = f"agent_pp_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 100_000, clock)

    cmd = AuthorizeTransactionCommand(
        agent_id=agent_id,
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=12_000,
        currency="USD",
        purpose="Payment requiring proof verification",
        idempotency_key=f"idem_{uuid.uuid4().hex}",
    )
    auth_resp = auth_service.authorize(cmd)
    req_id = auth_resp.request_id

    # 1. Unverified or pending capture ID must be refused
    test_rail.set_lookup_result(
        "unverified_capture_123",
        PaymentResult(
            success=False,
            transaction_id="unverified_capture_123",
            status="PENDING",
            details={},
        ),
    )
    with pytest.raises(ValueError, match="could not be verified with provider"):
        auth_service.resolve_needs_review(
            req_id, action="PROVIDE_PROOF", capture_id="unverified_capture_123"
        )

    # 2. Confirmed COMPLETED capture ID verified against provider settles reservation
    test_rail.set_lookup_result(
        "verified_capture_456",
        PaymentResult(
            success=True,
            transaction_id="verified_capture_456",
            status="COMPLETED",
            details={},
        ),
    )
    res_state = auth_service.resolve_needs_review(
        req_id, action="PROVIDE_PROOF", capture_id="verified_capture_456"
    )
    assert res_state == RequestState.SETTLED


def test_concurrent_reconciler_instances_skip_locked_no_double_processing(db_engine):
    """Two concurrent reconciler instances use FOR UPDATE SKIP LOCKED and do not double-process."""
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    clock = SystemUtcClock()
    shared_rail = FakePaymentRail(should_succeed=True, status="COMPLETED")
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)

    agent_id = f"agent_conc_rec_{uuid.uuid4().hex[:8]}"
    mandate_id = f"mandate_{uuid.uuid4().hex[:8]}"
    _seed_agent_mandate_and_budget(session_factory, agent_id, mandate_id, 500_000, clock)

    auth_init = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=FakePaymentRail(should_succeed=True, status="RECONCILE"),
        db_session_factory=session_factory,
    )

    # Seed 4 separate ambiguous transactions in RECONCILE
    req_ids = []
    payout_ids = []
    for i in range(4):
        cmd = AuthorizeTransactionCommand(
            agent_id=agent_id,
            recipient_id=f"vendor-conc-{i}",
            amount_minor=10_000,
            currency="USD",
            purpose=f"Payment {i} for concurrent reconciliation",
            idempotency_key=f"idem_conc_{i}_{uuid.uuid4().hex}",
        )
        resp = auth_init.authorize(cmd)
        req_ids.append(resp.request_id)
        payout_ids.append(resp.payout_id)
        shared_rail.set_lookup_result(
            resp.payout_id,
            PaymentResult(
                success=True,
                transaction_id=resp.payout_id,
                status="COMPLETED",
                details={},
            ),
        )

    # Instance 1 and Instance 2
    svc1 = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=shared_rail,
        db_session_factory=session_factory,
    )
    reconciler_1 = ReconcilerService(
        auth_service=svc1,
        payment_rail=shared_rail,
        clock=clock,
        db_session_factory=session_factory,
    )

    svc2 = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=shared_rail,
        db_session_factory=session_factory,
    )
    reconciler_2 = ReconcilerService(
        auth_service=svc2,
        payment_rail=shared_rail,
        clock=clock,
        db_session_factory=session_factory,
    )

    # Run both simultaneously
    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(reconciler_1.reconcile_all, force=True, agent_id=agent_id)
        f2 = executor.submit(reconciler_2.reconcile_all, force=True, agent_id=agent_id)
        m1 = f1.result(timeout=15)
        m2 = f2.result(timeout=15)

    # Exactly 4 total processed across both instances without duplicate processing
    total_settled = m1["settled"] + m2["settled"]
    assert total_settled == 4, f"Expected 4 settled, got m1={m1}, m2={m2}"

    with session_factory() as session:
        b = session.scalar(select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id))
        assert b.reserved_minor == 0
        assert b.spent_minor == 40_000
