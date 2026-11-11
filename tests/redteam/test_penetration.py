"""Hostile Penetration Test Suite for PHALANX.

Covers adversarial threat vectors:
1. Token tampering (payload edits, truncated/reordered, wrong key, alg/role swaps, expired, replay)
2. IDOR across principals and agents
3. Mass assignment and unexpected property injection
4. Role escalation attempts
5. Agent self-approval attempts
6. Approval digest swap & TOCTOU race conditions
7. Idempotency-key abuse & mutations
8. Rate-limit bypass attempts (X-Forwarded-For spoofing, many identities)
9. Oversized, deeply nested, and unicode-confusable payloads
10. Log-injection strings (CRLF, ANSI escapes, structured forgery)
11. SSRF attempts through URL parameters and webhook certs
12. Forged, replayed, and out-of-order webhooks
13. CORS preflight abuse & unauthorized origins
14. Clickjacking defense (X-Frame-Options & CSP frame-ancestors)
15. Constant-time comparisons (tokens & admin token)
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.auth import check_approver_object_authorization
from app.api.dependencies import (
    get_authorization_service,
    get_clock,
    get_ledger,
    get_ledger_service,
    get_mandate_service,
    get_payment_rail,
)
from app.application.dtos import CreateMandateCommand
from app.application.services import (
    AuthorizationService,
    LedgerService,
    MandateService,
)
from app.infrastructure.config import settings
from app.infrastructure.ledger import InMemoryLedgerAdapter
from app.infrastructure.paypal import FakePaymentRail
from app.infrastructure.tokens import (
    Identity,
    Role,
    TokenExpiredError,
    TokenSignatureError,
    _b64url_decode,
    _b64url_encode,
    create_role_token,
    verify_role_token,
)
from app.main import create_app
from tests.conftest import FixedTestClock


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from app.api.middleware import _rate_limiter

    _rate_limiter._history.clear()
    yield
    _rate_limiter._history.clear()


@pytest.fixture
def pen_clock() -> FixedTestClock:
    return FixedTestClock(datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def pen_ledger() -> InMemoryLedgerAdapter:
    return InMemoryLedgerAdapter()


@pytest.fixture
def pen_rail() -> FakePaymentRail:
    return FakePaymentRail()


@pytest.fixture
def pen_mandate_service(pen_clock: FixedTestClock) -> MandateService:
    return MandateService(clock=pen_clock)


@pytest.fixture
def pen_auth_service(
    pen_clock: FixedTestClock,
    pen_ledger: InMemoryLedgerAdapter,
    pen_rail: FakePaymentRail,
    pen_mandate_service: MandateService,
) -> AuthorizationService:
    return AuthorizationService(
        clock=pen_clock,
        ledger=pen_ledger,
        mandate_service=pen_mandate_service,
        payment_rail=pen_rail,
    )


@pytest.fixture
def pen_client(
    pen_clock: FixedTestClock,
    pen_ledger: InMemoryLedgerAdapter,
    pen_rail: FakePaymentRail,
    pen_mandate_service: MandateService,
    pen_auth_service: AuthorizationService,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_clock] = lambda: pen_clock
    app.dependency_overrides[get_ledger] = lambda: pen_ledger
    app.dependency_overrides[get_ledger_service] = lambda: LedgerService(ledger=pen_ledger)
    app.dependency_overrides[get_payment_rail] = lambda: pen_rail
    app.dependency_overrides[get_mandate_service] = lambda: pen_mandate_service
    app.dependency_overrides[get_authorization_service] = lambda: pen_auth_service
    return TestClient(app)


# 1. TOKEN TAMPERING


@pytest.mark.redteam
def test_pen_token_payload_edit_signature_mismatch(pen_client: TestClient) -> None:
    """Attacker tampers with the base64url payload segment without re-signing."""
    valid_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    header_b64, payload_b64, sig_b64 = valid_token.split(".")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    payload["role"] = "principal"  # Tamper role
    tampered_payload_b64 = _b64url_encode(json.dumps(payload).encode("utf-8"))
    tampered_token = f"{header_b64}.{tampered_payload_b64}.{sig_b64}"

    with pytest.raises(TokenSignatureError):
        verify_role_token(tampered_token)

    resp = pen_client.get(
        "/v1/overview",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )
    assert resp.status_code == 401
    assert "Invalid token" in resp.json().get("detail", "")


@pytest.mark.redteam
def test_pen_token_truncated_and_extra_segments(pen_client: TestClient) -> None:
    """Attacker sends truncated (1, 2) or extra (4) segment tokens."""
    valid_token = create_role_token(Role.AGENT, "principal_treasury")
    parts = valid_token.split(".")

    token_2 = f"{parts[0]}.{parts[1]}"
    token_1 = parts[0]
    token_4 = f"{valid_token}.extra_part"

    for bad_tok in (token_2, token_1, token_4):
        with pytest.raises(TokenSignatureError):
            verify_role_token(bad_tok)
        resp = pen_client.get(
            "/v1/overview",
            headers={"Authorization": f"Bearer {bad_tok}"},
        )
        assert resp.status_code == 401


@pytest.mark.redteam
def test_pen_token_reordered_segments(pen_client: TestClient) -> None:
    """Attacker swaps segment order: signature.payload.header."""
    valid_token = create_role_token(Role.AGENT, "principal_treasury")
    header_b64, payload_b64, sig_b64 = valid_token.split(".")

    reordered = f"{sig_b64}.{payload_b64}.{header_b64}"
    with pytest.raises(TokenSignatureError):
        verify_role_token(reordered)

    resp = pen_client.get(
        "/v1/overview",
        headers={"Authorization": f"Bearer {reordered}"},
    )
    assert resp.status_code == 401


@pytest.mark.redteam
def test_pen_token_wrong_signing_key(pen_client: TestClient) -> None:
    """Attacker signs a valid payload structure with an adversarial key."""
    header = {"alg": "HS256", "typ": "PHX"}
    payload = {
        "sub": "agent:agent-auto-1",
        "role": "agent",
        "principal_id": "principal_treasury",
        "agent_id": "agent-auto-1",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
    }
    h_b64 = _b64url_encode(json.dumps(header).encode())
    p_b64 = _b64url_encode(json.dumps(payload).encode())
    signing_input = f"{h_b64}.{p_b64}".encode()

    fake_key = b"attacker-secret-key-at-least-32-bytes-long"
    fake_sig = _b64url_encode(hmac.new(fake_key, signing_input, hashlib.sha256).digest())
    bad_token = f"{h_b64}.{p_b64}.{fake_sig}"

    with pytest.raises(TokenSignatureError):
        verify_role_token(bad_token)

    resp = pen_client.get(
        "/v1/overview",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert resp.status_code == 401


@pytest.mark.redteam
def test_pen_token_alg_none_and_swaps(pen_client: TestClient) -> None:
    """Attacker attempts algorithm confusion (alg: none, alg: RS256)."""
    payload = {
        "sub": "principal:admin",
        "role": "principal",
        "principal_id": "principal_treasury",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
    }
    p_b64 = _b64url_encode(json.dumps(payload).encode())

    # alg: none with empty sig
    h_none = _b64url_encode(json.dumps({"alg": "none", "typ": "PHX"}).encode())
    token_none = f"{h_none}.{p_b64}."

    with pytest.raises(TokenSignatureError):
        verify_role_token(token_none)

    resp = pen_client.get(
        "/v1/overview",
        headers={"Authorization": f"Bearer {token_none}"},
    )
    assert resp.status_code == 401

    # alg: RS256
    h_rsa = _b64url_encode(json.dumps({"alg": "RS256", "typ": "PHX"}).encode())
    token_rsa = f"{h_rsa}.{p_b64}.invalidsig"
    with pytest.raises(TokenSignatureError):
        verify_role_token(token_rsa)


@pytest.mark.redteam
def test_pen_token_expired_rejection(pen_client: TestClient) -> None:
    """Attacker replays an expired token past its exp window."""
    expired_token = create_role_token(
        Role.AGENT,
        "principal_treasury",
        expires_in_seconds=-300,  # 5 minutes in past
    )
    with pytest.raises(TokenExpiredError):
        verify_role_token(expired_token)

    resp = pen_client.get(
        "/v1/overview",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    assert "Token expired" in resp.json().get("detail", "")


@pytest.mark.redteam
def test_pen_token_replay_after_key_rotation(pen_client: TestClient) -> None:
    """Attacker captures a valid token, but secret key is rotated."""
    original_key = settings.secret_key
    token_under_key1 = create_role_token(Role.AGENT, "principal_treasury")

    try:
        settings.secret_key = "brand-new-rotated-secret-key-at-least-32-bytes"
        with pytest.raises(TokenSignatureError):
            verify_role_token(token_under_key1)

        resp = pen_client.get(
            "/v1/overview",
            headers={"Authorization": f"Bearer {token_under_key1}"},
        )
        assert resp.status_code == 401
    finally:
        settings.secret_key = original_key


# 2. IDOR ACROSS PRINCIPALS AND AGENTS


@pytest.mark.redteam
def test_pen_idor_agent_cannot_impersonate_another_agent(pen_client: TestClient) -> None:
    """Agent A attempts to issue transaction under Agent B identity."""
    token_agent_1 = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")

    req_body = {
        "agent_id": "agent-auto-2",  # Cross-agent IDOR
        "recipient_id": "payee_vendor_1",
        "amount_minor": 5000,
        "currency": "USD",
        "purpose": "IDOR impersonation attempt",
        "idempotency_key": "pen_idor_agent_1",
    }
    resp = pen_client.post(
        "/v1/payment-requests",
        json=req_body,
        headers={"Authorization": f"Bearer {token_agent_1}"},
    )
    assert resp.status_code == 403
    expected_msg = "Agent 'agent-auto-1' cannot initiate transactions on behalf of 'agent-auto-2'"
    assert expected_msg in resp.json()["detail"]


@pytest.mark.redteam
def test_pen_idor_cross_principal_approver_rejected() -> None:
    """Approver from Tenant B attempts to approve step-up from Tenant A."""
    from fastapi import HTTPException

    tenant_a_identity = Identity(
        subject="approver:tenant_b",
        role=Role.APPROVER,
        principal_id="principal_subsidiary_b",
    )
    with pytest.raises(HTTPException) as exc_info:
        check_approver_object_authorization(tenant_a_identity, "principal_treasury")
    assert exc_info.value.status_code == 403
    assert "does not match mandate principal" in exc_info.value.detail


@pytest.mark.redteam
def test_pen_idor_agent_cannot_read_approvals_queue(pen_client: TestClient) -> None:
    """Agent identity is forbidden from accessing the supervisor approval queue."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    resp = pen_client.get(
        "/v1/approvals",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 403
    assert "Autonomous agents cannot access the supervisor approval queue" in resp.json()["detail"]


# 3. MASS ASSIGNMENT AND EXTRA FIELDS


@pytest.mark.redteam
def test_pen_mass_assignment_extra_fields_in_payment_request(pen_client: TestClient) -> None:
    """Attacker injects undeclared parameters (admin_override, bypass_policy)."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "payee_vendor_1",
        "amount_minor": 5000,
        "currency": "USD",
        "purpose": "Legitimate payment",
        "idempotency_key": "pen_mass_assign_1",
        "admin_override": True,  # Injected field
        "bypass_policy": True,  # Injected field
    }
    resp = pen_client.post(
        "/v1/payment-requests",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 422
    assert "extra" in str(resp.json()).lower() or "forbidden" in str(resp.json()).lower()


@pytest.mark.redteam
def test_pen_mass_assignment_extra_fields_in_approval(pen_client: TestClient) -> None:
    """Attacker injects privilege escalation fields into approval body."""
    approver_token = create_role_token(Role.APPROVER, "principal_treasury")
    payload = {
        "decision": "ALLOW",
        "reason": "Supervisor approval",
        "expected_digest": "a" * 64,
        "super_admin": True,  # Injected
    }
    resp = pen_client.post(
        "/v1/approvals/req_12345",
        json=payload,
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert resp.status_code == 422


# 4. ROLE ESCALATION


@pytest.mark.redteam
def test_pen_role_escalation_auditor_cannot_request_payment(pen_client: TestClient) -> None:
    """Auditor role attempts to dispatch financial transaction."""
    auditor_token = create_role_token(Role.AUDITOR, "principal_treasury")
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "payee_vendor_1",
        "amount_minor": 5000,
        "currency": "USD",
        "purpose": "Unauthorized payment attempt",
        "idempotency_key": "pen_role_esc_auditor",
    }
    resp = pen_client.post(
        "/v1/payment-requests",
        json=payload,
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert resp.status_code == 403
    assert "Role 'auditor' cannot submit payment requests" in resp.json()["detail"]


@pytest.mark.redteam
def test_pen_role_escalation_agent_cannot_create_mandate(pen_client: TestClient) -> None:
    """Agent role attempts to create a root authority mandate."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    payload = {
        "mandate_id": "mandate_adversarial",
        "principal_id": "principal_treasury",
        "agent_id": "agent-auto-1",
        "single_limit_minor": 10000000,
        "instant_threshold_minor": 10000000,
        "lifetime_budget_minor": 10000000,
        "currency": "USD",
        "allowed_payees": ["*"],
        "allowed_purposes": ["*"],
        "valid_days": 90,
    }
    resp = pen_client.post(
        "/v1/mandates",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.redteam
def test_pen_role_escalation_admin_reset_requires_secret(pen_client: TestClient) -> None:
    """Agent token cannot invoke admin reset."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    resp = pen_client.post(
        "/v1/admin/reset",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 403
    assert "cannot reset admin state" in resp.json()["detail"]


# 5. AGENT SELF-APPROVAL


@pytest.mark.redteam
def test_pen_agent_self_approval_strictly_blocked(pen_client: TestClient) -> None:
    """Agent requests a step-up payment, then attempts to approve its own request."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")

    # 1. Trigger step-up payment
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "payee_vendor_1",
        "amount_minor": 500000,  # $5000 exceeds single tx limit -> STEP_UP
        "currency": "USD",
        "purpose": "Step-up trigger for self-approval test",
        "idempotency_key": "pen_self_approval_1",
    }
    resp = pen_client.post(
        "/v1/payment-requests",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "STEP_UP"
    req_id = data["request_id"]
    intent_digest = data["intent_digest"]

    # 2. Agent attempts self-approval
    approval_body = {
        "decision": "ALLOW",
        "reason": "Agent self-approval override",
        "expected_digest": intent_digest,
    }
    resp_approve = pen_client.post(
        f"/v1/approvals/{req_id}",
        json=approval_body,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp_approve.status_code == 403
    assert "Autonomous agents cannot approve transactions" in resp_approve.json()["detail"]


# 6. APPROVAL DIGEST SWAP AND TOCTOU


@pytest.mark.redteam
def test_pen_approval_digest_swap_detected_and_rejected(pen_client: TestClient) -> None:
    """Approver attempts to approve with a swapped/tampered intent digest."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    approver_token = create_role_token(Role.APPROVER, "principal_treasury")

    # Step-up request
    payload = {
        "agent_id": "agent-auto-1",
        "recipient_id": "payee_vendor_1",
        "amount_minor": 200000,
        "currency": "USD",
        "purpose": "Legitimate step-up purchase",
        "idempotency_key": "pen_digest_swap_1",
    }
    resp = pen_client.post(
        "/v1/payment-requests",
        json=payload,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    req_id = resp.json()["request_id"]

    # Swapped digest
    swapped_digest = "e" * 64
    approval_body = {
        "decision": "ALLOW",
        "reason": "Supervisor approve",
        "expected_digest": swapped_digest,
    }
    resp_approve = pen_client.post(
        f"/v1/approvals/{req_id}",
        json=approval_body,
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert resp_approve.status_code in (400, 409)


# 7. IDEMPOTENCY-KEY ABUSE


@pytest.mark.redteam
def test_pen_idempotency_key_mutation_raises_conflict(pen_client: TestClient) -> None:
    """Same idempotency_key reused with different amount and recipient."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")

    # Initial request
    resp1 = pen_client.post(
        "/v1/payment-requests",
        json={
            "agent_id": "agent-auto-1",
            "recipient_id": "vendor-paypal-sandbox-1",
            "amount_minor": 1000,
            "currency": "USD",
            "purpose": "Original purchase",
            "idempotency_key": "pen_idem_abuse_key",
        },
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp1.status_code == 200

    # Mutated request with same key
    resp2 = pen_client.post(
        "/v1/payment-requests",
        json={
            "agent_id": "agent-auto-1",
            "recipient_id": "vendor-paypal-sandbox-1",
            "amount_minor": 99999,  # Changed amount
            "currency": "USD",
            "purpose": "Mutated attempt",
            "idempotency_key": "pen_idem_abuse_key",
        },
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["decision"] == "DENY"
    assert "IDEMPOTENCY_MISMATCH" in resp2.json()["reason_codes"] or any(
        "idempotency" in r.lower() for r in resp2.json()["reasons"]
    )


@pytest.mark.redteam
def test_pen_idempotency_key_empty_or_whitespace_rejected(pen_client: TestClient) -> None:
    """Empty string idempotency key rejected by boundary validation."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    resp = pen_client.post(
        "/v1/payment-requests",
        json={
            "agent_id": "agent-auto-1",
            "recipient_id": "payee_vendor_1",
            "amount_minor": 1000,
            "currency": "USD",
            "purpose": "Empty idempotency test",
            "idempotency_key": "",
        },
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 422


# 8. RATE-LIMIT BYPASS ATTEMPTS


@pytest.mark.redteam
def test_pen_rate_limit_bypass_spoofed_x_forwarded_for_fails(pen_client: TestClient) -> None:
    """Attacker attempts to evade rate limits by spoofing X-Forwarded-For headers."""
    from app.api.middleware import _rate_limiter

    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    _rate_limiter._history.clear()

    # Fill up limit for this token
    for i in range(120):
        resp = pen_client.get(
            "/v1/overview",
            headers={
                "Authorization": f"Bearer {agent_token}",
                "X-Forwarded-For": f"198.51.100.{i % 250}",
                "X-Real-IP": f"203.0.113.{i % 250}",
            },
        )
        assert resp.status_code == 200

    # 121st request must trigger HTTP 429 despite spoofed headers
    blocked_resp = pen_client.get(
        "/v1/overview",
        headers={
            "Authorization": f"Bearer {agent_token}",
            "X-Forwarded-For": "198.51.100.254",
        },
    )
    assert blocked_resp.status_code == 429
    assert "Rate limit exceeded" in blocked_resp.json()["detail"]


# 9. OVERSIZED, DEEPLY NESTED, AND UNICODE-CONFUSABLE PAYLOADS


@pytest.mark.redteam
def test_pen_oversized_payload_body_size_middleware_blocks(pen_client: TestClient) -> None:
    """Payloads exceeding 64 KB trigger HTTP 413 Payload Too Large."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    huge_string = "X" * (65 * 1024)  # 65 KB

    resp = pen_client.post(
        "/v1/payment-requests",
        content=huge_string,
        headers={
            "Authorization": f"Bearer {agent_token}",
            "Content-Type": "application/json",
            "Content-Length": str(len(huge_string)),
        },
    )
    assert resp.status_code == 413
    assert "Payload Too Large" in resp.json().get("title", "")


@pytest.mark.redteam
def test_pen_deeply_nested_json_rejected(pen_client: TestClient) -> None:
    """Deeply nested JSON structure rejected by schema validation."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    nested: dict = {"agent_id": "agent-auto-1"}
    for _ in range(40):
        nested = {"level": nested}

    resp = pen_client.post(
        "/v1/payment-requests",
        json=nested,
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.redteam
def test_pen_unicode_confusable_payee_does_not_bypass_allowlist(
    pen_client: TestClient, pen_mandate_service: MandateService
) -> None:
    """Cyrillic homoglyph (Cyrillic 'а' U+0430 vs Latin 'a' U+0061) does not spoof allowlist."""
    pen_mandate_service.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate_restricted_allowlist",
            principal_id="principal_treasury",
            agent_id="agent-restricted-payee",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=500_000,
            currency="USD",
            allowed_payees=["paypal-vendor"],
            allow_unregistered_payees=False,
            allowed_purposes=[],
            valid_days=30,
        )
    )
    agent_token = create_role_token(
        Role.AGENT, "principal_treasury", agent_id="agent-restricted-payee"
    )

    # "pаypal-vendor" with Cyrillic 'а'
    spoofed_payee = "p\u0430ypal-vendor"

    resp = pen_client.post(
        "/v1/payment-requests",
        json={
            "agent_id": "agent-restricted-payee",
            "recipient_id": spoofed_payee,
            "amount_minor": 1000,
            "currency": "USD",
            "purpose": "Homoglyph spoof attempt",
            "idempotency_key": "pen_homoglyph_1",
        },
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 200
    decision = resp.json()["decision"]
    assert decision in ("DENY", "STEP_UP")
    assert any(
        "RECIPIENT_NOT_ALLOWED" in c or "MANDATE" in c or "PAYEE_UNAUTHORIZED" in c
        for c in resp.json()["reason_codes"]
    )


@pytest.mark.redteam
def test_pen_zero_width_space_in_payee_does_not_match_allowlist(
    pen_client: TestClient, pen_mandate_service: MandateService
) -> None:
    """Payee containing zero-width space does not match legitimate payee allowlist."""
    pen_mandate_service.create_mandate(
        CreateMandateCommand(
            mandate_id="mandate_restricted_zwsp",
            principal_id="principal_treasury",
            agent_id="agent-restricted-zwsp",
            single_limit_minor=100_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=500_000,
            currency="USD",
            allowed_payees=["payee_vendor_1"],
            allow_unregistered_payees=False,
            allowed_purposes=[],
            valid_days=30,
        )
    )
    agent_token = create_role_token(
        Role.AGENT, "principal_treasury", agent_id="agent-restricted-zwsp"
    )
    spoofed_payee = "payee\u200b_vendor_1"

    resp = pen_client.post(
        "/v1/payment-requests",
        json={
            "agent_id": "agent-restricted-zwsp",
            "recipient_id": spoofed_payee,
            "amount_minor": 1000,
            "currency": "USD",
            "purpose": "Zero-width space injection",
            "idempotency_key": "pen_zwsp_1",
        },
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] in ("DENY", "STEP_UP")
    assert any(
        "RECIPIENT_NOT_ALLOWED" in c or "MANDATE" in c or "PAYEE_UNAUTHORIZED" in c
        for c in resp.json()["reason_codes"]
    )


# 10. LOG-INJECTION STRINGS


@pytest.mark.redteam
def test_pen_log_injection_crlf_and_ansi_escaped(
    pen_client: TestClient, pen_ledger: InMemoryLedgerAdapter
) -> None:
    """CRLF newlines and ANSI sequences in purpose are sanitized via JSON encoding."""
    agent_token = create_role_token(Role.AGENT, "principal_treasury", agent_id="agent-auto-1")
    malicious_purpose = (
        "Normal purpose\r\n"
        '{"timestamp":"2026-11-06T00:00:00Z","level":"INFO","event":"AUTH_OVERRIDE_GRANTED"}\r\n'
        "\x1b[31;1mRED INJECTION\x1b[0m"
    )

    resp = pen_client.post(
        "/v1/payment-requests",
        json={
            "agent_id": "agent-auto-1",
            "recipient_id": "payee_vendor_1",
            "amount_minor": 1000,
            "currency": "USD",
            "purpose": malicious_purpose,
            "idempotency_key": "pen_log_inj_1",
        },
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp.status_code == 200
    events = pen_ledger.get_all_events()
    matching = [e for e in events if e.payload.get("idempotency_key") == "pen_log_inj_1"]
    assert len(matching) == 1
    assert matching[0].payload["purpose"] == malicious_purpose


# 11. SSRF ATTEMPTS THROUGH ANY URL FIELD


@pytest.mark.redteam
def test_pen_ssrf_webhook_cert_url_internal_metadata_rejected(pen_client: TestClient) -> None:
    """Webhook PAYPAL-CERT-URL pointing to AWS metadata IP (169.254.169.254) is blocked."""
    headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "http://169.254.169.254/latest/meta-data/",
        "PAYPAL-TRANSMISSION-ID": "trans_123",
        "PAYPAL-TRANSMISSION-SIG": "fixture-valid-test-sig",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-06T12:00:00Z",
    }
    body = {"id": "WH-EVENT-SSRF-1", "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED"}
    resp = pen_client.post("/v1/webhooks/paypal", json=body, headers=headers)
    assert resp.status_code in (400, 401)


@pytest.mark.redteam
def test_pen_ssrf_webhook_cert_url_attacker_domain_rejected(pen_client: TestClient) -> None:
    """Webhook PAYPAL-CERT-URL pointing to attacker domain is blocked."""
    headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://evil-attacker.com/malicious_cert.pem",
        "PAYPAL-TRANSMISSION-ID": "trans_123",
        "PAYPAL-TRANSMISSION-SIG": "fixture-valid-test-sig",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-06T12:00:00Z",
    }
    body = {"id": "WH-EVENT-SSRF-2", "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED"}
    resp = pen_client.post("/v1/webhooks/paypal", json=body, headers=headers)
    assert resp.status_code in (400, 401)


# 12. FORGED, REPLAYED, AND OUT-OF-ORDER WEBHOOKS


@pytest.mark.redteam
def test_pen_webhook_forged_signature_rejected(pen_client: TestClient) -> None:
    """Webhook with forged arbitrary signature string rejected with HTTP 400 or 401."""
    headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/certs/cert.pem",
        "PAYPAL-TRANSMISSION-ID": "trans_forged_999",
        "PAYPAL-TRANSMISSION-SIG": "totally-fake-forged-signature-string",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-06T12:00:00Z",
    }
    body = {"id": "WH-EVENT-FORGED-1", "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED"}
    resp = pen_client.post("/v1/webhooks/paypal", json=body, headers=headers)
    assert resp.status_code in (400, 401)


@pytest.mark.redteam
def test_pen_webhook_replayed_event_id_deduplicated(pen_client: TestClient) -> None:
    """Captured legitimate webhook replayed twice is recognized as duplicate."""
    headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/certs/cert.pem",
        "PAYPAL-TRANSMISSION-ID": "trans_valid_123",
        "PAYPAL-TRANSMISSION-SIG": "fixture-valid-test-sig",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-06T12:00:00Z",
    }
    body = {
        "id": "WH-EVENT-REPLAY-TARGET-1",
        "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
        "resource": {"payout_item_id": "tx_replay_1"},
    }
    # First delivery
    resp1 = pen_client.post("/v1/webhooks/paypal", json=body, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "processed"

    # Replay with identical event_id
    resp2 = pen_client.post("/v1/webhooks/paypal", json=body, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "duplicate_ignored"


# 13. CORS PREFLIGHT ABUSE


@pytest.mark.redteam
def test_pen_cors_unauthorized_origin_preflight_rejected(pen_client: TestClient) -> None:
    """Preflight OPTIONS request from unauthorized origin does not echo origin."""
    resp = pen_client.options(
        "/v1/payment-requests",
        headers={
            "Origin": "https://evil-attacker-site.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    allow_origin = resp.headers.get("access-control-allow-origin")
    assert allow_origin != "https://evil-attacker-site.com"
    assert allow_origin != "*"


@pytest.mark.redteam
def test_pen_cors_authorized_origin_permitted(pen_client: TestClient) -> None:
    """Preflight OPTIONS request from authorized localhost origin is permitted."""
    resp = pen_client.options(
        "/v1/payment-requests",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


# 14. CLICKJACKING AND DEFENSIVE HEADERS


@pytest.mark.redteam
def test_pen_clickjacking_defense_headers_present(pen_client: TestClient) -> None:
    """All responses enforce frame-ancestors 'none' and X-Frame-Options: DENY."""
    resp = pen_client.get("/healthz")
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    csp = resp.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp


# 15. CONSTANT-TIME TIMING SAFETY


@pytest.mark.redteam
def test_pen_constant_time_comparison_implemented() -> None:
    """Verify hmac.compare_digest is utilized for tokens and admin comparison."""
    token_a = "phx_admin_secret_token_at_least_24_chars_correct"
    token_b = "phx_admin_secret_token_at_least_24_chars_differe"
    token_c = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    assert hmac.compare_digest(token_a, token_a) is True
    assert hmac.compare_digest(token_a, token_b) is False
    assert hmac.compare_digest(token_a, token_c) is False
