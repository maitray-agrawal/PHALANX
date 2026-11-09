# STATE (update after every task)
Date: 7 Nov 2026 | Branch: dev (local only until the first push) | Last pushed commit on main: d41cff0 | CI: unknown
Working tree: uncommitted F1 and F1c changes (reported passing locally: 357 tests, 105 red-team, ruff, mypy)
Doing: T1 | Next: T2 | Blocked on me: nothing
Database password rotated 7 Nov (user report). Hosting: nothing deployed.

---

# context.md
Phase: R13 Live PayPal Sandbox (Orders v2 Two-Phase Flow, Payouts 403 Restricted Proof, Webhook Verification)   Branches: main, dev   Last green CI: https://github.com/maitray-agrawal/PHALANX/actions/runs/42326907597
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline. SubmitApprovalRequestDTO enforces strict mass-assignment prevention (`extra="forbid"`).
- app/infrastructure: Multi-stage container packaging (Node 20 + Python 3.12 slim), single managed SQLAlchemy engine, dialect-specific connect args, request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter (re-entrant RLock to prevent deadlocks), PayPal Sandbox rail adapter (with deterministic request IDs from intent digests, real provider states, live webhook signature verification API, SSRF validation on certificate URLs restricting strictly to `.paypal.com`), UTC clock.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, timing-safe admin reset (hmac.compare_digest with min 24-char token), fail-closed dependencies (mandatory PostgreSQL outside test mode), fail-closed webhooks (503 if unconfigured), demo mode guardrails (/v1/auth/demo-token with configurable rate limit, /v1/ledger/tamper, /restore, /v1/attack-lab/run gated on DEMO_MODE), strict query parameter length validation, paginated/windowed `/v1/ledger?limit=50` to guarantee high performance on slow 4G, CSP header with `default-src 'self'; frame-ancestors 'none'; form-action 'self'`, and HTTP caching controls (`Cache-Control: no-store`, `ETag`, `Vary: Authorization`). Role.AGENT explicitly forbidden from supervisor approval queue.
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PayPal-inspired clarity, mobile-first design (Inter & JetBrains Mono typography, gold/blue actions, semantic state tokens, 8px grid, max width 1120px). Topbar + bottom tabbar (< 768px), sticky primary action, demo persona switcher, and mandatory footer disclaimer: 'Not affiliated with PayPal.'.
- web screens:
  1. Home: Three numbers (remaining authority, pending approvals, last recorded activity), primary Pay action, recent activity stream.
  2. Pay: Request console with scenario presets, custom input, intent card, instant decision badge with plain reason.
  3. Approvals: Step-up queue, exact request, RFC 8785 canonical digest, inspect diff, Approve/Decline bound to digest, Agent role locking. Stored XSS rendered inertly. Persistent demo step-up fallback.
  4. Activity: Ledger journal, windowed visual chain strip (latest 20 blocks with total count indicator), honest provider states, Verify chain trigger, receipt links. Stored XSS rendered inertly.
  5. Mandates: Read-only Ed25519 limits, lifetime budget meter with accessible ARIA progressbar, allowed payees, authorized purposes, signature status.
  6. Attack Lab: 6 canned threat vectors (prompt injection, payee swap, amount tamper after approval, replay, forged webhook, agent self-approval), Run suite trigger, 100% defense check.
  7. Receipt & Verify: Cryptographic receipt card, public SHA-256 hash chain proof verifier, search input. Stored XSS rendered inertly.
- ux, accessibility & multi-browser quality:
  - Playwright E2E: 38/38 passing tests (30 cross-device tests across Chromium with slow 4G throttling, WebKit, Firefox, iPhone SE, Pixel 7, iPad; 8 cognitive walkthrough tests across APPROVER, AGENT, AUDITOR, PRINCIPAL personas).
  - Axe Core automated accessibility audit: 0 critical / 0 serious violations across all 7 views.
  - Lighthouse mobile audit: Accessibility: 100/100, Performance: 89/100, Best Practices: 96/100, SEO: 91/100.
  - Mobile responsiveness: 0 horizontal scroll at 375px; 44px minimum touch targets across all interactive controls.
  - Reduced motion: Clamped transitions (`<= 0.01ms`) under `prefers-reduced-motion: reduce`.
- tests: 357 automated backend tests (357 passed, 0 skipped, 0 failed), 105 red-team tests; 28 Vitest frontend tests; 38 Playwright end-to-end tests.

Test status:
- Backend: 357 passed, 0 skipped (357 total backend tests across 24 test files including tests/integration/test_reconciliation.py)
- Red Team: 105/105 red-team tests passed
- Performance & Invariants: All accounting and ledger invariants tested across 13,345 events; budget invariants verified with payment in flight and under concurrent load
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 39 source files)
- Frontend: Vitest passed (28/28 tests across 3 suites), ESLint clean (0 errors, 0 warnings), TypeScript clean (0 errors), build clean
- E2E: Playwright passed (38/38 tests across 6 browsers/viewports)
- Documentation: docs/decisions.md and docs/context.md updated.

Next recommended action: Commit all changes directly to main and push.
