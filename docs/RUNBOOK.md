# Operational Runbook & Incident Response (Manual 56.29 - 56.31)

PHALANX Authorization & Governance Layer for Autonomous Financial Agents (AstraX / PayPal AI Hackathon 2026).

---

## 1. System Health & Diagnostics

- **Liveness Probe**: `GET /healthz` -> returns `{"status": "ok"}` (HTTP 200).
- **Readiness Probe**: `GET /readyz` -> verifies database connectivity (HTTP 200 when ready, HTTP 503 if database down).
- **System Diagnostics**: `GET /health` -> detailed timestamp and service version.
- **Cryptographic Ledger Integrity**: `GET /v1/ledger/verify` -> verifies complete SHA-256 hash chain and outputs `broken_index` if tampered.

---

## 2. Sandbox Demo State Reset (Manual 56.30)

For hackathon judges and evaluation testing, the demo state can be reset cleanly without restarting the service.

### Method A: Admin Token (Automated Probes & CI)
```bash
curl -X POST https://phalanx-governance.onrender.com/v1/admin/reset \
  -H "X-Admin-Token: phalanx-admin-demo-key"
```

### Method B: Principal Role Header (Demo Dashboard)
```bash
curl -X POST https://phalanx-governance.onrender.com/v1/admin/reset \
  -H "X-Phalanx-Role: principal"
```

**Actions Performed on Reset**:
1. Lifetime and rolling 24-hour spent budget counters are reset to zero.
2. Idempotency replay cache is cleared.
3. Pending step-up approval queue is restored with initial demo invoice (`req_stepup_1001`).
4. Any auditor-tampered ledger blocks are restored to pristine valid hash chains.

---

## 3. Production Deployment Procedure

### Automated Continuous Deployment
1. Ensure GitHub Actions CI passes on the `main` branch.
2. The `deploy` job in `.github/workflows/ci.yml` automatically triggers the Render Deploy Hook:
   ```bash
   curl -f -X POST "$RENDER_DEPLOY_HOOK"
   ```
3. Render pulls the latest `main` commit, executes `pip install uv && uv sync && cd web && npm ci && npm run build`.
4. Render runs the startup command:
   ```bash
   uv run python scripts/boot.py && uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
5. Idempotent boot script checks schema, installs triggers, and seeds demo mandate valid until 31 Mar 2027.

---

## 4. Rollback to Previous Git Tag or Release (Manual 56.31)

If a breaking deployment or regression occurs:

### Step 1: Rollback via Render Dashboard
1. Navigate to Render Dashboard -> **phalanx-governance** -> **Deploys**.
2. Locate the previous successful deploy corresponding to the stable Git tag (e.g., `v0.1.0`).
3. Click the three dots (`...`) next to the deploy and select **Rollback to this deploy**.
4. Render immediately switches traffic to the previous immutable release image without rebuilding.

### Step 2: Rollback via Git (Emergency Hotfix)
```bash
git checkout main
git revert HEAD --no-edit
git push origin main
```
CI will run all tests and trigger the deploy hook upon passing.

### Step 3: Post-Rollback Health Verification
Run the automated post-deploy smoke test against the live deployment:
```bash
uv run python scripts/post_deploy_smoke.py --url https://phalanx-governance.onrender.com
```

---

## 5. Incident Response Playbooks

### Incident 1: Cold Instance Timeout During Evaluation
- **Symptom**: HTTP client experiences 30-50 second delay or connection timeout on the first request.
- **Root Cause**: Render free instance spun down after 15 minutes of inactivity.
- **Immediate Resolution**:
  Run the pinger script locally or trigger the GitHub Actions keepalive workflow:
  ```bash
  uv run python scripts/pinger.py --url https://phalanx-governance.onrender.com
  ```
- **Permanent Fix**: Ensure the keepalive cron workflow (`.github/workflows/keepalive.yml`) is active (`*/10 * * * *`).

### Incident 2: Cryptographic Chain Broken (`is_valid: false`)
- **Symptom**: `GET /v1/ledger/verify` returns `is_valid: false` with a specific `broken_index`.
- **Root Cause**: Direct SQL mutation or storage tampering detected on `ledger_events`.
- **Action Plan**:
  1. Inspect the tampered block: Query `GET /v1/ledger` and inspect block at `broken_index`.
  2. Restore pristine state immediately:
     ```bash
     curl -X POST https://phalanx-governance.onrender.com/v1/ledger/restore \
       -H "X-Phalanx-Role: auditor"
     ```
  3. Verify chain integrity: Confirm `GET /v1/ledger/verify` returns `is_valid: true`.

### Incident 3: Database Deletion or Render Expiry
- **Symptom**: `GET /readyz` returns `503 Service Unavailable` with database connection error.
- **Root Cause**: Render 30-day free database expiry window elapsed and deleted the database.
- **Action Plan**:
  1. In Render Dashboard, provision a new PostgreSQL instance (select **Starter** plan for permanent survival).
  2. Attach the database connection string to `DATABASE_URL` on `phalanx-governance`.
  3. Restart the web service: `scripts/boot.py` automatically reconstructs all tables, immutability triggers, demo mandates, payees, and genesis records in under 3 seconds.
