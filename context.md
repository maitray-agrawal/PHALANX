# context.md
Phase: R3 Complete (Judge-Facing Product Integration & PayPal E2E Verification)   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline.
- app/infrastructure: Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens, append-only ledger adapter, PayPal Sandbox rail adapter (Payouts with Orders v2 fallback and lookup), UTC clock, Bandit security scan.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts (/v1/payment-requests, /api/v1/authorize, /v1/mandates, /api/v1/mandates/{id}, /v1/decisions, /v1/approvals, /api/v1/approvals/{id}/approve, /api/v1/approvals/{id}/reject, /v1/ledger, /api/v1/ledger/verify, /v1/webhooks/paypal, /v1/admin/reset, /v1/auth/demo-token).
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PHALANX visual identity and 0/90 geometric logo mark; 4 core operational scenes (Request Console, Step-Up Approvals, Tamper-Evident Ledger, Active Mandate) + Reconciliation & Security Center.
- tests: 247 automated tests (unit, integration, concurrency, external failure, MCP parity, red-team A1-H2, security audit regressions, payment rail order lookup).

Completed R3 Milestones:
- R3.1: PayPal Sandbox End-to-End verified live against `api.sandbox.paypal.com` with real transaction creation and order lookup (`3J77364339194024E`).
- R3.2: API contract synchronized between `/v1/` and `/api/v1/` endpoints.
- R3.3: Agent Console updated with policy checks checklist and payment result cards for ALLOW, STEP-UP, and DENY.
- R3.4: Approval Queue bound to exact RFC 8785 canonical intent digest with agent role rejection.
- R3.5: Audit Ledger verified with AG Grid and live hash-chain tamper detection.
- R3.6: Light / Dark / System themes verified with ivory/sandstone light and deep-ink dark palettes.
- R3.7: Three Hero Scenarios (Legitimate, Over-limit, Injection/unauthorized payee) demonstrable and verified.
- R3.8: Tests updated and verified green across Python and TypeScript test suites.
- R3.9: Demo-state seeding and reset via `/v1/admin/reset` verified.
- R3.10: Public UI and documentation cleansed of AstraX/KuberSetu references; evidence recorded in `docs/EVIDENCE.md`.

Test status:
- Backend: 247/247 pytest tests passed in 25.41s
- Red Team: 67/67 red-team tests passed in 4.67s
- Concurrency / Transaction Audit: 15/15 passed in `tests/concurrency/test_transaction_audit.py`
- Payment Rail Suite: 5/5 passed in `tests/unit/test_payment_rail.py`
- Security Audit: bandit -r app reports 0 issues (0 High, 0 Medium, 0 Low)
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 38 source files)
- Frontend: ESLint clean (0 errors), TypeScript clean (`npx tsc --noEmit`), Vitest passed (11/11 across 2 suites), Vite production build clean

Next recommended action: Run final pre-flight verification gate, commit to main, and output final report.
