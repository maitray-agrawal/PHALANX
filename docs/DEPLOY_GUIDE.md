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
5. Fill in the required secrets (`sync: false`) in Render Dashboard:
   - `SECRET_KEY`: generated 64-char hex key
   - `ADMIN_TOKEN`: generated 64-char hex token
   - `MANDATE_SIGNING_KEY_HEX`: generated 64-char Ed25519 signing key
   - `RECONCILE_SECRET`: generated 64-char secret
   - `DATABASE_URL`: Neon direct PostgreSQL connection URI
   - `PAYPAL_CLIENT_ID`: PayPal Sandbox App Client ID
   - `PAYPAL_CLIENT_SECRET`: PayPal Sandbox App Secret
   - `PAYPAL_WEBHOOK_ID`: PayPal Webhook ID
   - `GEMINI_API_KEY`: Google Gemini API Key
6. Click **Apply**. Render will build the Docker container and start the service.

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
