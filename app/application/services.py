"""Application services coordinating use cases.

Invariants:
- All entry points go through application services.
- Deterministic policy evaluation with pure domain logic.
- Cryptographic hash chaining on all ledger writes.
- Mandatory intent digest verification before human approval execution.
- Payment rail dispatch only on confirmed ALLOW.
"""

import hashlib
from datetime import datetime, timedelta
from threading import Lock
from typing import Any

from app.application.dtos import (
    ApprovalCommand,
    AuthorizationResponseDTO,
    AuthorizeTransactionCommand,
    CreateMandateCommand,
    HealthStatusDTO,
    LedgerEventDTO,
    LedgerVerificationDTO,
    MandateResponseDTO,
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
from app.infrastructure.crypto import (
    generate_ed25519_keypair,
    get_key_id,
    sign_bytes,
    verify_signature,
)
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

    def __init__(self, clock: ClockPort) -> None:
        self._clock = clock
        self._priv_key, self._pub_key = generate_ed25519_keypair()
        self._key_id = get_key_id(self._pub_key)
        self._mandates: dict[str, Mandate] = {}
        self._lock = Lock()
        self._seed_default_mandate()

    def _seed_default_mandate(self) -> None:
        """Seed a standard operational demo mandate."""
        now = self._clock.now_utc()
        mandate_id = "mandate_default_astra"
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
            "allowed_purposes": [],
            "valid_from_utc": (now - timedelta(days=1)).isoformat(),
            "valid_until_utc": (now + timedelta(days=365)).isoformat(),
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
            allowed_purposes=(),
            valid_from_utc=now - timedelta(days=1),
            valid_until_utc=now + timedelta(days=365),
            status=MandateStatus.ACTIVE,
            key_id=self._key_id,
            signature=sig,
        )
        self._mandates[mandate_id] = mandate

    def get_active_mandate_for_agent(self, agent_id: str) -> Mandate | None:
        with self._lock:
            for mandate in self._mandates.values():
                if mandate.agent_id == agent_id and mandate.status == MandateStatus.ACTIVE:
                    return mandate
            # Fallback to default mandate if agent matches or general
            return self._mandates.get("mandate_default_astra")

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
            allowed_purposes=tuple(cmd.allowed_purposes),
            valid_from_utc=now,
            valid_until_utc=valid_until,
            status=MandateStatus.ACTIVE,
            key_id=self._key_id,
            signature=sig,
        )
        with self._lock:
            self._mandates[cmd.mandate_id] = mandate

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
            allowed_purposes=list(mandate.allowed_purposes),
            valid_from_utc=mandate.valid_from_utc,
            valid_until_utc=mandate.valid_until_utc,
            status=mandate.status,
            key_id=mandate.key_id,
            signature=mandate.signature,
        )

    def verify_mandate_integrity(self, mandate: Mandate) -> bool:
        """Verify the Ed25519 signature of a mandate."""
        signable_dict = mandate.to_signable_dict()
        message = canonical_json_bytes(signable_dict)
        return verify_signature(self._pub_key, message, mandate.signature)


class AuthorizationService:
    """Orchestrates authorization requests against domain policies and ledger."""

    def __init__(
        self,
        clock: ClockPort,
        ledger: LedgerPort,
        mandate_service: MandateService | None = None,
        payment_rail: PaymentRail | None = None,
    ) -> None:
        self._clock = clock
        self._ledger = ledger
        self._mandate_service = mandate_service or MandateService(clock=clock)
        self._payment_rail = payment_rail or FakePaymentRail()
        self._lock = Lock()
        self._lifetime_spent: int = 0
        self._rolling_spent: int = 0
        self._idempotency_records: dict[str, tuple[str, DecisionOutcome]] = {}
        self._pending_step_ups: dict[str, dict[str, Any]] = {}
        self._responses_by_id: dict[str, AuthorizationResponseDTO] = {}

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
                    state = PolicyState(
                        lifetime_spent_minor=self._lifetime_spent,
                        rolling_24h_spent_minor=self._rolling_spent,
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
            if final_decision == DecisionOutcome.ALLOW:
                # Reserve budget
                self._lifetime_spent += intent.money.amount_minor
                self._rolling_spent += intent.money.amount_minor
                # Dispatch payment rail
                rail_res = self._payment_rail.pay(intent)
                payout_id = rail_res.transaction_id

            elif final_decision == DecisionOutcome.STEP_UP:
                # Store pending approval record bound to intent digest
                self._pending_step_ups[request_id] = {
                    "intent": intent,
                    "intent_digest": intent_digest,
                    "created_at_utc": now_utc,
                    "mandate": mandate,
                }

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

            if command.decision == DecisionOutcome.ALLOW:
                # Re-verify budget on current state
                if (
                    self._lifetime_spent + intent.money.amount_minor
                ) > mandate.lifetime_budget_minor:
                    final_decision = DecisionOutcome.DENY
                    reasons.append("Lifetime budget exceeded on execution re-check")
                    codes.append(PolicyReasonCode.LIFETIME_BUDGET_EXCEEDED)
                else:
                    final_decision = DecisionOutcome.ALLOW
                    self._lifetime_spent += intent.money.amount_minor
                    self._rolling_spent += intent.money.amount_minor
                    rail_res = self._payment_rail.pay(intent)
                    payout_id = rail_res.transaction_id
            else:
                final_decision = DecisionOutcome.DENY

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
            )
            self._responses_by_id[command.request_id] = resp
            return resp

    def get_payment_request(self, request_id: str) -> AuthorizationResponseDTO | None:
        with self._lock:
            return self._responses_by_id.get(request_id)

    def get_decision(self, decision_id: str) -> AuthorizationResponseDTO | None:
        with self._lock:
            for resp in self._responses_by_id.values():
                if resp.event_id == decision_id or resp.request_id == decision_id:
                    return resp
            return None

    def reset_state(self) -> None:
        with self._lock:
            self._lifetime_spent = 0
            self._rolling_spent = 0
            self._idempotency_records.clear()
            self._pending_step_ups.clear()
            self._responses_by_id.clear()


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
