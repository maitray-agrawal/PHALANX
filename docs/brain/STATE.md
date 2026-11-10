# STATE (update after every task)
Date: 10 Nov 2026 | Branch: dev | Last pushed commit on dev: 4aa958c | CI: passing (run 42839047363)
Working tree: clean | M0 complete, hardened; T8 Real LLM Invoice Agent complete; D1 Render & Neon deployment ready (CI Green)
Completed: T1, T2 (H1-H7), T3/T4 (N1, U1), M0 Hardening (H8-H10 closed), M0 Invariants (reconcile, auditor role, idempotent replay, may_release, exact webhooks), T8 Real LLM Invoice Agent, D1 Free Hosted Demo Config (render.yaml, Neon setup, healthz DB-isolation, reconcile-scheduled endpoint, demo env model, proxy-aware rate limits) | Doing: D1 verification | Next: T5 | Blocked on me: nothing
Database password rotated 7 Nov; verified live 9 Nov (active connection ok, old passwords rejected). Hosting: Render + Neon manifests ready; awaiting user dashboard action.

---

# context.md
Phase: R13 Live PayPal Sandbox (Orders v2 Two-Phase Flow, Payouts 403 Restricted Proof, Webhook Verification) + T8 Invoice Agent   Branches: main, dev   Last green CI: https://github.com/maitray-agrawal/PHALANX/actions/runs/42816173523
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, InvoiceAgent (autonomous supplier invoice ingestion with strict prompt delimiter isolation and deterministic PHALANX policy boundary), ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor, GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline.
- app/infrastructure: Multi-stage container packaging (Node 20 + Python 3.12 slim), single managed SQLAlchemy engine, dialect-specific connect args, request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter (re-entrant RLock to prevent deadlocks), GeminiLLMClient (official Gemini API adapter, temperature 0, strict JSON schema output, timeout 10s, 1 retry, token cap 1024, daily quota tracker with demo budget cap, server-side only key handling), PayPal Sandbox rail adapter, UTC clock. FOR UPDATE SKIP LOCKED row claiming for concurrent reconcilers.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, Invoice Agent endpoints (`GET /v1/invoice-agent/samples`, `POST /v1/invoice-agent/process`).
- web: React + Vite + TypeScript security console with PayPal-inspired clarity, mobile-first design.
- web screens:
  1. Home: Three numbers, primary Pay action, recent activity stream.
  2. Pay: Request console with scenario presets, custom input, intent card, instant decision badge with plain reason.
  3. Approvals: Step-up queue, exact request, RFC 8785 canonical digest, inspect diff, Approve/Decline bound to digest.
  4. Activity: Ledger journal, windowed visual chain strip, honest provider states, Verify chain trigger.
  5. Mandates: Read-only Ed25519 limits, lifetime budget meter with accessible ARIA progressbar.
  6. Invoice Agent (Screen): Autonomous AI invoice parsing with Gemini, displaying raw invoice text, extracted fields, exact authorization request sent to /v1/authorize, deterministic PHALANX decision, hash-chained ledger event, and clear 'RECORDED RUN' fallback indicator.
  7. Attack Lab: 6 canned threat vectors.
  8. Receipt & Verify: Cryptographic receipt card, public SHA-256 hash chain proof verifier.

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
