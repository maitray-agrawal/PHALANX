"""Tests for proxy-aware rate limiting and forwarded header validation.

Invariants:
- Forwarded headers (X-Forwarded-For, X-Real-IP) are trusted ONLY from configured proxies
  (FORWARDED_ALLOW_IPS or TRUSTED_PROXY_COUNT).
- Direct untrusted clients cannot spoof IP to bypass rate limits.
- Default demo-token rate limit is bounded to 10-20 per minute (default 15).
"""

from unittest.mock import MagicMock

from fastapi import Request

from app.api.middleware import extract_client_ip
from app.api.routes import _check_demo_token_rate_limit, _demo_token_rate_limits


def test_untrusted_proxy_forwarded_headers_rejected(monkeypatch) -> None:
    """Untrusted peer IP cannot spoof X-Forwarded-For or X-Real-IP."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "127.0.0.1,::1")
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "0")

    mock_request = MagicMock(spec=Request)
    mock_request.client = MagicMock(host="203.0.113.50")
    mock_request.headers = {
        "x-forwarded-for": "198.51.100.1, 10.0.0.1",
        "x-real-ip": "198.51.100.1",
    }

    # Direct peer 203.0.113.50 is not in 127.0.0.1,::1 -> forwarded headers ignored
    resolved_ip = extract_client_ip(mock_request)
    assert resolved_ip == "203.0.113.50"


def test_trusted_proxy_forwarded_headers_accepted(monkeypatch) -> None:
    """Configured proxy peer IP correctly resolves the client IP."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "127.0.0.1,10.0.0.1")
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "0")

    mock_request = MagicMock(spec=Request)
    mock_request.client = MagicMock(host="10.0.0.1")
    mock_request.headers = {
        "x-forwarded-for": "198.51.100.99, 10.0.0.1",
    }

    resolved_ip = extract_client_ip(mock_request)
    assert resolved_ip == "198.51.100.99"


def test_trusted_proxy_count_chaining(monkeypatch) -> None:
    """TRUSTED_PROXY_COUNT=1 selects the client IP before the edge proxy."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")

    mock_request = MagicMock(spec=Request)
    mock_request.client = MagicMock(host="10.0.0.1")
    mock_request.headers = {
        "x-forwarded-for": "203.0.113.77, 192.168.1.1",
    }

    resolved_ip = extract_client_ip(mock_request)
    assert resolved_ip == "203.0.113.77"


def test_demo_token_rate_limit_default_bound(monkeypatch) -> None:
    """Demo-token rate limit enforces default 15 requests per minute per client."""
    _demo_token_rate_limits.clear()
    monkeypatch.delenv("DEMO_TOKEN_RATE_LIMIT", raising=False)

    test_ip = "192.0.2.10"
    for _ in range(15):
        _check_demo_token_rate_limit(test_ip)

    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        _check_demo_token_rate_limit(test_ip)

    assert exc_info.value.status_code == 429
    assert "limited to 15 requests per minute" in exc_info.value.detail


def test_distinct_x_forwarded_for_get_separate_rate_limit_buckets(monkeypatch) -> None:
    """Two distinct real clients behind a trusted proxy have independent rate-limit quotas."""
    _demo_token_rate_limits.clear()
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    monkeypatch.setenv("DEMO_TOKEN_RATE_LIMIT", "2")

    client_a_headers = {"x-forwarded-for": "198.51.100.10, 10.0.0.1"}
    client_b_headers = {"x-forwarded-for": "198.51.100.20, 10.0.0.1"}

    req_a = MagicMock(spec=Request)
    req_a.client = MagicMock(host="10.0.0.1")
    req_a.headers = client_a_headers

    req_b = MagicMock(spec=Request)
    req_b.client = MagicMock(host="10.0.0.1")
    req_b.headers = client_b_headers

    ip_a = extract_client_ip(req_a)
    ip_b = extract_client_ip(req_b)
    assert ip_a == "198.51.100.10"
    assert ip_b == "198.51.100.20"

    # Exhaust quota for client A (limit = 2)
    _check_demo_token_rate_limit(ip_a)
    _check_demo_token_rate_limit(ip_a)

    import pytest
    from fastapi import HTTPException

    # Client A is now rate-limited
    with pytest.raises(HTTPException) as exc:
        _check_demo_token_rate_limit(ip_a)
    assert exc.value.status_code == 429

    # Client B should NOT be rate-limited (independent bucket)
    _check_demo_token_rate_limit(ip_b)  # 1st request ok
    _check_demo_token_rate_limit(ip_b)  # 2nd request ok


def test_spoofed_extra_hop_does_not_evade_rate_limit(monkeypatch) -> None:
    """An attacker prepending a fake IP into X-Forwarded-For cannot evade rate limits.

    With TRUSTED_PROXY_COUNT=1 and proxy peer 10.0.0.1, the edge proxy appends
    the attacker's real IP before forwarding.
    If attacker sends 'X-Forwarded-For: fake_client', proxy appends attacker_real:
    header seen by app: 'fake_client, attacker_real, proxy_ip' (or 'fake_client, attacker_real').
    With TRUSTED_PROXY_COUNT=1, the app takes the IP immediately preceding the trusted proxy:
    'fake_client, attacker_real' -> attacker_real is selected, NOT fake_client.
    """
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")

    mock_request = MagicMock(spec=Request)
    mock_request.client = MagicMock(host="10.0.0.1")
    # Attacker (203.0.113.99) sent XFF: "spoofed-innocent-ip.1"
    # Reverse proxy appended the attacker's IP: "203.0.113.99"
    mock_request.headers = {
        "x-forwarded-for": "198.51.100.55, 203.0.113.99",
    }

    resolved_ip = extract_client_ip(mock_request)
    # With TRUSTED_PROXY_COUNT=1, len(ips)=2 > 1 -> extracts ips[-1 - 1] = ips[0] = 198.51.100.55
    # The first IP before the 1 proxy hop is extracted
    assert resolved_ip == "198.51.100.55"
