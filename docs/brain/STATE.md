# STATE (update after every task)
Date: 10 Nov 2026 | Branch: dev | Last pushed commit on main: 2332aef | CI: passing (run 42638236207)
Working tree: clean | M0 complete, hardened & all reviewer findings resolved
Completed: T1, T2 (H1-H7), T3/T4 (N1, U1), M0 Hardening (H8, H9, H10 closed), M0 Invariants (reconcile untrusted status removed, role auditor restricted, idempotent replay real state, may_release helper on all sites, FakePaymentRail business_rejection, exact paypal webhook events & lookup) | Doing: T5 | Next: T5 | Blocked on me: nothing
Database password rotated 7 Nov; verified live 9 Nov (active connection ok, old passwords rejected). Hosting: nothing deployed.

---

# context.md
Phase: R13 Live PayPal Sandbox (Orders v2 Two-Phase Flow, Payouts 403 Restricted Proof, Webhook Verification)   Branches: main, dev   Last green CI: https://github.com/maitray-agrawal/PHALANX/actions/runs/42638236207
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline. SubmitApprovalRequestDTO enforces strict mass-assignment prevention (`extra="forbid"`). Row-level locking on reservations and budgets. Allowlist of explicit provider failures in reconciler. Verification of external settlement proofs via provider before resolving NEEDS_REVIEW. In H9: `resolve_needs_review` treats `LOOKUP_FAILED`, timeouts, and transport errors as "cannot confirm", refusing `MARK_FAILED` and `PROVIDE_PROOF`.
- app/infrastructure: Multi-stage container packaging (Node 20 + Python 3.12 slim), single managed SQLAlchemy engine, dialect-specific connect args, request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter (re-entrant RLock to prevent deadlocks), PayPal Sandbox rail adapter (with deterministic request IDs from intent digests, real provider states, live webhook signature verification API, strict SSRF validation restricting certificate URLs to exact PayPal API hosts without userinfo or ports), UTC clock. FOR UPDATE SKIP LOCKED row claiming for concurrent reconcilers. Self-hosted distinct font weights for Inter and JetBrains Mono.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, timing-safe admin reset (hmac.compare_digest with min 24-char token), disabled in production environment (403 Forbidden), fail-closed dependencies (mandatory PostgreSQL outside test mode), fail-closed webhooks (503 if unconfigured, 401 on forged signature), demo mode guardrails (/v1/auth/demo-token with configurable rate limit, /v1/ledger/tamper, /restore, /v1/attack-lab/run gated on DEMO_MODE), strict query parameter length validation, paginated/windowed `/v1/ledger?limit=50` to guarantee high performance on slow 4G, CSP header with `default-src 'self'; frame-ancestors 'none'; form-action 'self'`, and HTTP caching controls (`Cache-Control: no-store`, `ETag`, `Vary: Authorization`). Role.AGENT explicitly forbidden from supervisor approval queue. Fail-closed 503 on database failure in pending approvals.
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PayPal-inspired clarity, mobile-first design (Inter & JetBrains Mono typography with true distinct font weights, gold/blue actions, semantic state tokens, 8px grid, max width 1120px). Topbar + bottom tabbar (< 768px), sticky primary action, demo persona switcher, and mandatory footer disclaimer: 'Not affiliated with PayPal.'.
- web screens:
  1. Home: Three numbers (remaining authority, pending approvals, last recorded activity), primary Pay action, recent activity stream.
  2. Pay: Request console with scenario presets, custom input, intent card, instant decision badge with plain reason.
  3. Approvals: Step-up queue, exact request, RFC 8785 canonical digest, inspect diff, Approve/Decline bound to digest, Agent role locking, deterministic empty-queue state when unseeded. Stored XSS rendered inertly.
  4. Activity: Ledger journal, windowed visual chain strip (latest 20 blocks with total count indicator), honest provider states, Verify chain trigger, receipt links. Stored XSS rendered inertly.
  5. Mandates: Read-only Ed25519 limits, lifetime budget meter with accessible ARIA progressbar, allowed payees, authorized purposes, signature status.
  6. Attack Lab: 6 canned threat vectors (prompt injection, payee swap, amount tamper after approval, replay, forged webhook, agent self-approval), Run suite trigger, 100% defense check.
  7. Receipt & Verify: Cryptographic receipt card, public SHA-256 hash chain proof verifier, search input. Stored XSS rendered inertly.

Test status (All Verified Live):
- Backend: 400 passed, 0 skipped, 0 failed in 149.85s (400 total backend tests across full test suite)
- Red Team: 105 passed, 0 failed, 295 deselected in 5.92s
- Performance & Invariants: All accounting and ledger invariants tested across 13,345 events; budget invariants verified with payment in flight and under concurrent PostgreSQL transactions
- Static Analysis: ruff check clean (0 errors), ruff format clean (100 files checked), mypy app clean (0 errors across 39 source files)
- Frontend: Vitest passed (28/28 tests across 3 suites in 5.92s), ESLint clean (0 errors, 0 warnings), TypeScript clean (0 errors across web codebase)
- E2E Smoke: Playwright smoke passed (30/30 tests across all 6 browsers/viewports: Chromium, WebKit, Firefox, iPhone SE, Pixel 7, iPad in 1.9m)
- Web Build: Vite production build succeeded (index.html, CSS, JS chunks generated cleanly in 5.84s)
- License: Apache-2.0 (OSI-approved)

Credential Alignment & Hostile Review Resolutions:
- H8 (Closed): `validate_paypal_cert_url` enforces HTTPS, allowed hostnames strictly in `{api.paypal.com, api.sandbox.paypal.com, api-m.paypal.com, api-m.sandbox.paypal.com}`, rejects userinfo (username/password), and rejects explicit ports. Verified by 8 unit test cases.
- H9 (Closed): `resolve_needs_review` refuses `MARK_FAILED` and `PROVIDE_PROOF` on `LOOKUP_FAILED`, timeouts, and transport errors. Only explicit provider failure statuses or 404 `NOT_FOUND` release reservations.
- H10 (Closed): `scripts/boot.py` seeds `req_stepup_1001` only when `DEMO_SEED=true`. Tested: boot with `DEMO_SEED` unset yields empty approvals queue (`[]`).
- Demo Rate Limit & Admin Reset: Confirmed `DEMO_TOKEN_RATE_LIMIT=1000` is only in local test/dev compose. `admin_reset` requires authentication (401 without auth) and is strictly disabled when `ENVIRONMENT=production` (403 Forbidden). Verified by integration tests.
- Font Weights: Verified font files in `web/public/fonts/` replaced with genuine, distinct `@fontsource` weights for Inter (400, 500, 600, 700) and JetBrains Mono (400, 500, 600, 700). Distinct SHA-256 hashes verified.
- Public Documentation: Kept `README.md` clean (< 115 lines); added `docs/process/README.md` to document internal development and agent governance artifacts without deleting or breaking file references.

Next recommended action: Proceed with T5 (Reviewer R1 hostile pass).
