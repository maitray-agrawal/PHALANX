"""FastAPI dependencies for application service injection."""

from functools import lru_cache

from app.application.services import (
    AuthorizationService,
    HealthService,
    LedgerService,
    MandateService,
)
from app.domain.ports import PaymentRail
from app.infrastructure.clock import SystemUtcClock
from app.infrastructure.config import settings
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.paypal import FakePaymentRail, PayPalPaymentRailAdapter


@lru_cache(maxsize=1)
def get_clock() -> SystemUtcClock:
    return SystemUtcClock()


@lru_cache(maxsize=1)
def get_ledger() -> InMemoryLedgerAdapter:
    from app.infrastructure.database import check_database_readiness, get_session_factory

    db_factory = None
    is_ready, _ = check_database_readiness()
    if is_ready:
        db_factory = get_session_factory()

    ledger = InMemoryLedgerAdapter(db_session_factory=db_factory)
    ledger.seed_demo_events()
    return ledger


@lru_cache(maxsize=1)
def get_payment_rail() -> PaymentRail:
    if settings.paypal_client_id and settings.paypal_client_secret:
        return PayPalPaymentRailAdapter()
    return FakePaymentRail()


@lru_cache(maxsize=1)
def get_mandate_service() -> MandateService:
    return MandateService(clock=get_clock())


@lru_cache(maxsize=1)
def get_authorization_service() -> AuthorizationService:
    from app.infrastructure.database import check_database_readiness, get_session_factory

    db_factory = None
    is_ready, _ = check_database_readiness()
    if is_ready:
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
