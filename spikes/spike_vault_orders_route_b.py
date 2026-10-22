"""Spike: Route B - PayPal Vault + Orders v2 (Merchant-Initiated Transaction).

Endpoint: POST https://api-m.sandbox.paypal.com/v2/checkout/orders
Structure:
  intent: CAPTURE
  payment_source:
    vault: { id: <vault_id> }  OR  card: { ... }
    payment_initiator: "MERCHANT"
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


def run_vault_orders_spike() -> dict[str, str]:
    load_env_if_present()
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET")

    if not client_id or not client_secret:
        return {
            "status": "SKIPPED_NO_ENV",
            "message": "PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET not configured in .env",
            "route": "Route B (Vault + Orders v2)",
        }

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
    request_id = f"vault_req_{uuid.uuid4().hex}"
    orders_url = "https://api-m.sandbox.paypal.com/v2/checkout/orders"

    # In Route B, an autonomous agent attempts a merchant-initiated charge using a vaulted token.
    # Without an existing vaulted customer token, we demonstrate the schema requirement:
    dummy_vault_id = "test_vault_id_12345"
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": "pu_001",
                "amount": {"currency_code": "USD", "value": "25.00"},
                "description": "Autonomous Agent Periodic Cloud Renewal",
            }
        ],
        "payment_source": {
            "vault": {"id": dummy_vault_id},
        },
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "PayPal-Request-Id": request_id,
    }

    try:
        resp = httpx.post(orders_url, json=payload, headers=headers, timeout=12.0)
        return {
            "status": "EXECUTED",
            "http_status": str(resp.status_code),
            "response_preview": resp.text[:300],
        }
    except Exception as exc:
        return {"status": "HTTP_EXCEPTION", "error": str(exc)}


if __name__ == "__main__":
    result = run_vault_orders_spike()
    print("Vault + Orders Spike Result:", result)
