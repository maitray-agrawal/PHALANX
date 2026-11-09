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
