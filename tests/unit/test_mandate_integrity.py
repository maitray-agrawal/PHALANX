"""Tests for mandate cryptographic integrity, fixed seed dates, and tamper detection."""

from datetime import UTC, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.services import (
    FIXED_MANDATE_VALID_FROM_UTC,
    FIXED_MANDATE_VALID_UNTIL_UTC,
    MandateService,
)
from app.domain.ports import ClockPort
from app.infrastructure.models import Base


class FixedTestClock(ClockPort):
    def now_utc(self) -> datetime:
        return datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


def test_mandate_seed_fixed_dates_and_integrity() -> None:
    """Mandates seeded must have exact fixed validity dates and valid Ed25519 signature."""
    clock = FixedTestClock()
    service = MandateService(clock=clock)

    mandate = service.get_mandate("mandate_default_sandbox")
    assert mandate is not None
    assert mandate.valid_from_utc == FIXED_MANDATE_VALID_FROM_UTC
    assert mandate.valid_until_utc == FIXED_MANDATE_VALID_UNTIL_UTC
    assert mandate.valid_from_utc == datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC)
    assert mandate.valid_until_utc == datetime(2027, 3, 31, 23, 59, 59, tzinfo=UTC)

    # Signature must verify over canonical signable payload
    assert service.verify_mandate_integrity(mandate) is True


def test_mandate_two_reads_return_identical_data() -> None:
    """Two subsequent reads from the mandate store return identical data."""
    clock = FixedTestClock()
    service = MandateService(clock=clock)

    read1 = service.get_mandate("mandate_default_sandbox")
    read2 = service.get_mandate("mandate_default_sandbox")

    assert read1 is not None and read2 is not None
    assert read1.mandate_id == read2.mandate_id
    assert read1.version == read2.version
    assert read1.single_limit_minor == read2.single_limit_minor
    assert read1.instant_threshold_minor == read2.instant_threshold_minor
    assert read1.lifetime_budget_minor == read2.lifetime_budget_minor
    assert read1.currency == read2.currency
    assert read1.valid_from_utc == read2.valid_from_utc
    assert read1.valid_until_utc == read2.valid_until_utc
    assert read1.signature == read2.signature
    assert read1.to_signable_dict() == read2.to_signable_dict()


def test_mandate_editing_stored_row_makes_verification_fail() -> None:
    """Editing the database-stored row causes cryptographic seal verification to fail."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    clock = FixedTestClock()
    service = MandateService(clock=clock, db_session_factory=session_factory)

    # 1. Verify fresh mandate passes integrity check
    fresh_mandate = service.get_mandate("mandate_default_sandbox")
    assert fresh_mandate is not None
    assert service.verify_mandate_integrity(fresh_mandate) is True

    # 2. Directly tamper with the database row (e.g. increase spending limit)
    with session_factory() as session, session.begin():
        session.execute(
            text(
                "UPDATE mandates SET single_limit_minor = 999999 "
                "WHERE mandate_id = 'mandate_default_sandbox'"
            )
        )

    # 3. Read back the mandate: returns stored values directly from the database
    tampered_mandate = service.get_mandate("mandate_default_sandbox")
    assert tampered_mandate is not None
    assert tampered_mandate.single_limit_minor == 999999

    # 4. Cryptographic integrity check MUST fail because signature was over original payload
    assert service.verify_mandate_integrity(tampered_mandate) is False


def test_mandate_editing_dates_in_stored_row_makes_verification_fail() -> None:
    """Editing validity dates in the database row invalidates cryptographic seal."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    clock = FixedTestClock()
    service = MandateService(clock=clock, db_session_factory=session_factory)

    # Tamper with expiration date in DB
    with session_factory() as session, session.begin():
        session.execute(
            text(
                "UPDATE mandates SET valid_until_utc = '2030-01-01 00:00:00' "
                "WHERE mandate_id = 'mandate_default_sandbox'"
            )
        )

    tampered_date_mandate = service.get_mandate("mandate_default_sandbox")
    assert tampered_date_mandate is not None
    assert service.verify_mandate_integrity(tampered_date_mandate) is False


def test_mandate_api_two_reads_and_tamper_fails() -> None:
    """GET /v1/mandates/{id} returns stored values, identical across reads,
    failing on row tamper.
    """
    from fastapi.testclient import TestClient

    from app.api.dependencies import (
        get_authorization_service,
        get_clock,
        get_mandate_service,
    )
    from app.application.services import AuthorizationService
    from app.domain.mandates import Mandate
    from app.infrastructure.ledger import InMemoryLedgerAdapter
    from app.infrastructure.paypal import FakePaymentRail
    from app.infrastructure.tokens import Role, create_role_token
    from app.main import create_app

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    clock = FixedTestClock()
    mandate_svc = MandateService(clock=clock, db_session_factory=session_factory)
    auth_svc = AuthorizationService(
        clock=clock,
        ledger=InMemoryLedgerAdapter(),
        mandate_service=mandate_svc,
        payment_rail=FakePaymentRail(should_succeed=True),
    )

    app = create_app()
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_mandate_service] = lambda: mandate_svc
    app.dependency_overrides[get_authorization_service] = lambda: auth_svc

    client = TestClient(app)
    token = create_role_token(
        role=Role.AGENT,
        principal_id="principal_treasury",
        agent_id="agent-auto-1",
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Two reads return identical data
    resp1 = client.get("/v1/mandates/mandate_default_sandbox", headers=headers)
    resp2 = client.get("/v1/mandates/mandate_default_sandbox", headers=headers)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()

    data = resp1.json()
    assert data["valid_from_utc"].startswith("2026-11-01T00:00:00")
    assert data["valid_until_utc"].startswith("2027-03-31T23:59:59")

    # Verify signature over returned fields
    mandate_from_api = Mandate(
        mandate_id=data["mandate_id"],
        version=data["version"],
        principal_id=data["principal_id"],
        agent_id=data["agent_id"],
        single_limit_minor=data["single_limit_minor"],
        instant_threshold_minor=data["instant_threshold_minor"],
        lifetime_budget_minor=data["lifetime_budget_minor"],
        currency=data["currency"],
        allowed_payees=tuple(data["allowed_payees"]),
        allowed_purposes=tuple(data["allowed_purposes"]),
        valid_from_utc=datetime.fromisoformat(data["valid_from_utc"]),
        valid_until_utc=datetime.fromisoformat(data["valid_until_utc"]),
        status=data["status"],
        key_id=data["key_id"],
        signature=data["signature"],
        allow_unregistered_payees=data.get("allow_unregistered_payees", False),
        require_invoice_reference=data.get("require_invoice_reference", False),
    )
    assert mandate_svc.verify_mandate_integrity(mandate_from_api) is True

    # Directly edit the stored row
    with session_factory() as session, session.begin():
        session.execute(
            text(
                "UPDATE mandates SET single_limit_minor = 888888 "
                "WHERE mandate_id = 'mandate_default_sandbox'"
            )
        )

    # Read again via API: returns stored values only
    resp_tampered = client.get("/v1/mandates/mandate_default_sandbox", headers=headers)
    assert resp_tampered.status_code == 200
    tampered_data = resp_tampered.json()
    assert tampered_data["single_limit_minor"] == 888888

    # Signature verification over returned fields FAILS
    tampered_mandate_from_api = Mandate(
        mandate_id=tampered_data["mandate_id"],
        version=tampered_data["version"],
        principal_id=tampered_data["principal_id"],
        agent_id=tampered_data["agent_id"],
        single_limit_minor=tampered_data["single_limit_minor"],
        instant_threshold_minor=tampered_data["instant_threshold_minor"],
        lifetime_budget_minor=tampered_data["lifetime_budget_minor"],
        currency=tampered_data["currency"],
        allowed_payees=tuple(tampered_data["allowed_payees"]),
        allowed_purposes=tuple(tampered_data["allowed_purposes"]),
        valid_from_utc=datetime.fromisoformat(tampered_data["valid_from_utc"]),
        valid_until_utc=datetime.fromisoformat(tampered_data["valid_until_utc"]),
        status=tampered_data["status"],
        key_id=tampered_data["key_id"],
        signature=tampered_data["signature"],
        allow_unregistered_payees=tampered_data.get("allow_unregistered_payees", False),
        require_invoice_reference=tampered_data.get("require_invoice_reference", False),
    )
    assert mandate_svc.verify_mandate_integrity(tampered_mandate_from_api) is False
