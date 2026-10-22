"""External failure tests covering PayPal timeout, 5xx, and malformed responses (Manual 56.19)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.domain.models import Money, TransactionIntent
from app.infrastructure.paypal import PayPalPaymentRailAdapter


@pytest.fixture
def sample_intent() -> TransactionIntent:
    return TransactionIntent(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        money=Money(amount_minor=2500, currency="USD"),
        purpose="Monthly cloud infrastructure subscription",
        idempotency_key="tx-fail-test-001",
        occurred_at_utc=datetime.now(UTC),
    )


def test_paypal_network_timeout_returns_safe_failure(sample_intent: TransactionIntent) -> None:
    """Manual 56.19: Network timeout does not crash application or release budget erroneously."""
    adapter = PayPalPaymentRailAdapter()

    with (
        patch.object(adapter, "_get_access_token", return_value="fake_access_token"),
        patch("httpx.post", side_effect=httpx.TimeoutException("Connection timed out")),
    ):
        result = adapter.pay(sample_intent)

        assert result.success is False
        assert result.status == "PAYOUT_EXCEPTION"
        assert "timed out" in str(result.details.get("error", "")).lower()


def test_paypal_5xx_server_error_returns_safe_failure(sample_intent: TransactionIntent) -> None:
    """Manual 56.19: PayPal 500/503 HTTP server error returns standardized failure."""
    adapter = PayPalPaymentRailAdapter()

    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable: Downstream PayPal gateway timeout"

    with (
        patch.object(adapter, "_get_access_token", return_value="fake_access_token"),
        patch("httpx.post", return_value=mock_resp),
    ):
        result = adapter.pay(sample_intent)

        assert result.success is False
        assert result.status == "PAYOUT_REJECTED"
        assert "Service Unavailable" in str(result.details.get("error", ""))


def test_paypal_malformed_json_response_handled_gracefully(
    sample_intent: TransactionIntent,
) -> None:
    """Manual 56.19: Malformed/non-JSON response from PayPal is caught safely."""
    adapter = PayPalPaymentRailAdapter()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")

    with (
        patch.object(adapter, "_get_access_token", return_value="fake_access_token"),
        patch("httpx.post", return_value=mock_resp),
    ):
        result = adapter.pay(sample_intent)

        assert result.success is False
        assert result.status == "PAYOUT_EXCEPTION"
        assert "expecting value" in str(result.details.get("error", "")).lower()
