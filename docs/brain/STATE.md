# STATE (update after every task)
Date: 9 Nov 2026 | Branch: dev | Last pushed commit on main: 2332aef | CI: passing
Working tree: clean | M0 complete (all 10 items implemented and verified)
Completed: T1, T2 (F1c-fix: H1-H7 closed), M0 Hardening (Items 1-10) | Doing: Full Verification Suite | Next: T3 / T4 | Blocked on me: nothing
Database password rotated 7 Nov (user report). Hosting: nothing deployed.

---

# context.md
Phase: R13 Live PayPal Sandbox (Orders v2 Two-Phase Flow, Payouts 403 Restricted Proof, Webhook Verification)   Branches: main, dev   Last green CI: https://github.com/maitray-agrawal/PHALANX/actions/runs/42326907597
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline. SubmitApprovalRequestDTO enforces strict mass-assignment prevention (`extra="forbid"`). Row-level locking on reservations and budgets. Allowlist of explicit provider failures in reconciler. Verification of external settlement proofs via provider before resolving NEEDS_REVIEW.
- app/infrastructure: Multi-stage container packaging (Node 20 + Python 3.12 slim), single managed SQLAlchemy engine, dialect-specific connect args, request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter (re-entrant RLock to prevent deadlocks), PayPal Sandbox rail adapter (with deterministic request IDs from intent digests, real provider states, live webhook signature verification API, SSRF validation on certificate URLs restricting strictly to `.paypal.com`), UTC clock. FOR UPDATE SKIP LOCKED row claiming for concurrent reconcilers.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, timing-safe admin reset (hmac.compare_digest with min 24-char token), fail-closed dependencies (mandatory PostgreSQL outside test mode), fail-closed webhooks (503 if unconfigured, 401 on forged signature), demo mode guardrails (/v1/auth/demo-token with configurable rate limit, /v1/ledger/tamper, /restore, /v1/attack-lab/run gated on DEMO_MODE), strict query parameter length validation, paginated/windowed `/v1/ledger?limit=50` to guarantee high performance on slow 4G, CSP header with `default-src 'self'; frame-ancestors 'none'; form-action 'self'`, and HTTP caching controls (`Cache-Control: no-store`, `ETag`, `Vary: Authorization`). Role.AGENT explicitly forbidden from supervisor approval queue. Fail-closed 503 on database failure in pending approvals.
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PayPal-inspired clarity, mobile-first design (Inter & JetBrains Mono typography, gold/blue actions, semantic state tokens, 8px grid, max width 1120px). Topbar + bottom tabbar (< 768px), sticky primary action, demo persona switcher, and mandatory footer disclaimer: 'Not affiliated with PayPal.'.
- web screens:
  1. Home: Three numbers (remaining authority, pending approvals, last recorded activity), primary Pay action, recent activity stream.
  2. Pay: Request console with scenario presets, custom input, intent card, instant decision badge with plain reason.
  3. Approvals: Step-up queue, exact request, RFC 8785 canonical digest, inspect diff, Approve/Decline bound to digest, Agent role locking, empty-queue clear state when unseeded. Stored XSS rendered inertly.
  4. Activity: Ledger journal, windowed visual chain strip (latest 20 blocks with total count indicator), honest provider states, Verify chain trigger, receipt links. Stored XSS rendered inertly.
  5. Mandates: Read-only Ed25519 limits, lifetime budget meter with accessible ARIA progressbar, allowed payees, authorized purposes, signature status.
  6. Attack Lab: 6 canned threat vectors (prompt injection, payee swap, amount tamper after approval, replay, forged webhook, agent self-approval), Run suite trigger, 100% defense check.
  7. Receipt & Verify: Cryptographic receipt card, public SHA-256 hash chain proof verifier, search input. Stored XSS rendered inertly.

Test status (All Verified Live):
- Backend: 381 passed, 0 skipped, 0 failed in 196.69s (381 total backend tests across full test suite)
- Red Team: 105 passed, 0 failed, 276 deselected in 13.85s
- Performance & Invariants: All accounting and ledger invariants tested across 13,345 events; budget invariants verified with payment in flight and under concurrent PostgreSQL transactions
- Static Analysis: ruff check clean (0 errors), ruff format clean (99 files checked), mypy app clean (0 errors across 39 source files)
- Frontend: Vitest passed (28/28 tests across 3 suites in 5.35s), ESLint clean (0 errors, 0 warnings), TypeScript clean (0 errors across web codebase)
- E2E: Playwright smoke passed (30/30 tests across all 6 browsers/viewports: Chromium, WebKit, Firefox, iPhone SE, Pixel 7, iPad in 53.3s)
- Documentation: docs/brain/STATE.md updated, redundant brain/STATUS.md removed.

M0 Completed Items:
1. `make step up seeding demo only`: `_seed_default_step_up` demo-only (explicit `DEMO_SEED=true`), removed from `AuthorizationService.__init__`. (597083b)
2. `lock reservation and budget rows on settle and release`: `SELECT ... FOR UPDATE` row locking on reservation row then budget row. Real PostgreSQL concurrency tests added. (4e4c7e2)
3. `hold 408 429 and 5xx in reconcile never failed`: `pay()` routes 408, 429, and 5xx to `RECONCILE`. Only explicit 400/422 releases. Parameterized unit tests added. (9ce6fcc)
4. `fail closed on pending step ups database error`: `get_pending_step_ups` raises 503, no in-memory fallback. Integration tests added. (ebe5e51)
5. `allowlist explicit failures in reconcile reservation`: Replaced denylist with explicit provider failure allowlist; unknown statuses hold and set `NEEDS_REVIEW`. (f2b57ca)
6. `verify provider proof on resolve needs review`: `MARK_FAILED` confirmed via provider; `PROVIDE_PROOF` verified against provider lookup. (31ab157)
7. `claim reconcile rows with skip locked`: Claim rows with `FOR UPDATE SKIP LOCKED`; tested against PostgreSQL concurrency. (fc3c4a5)
8. `run alter role as postgres superuser in rotation`: `scripts/rotate_db_credentials.ps1` executes `ALTER ROLE` as `postgres` superuser with error stop. (24144ab)
9. `test real verify webhook rejects forged headers`: Real `PayPalPaymentRailAdapter.verify_webhook` tested against forged SSRF cert URLs, userinfo, and forged signatures. (c4b5022)
10. `update smoke test for empty approvals queue`: `web/e2e/smoke.spec.ts` updated to empty-queue behavior, verified across all 6 browsers/viewports. (6f06c58)

Next recommended action: Proceed with T3 / T4 (env alignment and password confirmation).
