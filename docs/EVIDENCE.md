# EVIDENCE.md - Verified Facts & Tooling Proof

All facts about external systems, PayPal sandbox APIs, libraries, and toolchains are recorded here with verification evidence. Any unverified item is explicitly marked `UNVERIFIED`.

## Environment & Toolchain Proof
- **Date**: 2026-10-22
- **OS**: Windows 11 (64-bit)
- **Python**: Python 3.12.10 verified available at `C:\Users\agraw\AppData\Local\Python\pythoncore-3.12-64\python.exe`
  - *Proof*: `uv python list` output on 2026-10-22: `cpython-3.12.10-windows-x86_64-none C:\Users\agraw\AppData\Local\Python\pythoncore-3.12-64\python.exe`
- **Node.js**: v24.15.0
  - *Proof*: `node --version` output on 2026-10-22: `v24.15.0`
- **npm**: 12.0.1
  - *Proof*: `npm --version` output on 2026-10-22: `12.0.1`
- **uv**: 0.12.17
  - *Proof*: `uv --version` output on 2026-10-22: `uv 0.12.17 (635500036 2026-09-18 x86_64-pc-windows-msvc)`

## Test & Validation Execution Proof (2026-10-22)
- **Pytest Suite**: 19 passed in 0.07s
  - *Proof*: `.venv\Scripts\pytest -q` output on 2026-10-22: `19 passed in 0.07s`
- **Red Team Adversarial Suite**: 4 passed, 15 deselected in 0.03s
  - *Proof*: `.venv\Scripts\pytest -q -m redteam` output on 2026-10-22: `4 passed, 15 deselected in 0.03s`
- **Linter & Formatter (Ruff)**: All checks passed, 21 files already formatted
  - *Proof*: `.venv\Scripts\ruff check .` and `ruff format --check .` output on 2026-10-22: `All checks passed!`
- **Static Type Check (Mypy)**: 0 issues across 15 source files
  - *Proof*: `.venv\Scripts\mypy app` output on 2026-10-22: `Success: no issues found in 15 source files`
- **Web Linter & Typecheck**: Passed
  - *Proof*: `npm run lint` and `npx tsc --noEmit` exited with code 0 on 2026-10-22.
- **Web Test Suite**: 2 passed in 1.42s
  - *Proof*: `npm test -- --run` exited with code 0 on 2026-10-22.
- **Web Production Build**: Passed in 4.85s
  - *Proof*: `npm run build` completed bundle generation (`dist/index.html`, `dist/assets/`) on 2026-10-22.

## PayPal Sandbox Specifications
- **Sandbox Base URL**: `https://api-m.sandbox.paypal.com` [UNVERIFIED - pending sandbox live verification]
- **OAuth Token Endpoint**: `POST /v1/oauth2/token` with HTTP Basic Auth (Client ID : Client Secret) and body `grant_type=client_credentials` [UNVERIFIED]
- **Orders v2 Endpoint**: `POST /v2/checkout/orders` [UNVERIFIED]
- **Payouts v1 Endpoint**: `POST /v1/payments/payouts` [UNVERIFIED]
- **Webhook Signature Verification**: `POST /v1/notifications/verify-webhook-signature` [UNVERIFIED]
  - Headers required: `PAYPAL-AUTH-ALGO`, `PAYPAL-CERT-URL`, `PAYPAL-TRANSMISSION-ID`, `PAYPAL-TRANSMISSION-SIG`, `PAYPAL-TRANSMISSION-TIME` [UNVERIFIED]

## Database & Ledger Security
- **PostgreSQL**: PostgreSQL 16 Alpine container via `docker compose up -d db`.
- **ledger_events Table Privileges**: The application database role only receives `INSERT` and `SELECT` grants on `ledger_events` (no `UPDATE`, no `DELETE`, no `TRUNCATE`).
