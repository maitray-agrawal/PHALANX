# STATE (update after every task)
Date: 9 Nov 2026 | Branch: dev | Last commit on dev: 1643f37 | Last pushed commit on main: 2332aef | CI: passing
Working tree: clean
Completed: T1, T2 (F1c-fix: H1-H7 closed) | Doing: T3 | Next: T4 | Blocked on me: nothing
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
  3. Approvals: Step-up queue, exact request, RFC 8785 canonical digest, inspect diff, Approve/Decline bound to digest, Agent role locking. Stored XSS rendered inertly.
  4. Activity: Ledger journal, windowed visual chain strip (latest 20 blocks with total count indicator), honest provider states, Verify chain trigger, receipt links. Stored XSS rendered inertly.
  5. Mandates: Read-only Ed25519 limits, lifetime budget meter with accessible ARIA progressbar, allowed payees, authorized purposes, signature status.
  6. Attack Lab: 6 canned threat vectors (prompt injection, payee swap, amount tamper after approval, replay, forged webhook, agent self-approval), Run suite trigger, 100% defense check.
  7. Receipt & Verify: Cryptographic receipt card, public SHA-256 hash chain proof verifier, search input. Stored XSS rendered inertly.
- tests: 363 automated backend tests (363 passed, 0 skipped, 0 failed), 105 red-team tests; 28 Vitest frontend tests; 38 Playwright end-to-end tests.

Test status:
- Backend: 363 passed, 0 skipped (363 total backend tests across 25 test files including tests/integration/test_reconciliation.py)
- Red Team: 105/105 red-team tests passed
- Performance & Invariants: All accounting and ledger invariants tested across 13,345 events; budget invariants verified with payment in flight and under concurrent load
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 39 source files)
- Frontend: Vitest passed (28/28 tests across 3 suites), ESLint clean (0 errors, 0 warnings), TypeScript clean (0 errors), build clean
- E2E: Playwright passed (38/38 tests across 6 browsers/viewports)
- Documentation: docs/decisions.md and docs/context.md updated.

Next recommended action: Proceed with T3 / T4 (env alignment and password confirmation).
