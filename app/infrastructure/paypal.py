"""PayPal Sandbox Rail Adapter & Protocol."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.models import TransactionIntent


@dataclass(frozen=True)
class RailPaymentResult:
    """Outcome of dispatching payment through payment rail."""

    success: bool
    transaction_id: str
    status: str
    details: dict[str, Any]


class PaymentRail(Protocol):
    """Protocol for executing external payments."""

    def pay(self, intent: TransactionIntent) -> RailPaymentResult: ...

    def lookup(self, transaction_id: str) -> RailPaymentResult: ...

    def verify_webhook(self, headers: dict[str, str], body_bytes: bytes) -> bool: ...


class FakePaymentRail:
    """In-memory recording payment rail for deterministic test execution."""

    def __init__(self, should_succeed: bool = True) -> None:
        self.should_succeed = should_succeed
        self.dispatched_payments: list[TransactionIntent] = []
        self._tx_counter = 0

    def pay(self, intent: TransactionIntent) -> RailPaymentResult:
        self.dispatched_payments.append(intent)
        self._tx_counter += 1
        if self.should_succeed:
            return RailPaymentResult(
                success=True,
                transaction_id=f"sandbox_tx_{self._tx_counter:08d}",
                status="COMPLETED",
                details={"rail": "fake_sandbox", "amount": intent.money.amount_minor},
            )
        return RailPaymentResult(
            success=False,
            transaction_id="",
            status="FAILED",
            details={"error": "simulated_rail_failure"},
        )

    def lookup(self, transaction_id: str) -> RailPaymentResult:
        return RailPaymentResult(
            success=True,
            transaction_id=transaction_id,
            status="COMPLETED",
            details={},
        )

    def verify_webhook(self, headers: dict[str, str], body_bytes: bytes) -> bool:
        # Check presence of required PayPal webhook headers and non-empty payload
        _ = body_bytes
        algo = headers.get("PAYPAL-AUTH-ALGO") or headers.get("paypal-auth-algo")
        sig = headers.get("PAYPAL-TRANSMISSION-SIG") or headers.get("paypal-transmission-sig")
        return bool(algo and sig)
