# API Specifications & Model Context Protocol (MCP)

All protected endpoints require authentication via Bearer token (`Authorization: Bearer <token>`). Payloads use strict schemas (`extra="forbid"`), bounded strings, integer minor units, and RFC 7807 Problem+JSON error responses.

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
Available when `DEMO_MODE=true`:
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

1. **Payload Size Limit**: Hard cap at 64 KB (`MAX_REQUEST_BODY_BYTES = 65,536`). Payloads exceeding this limit return `413 Payload Too Large`.
2. **Rate Limiting**: Sliding-window rate limiter per identity/IP: 120 requests per minute. Exceeding limits returns `429 Too Many Requests`.
3. **Security Headers**:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; form-action 'self'`
   - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
   - `Referrer-Policy: no-referrer`
   - `Cache-Control: no-store, no-cache, must-revalidate`
4. **RFC 7807 Problem+JSON**: Standardized error envelope without internal stack trace leakage.
5. **Log Redaction**: Credentials, tokens, client secrets, and private keys are scrubbed from server logs.

---

## 3. Core REST Endpoints

### 3.1 Health & Probes
- `GET /healthz` -> `{"status": "ok"}`
- `GET /readyz` -> `{"status": "ready", "database": "healthy"}`
- `GET /health` -> `HealthStatusDTO`

### 3.2 Payment Authorization (`POST /v1/payments`)
Submits a proposed transaction intent for policy evaluation. Requires `agent` or `principal` role.

#### Request Body
```json
{
  "agent_id": "agent-auto-1",
  "recipient_id": "vendor-paypal-sandbox-1",
  "amount_minor": 2500,
  "currency": "USD",
  "purpose": "Monthly cloud hosting renewal",
  "idempotency_key": "tx_unique_001"
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
  "payout_id": "sandbox_tx_00000001",
  "request_state": "SETTLED"
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
  "payout_id": null,
  "request_state": "STEP_UP_REQUIRED"
}
```

### 3.3 Step-Up Queue & Approval (`GET /v1/approvals`, `POST /v1/approvals`)
- `GET /v1/approvals`: List pending approval requests (requires `approver` or `principal`).
- `POST /v1/approvals`: Authorize or reject a pending request bound to its intent digest.
  ```json
  {
    "request_id": "req_f8e7d6c5b4a30219",
    "intent_digest": "1e77aa99c8201a88bbfe1009832716a504b2ae41e4649b934ca495991b7852b8",
    "decision": "ALLOW",
    "approver_id": "approver-01"
  }
  ```

### 3.4 Orders v2 Lookup & Capture (`GET /v1/orders/{id}`, `POST /v1/orders/{id}/capture`)
- `GET /v1/orders/{order_id}`: Query order status on external PayPal rail.
- `POST /v1/orders/{order_id}/capture`: Execute capture on an approved order (requires `approver` or `principal`).

### 3.5 Mandates (`POST /v1/mandates`, `GET /v1/mandates/{id}`)
- `POST /v1/mandates`: Issue an Ed25519-signed mandate (requires `principal`).
- `GET /v1/mandates/{id}`: Inspect mandate parameters, budget limits, and signature seal.

### 3.6 Audit Ledger (`GET /v1/activity`, `GET /v1/ledger`)
- `GET /v1/activity`: Paginated activity feed with honest provider states.
- `GET /v1/ledger`: Cryptographic hash chain verification proof and block records.

### 3.7 Webhook Ingestion (`POST /v1/webhooks/paypal`)
Inbound webhook endpoint. Validates headers against PayPal signature check API and deduplicates event IDs.

---

## 4. Model Context Protocol (MCP) Tools

Autonomous agents connect over standard stdio transport using `mcp run app/mcp/server.py`:

| Tool Name | Arguments | Description |
|---|---|---|
| `request_payment` | `agent_id`, `recipient_id`, `amount_minor`, `currency`, `purpose`, `idempotency_key`, `auth_token` | Propose transaction for policy evaluation. |
| `get_mandate_status` | `mandate_id`, `auth_token` | Check active mandate limits and allowed payees. |
| `verify_ledger` | *(none)* | Check cryptographic audit chain integrity. |
