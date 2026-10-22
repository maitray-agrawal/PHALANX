# ROADMAP - Delivery Phases & Cut Order

Owner prompt: P1

---

## 1. Phase Schedule (P0 to P12)

The delivery timeline spans October 22 through November 22, 2026, explicitly accounting for the **scheduled away window from October 28 to November 4, 2026** (no active development during this period).

| Phase | Milestone Name | Target Date | Scope & Deliverables | Gate Status |
|---|---|---|---|---|
| **P0** | **Bootstrap & Foundation** | 22 Oct 2026 | Layout, FastAPI `/healthz`/`/readyz`, domain purity test, Dockerfile, docker-compose, CI. | **Completed** |
| **P1** | **Security Architecture & Review** | 22–23 Oct 2026 | Brutal review, `PRD.md`, `THREAT_MODEL.md`, `SECURITY.md`, `TESTING.md`, `ROADMAP.md`. | **Active** |
| **P2** | **Sandbox Evidence & PayPal Spike** | 24–25 Oct 2026 | PayPal Sandbox spike; OAuth token acquisition; verify endpoints; populate `EVIDENCE.md`. | Upcoming |
| **P3** | **Core Domain & Policy Engine** | 26–27 Oct 2026 | Deterministic policies (single limit, velocity window, allowlist); mandate sealing. | Upcoming |
| — | **AWAY WINDOW (No Dev)** | **28 Oct – 04 Nov** | **Repository frozen. No development activity.** | — |
| **P4** | **PostgreSQL & Append-Only Ledger** | 05–06 Nov 2026 | SQLAlchemy 2 models, Alembic migrations, DB role privileges (INSERT/SELECT only). | Upcoming |
| **P5** | **Idempotency & Concurrency Controls** | 07–08 Nov 2026 | Row-level locking on balance reservations, idempotency keys, race condition tests. | Upcoming |
| **P6** | **PayPal Sandbox Rail Integration** | 09–10 Nov 2026 | Orders/Payouts client adapter, webhook signature verification, webhook deduplication. | Upcoming |
| **P7** | **Advisory ML & Heuristic Evaluator** | 11–12 Nov 2026 | Risk signal evaluator integration; asymmetric escalation (`ALLOW` -> `STEP_UP` -> `DENY`). | Upcoming |
| **P8** | **Operator Console & Review Queue** | 13–14 Nov 2026 | AG Grid audit ledger, real-time step-up approval queue, AstraX theme tokens. | Upcoming |
| **P9** | **Red-Team Hardening & Coverage** | 15–16 Nov 2026 | Implementation of all catalog tests (A1 to H2); enforcement of 100% domain coverage. | Upcoming |
| **P10** | **Deployment & Observability** | 17–18 Nov 2026 | Deploy to Render, healthcheck probes, structured logging, runbooks. | Upcoming |
| **P11** | **Fresh-Machine Clean Verification** | 19–20 Nov 2026 | Clean clone test on fresh environment, end-to-end smoke test, performance checks. | Upcoming |
| **P12** | **Final Review & Submission** | 21–22 Nov 2026 | Vibe-code audit, final gates audit, demo video recording, hackathon submission package. | Upcoming |

---

## 2. The Strict Cut Order (Scope Compression Protocol)

If development time is compressed due to external dependencies or unexpected technical debt, features will be trimmed strictly in the following priority order:

1. **Cut First: Web UI Micro-Animations & Custom Theming**
   - *Impact*: Low. The AG Grid table and approval buttons will retain basic, clean functional styles without custom visual polish.
2. **Cut Second: Complex Heuristic Scoring**
   - *Impact*: Low. Fall back strictly to deterministic limits (single-transaction amount threshold and 24h rolling velocity cap) without auxiliary anomaly model inputs.
3. **Cut Third: Multi-Cloud / Render Deployment**
   - *Impact*: Medium. If cloud hosting faces deployment friction, fall back to reproducible local Docker Compose demonstration (`docker compose up`).
4. **Cut Fourth: Secondary Payment Rails**
   - *Impact*: Medium. Focus solely on PayPal Sandbox Orders; omit Payouts batch automation.

### What We Will NEVER Cut
Under no circumstances will the following core security guarantees be sacrificed:
- **Pure Domain Isolation**: AST purity test must pass.
- **Integer Minor Units**: No floating point currency math.
- **Append-Only Ledger**: Database-level immutability enforcement.
- **Deterministic Policy Supremacy**: LLMs will never hold authorization authority.
- **Adversarial Red-Team Suite**: All catalog tests must run and pass.
