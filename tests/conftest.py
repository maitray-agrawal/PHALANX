"""Shared pytest fixtures."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_authorization_service,
    get_clock,
    get_ledger,
    get_mandate_service,
    get_payment_rail,
)
from app.application.services import AuthorizationService, MandateService
from app.domain.ports import ClockPort
from app.infrastructure.config import settings
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.paypal import FakePaymentRail
from app.infrastructure.tokens import Role, create_role_token
from app.main import create_app

# Set valid secret key, admin token, and webhook ID for deterministic test suite execution
settings.environment = "test"
settings.payment_rail = "fake"
settings.secret_key = "test-secret-key-at-least-32-bytes-long-for-tests-1234"
settings.admin_token = "test-admin-token-at-least-24-characters"
settings.paypal_webhook_id = "WH-SANDBOX-TEST-12345"


class FixedTestClock(ClockPort):
    """Deterministic test clock."""

    def __init__(self, fixed_time: datetime | None = None) -> None:
        self._fixed_time = fixed_time or datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)

    def now_utc(self) -> datetime:
        return self._fixed_time


@pytest.fixture
def test_clock() -> FixedTestClock:
    return FixedTestClock()


@pytest.fixture
def test_ledger() -> InMemoryLedgerAdapter:
    return InMemoryLedgerAdapter()


@pytest.fixture
def test_payment_rail() -> FakePaymentRail:
    return FakePaymentRail()


@pytest.fixture
def test_mandate_service(test_clock: FixedTestClock) -> MandateService:
    return MandateService(clock=test_clock)


@pytest.fixture
def test_authorization_service(
    test_clock: FixedTestClock,
    test_ledger: InMemoryLedgerAdapter,
    test_payment_rail: FakePaymentRail,
    test_mandate_service: MandateService,
) -> AuthorizationService:
    return AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=test_payment_rail,
    )


@pytest.fixture
def agent_token() -> str:
    return create_role_token(
        role=Role.AGENT,
        principal_id="principal_treasury",
        agent_id="agent-auto-1",
    )


@pytest.fixture
def principal_token() -> str:
    return create_role_token(
        role=Role.PRINCIPAL,
        principal_id="principal_treasury",
    )


@pytest.fixture
def approver_token() -> str:
    return create_role_token(
        role=Role.APPROVER,
        principal_id="principal_treasury",
    )


@pytest.fixture
def auditor_token() -> str:
    return create_role_token(
        role=Role.AUDITOR,
        principal_id="principal_treasury",
    )


@pytest.fixture
def client(
    test_clock: FixedTestClock,
    test_ledger: InMemoryLedgerAdapter,
    test_payment_rail: FakePaymentRail,
    test_mandate_service: MandateService,
    test_authorization_service: AuthorizationService,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_clock] = lambda: test_clock
    app.dependency_overrides[get_ledger] = lambda: test_ledger
    app.dependency_overrides[get_payment_rail] = lambda: test_payment_rail
    app.dependency_overrides[get_mandate_service] = lambda: test_mandate_service
    app.dependency_overrides[get_authorization_service] = lambda: test_authorization_service
    return TestClient(app)
