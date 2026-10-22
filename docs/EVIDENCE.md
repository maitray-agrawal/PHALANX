# EVIDENCE - Verification & Tooling Evidence Register

Owner prompt: P2 and every phase

All facts about external systems, PayPal sandbox APIs, libraries, and toolchains are recorded here with verification evidence. Any unverified item is explicitly marked `UNVERIFIED`.

## Environment & Toolchain Proof
- **Date**: 2026-10-22
- **OS**: Windows 11 (64-bit)
- **Python**: Python 3.12.10 verified available at `C:\Users\agraw\AppData\Local\Python\pythoncore-3.12-64\python.exe`
  - *Proof*: `uv python list` output on 2026-10-22: `cpython-3.12.10-windows-x86_64-none C:\Users\agraw\AppData\Local\Python\pythoncore-3.12-64\python.exe`
- **Node.js**: v24.15.0 (`node --version`)
- **npm**: 12.0.1 (`npm --version`)
- **uv**: 0.12.17 (`uv --version`)

## Test & Validation Execution Proof (2026-10-22)
- **Pytest Suite**: 28 passed in 0.24s (`.venv\Scripts\pytest -q`)
- **Red Team Adversarial Suite**: 4 passed, 24 deselected in 0.18s (`.venv\Scripts\pytest -q -m redteam`)
- **Linter & Formatter (Ruff)**: All checks passed, 28 files clean (`.venv\Scripts\ruff check .` & `ruff format --check .`)
- **Static Type Check (Mypy)**: Success: no issues found in 17 source files (`.venv\Scripts\mypy app`)
- **Web Linter & Typecheck**: Passed (`npm run lint`, `npx tsc --noEmit`)
- **Web Test Suite**: 2 passed in 1.36s (`npm test -- --run`)
- **Web Production Build**: Passed in 4.73s (`npm run build`)

## PayPal Sandbox Specifications
- **Sandbox Base URL**: `https://api-m.sandbox.paypal.com` [UNVERIFIED]
- **OAuth Token Endpoint**: `POST /v1/oauth2/token` with HTTP Basic Auth (Client ID : Client Secret) and body `grant_type=client_credentials` [UNVERIFIED]
- **Orders v2 Endpoint**: `POST /v2/checkout/orders` [UNVERIFIED]
- **Payouts v1 Endpoint**: `POST /v1/payments/payouts` [UNVERIFIED]
- **Webhook Signature Verification**: `POST /v1/notifications/verify-webhook-signature` [UNVERIFIED]

## Database & Ledger Security
- **PostgreSQL**: PostgreSQL 16 Alpine container via `docker compose up -d db`.
- **ledger_events Table Privileges**: The application database role only receives `INSERT` and `SELECT` grants on `ledger_events` (no `UPDATE`, no `DELETE`, no `TRUNCATE`).
