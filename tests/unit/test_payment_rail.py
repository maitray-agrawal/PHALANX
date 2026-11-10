"""Unit tests for PaymentRail protocol, FakePaymentRail, and PayPalPaymentRailAdapter."""

from datetime import UTC, datetime

import pytest

from app.domain.models import Money, TransactionIntent
from app.domain.ports import PaymentRail
from app.infrastructure.paypal import FakePaymentRail, PayPalPaymentRailAdapter


def test_fake_payment_rail_records_dispatch() -> None:
    rail = FakePaymentRail(should_succeed=True)
    assert isinstance(rail, PaymentRail)

    intent = TransactionIntent(
        agent_id="agent-01",
        recipient_id="vendor-01",
        money=Money(amount_minor=5000, currency="USD"),
        purpose="Server subscription",
        idempotency_key="idemp-rail-001",
        occurred_at_utc=datetime.now(UTC),
    )

    res = rail.pay(intent)
    assert res.success is True
    assert res.transaction_id.startswith("sandbox_tx_")
    assert res.status == "COMPLETED"
    assert len(rail.dispatched_payments) == 1
    assert rail.dispatched_payments[0] == intent

    lookup_res = rail.lookup(res.transaction_id)
    assert lookup_res.success is True
    assert lookup_res.transaction_id == res.transaction_id


def test_fake_payment_rail_simulates_failure() -> None:
    rail = FakePaymentRail(should_succeed=False)
    intent = TransactionIntent(
        agent_id="agent-01",
        recipient_id="vendor-01",
        money=Money(amount_minor=5000, currency="USD"),
        purpose="Server subscription",
        idempotency_key="idemp-rail-002",
        occurred_at_utc=datetime.now(UTC),
    )
    res = rail.pay(intent)
    assert res.success is False
    assert res.status == "FAILED"
    assert "simulated_rail_failure" in rail.normalize_error(res.details)


def test_paypal_adapter_unconfigured_credentials_rejected(monkeypatch) -> None:
    adapter = PayPalPaymentRailAdapter()
    monkeypatch.setattr(adapter, "_get_access_token", lambda: None)
    assert isinstance(adapter, PaymentRail)

    intent = TransactionIntent(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        money=Money(amount_minor=1200, currency="USD"),
        purpose="Operational cloud hosting renewal",
        idempotency_key="idemp-rail-003",
        occurred_at_utc=datetime.now(UTC),
    )

    # When live env is unconfigured, adapter returns explicit error (no silent simulation)
    res = adapter.pay(intent)
    assert res.success is False
    assert res.transaction_id == ""
    assert res.status == "FAILED"
    assert "credentials missing" in res.details.get("error", "").lower()


def test_paypal_adapter_lookup_simulation_when_no_token(monkeypatch) -> None:
    adapter = PayPalPaymentRailAdapter()
    monkeypatch.setattr(adapter, "_get_access_token", lambda: "")
    res = adapter.lookup("mock-tx-12345")
    assert res.success is False
    assert res.status in ("LOOKUP_FAILED", "RECONCILE")
    assert res.business_rejection is False
    assert "credentials missing" in res.details.get("error", "").lower()


def test_paypal_adapter_lookup_order_fallback_mocked(monkeypatch) -> None:
    adapter = PayPalPaymentRailAdapter()
    monkeypatch.setattr(adapter, "_get_access_token", lambda: "fake-jwt-token")

    class FakePayoutResponse:
        status_code = 404
        text = '{"name":"INVALID_RESOURCE_ID","message":"Not found"}'

    class FakeOrderResponse:
        status_code = 200
        text = '{"id":"ORDER-999","status":"APPROVED"}'

        def json(self):
            return {"id": "ORDER-999", "status": "APPROVED"}

    def fake_get(url: str, **kwargs: object) -> object:
        _ = kwargs
        if "payouts" in url:
            return FakePayoutResponse()
        if "orders" in url:
            return FakeOrderResponse()
        raise ValueError(f"Unexpected url {url}")

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)
    res = adapter.lookup("ORDER-999")
    assert res.success is True
    assert res.transaction_id == "ORDER-999"
    assert res.status == "APPROVED"


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
def test_paypal_pay_ambiguous_and_transient_statuses_route_to_reconcile(
    monkeypatch, status_code: int
) -> None:
    """408, 429 and 5xx must hold funds and route to RECONCILE, never FAILED."""
    import httpx

    adapter = PayPalPaymentRailAdapter()
    monkeypatch.setattr(adapter, "_get_access_token", lambda: "fake-jwt-token")

    class FakeResponse:
        def __init__(self, sc: int):
            self.status_code = sc
            self.text = f'{{"error": "Simulated {sc}"}}'

        def json(self):
            return {"error": f"Simulated {self.status_code}"}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: FakeResponse(status_code))

    intent = TransactionIntent(
        agent_id="agent-01",
        recipient_id="vendor-01",
        money=Money(amount_minor=5000, currency="USD"),
        purpose="Subscription",
        idempotency_key=f"idemp-status-{status_code}",
        occurred_at_utc=datetime.now(UTC),
    )
    res = adapter.pay(intent)
    assert res.status == "RECONCILE"
    assert res.details.get("business_rejection") is False


@pytest.mark.parametrize("status_code", [400, 422])
def test_paypal_pay_explicit_provider_rejection_releases(monkeypatch, status_code: int) -> None:
    """Explicit 4xx business rejections (400, 422) return FAILED with business_rejection=True."""
    import httpx

    adapter = PayPalPaymentRailAdapter()
    monkeypatch.setattr(adapter, "_get_access_token", lambda: "fake-jwt-token")

    class FakeResponse:
        def __init__(self, sc: int):
            self.status_code = sc
            self.text = f'{{"error": "Simulated {sc}"}}'

        def json(self):
            return {"error": f"Simulated {self.status_code}"}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: FakeResponse(status_code))

    intent = TransactionIntent(
        agent_id="agent-01",
        recipient_id="vendor-01",
        money=Money(amount_minor=5000, currency="USD"),
        purpose="Subscription",
        idempotency_key=f"idemp-fail-{status_code}",
        occurred_at_utc=datetime.now(UTC),
    )
    res = adapter.pay(intent)
    assert res.status == "FAILED"
    assert res.details.get("business_rejection") is True


def test_real_verify_webhook_rejects_forged_headers(monkeypatch) -> None:
    """Real PayPalPaymentRailAdapter.verify_webhook must reject forged headers and signatures."""
    adapter = PayPalPaymentRailAdapter(client_id="test_client_id", client_secret="test_secret")
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-VALID-12345")
    monkeypatch.setattr(adapter, "_get_access_token", lambda: "fake-access-token")

    valid_payload = b'{"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'

    # 1. Forged cert URL with attacker domain (SSRF attempt)
    forged_cert_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://attacker.evil.com/certs/CERT-1",
        "PAYPAL-TRANSMISSION-ID": "trans-1",
        "PAYPAL-TRANSMISSION-SIG": "forged_sig",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-09T12:00:00Z",
    }
    assert adapter.verify_webhook(forged_cert_headers, valid_payload) is False

    # 2. Insecure non-HTTPS cert URL
    insecure_cert_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "http://api-m.sandbox.paypal.com/certs/CERT-1",
        "PAYPAL-TRANSMISSION-ID": "trans-2",
        "PAYPAL-TRANSMISSION-SIG": "forged_sig",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-09T12:00:00Z",
    }
    assert adapter.verify_webhook(insecure_cert_headers, valid_payload) is False

    # 3. Userinfo spoofing cert URL (e.g. evil.com@api.paypal.com)
    userinfo_cert_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api.paypal.com@attacker.com/cert.pem",
        "PAYPAL-TRANSMISSION-ID": "trans-3",
        "PAYPAL-TRANSMISSION-SIG": "forged_sig",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-09T12:00:00Z",
    }
    assert adapter.verify_webhook(userinfo_cert_headers, valid_payload) is False

    # 4. Missing required headers
    missing_sig_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api-m.sandbox.paypal.com/certs/CERT-1",
        "PAYPAL-TRANSMISSION-ID": "trans-4",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-09T12:00:00Z",
    }
    assert adapter.verify_webhook(missing_sig_headers, valid_payload) is False

    # 5. Legitimate PayPal cert host, but forged signature returned as FAILURE by PayPal API
    forged_sig_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api-m.sandbox.paypal.com/certs/CERT-1",
        "PAYPAL-TRANSMISSION-ID": "trans-5",
        "PAYPAL-TRANSMISSION-SIG": "forged_signature_token_abc123",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-09T12:00:00Z",
    }

    class FakeVerificationResponse:
        status_code = 200

        def json(self):
            return {"verification_status": "FAILURE"}

    import httpx

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: FakeVerificationResponse())
    assert adapter.verify_webhook(forged_sig_headers, valid_payload) is False

    # 6. PayPal API returns 400 Bad Request on forged parameters
    class Fake400Response:
        status_code = 400

        def json(self):
            return {"error": "INVALID_SIGNATURE"}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: Fake400Response())
    assert adapter.verify_webhook(forged_sig_headers, valid_payload) is False


def test_real_verify_webhook_accepts_valid_signature_with_provider_success(monkeypatch) -> None:
    """Real PayPalPaymentRailAdapter.verify_webhook returns True on provider SUCCESS."""
    adapter = PayPalPaymentRailAdapter(client_id="test_client_id", client_secret="test_secret")
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-VALID-12345")
    monkeypatch.setattr(adapter, "_get_access_token", lambda: "fake-access-token")

    valid_payload = b'{"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
    valid_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api-m.sandbox.paypal.com/certs/CERT-1",
        "PAYPAL-TRANSMISSION-ID": "trans-valid-123",
        "PAYPAL-TRANSMISSION-SIG": "valid_signature_token_xyz",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-09T12:00:00Z",
    }

    class FakeSuccessResponse:
        status_code = 200

        def json(self):
            return {"verification_status": "SUCCESS"}

    import httpx

    captured_requests = []

    def mock_post(url: str, **kwargs: object) -> object:
        captured_requests.append((url, kwargs))
        return FakeSuccessResponse()

    monkeypatch.setattr(httpx, "post", mock_post)

    assert adapter.verify_webhook(valid_headers, valid_payload) is True
    assert len(captured_requests) == 1
    assert "/v1/notifications/verify-webhook-signature" in captured_requests[0][0]
    payload_sent = captured_requests[0][1].get("json", {})
    assert payload_sent["webhook_id"] == "WH-VALID-12345"
    assert payload_sent["transmission_sig"] == "valid_signature_token_xyz"


def test_webhook_cert_url_strict_validation_rejections_and_accept(monkeypatch) -> None:
    """H8: webhook cert URL must be HTTPS, exactly in allowed PayPal hosts, no userinfo, no port."""
    adapter = PayPalPaymentRailAdapter(client_id="test_client_id", client_secret="test_secret")
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-VALID-12345")
    monkeypatch.setattr(adapter, "_get_access_token", lambda: "fake-access-token")

    class FakeSuccessResponse:
        status_code = 200

        def json(self):
            return {"verification_status": "SUCCESS"}

    import httpx

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: FakeSuccessResponse())

    payload = b'{"id": "WH-1"}'
    base_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-TRANSMISSION-ID": "trans-test",
        "PAYPAL-TRANSMISSION-SIG": "sig-test",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-09T12:00:00Z",
    }

    # Rejection 1: HTTP instead of HTTPS
    h1 = dict(base_headers, **{"PAYPAL-CERT-URL": "http://api.paypal.com/certs/CERT-1"})
    assert adapter.verify_webhook(h1, payload) is False

    # Rejection 2: Suffix domain (evilpaypal.com)
    h2 = dict(base_headers, **{"PAYPAL-CERT-URL": "https://evilpaypal.com/certs/CERT-1"})
    assert adapter.verify_webhook(h2, payload) is False

    # Rejection 3: Subdomain suffix evasion (api.paypal.com.evil.com)
    h3 = dict(base_headers, **{"PAYPAL-CERT-URL": "https://api.paypal.com.evil.com/certs/CERT-1"})
    assert adapter.verify_webhook(h3, payload) is False

    # Rejection 4: Arbitrary unlisted PayPal subdomain (attacker.paypal.com)
    h4 = dict(base_headers, **{"PAYPAL-CERT-URL": "https://attacker.paypal.com/certs/CERT-1"})
    assert adapter.verify_webhook(h4, payload) is False

    # Rejection 5: Username in URL
    h5 = dict(base_headers, **{"PAYPAL-CERT-URL": "https://attacker@api.paypal.com/certs/CERT-1"})
    assert adapter.verify_webhook(h5, payload) is False

    # Rejection 6: Username + password in URL
    h6 = dict(
        base_headers,
        **{"PAYPAL-CERT-URL": "https://user:pass@api.sandbox.paypal.com/certs/CERT-1"},
    )
    assert adapter.verify_webhook(h6, payload) is False

    # Rejection 7: Explicit port (standard 443 or custom 8443)
    h7a = dict(base_headers, **{"PAYPAL-CERT-URL": "https://api.paypal.com:443/certs/CERT-1"})
    assert adapter.verify_webhook(h7a, payload) is False
    h7b = dict(
        base_headers,
        **{"PAYPAL-CERT-URL": "https://api.sandbox.paypal.com:8443/certs/CERT-1"},
    )
    assert adapter.verify_webhook(h7b, payload) is False

    # Accept: Legitimate HTTPS PayPal cert with no userinfo or port
    h_accept = dict(
        base_headers,
        **{"PAYPAL-CERT-URL": "https://api-m.sandbox.paypal.com/certs/CERT-1"},
    )
    assert adapter.verify_webhook(h_accept, payload) is True
