"""PayPal Stub Workload Test Runner.

Executes a short PayPal-stub test suite validating:
- Normal Mode: fast 201 Created disbursement.
- Delay Mode: 2s latency tolerance.
- 5xx Error Mode: upstream gateway failure handling.
- Timeout Mode: 15s timeout triggering RECONCILE state machine transition.
"""

import subprocess
import sys
import time
import uuid

import httpx
import pytest

from app.domain.models import Money, TransactionIntent
from app.infrastructure.paypal import PayPalPaymentRailAdapter


@pytest.fixture(scope="module")
def stub_server():
    """Start PayPal stub server in background subprocess."""
    proc = subprocess.Popen(
        [sys.executable, "scripts/paypal_stub.py", "--port", "8089", "--mode", "normal"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        try:
            res = httpx.get("http://127.0.0.1:8089/mock/mode", timeout=0.5)
            if res.status_code == 200:
                break
        except Exception:
            time.sleep(0.2)
    yield "http://127.0.0.1:8089"
    proc.terminate()
    proc.wait()


def test_paypal_stub_normal_mode(stub_server):
    """Normal mode: fast 201 Created response."""
    # Ensure stub is in normal mode
    httpx.post(f"{stub_server}/mock/mode", json={"mode": "normal", "delay_seconds": 0.0})

    adapter = PayPalPaymentRailAdapter()
    adapter._base_url = stub_server
    adapter._client_id = "test_client_id"
    adapter._client_secret = "test_client_secret"

    from datetime import UTC, datetime

    intent = TransactionIntent(
        agent_id="agent-auto-1",
        recipient_id="vendor_infra_aws",
        money=Money(amount_minor=100, currency="USD"),
        purpose="Stub Normal Mode Test",
        idempotency_key=f"stub-norm-{uuid.uuid4().hex[:8]}",
        occurred_at_utc=datetime.now(UTC),
    )

    result = adapter.pay(intent)
    assert result.success is True, f"Expected success in normal mode, got {result}"
    assert result.status == "COMPLETED"
    assert result.transaction_id.startswith("batch_")


def test_paypal_stub_delay_mode(stub_server):
    """Delay mode: verifies handling of delayed upstream response."""
    httpx.post(f"{stub_server}/mock/mode", json={"mode": "delay", "delay_seconds": 0.5})

    adapter = PayPalPaymentRailAdapter()
    adapter._base_url = stub_server
    adapter._client_id = "test_client_id"
    adapter._client_secret = "test_client_secret"

    from datetime import UTC, datetime

    start = time.perf_counter()
    intent = TransactionIntent(
        agent_id="agent-auto-1",
        recipient_id="vendor_infra_aws",
        money=Money(amount_minor=100, currency="USD"),
        purpose="Stub Delay Mode Test",
        idempotency_key=f"stub-delay-{uuid.uuid4().hex[:8]}",
        occurred_at_utc=datetime.now(UTC),
    )

    result = adapter.pay(intent)
    elapsed = time.perf_counter() - start
    assert result.success is True
    assert elapsed >= 0.5, f"Expected delay >= 0.5s, got {elapsed:.2f}s"


def test_paypal_stub_5xx_mode(stub_server):
    """5xx mode: verifies failure handling when PayPal is down."""
    httpx.post(f"{stub_server}/mock/mode", json={"mode": "5xx", "delay_seconds": 0.0})

    adapter = PayPalPaymentRailAdapter()
    adapter._base_url = stub_server
    adapter._client_id = "test_client_id"
    adapter._client_secret = "test_client_secret"

    from datetime import UTC, datetime

    intent = TransactionIntent(
        agent_id="agent-auto-1",
        recipient_id="vendor_infra_aws",
        money=Money(amount_minor=100, currency="USD"),
        purpose="Stub 5xx Mode Test",
        idempotency_key=f"stub-5xx-{uuid.uuid4().hex[:8]}",
        occurred_at_utc=datetime.now(UTC),
    )

    result = adapter.pay(intent)
    assert result.success is False
    assert result.status == "FAILED"


def test_paypal_stub_timeout_mode(stub_server):
    """Timeout mode: verifies transition to RECONCILE state when PayPal times out."""
    httpx.post(f"{stub_server}/mock/mode", json={"mode": "timeout", "delay_seconds": 15.0})

    adapter = PayPalPaymentRailAdapter()
    adapter._base_url = stub_server
    adapter._client_id = "test_client_id"
    adapter._client_secret = "test_client_secret"

    from datetime import UTC, datetime

    intent = TransactionIntent(
        agent_id="agent-auto-1",
        recipient_id="vendor_infra_aws",
        money=Money(amount_minor=100, currency="USD"),
        purpose="Stub Timeout Mode Test",
        idempotency_key=f"stub-timeout-{uuid.uuid4().hex[:8]}",
        occurred_at_utc=datetime.now(UTC),
    )

    result = adapter.pay(intent)
    assert result.success is False
    # CRITICAL: Unknown outcome must transition to RECONCILE!
    assert result.status == "RECONCILE", f"Expected RECONCILE on timeout, got {result.status}"
