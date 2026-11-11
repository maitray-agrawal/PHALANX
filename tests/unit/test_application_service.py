"""Unit tests for application layer services."""

from app.application.dtos import AuthorizeTransactionCommand
from app.application.services import AuthorizationService, HealthService
from app.domain.models import DecisionOutcome
from app.domain.ports import ClockPort
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.paypal import FakePaymentRail


def test_authorization_service_allow(
    test_clock: ClockPort, test_ledger: InMemoryLedgerAdapter
) -> None:
    service = AuthorizationService(clock=test_clock, ledger=test_ledger)
    cmd = AuthorizeTransactionCommand(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=2500,  # $25.00
        currency="USD",
        purpose="Monthly subscription renewal",
        idempotency_key="idemp-001",
    )
    result = service.authorize(cmd)
    assert result.decision == DecisionOutcome.ALLOW
    assert result.escalated is False
    assert len(test_ledger.entries) == 1
    assert test_ledger.entries[0].decision == "ALLOW"


def test_authorization_service_step_up(
    test_clock: ClockPort, test_ledger: InMemoryLedgerAdapter
) -> None:
    service = AuthorizationService(clock=test_clock, ledger=test_ledger)
    cmd = AuthorizeTransactionCommand(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=100000,  # $1,000.00 -> exceeds 50,000 threshold
        currency="USD",
        purpose="Equipment invoice",
        idempotency_key="idemp-002",
    )
    result = service.authorize(cmd)
    assert result.decision == DecisionOutcome.STEP_UP
    assert result.escalated is False


def test_authorization_service_deny(
    test_clock: ClockPort, test_ledger: InMemoryLedgerAdapter
) -> None:
    service = AuthorizationService(clock=test_clock, ledger=test_ledger)
    cmd = AuthorizeTransactionCommand(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=600000,  # $6,000.00 -> exceeds 500,000 threshold
        currency="USD",
        purpose="Excessive withdrawal",
        idempotency_key="idemp-003",
    )
    result = service.authorize(cmd)
    assert result.decision == DecisionOutcome.DENY


def test_health_service(test_clock: ClockPort) -> None:
    service = HealthService(clock=test_clock)
    health = service.check_health()
    assert health.status == "ok"
    assert health.version == "0.1.0"
    assert health.timestamp_utc == test_clock.now_utc()


def test_idempotent_replay_in_memory_reconcile_and_needs_review(
    test_authorization_service: AuthorizationService,
    test_payment_rail: FakePaymentRail,
) -> None:
    """In-memory idempotent replay returns real request_state, never SETTLED by default."""
    from app.domain.state_machine import RequestState

    test_payment_rail.should_succeed = True
    test_payment_rail.status = "RECONCILE"

    cmd = AuthorizeTransactionCommand(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=2000,
        currency="USD",
        purpose="In-memory replay test",
        idempotency_key="idemp-inmem-replay-1",
    )
    res1 = test_authorization_service.authorize(cmd)
    assert res1.request_state == RequestState.RECONCILE

    # Replay while in RECONCILE: must return RECONCILE, never SETTLED
    res_replay1 = test_authorization_service.authorize(cmd)
    assert res_replay1.request_state == RequestState.RECONCILE
    assert res_replay1.request_state != RequestState.SETTLED

    # Move request to NEEDS_REVIEW
    test_authorization_service._request_states[res1.request_id] = RequestState.NEEDS_REVIEW
    if res1.request_id in test_authorization_service._held_reservations:
        test_authorization_service._held_reservations[res1.request_id]["state"] = (
            RequestState.NEEDS_REVIEW.value
        )

    # Replay while in NEEDS_REVIEW: must return NEEDS_REVIEW, never SETTLED
    res_replay2 = test_authorization_service.authorize(cmd)
    assert res_replay2.request_state == RequestState.NEEDS_REVIEW
    assert res_replay2.request_state != RequestState.SETTLED
