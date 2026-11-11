# PHALANX — Judge Technical FAQ (10 Deep-Dive Security & Architectural Questions)

This document addresses 10 rigorous technical questions that a PayPal platform engineer, security architect, or hackathon judge would ask about PHALANX.

---

### Q1: Why not just use prompt engineering or system instructions to tell the LLM never to exceed limits or pay unapproved accounts?
**Answer**: Prompt engineering is an advisory boundary, not a security boundary. A language model processes instructions and untrusted data in the same context window; adversarial prompt injection, token manipulation, or nested delimiter escapes can reliably circumvent LLM-based guardrails. In PHALANX, the LLM is strictly an untrusted data extractor. The authorization boundary is deterministic Python code governed by mathematical policy rules and Ed25519-signed mandates. Even if the LLM is completely compromised and outputs an attacker-controlled account, PHALANX's policy engine blocks 100% of unauthorized transfers.  
**Pointers**: `app/domain/policy.py:30-115`, `tests/unit/test_invoice_agent.py`.

---

### Q2: What happens if PayPal returns a 500 error, 408 timeout, or 429 rate limit during payment execution? Could money be disbursed twice?
**Answer**: Transient network errors (408, 429, 5xx) or gateway timeouts are classified as ambiguous states (`RECONCILE` or `LOOKUP_FAILED`). In PHALANX, reservations are strictly held in a pending state until an out-of-band provider lookup confirms the true provider status. The reservation is released if and only if PayPal provides an explicit business rejection (`business_rejection=True`). Idempotency keys (`PayPal-Request-Id` headers) are submitted with all rail calls, ensuring replayed requests never create duplicate disbursements.  
**Pointers**: `app/domain/money_outcome.py:27-60`, `app/infrastructure/paypal.py:473-508`, `tests/unit/test_may_release_and_rail.py`.

---

### Q3: Can an autonomous agent approve its own step-up exception?
**Answer**: No. Step-up approval strictly requires the `APPROVER` or `PRINCIPAL` role. Role-based access control enforces that tokens bearing `Role.AGENT` or `Role.AUDITOR` receive a `403 Forbidden` if they attempt to approve an escalated transaction. Furthermore, the approval payload requires an RFC 8785 canonical JSON digest (`expected_digest`) matching the exact intent parameters; tampering with any field invalidates the approval.  
**Pointers**: `app/api/routes.py:640-695`, `tests/redteam/test_attack_lab.py`.

---

### Q4: How do you prevent an attacker from modifying an invoice's payment account while keeping a legitimate vendor name (Vendor Impersonation)?
**Answer**: We enforce `KNOWN_VENDOR_BINDINGS` in the policy layer. If an invoice claims to originate from an established supplier (e.g., "Acme Cloud Hosting Services"), the policy engine checks whether the destination account matches the pre-registered account bound to that vendor identity. If an attacker's invoice claims the vendor name but directs payment to an unauthorized account, PHALANX rejects the transaction with `PolicyReasonCode.VENDOR_IMPERSONATION`, preventing auto-allowance even if the account is syntactically valid.  
**Pointers**: `app/domain/policy.py:84-118`, `tests/integration/test_invoice_agent_api.py::test_process_invoice_sample_d_impersonation_blocked`.

---

### Q5: In PayPal Orders v2, why don't you mark the transaction settled when the order is created?
**Answer**: Creating an order in PayPal Orders v2 (`POST /v2/checkout/orders`) with `intent="CAPTURE"` merely reserves the order and generates an approval link; funds are not moved until buyer approval and capture occur. Marking an order `SETTLED` upon creation is a critical accounting bug. PHALANX places the transaction in `RequestState.RECONCILE` awaiting buyer sandbox authorization, and only settles upon verified capture execution.  
**Pointers**: `app/infrastructure/paypal.py:460-472`, `app/application/services.py:1169-1180`, `scripts/e1_sandbox_check.py`.

---

### Q6: What prevents a malicious database administrator or SQL injection from altering the audit log in PostgreSQL?
**Answer**: PHALANX employs defense-in-depth:
1. **Cryptographic Hash Chaining**: Every `ledger_events` row contains `prev_hash` and `event_hash = SHA256(prev_hash + event_seq + event_type + canonical_payload)`. Modifying, inserting, or deleting any historical record breaks the chain, detected by `GET /v1/ledger/verify`.
2. **Database Immutability Triggers**: PostgreSQL triggers (`append_only_ledger` and `no_truncate_ledger`) abort any `UPDATE`, `DELETE`, or `TRUNCATE` operations on `ledger_events` at the database engine level.  
**Pointers**: `app/infrastructure/ledger.py:30-110`, `docs/evidence/neon-manual-setup.md`, `tests/integration/test_ledger.py`.

---

### Q7: How does your system handle concurrent payment requests from multiple agent instances trying to drain the same budget?
**Answer**: PHALANX uses database row-level locking via SQLAlchemy `SELECT ... FOR UPDATE` on the agent's budget record (`AgentBudgetModel`). When concurrent transactions arrive, they are queued serially in PostgreSQL, ensuring that lifetime budget limits and rolling velocity caps are calculated atomically without race conditions.  
**Pointers**: `app/infrastructure/database.py`, `tests/concurrency/test_transaction_audit.py`.

---

### Q8: Why is the domain logic pure, and how is purity enforced?
**Answer**: `app/domain` contains zero I/O, no network calls, no clock, and no outer imports. This guarantees that policy decisions are completely deterministic, reproducible, and verifiable in milliseconds without external side effects. Purity is enforced on every commit by an automated Abstract Syntax Tree (AST) test that inspects `app/domain` and fails if any disallowed import or side effect is introduced.  
**Pointers**: `app/domain/policy.py`, `tests/unit/test_domain_purity.py`.

---

### Q9: What happens if the Gemini API is down, rate-limited, or out of budget?
**Answer**: PHALANX implements a resilient fallback architecture. Calls to Gemini feature strict timeouts (10s), 1 retry on network errors, and daily budget tracking persisted in PostgreSQL (`daily_quotas`). If the API key is not configured, if Gemini experiences an outage, or if the daily quota is reached, the Invoice Agent gracefully falls back to certified recorded runs, clearly labeled as `RECORDED RUN (Offline Fallback)`. The system never blocks operations or silently fails open.  
**Pointers**: `app/infrastructure/gemini.py:65-175`, `app/application/invoice_agent.py:260-305`.

---

### Q10: How do you verify that inbound PayPal webhooks are genuinely from PayPal and not spoofed by an attacker?
**Answer**: Webhook verification verifies the cryptographic signature against PayPal's public certificates. Before calling PayPal's verification endpoint, PHALANX validates the webhook certificate URL using strict security invariants: scheme must be HTTPS, host must be strictly within `{api.paypal.com, api.sandbox.paypal.com, api-m.paypal.com, api-m.sandbox.paypal.com}`, with no userinfo and no custom port. Only verified webhooks with matching event signatures are processed.  
**Pointers**: `app/infrastructure/paypal.py:30-60, 737-805`, `tests/integration/test_reconciliation.py`.
