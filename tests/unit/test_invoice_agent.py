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
    GeminiConfigurationError,
    GeminiDailyBudgetExceededError,
    GeminiError,
    GeminiLLMClient,
    GeminiTimeoutError,
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


def test_gemini_client_missing_api_key_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing API key raises GeminiConfigurationError on generate_json."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiLLMClient(api_key="")
    assert client.is_configured is False
    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY unconfigured"):
        client.generate_json("Test prompt")


def test_gemini_client_valid_model_configuration() -> None:
    """Valid model configuration selects the specified model and defaults to gemini-2.5-flash."""
    client_default = GeminiLLMClient(api_key="mock-key")
    assert client_default.model_name == "gemini-2.5-flash"
    assert client_default.is_configured is True

    client_custom = GeminiLLMClient(api_key="mock-key", model_name="gemini-2.5-pro")
    assert client_custom.model_name == "gemini-2.5-pro"


def test_gemini_client_malformed_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed candidate or missing text parts raises GeminiError."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-key")
    client = GeminiLLMClient(api_key="mock-key")

    with patch("httpx.post") as mock_post:
        # Case 1: Empty candidates list
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = {"candidates": []}
        mock_post.return_value = mock_resp1

        with pytest.raises(GeminiError, match="contained no candidates"):
            client.generate_json("Prompt")

        # Case 2: Candidate with no content parts
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {"candidates": [{"content": {"parts": []}}]}
        mock_post.return_value = mock_resp2

        with pytest.raises(GeminiError, match="contained no text parts"):
            client.generate_json("Prompt")


def test_gemini_client_provider_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider timeout raises GeminiTimeoutError."""
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "mock-key")
    client = GeminiLLMClient(api_key="mock-key", max_retries=0)

    with (
        patch("httpx.post", side_effect=httpx.TimeoutException("Read timed out")),
        pytest.raises(GeminiTimeoutError, match="timed out"),
    ):
        client.generate_json("Prompt")


def test_gemini_client_http_429_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 429 rate limit raises GeminiError."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-key")
    client = GeminiLLMClient(api_key="mock-key", max_retries=0)

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_post.return_value = mock_resp

        with pytest.raises(GeminiError, match="HTTP 429"):
            client.generate_json("Prompt")


def test_gemini_client_http_5xx_retries_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 500 error retries and then raises GeminiError."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-key")
    client = GeminiLLMClient(api_key="mock-key", max_retries=1)

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_post.return_value = mock_resp

        with pytest.raises(GeminiError, match="HTTP 503"):
            client.generate_json("Prompt")
        assert mock_post.call_count == 2


def test_gemini_client_invalid_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-JSON text returned by model raises GeminiError."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-key")
    client = GeminiLLMClient(api_key="mock-key", max_retries=0)

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "This is raw unescaped text, not JSON {",
                            }
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        with pytest.raises(GeminiError, match="Invalid JSON"):
            client.generate_json("Prompt")


def test_gemini_client_successful_structured_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful structured JSON extraction returns parsed InvoiceExtraction and live label."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-key")
    client = GeminiLLMClient(api_key="mock-key", model_name="gemini-2.5-flash")

    valid_json = (
        '{"payee": "Acme Cloud Services", "account": "vendor-paypal-sandbox-1", '
        '"amount_minor": 2500, "currency": "USD", "due_date": "2026-11-30", '
        '"invoice_number": "INV-2026-001", "purpose": "Cloud Hosting"}'
    )

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": valid_json}]}}]
        }
        mock_post.return_value = mock_resp

        extraction, is_live, label = client.extract_invoice(SAMPLE_INVOICE_A["text"])

        assert is_live is True
        assert label == "LIVE (gemini-2.5-flash)"
        assert extraction.payee == "Acme Cloud Services"
        assert extraction.amount_minor == 2500
        assert extraction.account == "vendor-paypal-sandbox-1"


def test_gemini_client_fallback_status_accuracy_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When an error occurs during extraction, fallback is clearly labelled as RECORDED RUN."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-key")
    client = GeminiLLMClient(api_key="mock-key")

    with patch("httpx.post", side_effect=Exception("Connection reset")):
        extraction, is_live, label = client.extract_invoice(SAMPLE_INVOICE_A["text"])

        assert is_live is False
        assert "RECORDED RUN" in label
        assert "Connection reset" in label or "Provider Error" in label
        assert extraction.amount_minor == 2500


def test_invoice_agent_allow_with_paypal_rail_labels_awaiting_approval(
    test_clock: ClockPort, test_ledger: InMemoryLedgerAdapter
) -> None:
    """When an order is created on PayPal rail, state is clearly marked AWAITING_BUYER_APPROVAL."""
    from app.infrastructure.paypal import PayPalPaymentRailAdapter

    mandate_service = MandateService(clock=test_clock)
    mandate_service.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate-inv-agent-paypal-flow",
            principal_id="principal-corp-1",
            agent_id="agent-invoice-1",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=500_000,
            allowed_payees=["vendor-paypal-sandbox-1"],
            allow_unregistered_payees=False,
            valid_days=30,
        )
    )

    rail = PayPalPaymentRailAdapter(client_id="mock_id", client_secret="mock_secret")
    with (
        patch.object(rail, "validate_configuration", return_value=(True, None)),
        patch.object(
            rail,
            "pay",
            return_value=MagicMock(
                success=True,
                status="RECONCILE",
                transaction_id="ORDER-SANDBOX-7788",
                details={
                    "order_id": "ORDER-SANDBOX-7788",
                    "approval_url": "https://sandbox.paypal.com/checkout",
                },
            ),
        ),
    ):
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
        res = agent.process_invoice(SAMPLE_INVOICE_A["text"], force_fallback=True)

        assert res.decision == "ALLOW"
        assert res.request_state == "AWAITING_BUYER_APPROVAL"
        assert res.payout_id == "ORDER-SANDBOX-7788"
        assert res.payment_rail == "PayPal Sandbox (Orders v2)"
