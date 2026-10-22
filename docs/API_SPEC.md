# API_SPEC - API Specifications & Contracts

All endpoints return JSON and accept strict schemas (`extra="forbid"`).

---

## 1. Health & Probes
- `GET /healthz` -> `{"status": "ok"}`
- `GET /readyz` -> `{"status": "ready", "database": "healthy"}`
- `GET /health` -> `HealthStatusDTO`

---

## 2. Payment Requests (`POST /v1/payment-requests`)
Submits a proposed transaction intent for policy evaluation.

### Request Body
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

### Response (200 OK - ALLOW)
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

### Response (200 OK - STEP_UP)
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

---

## 3. Human Step-Up Approvals (`POST /v1/approvals/{request_id}`)
Authorizes or denies an escalated request.

### Headers
- `X-Phalanx-Role`: `approver` or `principal` (caller role `agent` is rejected with `403 Forbidden`).

### Request Body
```json
{
  "expected_digest": "1e77aa99c8201a88bbfe1009832716a504b2ae41e4649b934ca495991b7852b8",
  "decision": "ALLOW",
  "reason": "Approved by CFO after invoice verification"
}
```

### Response (200 OK)
Returns updated `AuthorizationResponseDTO` with `decision: "ALLOW"` and dispatched `payout_id`.

---

## 4. Mandate Management (`POST /v1/mandates`, `GET /v1/mandates/{id}`)
- `POST /v1/mandates`: Issues a newly signed Ed25519 mandate.
- `GET /v1/mandates/{id}`: Returns mandate parameters and signature seal.

---

## 5. Audit Ledger & Verification (`GET /v1/ledger`, `GET /v1/ledger/verify`)
- `GET /v1/ledger`: Returns all chained events with `prev_hash` and `event_hash`.
- `GET /v1/ledger/verify`:
```json
{
  "is_valid": true,
  "message": "Verified chain of 15 events",
  "broken_index": null,
  "total_events": 15
}
```

---

## 6. Admin Reset (`POST /v1/admin/reset`)
Resets demo sandbox counters, clearing spent budget and idempotency tables for demo sessions.
