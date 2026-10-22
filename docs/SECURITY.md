# SECURITY - Security Controls & Production Gate Audit

Owner prompt: P1

---

## 1. Security Architecture & Controls

PHALANX implements multi-layered security controls derived from the Antigravity Master Project Manual v2.0:

### 1.1 Boundary Enforcement (Manual Section 2, 18)
- **Backend as Single Trust Boundary**: The web console and external clients are untrusted. All authorization, policy checks, and approvals occur strictly on the backend.
- **Strict Parsing**: Every incoming JSON payload is validated using strict Pydantic v2 models with `extra="forbid"` and explicit string length bounds.
- **Pure Domain Isolation**: The authorization policy core in `app/domain` contains zero I/O, zero clock calls, and zero external dependencies. Enforced via automated AST inspection in CI.

### 1.2 Secrets & Credential Management (Manual Section 19)
- **Zero Secret Defaults**: `pydantic-settings` models define no fallback defaults for sensitive keys (`SECRET_KEY`, `PAYPAL_CLIENT_SECRET`, etc.). Missing production secrets prevent application boot.
- **Git Hygiene & Secret Scanning**: Local git hooks run `gitleaks` via `.pre-commit-config.yaml`. `.env` is strictly gitignored; only `.env.example` (variable names only, no values) is committed.

### 1.3 Data Integrity & Storage Security (Manual Section 27, 56.13, 56.14)
- **Parameterized SQL Only**: All database operations use SQLAlchemy 2 core parameterized statements. Raw string concatenation is prohibited.
- **DB Role Privilege Least Privilege**: The `phalanx_app` database user role has `INSERT` and `SELECT` privileges only on `ledger_events`. `UPDATE`, `DELETE`, and `TRUNCATE` are revoked at the PostgreSQL engine level.
- **Monetary Integrity**: Currency values are strictly represented as non-negative integer minor units (e.g. cents). Floating point math is prohibited in domain logic.

### 1.4 AI / LLM Guardrails (Manual Section 41-44)
- **LLM Non-Authority**: The LLM is never in the critical path of authorization. Deterministic code evaluates rules.
- **Asymmetric Risk Escalation**: Heuristic signals or ML risk assessments are strictly advisory and can only raise decision severity (`ALLOW` -> `STEP_UP` -> `DENY`), never lower it.
- **Delimited Untrusted Text**: Invoices, vendor descriptions, and external prompt texts are encapsulated in strict data boundaries and never evaluated as code or instructions.

---

## 2. Production Gates Mapping (Manual Section 56)

Every gate from the manual is audited here as **Adopted**, **Scaled**, or **Skipped**, with an explicit justification.

| Gate ID | Description | Status | Rationale / Implementation |
|---|---|---|---|
| **56.1** | Input Validation & Schema Enforcement | **Adopted** | Strict Pydantic v2 models (`extra="forbid"`), length limits, regex patterns on all routes. |
| **56.2** | SQL Injection Prevention | **Adopted** | Parameterized queries only via SQLAlchemy 2. No dynamic string SQL execution. |
| **56.5** | Automated CI Validation Gates | **Adopted** | GitHub Actions workflow (`ci.yml`) runs Ruff, Mypy strict, Pytest unit/concurrency/redteam, and web build. |
| **56.7** | Zero Secret Defaults in Configuration | **Adopted** | `Settings` class in `app/infrastructure/config.py` specifies empty/no-default secrets. |
| **56.9** | Observability & Audit Trail | **Scaled** | Scaled to append-only PostgreSQL `ledger_events` table and structured logging (Datadog/ELK skipped for hackathon scope). |
| **56.12** | Database Migrations & Versioning | **Scaled** | Managed via Alembic migrations and container initialization scripts. |
| **56.13** | Concurrency Control & State Isolation | **Adopted** | Row-level locking on balance reservations and atomic state transitions to prevent double-spend races. |
| **56.14** | Request Idempotency & Deduplication | **Adopted** | Unique `idempotency_key` checking on transaction intents; PayPal webhook `event_id` deduplication. |
| **56.16** | Deterministic Business Logic | **Adopted** | Pure domain layer (`app/domain`) with injected UTC timestamps and integer math. |
| **56.17** | Transaction State Machine Rigor | **Adopted** | State machine validates allowable transitions (`PENDING` -> `AUTHORIZED` -> `CAPTURED` / `VOIDED`). |
| **56.19** | External Failure Circuit Breakers | **Scaled** | Fast-fail timeout handlers (3s timeout on PayPal API calls); graceful degradation on network drops. |
| **56.31** | Automated Rollback Capabilities | **Scaled** | Container restarts and Alembic downgrade migrations for schema rollback. |
| **56.36** | Production Deployment Pipeline | **Scaled** | Scaled to multi-stage slim Dockerfile and Render web service deployment. |
| **56.37** | Fresh-Machine Clean Clone Test | **Adopted** | Verified reproducible clean installation via `uv` and `npm ci` without global dependencies. |
| **56.39** | Health & Readiness Probes | **Adopted** | `GET /healthz` (liveness) and `GET /readyz` (live DB connectivity probe) returning 200/503. |
| **56.41** | Domain Purity AST Verification | **Adopted** | `test_domain_purity.py` uses AST inspection to guarantee zero I/O, clocks, or outer imports in domain. |
| **56.44** | Adversarial Red-Team Test Suite | **Adopted** | Catalog tests A1 through H2 executed via `pytest -q -m redteam`. |
| **56.47** | Non-Vibe Verification Gate | **Adopted** | Every claim in PRD has a corresponding verifiable automated test or tool proof in `docs/EVIDENCE.md`. |
| **17, 19** | Passwords & Multi-Factor Auth (MFA) | **Skipped** | Prototype uses signed agent tokens and operator session role tokens for hackathon scope; no consumer passwords. |
| **22** | File Upload Security & Malware Scan | **Skipped** | PHALANX does not accept raw file or document uploads (JSON intents only). |
| **26** | Bot Protection & Captchas | **Skipped** | Service is a backend API and authenticated operator console, not a public consumer form. |
| **34, 35** | Landing Page Copy & SEO Optimization | **Skipped** | Project is focused purely on security authorization architecture, not marketing. |
| **46, 48** | End-User Analytics & Legal Pages | **Skipped** | Internal governance tool prototype; terms/privacy policies deferred to commercialization. |
