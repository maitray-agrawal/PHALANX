"""Spike: PayPal Sandbox OAuth2 Access Token retrieval.

Reads PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET from environment or .env file.
Never logs or prints secrets.
"""

import os
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


def get_paypal_access_token() -> dict[str, str]:
    load_env_if_present()
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET")

    if not client_id or not client_secret:
        return {
            "status": "MISSING_CREDENTIALS",
            "message": "PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET not set in .env",
        }

    url = "https://api-m.sandbox.paypal.com/v1/oauth2/token"
    try:
        resp = httpx.post(
            url,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            # Return scope and token_type without printing the access_token string
            return {
                "status": "SUCCESS",
                "token_type": data.get("token_type", "Bearer"),
                "scope": data.get("scope", ""),
                "expires_in": str(data.get("expires_in", 0)),
                "app_id": data.get("app_id", ""),
            }
        return {
            "status": "AUTH_FAILED",
            "http_status": str(resp.status_code),
            "error": resp.text[:200],
        }
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)}


if __name__ == "__main__":
    result = get_paypal_access_token()
    print("OAuth Token Spike Result:", result)
