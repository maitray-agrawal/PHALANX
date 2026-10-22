# API_SPEC - API Specifications & Contracts

Owner prompt: P9

All protected endpoints require authentication via Bearer token (`Authorization: Bearer <token>`) or demo header in sandbox demo mode (`X-Phalanx-Role: <role>`). Payloads use strict schemas (`extra="forbid"`), bounded strings, integer minor units, and RFC 7807 Problem+JSON error responses.

---

## 1. Authentication & Role-Based Access Control (RBAC)

Tokens are signed HMAC-SHA256 short-lived tokens with 15-minute validity windows.

### Roles
- `principal`: Organization administrator. Full permissions (issue mandates, authorize, approve, reset).
- `agent`: Autonomous software agent. Can only request payments for its own `agent_id`. Cannot approve.
- `approver`: Human supervisor. Can approve/reject step-up requests belonging to its principal.
- `auditor`: Compliance officer. Read-only access to ledger and verification endpoints.

### Object-Level Authorization (OLA)
- **Agent OLA**: An `agent` identity can only submit payment intents where `command.agent_id == identity.agent_id`.
- **Approver OLA**: An `approver` identity can only approve step-up transactions for mandates whose `principal_id == identity.principal_id`.

### Demo Token Minting (`POST /v1/auth/demo-token`, `GET /v1/auth/demo-token`)
- Request: `{"role": "agent", "principal_id": "demo-principal", "agent_id": "agent-auto-1"}`
- Response (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IlBIWCJ9...",
  "token_type": "bearer",
  "role": "agent",
  "expires_in_seconds": 900
}
```

---

## 2. Abuse Controls & Middleware

1. **Payload Size Limit**: Hard cap at 64 KB (`MAX_REQUEST_BODY_BYTES = 65,536`). Payloads exceeding this limit return `413 Payload Too Large` in Problem+JSON.
2. **Rate Limiting**: Sliding-window rate limiter per identity/IP: 120 requests per minute. Exceeding limits returns `429 Too Many Requests` with `Retry-After` header.
3. **Defensive Security Headers**:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Content-Security-Policy: default-src 'self'`
   - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
   - `Referrer-Policy: no-referrer`
   - `Cache-Control: no-store, no-cache, must-revalidate`
4. **RFC 7807 Problem+JSON**: Standardized error envelope without internal stack trace leakage:
```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Unauthorized: Authentication token required (Bearer <token>)",
  "instance": "/v1/payment-requests"
}
```
5. **Log Redaction**: Credentials, tokens, client secrets, and private keys are scrubbed from server logs.

---

## 3. Endpoints

### 3.1 Health & Probes
- `GET /healthz` -> `{"status": "ok"}`
- `GET /readyz` -> `{"status": "ready", "database": "healthy"}`
- `GET /health` -> `HealthStatusDTO`

### 3.2 Payment Requests (`POST /v1/payment-requests`)
Submits a proposed transaction intent for policy evaluation. Requires `agent` or `principal` role.

#### Request Body
```json
{
  "agent_id": "agent-auto-1",
  "recipient_id": "vendor-paypal-sandbox-1",
  "amount_minor": 2500,
  "currency": "USD",
  "purpose": "Monthly subscription renewal",
  "idempotency_key": "tx_unique_001",
  "anomaly_signal": null
}
```

#### Response (200 OK - ALLOW)
```json
{
  "request_id": "req_a1b2c3d4e5f60718",
  "decision": "ALLOW",
  "reasons": ["Amount within pre-authorized autonomous limits"],
  "reason_codes": ["PRE_AUTHORIZED"],
  "escalated": false,
  "event_id": "evt_000001_8a12f901",
  "intent_digest": "7a89f302b1c4e8590d9a62310188ef4a9b7e12f0a1d401ec8891000b0188992a",
  "evaluated_at_utc": "2026-10-22T12:00:00Z",
  "payout_id": "sandbox_tx_00000001"
}
```

#### Response (200 OK - STEP_UP)
```json
{
  "request_id": "req_f8e7d6c5b4a30219",
  "decision": "STEP_UP",
  "reasons": ["Amount exceeds instant threshold (50000); human approval required"],
  "reason_codes": ["INSTANT_THRESHOLD_EXCEEDED"],
  "escalated": false,
  "event_id": "evt_000002_4b98cf12",
  "intent_digest": "1e77aa99c8201a88bbfe1009832716a504b2ae41e4649b934ca495991b7852b8",
  "evaluated_at_utc": "2026-10-22T12:05:00Z",
  "payout_id": null
}
```

### 3.3 Payment Request Lookup (`GET /v1/payment-requests/{request_id}`)
Retrieves request state and stored evaluation outcome.

### 3.4 Mandate Management (`POST /v1/mandates`, `GET /v1/mandates/{id}`)
- `POST /v1/mandates`: Issues a newly signed Ed25519 mandate (principal only).
- `GET /v1/mandates/{id}`: Returns mandate parameters and signature seal.

### 3.5 Decision Query (`GET /v1/decisions/{decision_id}`)
Query decision record by decision ID or request ID.

### 3.6 Human Step-Up Approvals (`POST /v1/approvals/{request_id}`)
Authorizes or denies an escalated request. Enforces agent cannot approve (403), approver belongs to principal (403), and digest matches expected value (400 on tampering).

#### Request Body
```json
{
  "expected_digest": "1e77aa99c8201a88bbfe1009832716a504b2ae41e4649b934ca495991b7852b8",
  "decision": "ALLOW",
  "reason": "Approved by supervisor after manual verification"
}
```

### 3.7 Audit Ledger (`GET /v1/ledger`, `GET /v1/ledger/verify`)
- `GET /v1/ledger`: Returns append-only event stream.
- `GET /v1/ledger/verify`: Cryptographically verifies the SHA-256 hash chain from genesis to tail.

### 3.8 PayPal Webhook Ingestion (`POST /v1/webhooks/paypal`)
Verifies incoming PayPal webhook headers (`PAYPAL-AUTH-ALGO`, `PAYPAL-TRANSMISSION-SIG`), rejects unauthenticated/forged signatures with `401 Unauthorized`, and deduplicates replay attacks using PayPal event IDs.

### 3.9 Admin Reset (`POST /v1/admin/reset`)
Resets sandbox state, clearing spent budget tables and idempotency cache. Principal only.
