"""Application services coordinating use cases."""

from app.application.dtos import (
    AuthorizationResponseDTO,
    AuthorizeTransactionCommand,
    HealthStatusDTO,
)
from app.domain.models import (
    DecisionOutcome,
    Money,
    PolicyEvaluationResult,
    TransactionIntent,
    escalate_decision,
)
from app.domain.ports import ClockPort, LedgerPort


class AuthorizationService:
    """Orchestrates authorization requests against domain policies and ledger."""

    def __init__(self, clock: ClockPort, ledger: LedgerPort) -> None:
        self._clock = clock
        self._ledger = ledger

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

        # Baseline policy evaluation:
        # <= $500.00 (50,000 minor units): ALLOW
        # > $500.00 and <= $5,000.00 (500,000 minor units): STEP_UP (human review required)
        # > $5,000.00: DENY (exceeds single transaction authority)
        reasons: list[str] = []
        if money.amount_minor > 500_000:
            base_decision = DecisionOutcome.DENY
            reasons.append("Amount exceeds maximum single transaction limit (500,000 minor units)")
        elif money.amount_minor > 50_000:
            base_decision = DecisionOutcome.STEP_UP
            reasons.append(
                "Amount exceeds instant threshold (50,000 minor units); step-up required"
            )
        else:
            base_decision = DecisionOutcome.ALLOW
            reasons.append("Amount within pre-authorized autonomous limit")

        # Escalate if heuristic/ML anomaly signal is present
        final_decision = escalate_decision(base_decision, command.anomaly_signal)
        escalated = final_decision != base_decision
        if escalated:
            reasons.append(
                f"Decision escalated by risk signal: "
                f"{base_decision.value} -> {final_decision.value}"
            )

        eval_result = PolicyEvaluationResult(
            outcome=final_decision,
            reasons=tuple(reasons),
            escalated_from=base_decision if escalated else None,
            evaluated_at_utc=now_utc,
        )

        event_id = self._ledger.append_event(
            event_type="AUTHORIZATION_EVALUATED",
            intent=intent,
            result=eval_result,
            recorded_at_utc=now_utc,
        )

        return AuthorizationResponseDTO(
            decision=final_decision,
            reasons=reasons,
            escalated=escalated,
            event_id=event_id,
            evaluated_at_utc=now_utc,
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
