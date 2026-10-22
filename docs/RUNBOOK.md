# Operational Runbook & Incident Response

PHALANX Authorization & Governance Layer for Autonomous Financial Agents (AstraX / PayPal Hackathon 2026).

---

## 1. System Health & Probes
- **Liveness Probe**: `GET /healthz` -> returns `{"status": "ok"}` (HTTP 200).
- **Readiness Probe**: `GET /readyz` -> verifies database connectivity (HTTP 200 when ready, HTTP 503 if database down).
- **System Diagnostics**: `GET /health` -> detailed timestamp and service version.
- **Cryptographic Ledger Integrity**: `GET /v1/ledger/verify` -> verifies complete SHA-256 hash chain and outputs broken index if tampered.

---

## 2. Sandbox Demo State Reset
For hackathon judges and demo presentations:
```bash
curl -X POST https://phalanx-api.onrender.com/v1/admin/reset \
  -H "X-Phalanx-Role: principal"
```
This resets all spent budget counters, clears the idempotency replay cache, and re-initializes the demo environment safely.

---

## 3. Deployment Procedure

### Local Deployment
```bash
# 1. Start PostgreSQL 16
docker compose up -d db

# 2. Run backend API
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Run frontend React dashboard
cd web && npm run dev
```

### Hosted Production Deployment (Render)
1. Ensure GitHub Actions CI passes on `main` branch.
2. Render automatically syncs via Blueprint (`render.yaml`).
3. Set secret environment variables in Render Dashboard:
   - `PAYPAL_CLIENT_ID`: Sandbox client ID
   - `PAYPAL_CLIENT_SECRET`: Sandbox secret key
   - `PAYPAL_MODE`: `sandbox`

---

## 4. Rollback Procedure
If a breaking deployment or regression occurs:
1. In Render Dashboard, navigate to `phalanx-api` -> **Deploys**.
2. Identify the last green commit SHA.
3. Click **Rollback to this deploy**.
4. Run `GET /healthz` and `GET /v1/ledger/verify` to confirm service recovery.

---

## 5. Incident Response Playbooks

### Incident A: Cryptographic Chain Broken (`is_valid: false`)
- **Trigger**: `GET /v1/ledger/verify` returns `is_valid: false` with a specific `broken_index`.
- **Cause**: Direct database SQL mutation or unauthorized UPDATE/DELETE executed against `ledger_events`.
- **Action**:
  1. Inspect the tampered block: `GET /v1/ledger` and locate block at `broken_index`.
  2. Check PostgreSQL audit logs for unauthorized direct SQL access.
  3. Freeze affected agent mandate: revoke mandate ID via principal authority.
  4. Restore immutable chain from authenticated backup replica if necessary.

### Incident B: PayPal Webhook Signature Failure
- **Trigger**: Repeated `401 Unauthorized` responses on `POST /v1/webhooks/paypal`.
- **Cause**: Missing PayPal transmission headers (`PAYPAL-AUTH-ALGO`, `PAYPAL-TRANSMISSION-SIG`) or expired PayPal cert URL.
- **Action**:
  1. Inspect webhook request headers.
  2. Ensure external traffic routes through legitimate PayPal Sandbox webhook endpoints.

### Incident C: Prompt Injection Storm
- **Trigger**: Spikes in `STEP_UP` reviews with reason `Prompt injection pattern detected`.
- **Cause**: Autonomous agent or external untrusted text attempting instruction overrides.
- **Mitigation**: System automatically escalates decisions and wraps text inside data delimiters. Human reviewers inspect the canonical SHA-256 intent digest before any exception is approved.
