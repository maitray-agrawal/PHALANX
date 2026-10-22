# Context - PHALANX

## Project Overview
PHALANX is an authorization and governance layer for autonomous financial agents.
Agents submit transaction/action requests. Configured policies evaluate the request deterministically.
Humans authorize exceptions via step-up review workflows.
Every evaluation and action generates immutable evidence in an append-only audit trail (`ledger_events`).
This project is an entry for the PayPal AI Hackathon 2026 (AstraX product). Sandbox only, no real money.

## Current State
- Branch: `feat/bootstrap`
- Repository status: Foundational bootstrap complete.
- Backend: Clean Architecture (Domain -> Application -> Infrastructure / API) in Python 3.12 with FastAPI. Fully validated with Ruff, Mypy strict, and Pytest (standard and red team).
- Frontend: Single Page Application in React + Vite + TypeScript with AG Grid under `web/`. Fully validated with ESLint, TypeScript compiler, Vitest, and production build.
- CI/CD: GitHub Actions pipeline configured (`.github/workflows/ci.yml`) enforcing linting, static typing, unit tests, red-team checks, and frontend build/tests.

## Architecture & Boundaries
1. **app/domain**: Pure business logic. Zero external I/O, no system clock access (`datetime.now()` prohibited; UTC timestamps injected), no pseudorandom generators. No dependencies on outer layers (`api`, `application`, `infrastructure`). Enforced by AST automated test (`tests/test_domain_purity.py`).
2. **app/application**: Orchestration, use cases, workflow services, policy evaluation coordination. All external entry points (REST API, MCP server, web UI) route through application services.
3. **app/infrastructure**: Concrete adapters implementing domain and application ports (PostgreSQL / in-memory repositories, external PayPal sandbox client, event publishers, UTC clock adapter).
4. **app/api**: FastAPI routes, HTTP serialization, request authentication/validation, mapping HTTP requests to application commands.
5. **Security Model**:
   - Backend is the sole trust boundary.
   - Pydantic models configured with `extra="forbid"`.
   - Money is stored strictly as integer minor units (e.g. cents).
   - Read/write access on `ledger_events` restricted at DB role level (INSERT/SELECT only).
   - LLMs are never permitted in the direct authorization path; heuristic or model signals may only escalate decisions (`ALLOW` -> `STEP_UP` -> `DENY`), never soften them.

## Milestones
- [x] Repository bootstrap: AGENTS.md, context.md, DECISIONS.md, testing and evidence docs.
- [x] Foundation architecture: app/domain, app/application, app/infrastructure, app/api.
- [x] Automated test suites: Domain purity AST, unit tests, and red team adversarial suite.
- [x] Web frontend: React + Vite + TypeScript with AG Grid console and Vitest suite.
- [x] CI/CD pipeline: GitHub Actions workflow for backend & frontend validation.
- [ ] Next milestone: Core persistence layer with SQLAlchemy 2, Alembic migrations, and PostgreSQL container wiring.
- [ ] Next milestone: PayPal sandbox adapter integration & webhook signature validation.
