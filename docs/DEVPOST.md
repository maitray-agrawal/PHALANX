# PHALANX - Devpost Submission Copy

## Inspiration
Autonomous financial agents are rapidly advancing from passive advice to active execution—booking flights, paying SaaS invoices, and balancing treasury accounts. However, giving an LLM direct API access to corporate or personal payment rails is inherently dangerous: prompt injection attacks, catastrophic hallucination, and run-away loops can drain bank balances in seconds.

We built **PHALANX** (an AstraX product) to solve this fundamental trust barrier: **Agents can propose. Policies decide. Humans authorize exceptions. Every transaction leaves cryptographic evidence.**

---

## What It Does
PHALANX is an authorization, governance, and tamper-evident audit layer positioned between autonomous financial agents and payment rails (PayPal Sandbox):

1. **Ed25519-Signed Mandates**: Human principals grant bounded financial authority to agents via versioned, cryptographically signed mandates (capping single transactions, instant thresholds, lifetime budgets, allowed payees, and temporal windows).
2. **Pure Deterministic Policy Engine**: A mathematically pure policy core (zero I/O, zero clock, zero randomness, 1.10 µs evaluation latency) enforces hard financial boundaries.
3. **The LLM is Never in the Authorization Path**: Untrusted user text is isolated inside delimiters. Auxiliary ML/heuristic anomaly signals can only *tighten* a decision (`ALLOW` -> `STEP_UP` -> `DENY`), never loosen it.
4. **Digest-Locked Human Approvals**: Transactions exceeding instant thresholds require human step-up review bound to the RFC 8785 canonical SHA-256 intent digest. Any attempt to mutate transaction details after approval invalidates the hash and aborts payment.
5. **Cryptographic Shield-Wall Ledger**: Every decision is linked into an append-only SHA-256 hash chain (`prev_hash` -> `event_hash`). Any illicit SQL `UPDATE` or `DELETE` immediately breaks chain verification and is visually exposed.

---

## How We Built It
- **Backend & Core**: Python 3.12, FastAPI, Pydantic v2 (strict `extra="forbid"`), RFC 8785 Canonical JSON serialization, `cryptography` (Ed25519).
- **Architecture**: Clean Hexagonal Architecture (Ports and Adapters). An AST purity test enforces that `app/domain` imports zero external modules.
- **Frontend**: React + Vite + TypeScript, AG Grid, AstraX dark-control-room design system with Space Grotesk, Inter, and JetBrains Mono typography.
- **Testing & Security**: 230 automated unit, integration, and red-team tests covering threat catalog items A1 through H2 (prompt injection, digest mutation, replay attacks, privilege escalation, unmandated fallback rejection, mandate revocation recheck, and database tampering).
- **Model Context Protocol (MCP)**: Official Python FastMCP server (`mcp==1.3.0`) exposing authenticated agent payment request and status inspection without bypass paths.
- **Deployment**: Docker multi-stage build, non-root user, GitHub Actions CI, Render blueprint (`render.yaml`).

---

## How We Used PayPal
PHALANX integrates with the **PayPal Sandbox Payouts Rail**:
- Autonomous payments evaluated as `ALLOW` dispatch directly to PayPal Sandbox recipients.
- Transactions requiring `STEP_UP` hold dispatch until human supervisor approval is cryptographically verified.
- Inbound PayPal webhooks are deduplicated by event ID and verified via PayPal signature headers.

---

## Built With (AI Tools & Models Transparency)
In compliance with hackathon rules, this project was developed using:
- **Google Antigravity IDE & Antigravity Agentic Pair Programming**: Scaffolded architecture, automated refactoring, and test suite generation.
- **Gemini 2.5 Flash**: Assisting in documentation synthesis, threat modeling, and red-team test vector creation.

---

## Try It Out
- **Live Demo**: https://phalanx-api.onrender.com (API) & https://phalanx-web.onrender.com (UI)
- **GitHub Repository**: https://github.com/maitray-agrawal/PHALANX
- **Reset Demo State**: `POST /v1/admin/reset`
