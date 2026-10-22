"""FastAPI dependencies for application service injection."""

from functools import lru_cache

from app.application.services import AuthorizationService, HealthService
from app.infrastructure.clock import SystemUtcClock
from app.infrastructure.ledger import InMemoryLedgerAdapter


@lru_cache(maxsize=1)
def get_clock() -> SystemUtcClock:
    return SystemUtcClock()


@lru_cache(maxsize=1)
def get_ledger() -> InMemoryLedgerAdapter:
    return InMemoryLedgerAdapter()


def get_health_service() -> HealthService:
    return HealthService(clock=get_clock())


def get_authorization_service() -> AuthorizationService:
    return AuthorizationService(clock=get_clock(), ledger=get_ledger())
