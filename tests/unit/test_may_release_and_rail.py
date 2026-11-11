"""Unit tests for may_release helper and release sites across services and paypal.py."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.application.dtos import AuthorizeTransactionCommand
from app.application.services import AuthorizationService, MandateService
from app.domain.models import Money, TransactionIntent
from app.domain.ports import ClockPort, PaymentResult, may_release
from app.domain.state_machine import RequestState
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.paypal import FakePaymentRail, PayPalPaymentRailAdapter


def test_may_release_predicate() -> None:
    """may_release returns True ONLY when business_rejection is True."""
    assert may_release(None) is False

    res_no_rej = PaymentResult(
        success=False,
        transaction_id="tx_1",
        status="FAILED",
        details={},
        business_rejection=False,
    )
    assert may_release(res_no_rej) is False

    res_rej = PaymentResult(
        success=False,
        transaction_id="tx_2",
        status="FAILED",
        details={},
        business_rejection=True,
    )
    assert may_release(res_rej) is True

    # Details fallback
    res_details_rej = PaymentResult(
        success=False,
        transaction_id="tx_3",
        status="FAILED",
        details={"business_rejection": True},
        business_rejection=False,
    )
    assert may_release(res_details_rej) is True


def test_release_site_capture_order(
    test_clock: ClockPort,
    test_ledger: InMemoryLedgerAdapter,
    test_mandate_service: MandateService,
) -> None:
    """Site 1: capture_order releases ONLY when business_rejection is True."""
    # 1. capture failure with business_rejection=False (e.g. 500 or timeout) must NOT release
    rail_ambig = FakePaymentRail(should_succeed=False, status="FAILED", business_rejection=False)
    authz1 = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=rail_ambig,
    )
    req_id = "req_cap_test_1"
    authz1._held_reservations[req_id] = {
        "request_id": req_id,
        "agent_id": "agent-auto-1",
        "amount_minor": 1500,
        "payout_id": "order_123",
        "state": RequestState.RECONCILE.value,
    }
    authz1._request_states[req_id] = RequestState.RECONCILE
    res1 = authz1.capture_order("order_123", req_id)
    assert res1.success is False
    assert req_id in authz1._held_reservations, "Must NOT release on ambiguous capture failure"
    assert authz1.get_request_state(req_id) != RequestState.FAILED

    # 2. capture failure with business_rejection=True releases the reservation
    rail_rej = FakePaymentRail(should_succeed=False, status="FAILED", business_rejection=True)
    authz2 = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=rail_rej,
    )
    req_id2 = "req_cap_test_2"
    authz2._held_reservations[req_id2] = {
        "request_id": req_id2,
        "agent_id": "agent-auto-1",
        "amount_minor": 1500,
        "payout_id": "order_456",
        "state": RequestState.RECONCILE.value,
    }
    authz2._request_states[req_id2] = RequestState.RECONCILE
    res2 = authz2.capture_order("order_456", req_id2)
    assert res2.success is False
    assert req_id2 not in authz2._held_reservations, "Must release on confirmed business rejection"
    assert authz2.get_request_state(req_id2) == RequestState.FAILED


def test_release_site_authorize(
    test_clock: ClockPort,
    test_ledger: InMemoryLedgerAdapter,
    test_mandate_service: MandateService,
) -> None:
    """Site 2: authorize releases directly ONLY when business_rejection is True."""
    # Ambiguous failure (business_rejection=False) moves to RECONCILE and holds reservation
    rail_ambig = FakePaymentRail(should_succeed=False, status="FAILED", business_rejection=False)
    authz = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=rail_ambig,
    )
    cmd = AuthorizeTransactionCommand(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=1000,
        currency="USD",
        purpose="Auth fail test",
        idempotency_key="k_auth_fail_1",
    )
    resp_ambig = authz.authorize(cmd)
    assert resp_ambig.request_state == RequestState.RECONCILE
    assert resp_ambig.request_id in authz._held_reservations

    # Confirmed business rejection (business_rejection=True) releases reservation
    rail_rej = FakePaymentRail(should_succeed=False, status="FAILED", business_rejection=True)
    authz_rej = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=rail_rej,
    )
    cmd2 = AuthorizeTransactionCommand(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=1000,
        currency="USD",
        purpose="Auth fail test 2",
        idempotency_key="k_auth_fail_2",
    )
    resp_rej = authz_rej.authorize(cmd2)
    assert resp_rej.request_state == RequestState.FAILED
    assert resp_rej.request_id not in authz_rej._held_reservations


def test_release_site_reconcile(
    test_clock: ClockPort,
    test_ledger: InMemoryLedgerAdapter,
    test_mandate_service: MandateService,
) -> None:
    """Site 3: reconcile releases reservation ONLY when business_rejection is True."""
    # Lookup returns FAILED with business_rejection=False: does NOT release
    rail_ambig = FakePaymentRail(should_succeed=False, status="FAILED", business_rejection=False)
    authz = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=rail_ambig,
    )
    req_id = "req_recon_test_1"
    authz._held_reservations[req_id] = {
        "request_id": req_id,
        "agent_id": "agent-auto-1",
        "amount_minor": 1500,
        "payout_id": "tx_recon_1",
        "state": RequestState.RECONCILE.value,
    }
    authz._request_states[req_id] = RequestState.RECONCILE
    st1 = authz.reconcile(req_id)
    assert st1 in (RequestState.RECONCILE, RequestState.NEEDS_REVIEW)
    assert req_id in authz._held_reservations

    # Lookup returns FAILED with business_rejection=True: releases reservation
    rail_rej = FakePaymentRail(should_succeed=False, status="FAILED", business_rejection=True)
    authz2 = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=rail_rej,
    )
    req_id2 = "req_recon_test_2"
    authz2._held_reservations[req_id2] = {
        "request_id": req_id2,
        "agent_id": "agent-auto-1",
        "amount_minor": 1500,
        "payout_id": "tx_recon_2",
        "state": RequestState.RECONCILE.value,
    }
    authz2._request_states[req_id2] = RequestState.RECONCILE
    st2 = authz2.reconcile(req_id2)
    assert st2 == RequestState.FAILED
    assert req_id2 not in authz2._held_reservations


def test_release_site_resolve_needs_review(
    test_clock: ClockPort,
    test_ledger: InMemoryLedgerAdapter,
    test_mandate_service: MandateService,
) -> None:
    """Site 4: resolve_needs_review releases reservation ONLY when business_rejection is True."""
    # 1. MARK_FAILED refused when lookup returns business_rejection=False
    rail_ambig = FakePaymentRail(should_succeed=False, status="FAILED", business_rejection=False)
    authz = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=rail_ambig,
    )
    req_id = "req_nr_test_1"
    authz._held_reservations[req_id] = {
        "request_id": req_id,
        "agent_id": "agent-auto-1",
        "amount_minor": 1500,
        "payout_id": "tx_nr_1",
        "state": RequestState.NEEDS_REVIEW.value,
    }
    authz._request_states[req_id] = RequestState.NEEDS_REVIEW
    with pytest.raises(ValueError, match="not a confirmed business rejection"):
        authz.resolve_needs_review(req_id, action="MARK_FAILED")

    # 2. MARK_FAILED succeeds and releases when lookup returns business_rejection=True
    rail_rej = FakePaymentRail(should_succeed=False, status="FAILED", business_rejection=True)
    authz2 = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=rail_rej,
    )
    req_id2 = "req_nr_test_2"
    authz2._held_reservations[req_id2] = {
        "request_id": req_id2,
        "agent_id": "agent-auto-1",
        "amount_minor": 1500,
        "payout_id": "tx_nr_2",
        "state": RequestState.NEEDS_REVIEW.value,
    }
    authz2._request_states[req_id2] = RequestState.NEEDS_REVIEW
    st = authz2.resolve_needs_review(req_id2, action="MARK_FAILED")
    assert st == RequestState.FAILED
    assert req_id2 not in authz2._held_reservations


def test_paypal_lookup_and_capture_error_classification() -> None:
    """paypal.py: capture_order and lookup return RECONCILE/LOOKUP_FAILED on error."""
    adapter = PayPalPaymentRailAdapter(client_id=None, client_secret=None)

    # 1. Missing credentials: lookup returns LOOKUP_FAILED with business_rejection=False
    with patch.object(adapter, "_get_access_token", return_value=None):
        lookup_token_err = adapter.lookup("tx_nonexistent")
        assert lookup_token_err.status in ("LOOKUP_FAILED", "RECONCILE")
        assert lookup_token_err.business_rejection is False

    # 2. Missing credentials: capture_order returns RECONCILE with business_rejection=False
    with patch.object(adapter, "_get_access_token", return_value=None):
        cap_token_err = adapter.capture_order("order_nonexistent")
        assert cap_token_err.status == "RECONCILE"
        assert cap_token_err.business_rejection is False

    # 3. HTTP 500 error on lookup: returns LOOKUP_FAILED with business_rejection=False
    with (
        patch.object(adapter, "_get_access_token", return_value="fake_token"),
        patch("httpx.get") as mock_get,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = '{"error": "Internal Server Error"}'
        mock_get.return_value = mock_resp

        res_500 = adapter.lookup("tx_500")
        assert res_500.status in ("LOOKUP_FAILED", "RECONCILE")
        assert res_500.business_rejection is False

    # 4. HTTP 500 error on capture_order: returns RECONCILE with business_rejection=False
    with (
        patch.object(adapter, "_get_access_token", return_value="fake_token"),
        patch("httpx.post") as mock_post,
    ):
        mock_resp_post = MagicMock()
        mock_resp_post.status_code = 503
        mock_resp_post.text = '{"error": "Service Unavailable"}'
        mock_post.return_value = mock_resp_post

        res_cap_503 = adapter.capture_order("order_503")
        assert res_cap_503.status == "RECONCILE"
        assert res_cap_503.business_rejection is False


def test_wrong_oauth_secret_returns_503_before_reservation(
    test_clock: ClockPort,
    test_ledger: InMemoryLedgerAdapter,
    test_mandate_service: MandateService,
) -> None:
    """Wrong OAuth secret or 401 response aborts with 503 before any reservation."""
    from fastapi import HTTPException

    adapter = PayPalPaymentRailAdapter(client_id="bad_client", client_secret="bad_secret")

    with patch("httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = (
            '{"error": "invalid_client", "error_description": "Client Authentication failed"}'
        )
        mock_post.return_value = mock_resp

        auth_svc = AuthorizationService(
            clock=test_clock,
            ledger=test_ledger,
            mandate_service=test_mandate_service,
            payment_rail=adapter,
        )

        cmd = AuthorizeTransactionCommand(
            agent_id="agent-auto-1",
            recipient_id="vendor-paypal-sandbox-1",
            amount_minor=2500,
            currency="USD",
            purpose="Compute hosting",
            idempotency_key="idem_auth_cfg_err_1",
        )

        with pytest.raises(HTTPException) as exc_info:
            auth_svc.authorize(cmd)

        assert exc_info.value.status_code == 503
        assert "invalid credentials" in exc_info.value.detail.lower()
        # Verify no budget or rolling spent was reserved
        assert auth_svc._rolling_spent.get("agent-auto-1", 0) == 0
        assert auth_svc._lifetime_spent.get("agent-auto-1", 0) == 0


def test_duplicate_order_replay_does_not_create_duplicate_order(
    test_clock: ClockPort,
    test_ledger: InMemoryLedgerAdapter,
    test_mandate_service: MandateService,
) -> None:
    """Duplicate order replay returns cached decision without creating a duplicate payment."""
    from app.domain.policy import PolicyReasonCode

    fake_rail = FakePaymentRail(should_succeed=True, status="COMPLETED")
    auth_svc = AuthorizationService(
        clock=test_clock,
        ledger=test_ledger,
        mandate_service=test_mandate_service,
        payment_rail=fake_rail,
    )

    cmd = AuthorizeTransactionCommand(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        amount_minor=2500,
        currency="USD",
        purpose="Cloud GPU instance",
        idempotency_key="idem_replay_test_99",
    )

    # First call: executes payment
    resp1 = auth_svc.authorize(cmd)
    assert resp1.decision.value == "ALLOW"
    assert len(fake_rail.dispatched_payments) == 1
    spent_after_call1 = auth_svc._rolling_spent.get("agent-auto-1", 0)
    assert spent_after_call1 == 2500

    # Second call (replay with exact same idempotency_key): cached decision, no dual payment
    resp2 = auth_svc.authorize(cmd)
    assert resp2.decision.value == "ALLOW"
    assert PolicyReasonCode.IDEMPOTENCY_REPLAY in resp2.reason_codes
    assert len(fake_rail.dispatched_payments) == 1  # No duplicate payment dispatched
    assert (
        auth_svc._rolling_spent.get("agent-auto-1", 0) == spent_after_call1
    )  # No double reservation


def test_unknown_id_lookup_holds() -> None:
    """Lookup of unknown order ID (404/not found) strictly holds and never releases."""
    from app.domain.money_outcome import MoneyOutcome, money_outcome

    adapter = PayPalPaymentRailAdapter(client_id="test_id", client_secret="test_secret")

    with (
        patch.object(adapter, "_get_access_token", return_value="valid_mock_token"),
        patch("httpx.get") as mock_get,
    ):
        mock_404 = MagicMock()
        mock_404.status_code = 404
        mock_404.text = (
            '{"name": "RESOURCE_NOT_FOUND", "message": "The specified resource does not exist."}'
        )
        mock_get.return_value = mock_404

        lookup_res = adapter.lookup("unknown_order_resource_id_404")

        # Unknown ID must classify as LOOKUP_FAILED with business_rejection=False
        assert lookup_res.status in ("LOOKUP_FAILED", "RECONCILE")
        assert lookup_res.business_rejection is False

        # may_release helper must reject release
        assert may_release(lookup_res) is False

        # money_outcome must strictly HOLD
        outcome = money_outcome(
            source="reconcile",
            provider_status=lookup_res.status,
            business_rejection=lookup_res.business_rejection,
        )
        assert outcome == MoneyOutcome.HOLD


@pytest.mark.parametrize("status_code", [401, 403, 408, 429, 500, 502, 503, 504])
def test_pay_http_codes_401_403_408_429_5xx_hold(status_code: int) -> None:
    """In pay(), HTTP status codes 401, 403, 408, 429, and 5xx must hold
    and never set business_rejection=True.
    """
    adapter = PayPalPaymentRailAdapter(client_id="test_id", client_secret="test_secret")
    intent = TransactionIntent(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        money=Money(amount_minor=5000, currency="USD"),
        purpose="Test transient error holding",
        idempotency_key="idemp_transient_hold_1",
        occurred_at_utc=datetime.now(UTC),
    )

    with (
        patch.object(adapter, "_get_access_token", return_value="mock_valid_token"),
        patch("httpx.post") as mock_post,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = f'{{"error": "HTTP {status_code} Error"}}'
        mock_post.return_value = mock_resp

        # For 403, pay() falls back to Orders v2; mock_post will be called on Orders v2
        res = adapter.pay(intent)
        assert res.status == "RECONCILE"
        assert res.business_rejection is False
        assert may_release(res) is False


def test_orders_v2_return_and_cancel_urls_use_public_base_url() -> None:
    """PayPal return_url and cancel_url must come from PUBLIC_BASE_URL setting, never localhost."""
    from app.infrastructure.config import settings

    adapter = PayPalPaymentRailAdapter(client_id="test_id", client_secret="test_secret")
    intent = TransactionIntent(
        agent_id="agent-auto-1",
        recipient_id="vendor-paypal-sandbox-1",
        money=Money(amount_minor=5000, currency="USD"),
        purpose="Test return_url configuration",
        idempotency_key="idemp_url_check_1",
        occurred_at_utc=datetime.now(UTC),
    )

    captured_payload: dict[str, Any] = {}

    def capture_post(_url: str, **kwargs: Any) -> MagicMock:
        nonlocal captured_payload
        captured_payload = kwargs.get("json", {})
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {
            "id": "ORD-TEST-URL",
            "status": "CREATED",
            "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/checkout"}],
        }
        return resp

    with (
        patch.object(adapter, "_get_access_token", return_value="mock_valid_token"),
        patch.object(settings, "public_base_url", "https://phalanx-nrxk.onrender.com"),
        patch("httpx.post", side_effect=capture_post),
    ):
        adapter._orders_v2_fallback(intent, "mock_valid_token", "req_test_urls")

        app_ctx = captured_payload.get("application_context", {})
        return_url = app_ctx.get("return_url", "")
        cancel_url = app_ctx.get("cancel_url", "")

        assert "https://phalanx-nrxk.onrender.com" in return_url
        assert "https://phalanx-nrxk.onrender.com" in cancel_url
        assert "localhost" not in return_url
        assert "localhost" not in cancel_url
        assert "127.0.0.1" not in return_url
        assert "127.0.0.1" not in cancel_url


def test_404_lookup_before_10_minutes_holds_and_after_releases() -> None:
    """A 404 from lookup holds if age < 10m (600s), but counts as confirmed failure after 10m."""
    from app.application.services import AuthorizationService, MandateService
    from app.domain.state_machine import RequestState
    from app.infrastructure.ledger import InMemoryLedgerAdapter

    class SimpleClock(ClockPort):
        def __init__(self, t: datetime):
            self._t = t

        def now_utc(self) -> datetime:
            return self._t

        def advance(self, seconds: int) -> None:
            self._t += timedelta(seconds=seconds)

    clock = SimpleClock(datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC))
    rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    auth_svc = AuthorizationService(
        clock=clock,
        ledger=InMemoryLedgerAdapter(),
        mandate_service=MandateService(clock=clock),
        payment_rail=rail,
    )

    req_id = "req_404_age_test"
    auth_svc._request_states[req_id] = RequestState.RECONCILE
    auth_svc._held_reservations[req_id] = {
        "state": RequestState.RECONCILE.value,
        "payout_id": "tx_404_not_found",
        "agent_id": "agent-auto-1",
        "amount_minor": 5000,
        "created_at_utc": clock.now_utc(),
    }

    # Configure rail lookup to return 404 Not Found
    rail.set_lookup_result(
        "tx_404_not_found",
        PaymentResult(
            success=False,
            transaction_id="tx_404_not_found",
            status="LOOKUP_FAILED",
            details={
                "http_status": 404,
                "name": "RESOURCE_NOT_FOUND",
                "message": "Resource not found",
            },
            business_rejection=False,
        ),
    )

    # 1. Under 10 minutes (age = 60s): 404 must hold in RECONCILE
    clock.advance(seconds=60)
    st_under = auth_svc.reconcile(req_id)
    assert st_under == RequestState.RECONCILE
    assert auth_svc.get_request_state(req_id) == RequestState.RECONCILE

    # 2. Over 10 minutes (age = 660s): 404 counts as FAILED and releases
    clock.advance(seconds=600)
    st_over = auth_svc.reconcile(req_id)
    assert st_over == RequestState.FAILED
    assert auth_svc.get_request_state(req_id) == RequestState.FAILED


def test_resolve_needs_review_mark_failed_404_age_guard() -> None:
    """resolve_needs_review MARK_FAILED refuses on 404 if age < 10m, releases if age >= 10m."""
    from app.application.services import AuthorizationService, MandateService
    from app.domain.state_machine import RequestState
    from app.infrastructure.ledger import InMemoryLedgerAdapter

    class SimpleClock(ClockPort):
        def __init__(self, t: datetime):
            self._t = t

        def now_utc(self) -> datetime:
            return self._t

        def advance(self, seconds: int) -> None:
            self._t += timedelta(seconds=seconds)

    clock = SimpleClock(datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC))
    rail = FakePaymentRail(should_succeed=True, status="RECONCILE")
    auth_svc = AuthorizationService(
        clock=clock,
        ledger=InMemoryLedgerAdapter(),
        mandate_service=MandateService(clock=clock),
        payment_rail=rail,
    )

    req_id = "req_rnr_404_test"
    auth_svc._request_states[req_id] = RequestState.NEEDS_REVIEW
    auth_svc._held_reservations[req_id] = {
        "state": RequestState.NEEDS_REVIEW.value,
        "payout_id": "tx_rnr_404",
        "agent_id": "agent-auto-1",
        "amount_minor": 5000,
        "created_at_utc": clock.now_utc(),
    }

    rail.set_lookup_result(
        "tx_rnr_404",
        PaymentResult(
            success=False,
            transaction_id="tx_rnr_404",
            status="NOT_FOUND",
            details={
                "http_status": 404,
                "name": "RESOURCE_NOT_FOUND",
            },
            business_rejection=True,
        ),
    )

    # 1. Under 10 minutes (age = 60s): MARK_FAILED must be refused due to potential replication lag
    clock.advance(seconds=60)
    with pytest.raises(ValueError, match="10 minutes|replication lag|cannot confirm failure"):
        auth_svc.resolve_needs_review(req_id, action="MARK_FAILED")

    # 2. Over 10 minutes (age = 660s): MARK_FAILED succeeds and releases
    clock.advance(seconds=600)
    st = auth_svc.resolve_needs_review(req_id, action="MARK_FAILED")
    assert st == RequestState.FAILED
    assert auth_svc.get_request_state(req_id) == RequestState.FAILED
