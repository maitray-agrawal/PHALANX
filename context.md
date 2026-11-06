# context.md
Phase: R6 Complete (Containerization & Full CI Gating Pipeline)   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline.
- app/infrastructure: Multi-stage container packaging (Node 20 + Python 3.12 slim), single managed SQLAlchemy engine, dialect-specific connect args, request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter, PayPal Sandbox rail adapter (with deterministic request IDs from intent digests, real provider states, live webhook signature verification API), UTC clock, Bandit security scan.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, timing-safe admin reset (hmac.compare_digest with min 24-char token), fail-closed dependencies (mandatory PostgreSQL outside test mode), fail-closed webhooks (503 if unconfigured), and demo mode guardrails (/v1/auth/demo-token, /v1/ledger/tamper, /restore gated on DEMO_MODE).
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PHALANX visual identity and 0/90 geometric logo mark; 4 core operational scenes (Request Console, Step-Up Approvals, Tamper-Evident Ledger, Active Mandate) + Reconciliation & Security Center.
- tests: 269 automated backend tests (unit, integration, concurrency, PostgreSQL persistence and shared budget stress, database failure modes, external failure, MCP parity, red-team A1-I5, payment rail order lookup, metrics alignment).

Completed R6 Milestones:
- R6.1: Multi-stage Dockerfile: Node 20 alpine builder for SPA (Vite + TypeScript), Python 3.12 slim builder with uv for wheels/packages, and production slim runtime with dedicated non-root user `appuser`, healthcheck (`/healthz`), static mounting of `web/dist`, and fail-closed boot script execution prior to `exec uvicorn`.
- R6.2: Docker Compose hardening: every secret passed strictly from environment variables without default fallbacks (`POSTGRES_PASSWORD`, `SECRET_KEY`, `ADMIN_TOKEN`, `PAYPAL_CLIENT_SECRET`); `db` healthcheck using `pg_isready`; `api` depends on `service_healthy`; named persistent volume `postgres_data`; restart policy `unless-stopped`; configurable ports (`POSTGRES_PORT` default 5433, `APP_PORT` default 8000). Fixed PostgreSQL 16 schema permissions in `scripts/init_db.sh` (`GRANT ALL ON SCHEMA public TO phalanx_app`).
- R6.3: Comprehensive CI push-gate pipeline in `.github/workflows/ci.yml`: 8 gating jobs including `backend` (ruff, mypy, PostgreSQL service, boot sequence, pytest with 75% coverage floor), `redteam` (adversarial invariant suite), `bandit` (AST security analysis), `pip-audit` (dependency vulnerability scanner), `frontend` (lint, tsc, vitest, build), `gitleaks` (scanning full history with `.gitleaks.toml`), `docker` (multi-stage build and Trivy vulnerability scan), and `smoke` (starts compose stack, verifies 200 on `/healthz`, `/readyz`, and `/`, then tears down). Deploy hook triggers only on main after all 8 jobs pass.
- R6.4: Hardened `render.yaml`: Starter plan for both web service and PostgreSQL database (guaranteeing survival past evaluation/judging through 15 Dec 2026), removed free plan contradictions, removed `ALLOWED_HOSTS='*'` in favor of explicit domain list.
- R6.5: Live container verification: verified `docker compose config`, `docker compose build --no-cache`, `docker compose up -d`, 200 responses on `/healthz`, `/readyz`, and `/`, API container restart with persistence verification of `mandate_default_sandbox` from PostgreSQL named volume, and clean teardown without `down -v`.

Test status:
- Backend: 262 passed, 7 skipped (269 total backend tests across 17 test files; 7 skipped are Docker PostgreSQL tests that run in CI)
- Red Team: 72/72 red-team tests passed in 24.81s
- Concurrency / Transaction Audit: 15/15 passed in `tests/concurrency/test_transaction_audit.py`
- Payment Rail Suite: 5/5 passed in `tests/unit/test_payment_rail.py`
- Security Audit: bandit -r app reports 0 issues (0 High, 0 Medium, 0 Low)
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 38 source files)
- Frontend: ESLint clean (0 errors), TypeScript clean (`npx tsc --noEmit`), Vitest passed (11/11 across 2 suites), Vite production build clean
- Gitleaks: 0 leaks found across full history
- Trivy: Clean (0 security findings on container image)
- Docker Compose: Verified healthy, all 3 endpoints 200, API restart persistent

Next recommended action: Commit all R6 containerization and CI gating pipeline changes directly to main.
