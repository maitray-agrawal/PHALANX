# context.md
Phase: R8 Complete (PayPal-Inspired Mobile-First Shell & Seven Operational Screens)   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline.
- app/infrastructure: Multi-stage container packaging (Node 20 + Python 3.12 slim), single managed SQLAlchemy engine, dialect-specific connect args, request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter, PayPal Sandbox rail adapter (with deterministic request IDs from intent digests, real provider states, live webhook signature verification API), UTC clock, Bandit security scan.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, timing-safe admin reset (hmac.compare_digest with min 24-char token), fail-closed dependencies (mandatory PostgreSQL outside test mode), fail-closed webhooks (503 if unconfigured), demo mode guardrails (/v1/auth/demo-token, /v1/ledger/tamper, /restore, /v1/attack-lab/run gated on DEMO_MODE), and HTTP caching controls (ETag conditional 304, no-store, immutable assets).
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PayPal-inspired clarity, mobile-first design (Inter & JetBrains Mono typography, gold/blue actions, semantic state tokens, 8px grid, max width 1120px). Topbar + bottom tabbar (< 768px), sticky primary action, demo persona switcher, and mandatory footer disclaimer: 'Not affiliated with PayPal.'.
- web screens:
  1. Home: Three numbers (remaining authority, pending approvals, last recorded activity), primary Pay action, recent activity stream.
  2. Pay: Request console with scenario presets, custom input, intent card, instant decision badge with plain reason.
  3. Approvals: Step-up queue, exact request, RFC 8785 canonical digest, inspect diff, Approve/Decline bound to digest, Agent role locking.
  4. Activity: Ledger journal, visual chain strip, honest provider states, Verify chain trigger, receipt links.
  5. Mandates: Read-only Ed25519 limits, lifetime budget meter, allowed payees, authorized purposes, signature status.
  6. Attack Lab: 6 canned threat vectors (prompt injection, payee swap, amount tamper after approval, replay, forged webhook, agent self-approval), Run suite trigger, 100% defense verification proof.
  7. Receipt & Verify: Cryptographic receipt card, public SHA-256 hash chain proof verifier, search input.
- tests: 276 automated backend tests (269 passed, 7 skipped in non-Docker), 72 red-team tests; 28 Vitest frontend tests; 5 Playwright end-to-end multi-viewport tests with automated screenshots at 1280px, 768px, and 375px.

Test status:
- Backend: 269 passed, 7 skipped (276 total backend tests across 18 test files; 7 skipped are Docker PostgreSQL tests that run in CI)
- Red Team: 72/72 red-team tests passed
- Security Audit: bandit -r app reports 0 issues (0 High, 0 Medium, 0 Low)
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 38 source files)
- Frontend: Vitest passed (28/28 tests across 3 suites), ESLint clean (0 errors, 0 warnings), TypeScript clean (0 errors), build clean
- E2E: Playwright passed (5/5 tests across desktop, tablet, and mobile viewports)
- Screenshots: Captured and verified at 1280px, 768px, and 375px in artifact directory

Next recommended action: Commit all changes directly to main.
