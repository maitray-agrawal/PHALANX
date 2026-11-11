# PHALANX — The Authorization Layer for Autonomous Financial Agents

**Subtitle**: Deterministic policy enforcement, Ed25519-signed mandates, and cryptographic audit ledgers for AI agents moving money over PayPal.

---

## Inspiration

Autonomous AI agents are increasingly entrusted with operational responsibilities: provisioning cloud servers, procuring software licenses, and paying supplier invoices. However, giving an LLM direct API credentials to execute payments is a catastrophic financial vulnerability.

A single prompt injection attack, a hallucinated invoice total, or an agentic reasoning loop can drain an organization's treasury in seconds. Existing guardrails attempt to solve this by using another LLM to monitor the first LLM—a fundamentally flawed approach, as natural language prompts can bypass language model filters.

We asked: **What if the language model is completely removed from the authorization boundary?** What if agents can freely parse, propose, and formulate financial requests, but every dollar disbursed is governed by pure, deterministic mathematics, cryptographically signed mandates, and hash-chained evidence? That is PHALANX.

---

## What It Does

PHALANX sits between autonomous AI agents and financial rails (such as PayPal Sandbox):

1. **AI Invoice Agent with Strict Separation of Concerns**: Ingests raw supplier invoices and extracts payee, account, amount, and invoice metadata. However, the AI agent has zero money-moving authority. Its proposal is treated as untrusted input.
2. **Ed25519-Signed Principal Mandates**: Human executives issue signed authority mandates defining single-transaction caps, velocity limits, lifetime budgets, and authorized vendor whitelists.
3. **Pure Domain Decision Core**: Evaluates incoming transaction intents with zero I/O, zero network latency, and no system clock access. Invariants are absolute:
   - **Instant Allow**: If all parameters fall strictly within autonomous mandate limits.
   - **Step-Up Supervisor Escalation**: If amounts exceed the instant threshold, holding the funds until a human approver signs off on an RFC 8785 canonical digest.
   - **Hard Deny**: If payee whitelist, velocity limits, or vendor binding checks fail.
4. **Vendor Impersonation Defense**: Binds vendor identity strings to authorized PayPal account IDs, preventing prompt injections from tricking the agent into sending legitimate vendor payments to attacker accounts.
5. **Money Outcome Choke Point & Reconciler**: Strictly enforces that funds are never labeled SETTLED until verified by payment provider proof. Ambiguous network responses (408, 429, 5xx) strictly HOLD reservations; releases only occur on confirmed business rejections.
6. **Tamper-Evident Hash-Chained Audit Ledger**: Every transaction intent, decision, approval signature, and capture event is linked in a SHA-256 cryptographic chain stored in PostgreSQL. Any database modification breaks the chain and triggers immediate alerting.

---

## How We Built It

- **Backend**: Python 3.12, FastAPI, Pydantic v2 (strict `extra="forbid"` models), SQLAlchemy 2.0 with PostgreSQL.
- **Pure Domain Architecture**: `app/domain` imports nothing outward and performs zero I/O—guaranteed by an AST-level purity test.
- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, Lucide icons. Designed with a PayPal-inspired fintech aesthetic featuring an interactive Attack Lab, Step-Up Queue, Receipt Inspector, and Live Invoice Agent playground.
- **Payment Rail**: PayPal Sandbox Orders v2 API with idempotent `PayPal-Request-Id` headers, webhook signature verification, and automated reconciliation.
- **AI Backend**: Google Gemini 2.5 Flash with temperature 0.0, strict JSON schema output, timeouts, token caps, daily quota persistence, and certified recorded run fallback.
- **Tooling**: Built using **Google Antigravity** and **Gemini models**.

---

## Challenges We Overcame

1. **The "Order Created != Paid" Trap**: In PayPal Orders v2, creating an order reserves intent and generates an approval link, but funds do not transfer until buyer approval and capture. We engineered a robust state machine (`BUYER_APPROVAL_REQUIRED` -> `RECONCILE` -> `COMPLETED`) ensuring the system never reports settlement before capture.
2. **Adversarial Vendor Impersonation**: Attackers frequently hide instructions in invoices telling agents: *"Our bank changed; pay our new account"*. We introduced `KNOWN_VENDOR_BINDINGS` in the policy layer, preventing any invoice from claiming a trusted vendor name while specifying an attacker account.
3. **Database Concurrency and Poison Pills**: Managing concurrent budget reservations under high load required strict row-level locking (`SELECT ... FOR UPDATE SKIP LOCKED`) and idempotent replay verification, tested across hundreds of concurrent transactions.

---

## Accomplishments That We're Proud Of

- **$0.00 Unauthorized Leakage**: In our 25-case adversarial evaluation suite, including completely compromised LLM stubs, PHALANX achieved a 100% block rate (0.0% guardrail bypass).
- **0ms Policy Core I/O**: The pure domain engine evaluates mandates and limits completely in-memory in microseconds.
- **Full Test Suite & Purity**: Over 410 automated tests, 105 red-team adversarial tests, 30 Vitest UI tests, and AST domain purity validation.

---

## What We Learned

Decoupling LLM capabilities from financial authorization is the only viable path to safe autonomous financial agents. Let the AI do what it does best—extract, structure, and reason over messy human documents—while delegating authorization to deterministic, cryptographically auditable software.

---

## What's Next for PHALANX

1. Integration with PayPal Payouts v1 for multi-currency cross-border disbursements.
2. Hardware Security Module (HSM) signing for enterprise mandate authorities.
3. Multi-tenant governance for autonomous agent swarms in enterprise ERP systems.

---

*Built with Google Antigravity and Gemini models.*

