# context.md
Phase: P12 Complete (Final Review & Submission Package Ready)   Branch: main   Last green CI: local-verified
Architecture now: Pure Hexagonal Architecture (Ports and Adapters)
- app/domain: Pure deterministic policy engine, Ed25519 mandate invariants, canonical RFC 8785 JSON, cryptographic hash-chained ledger. AST purity test enforced.
- app/application: AuthorizationService, MandateService, LedgerService, ProviderAgnosticLLMClient (quotas, timeouts, retries), IntentExtractor (delimiter isolation, strict Pydantic draft), GroundedExplanationValidator (hallucination rejection & templated fallback), PrincipalSessionMemory (rolling summary, N turns), DeterministicKnowledgeBase ("I do not know" boundary), CompositeAdvisoryPipeline (heuristics, Median/MAD velocity, synthetic TF-IDF + Logistic Regression).
- app/infrastructure: Ed25519 signing/verification, HMAC-SHA256 role tokens, append-only ledger adapter, PayPal Sandbox rail adapter, UTC clock, Bandit security scan.
- app/api: Complete FastAPI REST suite (/v1/payment-requests, /v1/mandates, /v1/decisions, /v1/approvals, /v1/ledger, /v1/ledger/verify, /v1/webhooks/paypal, /v1/admin/reset, /v1/auth/demo-token).
- app/mcp: Model Context Protocol server exposing financial agent governance tools.
- web: React + Vite + TypeScript dashboard in AstraX design system with 4 operational scenes (Request Console, Step-Up Approvals, Tamper-Evident Ledger, Active Mandate).
- tests: 230 automated tests (unit, integration, concurrency, external failure, MCP parity, red-team A1-H2, security audit regressions).

Completed:
- P0: Bootstrap layout, Dockerfile, docker-compose.yml, CI workflows, and AST domain purity test.
- P1: PRD, Threat Model (STRIDE + A1-H2), Security controls audit, and Testing strategy.
- P2: Ed25519 mandate schema, versioning, canonical RFC 8785 JSON serialization, and cryptographic verification.
- P3: Pure deterministic policy engine with precedence hierarchy, instant thresholds, lifetime budget caps, and asymmetric risk escalation.
- P4: Cryptographic SHA-256 hash-chained ledger (`prev_hash` -> `event_hash`), anti-tampering verification, and PayPal rail adapter.
- P5: Comprehensive API routes with object-level authorization, role separation (agent vs approver), and PayPal webhook signature verification.
- P6: LLM intent proposer with delimiter isolation, heuristic prompt injection scanner, and grounded explanation validator.
- P7: AstraX theme UI with Space Grotesk, Inter, and JetBrains Mono fonts, AG Grid audit log, and visual blockchain diagram.
- P8: Full adversarial red-team suite (30 prompt injection vectors, digest tampering, replay attacks, and `docs/TEST_REPORT.md` generator).
- P9: Official Python MCP SDK (`mcp==1.3.0`, FastMCP) exposing `request_payment` and `get_mandate_status` through `app/application`, authenticated strictly as agent identity (`Role.AGENT`), returning decision and pending-approval references only with zero credential leakage, red-team G1 test proving no alternate path, AstraX client example (`examples/astrax_mcp_client.py`), `docs/MCP_INTEGRATION.md`, and 100% decision parity between MCP and HTTP verified in `tests/integration/test_mcp_vs_http.py`.
- P10: Hosted demo deployment pipeline on Render (`render.yaml`), idempotent boot script (`scripts/boot.py`), demo mandate valid until 31 Mar 2027, admin-token reset endpoint (`POST /v1/admin/reset` with `X-Admin-Token`), structured JSON logging with request IDs (`X-Request-ID`), external keepalive pinger (`scripts/pinger.py` and `.github/workflows/keepalive.yml`), deploy-on-green-CI GitHub Actions workflow with Render deploy hook, automated post-deploy smoke test runner (`scripts/post_deploy_smoke.py` validating Scene 1, Scene 2, Scene 3, and admin reset), `docs/DEPLOYMENT.md`, `docs/OBSERVABILITY.md`, updated `docs/RUNBOOK.md`, and Render free tier vs Starter plan evidence and PayPal sandbox longevity recorded in `docs/EVIDENCE.md`.
- P11: Complete documentation and submission package (`README.md`, `ARCHITECTURE.md`, `API_SPEC.md`, `DEMO_SCRIPT.md`, `DEVPOST.md`).
- P12: Comprehensive Independent Release Review & Audit (manual 56.41 vibe-code audit, 56.44 prove-it gate claim mapping, 56.36 fresh-machine installation test, Apache-2.0 license check, Bandit AST 0-issue security scan, git history credential scan, pinned `requirements.txt` / `requirements-dev.txt`, and publication of `docs/FINAL_REPORT.md` with Release Status `QUALIFIED_FOR_SUBMISSION` and Assessment Confidence `HIGH`).
- Hostile Security Review & P0/P1 Remediation: Remediated F-01 unmandated agent fallback (strictly returns None -> DENY), F-02 approval execution rechecks live mandate active status and expiry, F-03 cross-tenant approver IDOR and demo principal alignment, F-04 MCP impersonation guard, F-05 restricted ledger tamper endpoint. Added 6 redteam regression tests in `tests/redteam/test_redteam.py`.

Test status:
- Backend: 230/230 pytest tests passed in 22.66s (including external failure, concurrency, LLM safety, FastMCP tools, parity, and 67 red-team tests)
- Red Team: 67/67 red-team tests passed (catalog A1-H2, B-Crypto 1-5, G1-G6, 30 prompt injection corpus vectors, and F01-F05 hostile review regressions)
- Security Audit: bandit -r app reports 0 issues (0 High, 0 Medium, 0 Low across 4,936 lines)
- Static Analysis: ruff check clean (0 errors), ruff format clean, mypy app clean (0 errors across 38 source files)
- Frontend: ESLint clean (0 errors), TypeScript clean (`npx tsc --noEmit`), Vitest passed (6/6), Playwright smoke tests passed (4/4 on Chromium), Vite production build clean (0 errors)

Next recommended action: Prompt user for approval to apply tag v1.0-submission.
