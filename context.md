# context.md
Phase: R5 Complete (Money-Safe State, Mandatory PostgreSQL Invariants & Real Provider States)   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline.
- app/infrastructure: Single managed SQLAlchemy engine, dialect-specific connect args, request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter, PayPal Sandbox rail adapter (with deterministic request IDs from intent digests, real provider states, live webhook signature verification API), UTC clock, Bandit security scan.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, timing-safe admin reset (hmac.compare_digest with min 24-char token), fail-closed dependencies (mandatory PostgreSQL outside test mode), fail-closed webhooks (503 if unconfigured), and demo mode guardrails (/v1/auth/demo-token, /v1/ledger/tamper, /restore gated on DEMO_MODE).
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PHALANX visual identity and 0/90 geometric logo mark; 4 core operational scenes (Request Console, Step-Up Approvals, Tamper-Evident Ledger, Active Mandate) + Reconciliation & Security Center.
- tests: 269 automated backend tests (unit, integration, concurrency, PostgreSQL persistence and shared budget stress, database failure modes, external failure, MCP parity, red-team A1-I5, payment rail order lookup, metrics alignment).

Completed R5 Milestones:
- R5.1: Unified database connection layer in `app/infrastructure/database.py` with a single managed engine, dialect-specific connect args (`connect_timeout=5`, `pool_size=10`, `max_overflow=20`, `pool_recycle=1800` for PostgreSQL; `timeout=15`, `check_same_thread=False` for SQLite), and request-scoped session dependency `get_db_session()`.
- R5.2: Injected database session factory and `DatabaseLedgerAdapter` into `AuthorizationService` via `app/api/dependencies.py`. In-memory adapters and `FakePaymentRail` permitted only when `ENVIRONMENT=test` or `PAYMENT_RAIL=fake`. Mandatory PostgreSQL enforced outside test mode: unreachability immediately fails boot and readiness (zero silent fallback).
- R5.3: Hardened `PayPalPaymentRailAdapter` in `app/infrastructure/paypal.py`: removed silent `sandbox_tx_` fallback when credentials are missing (clear error returned); derived `PayPal-Request-Id` deterministically as `req_{intent_digest[:32]}` from `compute_intent_digest()`; enforced real provider states (`ORDER_CREATED`, `BUYER_APPROVAL_REQUIRED`, `APPROVED`, `CAPTURE_REQUESTED`, `COMPLETED`, `RECONCILE`, `FAILED`); guarded settlement so orders are never labeled `SETTLED` before real sandbox capture.
- R5.4: Hardened `scripts/boot.py` to exit non-zero on any database or migration failure. Verified Alembic schema revision matches migration head via `MigrationContext` and `ScriptDirectory`. Seeded only missing demo data with mandate validity through 31 Mar 2027.
- R5.5: Added PostgreSQL CI container (`postgres:16-alpine`, port 5433) in `.github/workflows/ci.yml`. Added tests for restart persistence of budgets, idempotency, approvals and ledger; two service instances sharing one budget; 50 parallel requests on one budget (`tests/concurrency/test_postgres_concurrency.py`); database down at startup and readiness down after startup (`tests/integration/test_database_failure_modes.py`).

Test status:
- Backend: 262 passed, 7 skipped (269 total backend tests across 17 test files; 7 skipped are Docker PostgreSQL tests that run in CI)
- Red Team: 72/72 red-team tests passed in 24.81s
- Concurrency / Transaction Audit: 15/15 passed in `tests/concurrency/test_transaction_audit.py`
- Payment Rail Suite: 5/5 passed in `tests/unit/test_payment_rail.py`
- Security Audit: bandit -r app reports 0 issues (0 High, 0 Medium, 0 Low)
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 38 source files)
- Frontend: ESLint clean (0 errors), TypeScript clean (`npx tsc --noEmit`), Vitest passed (11/11 across 2 suites), Vite production build clean

Next recommended action: Commit all R5 money-safe state changes directly to main.
