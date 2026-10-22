# DECISIONS.md - PHALANX Architectural & Technical Decisions

Every architectural decision and dependency addition must be recorded here before adoption.

---

### DEC-0001: Clean Hexagonal Architecture Layers
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Autonomous financial agents require airtight authorization guarantees, testability, and auditability.
- **Decision**: Code is organized into 4 strict layers:
  1. `app/domain`: Pure entities, value objects, ports, and invariants. Zero I/O, no system clock, no randomness.
  2. `app/application`: Use cases, policy orchestration, audit trail dispatch.
  3. `app/infrastructure`: Adapters for PostgreSQL, external sandbox APIs (PayPal), security cryptography.
  4. `app/api`: FastAPI HTTP routers and request/response adapters.
- **Consequences**: `app/domain` imports nothing from outer layers. An automated unit test verifies this constraint.

---

### DEC-0002: Monies Represented as Integer Minor Units
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Floating-point rounding errors are catastrophic in financial calculations.
- **Decision**: All currency amounts (USD cents, etc.) must be stored and computed as integer minor units (`int`). Currency codes must conform to ISO 4217.
- **Consequences**: No float or Decimal conversions allowed in pure domain calculation logic.

---

### DEC-0003: LLM Non-Authority in Financial Authorization
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: LLMs can hallucinate, be jailbroken via prompt injection, or behave nondeterministically.
- **Decision**: The LLM is never in the primary authorization path. Deterministic policies make base authorization decisions. ML or heuristic anomaly signals are only allowed to escalate risk levels (`ALLOW` -> `STEP_UP` -> `DENY`), never lower or grant permissions.
- **Consequences**: System remains deterministic and resilient against prompt injection attacks.

---

### DEC-0004: Injected UTC Clock & Deterministic Timestamps
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Time-dependent policies (e.g. 24h rolling velocity limits) must be reproducible in unit tests and immune to clock drift or timezone bugs.
- **Decision**: `datetime.now()` is prohibited in domain logic. UTC timestamps are injected from application service callers via explicit clock ports.
- **Consequences**: All domain policy evaluations are 100% reproducible given the same inputs and timestamp.

---

### DEC-0005: Initial Python Backend Dependencies
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Bootstrapping Python 3.12 backend with high-performance web framework, type safety, ORM, migrations, and quality tools.
- **Decision**: Adopt the following pinned core and dev dependencies:
  - `fastapi==0.115.8`: Modern ASGI web framework for Python.
  - `uvicorn[standard]==0.34.0`: ASGI server for FastAPI.
  - `pydantic==2.10.6`: Data validation with `extra="forbid"`.
  - `pydantic-settings==2.8.0`: Environment configuration management.
  - `sqlalchemy==2.0.38`: Database ORM and query builder (parameterized queries).
  - `alembic==1.14.1`: Database schema migrations.
  - `psycopg[binary]==3.2.4`: PostgreSQL DB driver.
  - `httpx==0.28.1`: HTTP client for testing and external sandbox APIs.
  - `pytest==8.3.4`: Test framework.
  - `pytest-asyncio==0.25.3`: Async test support for pytest.
  - `ruff==0.9.7`: Fast linter and formatter.
  - `mypy==1.15.0`: Strict static type checker.
- **Consequences**: All dependencies pinned; changes require updating this file.

---

### DEC-0006: Initial Frontend Web Dependencies
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Human operator review dashboard for exceptions and transaction ledger.
- **Decision**: Adopt the following pinned web dependencies under `web/`:
  - `react`: 19.x
  - `react-dom`: 19.x
  - `vite`: 6.x
  - `typescript`: 5.x
  - `ag-grid-react` & `ag-grid-community`: 33.x for tabular audit and approval logs.
  - `lucide-react`: Lightweight iconography.
  - `vitest`: Unit test runner for frontend components.
- **Consequences**: Frontend is treated as untrusted; backend validates all commands.
