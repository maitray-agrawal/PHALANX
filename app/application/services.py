"""Application services coordinating use cases.

Invariants:
- All entry points go through application services.
- Deterministic policy evaluation with pure domain logic.
- Cryptographic hash chaining on all ledger writes.
- Mandatory intent digest verification before human approval execution.
- Payment rail dispatch only on confirmed ALLOW.
"""

import hashlib
import logging
import os
from datetime import UTC, datetime, timedelta
from threading import Lock, RLock
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import select

from app.application.dtos import (
    ApprovalCommand,
    AuthorizationResponseDTO,
    AuthorizeTransactionCommand,
    CreateMandateCommand,
    HealthStatusDTO,
    LedgerEventDTO,
    LedgerVerificationDTO,
    MandateResponseDTO,
    PendingStepUpDTO,
)
from app.domain.canonical_json import canonical_json_bytes
from app.domain.mandates import Mandate, MandateStatus
from app.domain.models import (
    DecisionOutcome,
    Money,
    PolicyEvaluationResult,
    TransactionIntent,
)
from app.domain.policy import (
    PolicyDecision,
    PolicyReasonCode,
    PolicyState,
    evaluate_policy,
)
from app.domain.ports import ClockPort, LedgerPort, PaymentRail, PaymentResult
from app.domain.state_machine import RequestState, transition_request_state
from app.infrastructure.crypto import (
    load_or_generate_keypair,
    sign_bytes,
    verify_mandate_seal,
)
from app.infrastructure.db_budget_repo import (
    BudgetRepository,
    IdempotencyMismatchError,
    IdempotencyReplayError,
    InsufficientBudgetError,
)
from app.infrastructure.models import AgentBudgetModel
from app.infrastructure.paypal import FakePaymentRail

logger = logging.getLogger(__name__)


def compute_intent_digest(
    agent_id: str,
    recipient_id: str,
    amount_minor: int,
    currency: str,
    purpose: str,
    idempotency_key: str,
) -> str:
    """Compute SHA-256 digest of canonical intent fields."""
    canonical_dict = {
        "agent_id": agent_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "idempotency_key": idempotency_key,
        "purpose": purpose,
        "recipient_id": recipient_id,
    }
    raw = canonical_json_bytes(canonical_dict)
    return hashlib.sha256(raw).hexdigest()


FIXED_MANDATE_VALID_FROM_UTC = datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC)
FIXED_MANDATE_VALID_UNTIL_UTC = datetime(2027, 3, 31, 23, 59, 59, tzinfo=UTC)


class MandateService:
    """Manages Ed25519-signed authority mandates."""

    def __init__(
        self,
        clock: ClockPort,
        priv_key: bytes | None = None,
        pub_key: bytes | None = None,
        key_id: str | None = None,
        db_session_factory: Any | None = None,
    ) -> None:
        self._clock = clock
        self._db_session_factory = db_session_factory
        from app.infrastructure.config import settings

        self._is_test = (
            os.getenv("ENVIRONMENT") == "test" or getattr(settings, "environment", "") == "test"
        )
        if not self._is_test and self._db_session_factory is None:
            raise RuntimeError(
                "Database session factory is mandatory for MandateService outside test environment"
            )

        if priv_key and pub_key and key_id:
            self._priv_key = priv_key
            self._pub_key = pub_key
            self._key_id = key_id
        else:
            self._priv_key, self._pub_key, self._key_id = load_or_generate_keypair(
                key_hex=settings.mandate_signing_key_hex,
                key_file_path=settings.mandate_signing_key_file,
            )
        self._mandates: dict[str, Mandate] = {}
        self._history: dict[str, list[Mandate]] = {}
        self._lock = Lock()
        if self._db_session_factory is None or self._is_test:
            self._seed_default_mandate()

    def _save_mandate_to_db(self, mandate: Mandate, signed_payload_str: str) -> None:
        if self._db_session_factory is None:
            if not self._is_test:
                raise RuntimeError(
                    "Database session factory is mandatory for MandateService "
                    "outside test environment"
                )
            return

        import json

        from app.infrastructure.models import MandateModel

        with self._db_session_factory() as session, session.begin():
            existing = session.scalar(
                select(MandateModel).where(
                    MandateModel.mandate_id == mandate.mandate_id,
                    MandateModel.version == mandate.version,
                )
            )
            if not existing:
                row = MandateModel(
                    mandate_id=mandate.mandate_id,
                    version=mandate.version,
                    principal_id=mandate.principal_id,
                    agent_id=mandate.agent_id,
                    single_limit_minor=mandate.single_limit_minor,
                    instant_threshold_minor=mandate.instant_threshold_minor,
                    lifetime_budget_minor=mandate.lifetime_budget_minor,
                    currency=mandate.currency,
                    allowed_payees_json=json.dumps(list(mandate.allowed_payees)),
                    allowed_purposes_json=json.dumps(list(mandate.allowed_purposes)),
                    allow_unregistered_payees=mandate.allow_unregistered_payees,
                    require_invoice_reference=mandate.require_invoice_reference,
                    valid_from_utc=mandate.valid_from_utc,
                    valid_until_utc=mandate.valid_until_utc,
                    status=mandate.status.value,
                    key_id=mandate.key_id,
                    signature=mandate.signature,
                    signed_payload=signed_payload_str,
                )
                session.add(row)
            else:
                existing.status = mandate.status.value
                existing.updated_at_utc = datetime.now(UTC)

    def _seed_default_mandate(self) -> None:
        """Seed standard demo mandate with fixed temporal window (test mode only)."""
        mandate_id = "mandate_default_sandbox"
        valid_from = FIXED_MANDATE_VALID_FROM_UTC
        valid_until = FIXED_MANDATE_VALID_UNTIL_UTC
        payload = {
            "mandate_id": mandate_id,
            "version": 1,
            "principal_id": "principal_treasury",
            "agent_id": "agent-auto-1",
            "single_limit_minor": 500_000,  # $5,000 max single cap
            "instant_threshold_minor": 50_000,  # $500 instant threshold
            "lifetime_budget_minor": 2_500_000,  # $25,000 lifetime cap
            "currency": "USD",
            "allowed_payees": [],
            "allow_unregistered_payees": True,
            "allowed_purposes": [],
            "valid_from_utc": valid_from.isoformat(),
            "valid_until_utc": valid_until.isoformat(),
            "status": MandateStatus.ACTIVE.value,
            "key_id": self._key_id,
        }
        signed_bytes = canonical_json_bytes(payload)
        signed_payload_str = signed_bytes.decode("utf-8")
        sig = sign_bytes(self._priv_key, signed_bytes)
        mandate = Mandate(
            mandate_id=mandate_id,
            version=1,
            principal_id="principal_treasury",
            agent_id="agent-auto-1",
            single_limit_minor=500_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=2_500_000,
            currency="USD",
            allowed_payees=(),
            allow_unregistered_payees=True,
            allowed_purposes=(),
            valid_from_utc=valid_from,
            valid_until_utc=valid_until,
            status=MandateStatus.ACTIVE,
            key_id=self._key_id,
            signature=sig,
        )
        if self._db_session_factory is None:
            self._mandates[mandate_id] = mandate
            self._history[mandate_id] = [mandate]
        self._save_mandate_to_db(mandate, signed_payload_str)

    def get_active_mandate_for_agent(self, agent_id: str) -> Mandate | None:
        if self._db_session_factory is not None:
            from app.infrastructure.models import MandateModel

            with self._db_session_factory() as session:
                stmt = (
                    select(MandateModel)
                    .where(
                        MandateModel.agent_id == agent_id,
                        MandateModel.status == MandateStatus.ACTIVE.value,
                    )
                    .order_by(MandateModel.version.desc())
                    .limit(1)
                )
                row = session.scalar(stmt)
                return cast(Mandate, row.to_domain()) if row else None

        if not self._is_test:
            raise RuntimeError(
                "Database session factory is mandatory for MandateService outside test environment"
            )

        with self._lock:
            for mandate in self._mandates.values():
                if mandate.agent_id == agent_id and mandate.status == MandateStatus.ACTIVE:
                    return mandate
            return None

    def get_mandate(self, mandate_id: str) -> Mandate | None:
        if self._db_session_factory is not None:
            from app.infrastructure.models import MandateModel

            with self._db_session_factory() as session:
                stmt = (
                    select(MandateModel)
                    .where(MandateModel.mandate_id == mandate_id)
                    .order_by(MandateModel.version.desc())
                    .limit(1)
                )
                row = session.scalar(stmt)
                return cast(Mandate, row.to_domain()) if row else None

        if not self._is_test:
            raise RuntimeError(
                "Database session factory is mandatory for MandateService outside test environment"
            )

        with self._lock:
            return self._mandates.get(mandate_id)

    def create_mandate(self, cmd: CreateMandateCommand) -> MandateResponseDTO:
        now = self._clock.now_utc()
        valid_until = now + timedelta(days=cmd.valid_days)
        signable_dict = {
            "mandate_id": cmd.mandate_id,
            "version": 1,
            "principal_id": cmd.principal_id,
            "agent_id": cmd.agent_id,
            "single_limit_minor": cmd.single_limit_minor,
            "instant_threshold_minor": cmd.instant_threshold_minor,
            "lifetime_budget_minor": cmd.lifetime_budget_minor,
            "currency": cmd.currency,
            "allowed_payees": cmd.allowed_payees,
            "allow_unregistered_payees": cmd.allow_unregistered_payees,
            "allowed_purposes": cmd.allowed_purposes,
            "valid_from_utc": now.isoformat(),
            "valid_until_utc": valid_until.isoformat(),
            "status": MandateStatus.ACTIVE.value,
            "key_id": self._key_id,
        }
        signed_bytes = canonical_json_bytes(signable_dict)
        sig = sign_bytes(self._priv_key, signed_bytes)
        mandate = Mandate(
            mandate_id=cmd.mandate_id,
            version=1,
            principal_id=cmd.principal_id,
            agent_id=cmd.agent_id,
            single_limit_minor=cmd.single_limit_minor,
            instant_threshold_minor=cmd.instant_threshold_minor,
            lifetime_budget_minor=cmd.lifetime_budget_minor,
            currency=cmd.currency,
            allowed_payees=tuple(cmd.allowed_payees),
            allow_unregistered_payees=cmd.allow_unregistered_payees,
            allowed_purposes=tuple(cmd.allowed_purposes),
            valid_from_utc=now,
            valid_until_utc=valid_until,
            status=MandateStatus.ACTIVE,
            key_id=self._key_id,
            signature=sig,
        )
        with self._lock:
            self._mandates[cmd.mandate_id] = mandate
            self._history[cmd.mandate_id] = [mandate]
        self._save_mandate_to_db(mandate, signed_bytes.decode("utf-8"))

        return MandateResponseDTO(
            mandate_id=mandate.mandate_id,
            version=mandate.version,
            principal_id=mandate.principal_id,
            agent_id=mandate.agent_id,
            single_limit_minor=mandate.single_limit_minor,
            instant_threshold_minor=mandate.instant_threshold_minor,
            lifetime_budget_minor=mandate.lifetime_budget_minor,
            currency=mandate.currency,
            allowed_payees=list(mandate.allowed_payees),
            allow_unregistered_payees=mandate.allow_unregistered_payees,
            allowed_purposes=list(mandate.allowed_purposes),
            valid_from_utc=mandate.valid_from_utc,
            valid_until_utc=mandate.valid_until_utc,
            status=mandate.status,
            key_id=mandate.key_id,
            signature=mandate.signature,
        )

    def supersede_mandate(
        self,
        mandate_id: str,
        *,
        single_limit_minor: int | None = None,
        instant_threshold_minor: int | None = None,
        lifetime_budget_minor: int | None = None,
        allowed_payees: list[str] | None = None,
        allow_unregistered_payees: bool | None = None,
        allowed_purposes: list[str] | None = None,
        valid_days: int | None = None,
    ) -> MandateResponseDTO:
        """Create a new version of an active mandate and mark the previous version SUPERSEDED.

        Invariants:
        - Old versions are never edited in place (frozen).
        - Version numbers are strictly monotonic (+1).
        """
        if self._db_session_factory is not None:
            current = self.get_mandate(mandate_id)
        elif not self._is_test:
            raise RuntimeError(
                "Database session factory is mandatory for MandateService outside test environment"
            )
        else:
            with self._lock:
                current = self._mandates.get(mandate_id)

        if not current:
            raise ValueError(f"Mandate {mandate_id} not found")
        if current.status != MandateStatus.ACTIVE:
            raise ValueError(f"Cannot supersede mandate {mandate_id} with status {current.status}")

        now = self._clock.now_utc()
        new_version = current.version + 1
        valid_until = (
            now + timedelta(days=valid_days) if valid_days is not None else current.valid_until_utc
        )

        effective_payees = (
            allowed_payees if allowed_payees is not None else list(current.allowed_payees)
        )
        effective_allow_unregistered = (
            allow_unregistered_payees
            if allow_unregistered_payees is not None
            else current.allow_unregistered_payees
        )
        effective_purposes = (
            allowed_purposes if allowed_purposes is not None else list(current.allowed_purposes)
        )

        signable_dict = {
            "mandate_id": current.mandate_id,
            "version": new_version,
            "principal_id": current.principal_id,
            "agent_id": current.agent_id,
            "single_limit_minor": (
                single_limit_minor if single_limit_minor is not None else current.single_limit_minor
            ),
            "instant_threshold_minor": (
                instant_threshold_minor
                if instant_threshold_minor is not None
                else current.instant_threshold_minor
            ),
            "lifetime_budget_minor": (
                lifetime_budget_minor
                if lifetime_budget_minor is not None
                else current.lifetime_budget_minor
            ),
            "currency": current.currency,
            "allowed_payees": effective_payees,
            "allow_unregistered_payees": effective_allow_unregistered,
            "allowed_purposes": effective_purposes,
            "valid_from_utc": now.isoformat(),
            "valid_until_utc": valid_until.isoformat(),
            "status": MandateStatus.ACTIVE.value,
            "key_id": self._key_id,
        }
        sig = sign_bytes(self._priv_key, canonical_json_bytes(signable_dict))

        superseded_old, active_new = current.supersede(
            new_version=new_version,
            key_id=self._key_id,
            signature=sig,
            single_limit_minor=single_limit_minor,
            instant_threshold_minor=instant_threshold_minor,
            lifetime_budget_minor=lifetime_budget_minor,
            allowed_payees=tuple(effective_payees),
            allow_unregistered_payees=effective_allow_unregistered,
            allowed_purposes=tuple(effective_purposes),
            valid_from_utc=now,
            valid_until_utc=valid_until,
        )

        self._mandates[mandate_id] = active_new
        if mandate_id not in self._history:
            self._history[mandate_id] = []
        self._history[mandate_id].append(active_new)
        self._save_mandate_to_db(superseded_old, "")
        self._save_mandate_to_db(active_new, canonical_json_bytes(signable_dict).decode("utf-8"))

        return MandateResponseDTO(
            mandate_id=active_new.mandate_id,
            version=active_new.version,
            principal_id=active_new.principal_id,
            agent_id=active_new.agent_id,
            single_limit_minor=active_new.single_limit_minor,
            instant_threshold_minor=active_new.instant_threshold_minor,
            lifetime_budget_minor=active_new.lifetime_budget_minor,
            currency=active_new.currency,
            allowed_payees=list(active_new.allowed_payees),
            allow_unregistered_payees=active_new.allow_unregistered_payees,
            allowed_purposes=list(active_new.allowed_purposes),
            valid_from_utc=active_new.valid_from_utc,
            valid_until_utc=active_new.valid_until_utc,
            status=active_new.status,
            key_id=active_new.key_id,
            signature=active_new.signature,
        )

    def revoke_mandate(self, mandate_id: str) -> MandateResponseDTO:
        """Revoke an active mandate. Returns the updated revoked mandate model."""
        if self._db_session_factory is not None:
            from app.infrastructure.models import MandateModel

            with self._db_session_factory() as session, session.begin():
                stmt = (
                    select(MandateModel)
                    .where(MandateModel.mandate_id == mandate_id)
                    .order_by(MandateModel.version.desc())
                    .limit(1)
                )
                row = session.scalar(stmt)
                if not row:
                    raise ValueError(f"Mandate {mandate_id} not found")
                row.status = MandateStatus.REVOKED.value
                row.updated_at_utc = datetime.now(UTC)
                revoked = cast(Mandate, row.to_domain())
                with self._lock:
                    self._mandates[mandate_id] = revoked
                return MandateResponseDTO(
                    mandate_id=revoked.mandate_id,
                    version=revoked.version,
                    principal_id=revoked.principal_id,
                    agent_id=revoked.agent_id,
                    single_limit_minor=revoked.single_limit_minor,
                    instant_threshold_minor=revoked.instant_threshold_minor,
                    lifetime_budget_minor=revoked.lifetime_budget_minor,
                    currency=revoked.currency,
                    allowed_payees=list(revoked.allowed_payees),
                    allow_unregistered_payees=revoked.allow_unregistered_payees,
                    allowed_purposes=list(revoked.allowed_purposes),
                    valid_from_utc=revoked.valid_from_utc,
                    valid_until_utc=revoked.valid_until_utc,
                    status=revoked.status,
                    key_id=revoked.key_id,
                    signature=revoked.signature,
                )

        if not self._is_test:
            raise RuntimeError(
                "Database session factory is mandatory for MandateService outside test environment"
            )

        with self._lock:
            current = self._mandates.get(mandate_id)
            if not current:
                raise ValueError(f"Mandate {mandate_id} not found")
            revoked = current.revoke()
            self._mandates[mandate_id] = revoked
            if mandate_id not in self._history:
                self._history[mandate_id] = []
            self._history[mandate_id].append(revoked)
            self._save_mandate_to_db(revoked, "")

            return MandateResponseDTO(
                mandate_id=revoked.mandate_id,
                version=revoked.version,
                principal_id=revoked.principal_id,
                agent_id=revoked.agent_id,
                single_limit_minor=revoked.single_limit_minor,
                instant_threshold_minor=revoked.instant_threshold_minor,
                lifetime_budget_minor=revoked.lifetime_budget_minor,
                currency=revoked.currency,
                allowed_payees=list(revoked.allowed_payees),
                allow_unregistered_payees=revoked.allow_unregistered_payees,
                allowed_purposes=list(revoked.allowed_purposes),
                valid_from_utc=revoked.valid_from_utc,
                valid_until_utc=revoked.valid_until_utc,
                status=revoked.status,
                key_id=revoked.key_id,
                signature=revoked.signature,
            )

    def get_mandate_history(self, mandate_id: str) -> list[Mandate]:
        """Retrieve complete immutable version history of a mandate."""
        if self._db_session_factory is not None:
            from app.infrastructure.models import MandateModel

            with self._db_session_factory() as session:
                stmt = (
                    select(MandateModel)
                    .where(MandateModel.mandate_id == mandate_id)
                    .order_by(MandateModel.version.asc())
                )
                rows = list(session.scalars(stmt))
                return [row.to_domain() for row in rows]

        if not self._is_test:
            raise RuntimeError(
                "Database session factory is mandatory for MandateService outside test environment"
            )

        with self._lock:
            return list(self._history.get(mandate_id, []))

    def verify_mandate_integrity(self, mandate: Mandate) -> bool:
        """Verify the Ed25519 signature seal of a mandate and ensure key_id binding."""
        signable_dict = mandate.to_signable_dict()
        message = canonical_json_bytes(signable_dict)
        return verify_mandate_seal(self._pub_key, message, mandate.signature, mandate.key_id)


class AuthorizationService:
    """Orchestrates authorization requests against domain policies and ledger."""

    def __init__(
        self,
        clock: ClockPort,
        ledger: LedgerPort,
        mandate_service: MandateService | None = None,
        payment_rail: PaymentRail | None = None,
        db_session_factory: Any | None = None,
    ) -> None:
        self._clock = clock
        self._ledger = ledger
        self._mandate_service = mandate_service or MandateService(clock=clock)
        self._payment_rail = payment_rail or FakePaymentRail()
        self._db_session_factory = db_session_factory
        self._lock = RLock()
        self._lifetime_spent: dict[str, int] = {}
        self._rolling_spent: dict[str, int] = {}
        self._idempotency_records: dict[str, tuple[str, DecisionOutcome]] = {}
        self._pending_step_ups: dict[str, dict[str, Any]] = {}
        self._responses_by_id: dict[str, AuthorizationResponseDTO] = {}
        self._request_states: dict[str, RequestState] = {}
        self._held_reservations: dict[str, dict[str, Any]] = {}

    def _seed_default_step_up(self) -> None:
        """Seed a pending step-up request for the human supervisor demo queue.

        Demo-only: requires explicit DEMO_SEED=true; prohibited from running in __init__.
        """
        demo_seed = os.getenv("DEMO_SEED", "").lower() in ("true", "1")
        if not demo_seed:
            return
        now_utc = self._clock.now_utc()
        intent = TransactionIntent(
            agent_id="agent-auto-1",
            recipient_id="vendor-paypal-sandbox-1",
            money=Money(amount_minor=120000, currency="USD"),
            purpose="Equipment invoice review",
            idempotency_key="stepup_seed_1001",
            occurred_at_utc=now_utc,
        )
        digest = compute_intent_digest(
            agent_id=intent.agent_id,
            recipient_id=intent.recipient_id,
            amount_minor=intent.money.amount_minor,
            currency=intent.money.currency,
            purpose=intent.purpose,
            idempotency_key=intent.idempotency_key,
        )
        mandate = self._mandate_service.get_active_mandate_for_agent("agent-auto-1")
        self._pending_step_ups["req_stepup_1001"] = {
            "intent": intent,
            "intent_digest": digest,
            "created_at_utc": now_utc,
            "mandate": mandate,
        }
        if self._db_session_factory is not None:
            try:
                import json

                from app.infrastructure.models import ApprovalStatus, StepUpApprovalModel

                intent_dict = {
                    "agent_id": intent.agent_id,
                    "recipient_id": intent.recipient_id,
                    "amount_minor": intent.money.amount_minor,
                    "currency": intent.money.currency,
                    "purpose": intent.purpose,
                    "idempotency_key": intent.idempotency_key,
                    "occurred_at_utc": intent.occurred_at_utc.isoformat(),
                    "invoice_reference": intent.invoice_reference,
                }
                with self._db_session_factory() as session, session.begin():
                    existing = session.scalar(
                        select(StepUpApprovalModel).where(
                            StepUpApprovalModel.request_id == "req_stepup_1001"
                        )
                    )
                    if not existing:
                        step_row = StepUpApprovalModel(
                            request_id="req_stepup_1001",
                            idempotency_key=intent.idempotency_key,
                            expected_digest=digest,
                            intent_payload=json.dumps(intent_dict),
                            status=ApprovalStatus.PENDING.value,
                            expires_at_utc=now_utc + timedelta(hours=24),
                            created_at_utc=now_utc,
                            updated_at_utc=now_utc,
                        )
                        session.add(step_row)
            except Exception as exc:
                logger.warning("Failed to save step-up approval to DB: %s", exc)

    def get_pending_step_ups(self) -> list[PendingStepUpDTO]:
        with self._lock:
            if self._db_session_factory is not None:
                try:
                    import json

                    from app.infrastructure.models import ApprovalStatus, StepUpApprovalModel

                    with self._db_session_factory() as session:
                        stmt = (
                            select(StepUpApprovalModel)
                            .where(StepUpApprovalModel.status == ApprovalStatus.PENDING.value)
                            .order_by(StepUpApprovalModel.created_at_utc.desc())
                        )
                        rows = session.scalars(stmt).all()
                        db_items: list[PendingStepUpDTO] = []
                        for r in rows:
                            payload_dict = json.loads(r.intent_payload)
                            amount = (
                                payload_dict.get("money", {}).get("amount_minor")
                                if "money" in payload_dict
                                else payload_dict.get("amount_minor", 0)
                            )
                            curr = (
                                payload_dict.get("money", {}).get("currency")
                                if "money" in payload_dict
                                else payload_dict.get("currency", "USD")
                            )
                            db_items.append(
                                PendingStepUpDTO(
                                    request_id=r.request_id,
                                    agent_id=payload_dict.get("agent_id", "agent-auto-1"),
                                    recipient_id=payload_dict.get("recipient_id", ""),
                                    amount_minor=amount,
                                    currency=curr,
                                    purpose=payload_dict.get("purpose", ""),
                                    intent_digest=r.expected_digest,
                                    created_at_utc=r.created_at_utc,
                                    status=r.status,
                                )
                            )
                        seen_ids = {item.request_id for item in db_items}
                        for req_id, data in self._pending_step_ups.items():
                            if req_id not in seen_ids:
                                it = data["intent"]
                                db_items.append(
                                    PendingStepUpDTO(
                                        request_id=req_id,
                                        agent_id=it.agent_id,
                                        recipient_id=it.recipient_id,
                                        amount_minor=it.money.amount_minor,
                                        currency=it.money.currency,
                                        purpose=it.purpose,
                                        intent_digest=data["intent_digest"],
                                        created_at_utc=data["created_at_utc"],
                                        status="PENDING",
                                    )
                                )
                        return db_items
                except Exception as exc:
                    logger.warning("Failed to load pending step-ups from DB: %s", exc)

            items = []
            for req_id, data in self._pending_step_ups.items():
                intent = data["intent"]
                items.append(
                    PendingStepUpDTO(
                        request_id=req_id,
                        agent_id=intent.agent_id,
                        recipient_id=intent.recipient_id,
                        amount_minor=intent.money.amount_minor,
                        currency=intent.money.currency,
                        purpose=intent.purpose,
                        intent_digest=data["intent_digest"],
                        created_at_utc=data["created_at_utc"],
                        status="PENDING",
                    )
                )
            return items

    def get_pending_step_up(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            in_mem = self._pending_step_ups.get(request_id)
            if in_mem:
                return in_mem
            if self._db_session_factory is not None:
                try:
                    import json

                    from app.infrastructure.models import ApprovalStatus, StepUpApprovalModel

                    with self._db_session_factory() as session:
                        stmt = select(StepUpApprovalModel).where(
                            StepUpApprovalModel.request_id == request_id,
                            StepUpApprovalModel.status == ApprovalStatus.PENDING.value,
                        )
                        row = session.scalar(stmt)
                        if row:
                            payload_dict = json.loads(row.intent_payload)
                            it = TransactionIntent(
                                agent_id=payload_dict["agent_id"],
                                recipient_id=payload_dict["recipient_id"],
                                money=Money(
                                    amount_minor=payload_dict["amount_minor"],
                                    currency=payload_dict["currency"],
                                ),
                                purpose=payload_dict["purpose"],
                                idempotency_key=payload_dict["idempotency_key"],
                                occurred_at_utc=datetime.fromisoformat(
                                    payload_dict["occurred_at_utc"]
                                ),
                                invoice_reference=payload_dict.get("invoice_reference"),
                            )
                            mandate = self._mandate_service.get_active_mandate_for_agent(
                                it.agent_id
                            )
                            item = {
                                "intent": it,
                                "intent_digest": row.expected_digest,
                                "created_at_utc": row.created_at_utc,
                                "mandate": mandate,
                            }
                            self._pending_step_ups[request_id] = item
                            return item
                except Exception as exc:
                    logger.warning("Failed to load pending step-up from DB: %s", exc)
            return None

    def get_lifetime_spent(self, agent_id: str | None = None) -> int:
        if self._db_session_factory is not None:
            with self._db_session_factory() as session:
                repo = BudgetRepository(session)
                if agent_id:
                    return repo.get_spent_budget(agent_id)
                stmt = select(AgentBudgetModel)
                budgets = session.scalars(stmt).all()
                return sum(b.spent_minor + b.reserved_minor for b in budgets)
        with self._lock:
            if agent_id:
                return self._lifetime_spent.get(agent_id, 0)
            return sum(self._lifetime_spent.values())

    def authorize(self, command: AuthorizeTransactionCommand) -> AuthorizationResponseDTO:
        now_utc = self._clock.now_utc()
        money = Money(amount_minor=command.amount_minor, currency=command.currency)
        intent = TransactionIntent(
            agent_id=command.agent_id,
            recipient_id=command.recipient_id,
            money=money,
            purpose=command.purpose,
            idempotency_key=command.idempotency_key,
            occurred_at_utc=now_utc,
            invoice_reference=command.invoice_reference,
        )

        intent_digest = compute_intent_digest(
            agent_id=intent.agent_id,
            recipient_id=intent.recipient_id,
            amount_minor=intent.money.amount_minor,
            currency=intent.money.currency,
            purpose=intent.purpose,
            idempotency_key=intent.idempotency_key,
        )
        request_id = f"req_{hashlib.sha256(intent.idempotency_key.encode()).hexdigest()[:16]}"

        with self._lock:
            mandate = self._mandate_service.get_active_mandate_for_agent(command.agent_id)
            if mandate is None:
                # No active mandate for agent -> DENY
                reasons = ["No active mandate found for agent"]
                codes = [PolicyReasonCode.MANDATE_INACTIVE]
                final_decision = DecisionOutcome.DENY
                base_decision = DecisionOutcome.DENY
            else:
                # Check mandate signature integrity
                if not self._mandate_service.verify_mandate_integrity(mandate):
                    reasons = ["Mandate signature integrity verification failed"]
                    codes = [PolicyReasonCode.MANDATE_INACTIVE]
                    final_decision = DecisionOutcome.DENY
                    base_decision = DecisionOutcome.DENY
                else:
                    if self._db_session_factory is not None:
                        with self._db_session_factory() as session, session.begin():
                            repo = BudgetRepository(session)
                            repo.get_or_create_budget(
                                agent_id=mandate.agent_id,
                                mandate_id=mandate.mandate_id,
                                currency=mandate.currency,
                                allocated_minor=mandate.lifetime_budget_minor,
                            )
                            try:
                                repo.check_idempotency(intent.idempotency_key, intent_digest)
                            except IdempotencyMismatchError:
                                return AuthorizationResponseDTO(
                                    request_id=request_id,
                                    decision=DecisionOutcome.DENY,
                                    reasons=[
                                        "Idempotency violation: key reused with mutated parameters"
                                    ],
                                    reason_codes=[PolicyReasonCode.IDEMPOTENCY_MISMATCH],
                                    escalated=False,
                                    event_id="",
                                    intent_digest=intent_digest,
                                    evaluated_at_utc=now_utc,
                                    payout_id=None,
                                    request_state=RequestState.DENIED,
                                )
                            except IdempotencyReplayError as e:
                                if (
                                    e.record.decision in ("PROCESSING", "PENDING")
                                    or e.record.decision not in DecisionOutcome._value2member_map_
                                ):
                                    raise HTTPException(
                                        status_code=status.HTTP_409_CONFLICT,
                                        detail="Transaction currently executing",
                                    ) from e
                                cached_dec = DecisionOutcome(e.record.decision)
                                return AuthorizationResponseDTO(
                                    request_id=request_id,
                                    decision=cached_dec,
                                    reasons=[
                                        "Idempotency match: returning previously stored decision"
                                    ],
                                    reason_codes=[PolicyReasonCode.IDEMPOTENCY_REPLAY],
                                    escalated=False,
                                    event_id="",
                                    intent_digest=intent_digest,
                                    evaluated_at_utc=now_utc,
                                    payout_id=None,
                                    request_state=(
                                        RequestState.SETTLED
                                        if cached_dec == DecisionOutcome.ALLOW
                                        else RequestState.PENDING_APPROVAL
                                    ),
                                )

                    agent_lifetime = self.get_lifetime_spent(command.agent_id)
                    agent_rolling = self._rolling_spent.get(command.agent_id, 0)
                    state = PolicyState(
                        lifetime_spent_minor=agent_lifetime,
                        rolling_24h_spent_minor=agent_rolling,
                        idempotency_records=dict(self._idempotency_records),
                    )
                    eval_res: PolicyDecision = evaluate_policy(
                        intent=intent,
                        mandate=mandate,
                        state=state,
                        now_utc=now_utc,
                        advisory_signal=command.anomaly_signal,
                        intent_digest=intent_digest,
                    )
                    final_decision = eval_res.outcome
                    reasons = list(eval_res.reasons)
                    codes = list(eval_res.reason_codes)
                    base_decision = eval_res.escalated_from or eval_res.outcome

            escalated = final_decision != base_decision

            # Record in idempotency cache
            self._idempotency_records[intent.idempotency_key] = (
                intent_digest,
                final_decision,
            )

            payout_id: str | None = None
            is_replay = PolicyReasonCode.IDEMPOTENCY_REPLAY in codes

            current_req_state = RequestState.RECEIVED
            current_req_state = transition_request_state(current_req_state, RequestState.EVALUATING)

            if final_decision == DecisionOutcome.DENY:
                current_req_state = transition_request_state(current_req_state, RequestState.DENIED)
            elif final_decision == DecisionOutcome.STEP_UP:
                current_req_state = transition_request_state(
                    current_req_state, RequestState.PENDING_APPROVAL
                )
                if not is_replay:
                    self._pending_step_ups[request_id] = {
                        "intent": intent,
                        "intent_digest": intent_digest,
                        "created_at_utc": now_utc,
                        "mandate": mandate,
                    }
                    if self._db_session_factory is not None:
                        try:
                            import json

                            from app.infrastructure.models import (
                                ApprovalStatus,
                                StepUpApprovalModel,
                            )

                            intent_dict = {
                                "agent_id": intent.agent_id,
                                "recipient_id": intent.recipient_id,
                                "amount_minor": intent.money.amount_minor,
                                "currency": intent.money.currency,
                                "purpose": intent.purpose,
                                "idempotency_key": intent.idempotency_key,
                                "occurred_at_utc": intent.occurred_at_utc.isoformat(),
                                "invoice_reference": intent.invoice_reference,
                            }
                            with self._db_session_factory() as session, session.begin():
                                step_row = StepUpApprovalModel(
                                    request_id=request_id,
                                    idempotency_key=intent.idempotency_key,
                                    expected_digest=intent_digest,
                                    intent_payload=json.dumps(intent_dict),
                                    status=ApprovalStatus.PENDING.value,
                                    expires_at_utc=now_utc + timedelta(hours=24),
                                    created_at_utc=now_utc,
                                    updated_at_utc=now_utc,
                                )
                                session.merge(step_row)
                        except Exception as exc:
                            logger.warning("Failed to persist updated step-up to DB: %s", exc)
            elif final_decision == DecisionOutcome.ALLOW:
                # Configuration errors fail before any reservation with a clear 503
                # Missing method, non-callable, wrong type, or invalid credentials all fail closed
                validate_fn = getattr(self._payment_rail, "validate_configuration", None)
                if not callable(validate_fn):
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Payment rail unavailable: configuration validator is missing",
                    )
                cfg_check = validate_fn()
                if not isinstance(cfg_check, tuple) or len(cfg_check) != 2:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Payment rail unavailable: invalid configuration check result",
                    )
                is_rail_ready, rail_cfg_err = cfg_check
                if not is_rail_ready:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Payment rail unavailable: {rail_cfg_err}",
                    )

                current_req_state = transition_request_state(
                    current_req_state, RequestState.AUTHORIZED
                )
                if not is_replay:
                    db_res_id: str | None = None
                    if self._db_session_factory is not None:
                        with self._db_session_factory() as session, session.begin():
                            repo = BudgetRepository(session)
                            try:
                                res_model = repo.reserve_budget(
                                    agent_id=command.agent_id,
                                    amount_minor=intent.money.amount_minor,
                                    currency=intent.money.currency,
                                    idempotency_key=intent.idempotency_key,
                                    intent_digest=intent_digest,
                                )
                                db_res_id = res_model.reservation_id
                            except InsufficientBudgetError as ibe:
                                current_req_state = transition_request_state(
                                    current_req_state, RequestState.DENIED
                                )
                                return AuthorizationResponseDTO(
                                    request_id=request_id,
                                    decision=DecisionOutcome.DENY,
                                    reasons=[f"Lifetime budget cap exceeded: {ibe}"],
                                    reason_codes=[PolicyReasonCode.LIFETIME_BUDGET_EXCEEDED],
                                    escalated=False,
                                    event_id="",
                                    intent_digest=intent_digest,
                                    evaluated_at_utc=now_utc,
                                    payout_id=None,
                                    request_state=RequestState.DENIED,
                                )
                            except IdempotencyReplayError as replay_err:
                                if replay_err.record.decision in ("PROCESSING", "PENDING") or (
                                    replay_err.record.decision
                                    not in DecisionOutcome._value2member_map_
                                ):
                                    raise HTTPException(
                                        status_code=status.HTTP_409_CONFLICT,
                                        detail="Transaction currently executing",
                                    ) from replay_err
                                cached_dec = DecisionOutcome(replay_err.record.decision)
                                return AuthorizationResponseDTO(
                                    request_id=request_id,
                                    decision=cached_dec,
                                    reasons=[
                                        "Idempotency match: returning previously stored decision"
                                    ],
                                    reason_codes=[PolicyReasonCode.IDEMPOTENCY_REPLAY],
                                    escalated=False,
                                    event_id="",
                                    intent_digest=intent_digest,
                                    evaluated_at_utc=now_utc,
                                    payout_id=None,
                                    request_state=(
                                        RequestState.SETTLED
                                        if cached_dec == DecisionOutcome.ALLOW
                                        else RequestState.PENDING_APPROVAL
                                    ),
                                )
                    else:
                        # In-memory reserve budget
                        agent_lifetime = self._lifetime_spent.get(command.agent_id, 0)
                        agent_rolling = self._rolling_spent.get(command.agent_id, 0)
                        self._lifetime_spent[command.agent_id] = (
                            agent_lifetime + intent.money.amount_minor
                        )
                        self._rolling_spent[command.agent_id] = (
                            agent_rolling + intent.money.amount_minor
                        )

                    # Dispatch payment rail
                    current_req_state = transition_request_state(
                        current_req_state, RequestState.EXECUTING
                    )
                    rail_res = self._payment_rail.pay(intent)
                    payout_id = rail_res.transaction_id
                    active_provider_state = rail_res.status

                    AMBIGUOUS_STATUSES = {
                        "PAYOUT_EXCEPTION",
                        "FALLBACK_EXCEPTION",
                        "TIMEOUT",
                        "UNKNOWN",
                    }
                    err_text = str(rail_res.details.get("error", "")).lower()
                    is_ambiguous = (
                        rail_res.status in AMBIGUOUS_STATUSES
                        or "gateway timeout" in err_text
                        or "service unavailable" in err_text
                        or "timeout" in err_text
                        or rail_res.details.get("status_code", 0) >= 500
                        or rail_res.details.get("http_status", 0) >= 500
                        or rail_res.details.get("status_code", 0) in (408, 429)
                        or rail_res.details.get("http_status", 0) in (408, 429)
                    )

                    if rail_res.success and rail_res.status in ("COMPLETED", "SUCCESS"):
                        current_req_state = transition_request_state(
                            current_req_state, RequestState.SETTLED
                        )
                        if self._db_session_factory is not None and db_res_id:
                            with self._db_session_factory() as session, session.begin():
                                repo = BudgetRepository(session)
                                repo.confirm_reservation(db_res_id)
                                repo.record_decision(
                                    idempotency_key=intent.idempotency_key,
                                    agent_id=command.agent_id,
                                    intent_digest=intent_digest,
                                    decision=final_decision.value,
                                    response_payload="",
                                )
                    elif rail_res.success and rail_res.status in (
                        "ORDER_CREATED",
                        "BUYER_APPROVAL_REQUIRED",
                        "APPROVED",
                        "CAPTURE_REQUESTED",
                    ):
                        # Never label an order SETTLED before a real sandbox capture
                        current_req_state = transition_request_state(
                            current_req_state,
                            RequestState.RECONCILE,
                            reason=f"Order awaiting sandbox capture: {rail_res.status}",
                        )
                        self._held_reservations[request_id] = {
                            "request_id": request_id,
                            "agent_id": command.agent_id,
                            "amount_minor": intent.money.amount_minor,
                            "reservation_id": db_res_id,
                            "intent": intent,
                            "payout_id": payout_id,
                            "intent_digest": intent_digest,
                            "provider_status": rail_res.status,
                            "created_at_utc": now_utc,
                            "state": RequestState.RECONCILE.value,
                        }
                        if self._db_session_factory is not None and db_res_id:
                            with self._db_session_factory() as session, session.begin():
                                repo = BudgetRepository(session)
                                repo.release_reservation(db_res_id, confirmed_failure=False)
                                import json

                                payload_meta = {
                                    "request_id": request_id,
                                    "payout_id": payout_id,
                                    "provider_status": rail_res.status,
                                    "amount_minor": intent.money.amount_minor,
                                    "currency": intent.money.currency,
                                    "agent_id": command.agent_id,
                                    "recipient_id": intent.recipient_id,
                                    "purpose": intent.purpose,
                                    "idempotency_key": intent.idempotency_key,
                                }
                                repo.record_decision(
                                    idempotency_key=intent.idempotency_key,
                                    agent_id=command.agent_id,
                                    intent_digest=intent_digest,
                                    decision=final_decision.value,
                                    response_payload=json.dumps(payload_meta),
                                )
                    elif (
                        is_ambiguous
                        or rail_res.status == "RECONCILE"
                        or not (
                            rail_res.status == "FAILED"
                            and rail_res.details.get("business_rejection") is True
                        )
                    ):
                        current_req_state = transition_request_state(
                            current_req_state,
                            RequestState.RECONCILE,
                            reason=f"Ambiguous or unconfirmed rail outcome: {rail_res.status}",
                        )
                        # Associated budget reservation MUST remain held:
                        self._held_reservations[request_id] = {
                            "request_id": request_id,
                            "agent_id": command.agent_id,
                            "amount_minor": intent.money.amount_minor,
                            "reservation_id": db_res_id,
                            "intent": intent,
                            "payout_id": payout_id,
                            "intent_digest": intent_digest,
                            "provider_status": rail_res.status,
                            "created_at_utc": now_utc,
                            "state": RequestState.RECONCILE.value,
                        }
                        if self._db_session_factory is not None and db_res_id:
                            with self._db_session_factory() as session, session.begin():
                                repo = BudgetRepository(session)
                                repo.release_reservation(db_res_id, confirmed_failure=False)
                                import json

                                payload_meta = {
                                    "request_id": request_id,
                                    "payout_id": payout_id,
                                    "provider_status": rail_res.status,
                                    "amount_minor": intent.money.amount_minor,
                                    "currency": intent.money.currency,
                                    "agent_id": command.agent_id,
                                    "recipient_id": intent.recipient_id,
                                    "purpose": intent.purpose,
                                    "idempotency_key": intent.idempotency_key,
                                }
                                repo.record_decision(
                                    idempotency_key=intent.idempotency_key,
                                    agent_id=command.agent_id,
                                    intent_digest=intent_digest,
                                    decision=final_decision.value,
                                    response_payload=json.dumps(payload_meta),
                                )
                    else:
                        # Only definite provider rejection (4xx business error)
                        # releases a reservation
                        current_req_state = transition_request_state(
                            current_req_state, RequestState.FAILED
                        )
                        if self._db_session_factory is not None and db_res_id:
                            with self._db_session_factory() as session, session.begin():
                                repo = BudgetRepository(session)
                                repo.release_reservation(db_res_id, confirmed_failure=True)
                        else:
                            # Confirmed failure releases the budget reservation:
                            self._lifetime_spent[command.agent_id] = max(
                                0,
                                self._lifetime_spent[command.agent_id] - intent.money.amount_minor,
                            )
                            self._rolling_spent[command.agent_id] = max(
                                0,
                                self._rolling_spent[command.agent_id] - intent.money.amount_minor,
                            )
                else:
                    prev_resp = self._responses_by_id.get(request_id)
                    payout_id = prev_resp.payout_id if prev_resp else None
                    current_req_state = self._request_states.get(request_id, RequestState.SETTLED)

            self._request_states[request_id] = current_req_state

            domain_result = PolicyEvaluationResult(
                outcome=final_decision,
                reasons=tuple(reasons),
                escalated_from=base_decision if escalated else None,
                evaluated_at_utc=now_utc,
            )

            kwargs: dict[str, Any] = {}
            act_st = locals().get("active_provider_state")
            if act_st:
                kwargs["provider_state"] = act_st
            try:
                event_id = self._ledger.append_event(
                    event_type="AUTHORIZATION_EVALUATED",
                    intent=intent,
                    result=domain_result,
                    recorded_at_utc=now_utc,
                    **kwargs,
                )
            except TypeError:
                event_id = self._ledger.append_event(
                    event_type="AUTHORIZATION_EVALUATED",
                    intent=intent,
                    result=domain_result,
                    recorded_at_utc=now_utc,
                )

            resp = AuthorizationResponseDTO(
                request_id=request_id,
                decision=final_decision,
                reasons=reasons,
                reason_codes=codes,
                escalated=escalated,
                event_id=event_id,
                intent_digest=intent_digest,
                evaluated_at_utc=now_utc,
                payout_id=payout_id,
                request_state=current_req_state,
            )
            self._responses_by_id[request_id] = resp
            if self._db_session_factory is not None:
                try:
                    with self._db_session_factory() as session, session.begin():
                        repo = BudgetRepository(session)
                        repo.record_decision(
                            idempotency_key=intent.idempotency_key,
                            agent_id=command.agent_id,
                            intent_digest=intent_digest,
                            decision=final_decision.value,
                            response_payload=resp.model_dump_json(),
                        )
                except Exception:
                    pass  # nosec: B110
            return resp

    def execute_approval(
        self,
        command: ApprovalCommand,
        caller_role: str = "approver",
    ) -> AuthorizationResponseDTO:
        """Process human supervisor approval bound to canonical intent digest."""
        if caller_role == "agent":
            raise PermissionError("Forbidden: Agent identity cannot approve step-up transactions.")

        now_utc = self._clock.now_utc()
        with self._lock:
            pending = self._pending_step_ups.get(command.request_id)
            if not pending and (
                command.request_id in self._held_reservations
                or self._request_states.get(command.request_id) == RequestState.NEEDS_REVIEW
            ):
                raise ValueError(
                    f"Request '{command.request_id}' is in NEEDS_REVIEW. Transitioning to SETTLED "
                    "requires verified provider settlement proof, "
                    "not a manual click in the approval queue."
                )
            elif not pending:
                raise KeyError(
                    f"Pending step-up request '{command.request_id}' not found or already resolved."
                )

            stored_digest: str = pending["intent_digest"]
            if command.expected_digest != stored_digest:
                raise ValueError(
                    f"Approval digest mismatch: expected '{stored_digest}', "
                    f"received '{command.expected_digest}'. Tampering detected!"
                )

            intent: TransactionIntent = pending["intent"]
            mandate: Mandate = pending["mandate"]

            # Expiry check: approvals expire after 24 hours
            created_at: datetime = pending["created_at_utc"]
            if (now_utc - created_at) > timedelta(hours=24):
                del self._pending_step_ups[command.request_id]
                raise TimeoutError("Approval request has expired (window is 24 hours).")

            del self._pending_step_ups[command.request_id]

            reasons: list[str] = [
                f"Human supervisor decision: {command.decision.value} ({command.reason})"
            ]
            codes: list[PolicyReasonCode] = []
            payout_id: str | None = None
            current_req_state = RequestState.PENDING_APPROVAL

            if command.decision == DecisionOutcome.ALLOW:
                # 1. Re-verify mandate status from mandate service
                current_mandate = self._mandate_service.get_mandate(mandate.mandate_id)
                if current_mandate is None or current_mandate.status != MandateStatus.ACTIVE:
                    final_decision = DecisionOutcome.DENY
                    status_str = current_mandate.status.value if current_mandate else "MISSING"
                    reasons.append(f"Mandate is no longer active (status: {status_str})")
                    codes.append(PolicyReasonCode.MANDATE_INACTIVE)
                elif now_utc > current_mandate.valid_until_utc:
                    final_decision = DecisionOutcome.DENY
                    reasons.append("Mandate expired before human approval execution")
                    codes.append(PolicyReasonCode.MANDATE_EXPIRED)
                elif now_utc < current_mandate.valid_from_utc:
                    final_decision = DecisionOutcome.DENY
                    reasons.append("Mandate is not yet valid")
                    codes.append(PolicyReasonCode.MANDATE_NOT_YET_VALID)
                else:
                    # 2. Re-evaluate policy against current state and current mandate
                    agent_lifetime = self.get_lifetime_spent(intent.agent_id)
                    agent_rolling = self._rolling_spent.get(intent.agent_id, 0)
                    state = PolicyState(
                        lifetime_spent_minor=agent_lifetime,
                        rolling_24h_spent_minor=agent_rolling,
                        idempotency_records=dict(self._idempotency_records),
                    )
                    eval_res = evaluate_policy(
                        intent=intent,
                        mandate=current_mandate,
                        state=state,
                        now_utc=now_utc,
                        advisory_signal=None,
                        intent_digest=stored_digest,
                    )
                    if eval_res.outcome == DecisionOutcome.DENY:
                        final_decision = DecisionOutcome.DENY
                        reasons.extend(eval_res.reasons)
                        codes.extend(eval_res.reason_codes)
                    else:
                        final_decision = DecisionOutcome.ALLOW
                        # Configuration errors fail before any reservation with a clear 503
                        validate_fn = getattr(self._payment_rail, "validate_configuration", None)
                        if not callable(validate_fn):
                            raise HTTPException(
                                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail=(
                                    "Payment rail unavailable: configuration validator is missing"
                                ),
                            )
                        cfg_check = validate_fn()
                        if not isinstance(cfg_check, tuple) or len(cfg_check) != 2:
                            raise HTTPException(
                                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail=(
                                    "Payment rail unavailable: invalid configuration check result"
                                ),
                            )
                        is_rail_ready, rail_cfg_err = cfg_check
                        if not is_rail_ready:
                            raise HTTPException(
                                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail=f"Payment rail unavailable: {rail_cfg_err}",
                            )

                        db_res_id = None
                        if self._db_session_factory is not None:
                            with self._db_session_factory() as session, session.begin():
                                repo = BudgetRepository(session)
                                res_model = repo.reserve_budget(
                                    agent_id=intent.agent_id,
                                    amount_minor=intent.money.amount_minor,
                                    currency=intent.money.currency,
                                    idempotency_key=intent.idempotency_key,
                                    intent_digest=stored_digest,
                                    is_approval=True,
                                )
                                db_res_id = res_model.reservation_id
                        else:
                            self._lifetime_spent[intent.agent_id] = (
                                agent_lifetime + intent.money.amount_minor
                            )
                            self._rolling_spent[intent.agent_id] = (
                                agent_rolling + intent.money.amount_minor
                            )
                        current_req_state = transition_request_state(
                            current_req_state, RequestState.APPROVED
                        )
                        current_req_state = transition_request_state(
                            current_req_state, RequestState.AUTHORIZED
                        )
                        current_req_state = transition_request_state(
                            current_req_state, RequestState.EXECUTING
                        )
                        rail_res = self._payment_rail.pay(intent)
                        payout_id = rail_res.transaction_id
                        active_approval_provider_state = rail_res.status

                        AMBIGUOUS_STATUSES = {
                            "PAYOUT_EXCEPTION",
                            "FALLBACK_EXCEPTION",
                            "TIMEOUT",
                            "UNKNOWN",
                        }
                        err_text = str(rail_res.details.get("error", "")).lower()
                        is_ambiguous = (
                            rail_res.status in AMBIGUOUS_STATUSES
                            or "gateway timeout" in err_text
                            or "service unavailable" in err_text
                            or "timeout" in err_text
                            or rail_res.details.get("status_code", 0) >= 500
                            or rail_res.details.get("http_status", 0) >= 500
                            or rail_res.details.get("status_code", 0) in (408, 429)
                            or rail_res.details.get("http_status", 0) in (408, 429)
                        )

                        if rail_res.success and rail_res.status in ("COMPLETED", "SUCCESS"):
                            current_req_state = transition_request_state(
                                current_req_state, RequestState.SETTLED
                            )
                            if self._db_session_factory is not None and db_res_id:
                                with self._db_session_factory() as session, session.begin():
                                    repo = BudgetRepository(session)
                                    repo.confirm_reservation(db_res_id)
                                    repo.record_decision(
                                        idempotency_key=intent.idempotency_key,
                                        agent_id=intent.agent_id,
                                        intent_digest=stored_digest,
                                        decision=final_decision.value,
                                        response_payload="",
                                    )
                        elif rail_res.success and rail_res.status in (
                            "ORDER_CREATED",
                            "BUYER_APPROVAL_REQUIRED",
                            "APPROVED",
                            "CAPTURE_REQUESTED",
                        ):
                            # Never label an order SETTLED before a real sandbox capture
                            current_req_state = transition_request_state(
                                current_req_state,
                                RequestState.RECONCILE,
                                reason=f"Order awaiting sandbox capture: {rail_res.status}",
                            )
                            self._held_reservations[command.request_id] = {
                                "request_id": command.request_id,
                                "agent_id": intent.agent_id,
                                "amount_minor": intent.money.amount_minor,
                                "reservation_id": db_res_id,
                                "intent": intent,
                                "payout_id": payout_id,
                                "intent_digest": stored_digest,
                                "provider_status": rail_res.status,
                                "created_at_utc": now_utc,
                                "state": RequestState.RECONCILE.value,
                            }
                            if self._db_session_factory is not None and db_res_id:
                                with self._db_session_factory() as session, session.begin():
                                    repo = BudgetRepository(session)
                                    repo.release_reservation(db_res_id, confirmed_failure=False)
                        elif (
                            is_ambiguous
                            or rail_res.status == "RECONCILE"
                            or not (
                                rail_res.status == "FAILED"
                                and rail_res.details.get("business_rejection") is True
                            )
                        ):
                            current_req_state = transition_request_state(
                                current_req_state,
                                RequestState.RECONCILE,
                                reason=f"Ambiguous rail outcome: {rail_res.status}",
                            )
                            self._held_reservations[command.request_id] = {
                                "request_id": command.request_id,
                                "agent_id": intent.agent_id,
                                "amount_minor": intent.money.amount_minor,
                                "reservation_id": db_res_id,
                                "intent": intent,
                                "payout_id": payout_id,
                                "intent_digest": stored_digest,
                                "provider_status": rail_res.status,
                                "created_at_utc": now_utc,
                                "state": RequestState.RECONCILE.value,
                            }
                            if self._db_session_factory is not None and db_res_id:
                                with self._db_session_factory() as session, session.begin():
                                    repo = BudgetRepository(session)
                                    repo.release_reservation(db_res_id, confirmed_failure=False)
                        else:
                            current_req_state = transition_request_state(
                                current_req_state, RequestState.FAILED
                            )
                            if self._db_session_factory is not None and db_res_id:
                                with self._db_session_factory() as session, session.begin():
                                    repo = BudgetRepository(session)
                                    repo.release_reservation(db_res_id, confirmed_failure=True)
                            else:
                                self._lifetime_spent[intent.agent_id] = max(
                                    0,
                                    self._lifetime_spent.get(intent.agent_id, 0)
                                    - intent.money.amount_minor,
                                )
                                self._rolling_spent[intent.agent_id] = max(
                                    0,
                                    self._rolling_spent.get(intent.agent_id, 0)
                                    - intent.money.amount_minor,
                                )
            else:
                final_decision = DecisionOutcome.DENY

            if final_decision == DecisionOutcome.DENY:
                current_req_state = transition_request_state(
                    current_req_state, RequestState.REJECTED
                )

            self._request_states[command.request_id] = current_req_state

            # F1: Update idempotency cache with final approved decision
            self._idempotency_records[intent.idempotency_key] = (
                stored_digest,
                final_decision,
            )

            domain_result = PolicyEvaluationResult(
                outcome=final_decision,
                reasons=tuple(reasons),
                escalated_from=DecisionOutcome.STEP_UP,
                evaluated_at_utc=now_utc,
            )

            kwargs_step: dict[str, Any] = {}
            act_app_st = locals().get("active_approval_provider_state")
            if act_app_st:
                kwargs_step["provider_state"] = act_app_st
            try:
                event_id = self._ledger.append_event(
                    event_type="HUMAN_STEP_UP_RESOLVED",
                    intent=intent,
                    result=domain_result,
                    recorded_at_utc=now_utc,
                    **kwargs_step,
                )
            except TypeError:
                event_id = self._ledger.append_event(
                    event_type="HUMAN_STEP_UP_RESOLVED",
                    intent=intent,
                    result=domain_result,
                    recorded_at_utc=now_utc,
                )

            resp = AuthorizationResponseDTO(
                request_id=command.request_id,
                decision=final_decision,
                reasons=reasons,
                reason_codes=codes,
                escalated=False,
                event_id=event_id,
                intent_digest=stored_digest,
                evaluated_at_utc=now_utc,
                payout_id=payout_id,
                request_state=current_req_state,
            )
            self._responses_by_id[command.request_id] = resp
            if self._db_session_factory is not None:
                try:
                    from app.infrastructure.models import ApprovalStatus, StepUpApprovalModel

                    with self._db_session_factory() as session, session.begin():
                        stmt_step = select(StepUpApprovalModel).where(
                            StepUpApprovalModel.request_id == command.request_id
                        )
                        step_row = session.scalar(stmt_step)
                        if step_row:
                            step_row.status = (
                                ApprovalStatus.APPROVED.value
                                if command.decision == DecisionOutcome.ALLOW
                                else ApprovalStatus.REJECTED.value
                            )
                            step_row.decision = final_decision.value
                            step_row.approver_id = caller_role
                            step_row.updated_at_utc = now_utc
                except Exception as exc:
                    logger.warning("Failed to update step-up approval in DB: %s", exc)
            if self._db_session_factory is not None:
                try:
                    with self._db_session_factory() as session, session.begin():
                        repo = BudgetRepository(session)
                        repo.record_decision(
                            idempotency_key=intent.idempotency_key,
                            agent_id=intent.agent_id,
                            intent_digest=stored_digest,
                            decision=final_decision.value,
                            response_payload=resp.model_dump_json(),
                        )
                except Exception:
                    pass  # nosec: B110
            return resp

    def get_request_state(self, request_id: str) -> RequestState | None:
        """Return the current lifecycle state of a request."""
        with self._lock:
            return self._request_states.get(request_id)

    def reconcile(
        self,
        request_id: str,
        rail_status: str | None = None,
        max_age_seconds: int = 86400,
    ) -> RequestState:
        """Reconcile a transaction currently in RECONCILE state against external rail outcome.

        Classification (Manual 56.13, 56.17):
        - Confirmed success: -> RequestState.SETTLED. Budget moves to spent.
        - Confirmed failure / denial / expiry: -> RequestState.FAILED. Releases held budget.
        - Still unknown / pending: -> remains RequestState.RECONCILE. Budget remains held.
        - Past RECONCILE_MAX_AGE: -> RequestState.NEEDS_REVIEW. Holds budget; never auto-releases.
        - Idempotent: re-calling on already SETTLED or FAILED request returns current state safely.
        """
        with self._lock:
            current_state = self._request_states.get(request_id)
            if current_state == RequestState.SETTLED:
                return RequestState.SETTLED
            if current_state == RequestState.FAILED:
                return RequestState.FAILED
            if current_state not in (RequestState.RECONCILE, RequestState.NEEDS_REVIEW):
                msg = (
                    f"Request '{request_id}' is not in RECONCILE or NEEDS_REVIEW state "
                    f"(current: {current_state})"
                )
                raise ValueError(msg)

            resp = self._responses_by_id.get(request_id)
            held = self._held_reservations.get(request_id)
            payout_id = (resp.payout_id if resp else None) or (
                held.get("payout_id") if held else None
            )

            if rail_status is None and payout_id:
                try:
                    lookup_res = self._payment_rail.lookup(payout_id)
                    rail_status = lookup_res.status
                except Exception as exc:
                    logger.warning("Payment rail lookup exception for '%s': %s", payout_id, exc)
                    rail_status = "LOOKUP_FAILED"

            status_norm = (rail_status or "UNKNOWN").upper()
            CONFIRMED_SUCCESS = {"SUCCESS", "COMPLETED", "CONFIRMED", "SETTLED"}
            CONFIRMED_FAILURE = {
                "FAILED",
                "DENIED",
                "REJECTED",
                "PAYOUT_REJECTED",
                "FALLBACK_FAILED",
                "CANCELED",
                "RETURNED",
                "EXPIRED",
                "VOIDED",
            }
            AMBIGUOUS_ERRORS = {
                "LOOKUP_FAILED",
                "TIMEOUT",
                "NETWORK_ERROR",
                "CONNECTION_ERROR",
                "ERROR",
            }

            now_utc = self._clock.now_utc()
            created_at = held.get("created_at_utc", now_utc) if held else now_utc
            age_seconds = (now_utc - created_at).total_seconds() if created_at else 0
            is_ambiguous_error = status_norm in AMBIGUOUS_ERRORS

            if self._db_session_factory is not None and held and held.get("reservation_id"):
                with self._db_session_factory() as session, session.begin():
                    repo = BudgetRepository(session)
                    if status_norm in CONFIRMED_SUCCESS:
                        repo.confirm_reservation(held["reservation_id"])
                        new_state = transition_request_state(current_state, RequestState.SETTLED)
                        self._held_reservations.pop(request_id, None)
                    elif status_norm in CONFIRMED_FAILURE and not is_ambiguous_error:
                        repo.release_reservation(held["reservation_id"], confirmed_failure=True)
                        new_state = transition_request_state(current_state, RequestState.FAILED)
                        self._held_reservations.pop(request_id, None)
                    elif is_ambiguous_error or age_seconds >= max_age_seconds:
                        repo.release_reservation(held["reservation_id"], confirmed_failure=False)
                        new_state = (
                            RequestState.NEEDS_REVIEW
                            if current_state == RequestState.NEEDS_REVIEW
                            else transition_request_state(current_state, RequestState.NEEDS_REVIEW)
                        )
                        held["state"] = RequestState.NEEDS_REVIEW.value
                        held["provider_status"] = status_norm
                    else:
                        repo.release_reservation(held["reservation_id"], confirmed_failure=False)
                        new_state = RequestState.RECONCILE
                        held["provider_status"] = status_norm

                    self._request_states[request_id] = new_state
                    if resp:
                        resp.request_state = new_state

                    intent = held.get("intent")
                    if intent and new_state in (RequestState.SETTLED, RequestState.FAILED):
                        evt_name = (
                            "RECONCILIATION_CONFIRMED"
                            if new_state == RequestState.SETTLED
                            else "RECONCILIATION_RELEASED"
                        )
                        dec_out = (
                            DecisionOutcome.ALLOW
                            if new_state == RequestState.SETTLED
                            else DecisionOutcome.DENY
                        )
                        dom_res = PolicyEvaluationResult(
                            outcome=dec_out,
                            reasons=(f"Reconciliation outcome: {status_norm}",),
                            evaluated_at_utc=now_utc,
                        )
                        try:
                            self._ledger.append_event(
                                event_type=evt_name,
                                intent=intent,
                                result=dom_res,
                                recorded_at_utc=now_utc,
                                provider_state=status_norm,
                            )
                        except TypeError:
                            self._ledger.append_event(
                                event_type=evt_name,
                                intent=intent,
                                result=dom_res,
                                recorded_at_utc=now_utc,
                            )

                    return new_state

            # In-memory execution
            if status_norm in CONFIRMED_SUCCESS:
                new_state = transition_request_state(current_state, RequestState.SETTLED)
                self._request_states[request_id] = new_state
                self._held_reservations.pop(request_id, None)
                if resp:
                    resp.request_state = new_state
                intent = held.get("intent") if held else None
                if intent:
                    dom_res = PolicyEvaluationResult(
                        outcome=DecisionOutcome.ALLOW,
                        reasons=(f"Reconciliation outcome: {status_norm}",),
                        evaluated_at_utc=now_utc,
                    )
                    try:
                        self._ledger.append_event(
                            event_type="RECONCILIATION_CONFIRMED",
                            intent=intent,
                            result=dom_res,
                            recorded_at_utc=now_utc,
                            provider_state=status_norm,
                        )
                    except TypeError:
                        self._ledger.append_event(
                            event_type="RECONCILIATION_CONFIRMED",
                            intent=intent,
                            result=dom_res,
                            recorded_at_utc=now_utc,
                        )
                return new_state
            elif status_norm in CONFIRMED_FAILURE and not is_ambiguous_error:
                new_state = transition_request_state(current_state, RequestState.FAILED)
                self._request_states[request_id] = new_state
                if held:
                    agent_id = held["agent_id"]
                    amount = held["amount_minor"]
                    self._lifetime_spent[agent_id] = max(
                        0, self._lifetime_spent.get(agent_id, 0) - amount
                    )
                    self._rolling_spent[agent_id] = max(
                        0, self._rolling_spent.get(agent_id, 0) - amount
                    )
                    self._held_reservations.pop(request_id, None)
                if resp:
                    resp.request_state = new_state
                intent = held.get("intent") if held else None
                if intent:
                    dom_res = PolicyEvaluationResult(
                        outcome=DecisionOutcome.DENY,
                        reasons=(f"Reconciliation outcome: {status_norm}",),
                        evaluated_at_utc=now_utc,
                    )
                    try:
                        self._ledger.append_event(
                            event_type="RECONCILIATION_RELEASED",
                            intent=intent,
                            result=dom_res,
                            recorded_at_utc=now_utc,
                            provider_state=status_norm,
                        )
                    except TypeError:
                        self._ledger.append_event(
                            event_type="RECONCILIATION_RELEASED",
                            intent=intent,
                            result=dom_res,
                            recorded_at_utc=now_utc,
                        )
                return new_state
            elif is_ambiguous_error or age_seconds >= max_age_seconds:
                new_state = (
                    RequestState.NEEDS_REVIEW
                    if current_state == RequestState.NEEDS_REVIEW
                    else transition_request_state(current_state, RequestState.NEEDS_REVIEW)
                )
                self._request_states[request_id] = new_state
                if held:
                    held["state"] = RequestState.NEEDS_REVIEW.value
                    held["provider_status"] = status_norm
                if resp:
                    resp.request_state = new_state
                return RequestState.NEEDS_REVIEW
            else:
                # Still unknown / within max_age: remains RECONCILE, reservation remains held
                if held:
                    held["provider_status"] = status_norm
                return RequestState.RECONCILE

    def get_payment_request(self, request_id: str) -> AuthorizationResponseDTO | None:
        with self._lock:
            resp = self._responses_by_id.get(request_id)
            if resp:
                return resp
            if self._db_session_factory is not None:
                try:
                    import json

                    from sqlalchemy import select

                    from app.infrastructure.models import IdempotencyModel

                    with self._db_session_factory() as session:
                        stmt = (
                            select(IdempotencyModel)
                            .where(IdempotencyModel.response_payload.contains(request_id))
                            .limit(1)
                        )
                        rec = session.scalar(stmt)
                        if rec and rec.response_payload:
                            data = json.loads(rec.response_payload)
                            loaded = AuthorizationResponseDTO(**data)
                            self._responses_by_id[request_id] = loaded
                            return loaded
                except Exception:
                    pass  # nosec: B110
            return None

    def get_decision(self, decision_id: str) -> AuthorizationResponseDTO | None:
        with self._lock:
            for resp in self._responses_by_id.values():
                if resp.event_id == decision_id or resp.request_id == decision_id:
                    return resp
            if self._db_session_factory is not None:
                try:
                    import json

                    from sqlalchemy import select

                    from app.infrastructure.models import IdempotencyModel

                    with self._db_session_factory() as session:
                        stmt = (
                            select(IdempotencyModel)
                            .where(IdempotencyModel.response_payload.contains(decision_id))
                            .limit(1)
                        )
                        rec = session.scalar(stmt)
                        if rec and rec.response_payload:
                            data = json.loads(rec.response_payload)
                            loaded = AuthorizationResponseDTO(**data)
                            self._responses_by_id[loaded.request_id] = loaded
                            return loaded
                except Exception:
                    pass  # nosec: B110
            return None

    def capture_order(self, order_id: str, request_id: str | None = None) -> PaymentResult:
        """Capture an approved PayPal order and update ledger/budget reservations."""
        with self._lock:
            result = self._payment_rail.capture_order(order_id, request_id)
            now_utc = self._clock.now_utc()

            target_req_id = request_id
            if not target_req_id:
                for req_k, held_info in list(self._held_reservations.items()):
                    if held_info.get("payout_id") == order_id:
                        target_req_id = req_k
                        break

            if target_req_id and target_req_id in self._held_reservations:
                held = self._held_reservations[target_req_id]
                res_id = held.get("reservation_id")
                intent = held.get("intent")
                if result.success and result.status == "COMPLETED":
                    self._request_states[target_req_id] = RequestState.SETTLED
                    if self._db_session_factory is not None and res_id:
                        with self._db_session_factory() as session, session.begin():
                            repo = BudgetRepository(session)
                            repo.confirm_reservation(res_id)
                    self._held_reservations.pop(target_req_id, None)

                    if intent:
                        eval_result = PolicyEvaluationResult(
                            outcome=DecisionOutcome.ALLOW,
                            reasons=("ORDER_CAPTURED_COMPLETED",),
                            evaluated_at_utc=now_utc,
                        )
                        self._ledger.append_event(
                            event_type="ORDER_CAPTURED",
                            intent=intent,
                            result=eval_result,
                            recorded_at_utc=now_utc,
                            provider_state="COMPLETED",
                        )
                elif result.status == "FAILED":
                    self._request_states[target_req_id] = RequestState.FAILED
                    if self._db_session_factory is not None and res_id:
                        with self._db_session_factory() as session, session.begin():
                            repo = BudgetRepository(session)
                            repo.release_reservation(res_id, confirmed_failure=True)
                    self._held_reservations.pop(target_req_id, None)

            return result

    def get_held_reservations(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._db_session_factory is not None:
                import json

                from app.infrastructure.models import (
                    BudgetReservationModel,
                    IdempotencyModel,
                    ReservationStatus,
                )

                with self._db_session_factory() as session:
                    stmt = (
                        select(BudgetReservationModel)
                        .where(
                            BudgetReservationModel.status.in_(
                                [
                                    ReservationStatus.PENDING.value,
                                    ReservationStatus.RECONCILE.value,
                                ]
                            )
                        )
                        .order_by(BudgetReservationModel.created_at_utc.asc())
                    )
                    reservations = list(session.scalars(stmt).all())
                    items: list[dict[str, Any]] = []
                    for res in reservations:
                        idem = session.scalar(
                            select(IdempotencyModel).where(
                                IdempotencyModel.idempotency_key == res.idempotency_key
                            )
                        )
                        meta: dict[str, Any] = {}
                        if idem and idem.response_payload:
                            try:
                                meta = json.loads(idem.response_payload)
                            except Exception:
                                meta = {}

                        req_id = meta.get("request_id") or f"req_{res.idempotency_key}"
                        payout_id = meta.get("payout_id")
                        prov_status = meta.get("provider_status", res.status)

                        curr_state = self._request_states.get(
                            req_id,
                            RequestState(meta.get("state", RequestState.RECONCILE.value)),
                        )

                        held_data = {
                            "request_id": req_id,
                            "agent_id": res.agent_id,
                            "amount_minor": res.amount_minor,
                            "currency": res.currency,
                            "reservation_id": res.reservation_id,
                            "payout_id": payout_id,
                            "state": curr_state.value,
                            "provider_status": prov_status,
                            "created_at_utc": res.created_at_utc,
                            "intent_digest": idem.intent_digest if idem else "",
                        }
                        items.append(held_data)
                        self._held_reservations[req_id] = held_data
                        self._request_states[req_id] = curr_state
                    return items

            items = []
            for req_id, data in self._held_reservations.items():
                intent = data.get("intent")
                curr = intent.money.currency if intent and hasattr(intent, "money") else "USD"
                items.append(
                    {
                        "request_id": req_id,
                        "agent_id": data.get("agent_id", "agent-auto-1"),
                        "amount_minor": data.get("amount_minor", 0),
                        "currency": curr,
                        "payout_id": data.get("payout_id"),
                        "state": self._request_states.get(
                            req_id,
                            RequestState(data.get("state", RequestState.RECONCILE.value)),
                        ).value,
                        "provider_status": data.get("provider_status", "RECONCILE"),
                        "created_at_utc": data.get("created_at_utc"),
                    }
                )
            return items

    def get_needs_review_items(self) -> list[dict[str, Any]]:
        """Return transactions in NEEDS_REVIEW state awaiting provider settlement proof."""
        with self._lock:
            items: list[dict[str, Any]] = []
            held_list = self.get_held_reservations()
            for held in held_list:
                req_id = str(held.get("request_id") or "")
                state = self._request_states.get(
                    req_id, RequestState(held.get("state", "RECONCILE"))
                )
                if (
                    state == RequestState.NEEDS_REVIEW
                    or held.get("state") == RequestState.NEEDS_REVIEW.value
                ):
                    items.append(held)
            return items

    def resolve_needs_review(
        self,
        request_id: str,
        action: str,
        capture_id: str | None = None,
        reason: str = "",
        actor: str = "supervisor",
    ) -> RequestState:
        """Resolve a NEEDS_REVIEW transaction.

        Invariants:
        - SETTLED requires verified provider proof (COMPLETED); NEVER a manual click.
        - action == 'RETRY_LOOKUP': queries rail with stored payout_id.
        - action == 'PROVIDE_PROOF': queries rail with capture_id.
        - action == 'MARK_FAILED': marks failed with reason, releases funds, logs event.
        - action in ('APPROVE', 'ALLOW', 'SETTLE'): rejected without provider proof.
        """
        import contextlib

        with self._lock:
            held = self._held_reservations.get(request_id)
            if not held and self._db_session_factory is not None:
                self.get_held_reservations()
                held = self._held_reservations.get(request_id)

            if not held:
                raise KeyError(f"Transaction '{request_id}' not found in held reservations")

            action_upper = action.strip().upper()
            if action_upper in ("APPROVE", "ALLOW", "SETTLE"):
                raise ValueError(
                    "Transitioning NEEDS_REVIEW to SETTLED requires verified provider proof; "
                    "manual override without provider proof is prohibited."
                )

            now_utc = self._clock.now_utc()
            payout_id = capture_id or held.get("payout_id")

            if action_upper in ("RETRY_LOOKUP", "PROVIDE_PROOF"):
                if not payout_id:
                    raise ValueError(
                        f"No provider ID available for proof verification on '{request_id}'"
                    )
                lookup_res = self._payment_rail.lookup(payout_id)
                provider_status = (lookup_res.status or "UNKNOWN").upper()
                CONFIRMED_SUCCESS = {"SUCCESS", "COMPLETED", "CONFIRMED", "SETTLED"}
                CONFIRMED_FAILURE = {
                    "FAILED",
                    "DENIED",
                    "REJECTED",
                    "EXPIRED",
                    "VOIDED",
                    "CANCELED",
                }

                if provider_status in CONFIRMED_SUCCESS:
                    new_state = self.reconcile(request_id, rail_status="COMPLETED")
                    intent = held.get("intent")
                    if intent:
                        dom_res = PolicyEvaluationResult(
                            outcome=DecisionOutcome.ALLOW,
                            reasons=(
                                f"Provider settlement confirmed ({payout_id}): "
                                f"{provider_status} by {actor}",
                            ),
                            evaluated_at_utc=now_utc,
                        )
                        with contextlib.suppress(Exception):
                            self._ledger.append_event(
                                event_type="RECONCILIATION_CONFIRMED",
                                intent=intent,
                                result=dom_res,
                                recorded_at_utc=now_utc,
                                provider_state=provider_status,
                            )
                    return new_state
                elif provider_status in CONFIRMED_FAILURE:
                    new_state = self.reconcile(request_id, rail_status=provider_status)
                    intent = held.get("intent")
                    if intent:
                        dom_res = PolicyEvaluationResult(
                            outcome=DecisionOutcome.DENY,
                            reasons=(
                                f"Provider confirmed failure ({payout_id}): "
                                f"{provider_status} by {actor}",
                            ),
                            evaluated_at_utc=now_utc,
                        )
                        with contextlib.suppress(Exception):
                            self._ledger.append_event(
                                event_type="RECONCILIATION_RELEASED",
                                intent=intent,
                                result=dom_res,
                                recorded_at_utc=now_utc,
                                provider_state=provider_status,
                            )
                    return new_state
                else:
                    held["provider_status"] = provider_status
                    return RequestState.NEEDS_REVIEW

            elif action_upper in ("MARK_FAILED", "REJECT", "CANCEL"):
                new_state = self.reconcile(request_id, rail_status="FAILED")
                intent = held.get("intent")
                if intent:
                    dom_res = PolicyEvaluationResult(
                        outcome=DecisionOutcome.DENY,
                        reasons=(
                            f"Supervisor marked failed by {actor}: "
                            f"{reason or 'Manual review failure'}",
                        ),
                        evaluated_at_utc=now_utc,
                    )
                    with contextlib.suppress(Exception):
                        self._ledger.append_event(
                            event_type="RECONCILIATION_RELEASED",
                            intent=intent,
                            result=dom_res,
                            recorded_at_utc=now_utc,
                            provider_state="FAILED",
                        )
                return new_state
            else:
                raise ValueError(f"Unknown action '{action}' for resolving NEEDS_REVIEW")

    def reset_state(self) -> None:
        with self._lock:
            self._lifetime_spent.clear()
            self._rolling_spent.clear()
            self._idempotency_records.clear()
            self._pending_step_ups.clear()
            self._responses_by_id.clear()
            self._held_reservations.clear()
            self._seed_default_step_up()

            if self._db_session_factory is not None:
                from sqlalchemy import delete, update

                from app.infrastructure.models import (
                    AgentBudgetModel,
                    ApprovalStatus,
                    BudgetReservationModel,
                    IdempotencyModel,
                    StepUpApprovalModel,
                )

                with self._db_session_factory() as session, session.begin():
                    session.execute(delete(BudgetReservationModel))
                    session.execute(delete(IdempotencyModel))
                    session.execute(
                        update(AgentBudgetModel).values(spent_minor=0, reserved_minor=0)
                    )
                    session.execute(
                        update(StepUpApprovalModel).values(status=ApprovalStatus.PENDING.value)
                    )


class LedgerService:
    """Application service for querying and cryptographically verifying the audit ledger."""

    def __init__(self, ledger: LedgerPort) -> None:
        self._ledger = ledger

    def get_all_events(self) -> list[LedgerEventDTO]:
        if hasattr(self._ledger, "get_all_events"):
            events = self._ledger.get_all_events()
            return [
                LedgerEventDTO(
                    event_id=e.event_id,
                    event_type=e.event_type,
                    prev_hash=e.prev_hash,
                    event_hash=e.event_hash,
                    payload=e.payload,
                )
                for e in events
            ]
        return []

    def verify_chain(self) -> LedgerVerificationDTO:
        if hasattr(self._ledger, "verify_integrity"):
            is_valid, msg, broken_idx = self._ledger.verify_integrity()
            events = (
                self._ledger.get_all_events() if hasattr(self._ledger, "get_all_events") else []
            )
            return LedgerVerificationDTO(
                is_valid=is_valid,
                message=msg,
                broken_index=broken_idx,
                total_events=len(events),
            )
        return LedgerVerificationDTO(
            is_valid=True,
            message="No ledger verification available",
            broken_index=None,
            total_events=0,
        )

    def tamper_chain(self, index: int = 1, new_amount: int = 99999999) -> None:
        """Tamper with a ledger block for auditor demo testing."""
        if hasattr(self._ledger, "tamper_for_testing"):
            self._ledger.tamper_for_testing(index, new_amount)

    def restore_chain(self) -> None:
        """Restore pristine unmodified ledger state."""
        if hasattr(self._ledger, "restore_true_ledger"):
            self._ledger.restore_true_ledger()


class HealthService:
    """Application service for system liveness and health diagnostics."""

    def __init__(self, clock: ClockPort) -> None:
        self._clock = clock

    def check_health(self) -> HealthStatusDTO:
        return HealthStatusDTO(
            status="ok",
            version="0.1.0",
            timestamp_utc=self._clock.now_utc(),
        )
