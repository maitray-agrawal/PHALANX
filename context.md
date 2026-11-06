# context.md
Phase: R4 Complete (Application Security Hardening & Red-Team Probes)   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline.
- app/infrastructure: Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), append-only ledger adapter, PayPal Sandbox rail adapter (Payouts with Orders v2 fallback and live webhook signature verification API), UTC clock, Bandit security scan.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens (zero bypass headers/unsigned tokens), timing-safe admin reset (hmac.compare_digest with min 24-char token), fail-closed webhooks (503 if unconfigured), and demo mode guardrails (/v1/auth/demo-token, /v1/ledger/tamper, /restore gated on DEMO_MODE).
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PHALANX visual identity and 0/90 geometric logo mark; 4 core operational scenes (Request Console, Step-Up Approvals, Tamper-Evident Ledger, Active Mandate) + Reconciliation & Security Center.
- tests: 263 automated tests (unit, integration, concurrency, external failure, MCP parity, red-team A1-I5, security audit regressions, payment rail order lookup, metrics alignment).

Completed R4 Milestones:
- R4.1: Deleted unsigned 'demo-<role>' token bypass and X-Phalanx-Role header bypass paths from `app/infrastructure/tokens.py` and `app/api/auth.py`.
- R4.2: Enforced >= 32-byte `SECRET_KEY` validation for token signing outside test environments; verified boot failure (`scripts/boot.py`) and readiness failure (`/readyz`) when unconfigured or weak.
- R4.3: Hardened admin reset (`/v1/admin/reset`): removed fallback constant `phalanx-admin-demo-key`, enforced `ADMIN_TOKEN` length >= 24 chars (503 if unconfigured), and implemented constant-time comparison via `hmac.compare_digest`.
- R4.4: Implemented PayPal's documented webhook signature verification (`/v1/notifications/verify-webhook-signature`) in `PayPalPaymentRailAdapter` with headers, event deduplication, and fail-closed 503 behavior when `PAYPAL_WEBHOOK_ID` or credentials are unset. Documented in `docs/EVIDENCE.md`.
- R4.5: Added `DEMO_MODE` configuration (default false). Gated `/v1/auth/demo-token`, `/v1/ledger/tamper`, and `/restore` strictly behind `DEMO_MODE`. Demo tokens are signed with active secret key, bound to `principal_treasury`, and rate-limited.
- R4.6: Removed hardcoded database passwords from `docker-compose.yml`, `scripts/init_db.sql`, and `app/infrastructure/config.py`. Enforced `POSTGRES_PASSWORD` from environment, created `scripts/init_db.sh` for restricted role setup, and added configurable `POSTGRES_PORT` (default 5433) and `APP_PORT` (default 8000).
- R4.7: Added 5 redteam regression probe tests in `tests/redteam/test_redteam.py` (Family I: Security Probes I1-I5). Proved reproduction by verifying test failures against old code before verifying green against the fixes.

Test status:
- Backend: 259 passed, 4 skipped (263 total backend tests across 16 test files)
- Red Team: 72/72 red-team tests passed in 16.68s
- Concurrency / Transaction Audit: 15/15 passed in `tests/concurrency/test_transaction_audit.py`
- Payment Rail Suite: 5/5 passed in `tests/unit/test_payment_rail.py`
- Security Audit: bandit -r app reports 0 issues (0 High, 0 Medium, 0 Low)
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 38 source files)
- Frontend: ESLint clean (0 errors), TypeScript clean (`npx tsc --noEmit`), Vitest passed (11/11 across 2 suites), Vite production build clean

Next recommended action: Review and commit security hardening changes directly to main.
