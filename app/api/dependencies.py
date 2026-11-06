"""FastAPI dependencies for application service injection."""

import os
import sys
from functools import lru_cache

from app.application.services import (
    AuthorizationService,
    HealthService,
    LedgerService,
    MandateService,
)
from app.domain.ports import LedgerPort, PaymentRail
from app.infrastructure.clock import SystemUtcClock
from app.infrastructure.config import settings
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.paypal import FakePaymentRail, PayPalPaymentRailAdapter


def is_test_environment() -> bool:
    if settings.environment.lower() in ("production", "staging", "prod"):
        return False
    return (
        "pytest" in sys.modules
        or "PYTEST_CURRENT_TEST" in os.environ
        or settings.environment.lower() in ("test", "testing")
        or os.getenv("ENVIRONMENT", "").lower() in ("test", "testing")
    )


def is_fake_rail() -> bool:
    rail = os.getenv("PAYMENT_RAIL", settings.payment_rail).lower()
    return rail == "fake" or is_test_environment()


@lru_cache(maxsize=1)
def get_clock() -> SystemUtcClock:
    return SystemUtcClock()


@lru_cache(maxsize=1)
def get_ledger() -> LedgerPort:
    from app.infrastructure.database import check_database_readiness, get_session_factory
    from app.infrastructure.db_ledger_repo import DatabaseLedgerAdapter

    is_test_or_fake = is_test_environment() or is_fake_rail()
    is_ready, err = check_database_readiness()
    if not is_ready:
        if not is_test_or_fake:
            msg = f"PostgreSQL database is mandatory outside test/fake mode: {err}"
            raise RuntimeError(msg)
        ledger = InMemoryLedgerAdapter()
        ledger.seed_demo_events()
        return ledger

    db_factory = get_session_factory()
    if is_test_or_fake and "sqlite" in settings.database_url:
        mem_ledger = InMemoryLedgerAdapter(db_session_factory=db_factory)
        mem_ledger.seed_demo_events()
        return mem_ledger

    return DatabaseLedgerAdapter(session_factory=db_factory)


@lru_cache(maxsize=1)
def get_payment_rail() -> PaymentRail:
    is_test_or_fake = is_test_environment() or is_fake_rail()
    if is_test_or_fake:
        return FakePaymentRail()
    return PayPalPaymentRailAdapter()


@lru_cache(maxsize=1)
def get_mandate_service() -> MandateService:
    return MandateService(clock=get_clock())


@lru_cache(maxsize=1)
def get_authorization_service() -> AuthorizationService:
    from app.infrastructure.database import check_database_readiness, get_session_factory

    is_test_or_fake = is_test_environment() or is_fake_rail()
    is_ready, err = check_database_readiness()
    if not is_ready:
        if not is_test_or_fake:
            msg = f"PostgreSQL database is mandatory outside test/fake mode: {err}"
            raise RuntimeError(msg)
        db_factory = None
    else:
        db_factory = get_session_factory()

    return AuthorizationService(
        clock=get_clock(),
        ledger=get_ledger(),
        mandate_service=get_mandate_service(),
        payment_rail=get_payment_rail(),
        db_session_factory=db_factory,
    )


@lru_cache(maxsize=1)
def get_ledger_service() -> LedgerService:
    return LedgerService(ledger=get_ledger())


def get_health_service() -> HealthService:
    return HealthService(clock=get_clock())
