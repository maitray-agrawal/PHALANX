"""Shared pytest fixtures."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_clock, get_ledger
from app.domain.ports import ClockPort
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.main import create_app


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
def client(test_clock: FixedTestClock, test_ledger: InMemoryLedgerAdapter) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_clock] = lambda: test_clock
    app.dependency_overrides[get_ledger] = lambda: test_ledger
    return TestClient(app)
