# PHALANX Automated Security Test Report
Generated: 2026-10-22 12:28:38 UTC
Suite: Red-Team & Adversarial Invariant Suite (`tests/redteam/test_redteam.py`)

## Disclaimer
> [!IMPORTANT]
> A finite test suite does not mathematically prove absolute security.
> This report verifies that the deterministic policy engine, hash chain, Ed25519 seals,
> and grounding validators defend against the catalogued attacks under tested conditions.

---

## 1. Attack Family Verification Summary

| Catalog ID | Threat Scenario | Denominator | Passed | Pass Rate | Wilson 95% CI |
|---|---|---|---|---|---|
| **A1-Ext** | Direct Prompt Injection Corpus | 30 / 30 | 30 | 100% | [88.6%, 100.0%] |
| **A2-A3** | Advisory ML Signal Escalation Only | 2 / 2 | 2 | 100% | Invariant |
| **B1** | Ed25519 Mandate Signature Mutation | 1 / 1 | 1 | 100% | Verified |
| **C1** | Boundary Exploits (Negative Minor Units) | 1 / 1 | 1 | 100% | Blocked |
| **D1** | Idempotency Replay with Altered Payload | 1 / 1 | 1 | 100% | DENY |
| **E1** | Step-Up Approval Digest Tampering | 1 / 1 | 1 | 100% | Digest Lock |
| **F1** | Unsigned PayPal Webhook Rejection | 1 / 1 | 1 | 100% | 401 Rejection |
| **G1** | Agent Privilege Escalation to Approver | 1 / 1 | 1 | 100% | 403 Forbidden |
| **H1-H2** | Audit Ledger Row Tampering Detection | 2 / 2 | 2 | 100% | Chain Caught |

**Overall Result**: 83/83 Unit, Integration & Red-Team Tests Passed (100%).
**Hard Policy Violations Accepted**: **0**

---

## 2. Policy Engine Performance & Latency Benchmark
Sample Size: 2,000 pure policy evaluations (zero I/O, zero clock, zero randomness)

- **Median Latency**: **1.10 µs**
- **p95 Latency**: **1.20 µs**
- **Throughput Capability**: > 100,000 deterministic decisions / second per CPU core

---

## 3. Threat Model Defense Matrix
- **Prompt Injection**: Text is wrapped in data delimiters; logic is deterministic.
- **Asymmetric Risk**: Heuristics only tighten (`ALLOW` -> `STEP_UP` -> `DENY`).
- **Approval Anti-Tamper**: Locked to SHA-256 digest of canonical intent.
- **Audit Immobility**: Every block chains `prev_hash` to `event_hash`.
