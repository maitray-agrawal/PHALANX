# DECISIONS.md - PHALANX Architectural & Technical Decisions

Every architectural decision and dependency addition must be recorded here before adoption.

| ID | Decision | Reason | Alternatives | Tradeoff |
|---|---|---|---|---|
| D-001 | New repo PHALANX, history starts 22 Oct | Hackathon dating, clean history | Reuse KuberSetu repo | Reimplement a few helpers |
| D-002 | Deterministic policy engine decides; LLM proposes | LLM cannot be a security boundary | LLM approvals | Less 'magic', more defensible |
| D-003 | FastAPI monolith with ports and adapters | 3-week solo build, testable core | Microservices | Single deploy unit |
| D-004 | PostgreSQL | Transactions, locks, constraints for reservations | SQLite | Hosting cost to verify |
| D-005 | Ed25519 over RFC 8785 canonical JSON for mandates | Maintained libraries, small signatures | HMAC, JWT | Server-held key is an integrity seal only |
| D-006 | ML and heuristics are advisory and can only tighten | Honest, testable | Trained fraud model | No accuracy headline |
| D-007 | Merge commits, no squash | Visible history | Squash merge | Longer log |
| D-008 | Payment rail chosen by sandbox evidence (ADR after P2) | Capability not guaranteed | Assume Vault | Spike time |
| D-009 | Python 3.12 dependencies: fastapi==0.115.8, uvicorn==0.34.0, pydantic==2.10.6, pydantic-settings==2.8.0, sqlalchemy==2.0.38, alembic==1.14.1, psycopg[binary]==3.2.4, httpx==0.28.1, pytest==8.3.4, pytest-asyncio==0.25.3, pytest-cov==6.0.0, hypothesis==6.128.0, ruff==0.9.7, mypy==1.15.0 | Pinned core and testing dependencies | Unpinned ranges | Explicit updates required |
| D-010 | Web dependencies: React 19, Vite 6, TypeScript 5, AG Grid 33, Vitest 3 | Modern operator console with enterprise audit grid | Custom HTML table | AG Grid dependency weight |
| D-011 | cryptography==44.0.1 | Standard library-grade Ed25519 asymmetric signing and verification for mandates (RFC 8032) | PyNaCl, custom ECC | C-extension dependency |
| D-012 | PaymentRail: Route A Payouts v1 primary with Orders v2 fallback (ADR-009) | Autonomous agent disbursement without interactive payer present; automatic fallback trigger if 403 scope missing | Vault MIT only | Payouts requires business sandbox account |
| D-013 | rfc8785==0.1.4 | Official RFC 8785 (JSON Canonicalization Scheme) library | Hand-rolled json.dumps | Dependency addition pinned in pyproject.toml |
| D-014 | bandit==1.8.3 | Python AST security linter to verify zero high security findings | Manual code review only | Dev-only static analysis dependency |
| D-015 | mcp==1.3.0 | Official Python Model Context Protocol SDK for agent tool exposure | Custom JSON-RPC server | Maintained official SDK with standard stdio transport |
| D-016 | Savepoint rollback (begin_nested) & DB-backed AgentBudgetModel for F4/F5 | Prevent raw IntegrityError crashes on concurrent duplicate requests and guarantee multi-instance persistent budget isolation | In-memory only locks | Requires PostgreSQL/SQLite transaction savepoints |
| D-017 | PHALANX Master UI/UX Brand System | Enterprise financial security interface adhering to styleboard: 0/90 geometry, diamond bindu nodes, Light/Dark/System theme switcher, and interactive decision pipeline | Generic fintech dashboard | Custom tokens and SVG components |
| D-018 | Mandatory PostgreSQL outside test mode & deterministic PayPal-Request-Id | Prevent silent in-memory fallback in staging/production, fail-closed on unreachable DB, and enforce end-to-end idempotency on PayPal rails via intent digest | In-memory fallback in production | Unreachable DB causes immediate boot/readiness failure (safe fail-closed) |
| D-019 | Multi-stage Docker packaging & strict CI push-gate matrix | Container serves SPA and API under non-root user; CI gates all branches with backend coverage floor, redteam, bandit, pip-audit, frontend build, gitleaks, Trivy image scan, and Compose smoke test | Single monolithic image or untested deploys | Slightly longer CI pipeline (all parallelized) |
| D-020 | @axe-core/playwright==4.10.1 | Automated WCAG 2.1 AA accessibility audit and violation scanning in Playwright E2E suite | Manual browser inspection | devDependency in web/package.json |
| D-021 | Orders v2 Two-Phase Sandbox Flow & Discrete Provider States | Support explicit buyer approval and capture phases with honest states (ORDER_CREATED, BUYER_APPROVAL_REQUIRED, APPROVED, CAPTURE_REQUESTED, COMPLETED, RECONCILE, FAILED) | Direct settlement without capture | Fail-closed security: never mark complete before capture |
| D-022 | Asynchronous Reconciler with Exponential Backoff and Timeout NEEDS_REVIEW | Settle completed payments, release definite failures/expiries, mark timeouts as NEEDS_REVIEW without budget leaks (never auto-release), and fail-closed with 503 before any reservation on unconfigured rail credentials | Synchronous blocking or silent timeout release | Requires scheduled, webhook, or background triggers |

# DECISIONS (append only; merge with existing entries)
D-021 Branch model: main and dev; agents push dev only; PR dev to main merged by the owner on green CI.
D-022 Brain folder docs/brain holds facts, findings, state, plan and log; prompts live in docs/brain/prompts.
D-023 Fail closed for money, mandate, auth and database code; no silent fallback.

