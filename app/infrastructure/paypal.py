"""PayPal Sandbox Rail Adapter & Recording Test Double.

Implements the PaymentRail port from app/domain/ports.py.
Handles Route A (Payouts v1) with Orders v2 fallback trigger,
using PayPal-Request-Id for idempotency.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.domain.models import TransactionIntent
from app.domain.ports import PaymentRail, PaymentResult


def load_env_if_present() -> None:
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def validate_paypal_cert_url(cert_url: str) -> bool:
    """Validate PayPal webhook cert URL according to strict security invariants:

    - Scheme must be https (case-insensitive).
    - Hostname must be exactly in the documented PayPal API hosts:
      {api.paypal.com, api.sandbox.paypal.com, api-m.paypal.com, api-m.sandbox.paypal.com}.
    - No username or password (no userinfo allowed).
    - No explicit port (not even 443; must use standard default HTTPS port).
    """
    if not cert_url or not isinstance(cert_url, str):
        return False
    from urllib.parse import urlparse

    try:
        parsed = urlparse(cert_url)
        if parsed.scheme.lower() != "https":
            return False
        if parsed.username or parsed.password:
            return False
        if parsed.port is not None:
            return False
        hostname = (parsed.hostname or "").lower()
        allowed_hosts = {
            "api.paypal.com",
            "api.sandbox.paypal.com",
            "api-m.paypal.com",
            "api-m.sandbox.paypal.com",
        }
        return hostname in allowed_hosts
    except Exception:
        return False


class FakePaymentRail(PaymentRail):
    """Recording test double for deterministic test execution."""

    def __init__(
        self,
        should_succeed: bool = True,
        status: str = "COMPLETED",
        valid_signatures: set[str] | None = None,
        is_configured: bool = True,
        config_error: str = "",
    ) -> None:
        self.should_succeed = should_succeed
        self.status = status
        self.is_configured = is_configured
        self.config_error = config_error
        self.dispatched_payments: list[TransactionIntent] = []
        self._tx_counter = 0
        self.valid_signatures = (
            valid_signatures
            if valid_signatures is not None
            else {"fixture-valid-test-sig", "valid_mock_signature_test_123"}
        )
        self.lookup_results: dict[str, PaymentResult] = {}

    def set_lookup_result(self, transaction_id: str, result: PaymentResult) -> None:
        self.lookup_results[transaction_id] = result

    def validate_configuration(self) -> tuple[bool, str]:
        if not self.is_configured:
            return (
                False,
                self.config_error or "Payment provider credentials missing or not configured",
            )
        return True, ""

    def pay(self, intent: TransactionIntent) -> PaymentResult:
        self.dispatched_payments.append(intent)
        self._tx_counter += 1
        if self.should_succeed:
            return PaymentResult(
                success=True,
                transaction_id=f"sandbox_tx_{uuid.uuid4().hex[:12]}",
                status=self.status,
                details={"rail": "fake_sandbox", "amount_minor": intent.money.amount_minor},
            )
        return PaymentResult(
            success=False,
            transaction_id="",
            status=self.status if self.status != "COMPLETED" else "FAILED",
            details={"error": "simulated_rail_failure"},
        )

    def lookup(self, transaction_id: str) -> PaymentResult:
        if transaction_id in self.lookup_results:
            return self.lookup_results[transaction_id]
        return PaymentResult(
            success=self.should_succeed,
            transaction_id=transaction_id,
            status=self.status,
            details={"lookup": True},
        )

    def normalize_error(self, raw_error: Any) -> str:
        if isinstance(raw_error, dict):
            return str(
                raw_error.get("error")
                or raw_error.get("message")
                or raw_error.get("name")
                or "Rail execution error"
            )
        return str(raw_error)

    def verify_webhook(self, headers: dict[str, str], body_bytes: bytes) -> bool:
        _ = body_bytes
        sig = (
            headers.get("PAYPAL-TRANSMISSION-SIG")
            or headers.get("paypal-transmission-sig")
            or headers.get("Paypal-Transmission-Sig")
        )
        if not sig:
            return False
        cert_url = (
            headers.get("PAYPAL-CERT-URL")
            or headers.get("paypal-cert-url")
            or headers.get("Paypal-Cert-Url")
        )
        if cert_url and not validate_paypal_cert_url(cert_url):
            return False
        # Only signatures matching stubbed/fixture set are accepted
        return sig in self.valid_signatures

    def capture_order(self, order_id: str, request_id: str | None = None) -> PaymentResult:
        _ = request_id
        if self.should_succeed:
            return PaymentResult(
                success=True,
                transaction_id=order_id,
                status="COMPLETED",
                details={"captured": True, "order_id": order_id, "provider_status": "COMPLETED"},
            )
        return PaymentResult(
            success=False,
            transaction_id=order_id,
            status="FAILED",
            details={"error": "simulated_capture_failure"},
        )


class PayPalPaymentRailAdapter(PaymentRail):
    """Production PayPal Sandbox adapter implementing Route A (Payouts) with Orders fallback."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
    ) -> None:
        load_env_if_present()
        self._client_id = client_id if client_id is not None else os.getenv("PAYPAL_CLIENT_ID")
        self._client_secret = (
            client_secret if client_secret is not None else os.getenv("PAYPAL_CLIENT_SECRET")
        )
        self._base_url = (
            base_url
            if base_url is not None
            else os.getenv("PAYPAL_API_BASE_URL", "https://api-m.sandbox.paypal.com")
        )
        self._counter = 0
        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0

    def validate_configuration(self) -> tuple[bool, str]:
        """Validate PayPal credentials via live OAuth token probe.

        Fails closed on 401, missing keys, or outage.
        Error text never leaks environment variable names.
        """
        if not self._client_id or not self._client_secret:
            return False, "Payment provider credentials missing or not configured"

        url = f"{self._base_url}/v1/oauth2/token"
        try:
            resp = httpx.post(
                url,
                auth=(self._client_id, self._client_secret),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                if token:
                    import time

                    self._cached_token = str(token)
                    self._token_expires_at = time.time() + max(
                        60, data.get("expires_in", 3600) - 120
                    )
                    return True, ""
                return False, "Payment provider authentication response missing token"
            elif resp.status_code == 401:
                return False, "Payment provider authentication failed: invalid credentials"
            else:
                return False, f"Payment provider returned status {resp.status_code}"
        except httpx.TimeoutException:
            return False, "Payment provider service timed out during authentication check"
        except Exception:
            return False, "Payment provider service is unreachable"

    def _get_access_token(self) -> str | None:
        if not self._client_id or not self._client_secret:
            return None
        import time

        now = time.time()
        if self._cached_token and now < self._token_expires_at:
            return self._cached_token
        url = f"{self._base_url}/v1/oauth2/token"
        try:
            resp = httpx.post(
                url,
                auth=(self._client_id, self._client_secret),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                if token:
                    self._cached_token = str(token)
                    self._token_expires_at = now + max(60, data.get("expires_in", 3600) - 120)
                    return self._cached_token
        except Exception:
            return None
        return None

    def pay(self, intent: TransactionIntent) -> PaymentResult:
        token = self._get_access_token()
        if not token:
            return PaymentResult(
                success=False,
                transaction_id="",
                status="FAILED",
                details={"error": "Payment provider credentials missing or not configured"},
            )

        # Derive idempotent PayPal-Request-Id deterministically from intent digest
        from app.application.services import compute_intent_digest

        intent_digest = compute_intent_digest(
            agent_id=intent.agent_id,
            recipient_id=intent.recipient_id,
            amount_minor=intent.money.amount_minor,
            currency=intent.money.currency,
            purpose=intent.purpose,
            idempotency_key=intent.idempotency_key,
        )
        request_id = f"req_{intent_digest[:32]}"

        # Route A: Payouts API
        batch_id = f"batch_{intent_digest[:16]}"
        amount_dollars = f"{intent.money.amount_minor / 100:.2f}"
        receiver_email = (
            intent.recipient_id if "@" in intent.recipient_id else "sandbox-vendor@example.com"
        )

        payout_url = f"{self._base_url}/v1/payments/payouts"
        payload = {
            "sender_batch_header": {
                "sender_batch_id": batch_id,
                "email_subject": f"PHALANX Authorization: {intent.purpose}",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "amount": {"value": amount_dollars, "currency": intent.money.currency},
                    "receiver": receiver_email,
                    "note": intent.purpose[:100],
                    "sender_item_id": intent.idempotency_key[:30],
                }
            ],
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": request_id,
        }

        try:
            resp = httpx.post(payout_url, json=payload, headers=headers, timeout=12.0)
            if resp.status_code in (200, 201):
                data = resp.json()
                batch_header = data.get("batch_header", {})
                payout_batch_id = batch_header.get("payout_batch_id", batch_id)
                raw_batch_status = str(batch_header.get("batch_status", "")).upper()
                if raw_batch_status == "SUCCESS":
                    provider_state = "COMPLETED"
                    is_rejection = False
                elif raw_batch_status in ("PENDING", "PROCESSING"):
                    provider_state = "RECONCILE"
                    is_rejection = False
                elif raw_batch_status in ("DENIED", "CANCELED"):
                    provider_state = "FAILED"
                    is_rejection = True
                else:
                    provider_state = "RECONCILE"
                    is_rejection = False
                data["provider_status"] = provider_state
                data["business_rejection"] = is_rejection
                return PaymentResult(
                    success=(provider_state == "COMPLETED"),
                    transaction_id=payout_batch_id,
                    status=provider_state,
                    details=data,
                )
            # If account lacks Payouts permissions (HTTP 403), trigger Orders v2 fallback
            if resp.status_code == 403:
                return self._orders_v2_fallback(intent, token, request_id)

            if resp.status_code in (408, 429):
                # Rate limit (429) or request timeout (408) is not a final business rejection
                return PaymentResult(
                    success=False,
                    transaction_id="",
                    status="RECONCILE",
                    details={
                        "error": self.normalize_error(resp.text),
                        "http_status": resp.status_code,
                        "business_rejection": False,
                    },
                )
            if 400 <= resp.status_code < 500:
                # 4xx is a definite provider business rejection
                return PaymentResult(
                    success=False,
                    transaction_id="",
                    status="FAILED",
                    details={
                        "error": self.normalize_error(resp.text),
                        "http_status": resp.status_code,
                        "business_rejection": True,
                    },
                )

            # 5xx, timeouts or server errors must route to RECONCILE
            return PaymentResult(
                success=False,
                transaction_id="",
                status="RECONCILE",
                details={
                    "error": self.normalize_error(resp.text),
                    "http_status": resp.status_code,
                    "business_rejection": False,
                },
            )
        except Exception as exc:
            return PaymentResult(
                success=False,
                transaction_id="",
                status="RECONCILE",
                details={"error": self.normalize_error(exc), "business_rejection": False},
            )

    def _orders_v2_fallback(
        self, intent: TransactionIntent, token: str, request_id: str
    ) -> PaymentResult:
        """Fallback to Orders v2 checkout when Payouts capability is unavailable."""
        orders_url = f"{self._base_url}/v2/checkout/orders"
        amount_dollars = f"{intent.money.amount_minor / 100:.2f}"
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": intent.idempotency_key[:30],
                    "amount": {"currency_code": intent.money.currency, "value": amount_dollars},
                    "description": intent.purpose[:120],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": request_id,
        }
        try:
            resp = httpx.post(orders_url, json=payload, headers=headers, timeout=12.0)
            if resp.status_code in (200, 201):
                data = resp.json()
                order_id = data.get("id", "")
                has_buyer_action = any(
                    link.get("rel") in ("payer-action", "approve") for link in data.get("links", [])
                )
                provider_state = "BUYER_APPROVAL_REQUIRED" if has_buyer_action else "ORDER_CREATED"
                data["provider_status"] = provider_state
                data["business_rejection"] = False
                # Never label SETTLED before real sandbox capture
                return PaymentResult(
                    success=True,
                    transaction_id=order_id,
                    status=provider_state,
                    details=data,
                )
            if resp.status_code in (408, 429):
                # Rate limit (429) or request timeout (408) is not a final business rejection
                return PaymentResult(
                    success=False,
                    transaction_id="",
                    status="RECONCILE",
                    details={
                        "error": self.normalize_error(resp.text),
                        "http_status": resp.status_code,
                        "business_rejection": False,
                    },
                )
            if 400 <= resp.status_code < 500:
                # 4xx is a definite provider business rejection
                return PaymentResult(
                    success=False,
                    transaction_id="",
                    status="FAILED",
                    details={
                        "error": self.normalize_error(resp.text),
                        "http_status": resp.status_code,
                        "business_rejection": True,
                    },
                )
            # 5xx, timeouts or server errors must route to RECONCILE
            return PaymentResult(
                success=False,
                transaction_id="",
                status="RECONCILE",
                details={
                    "error": self.normalize_error(resp.text),
                    "http_status": resp.status_code,
                    "business_rejection": False,
                },
            )
        except Exception as exc:
            return PaymentResult(
                success=False,
                transaction_id="",
                status="RECONCILE",
                details={"error": self.normalize_error(exc), "business_rejection": False},
            )

    def lookup(self, transaction_id: str) -> PaymentResult:
        token = self._get_access_token()
        if not token:
            return PaymentResult(
                success=False,
                transaction_id=transaction_id,
                status="FAILED",
                details={"error": "Payment provider credentials missing or not configured"},
            )
        url = f"{self._base_url}/v1/payments/payouts/{transaction_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            resp = httpx.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                raw_batch_status = str(data.get("batch_header", {}).get("batch_status", "")).upper()
                if raw_batch_status == "SUCCESS":
                    provider_state = "COMPLETED"
                elif raw_batch_status in ("DENIED", "CANCELED"):
                    provider_state = "FAILED"
                else:
                    provider_state = "RECONCILE"
                data["provider_status"] = provider_state
                return PaymentResult(
                    success=(provider_state == "COMPLETED"),
                    transaction_id=transaction_id,
                    status=provider_state,
                    details=data,
                )

            # If not found in payouts (e.g. order fallback), query Orders v2 API
            if resp.status_code == 404 or "INVALID_RESOURCE_ID" in resp.text:
                order_url = f"{self._base_url}/v2/checkout/orders/{transaction_id}"
                order_resp = httpx.get(order_url, headers=headers, timeout=10.0)
                if order_resp.status_code == 200:
                    order_data = order_resp.json()
                    raw_status = str(order_data.get("status", "CREATED")).upper()
                    if raw_status == "COMPLETED":
                        provider_state = "COMPLETED"
                    elif raw_status == "APPROVED":
                        provider_state = "APPROVED"
                    elif raw_status == "CREATED":
                        has_action = any(
                            link_item.get("rel") in ("payer-action", "approve")
                            for link_item in order_data.get("links", [])
                        )
                        provider_state = (
                            "BUYER_APPROVAL_REQUIRED" if has_action else "ORDER_CREATED"
                        )
                    elif raw_status == "VOIDED":
                        provider_state = "FAILED"
                    else:
                        provider_state = "RECONCILE"

                    order_data["provider_status"] = provider_state
                    return PaymentResult(
                        success=(
                            provider_state
                            in ("COMPLETED", "APPROVED", "ORDER_CREATED", "BUYER_APPROVAL_REQUIRED")
                        ),
                        transaction_id=transaction_id,
                        status=provider_state,
                        details=order_data,
                    )

            if resp.status_code >= 500 or resp.status_code in (404, 408, 429):
                # 5xx, replication lag 404, request timeout 408, rate limit 429: stay in RECONCILE
                return PaymentResult(
                    success=False,
                    transaction_id=transaction_id,
                    status="RECONCILE",
                    details={
                        "error": self.normalize_error(resp.text),
                        "http_status": resp.status_code,
                        "business_rejection": False,
                    },
                )

            return PaymentResult(
                success=False,
                transaction_id=transaction_id,
                status="FAILED",
                details={
                    "error": self.normalize_error(resp.text),
                    "http_status": resp.status_code,
                    "business_rejection": True,
                },
            )
        except Exception as exc:
            return PaymentResult(
                success=False,
                transaction_id=transaction_id,
                status="RECONCILE",
                details={"error": self.normalize_error(exc)},
            )

    def normalize_error(self, raw_error: Any) -> str:
        if isinstance(raw_error, dict):
            return str(raw_error.get("message") or raw_error.get("name") or "Rail execution error")
        return str(raw_error)

    def capture_order(self, order_id: str, request_id: str | None = None) -> PaymentResult:
        """Capture an approved order on PayPal Orders v2 rail.

        Documentation:
        POST https://api-m.sandbox.paypal.com/v2/checkout/orders/{order_id}/capture
        """
        token = self._get_access_token()
        if not token:
            return PaymentResult(
                success=False,
                transaction_id=order_id,
                status="FAILED",
                details={"error": "Payment provider credentials missing or not configured"},
            )

        url = f"{self._base_url}/v2/checkout/orders/{order_id}/capture"
        req_id = request_id or f"req_cap_{order_id[:24]}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": req_id,
        }
        try:
            resp = httpx.post(url, json={}, headers=headers, timeout=15.0)
            if resp.status_code in (200, 201):
                data = resp.json()
                raw_status = str(data.get("status", "")).upper()
                if raw_status == "COMPLETED":
                    provider_state = "COMPLETED"
                elif raw_status == "PENDING":
                    provider_state = "RECONCILE"
                else:
                    provider_state = "RECONCILE"
                data["provider_status"] = provider_state
                data["business_rejection"] = False
                return PaymentResult(
                    success=(provider_state == "COMPLETED"),
                    transaction_id=order_id,
                    status=provider_state,
                    details=data,
                )
            if resp.status_code in (408, 429):
                # Rate limit (429) or request timeout (408) is not a final business rejection
                return PaymentResult(
                    success=False,
                    transaction_id=order_id,
                    status="RECONCILE",
                    details={
                        "error": self.normalize_error(resp.text),
                        "http_status": resp.status_code,
                        "raw": resp.text,
                        "business_rejection": False,
                    },
                )
            if 400 <= resp.status_code < 500:
                # 4xx is a definite business rejection
                return PaymentResult(
                    success=False,
                    transaction_id=order_id,
                    status="FAILED",
                    details={
                        "error": self.normalize_error(resp.text),
                        "http_status": resp.status_code,
                        "raw": resp.text,
                        "business_rejection": True,
                    },
                )
            # 5xx, timeouts or server errors route to RECONCILE
            return PaymentResult(
                success=False,
                transaction_id=order_id,
                status="RECONCILE",
                details={
                    "error": self.normalize_error(resp.text),
                    "http_status": resp.status_code,
                    "raw": resp.text,
                    "business_rejection": False,
                },
            )
        except Exception as exc:
            return PaymentResult(
                success=False,
                transaction_id=order_id,
                status="RECONCILE",
                details={"error": self.normalize_error(exc), "business_rejection": False},
            )

    def verify_webhook(self, headers: dict[str, str], body_bytes: bytes) -> bool:
        """Verify webhook signature via PayPal's verify-webhook-signature API.

        Documentation:
        POST https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature
        Fails closed on missing headers, unconfigured credentials, or invalid signature.
        """
        auth_algo = (
            headers.get("PAYPAL-AUTH-ALGO")
            or headers.get("paypal-auth-algo")
            or headers.get("Paypal-Auth-Algo")
        )
        cert_url = (
            headers.get("PAYPAL-CERT-URL")
            or headers.get("paypal-cert-url")
            or headers.get("Paypal-Cert-Url")
        )
        transmission_id = (
            headers.get("PAYPAL-TRANSMISSION-ID")
            or headers.get("paypal-transmission-id")
            or headers.get("Paypal-Transmission-Id")
        )
        transmission_sig = (
            headers.get("PAYPAL-TRANSMISSION-SIG")
            or headers.get("paypal-transmission-sig")
            or headers.get("Paypal-Transmission-Sig")
        )
        transmission_time = (
            headers.get("PAYPAL-TRANSMISSION-TIME")
            or headers.get("paypal-transmission-time")
            or headers.get("Paypal-Transmission-Time")
        )

        if not (
            auth_algo and cert_url and transmission_id and transmission_sig and transmission_time
        ):
            return False

        # SSRF defense: Validate cert_url must be HTTPS and hosted on a legitimate PayPal API domain
        if not validate_paypal_cert_url(cert_url):
            return False

        webhook_id = os.getenv("PAYPAL_WEBHOOK_ID") or ""
        if not webhook_id or not self._client_id or not self._client_secret:
            return False

        token = self._get_access_token()
        if not token:
            return False

        try:
            webhook_event = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return False

        verification_payload = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": webhook_id,
            "webhook_event": webhook_event,
        }

        url = f"{self._base_url}/v1/notifications/verify-webhook-signature"
        try:
            resp = httpx.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                json=verification_payload,
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return bool(data.get("verification_status") == "SUCCESS")
            return False
        except Exception:
            return False
