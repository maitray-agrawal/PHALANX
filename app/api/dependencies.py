"""FastAPI dependencies for application service injection."""

import os
import sys
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status

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

    if is_test_environment():
        ledger = InMemoryLedgerAdapter()
        ledger.seed_demo_events()
        return ledger

    is_ready, err = check_database_readiness()
    if not is_ready:
        msg = f"PostgreSQL database is mandatory outside test mode: {err}"
        raise RuntimeError(msg)

    db_factory = get_session_factory()
    return DatabaseLedgerAdapter(session_factory=db_factory)


@lru_cache(maxsize=1)
def get_payment_rail() -> PaymentRail:
    if is_fake_rail():
        return FakePaymentRail()
    adapter = PayPalPaymentRailAdapter()
    return adapter


def get_mandate_service() -> MandateService:
    from app.infrastructure.database import check_database_readiness, get_session_factory

    if is_test_environment():
        db_factory = None
    else:
        is_ready, err = check_database_readiness()
        if not is_ready:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database unavailable for mandate authority verification: {err}",
            )
        db_factory = get_session_factory()

    return MandateService(clock=get_clock(), db_session_factory=db_factory)


@lru_cache(maxsize=1)
def get_authorization_service() -> AuthorizationService:
    from app.infrastructure.database import check_database_readiness, get_session_factory

    if is_test_environment():
        db_factory = None
    else:
        is_ready, err = check_database_readiness()
        if not is_ready:
            msg = f"PostgreSQL database is mandatory outside test mode: {err}"
            raise RuntimeError(msg)
        db_factory = get_session_factory()

    return AuthorizationService(
        clock=get_clock(),
        ledger=get_ledger(),
        mandate_service=get_mandate_service(),
        payment_rail=get_payment_rail(),
        db_session_factory=db_factory,
    )


def get_ledger_service(
    ledger: Annotated[LedgerPort | None, Depends(get_ledger)] = None,
) -> LedgerService:
    actual_ledger = ledger if ledger is not None else get_ledger()
    return LedgerService(ledger=actual_ledger)


def get_health_service() -> HealthService:
    return HealthService(clock=get_clock())


def get_reconciler_service(
    auth_service: Annotated[AuthorizationService, Depends(get_authorization_service)] = None,  # type: ignore[assignment]
    rail: Annotated[PaymentRail, Depends(get_payment_rail)] = None,  # type: ignore[assignment]
) -> Any:
    from app.application.reconciler import ReconcilerService
    from app.infrastructure.config import settings
    from app.infrastructure.database import get_session_factory

    actual_auth = auth_service if auth_service is not None else get_authorization_service()
    actual_rail = rail if rail is not None else get_payment_rail()
    clock = get_clock()
    db_factory = None if is_test_environment() else get_session_factory()
    return ReconcilerService(
        auth_service=actual_auth,
        payment_rail=actual_rail,
        clock=clock,
        db_session_factory=db_factory,
        max_age_seconds=settings.reconcile_max_age_seconds,
    )
