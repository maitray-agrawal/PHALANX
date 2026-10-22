"""Spike: Route A - PayPal Payouts v1 API.

Endpoint: POST https://api-m.sandbox.paypal.com/v1/payments/payouts
Headers:
  Authorization: Bearer <token>
  Content-Type: application/json
  PayPal-Request-Id: <idempotency_key>
Body:
  sender_batch_header: { sender_batch_id, email_subject }
  items: [ { recipient_type, amount: { value, currency }, receiver, note, sender_item_id } ]
"""

import os
import uuid
from pathlib import Path

import httpx


def load_env_if_present() -> None:
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def run_payouts_spike() -> dict[str, str]:
    load_env_if_present()
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET")

    if not client_id or not client_secret:
        return {
            "status": "SKIPPED_NO_ENV",
            "message": "PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET not configured in .env",
            "route": "Route A (Payouts v1)",
        }

    # 1. Fetch Token
    token_url = "https://api-m.sandbox.paypal.com/v1/oauth2/token"
    token_resp = httpx.post(
        token_url,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json"},
        timeout=10.0,
    )
    if token_resp.status_code != 200:
        return {"status": "TOKEN_ERROR", "details": token_resp.text[:200]}

    access_token = token_resp.json().get("access_token")
    scopes = token_resp.json().get("scope", "")

    # 2. Check Payouts permission scope
    # Required scope: https://uri.paypal.com/v0/payments/payouts
    has_payouts_scope = "https://uri.paypal.com/v0/payments/payouts" in scopes

    # 3. Create Payout Batch
    batch_id = f"phalanx_spike_{uuid.uuid4().hex[:12]}"
    request_id = f"req_{uuid.uuid4().hex}"
    payout_url = "https://api-m.sandbox.paypal.com/v1/payments/payouts"
    payload = {
        "sender_batch_header": {
            "sender_batch_id": batch_id,
            "email_subject": "PHALANX Autonomous Agent Payout (Sandbox)",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {"value": "25.00", "currency": "USD"},
                "receiver": "sb-vendor-sandbox@business.example.com",
                "note": "Autonomous agent cloud hosting renewal",
                "sender_item_id": "item_001",
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "PayPal-Request-Id": request_id,
    }

    try:
        payout_resp = httpx.post(payout_url, json=payload, headers=headers, timeout=12.0)
        return {
            "status": "EXECUTED",
            "http_status": str(payout_resp.status_code),
            "has_payouts_scope": str(has_payouts_scope),
            "response_preview": payout_resp.text[:300],
        }
    except Exception as exc:
        return {"status": "HTTP_EXCEPTION", "error": str(exc)}


if __name__ == "__main__":
    result = run_payouts_spike()
    print("Payouts Spike Result:", result)
