# STATE (update after every task)
Date: 11 Nov 2026 | Branch: dev | Last pushed commit on dev: dbecaf3 | CI: PASSING (Run 191, ID 43029134603)
Working tree: modified on dev (alembic/env.py, scripts/boot.py, tests/integration/test_boot_and_migration_hardening.py)
CI Green across all 8 jobs (Run 43029134603); Full local battery verified:
- Backend: 665 passed, 0 skipped, 0 failed in pytest (test_boot_and_migration_hardening.py 8/8 pass)
- Red team: 105 passed, 560 deselected in 6.03s
- Frontend: Vitest passed (30/30 passed), ESLint clean, TypeScript clean, Vite build clean
- Static: ruff check clean, ruff format clean (113 files), mypy app clean (42 files)
Completed: Alembic startup failure diagnosed and resolved:
1. alembic/env.py fileConfig modified with disable_existing_loggers=False so phalanx.boot logger is never silenced.
2. scripts/boot.py hardened: all failure exit paths flush explicit error messages to sys.stderr, with full traceback formatting on unhandled exceptions.
3. tests/integration/test_boot_and_migration_hardening.py added covering logger preservation, fresh DB migration & boot, repeated boot idempotency, revision mismatch fail-closed, missing table fail-closed, missing unique constraint fail-closed, trigger immutability, and stderr traceback emission.

---

# context.md
Phase: Hackathon Submission Artifacts & Gallery Capture Complete   Branches: main, dev
Architecture: Pure Hexagonal Architecture (Ports and Adapters)
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
- Backend full suite: 639 passed, 0 skipped, 0 failed in 404.36s
- Red Team: 105 passed, 0 failed, 534 deselected in 33.24s
- Concurrency & DB: 9/9 passed in test_postgres_concurrency.py, 24/24 passed in test_reconciliation.py, 1/1 passed in test_migration_upgrade.py
- Static Analysis: ruff check clean (0 errors), ruff format clean (112 files checked), mypy app clean (0 errors across 42 source files), bandit clean (0 issues across 9,869 lines of code)
- Frontend: Vitest passed (30/30 tests across 4 suites), ESLint clean (0 errors, 0 warnings), TypeScript clean (0 errors across web codebase via tsc --noEmit), production build clean (4.70s)
- UI Gallery: 15 standard screenshots (11 desktop, 4 mobile) and 15 Devpost crops (1500x1000) verified in docs/gallery/
- Metrics Verification: docs/evidence/metrics.md verified with raw outputs, 49 API routes, 15 policy reason codes, 25-case invoice eval (0.0% bypass rate)
