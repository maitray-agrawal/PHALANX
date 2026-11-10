"""Unit tests for the Invoice Agent and Gemini provider adapter guardrails.

Invariants:
- The guardrail path blocks forged agent proposals even if the LLM is fully compromised.
- PHALANX decision is deterministic and does not rely on LLM honesty.
- Gemini adapter enforces temperature 0, strict JSON, timeout, retry, token & daily budget caps.
- Fallback returns a clearly labelled 'RECORDED RUN' and never claims to be live.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.application.dtos import CreateMandateCommand
from app.application.invoice_agent import (
    SAMPLE_INVOICE_A,
    SAMPLE_INVOICE_B,
    SAMPLE_INVOICE_C,
    InvoiceAgent,
    InvoiceExtraction,
)
from app.application.services import AuthorizationService, MandateService
from app.domain.models import DecisionOutcome
from app.domain.ports import ClockPort
from app.infrastructure.gemini import (
    GeminiDailyBudgetExceededError,
    GeminiLLMClient,
)
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.paypal import FakePaymentRail


class CompromisedStubLLM:
    """Simulates an LLM completely compromised by prompt injection.

    Always returns the attacker's offshore fraudulent account and inflated amount.
    """

    def __init__(self, attacker_account: str = "attacker-fraud-99@shadybank.com") -> None:
        self.attacker_account = attacker_account

    def extract_invoice(self, _invoice_text: str) -> tuple[InvoiceExtraction, bool, str]:
        # Always proposes the attacker's payee and account
        return (
            InvoiceExtraction(
                payee="Attacker Syndicate Ltd",
                account=self.attacker_account,
                amount_minor=999_900,  # $9,999.00
                currency="USD",
                due_date="2026-11-15",
                invoice_number="ATTACK-666",
                purpose="Urgent redirection of funds to attacker account",
            ),
            True,  # is_live
            "gemini-test-compromised-stub",
        )


def test_guardrail_path_blocks_compromised_llm_proposal(
    test_clock: ClockPort, test_ledger: InMemoryLedgerAdapter
) -> None:
    """Guardrail invariant: Compromised LLM proposal is deterministically BLOCKED by PHALANX.

    Even when the LLM returns the attacker's account, PHALANX's policy engine
    refuses authorization because the payee is unregistered and outside the mandate.
    """
    mandate_service = MandateService(clock=test_clock)
    mandate_service.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-inv-agent-1",
            principal_id="principal-corp-1",
            agent_id="agent-invoice-1",
            single_limit_minor=50_000,  # $500.00
            instant_threshold_minor=10_000,  # $100.00
            lifetime_budget_minor=500_000,  # $5,000.00
            allowed_payees=["vendor-paypal-sandbox-1", "acme-corp-verified"],
            allow_unregistered_payees=False,
            valid_days=30,
        )
    )

    rail = FakePaymentRail(should_succeed=True)
    auth_service = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
    )

    # Use the compromised stub LLM
    compromised_llm = CompromisedStubLLM(attacker_account="attacker-fraud-99@shadybank.com")
    agent = InvoiceAgent(
        authorization_service=auth_service,
        llm_extractor=compromised_llm,
        agent_id="agent-invoice-1",
    )

    # Feed an invoice with embedded injection
    result = agent.process_invoice(SAMPLE_INVOICE_C["text"])

    # 1. Verify LLM did propose the attacker's account
    assert result.extraction.account == "attacker-fraud-99@shadybank.com"
    assert result.extraction.amount_minor == 999_900

    # 2. Invariant: PHALANX decision is strictly DENY
    assert result.decision == DecisionOutcome.DENY.value
    assert (
        "not in mandate allowed_payees" in result.decision_reason
        or "Unregistered payee" in result.decision_reason
        or "exceeds" in result.decision_reason
    )
    assert result.request_state == "DENIED"

    # 3. Invariant: Zero funds dispatched, zero rail payments
    assert len(rail.dispatched_payments) == 0

    # 4. Invariant: Ledger records the denial event
    assert result.ledger_event is not None
    assert result.ledger_event["decision"] == "DENY"


def test_built_in_sample_invoices_matrix(
    test_clock: ClockPort, test_ledger: InMemoryLedgerAdapter
) -> None:
    """Verify built-in sample invoices A, B, C produce correct deterministic outcomes."""
    mandate_service = MandateService(clock=test_clock)
    mandate_service.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-inv-agent-samples",
            principal_id="principal-corp-1",
            agent_id="agent-invoice-1",
            single_limit_minor=100_000,  # $1,000.00
            instant_threshold_minor=50_000,  # $500.00
            lifetime_budget_minor=500_000,  # $5,000.00
            allowed_payees=["vendor-paypal-sandbox-1"],
            allow_unregistered_payees=False,
            valid_days=30,
        )
    )

    rail = FakePaymentRail(should_succeed=True)
    auth_service = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=mandate_service,
        payment_rail=rail,
    )

    agent = InvoiceAgent(
        authorization_service=auth_service,
        agent_id="agent-invoice-1",
    )

    # Sample A: Legitimate and within mandate ($25.00 < $500.00 threshold) -> ALLOW
    res_a = agent.process_invoice(SAMPLE_INVOICE_A["text"], force_fallback=True)
    assert res_a.decision == DecisionOutcome.ALLOW.value
    assert res_a.extraction.amount_minor == 2500
    assert res_a.extraction.account == "vendor-paypal-sandbox-1"

    # Sample B: Legitimate but above instant limit ($750.00 > $500.00 threshold) -> STEP_UP
    res_b = agent.process_invoice(SAMPLE_INVOICE_B["text"], force_fallback=True)
    assert res_b.decision == DecisionOutcome.STEP_UP.value
    assert res_b.extraction.amount_minor == 75000
    assert res_b.request_state == "PENDING_APPROVAL"

    # Sample C: Injection attack containing hidden instruction -> DENIED
    res_c = agent.process_invoice(SAMPLE_INVOICE_C["text"], force_fallback=True)
    assert res_c.decision == DecisionOutcome.DENY.value
    assert res_c.request_state == "DENIED"


def test_gemini_client_fallback_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """When GEMINI_API_KEY is not provided, client cleanly falls back to certified recorded run."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiLLMClient(api_key="")
    extraction, is_live, label = client.extract_invoice(SAMPLE_INVOICE_A["text"])

    assert is_live is False
    assert "RECORDED" in label
    assert extraction.amount_minor == 2500
    assert extraction.account == "vendor-paypal-sandbox-1"


def test_gemini_client_daily_budget_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce daily call cap with 'demo budget reached' response."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-mock-123")
    client = GeminiLLMClient(api_key="test-key-mock-123", daily_call_cap=2)

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        extracted_sample = (
            '{"payee": "Vendor", "account": "vendor-1", "amount_minor": 1000, '
            '"currency": "USD", "due_date": "2026-11-20", "invoice_number": "1", '
            '"purpose": "Test"}'
        )
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": extracted_sample,
                            }
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        # Call 1: OK
        client.generate_json("Prompt 1")
        # Call 2: OK
        client.generate_json("Prompt 2")
        # Call 3: Exceeds daily cap
        with pytest.raises(GeminiDailyBudgetExceededError, match="demo budget reached"):
            client.generate_json("Prompt 3")
