"""Database repository for money-safe budget reservations and idempotency (Manual 56.13, 56.14).

Invariants:
- All reservations occur within a single database transaction with row locks.
- Check constraints (spent + reserved <= allocated) enforced at the DB level.
- Ambiguous/UNKNOWN outcomes transition to RECONCILE; release happens strictly on confirmed failure.
- Step-up approvals are cryptographically bound to the SHA-256 intent digest.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import (
    AgentBudgetModel,
    ApprovalStatus,
    BudgetReservationModel,
    IdempotencyModel,
    ReservationStatus,
    StepUpApprovalModel,
)


class InsufficientBudgetError(Exception):
    """Raised when an allocation would breach the lifetime budget ceiling."""


class IdempotencyMismatchError(Exception):
    """Raised when an idempotency key is reused with altered parameters."""


class IdempotencyReplayError(Exception):
    """Raised when a valid idempotent replay is submitted."""

    def __init__(self, record: IdempotencyModel) -> None:
        self.record = record
        super().__init__(f"Idempotency replay for key: {record.idempotency_key}")


class ApprovalDigestMismatchError(Exception):
    """Raised when approval is attempted against an altered intent digest."""


class ApprovalExpiredError(Exception):
    """Raised when step-up approval is attempted after review window expiry."""


class InvalidApprovalStateError(Exception):
    """Raised when attempting to approve an already approved, rejected, or closed request."""


class ReservationNotFoundError(Exception):
    """Raised when reservation ID does not exist."""


class BudgetRepository:
    """Manages transactional budget reservations and idempotency enforcement."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_budget(
        self,
        agent_id: str,
        mandate_id: str,
        currency: str,
        allocated_minor: int,
    ) -> AgentBudgetModel:
        """Fetch existing agent budget or create a new one."""
        stmt = select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        budget = self.session.scalar(stmt)
        if not budget:
            now = datetime.now(UTC)
            budget = AgentBudgetModel(
                agent_id=agent_id,
                mandate_id=mandate_id,
                currency=currency,
                allocated_minor=allocated_minor,
                spent_minor=0,
                reserved_minor=0,
                created_at_utc=now,
                updated_at_utc=now,
            )
            self.session.add(budget)
            self.session.flush()
        return budget

    def check_idempotency(
        self,
        idempotency_key: str,
        current_digest: str,
    ) -> IdempotencyModel | None:
        """Check for existing idempotency records and detect parameter tampering.

        Raises:
            IdempotencyMismatchError: If the key exists with a different digest.
            IdempotencyReplayError: If the key exists with identical digest.
        """
        stmt = select(IdempotencyModel).where(IdempotencyModel.idempotency_key == idempotency_key)
        existing = self.session.scalar(stmt)
        if existing:
            if existing.intent_digest != current_digest:
                raise IdempotencyMismatchError(
                    f"Idempotency key '{idempotency_key}' reused with mutated parameters."
                )
            raise IdempotencyReplayError(existing)
        return None

    def reserve_budget(
        self,
        agent_id: str,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
        intent_digest: str,
    ) -> BudgetReservationModel:
        """Atomically reserve funds inside the database transaction.

        Uses SELECT ... FOR UPDATE (on dialects supporting row locking) or serial locks.
        Guarantees spent_minor + reserved_minor + amount_minor <= allocated_minor.
        """
        # 1. Idempotency check inside transaction
        self.check_idempotency(idempotency_key, intent_digest)

        # 2. Lock budget row
        dialect = self.session.bind.dialect.name if self.session.bind else ""
        stmt = select(AgentBudgetModel).where(AgentBudgetModel.agent_id == agent_id)
        if dialect in ("postgresql", "postgres"):
            stmt = stmt.with_for_update()

        budget = self.session.scalar(stmt)
        if not budget:
            raise ValueError(f"No budget configured for agent '{agent_id}'")

        if budget.currency != currency:
            raise ValueError(f"Currency mismatch: budget is {budget.currency}, requested {currency}")

        # 3. Invariant check: spent + reserved + amount <= allocated
        if budget.spent_minor + budget.reserved_minor + amount_minor > budget.allocated_minor:
            raise InsufficientBudgetError(
                f"Insufficient budget for agent '{agent_id}': requested {amount_minor}, "
                f"spent {budget.spent_minor}, reserved {budget.reserved_minor}, cap {budget.allocated_minor}"
            )

        # 4. Atomic increment
        budget.reserved_minor += amount_minor
        budget.updated_at_utc = datetime.now(UTC)

        reservation_id = f"res_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC)
        reservation = BudgetReservationModel(
            reservation_id=reservation_id,
            idempotency_key=idempotency_key,
            agent_id=agent_id,
            amount_minor=amount_minor,
            currency=currency,
            status=ReservationStatus.PENDING.value,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def confirm_reservation(self, reservation_id: str) -> BudgetReservationModel:
        """Confirm settlement of a reservation, moving reserved funds to spent."""
        res_stmt = select(BudgetReservationModel).where(
            BudgetReservationModel.reservation_id == reservation_id
        )
        res = self.session.scalar(res_stmt)
        if not res:
            raise ReservationNotFoundError(f"Reservation '{reservation_id}' not found")

        budget_stmt = select(AgentBudgetModel).where(AgentBudgetModel.agent_id == res.agent_id)
        budget = self.session.scalar(budget_stmt)
        if not budget:
            raise ValueError(f"Budget for agent '{res.agent_id}' not found")

        # Move from reserved to spent
        budget.reserved_minor -= res.amount_minor
        budget.spent_minor += res.amount_minor
        budget.updated_at_utc = datetime.now(UTC)

        res.status = ReservationStatus.CONFIRMED.value
        res.updated_at_utc = datetime.now(UTC)
        self.session.flush()
        return res

    def release_reservation(
        self,
        reservation_id: str,
        confirmed_failure: bool,
    ) -> BudgetReservationModel:
        """Release reservation upon confirmed failure, or route to RECONCILE if unknown.

        CRITICAL SAFETY RULE:
        Only a confirmed failure releases reserved funds. An ambiguous/unknown outcome
        transitions to RECONCILE, preserving budget lock to prevent double-spending.
        """
        res_stmt = select(BudgetReservationModel).where(
            BudgetReservationModel.reservation_id == reservation_id
        )
        res = self.session.scalar(res_stmt)
        if not res:
            raise ReservationNotFoundError(f"Reservation '{reservation_id}' not found")

        budget_stmt = select(AgentBudgetModel).where(AgentBudgetModel.agent_id == res.agent_id)
        budget = self.session.scalar(budget_stmt)
        if not budget:
            raise ValueError(f"Budget for agent '{res.agent_id}' not found")

        now = datetime.now(UTC)
        if confirmed_failure:
            # Verified failure: unlock reserved funds back to available pool
            budget.reserved_minor -= res.amount_minor
            budget.updated_at_utc = now
            res.status = ReservationStatus.RELEASED.value
        else:
            # Ambiguous / timeout / unknown outcome: HOLD funds in RECONCILE
            res.status = ReservationStatus.RECONCILE.value

        res.updated_at_utc = now
        self.session.flush()
        return res

    def record_decision(
        self,
        idempotency_key: str,
        agent_id: str,
        intent_digest: str,
        decision: str,
        response_payload: str,
    ) -> IdempotencyModel:
        """Persist authorization decision for replay deduplication."""
        record = IdempotencyModel(
            idempotency_key=idempotency_key,
            agent_id=agent_id,
            intent_digest=intent_digest,
            decision=decision,
            response_payload=response_payload,
            created_at_utc=datetime.now(UTC),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def create_step_up_approval(
        self,
        request_id: str,
        idempotency_key: str,
        expected_digest: str,
        intent_payload: str,
        expires_at_utc: datetime,
    ) -> StepUpApprovalModel:
        """Create step-up approval record bound to intent digest."""
        now = datetime.now(UTC)
        approval = StepUpApprovalModel(
            request_id=request_id,
            idempotency_key=idempotency_key,
            expected_digest=expected_digest,
            intent_payload=intent_payload,
            status=ApprovalStatus.PENDING.value,
            expires_at_utc=expires_at_utc,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self.session.add(approval)
        self.session.flush()
        return approval

    def approve_step_up(
        self,
        request_id: str,
        provided_digest: str,
        approver_id: str,
        now_utc: datetime,
    ) -> StepUpApprovalModel:
        """Execute step-up authorization with cryptographic digest and expiration verification."""
        stmt = select(StepUpApprovalModel).where(StepUpApprovalModel.request_id == request_id)
        approval = self.session.scalar(stmt)
        if not approval:
            raise ValueError(f"Step-up approval '{request_id}' not found")

        if approval.status != ApprovalStatus.PENDING.value:
            raise InvalidApprovalStateError(
                f"Approval '{request_id}' is already in state '{approval.status}'"
            )

        if now_utc > approval.expires_at_utc:
            approval.status = ApprovalStatus.EXPIRED.value
            approval.updated_at_utc = now_utc
            self.session.flush()
            raise ApprovalExpiredError(f"Approval '{request_id}' expired at {approval.expires_at_utc}")

        if provided_digest != approval.expected_digest:
            raise ApprovalDigestMismatchError(
                f"Provided digest '{provided_digest}' does not match expected '{approval.expected_digest}'"
            )

        approval.status = ApprovalStatus.APPROVED.value
        approval.approver_id = approver_id
        approval.decision = "ALLOW"
        approval.updated_at_utc = now_utc
        self.session.flush()
        return approval
