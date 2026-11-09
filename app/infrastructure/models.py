"""SQLAlchemy 2 database models for PHALANX.

Invariants:
- Strict integer minor unit typing (BigInteger).
- Check constraints to guarantee (spent + reserved <= allocated).
- Unique constraints on idempotency keys and event hashes.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"
    RECONCILE = "RECONCILE"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class AgentBudgetModel(Base):
    """Cumulative spending and reservation limits per agent."""

    __tablename__ = "agent_budgets"

    agent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mandate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    allocated_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spent_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        CheckConstraint(
            "spent_minor + reserved_minor <= allocated_minor",
            name="chk_budget_spent_plus_reserved_within_allocated",
        ),
        CheckConstraint("spent_minor >= 0", name="chk_spent_non_negative"),
        CheckConstraint("reserved_minor >= 0", name="chk_reserved_non_negative"),
        CheckConstraint("allocated_minor >= 0", name="chk_allocated_non_negative"),
    )

    @property
    def available_minor(self) -> int:
        """Remaining unreserved and unspent budget available for reservation."""
        return self.allocated_minor - self.spent_minor - self.reserved_minor


class BudgetReservationModel(Base):
    """Individual transaction reservations under an agent budget."""

    __tablename__ = "budget_reservations"

    reservation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ReservationStatus.PENDING.value
    )
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (CheckConstraint("amount_minor > 0", name="chk_reservation_positive"),)


class IdempotencyModel(Base):
    """Caches authorization decisions against intent digests."""

    __tablename__ = "idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    intent_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    response_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class StepUpApprovalModel(Base):
    """Binds supervisor authorizations to SHA-256 canonical intent digests."""

    __tablename__ = "step_up_approvals"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expected_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ApprovalStatus.PENDING.value
    )
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    approver_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class LedgerEventModel(Base):
    """Immutable hash-chained audit event log."""

    __tablename__ = "ledger_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    recipient_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (UniqueConstraint("event_seq", name="uq_ledger_events_event_seq"),)


class MandateModel(Base):
    """Persisted financial authority mandates with cryptographic seal."""

    __tablename__ = "mandates"

    mandate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=1)
    principal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    single_limit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    instant_threshold_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lifetime_budget_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    allowed_payees_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    allowed_purposes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    allow_unregistered_payees: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_invoice_reference: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    signed_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    def to_domain(self) -> Any:
        import json

        from app.domain.mandates import Mandate, MandateStatus

        return Mandate(
            mandate_id=self.mandate_id,
            version=int(self.version),
            principal_id=self.principal_id,
            agent_id=self.agent_id,
            single_limit_minor=int(self.single_limit_minor),
            instant_threshold_minor=int(self.instant_threshold_minor),
            lifetime_budget_minor=int(self.lifetime_budget_minor),
            currency=self.currency,
            allowed_payees=tuple(json.loads(self.allowed_payees_json)),
            allow_unregistered_payees=bool(self.allow_unregistered_payees),
            require_invoice_reference=bool(self.require_invoice_reference),
            allowed_purposes=tuple(json.loads(self.allowed_purposes_json)),
            valid_from_utc=(
                self.valid_from_utc.replace(tzinfo=UTC)
                if self.valid_from_utc.tzinfo is None
                else self.valid_from_utc
            ),
            valid_until_utc=(
                self.valid_until_utc.replace(tzinfo=UTC)
                if self.valid_until_utc.tzinfo is None
                else self.valid_until_utc
            ),
            status=MandateStatus(self.status),
            key_id=self.key_id,
            signature=self.signature,
        )
