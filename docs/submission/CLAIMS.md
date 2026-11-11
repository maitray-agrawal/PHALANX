# PHALANX Architectural & Security Claims Verification Matrix

This matrix maps every core capability and security invariant of PHALANX to its exact file:line implementation, verifying test command, and test result.

| Claim | Architectural Invariant | Implementation (File:Line) | Verifying Test Command | Test Result |
| :--- | :--- | :--- | :--- | :--- |
| **C1. Pure Domain Boundary** | `app/domain` contains zero I/O, no network calls, no clock, and no outer imports. | `app/domain/policy.py:1-120`<br>`app/domain/money_outcome.py:1-60` | `pytest tests/unit/test_domain_purity.py` | `6 passed in 0.18s` |
| **C2. LLM Never Authorizes** | The LLM is strictly an untrusted data extractor; decisions are deterministic. | `app/application/invoice_agent.py:307-365`<br>`app/domain/policy.py:30-100` | `pytest tests/unit/test_invoice_agent.py -v` | `14 passed in 1.33s` |
| **C3. Vendor Impersonation Defense** | Payee names are bound to authorized recipient accounts; mismatches trigger hard DENY. | `app/domain/policy.py:84-118`<br>`app/domain/models.py:30-40` | `pytest tests/integration/test_invoice_agent_api.py::test_process_invoice_sample_d_impersonation_blocked` | `PASSED` |
| **C4. Money Outcome Choke Point** | No money moves without provider proof; 408/429/5xx strictly HOLD; release only on explicit business rejection. | `app/domain/money_outcome.py:27-60`<br>`app/domain/ports.py:38-48` | `pytest tests/unit/test_money_outcome.py -v`<br>`pytest tests/unit/test_may_release_and_rail.py` | `197 passed`<br>`9 passed` |
| **C5. Auditor Role Lockdown** | `Role.AUDITOR` cannot invoke mutating endpoints (POST, PUT, DELETE, PATCH). | `app/api/routes.py:120-1300` | `pytest tests/integration/test_api.py -k test_all_mutating_routes_reject_auditor` | `PASSED (21 checked)` |
| **C6. Idempotent Replay Integrity** | Idempotency replay returns the real stored request state, never SETTLED by default. | `app/application/services.py:928-949`<br>`app/application/services.py:795-850` | `pytest tests/unit/test_may_release_and_rail.py::test_duplicate_order_replay_does_not_create_duplicate_order` | `PASSED` |
| **C7. Order Created != Settled** | PayPal Orders v2 creation yields `RECONCILE`; never `SETTLED` before capture. | `app/infrastructure/paypal.py:460-472`<br>`app/application/services.py:1169-1180` | `pytest tests/unit/test_may_release_and_rail.py::test_release_site_capture_order` | `PASSED` |
| **C8. Fail-Closed Rail Config** | Missing credentials or 401 OAuth error aborts with 503 before any budget reservation. | `app/application/services.py:1034-1051`<br>`app/infrastructure/paypal.py:240-277` | `pytest tests/unit/test_may_release_and_rail.py::test_wrong_oauth_secret_returns_503_before_reservation` | `PASSED` |
| **C9. Cryptographic Audit Ledger** | Events form an immutable SHA-256 hash chain; tampering breaks chain verification. | `app/infrastructure/ledger.py:30-110`<br>`app/application/services.py:1300-1400` | `pytest tests/integration/test_ledger.py` | `PASSED` |
| **C10. Step-Up Canonical Digest** | Escalations require human supervisor approval bound to RFC 8785 canonical JSON digest. | `app/domain/models.py:50-80`<br>`app/application/services.py:1450-1550` | `pytest tests/integration/test_approvals.py` | `PASSED` |

