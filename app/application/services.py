"""Application services coordinating use cases.

Invariants:
- All entry points go through application services.
- Deterministic policy evaluation with pure domain logic.
- Cryptographic hash chaining on all ledger writes.
- Mandatory intent digest verification before human approval execution.
- Payment rail dispatch only on confirmed ALLOW.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from threading import Lock, RLock
from typing import Any

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
from app.domain.ports import ClockPort, LedgerPort, PaymentRail
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
from app.infrastructure.models import AgentBudgetModel, ReservationStatus
from app.infrastructure.paypal import FakePaymentRail


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


class MandateService:
    """Manages Ed25519-signed authority mandates."""

    def __init__(
        self,
        clock: ClockPort,
        priv_key: bytes | None = None,
        pub_key: bytes | None = None,
        key_id: str | None = None,
    ) -> None:
        self._clock = clock
        if priv_key and pub_key and key_id:
            self._priv_key = priv_key
            self._pub_key = pub_key
            self._key_id = key_id
        else:
            from app.infrastructure.config import settings

            self._priv_key, self._pub_key, self._key_id = load_or_generate_keypair(
                key_hex=settings.mandate_signing_key_hex,
                key_file_path=settings.mandate_signing_key_file,
            )
        self._mandates: dict[str, Mandate] = {}
        self._history: dict[str, list[Mandate]] = {}
        self._lock = Lock()
        self._seed_default_mandate()

    def _seed_default_mandate(self) -> None:
        """Seed a standard operational demo mandate."""
        now = self._clock.now_utc()
        mandate_id = "mandate_default_astra"
        valid_until = max(
            now + timedelta(days=365),
            datetime(2027, 3, 31, 23, 59, 59, tzinfo=UTC),
        )
        payload = {
            "mandate_id": mandate_id,
            "version": 1,
            "principal_id": "principal_astra_treasury",
            "agent_id": "agent-auto-1",
            "single_limit_minor": 500_000,  # $5,000 max single cap
            "instant_threshold_minor": 50_000,  # $500 instant threshold
            "lifetime_budget_minor": 2_500_000,  # $25,000 lifetime cap
            "currency": "USD",
            "allowed_payees": [],
            "allow_unregistered_payees": True,
            "allowed_purposes": [],
            "valid_from_utc": (now - timedelta(days=1)).isoformat(),
            "valid_until_utc": valid_until.isoformat(),
            "status": MandateStatus.ACTIVE.value,
            "key_id": self._key_id,
        }
        sig = sign_bytes(self._priv_key, canonical_json_bytes(payload))
        mandate = Mandate(
            mandate_id=mandate_id,
            version=1,
            principal_id="principal_astra_treasury",
            agent_id="agent-auto-1",
            single_limit_minor=500_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=2_500_000,
            currency="USD",
            allowed_payees=(),
            allow_unregistered_payees=True,
            allowed_purposes=(),
            valid_from_utc=now - timedelta(days=1),
            valid_until_utc=valid_until,
            status=MandateStatus.ACTIVE,
            key_id=self._key_id,
            signature=sig,
        )
        self._mandates[mandate_id] = mandate
        self._mandates["mandate_default_sandbox"] = mandate
        self._history[mandate_id] = [mandate]
        self._history["mandate_default_sandbox"] = [mandate]

    def get_active_mandate_for_agent(self, agent_id: str) -> Mandate | None:
        with self._lock:
            for mandate in self._mandates.values():
                if mandate.agent_id == agent_id and mandate.status == MandateStatus.ACTIVE:
                    return mandate
            return None

    def get_mandate(self, mandate_id: str) -> Mandate | None:
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
        sig = sign_bytes(self._priv_key, canonical_json_bytes(signable_dict))
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
        with self._lock:
            current = self._mandates.get(mandate_id)
            if not current:
                raise ValueError(f"Mandate {mandate_id} not found")
            if current.status != MandateStatus.ACTIVE:
                raise ValueError(
                    f"Cannot supersede mandate {mandate_id} with status {current.status}"
                )

            now = self._clock.now_utc()
            new_version = current.version + 1
            valid_until = (
                now + timedelta(days=valid_days)
                if valid_days is not None
                else current.valid_until_utc
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
                    single_limit_minor
                    if single_limit_minor is not None
                    else current.single_limit_minor
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
        with self._lock:
            current = self._mandates.get(mandate_id)
            if not current:
                raise ValueError(f"Mandate {mandate_id} not found")
            revoked = current.revoke()
            self._mandates[mandate_id] = revoked
            if mandate_id not in self._history:
                self._history[mandate_id] = []
            self._history[mandate_id].append(revoked)

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
        self._seed_default_step_up()

    def _seed_default_step_up(self) -> None:
        """Seed a pending step-up request for the human supervisor demo queue."""
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

    def get_pending_step_ups(self) -> list[PendingStepUpDTO]:
        with self._lock:
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
            return self._pending_step_ups.get(request_id)

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
            elif final_decision == DecisionOutcome.ALLOW:
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
                    )

                    if rail_res.success:
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
                    elif is_ambiguous:
                        current_req_state = transition_request_state(
                            current_req_state,
                            RequestState.RECONCILE,
                            reason=f"Ambiguous rail outcome: {rail_res.status}",
                        )
                        # Associated budget reservation MUST remain held:
                        self._held_reservations[request_id] = {
                            "agent_id": command.agent_id,
                            "amount_minor": intent.money.amount_minor,
                            "reservation_id": db_res_id,
                            "intent": intent,
                            "payout_id": payout_id,
                            "intent_digest": intent_digest,
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
            if not pending:
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
                        )

                        if rail_res.success:
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
                        elif is_ambiguous:
                            current_req_state = transition_request_state(
                                current_req_state,
                                RequestState.RECONCILE,
                                reason=f"Ambiguous rail outcome: {rail_res.status}",
                            )
                            self._held_reservations[command.request_id] = {
                                "agent_id": intent.agent_id,
                                "amount_minor": intent.money.amount_minor,
                                "reservation_id": db_res_id,
                                "intent": intent,
                                "payout_id": payout_id,
                                "intent_digest": stored_digest,
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
            return resp

    def get_request_state(self, request_id: str) -> RequestState | None:
        """Return the current lifecycle state of a request."""
        with self._lock:
            return self._request_states.get(request_id)

    def reconcile(
        self,
        request_id: str,
        rail_status: str | None = None,
    ) -> RequestState:
        """Reconcile a transaction currently in RECONCILE state against external rail outcome.

        Classification (Manual 56.13, 56.17):
        - Confirmed success: -> RequestState.SETTLED. Budget remains spent.
        - Confirmed failure: -> RequestState.FAILED. Releases held budget.
        - Still unknown: -> remains RequestState.RECONCILE. Budget remains held.
        """
        with self._lock:
            current_state = self._request_states.get(request_id)
            if current_state != RequestState.RECONCILE:
                raise ValueError(
                    f"Request '{request_id}' is not in RECONCILE state (current: {current_state})"
                )

            resp = self._responses_by_id.get(request_id)
            payout_id = resp.payout_id if resp else None
            held = self._held_reservations.get(request_id)

            if rail_status is None and payout_id:
                lookup_res = self._payment_rail.lookup(payout_id)
                rail_status = lookup_res.status

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
                "LOOKUP_FAILED",
            }

            if self._db_session_factory is not None and held and held.get("reservation_id"):
                with self._db_session_factory() as session, session.begin():
                    repo = BudgetRepository(session)
                    res_model = repo.reconcile_reservation(
                        held["reservation_id"], rail_status=status_norm
                    )
                    if res_model.status == ReservationStatus.CONFIRMED.value:
                        new_state = transition_request_state(current_state, RequestState.SETTLED)
                        self._held_reservations.pop(request_id, None)
                    elif res_model.status == ReservationStatus.RELEASED.value:
                        new_state = transition_request_state(current_state, RequestState.FAILED)
                        self._held_reservations.pop(request_id, None)
                    else:
                        new_state = RequestState.RECONCILE
                    self._request_states[request_id] = new_state
                    if resp:
                        resp.request_state = new_state
                    return new_state

            if status_norm in CONFIRMED_SUCCESS:
                new_state = transition_request_state(current_state, RequestState.SETTLED)
                self._request_states[request_id] = new_state
                self._held_reservations.pop(request_id, None)
                if resp:
                    resp.request_state = new_state
                return new_state
            elif status_norm in CONFIRMED_FAILURE:
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
                return new_state
            else:
                # Still unknown: remains RECONCILE, reservation remains held
                return RequestState.RECONCILE

    def get_payment_request(self, request_id: str) -> AuthorizationResponseDTO | None:
        with self._lock:
            return self._responses_by_id.get(request_id)

    def get_decision(self, decision_id: str) -> AuthorizationResponseDTO | None:
        with self._lock:
            for resp in self._responses_by_id.values():
                if resp.event_id == decision_id or resp.request_id == decision_id:
                    return resp
            return None

    def get_held_reservations(self) -> list[dict[str, Any]]:
        with self._lock:
            items: list[dict[str, Any]] = []
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
                        "state": self._request_states.get(req_id, RequestState.RECONCILE).value,
                    }
                )
            return items

    def reset_state(self) -> None:
        with self._lock:
            self._lifetime_spent.clear()
            self._rolling_spent.clear()
            self._idempotency_records.clear()
            self._pending_step_ups.clear()
            self._responses_by_id.clear()
            self._held_reservations.clear()
            self._seed_default_step_up()


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
