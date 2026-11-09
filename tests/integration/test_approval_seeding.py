"""Tests verifying that demo step-up approvals are not seeded in production."""

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.services import AuthorizationService, MandateService
from app.infrastructure.clock import SystemUtcClock
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.models import Base
from app.infrastructure.paypal import FakePaymentRail


@pytest.fixture
def clean_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


def test_production_boot_clean_db_has_no_default_step_up_approval(clean_db, monkeypatch):
    """When booted with ENVIRONMENT=production on a clean DB, approvals queue must be empty.

    req_stepup_1001 must NOT appear unless DEMO_SEED=true.
    """
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DEMO_SEED", raising=False)

    clock = SystemUtcClock()
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=clean_db)
    rail = FakePaymentRail()

    service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=clean_db,
    )

    pending = service.get_pending_step_ups()
    req_ids = [p.request_id for p in pending]
    assert len(pending) == 0, f"Expected 0 pending approvals in production, got: {req_ids}"


def test_seed_default_step_up_requires_explicit_demo_seed_flag(clean_db, monkeypatch):
    """Calling _seed_default_step_up without DEMO_SEED=true must not seed anything."""
    monkeypatch.delenv("DEMO_SEED", raising=False)

    clock = SystemUtcClock()
    ledger = InMemoryLedgerAdapter()
    mandate_service = MandateService(clock=clock, db_session_factory=clean_db)
    rail = FakePaymentRail()

    service = AuthorizationService(
        clock=clock,
        ledger=ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
        db_session_factory=clean_db,
    )

    service._seed_default_step_up()
    assert len(service.get_pending_step_ups()) == 0

    # With DEMO_SEED=true
    monkeypatch.setenv("DEMO_SEED", "true")
    service._seed_default_step_up()
    pending = service.get_pending_step_ups()
    assert len(pending) == 1
    assert pending[0].request_id == "req_stepup_1001"


def test_boot_database_with_demo_seed_unset_leaves_approvals_empty(monkeypatch):
    """H10: scripts/boot.py seeds req_stepup_1001 only when DEMO_SEED=true.

    When booted with DEMO_SEED unset, GET /v1/approvals returns [].
    """
    from fastapi.testclient import TestClient

    import app.infrastructure.database as db_mod
    from app.api.dependencies import get_authorization_service, get_mandate_service
    from app.infrastructure.tokens import Role, create_role_token
    from app.main import app
    from scripts.boot import run_boot

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"
    monkeypatch.delenv("DEMO_SEED", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_at_least_32_bytes_long_12345")

    engine = create_engine(db_url)
    db_mod._engine = engine
    db_mod._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    try:
        success = run_boot()
        assert success is True

        factory = db_mod._session_factory
        clock = SystemUtcClock()
        mandate_service = MandateService(clock=clock, db_session_factory=factory)
        auth_service = AuthorizationService(
            clock=clock,
            ledger=InMemoryLedgerAdapter(),
            mandate_service=mandate_service,
            payment_rail=FakePaymentRail(),
            db_session_factory=factory,
        )

        app.dependency_overrides[get_authorization_service] = lambda: auth_service
        app.dependency_overrides[get_mandate_service] = lambda: mandate_service

        client = TestClient(app)
        token = create_role_token(Role.APPROVER, principal_id="supervisor-test")
        resp = client.get("/v1/approvals", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()
        db_mod._engine = None
        db_mod._session_factory = None
        engine.dispose()
        if os.path.exists(path):
            os.remove(path)
