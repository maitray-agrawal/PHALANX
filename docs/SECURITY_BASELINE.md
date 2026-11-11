# PHALANX Security Baseline & Architecture Audit

**Document Version**: 1.0.0  
**Audit Date**: November 7, 2026  
**Auditor Role**: Senior Security & Release Engineer  
**Scope**: Codebase, Containers, Database Architecture, CI/CD, Secrets & PayPal Sandbox Integration  

---

## 1. Existing Security Configuration

PHALANX implements a multi-tiered defense-in-depth architecture adhering to strict hexagonal boundaries (`api -> application -> domain <- infrastructure`).

### 1.1 Core Security Invariants
1. **Domain Purity**: The decision engine in `app/domain` is purely deterministic (no network I/O, no system clock, no random generation, and no outer imports).
2. **LLM Out of Authorization Path**: The Language Model is never permitted to authorize, loosen, or approve financial transactions. Heuristic and auxiliary signals may only elevate risk and tighten decisions (`ALLOW` $\to$ `STEP_UP` $\to$ `DENY`). Untrusted text is strictly isolated inside structured delimiters.
3. **Cryptographically Signed Mandates**: Financial limits (single transaction limits, instant thresholds, velocity caps, allowed payees, and temporal validity) are bounded by Ed25519 digital signatures. Verification occurs over RFC 8785 canonical JSON bytes.
4. **Tamper-Evident Hash-Chained Audit Ledger**: Every policy evaluation and reconciliation step emits a tamper-evident event chained to its predecessor (`prev_hash` $\to$ `event_hash`). PostgreSQL triggers prohibit `UPDATE`, `DELETE`, and `TRUNCATE` operations on `ledger_events`.
5. **Fail-Closed Principle**: If database connectivity, PayPal credentials, or cryptographic keys are unavailable or unconfigured, the system fails closed with HTTP 503 Problem+JSON before reserving any funds. No financial decisions or reservations occur during outage states.

### 1.2 Authentication & Cryptographic Keys
- **HKDF Key Derivation**: Session tokens and internal HMAC signatures are derived from `SECRET_KEY` using HKDF with domain-separated info strings (`phalanx-token-hmac`, `phalanx-mandate-ed25519`).
- **Role-Based Access Control (RBAC)**: Object-level authorization on all endpoints (`AGENT`, `APPROVER`, `AUDITOR`, `OPERATOR`, `PRINCIPAL`, `ADMIN`). Agents cannot request payments on behalf of other agent identifiers.
- **Admin Endpoints**: Protected by `ADMIN_TOKEN` via `verify_admin_reset_access`.
- **Content Security Policy (CSP)**: Strict headers configured in `app/api/middleware.py`:
  - `default-src 'self'`
  - `script-src 'self'`
  - `style-src 'self' 'unsafe-inline'`
  - `font-src 'self'` (self-hosted fonts in `web/public/fonts`)
  - `img-src 'self' data: https://api-m.sandbox.paypal.com`
  - `connect-src 'self'`
  - `frame-ancestors 'none'`
  - `form-action 'self'`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- **Rate Limiting**: Sliding-window in-memory limiter with trusted proxy detection (`forwarded_allow_ips` / `trusted_proxy_count`) preventing IP spoofing.

---

## 2. Existing Database Architecture

- **Engine**: PostgreSQL 16 Alpine running in Docker container `phalanx-postgres`.
- **Database Names**:
  - `phalanx_db`: Primary application database.
  - `phalanx_test`: Isolated test database for integration and concurrency test suites.
- **Role Separation**:
  - `postgres`: Superuser / database administrator (used only for initialization and administrative operations).
  - `phalanx_app`: Dedicated least-privilege application role. Granted `CONNECT`, `USAGE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE` on operational tables; `UPDATE`, `DELETE`, and `TRUNCATE` are strictly revoked on `ledger_events`.
- **Volume Persistence**: Named Docker volume `postgres_data` mapping to `/var/lib/postgresql/data`. Database volume is preserved across container recreations and restarts.
- **Schema Management**: Managed via Alembic migrations (`alembic/versions/`). Boot sequence (`scripts/boot.py`) validates that the database revision matches the declarative schema head.

---

## 3. Required Environment Variables

| Variable | Scope | Purpose | Sensitivity | Default in Production |
|---|---|---|---|---|
| `POSTGRES_PASSWORD` | Infrastructure / DB | Superuser administrator password for PostgreSQL container | **HIGH** | *None (Must be injected)* |
| `PHALANX_APP_DB_PASSWORD` | App / Infrastructure | Application role password for `phalanx_app` | **HIGH** | *None (Must be injected)* |
| `DATABASE_URL` | Local Host Backend | Connection URL for host application (`phalanx_app`) | **HIGH** | *Must be injected via .env* |
| `CONTAINER_DATABASE_URL` | Docker Compose API | Connection URL for Docker API container (`phalanx_app`) | **HIGH** | *Derived from compose env* |
| `SECRET_KEY` | Application Backend | Master entropy for HKDF token and key derivation | **CRITICAL** | *Must be injected ($\ge 32$ bytes)* |
| `ADMIN_TOKEN` | API Gateway | Bearer token for admin operations (`/v1/admin/*`) | **CRITICAL** | *Must be injected ($\ge 24$ chars)* |
| `MANDATE_SIGNING_KEY_HEX` | Mandate Governance | Ed25519 private key seed (hex) for signing authority mandates | **CRITICAL** | *Must be injected outside test* |
| `PAYPAL_CLIENT_ID` | External Rail | PayPal Sandbox application client identifier | **MEDIUM** | *Injected from PayPal Sandbox* |
| `PAYPAL_CLIENT_SECRET` | External Rail | PayPal Sandbox application secret | **HIGH** | *Injected from PayPal Sandbox* |
| `PAYPAL_WEBHOOK_ID` | External Rail | Registered PayPal Sandbox webhook ID for verification | **MEDIUM** | *Injected from PayPal Sandbox* |
| `PAYPAL_ENVIRONMENT` | External Rail | Must be strictly `sandbox` | **LOW** | `sandbox` |
| `ENVIRONMENT` | Runtime Control | Execution mode (`development`, `production`, `test`) | **LOW** | `production` |
| `DEMO_MODE` | Runtime Control | Permits simulated tampering and role switching in UI | **LOW** | `false` (in strict prod) |
| `FORWARDED_ALLOW_IPS` | Networking | Comma-separated trusted reverse proxy IPs | **LOW** | `127.0.0.1,::1` |
| `TRUSTED_PROXY_COUNT` | Networking | Number of trusted upstream proxies | **LOW** | `0` |
| `DEMO_TOKEN_RATE_LIMIT`| Rate Limiting | Rate limit for token dispensing (req/min) | **LOW** | `15` |
| `RECONCILER_ENABLED` | Background Task | Background reconciliation worker loop | **LOW** | `false` (enabled in prod) |

---

## 4. Potential Credential Exposures & Historical Findings

1. **Historic Git Commits in `docker-compose.yml`**:
   - Historical commits in the repository prior to rotation contained legacy database credentials and default fallbacks (`${POSTGRES_PASSWORD:-postgres}`).
   - *Risk*: Anyone with repository clone access could observe predictable historical passwords.
   - *Remediation*: Full rotation of database credentials to high-entropy randomly generated values; complete removal of fallback defaults in `docker-compose.yml`; documentation of git history cleanup options for repo owner.
2. **Missing Credential Separation**:
   - `scripts/init_db.sh` previously initialized `phalanx_app` with `$POSTGRES_PASSWORD`, reusing the superuser password for the application role.
   - *Remediation*: Explicitly separate `PHALANX_APP_DB_PASSWORD` from `POSTGRES_PASSWORD`.
3. **Hardcoded Fallbacks in `docker-compose.yml`**:
   - Line 38 had `MANDATE_SIGNING_KEY_HEX` defaulting to a static hex key.
   - *Remediation*: Strip static hex default; require runtime injection or HKDF derivation.
4. **SQL Quoting in `init_db.sh`**:
   - `scripts/init_db.sh` previously used bash interpolation `$POSTGRES_PASSWORD` directly in SQL statements.
   - *Risk*: Special characters in generated passwords (e.g. `'`, `"`, `\`, `$`) could break SQL syntax or introduce injection risks.
   - *Remediation*: Use `psql -v app_pwd="..."` and PostgreSQL `:'app_pwd'` literal parameterization.

---

## 5. Existing Deployment Architecture

- **Host Platform**: Render Cloud Application Hosting.
  - **Service**: `phalanx-governance` (Docker runtime, Starter plan, Oregon region).
  - **Database**: `phalanx-postgres` (Managed PostgreSQL Starter plan, Oregon region, `databaseName: phalanx_db`, user: `phalanx_app`).
  - **Public URL**: `https://phalanx-governance.onrender.com`
  - **Healthchecks**: `/healthz` (liveness), `/readyz` (readiness including database connectivity).
- **CI/CD Pipeline**: GitHub Actions (`.github/workflows/ci.yml`):
  - 8-stage gating pipeline on push: `backend`, `redteam`, `bandit`, `pip-audit`, `frontend`, `gitleaks`, `docker` (Trivy scan), and `smoke` (container compose).
  - Automatic deployment triggers only on `main` when `RENDER_DEPLOY_HOOK` secret is configured and all 8 gates are green.

---

## 6. Release Blockers & Findings

| Item ID | Component | Finding | Severity | Resolution Status |
|---|---|---|---|---|
| **BLK-01** | `db_budget_repo.py` / `services.py` | `LOOKUP_FAILED` was classified under `CONFIRMED_FAILURE`, causing reservations to be released on transient lookup errors. | **CRITICAL** | Remediated in Phase 7 (moved to hold in `RECONCILE`). |
| **BLK-02** | `paypal.py` | `lookup()` treated all HTTP 4xx responses as terminal failure (`FAILED`), which misclassified HTTP 429 (rate limits) and 408 (timeouts). | **HIGH** | Remediated in Phase 7 (differentiated transient vs business 4xx). |
| **BLK-03** | `docker-compose.yml` | Fallback `${POSTGRES_PASSWORD:-postgres}` permitted weak default superuser credentials. | **HIGH** | Remediated in Phase 2 (removed fallback). |
| **BLK-04** | `scripts/init_db.sh` | Direct shell interpolation of passwords in SQL could fail or be vulnerable to special character escaping. | **MEDIUM** | Remediated in Phase 2 (using `psql` variable literals). |
| **BLK-05** | `middleware.py` | Configuration/credential errors raised during authorization were not guaranteed to map to RFC 7807 503 Problem+JSON. | **MEDIUM** | Remediated in Phase 7. |
| **BLK-06** | `render.yaml` | Render Blueprint lacked documented credential rotation procedures. | **LOW** | Addressed in Phase 5 & `docs/CREDENTIAL_ROTATION.md`. |

---

## 7. Dependency Security Audit & Supply Chain Baseline (11 Nov 2026)

### 7.1 Frontend Node.js Dependencies (`web/`)

- **Production Dependencies (`npm audit --omit=dev`)**: **0 vulnerabilities**.
- **Development Tooling Dependencies (`npm audit`)**: 10 vulnerabilities (8 moderate, 2 critical):
  - **`tinypool` (Critical, via `vitest` v3.2.7)**: Prototype pollution gadget in test worker options (GHSA-5gmw-xhrv-c9v3, GHSA-85c8-ppgw-ccpr). Remediation requires Vitest 5.1.0 (major SemVer breaking upgrade).
  - **`minimatch` (Moderate, via `typescript-eslint` -> `@typescript-eslint/typescript-estree`)**: ReDoS / glob amplification (GHSA-g3hv-75wg-m249).
- **Runtime Docker Isolation (Verified)**:
  - In `Dockerfile`, Stage 1 (`frontend-builder`) builds the SPA assets using Node 22 Alpine.
  - Stage 3 (`runner`) copies **only** the compiled static files (`/web/dist`) to `/app/static`.
  - The entire `node_modules` directory, `vitest`, `tinypool`, and `minimatch` are **completely discarded** and **do not exist** in the runtime container image or production bundle.

### 7.2 Backend Python Dependencies

- **Audit Tool**: `pip-audit`
- **Findings**: 36 advisory hits across 4 packages (`cryptography 44.0.1`, `mcp 1.3.0`, `pytest 8.3.4`, `starlette 0.45.3` via `fastapi`):
  - `pytest 8.3.4`: Dev-only test dependency, excluded from runtime container builds.
  - `cryptography 44.0.1`: Pinned version; major upgrade to 46+ requires dependency tree alignment.
  - `starlette 0.45.3`: Pinned transitively by `fastapi==0.115.8`.
- **CI Gating**: Tracked in `.github/workflows/ci.yml` `pip-audit` step with explicit `--ignore-vuln` entries for monitored upstream advisories.
- **Truthfulness Statement**: PHALANX does not claim zero vulnerabilities across its dependency graph. The production web bundle contains 0 vulnerabilities, dev-only tools are quarantined from runtime containers, and backend Python packages are strictly tracked.

