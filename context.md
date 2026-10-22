# context.md
Phase: P12 Complete (Final Review & Submission Package Ready)   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator (hallucination rejection & templated fallback), PrincipalSessionMemory (rolling summary, N turns), DeterministicKnowledgeBase ("I do not know" boundary), CompositeAdvisoryPipeline (heuristics, Median/MAD velocity, synthetic TF-IDF + Logistic Regression).
- app/infrastructure: Ed25519 signing/verification, HMAC-SHA256 role tokens, append-only ledger adapter, PayPal Sandbox rail adapter, UTC clock, Bandit security scan.
- app/api: Complete FastAPI REST suite (/v1/payment-requests, /v1/mandates, /v1/decisions, /v1/approvals, /v1/ledger, /v1/ledger/verify, /v1/webhooks/paypal, /v1/admin/reset, /v1/auth/demo-token).
- app/mcp: Model Context Protocol server exposing financial agent governance tools.
- web: React + Vite + TypeScript dashboard in AstraX design system with 4 operational scenes (Request Console, Step-Up Approvals, Tamper-Evident Ledger, Active Mandate).
- tests: 237 automated tests (unit, integration, concurrency, external failure, MCP parity, red-team A1-H2, security audit regressions, transaction boundary audit F1-F7).

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
- P9: Official Python MCP SDK (`mcp==1.3.0`, FastMCP) exposing `request_payment` and `get_mandate_status` through `app/application`, authenticated strictly as agent identity (`Role.AGENT`), returning decision and pending-approval references only with zero credential leakage, red-team G1 test proving no alternate path, AstraX client example (`examples/astrax_mcp_client.py`), `docs/MCP_INTEGRATION.md`, and 100% decision parity between MCP and HTTP verified in `tests/integration/test_mcp_vs_http.py`.
- P10: Hosted demo deployment pipeline on Render (`render.yaml`), idempotent boot script (`scripts/boot.py`), demo mandate valid until 31 Mar 2027, admin-token reset endpoint (`POST /v1/admin/reset` with `X-Admin-Token`), structured JSON logging with request IDs (`X-Request-ID`), external keepalive pinger (`scripts/pinger.py` and `.github/workflows/keepalive.yml`), deploy-on-green-CI GitHub Actions workflow with Render deploy hook, automated post-deploy smoke test runner (`scripts/post_deploy_smoke.py` validating Scene 1, Scene 2, Scene 3, and admin reset), `docs/DEPLOYMENT.md`, `docs/OBSERVABILITY.md`, updated `docs/RUNBOOK.md`, and Render free tier vs Starter plan evidence and PayPal sandbox longevity recorded in `docs/EVIDENCE.md`.
- P11: Complete documentation and submission package (`README.md`, `ARCHITECTURE.md`, `API_SPEC.md`, `DEMO_SCRIPT.md`, `DEVPOST.md`).
- P12: Comprehensive Independent Release Review & Audit (manual 56.41 vibe-code audit, 56.44 prove-it gate claim mapping, 56.36 fresh-machine installation test, Apache-2.0 license check, Bandit AST 0-issue security scan, git history credential scan, pinned `requirements.txt` / `requirements-dev.txt`, and publication of `docs/FINAL_REPORT.md` with Release Status `QUALIFIED_FOR_SUBMISSION` and Assessment Confidence `HIGH`).
- Hostile Security Review & P0/P1 Remediation: Remediated F-01 unmandated agent fallback (strictly returns None -> DENY), F-02 approval execution rechecks live mandate active status and expiry, F-03 cross-tenant approver IDOR and demo principal alignment, F-04 MCP impersonation guard, F-05 restricted ledger tamper endpoint. Added 6 redteam regression tests in `tests/redteam/test_redteam.py`.
- P13: Concurrency Audit Completion (R2) & AstraX Master UI/UX Implementation:
  - R2 Concurrency Completion:
    - F4: Database savepoints (`begin_nested()`) catch concurrent duplicate constraint collisions on idempotency keys, rolling back reservation and raising `IdempotencyReplayError` without raw IntegrityError or double budget deductions.
    - F5: Authoritative database-backed budget repository (`BudgetRepository`, `AgentBudgetModel`) with row-level locks strictly enforces persistent budget tracking across separate service instances and restarts.
    - F6: PayPal ambiguous outcome lifecycle transitions to `RequestState.RECONCILE` on timeout/5xx; budget reservation held continuously until confirmed success or failure. Documented limitation: automated periodic background polling requires an external scheduled worker or inbound webhook dispatcher; interactive/API reconciliation provided via `/v1/reconcile`.
    - F7: Row-level locking on PostgreSQL dialect via `with_for_update()`.
    - Concurrency audit suite expanded to 15 tests in `tests/concurrency/test_transaction_audit.py`.
  - AstraX Master UI/UX Implementation:
    - Strict adherence to `LOGO/Phalanx Brand Identity Styleboard.png` and color token system: Light (Ivory `#FDF7EC`, Sandstone `#EADCC8`, Ink `#221B14`), Dark (Deep Ink `#14100D`, Elevated `#1F1914`, Copper `#B87333`), Indigo `#1E3A8A`, Teal `#0EA5A3`, Vermilion `#DC2626`, Forest Green `#166534`, and Saffron `#F59E38`.
    - Mathematical 0/90 geometry with 18x18px central diamond bindu authority node, shield perimeter wings, checkpoint nodes, and vertical spear axis of control in `PhalanxMark` and `PhalanxHeaderBrand`.
    - Functional Light / Dark / System theme switcher with `localStorage` persistence and zero flash.
    - Executive Cockpit Overview dashboard with 6 KPI cards, interactive architecture pipeline diagram, and quick-action shortcuts.
    - Real-time decision pipeline status strip in Request Console.
    - Dedicated Rail Reconciliation screen with interactive simulator for 504 gateway timeouts and resolution actions (`SETTLED`, `FAILED`, `RECONCILE`).
    - Security Center displaying the 6 core architectural invariants and red-team posture.
    - Developer & MCP catalog with tool definitions and client SDK snippets.
    - Preserved all existing test selectors and role bindings.

Test status:
- Backend: 245/245 pytest tests passed in 13.77s
- Red Team: 67/67 red-team tests passed in 2.34s
- Concurrency / Transaction Audit: 15/15 passed in `tests/concurrency/test_transaction_audit.py`
- Security Audit: bandit -r app reports 0 issues (0 High, 0 Medium, 0 Low across 5,529 lines)
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 38 source files)
- Frontend: ESLint clean (0 errors), TypeScript clean (`npx tsc --noEmit`), Vitest passed (11/11 across 2 suites in 1.76s), Vite production build clean (`web/dist` built in 7.87s)

Next recommended action: Review changes, open PR, and tag release v1.0.
