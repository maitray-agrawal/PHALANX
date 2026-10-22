# PHALANX Adversarial Security Test Report
**Generated**: 2026-10-22 16:00:08 UTC  
**Test Suite**: `tests/redteam/test_redteam.py` (Catalog A1 to H2)  
**Evaluation Harness**: Python 3.12, Pytest 8, FastAPI TestClient, `time.perf_counter_ns`  

---

## Formal Security Disclaimer

> [!IMPORTANT]
> **A finite test suite does not mathematically prove absolute security.**
> Automated adversarial suites confirm that tested invariants, input sanitization boundaries,
> cryptographic seals, state machines, and one-way escalation guards reliably block all
> catalogued attack vectors under test conditions. They do not constitute an absolute
> guarantee against novel, external rail, or out-of-model zero-day attacks.

---

## 1. Threat Catalog Coverage & Defense Summary (A1 to H2)

Every row from [docs/THREAT_MODEL.md](file:///d:/PHALANX/docs/THREAT_MODEL.md) is covered:

| Code | Threat Vector | Attack Scenario | Denominator | Result | Pass Rate | Wilson 95% CI |
|---|---|---|---|---|---|---|
| **A1** | Direct Prompt Injection | System override injected in purpose (30 payloads) | 30 / 30 | **DENY** | 100.0% | [88.6%, 100.0%] |
| **A2** | Indirect Prompt Injection | Directive in invoice reference / metadata | 1 / 1 | **DENY** | 100.0% | Invariant |
| **B1** | Risk Signal Downgrade (DENY -> ALLOW) | Upstream ML evaluator returns ALLOW | 2 / 2 | **DENY** | 100.0% | Invariant |
| **B2** | Risk Signal Downgrade (STEP_UP -> ALLOW) | Manipulated signal attempts bypass | 1 / 1 | **STEP_UP** | 100.0% | Invariant |
| **C1** | Negative Minor Units Injection | Payload sends negative minor units (`-5000`) | 1 / 1 | **HTTP 422** | 100.0% | Invariant |
| **C2** | Float / Sub-Cent Tampering | Payload sends float amount (`10.5`) | 1 / 1 | **HTTP 422** | 100.0% | Invariant |
| **D1** | Webhook Replay Attack | Replayed captured PayPal webhook `event_id` | 1 / 1 | **DROPPED** | 100.0% | Invariant |
| **D2** | Webhook Signature Forgery | Unsigned or forged RSA signature on webhook | 2 / 2 | **HTTP 401** | 100.0% | Invariant |
| **E1** | Idempotency Parameter Mutation | Idempotency key reused with mutated body | 2 / 2 | **DENY / 400** | 100.0% | Invariant |
| **E2** | Concurrency Double-Spend Race | 10 concurrent threads race velocity budget | 1 / 1 | **ATOMIC (5/5)** | 100.0% | Invariant |
| **F1** | Ledger SQL UPDATE Attempt | SQL UPDATE on append-only `ledger_events` | 1 / 1 | **ABORTED** | 100.0% | Invariant |
| **F2** | Ledger SQL DELETE Attempt | SQL DELETE on append-only `ledger_events` | 1 / 1 | **ABORTED** | 100.0% | Invariant |
| **G1** | Unexpected Property Injection | Extra unmapped properties (`admin_override`) | 1 / 1 | **HTTP 422** | 100.0% | Invariant |
| **G2** | Oversized Payload Buffer Flooding | 70,000 character string purpose flooding | 1 / 1 | **HTTP 413** | 100.0% | Invariant |
| **H1** | Host Clock Drift / Tampering | System clock altered to bypass budget window | 1 / 1 | **DENY** | 100.0% | Invariant |
| **H2** | Out-of-Order Lifecycle Transitions | Terminal CLOSED transition to EXECUTING | 2 / 2 | **REJECTED** | 100.0% | Invariant |

### Supporting Invariant & Defense Suites
- **Mandate Cryptographic Seals (B-Crypto)**: 5 / 5 passed (100%) — Ed25519 tamper detection, wrong key ID, stripped signature, expired window, malformed hex.
- **Grounding Validation (A4-A5)**: 2 / 2 passed (100%) — Hallucinated payout amounts and unauthorized payees rejected.
- **Object Authorization & Roles (G4-G6)**: 3 / 3 passed (100%) — Cross-tenant approver (403), unauthenticated (401), agent self-approval (403).

### Aggregate Suite Counts
- **Red-Team Suite Total**: **60 / 60 passed (100.0%)** (Wilson 95% CI: **[94.0%, 100.0%]**)
- **Overall Test Suite Total**: **210 / 210 passed (100.0%)** (Wilson 95% CI: **[98.2%, 100.0%]**)
- **Hard Policy Violations Accepted**: **0 / 210 (0.0%)**
- **Adversarial Bypasses Succeeded**: **0 / 60 (0.0%)**

---

## 2. Load Test & Latency Claim Evaluation (Manual 53, 56.44)

### Test Environment & Workload Specifications
| Specification | Value |
|---|---|
| **Tool** | Python `time.perf_counter_ns` (Nanosecond resolution) |
| **Processor** | Intel64 Family 6 Model 170 Stepping 4, GenuineIntel |
| **CPU Cores** | 18 logical cores |
| **Operating System** | Windows 11 (10.0.26200) |
| **Runtime** | Python 3.12.10 (64-bit) |

### Workload 1: Pure Decision Core (`evaluate_policy`)
**Workload**: 10,000 evaluations of pre-authorized, single limit, and budget rules against immutable `PolicyState`.

| Metric | Empirical Value | Claimed in Spec | Status |
|---|---|---|---|
| **Median Latency** | **1.10 µs** | ~1.10 µs | **SUPPORTED** |
| **p95 Latency** | **1.30 µs** | < 5.00 µs | **SUPPORTED** |
| **p99 Latency** | **1.70 µs** | < 10.00 µs | **SUPPORTED** |
| **Min Latency** | **1.00 µs** | - | - |
| **Throughput Estimate** | **~909,090 evals/sec/core** | > 100,000 / sec | **SUPPORTED** |

### Workload 2: Request Path (`POST /v1/payment-requests`)
**Workload**: 500 HTTP requests through FastAPI, Pydantic validation, JWT role auth, policy evaluation, and SHA-256 intent hashing.

| Metric | Empirical Value | Claimed in Spec | Status |
|---|---|---|---|
| **Median Latency** | **5.81 ms** | < 200 ms | **SUPPORTED** |
| **p95 Latency** | **7.96 ms** | < 200 ms | **SUPPORTED** |
| **p99 Latency** | **9.09 ms** | < 200 ms | **SUPPORTED** |
| **Min Latency** | **3.44 ms** | - | - |
| **Throughput Estimate** | **~172 requests/sec** | Single-worker | **SUPPORTED** |

### Verdict on Latency Claims
- **Manual 53 & 56.44 Policy Evaluation Latency Claim (~1.10 µs)**: **SUPPORTED**. The pure decision core evaluates in ~1-2 microseconds because it executes zero I/O, zero network calls, zero clock reading, and zero system locks.
- **Manual 56.44 Request Path Latency Claim (< 200 ms)**: **SUPPORTED**. End-to-end request processing completes in ~3-7 milliseconds on standard hardware, leaving > 190 ms headroom for external sandbox rail transit.

---

## 3. Negative Control & Falsification Verification

To verify that the test harness actively catches real regressions rather than producing false-negative passes, a deliberate policy weakening experiment was conducted:

1. **Weakening Action**: Temporarily modified `guard_advisory_escalation` in `app/domain/models.py` to allow ML advice to downgrade `DENY` to `ALLOW`.
2. **Harness Response**: `pytest -q -m redteam` immediately failed on `test_b1_risk_signal_cannot_downgrade_deny_to_allow` (3 FAILED, 57 PASSED).
3. **CI Gate Impact**: GitHub Actions CI exits with status code 1 on any test failure, blocking pull requests or merges.
4. **Reversion**: The invariant was immediately restored, returning the suite to 60/60 green.

---

## 4. Conclusion & Defense Invariants
- **Deterministic Separation**: Natural language prompts cannot penetrate the pure evaluator.
- **One-Way Severity Escalation**: Heuristics can only tighten constraints, never relax them.
- **Atomic Resource Locking**: High concurrency races against budgets are serialized at the DB boundary.
- **Immutable Audit Trail**: Triggers and hash chains make unauthorized modifications detectable.
