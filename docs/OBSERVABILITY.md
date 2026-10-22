# OBSERVABILITY - Metrics, Logging, and Audit Trails

## 1. Structured Logging & Request Tracing

PHALANX implements structured JSON access logging on all HTTP endpoints via [`RequestIdAndStructuredLoggingMiddleware`](file:///d:/PHALANX/app/api/middleware.py).

### 1.1 Log Format
Every HTTP request generates a structured single-line JSON log entry on stdout:
```json
{
  "timestamp": "2026-10-22T16:26:52.291434+00:00",
  "request_id": "req_7aabbe6e3cd5474b",
  "method": "POST",
  "path": "/v1/approvals/req_stepup_1001",
  "status_code": 200,
  "latency_ms": 3.62,
  "client_ip": "127.0.0.1"
}
```

### 1.2 Request ID Propagation
- Every incoming request is checked for an existing `X-Request-ID` header.
- If absent, a unique cryptographic identifier (`req_{hex16}`) is generated using `uuid.uuid4()`.
- The `X-Request-ID` is stamped onto all outbound HTTP response headers for distributed tracing and client correlation.

---

## 2. Sensitive Data Redaction (Manual 30)

All application logs pass through [`LogRedactionFilter`](file:///d:/PHALANX/app/api/middleware.py) before reaching standard output:
- **Redacted Tokens**: Any Bearer token, PayPal client secret, webhook signature, or private signing key is automatically detected via regex and replaced with `[REDACTED]`.
- **Zero-Secret Guarantee**: Private Ed25519 keys, client secrets, and sensitive tokens are never printed in traces or error bodies.

---

## 3. Health & Diagnostic Probes

| Endpoint | Probe Type | Purpose | Success Condition |
| :--- | :--- | :--- | :--- |
| `GET /healthz` | Liveness | Verifies Python web server is responsive and serving requests. | HTTP 200 `{"status": "ok"}` |
| `GET /readyz` | Readiness | Verifies database connectivity by executing `SELECT 1`. | HTTP 200 `{"status": "ready"}` (Returns 503 if DB unreachable) |
| `GET /health` | Diagnostics | System diagnostic endpoint reporting service version and UTC timestamp. | HTTP 200 `{"status": "ok", "version": "0.1.0"}` |
| `GET /v1/ledger/verify` | Integrity | Cryptographic audit probe verifying SHA-256 hash chain links. | HTTP 200 `{"is_valid": true, "total_events": N}` |

---

## 4. Latency Performance Benchmarks

Based on automated workload benchmarking ([`docs/TEST_REPORT.md`](file:///d:/PHALANX/docs/TEST_REPORT.md)):
- **Policy Engine Pure Evaluation Latency**:
  - Median: **0.021 ms** (21 microseconds)
  - 95th Percentile (p95): **0.043 ms** (43 microseconds)
- **End-to-End API Authorization Latency** (including authentication, validation, ledger write):
  - Local SQLite / In-Memory: **2.8 ms - 4.2 ms**
  - Remote Managed PostgreSQL: **18 ms - 32 ms** (dominated by network round-trip time)
- **Render Cold-Start Wakeup Latency**:
  - Typical cold wake: **32.4 seconds**
  - Warm response via [`scripts/pinger.py`](file:///d:/PHALANX/scripts/pinger.py): **< 85 ms**

---

## 5. Audit Ledger Hash Chaining

The ledger table `ledger_events` serves as the cryptographic ground truth:
- Each event row stores:
  - `event_seq`: Monotonically increasing sequence number (0, 1, 2, ...).
  - `prev_hash`: SHA-256 hash of the preceding ledger record (Genesis block uses `0000...0000`).
  - `event_hash`: `SHA-256(prev_hash + canonical_json(event_payload))`.
- Any manual SQL modification (`UPDATE` or `DELETE`) is rejected at the database level by trigger `trg_deny_ledger_mutation`.
- If tampering occurs outside the trigger (e.g. database file corruption), `GET /v1/ledger/verify` immediately flags `is_valid: false` and points to the exact `broken_index`.
