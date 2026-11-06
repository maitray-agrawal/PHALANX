# context.md
Phase: R10 Complete (Performance & Reliability Engineering, Load Testing, Caching & Chaos Hardening)   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator, PrincipalSessionMemory, DeterministicKnowledgeBase, CompositeAdvisoryPipeline. SubmitApprovalRequestDTO enforces strict mass-assignment prevention (`extra="forbid"`).
- app/infrastructure: Multi-stage container packaging (Node 20 + Python 3.12 slim), single managed SQLAlchemy engine, dialect-specific connect args, request-scoped sessions, Ed25519 signing/verification (PEM & raw hex), HMAC-SHA256 role tokens (validated >= 32-byte secret key), DatabaseLedgerAdapter, PayPal Sandbox rail adapter (with deterministic request IDs from intent digests, real provider states, live webhook signature verification API, SSRF validation on certificate URLs restricting strictly to `.paypal.com`), UTC clock.
- app/api: Complete FastAPI REST suite with /v1/ and /api/v1/ contracts, strictly validated Bearer tokens, timing-safe admin reset (hmac.compare_digest with min 24-char token), fail-closed dependencies (mandatory PostgreSQL outside test mode), fail-closed webhooks (503 if unconfigured), demo mode guardrails (/v1/auth/demo-token, /v1/ledger/tamper, /restore, /v1/attack-lab/run gated on DEMO_MODE), strict query parameter length validation, CSP header with `default-src 'self'; frame-ancestors 'none'; form-action 'self'`, and HTTP caching controls (`Cache-Control: no-store`, `ETag`, `Vary: Authorization`). Role.AGENT explicitly forbidden from supervisor approval queue.
- app/mcp: Model Context Protocol server exposing financial agent governance tools through identical application authorization boundary.
- web: React + Vite + TypeScript security console with PayPal-inspired clarity, mobile-first design (Inter & JetBrains Mono typography, gold/blue actions, semantic state tokens, 8px grid, max width 1120px). Topbar + bottom tabbar (< 768px), sticky primary action, demo persona switcher, and mandatory footer disclaimer: 'Not affiliated with PayPal.'.
- web screens:
  1. Home: Three numbers (remaining authority, pending approvals, last recorded activity), primary Pay action, recent activity stream.
  2. Pay: Request console with scenario presets, custom input, intent card, instant decision badge with plain reason.
  3. Approvals: Step-up queue, exact request, RFC 8785 canonical digest, inspect diff, Approve/Decline bound to digest, Agent role locking. Stored XSS rendered inertly.
  4. Activity: Ledger journal, visual chain strip, honest provider states, Verify chain trigger, receipt links. Stored XSS rendered inertly.
  5. Mandates: Read-only Ed25519 limits, lifetime budget meter, allowed payees, authorized purposes, signature status.
  6. Attack Lab: 6 canned threat vectors (prompt injection, payee swap, amount tamper after approval, replay, forged webhook, agent self-approval), Run suite trigger, 100% defense verification proof.
  7. Receipt & Verify: Cryptographic receipt card, public SHA-256 hash chain proof verifier, search input. Stored XSS rendered inertly.
- performance & reliability:
  - k6 workload suites: Smoke (1 VU, 1 min, p95: 105.73 ms, 0.00% error rate), Idempotency Storm (200 concurrent VUs, 0.00% error rate, exactly 1 payment disbursed), Single-Budget Contention (100 VUs, 1,460 requests, zero deadlocks), Spike (0-200 VUs in 10s, 1,763 requests, 0.00% errors), Average Load (50 VUs, 5 min, 4,282 requests, 0.00% errors), Stress (50-300 VUs, breaking point at 65 VUs on single row lock, zero corruption), Soak (30 VUs, 15 min, 299 MiB memory, 66 FDs, zero leak).
  - Invariants: 13,296 ledger blocks verified with 0 broken blocks; spent + reserved <= allocated (0 violations); exactly 1 payment per idempotency key (0 duplicates); 0 orphan reservations.
  - Caching: 6/6 tests passed (no-store on auth, mandate ETag 304, immutable hashed assets, index.html no-cache, Vary: Authorization, read-your-writes, cold-start stampede).
  - Chaos: 5/5 tests passed (PayPal 5xx fail-closed, PayPal timeout -> RECONCILE state machine transition, container restart recovery in < 2.5s, Postgres fail-closed, webhook deduplication, clock skew rejection).
  - PayPal stub: 4/4 tests passed (normal, delay, 5xx, timeout).
- tests: 317 automated backend tests (317 passed, 7 skipped in non-Docker), 105 red-team tests; 28 Vitest frontend tests; 7 Playwright end-to-end tests.

Test status:
- Backend: 317 passed, 7 skipped (324 total backend tests across 22 test files)
- Red Team: 105/105 red-team tests passed
- Performance & Invariants: All 4 accounting and ledger invariants verified across 13,296 events
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 38 source files)
- Frontend: Vitest passed (28/28 tests across 3 suites), ESLint clean (0 errors, 0 warnings), TypeScript clean (0 errors), build clean
- E2E: Playwright passed (7/7 tests)
- Documentation: docs/PERFORMANCE_REPORT.md authored and published.

Next recommended action: Commit all changes directly to main and push.
