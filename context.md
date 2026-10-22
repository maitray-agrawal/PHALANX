# context.md
Phase: P11 Complete   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, LLM intent extraction & grounding validator.
- app/infrastructure: Ed25519 signing/verification, append-only ledger adapter, PayPal Sandbox rail adapter, UTC clock.
- app/api: Complete FastAPI REST suite (/v1/payment-requests, /v1/mandates, /v1/approvals, /v1/ledger, /v1/webhooks/paypal, /v1/admin/reset).
- app/mcp: Model Context Protocol server exposing financial agent governance tools.
- web: React + Vite + TypeScript dashboard in AstraX design system with 4 operational scenes (Request Console, Step-Up Approvals, Tamper-Evident Ledger, Active Mandate).
- tests: 83 automated tests (unit, integration, concurrency, red-team A1-H2).

Completed:
- P0: Bootstrap layout, Dockerfile, docker-compose.yml, CI workflows, and AST domain purity test.
- P1: PRD, Threat Model (STRIDE + A1-H2), Security controls audit, and Testing strategy.
- P2: Ed25519 mandate schema, versioning, canonical RFC 8785 JSON serialization, and cryptographic verification.
- P3: Pure deterministic policy engine with precedence hierarchy, instant thresholds, lifetime budget caps, and asymmetric risk escalation.
- P4: Cryptographic SHA-256 hash-chained ledger (`prev_hash` -> `event_hash`), anti-tampering verification, and PayPal rail adapter.
- P5: Comprehensive API routes with object-level authorization, role separation (agent vs approver), and PayPal webhook signature verification.
- P6: LLM intent proposer with delimiter isolation, heuristic prompt injection scanner, and grounded explanation validator.
- P7: AstraX theme UI with Space Grotesk, Inter, and JetBrains Mono fonts, AG Grid audit log, and visual blockchain diagram.
- P8: Full adversarial red-team suite (30 prompt injection vectors, digest tampering, replay attacks, and `docs/TEST_REPORT.md` generator).
- P9: Python MCP server wrapper (`app/mcp/server.py`) routing agent tools through application services.
- P10: Deployment configuration (`render.yaml`), idempotent demo boot/reset (`POST /v1/admin/reset`), and `docs/RUNBOOK.md`.
- P11: Complete documentation and submission package (`README.md`, `ARCHITECTURE.md`, `API_SPEC.md`, `DEMO_SCRIPT.md`, `DEVPOST.md`).
- Payment Rail Proof: ADR-009 recorded; PaymentRail protocol, FakePaymentRail test double, and PayPalPaymentRailAdapter with Orders v2 fallback implemented and verified.
- Mandates & Applied Cryptography: Strict Pydantic Mandate model, RFC 8785 canonical JSON via `rfc8785==0.1.4`, Ed25519 signing/verification with key_id binding, immutable versioning (`supersede`/`revoke`), Hypothesis property testing, and threat catalog B1-B5 red-team tests.
- Pure Decision Core: Exact Master Specification Section 5 rule order, `PolicyReasonCode` enum, `PolicyDecision(policy_version="1.0.0")`, pure `PolicyState`, purpose & invoice reference allowlists, lifetime budget caps, `guard_advisory_escalation()`, explicit request lifecycle state machine (`RECEIVED` to `CLOSED`), and 99% unit test coverage on `app/domain`.
- Money-Safe Persistence & Concurrency Core: `docs/DATABASE.md`, SQLAlchemy 2 models, Alembic migrations forward/rollback verified on empty database, single-transaction budget reservation using row locks and check constraints, conditional release (UNKNOWN outcome routes to RECONCILE, never releases funds), idempotency table with replay detection and parameter mutation rejection, step-up approvals cryptographically bound to canonical SHA-256 intent digest with expiration and replay checks, append-only ledger with hash chaining (`prev_hash` -> `event_hash`) and verification detecting row modification and deletion, database triggers strictly rejecting UPDATE and DELETE on `ledger_events`, and 50 parallel requests budget race passing 20 consecutive runs with zero flakes or race condition leaks.

Test status:
- Backend: 166/166 pytest tests passed in 10.26s (including 13 concurrency/money-safety tests and 44 red-team adversarial tests)
- Concurrency: 50 parallel requests racing one budget verified across 20 consecutive runs with 0 race condition leaks or overdrafts
- Domain Coverage: 99% branch & statement coverage across `app/domain`
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 30 source files)
- Frontend: ESLint clean, TypeScript clean, Vitest passed (3/3), Vite production build clean

Next recommended action: Commit changes directly to main.
