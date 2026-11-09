"""Integration tests for fail-closed DB behavior and revoked mandate persistence."""

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_clock
from app.application.dtos import CreateMandateCommand
from app.application.services import MandateService
from app.domain.mandates import MandateStatus
from app.infrastructure.models import Base, MandateModel
from app.infrastructure.tokens import Role, create_role_token
from app.main import app


def test_database_down_gives_503_and_no_financial_decision():
    """Verify that when database is down outside test mode, endpoints return 503."""
    client = TestClient(app, raise_server_exceptions=False)

    def broken_check():
        return False, "OperationalError: could not connect to server: Connection refused"

    token = create_role_token(Role.PRINCIPAL, principal_id="principal_treasury")
    headers = {"Authorization": f"Bearer {token}"}

    target_app_state = app.state.settings if hasattr(app.state, "settings") else None or patch
    with (
        patch("app.infrastructure.database.check_database_readiness", side_effect=broken_check),
        patch.object(target_app_state, "environment", "production", create=True),
        patch("app.infrastructure.config.settings.environment", "production"),
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
    ):
        resp = client.get("/v1/mandates/agent-auto-1", headers=headers)
        assert resp.status_code == 503
        data = resp.json()
        assert "detail" in data or "title" in data
        assert "decision" not in data


def test_mandate_revoked_in_db_is_never_resurrected_from_memory(tmp_path):
    """Verify that once a mandate is revoked in DB, it cannot be resurrected from memory."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    sqlite_db_path = tmp_path / "test_revocation.db"
    engine = create_engine(f"sqlite:///{sqlite_db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    clock = get_clock()
    mandate_service = MandateService(clock=clock, db_session_factory=session_factory)

    cmd = CreateMandateCommand(
        mandate_id="mandate-test-revocation-1",
        principal_id="principal-1",
        agent_id="agent-revocable",
        single_limit_minor=10_000,
        instant_threshold_minor=1_000,
        lifetime_budget_minor=50_000,
        currency="USD",
        allowed_payees=[],
        allow_unregistered_payees=True,
        allowed_purposes=[],
        valid_days=30,
    )
    mandate_service.create_mandate(cmd)

    active = mandate_service.get_active_mandate_for_agent("agent-revocable")
    assert active is not None
    assert active.status == MandateStatus.ACTIVE

    with session_factory() as session, session.begin():
        row = session.get(MandateModel, ("mandate-test-revocation-1", 1))
        assert row is not None
        row.status = MandateStatus.REVOKED.value

    active_after_revoke = mandate_service.get_active_mandate_for_agent("agent-revocable")
    assert active_after_revoke is None, "Revoked mandate was improperly resurrected!"

    fetched = mandate_service.get_mandate("mandate-test-revocation-1")
    assert fetched is not None
    assert fetched.status == MandateStatus.REVOKED
