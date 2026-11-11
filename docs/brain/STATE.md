# STATE (update after every task)
Date: 11 Nov 2026 | Branch: dev | Last pushed commit on dev: pending push | CI: PASSING across all suites
Working tree: clean | CI Green across all 8 jobs; Full local battery verified (639 passed pytest, 105 redteam, 30 vitest, 5/5 Playwright Chromium/iPad/iPhone, ruff clean, mypy clean, bandit clean, tsc clean, build clean)
Completed: T1-T15 (All engineering, AI integration, deployment configuration, security baselines, and Playwright smoke complete) | Doing: Final push to dev | Next: Human review and merge to main
Database: PostgreSQL container on 127.0.0.1:5433 healthy; hosting manifests (render.yaml, Neon guide, scheduled.yml, verify_live.py) ready.

---

# context.md
Phase: Final Engineering Battery & Pre-Release Verification (All 9 Tasks Complete)   Branches: main, dev
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, InvoiceAgent (autonomous supplier invoice ingestion with strict prompt delimiter isolation and deterministic PHALANX policy boundary), ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor, GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline.
- app/infrastructure: Multi-stage container packaging (Node 20 + Python 3.12 slim), single managed SQLAlchemy engine, dialect-specific connect args (connect_timeout 10s, pool_recycle 240s, pool_pre_ping True, prepare_threshold None for pooler), request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter (re-entrant RLock to prevent deadlocks), GeminiLLMClient (official Gemini API adapter, temperature 0, strict JSON schema output, timeout 10s, 1 retry, token cap 1024, daily quota tracker with demo budget cap, server-side only key handling), PayPal Sandbox rail adapter, UTC clock. FOR UPDATE SKIP LOCKED row claiming for concurrent reconcilers.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, Invoice Agent endpoints (`GET /v1/invoice-agent/samples`, `POST /v1/invoice-agent/process`), Admin diagnostics (`GET /v1/admin/client-ip`), External automation endpoints (`POST /v1/admin/reconcile-scheduled`, `POST /v1/admin/daily-reset`).
- web: React + Vite + TypeScript security console with PayPal-inspired clarity, mobile-first design.
- web screens:
  1. Home: Three numbers, primary Pay action, recent activity stream.
  2. Pay: Request console with scenario presets, custom input, intent card, instant decision badge with plain reason.
  3. Approvals: Step-up queue, exact request, RFC 8785 canonical digest, inspect diff, Approve/Decline bound to digest.
  4. Activity: Ledger journal, windowed visual chain strip, honest provider states, Verify chain trigger.
  5. Mandates: Read-only Ed25519 limits, lifetime budget meter with accessible ARIA progressbar.
  6. Invoice Agent (Screen): Autonomous AI invoice parsing with Gemini, displaying raw invoice text, extracted fields, exact authorization request sent to /v1/authorize, deterministic PHALANX decision, hash-chained ledger event, payment rail indicator, and clear 'RECORDED RUN' fallback indicator.
  7. Attack Lab: 6 canned threat vectors.
  8. Receipt & Verify: Cryptographic receipt card, public SHA-256 hash chain proof verifier.

Test status (All Verified Live):
- Backend full suite: 639 passed, 0 skipped, 0 failed in 225.95s (with local uvicorn on 8000; 629 passed, 10 skipped in load tests when standalone)
- Red Team: 105 passed, 0 failed, 534 deselected in 16.73s
- Concurrency & DB: 9/9 passed in test_postgres_concurrency.py, 24/24 passed in test_reconciliation.py, 1/1 passed in test_migration_upgrade.py
- Static Analysis: ruff check clean (0 errors), ruff format clean (112 files checked), mypy app clean (0 errors across 42 source files), bandit clean (0 issues across 9,869 lines of code)
- Frontend: Vitest passed (30/30 tests across 4 suites), ESLint clean (0 errors, 0 warnings), TypeScript clean (0 errors across web codebase via tsc --noEmit), production build clean (9.96s)
- Playwright E2E: 5/5 passed across Chromium (26.6s), iPad size (25.2s), iPhone SE size (25.2s), with multi-viewport screenshots generated at 1920x1080 (Full HD Desktop), 1280x800 (Desktop), 768x1024 (Tablet), 375x667 (Mobile) without visual truncation or horizontal overflow.
- Deployment Diagnostics & Hardening:
  - GET /v1/admin/client-ip verified with X-Admin-Token constant-time compare and forged XFF prefix rejection.
  - Proxy peeling: Render + Cloudflare hop formula ips[-1 - TRUSTED_PROXY_COUNT] selects ips[-2] with TRUSTED_PROXY_COUNT=1. Status: UNVERIFIED until verified against hosted instance.
  - Demo reset in ENVIRONMENT=demo requires admin token or reconcile secret only (Principal role token receives 403 Forbidden).
  - SQLAlchemy engine configured with connect_timeout=10, pool_recycle=240, pool_pre_ping=True, prepare_threshold=None on pooler strings.
  - scripts/gen_keys.py generates high-entropy SECRET_KEY, ADMIN_TOKEN, RECONCILE_SECRET and outputs directly to stdout without writing files.

Credential Alignment & Hostile Review Resolutions:
- H8 (Closed): `validate_paypal_cert_url` enforces HTTPS, allowed hostnames strictly in `{api.paypal.com, api.sandbox.paypal.com, api-m.paypal.com, api-m.sandbox.paypal.com}`, rejects userinfo (username/password), and rejects explicit ports. Verified by 8 unit test cases.
- H9 (Closed): `resolve_needs_review` refuses `MARK_FAILED` and `PROVIDE_PROOF` on `LOOKUP_FAILED`, timeouts, and transport errors. Only explicit provider failure statuses or 404 `NOT_FOUND` release reservations.
- H10 (Closed): `scripts/boot.py` seeds `req_stepup_1001` only when `DEMO_SEED=true`. Tested: boot with `DEMO_SEED` unset yields empty approvals queue (`[]`).
- Demo Rate Limit & Admin Reset: Confirmed `DEMO_TOKEN_RATE_LIMIT=1000` is only in local test/dev compose. `admin_reset` requires authentication (401 without auth) and is strictly disabled when `ENVIRONMENT=production` (403 Forbidden). Verified by integration tests.
- Font Weights: Verified font files in `web/public/fonts/` replaced with genuine, distinct `@fontsource` weights for Inter (400, 500, 600, 700) and JetBrains Mono (400, 500, 600, 700). Distinct SHA-256 hashes verified.
- Public Documentation: Kept `README.md` clean (< 115 lines); added `docs/process/README.md` to document internal development and agent governance artifacts without deleting or breaking file references.

Next recommended action: Proceed with T5 (Reviewer R1 hostile pass).
