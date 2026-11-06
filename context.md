# context.md
Phase: R7 Complete (PayPal-Style Cached Endpoints & Adversarial Attack Lab)   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline.
- app/infrastructure: Multi-stage container packaging (Node 20 + Python 3.12 slim), single managed SQLAlchemy engine, dialect-specific connect args, request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter, PayPal Sandbox rail adapter (with deterministic request IDs from intent digests, real provider states, live webhook signature verification API), UTC clock, Bandit security scan.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, timing-safe admin reset (hmac.compare_digest with min 24-char token), fail-closed dependencies (mandatory PostgreSQL outside test mode), fail-closed webhooks (503 if unconfigured), demo mode guardrails (/v1/auth/demo-token, /v1/ledger/tamper, /restore, /v1/attack-lab/run gated on DEMO_MODE), and HTTP caching controls (ETag conditional 304, no-store, immutable assets).
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PHALANX visual identity and 0/90 geometric logo mark; 4 core operational scenes (Request Console, Step-Up Approvals, Tamper-Evident Ledger, Active Mandate) + Reconciliation & Security Center.
- tests: 276 automated backend tests (unit, integration, concurrency, PostgreSQL persistence and shared budget stress, database failure modes, external failure, MCP parity, red-team A1-I5, payment rail order lookup, metrics alignment, cached endpoints, receipts, attack lab).

Completed R7 Milestones:
- R7.1: GET /v1/overview: Executive summary returning exactly three values (`remaining_authority`, `pending_approval_count`, `last_activity`), authenticated and protected with `Cache-Control: no-store` and `Vary: Authorization`.
- R7.2: GET /v1/activity?cursor=&limit=: Paginated activity feed returning `receipt_id`, `decision`, `amount`, `payee`, `reason_code`, `provider_state`, and `timestamp_utc`.
- R7.3: Cryptographic receipts (`GET /v1/receipts/{id}` & `GET /v1/receipts/{id}/verify`): Receipts hold intent digest, mandate id & version, decision, reason codes, ledger sequence, and hash chain proof. Public read-only `/verify` endpoint recomputes SHA-256 block hash and chain proof, returning PASS or broken block without leaking sensitive details.
- R7.4: Adversarial Attack Lab (`POST /v1/attack-lab/run`): Gated on `DEMO_MODE=true` (404 when disabled); runs 6 canned attacks (prompt injection, payee swap, amount tamper after approval, replay, forged webhook, agent self-approval) through real application services; returns individual reason codes and proof that zero attacks reached PayPal.
- R7.5: Cache-correct headers: Middleware enforces `Cache-Control: no-store, no-cache, must-revalidate` and `Vary: Authorization` on authenticated responses; `/assets/*` cached with `public, max-age=31536000, immutable`; `/` and `index.html` set to `no-cache`; `GET /v1/mandates/{id}` emits deterministic ETag and returns `304 Not Modified` on matching `If-None-Match`.
- R7.6: Verification & Docs: 7 comprehensive tests in `tests/integration/test_cached_endpoints_and_attack_lab.py`, updated `docs/API_SPEC.md`, all tests passing with 0 lint, type, or security errors.

Test status:
- Backend: 269 passed, 7 skipped (276 total backend tests across 18 test files; 7 skipped are Docker PostgreSQL tests that run in CI)
- Red Team: 72/72 red-team tests passed
- Security Audit: bandit -r app reports 0 issues (0 High, 0 Medium, 0 Low)
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 38 source files)
- Frontend: Vitest passed (11/11 tests across 2 suites), TypeScript and build clean

Next recommended action: Commit all R6 containerization and CI gating pipeline changes directly to main.
