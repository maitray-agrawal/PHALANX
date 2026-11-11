# PHALANX Deployment Guide (Hosted Free Tier & Local Fallback)

This guide documents the exact steps to deploy PHALANX on Render Free Web Service with Neon Serverless Postgres, verify the deployment, and fall back to local execution.

---

## 1. Neon PostgreSQL Database Setup

1. Create a free account at [Neon](https://console.neon.tech).
2. Create a new project: `phalanx-db` (Region: AWS us-west-2 / Oregon to match Render).
3. In Neon's SQL Editor, execute the schema initialization SQL documented in `docs/evidence/neon-manual-setup.md`:
   - Configures the `phalanx_app` role.
   - Sets up immutability trigger functions on the `ledger_events` table (`append_only_ledger` and `no_truncate_ledger`).
4. In Neon dashboard, copy the **Direct Connection String** (recommended over connection pooling to avoid transaction pooler state issues with Alembic).
5. Ensure the connection string includes `sslmode=require`, for example:
   ```text
   postgresql://phalanx_app:PASSWORD@ep-sample-123456.us-west-2.aws.neon.tech/neondb?sslmode=require
   ```

---

## 2. Generate Deployment Keys

Run the key generator script locally (prints keys to stdout, never writes them to disk):
```bash
python scripts/gen_keys.py
```
Store the output securely in a password manager.

---

## 3. Render Web Service Deployment (Blueprint)

1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Blueprint**.
3. Connect your GitHub repository (`PHALANX`) and select the `dev` or `main` branch.
4. Render will parse `render.yaml` and configure:
   - Runtime: `docker`
   - Plan: `free`
   - Health Check Path: `/healthz`
   - Auto-deploy: `false` (coordinated with CI deployment hook)
5. Fill in secrets (`sync: false`) in Render Dashboard according to the Environment Secrets Matrix below.
6. Click **Apply**. Render will build the Docker container and start the service.

### Environment Secrets & Boot Invariants Matrix

| Secret / Env Var | Status | Boot Fails If Empty? | Fail-Closed Invariant & Unset Behavior |
| :--- | :---: | :---: | :--- |
| `DATABASE_URL` | **Required** | **YES** | Boot aborts immediately. PostgreSQL connection, Alembic schema migrations (`alembic upgrade head`), and `/readyz` fail closed. Requires `sslmode=require` for Neon. |
| `SECRET_KEY` | **Required** | **YES** | Boot aborts immediately (`validate_secret_key()`). Outside test, requires >= 32 bytes for HKDF master secret derivation. |
| `ADMIN_TOKEN` | Optional | No | Boot succeeds. Admin diagnostic (`GET /v1/admin/client-ip`) and reset (`POST /v1/admin/reset`) reject calls with `503 Service Unavailable` ("ADMIN_TOKEN unconfigured"). |
| `PAYPAL_CLIENT_ID` | Optional* | No | Boot succeeds. If `PAYMENT_RAIL=paypal`, payment dispatch aborts before any reservation with `503 Service Unavailable` ("PayPal credentials unconfigured"). |
| `PAYPAL_CLIENT_SECRET` | Optional* | No | Boot succeeds. Same as `PAYPAL_CLIENT_ID` — fail-closed before reservation. |
| `PAYPAL_WEBHOOK_ID` | Optional | No | Boot succeeds. Inbound webhook endpoint (`POST /v1/webhooks/paypal`) fails closed with `503 Service Unavailable` ("PAYPAL_WEBHOOK_ID unconfigured"). |
| `MANDATE_SIGNING_KEY_HEX` | Optional | No | Boot succeeds. If unset, HKDF-SHA256 deterministically derives a 32-byte Ed25519 signing seed from `SECRET_KEY` using label `phalanx-mandate-ed25519`. |
| `GEMINI_API_KEY` | Optional | No | Boot succeeds. Invoice Agent extraction cleanly falls back to certified recorded baseline runs (`is_live: false`, status `RECORDED RUN (GEMINI_API_KEY Unconfigured)`). |
| `RECONCILE_SECRET` | Optional | No | Boot succeeds. External cron endpoints (`POST /v1/admin/reconcile-scheduled`, `POST /v1/admin/daily-reset`) reject calls with `503` when unset. |

*\*Note: Required only for active PayPal sandbox payment execution; when unconfigured, the application boots normally and refuses payment dispatches fail-closed.*

---

## 4. Post-Deployment Verification

Once Render reports the service live, run the verification suite:
```bash
python scripts/verify_live.py https://phalanx.onrender.com --admin-token "$ADMIN_TOKEN"
```
The script will probe:
- `/healthz` (liveness probe)
- `/readyz` (database connectivity probe)
- `/v1/mandates/mandate_default_sandbox` (mandate storage)
- `/v1/approvals` (step-up queue)
- `/v1/ledger` (audit event query)
- `/v1/admin/client-ip` (proxy IP resolver)
- `/v1/invoice-agent/samples` (AI agent samples)

---

## 5. Local Fallback Execution

If Render free tier experiences cold starts or resource limits:
1. Start PostgreSQL locally:
   ```bash
   docker compose up -d db
   ```
2. Apply database migrations:
   ```bash
   uv run alembic upgrade head
   ```
3. Start backend API:
   ```bash
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
4. Start web frontend:
   ```bash
   cd web && npm run dev
   ```
5. Open browser at `http://127.0.0.1:5173`.

