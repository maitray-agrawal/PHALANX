"""PayPal Sandbox End-to-End Verification Check (Orders v2 Lifecycle).

Executes full sandbox order checkout cycle:
1. Validates PayPal Sandbox credentials.
2. Acquires OAuth bearer token.
3. Creates Orders v2 CAPTURE order with PayPal-Request-Id idempotency.
4. Extracts and displays PayPal Sandbox Buyer Approval URL.
5. Waits for buyer confirmation or polls for APPROVED status.
6. Executes Order Capture.
7. Polls Order Lookup to verify final COMPLETED status.
"""

import argparse
import os
import sys
import time
from typing import Any
import httpx


SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"


def get_credentials() -> tuple[str, str]:
    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        # Check .env file
        from pathlib import Path
        env_p = Path(".env")
        if env_p.exists():
            for line in env_p.read_text(encoding="utf-8").splitlines():
                if line.startswith("PAYPAL_CLIENT_ID=") and not client_id:
                    client_id = line.split("=", 1)[1].strip()
                elif line.startswith("PAYPAL_CLIENT_SECRET=") and not client_secret:
                    client_secret = line.split("=", 1)[1].strip()
    return client_id, client_secret


def get_access_token(client_id: str, client_secret: str) -> str:
    url = f"{SANDBOX_BASE_URL}/v1/oauth2/token"
    resp = httpx.post(
        url,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        timeout=15.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"PayPal OAuth failed (HTTP {resp.status_code}): {resp.text}")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("No access_token returned by PayPal OAuth")
    return str(token)


def create_order(token: str, amount_usd: str = "25.00") -> dict[str, Any]:
    url = f"{SANDBOX_BASE_URL}/v2/checkout/orders"
    req_id = f"e1_test_{int(time.time())}"
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": f"ref_{req_id[:24]}",
                "amount": {"currency_code": "USD", "value": amount_usd},
                "description": "PHALANX Autonomous Verification Order",
            }
        ],
        "application_context": {
            "return_url": "https://example.com/return",
            "cancel_url": "https://example.com/cancel",
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "PayPal-Request-Id": req_id,
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Create Order failed (HTTP {resp.status_code}): {resp.text}")
    return resp.json()


def lookup_order(token: str, order_id: str) -> dict[str, Any]:
    url = f"{SANDBOX_BASE_URL}/v2/checkout/orders/{order_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = httpx.get(url, headers=headers, timeout=12.0)
    if resp.status_code != 200:
        raise RuntimeError(f"Lookup Order failed (HTTP {resp.status_code}): {resp.text}")
    return resp.json()


def capture_order(token: str, order_id: str) -> dict[str, Any]:
    url = f"{SANDBOX_BASE_URL}/v2/checkout/orders/{order_id}/capture"
    req_id = f"e1_cap_{order_id[:20]}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "PayPal-Request-Id": req_id,
    }
    resp = httpx.post(url, json={}, headers=headers, timeout=20.0)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Capture Order failed (HTTP {resp.status_code}): {resp.text}")
    return resp.json()


def run_e1_check(poll_only: bool = False) -> None:
    print("=" * 65)
    print("  PHALANX PAYPAL SANDBOX ORDERS v2 END-TO-END CHECK (E1)")
    print("=" * 65)

    client_id, client_secret = get_credentials()
    if not client_id or not client_secret:
        print("\n[ERROR] PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET not configured.")
        print("Please configure credentials in environment or .env file.")
        sys.exit(1)

    print("\n[Step 1/5] Authenticating with PayPal Sandbox OAuth API...")
    token = get_access_token(client_id, client_secret)
    print(" -> SUCCESS: OAuth bearer token acquired.")

    print("\n[Step 2/5] Creating Orders v2 checkout order ($25.00 USD)...")
    order = create_order(token, amount_usd="25.00")
    order_id = order.get("id", "")
    order_status = order.get("status", "")
    print(f" -> SUCCESS: Order created! ID: {order_id} (Status: {order_status})")

    # Find approval URL
    approval_url = None
    for link in order.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            approval_url = link.get("href")
            break

    if not approval_url:
        approval_url = f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}"

    print("\n" + "*" * 65)
    print("  ACTION REQUIRED: BUYER SANDBOX APPROVAL")
    print("*" * 65)
    print(f"  Approval URL: {approval_url}")
    print("  1. Open the URL above in your browser.")
    print("  2. Log in with a PayPal Sandbox personal buyer account.")
    print("  3. Approve the payment of $25.00 USD.")
    print("*" * 65 + "\n")

    if not poll_only:
        try:
            input("Press [ENTER] once you have approved the payment in PayPal Sandbox...")
        except EOFError:
            pass

    print("\n[Step 3/5] Polling order status to confirm buyer approval...")
    approved = False
    for attempt in range(1, 13):
        info = lookup_order(token, order_id)
        current_status = str(info.get("status", "")).upper()
        print(f"  Polling attempt {attempt}/12: Order status is '{current_status}'")
        if current_status == "APPROVED":
            approved = True
            break
        elif current_status == "COMPLETED":
            print(" -> Order is already COMPLETED.")
            approved = True
            break
        time.sleep(3)

    if not approved:
        print(f"\n[WARN] Order not yet marked APPROVED (status: {current_status}).")
        print("Proceeding to capture attempt...")

    print(f"\n[Step 4/5] Executing Capture on order {order_id}...")
    capture_data = capture_order(token, order_id)
    capture_status = str(capture_data.get("status", "")).upper()
    print(f" -> SUCCESS: Capture executed! Status: {capture_status}")

    print(f"\n[Step 5/5] Polling final order lookup to verify settlement...")
    final_info = lookup_order(token, order_id)
    final_status = str(final_info.get("status", "")).upper()
    print(f" -> Final Order Status: {final_status}")

    print("\n" + "=" * 65)
    print("  E1 VERIFICATION SUMMARY")
    print("=" * 65)
    print(f"  PayPal Order ID:   {order_id}")
    print(f"  Initial State:     {order_status}")
    print(f"  Capture State:     {capture_status}")
    print(f"  Final Verified:    {final_status}")
    is_settled = final_status == "COMPLETED" or capture_status == "COMPLETED"
    print(f"  Lifecycle Result:  {'SETTLED (SUCCESS)' if is_settled else 'PENDING/FAILED'}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PayPal Sandbox E1 Checkout Verification")
    parser.add_argument("--poll-only", action="store_true", help="Poll automatically without waiting for ENTER")
    args = parser.parse_args()
    run_e1_check(poll_only=args.poll_only)
