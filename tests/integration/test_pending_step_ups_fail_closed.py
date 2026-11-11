"""Tests verifying that get_pending_step_ups fails closed on DB error."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.application.services import AuthorizationService, MandateService
from app.infrastructure.clock import SystemUtcClock
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.paypal import FakePaymentRail
from app.infrastructure.tokens import Role, create_role_token
from app.main import app


def test_get_pending_step_ups_raises_on_db_error():
    """get_pending_step_ups must raise on DB error without falling back to memory."""
    clock = SystemUtcClock()
    ledger = InMemoryLedgerAdapter()
    broken_factory = MagicMock(side_effect=RuntimeError("Database connection lost"))
    mandate_service = MandateService(clock=clock, db_session_factory=None)
    rail = FakePaymentRail()

    service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=broken_factory,
    )

    with pytest.raises(RuntimeError, match="Database connection lost"):
        service.get_pending_step_ups()


def test_api_approvals_returns_503_on_db_error():
    """GET /v1/approvals must return 503 when database is unavailable."""
    client = TestClient(app)
    token = create_role_token(Role.APPROVER, principal_id="human-supervisor")
    headers = {"Authorization": f"Bearer {token}"}

    from app.api.dependencies import get_authorization_service

    broken_service = MagicMock()
    broken_service.get_pending_step_ups.side_effect = RuntimeError("PostgreSQL unavailable")
    app.dependency_overrides[get_authorization_service] = lambda: broken_service

    try:
        resp = client.get("/v1/approvals", headers=headers)
        assert resp.status_code == 503
        assert "Database unavailable" in resp.json().get("detail", "")
    finally:
        app.dependency_overrides.clear()
