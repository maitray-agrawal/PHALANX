"""Pure deterministic policy engine for PHALANX.

Invariants:
- Zero I/O, no clock, no randomness (time and state injected).
- Strict rule order adhering exactly to Master Specification Section 5.
- One-way escalation: advisory signals can only raise risk, never soften it.
- State arrives as a plain, immutable object.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.domain.mandates import Mandate, MandateStatus
from app.domain.models import (
    DecisionOutcome,
    TransactionIntent,
    guard_advisory_escalation,
)


class PolicyReasonCode(str, Enum):
    IDEMPOTENCY_REPLAY = "IDEMPOTENCY_REPLAY"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    MANDATE_INACTIVE = "MANDATE_INACTIVE"
    MANDATE_NOT_YET_VALID = "MANDATE_NOT_YET_VALID"
    MANDATE_EXPIRED = "MANDATE_EXPIRED"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    PAYEE_UNAUTHORIZED = "PAYEE_UNAUTHORIZED"
    PURPOSE_UNAUTHORIZED = "PURPOSE_UNAUTHORIZED"
    INVOICE_REFERENCE_REQUIRED = "INVOICE_REFERENCE_REQUIRED"
    LIFETIME_BUDGET_EXCEEDED = "LIFETIME_BUDGET_EXCEEDED"
    SINGLE_LIMIT_EXCEEDED = "SINGLE_LIMIT_EXCEEDED"
    INSTANT_THRESHOLD_EXCEEDED = "INSTANT_THRESHOLD_EXCEEDED"
    PRE_AUTHORIZED = "PRE_AUTHORIZED"
    RISK_ESCALATED = "RISK_ESCALATED"


@dataclass(frozen=True)
class PolicyState:
    """Current cumulative financial state of the agent under a mandate.

    Plain object: zero database, network, clock, or randomness inside.
    """

    lifetime_spent_minor: int
    rolling_24h_spent_minor: int
    idempotency_records: dict[str, tuple[str, DecisionOutcome]]


@dataclass(frozen=True)
class PolicyDecision:
    """Outcome of a deterministic policy evaluation."""

    outcome: DecisionOutcome
    reasons: tuple[str, ...]
    reason_codes: tuple[PolicyReasonCode, ...]
    escalated_from: DecisionOutcome | None
    evaluated_at_utc: datetime
    policy_version: str = "1.0.0"


def evaluate_policy(
    intent: TransactionIntent,
    mandate: Mandate,
    state: PolicyState,
    now_utc: datetime,
    advisory_signal: DecisionOutcome | None = None,
    intent_digest: str | None = None,
) -> PolicyDecision:
    """Evaluate a transaction intent deterministically against mandate and state.

    Rule order (Master Specification Section 5):
    1. Idempotency Check (replay vs parameter tampering)
    2. Mandate Status Check (ACTIVE)
    3. Temporal Validity Check (valid_from <= now <= valid_until)
    4. Currency Check (ISO 4217 match)
    5. Payee Allowlist Check (if configured)
    6. Purpose Allowlist Check (if configured)
    7. Invoice Reference Check (if required by mandate)
    8. Lifetime Budget Cap Check (lifetime_spent + amount <= budget)
    9. Single Transaction Limit Check (amount <= single_limit)
    10. Instant Threshold Check (amount <= instant_threshold -> ALLOW, else STEP_UP)
    11. Advisory Signal Escalation Guard (one-way tightening: ALLOW -> STEP_UP -> DENY)
    """
    reasons: list[str] = []
    codes: list[PolicyReasonCode] = []

    current_digest = intent_digest or intent.idempotency_key

    # 1. Idempotency check
    if intent.idempotency_key in state.idempotency_records:
        cached_digest, cached_decision = state.idempotency_records[intent.idempotency_key]
        if cached_digest == current_digest:
            return PolicyDecision(
                outcome=cached_decision,
                reasons=("Idempotency match: returning previously stored decision",),
                reason_codes=(PolicyReasonCode.IDEMPOTENCY_REPLAY,),
                escalated_from=None,
                evaluated_at_utc=now_utc,
            )
        # Same key but mutated digest -> immediate hard DENY
        return PolicyDecision(
            outcome=DecisionOutcome.DENY,
            reasons=("Idempotency violation: key reused with mutated parameters",),
            reason_codes=(PolicyReasonCode.IDEMPOTENCY_MISMATCH,),
            escalated_from=None,
            evaluated_at_utc=now_utc,
        )

    # 2. Mandate status check
    if mandate.status != MandateStatus.ACTIVE:
        return PolicyDecision(
            outcome=DecisionOutcome.DENY,
            reasons=(f"Mandate is not active (status: {mandate.status.value})",),
            reason_codes=(PolicyReasonCode.MANDATE_INACTIVE,),
            escalated_from=None,
            evaluated_at_utc=now_utc,
        )

    # 3. Temporal validity check
    if now_utc < mandate.valid_from_utc:
        return PolicyDecision(
            outcome=DecisionOutcome.DENY,
            reasons=(f"Mandate not yet valid (valid from: {mandate.valid_from_utc.isoformat()})",),
            reason_codes=(PolicyReasonCode.MANDATE_NOT_YET_VALID,),
            escalated_from=None,
            evaluated_at_utc=now_utc,
        )
    if now_utc > mandate.valid_until_utc:
        return PolicyDecision(
            outcome=DecisionOutcome.DENY,
            reasons=(f"Mandate has expired (expired at: {mandate.valid_until_utc.isoformat()})",),
            reason_codes=(PolicyReasonCode.MANDATE_EXPIRED,),
            escalated_from=None,
            evaluated_at_utc=now_utc,
        )

    # 4. Currency check
    if intent.money.currency != mandate.currency:
        return PolicyDecision(
            outcome=DecisionOutcome.DENY,
            reasons=(
                f"Currency mismatch: requested {intent.money.currency}, "
                f"mandate authorizes {mandate.currency}",
            ),
            reason_codes=(PolicyReasonCode.CURRENCY_MISMATCH,),
            escalated_from=None,
            evaluated_at_utc=now_utc,
        )

    # 5. Payee allowlist check
    if not mandate.allowed_payees:
        if not mandate.allow_unregistered_payees:
            return PolicyDecision(
                outcome=DecisionOutcome.DENY,
                reasons=(
                    "Mandate requires an authorized payee from allowlist; "
                    "unregistered payees are prohibited",
                ),
                reason_codes=(PolicyReasonCode.PAYEE_UNAUTHORIZED,),
                escalated_from=None,
                evaluated_at_utc=now_utc,
            )
    elif (
        not mandate.allow_unregistered_payees and intent.recipient_id not in mandate.allowed_payees
    ):
        return PolicyDecision(
            outcome=DecisionOutcome.DENY,
            reasons=(f"Payee '{intent.recipient_id}' not in mandate allowed_payees",),
            reason_codes=(PolicyReasonCode.PAYEE_UNAUTHORIZED,),
            escalated_from=None,
            evaluated_at_utc=now_utc,
        )

    # 6. Purpose allowlist check
    if mandate.allowed_purposes and intent.purpose not in mandate.allowed_purposes:
        return PolicyDecision(
            outcome=DecisionOutcome.DENY,
            reasons=(f"Purpose '{intent.purpose}' not in mandate allowed_purposes",),
            reason_codes=(PolicyReasonCode.PURPOSE_UNAUTHORIZED,),
            escalated_from=None,
            evaluated_at_utc=now_utc,
        )

    # 7. Invoice reference check
    if mandate.require_invoice_reference and (
        not intent.invoice_reference or not intent.invoice_reference.strip()
    ):
        return PolicyDecision(
            outcome=DecisionOutcome.DENY,
            reasons=("Mandate requires an invoice reference, but none was provided",),
            reason_codes=(PolicyReasonCode.INVOICE_REFERENCE_REQUIRED,),
            escalated_from=None,
            evaluated_at_utc=now_utc,
        )

    # 8. Lifetime budget check
    new_lifetime_spent = state.lifetime_spent_minor + intent.money.amount_minor
    if new_lifetime_spent > mandate.lifetime_budget_minor:
        return PolicyDecision(
            outcome=DecisionOutcome.DENY,
            reasons=(
                f"Lifetime budget cap exceeded: requested {intent.money.amount_minor} + "
                f"spent {state.lifetime_spent_minor} > cap {mandate.lifetime_budget_minor}",
            ),
            reason_codes=(PolicyReasonCode.LIFETIME_BUDGET_EXCEEDED,),
            escalated_from=None,
            evaluated_at_utc=now_utc,
        )

    # 9. Single transaction limit check
    if intent.money.amount_minor > mandate.single_limit_minor:
        base_decision = DecisionOutcome.DENY
        reasons.append(
            f"Amount {intent.money.amount_minor} exceeds single limit cap "
            f"({mandate.single_limit_minor})"
        )
        codes.append(PolicyReasonCode.SINGLE_LIMIT_EXCEEDED)
    elif intent.money.amount_minor > mandate.instant_threshold_minor:
        base_decision = DecisionOutcome.STEP_UP
        reasons.append(
            f"Amount {intent.money.amount_minor} exceeds instant threshold "
            f"({mandate.instant_threshold_minor}); human approval required"
        )
        codes.append(PolicyReasonCode.INSTANT_THRESHOLD_EXCEEDED)
    else:
        base_decision = DecisionOutcome.ALLOW
        reasons.append("Amount within pre-authorized autonomous limits")
        codes.append(PolicyReasonCode.PRE_AUTHORIZED)

    # 10. Advisory signal escalation guard
    final_decision = guard_advisory_escalation(base_decision, advisory_signal)
    escalated = final_decision != base_decision
    if escalated:
        reasons.append(
            f"Decision escalated by risk signal: {base_decision.value} -> {final_decision.value}"
        )
        codes.append(PolicyReasonCode.RISK_ESCALATED)

    return PolicyDecision(
        outcome=final_decision,
        reasons=tuple(reasons),
        reason_codes=tuple(codes),
        escalated_from=base_decision if escalated else None,
        evaluated_at_utc=now_utc,
    )


# Standard functional alias matching evaluate(intent, mandate, state, now)
evaluate = evaluate_policy
