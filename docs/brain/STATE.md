# STATE (update after every task)
Date: 9 Nov 2026 | Branch: dev | Last pushed commit on main: 2332aef | CI: passing
Working tree: clean | M0 complete & hardened (Hostile Review Pass 2 completed, deterministic e2e verified)
Completed: T1, T2 (F1c-fix: H1-H7 closed), M0 Hardening (Items 1-10), T3/T4 (N1, U1 closed) | Doing: Verification & Local Commit | Next: T5 (Hostile Reviewer R1 pass) | Blocked on me: nothing
Database password rotated 7 Nov (user report); verified live 9 Nov (active connection ok, old passwords rejected). Hosting: nothing deployed.

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
  3. Approvals: Step-up queue, exact request, RFC 8785 canonical digest, inspect diff, Approve/Decline bound to digest, Agent role locking, deterministic empty-queue state when unseeded. Stored XSS rendered inertly.
  4. Activity: Ledger journal, windowed visual chain strip (latest 20 blocks with total count indicator), honest provider states, Verify chain trigger, receipt links. Stored XSS rendered inertly.
  5. Mandates: Read-only Ed25519 limits, lifetime budget meter with accessible ARIA progressbar, allowed payees, authorized purposes, signature status.
  6. Attack Lab: 6 canned threat vectors (prompt injection, payee swap, amount tamper after approval, replay, forged webhook, agent self-approval), Run suite trigger, 100% defense check.
  7. Receipt & Verify: Cryptographic receipt card, public SHA-256 hash chain proof verifier, search input. Stored XSS rendered inertly.

Test status (All Verified Live):
- Backend: 382 passed, 0 skipped, 0 failed in 213.80s (382 total backend tests across full test suite)
- Red Team: 105 passed, 0 failed, 277 deselected in 9.66s
- Performance & Invariants: All accounting and ledger invariants tested across 13,345 events; budget invariants verified with payment in flight and under concurrent PostgreSQL transactions
- Static Analysis: ruff check clean (0 errors), ruff format clean (99 files checked), mypy app clean (0 errors across 39 source files)
- Frontend: Vitest passed (28/28 tests across 3 suites in 5.35s), ESLint clean (0 errors, 0 warnings), TypeScript clean (0 errors across web codebase)
- E2E Smoke: Playwright smoke passed (30/30 tests across all 6 browsers/viewports: Chromium, WebKit, Firefox, iPhone SE, Pixel 7, iPad in 1.6m)
- E2E Walkthrough: Playwright UX walkthrough passed (8/8 tests across Chromium desktop and Pixel 7 mobile)
- Accessibility: Axe core clean on horizontally scrollable cryptographic hash chain strip (`tabIndex={0}`, `role="region"`, `aria-label`)

Credential Alignment & Verification (T3/T4):
- Password alignment: Verified `POSTGRES_PASSWORD` and `PHALANX_APP_DB_PASSWORD` separated in `.env`, `.env.example`, `docker-compose.yml`, `scripts/init_db.sh`.
- Live connection: Active credentials successfully connected to `phalanx_db` and `phalanx_test` (`Active credentials connection: SUCCESS`).
- Negative controls: Rejected predictable, default, and historical credentials with `InvalidPassword` / `password authentication failed` (`All old/predictable passwords: REJECTED`).
- Credential script: Deleted `scripts/rotate_db_credentials.ps1` to eliminate platform-specific Windows script that mutated `.env`.

Hostile Review Pass 2 Findings:
- Finding A (P1): `app/infrastructure/paypal.py:680-689` checks `parsed_cert.hostname.endswith(".paypal.com")` rejecting `evilpaypal.com` and `paypal.com.evil.com`, but does not inspect userinfo (`username:password@`) or port (`:8443`). E.g. `https://attacker:pass@api.sandbox.paypal.com:8443/cert.pem` passes the check.
- Finding B (P1): `app/application/services.py:2210-2227` (`resolve_needs_review`) treats `LOOKUP_FAILED` in the same tuple as confirmed failures (`FAILED`, `CANCELLED`, `DENIED`, `EXPIRED`, `NOT_FOUND`), allowing supervisor MARK_FAILED to release reservations during provider outages or credential errors.
- Finding C (P1): `scripts/boot.py:289-325` unconditionally seeds `req_stepup_1001` if missing, ignoring `DEMO_SEED=true`. Neither `docker-compose.yml` nor `render.yaml` specifies `DEMO_SEED=true`.

Next recommended action: Proceed with T5 (Reviewer R1 hostile pass with different model).
