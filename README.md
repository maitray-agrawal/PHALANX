# PHALANX

Authorization layer for autonomous financial agents.

> PayPal AI Hackathon 2026 entry. Sandbox only, no real money.  
> Not affiliated with PayPal.

## The Problem

Giving autonomous agents direct API credentials to move funds creates severe financial risk. A prompt injection, hallucinated invoice, or runaway loop can drain balances without oversight. Relying on an LLM to police another LLM fails because natural language prompts can bypass language model guardrails.

## Three Core Metrics

- **$0.00 Unauthorized Leakage**: 100% block rate across prompt injection, vendor impersonation, and tamper attacks.
- **0ms Policy Core I/O**: Pure domain engine with zero database queries, zero network calls, and no clock dependency.
- **100% Hash-Chained Auditability**: Every transaction intent, policy evaluation, and money outcome is cryptographically linked.

## What It Is

PHALANX sits between autonomous agents and payment rails. Agents propose payments, deterministic policies decide whether they proceed, humans review exceptions, and every action is recorded in an append-only audit ledger. The language model is never in the authorization path.

## How It Works

```
Agent Request (JSON)
       │
       ▼
┌──────────────┐      ALLOW     ┌────────────────────────┐
│ Pure Policy  │───────────────>│ PayPal Sandbox Capture │
│ Engine       │                └────────────────────────┘
└──────┬───────┘                            ▲
       │                                    │ Approved
       │ STEP_UP       ┌─────────────────┐  │
       ├──────────────>│ Human Reviewer  ├──┘
       │               │ (Approver Role) │
       │ DENY          └─────────────────┘
       ▼
  Blocked & Logged
       │
       ▼
┌─────────────────────────────────┐
│ Hash-Chained Ledger (PostgreSQL)│
└─────────────────────────────────┘
```

1. **Signed Mandates**: Principals set Ed25519-signed rules defining single limits, velocity caps, allowed payees, and expiry.
2. **Pure Decision Core**: Evaluates transactions with zero I/O, zero network calls, and no clock access. Invariants cannot be overridden by untrusted inputs.
3. **Digest-Bound Approvals**: Transactions exceeding instant limits require human supervisor sign-off bound to an RFC 8785 canonical SHA-256 digest.
4. **Audit Ledger**: Events form a cryptographic hash chain. Database modifications break the chain and are flagged.

## Running Locally

```bash
docker compose up --build
```
API: `http://localhost:8000`, Web UI: `http://localhost:5173`.

## Running Tests

```bash
uv run pytest -q && uv run pytest -q -m redteam
uv run ruff check . && uv run ruff format --check . && uv run mypy app
cd web && npm test -- --run && npm run build
```

## Run the Demo

- **Hosted Demo**: `https://phalanx-demo.onrender.com` (placeholder; set after deployment).
- **Cold Starts**: Render free tier sleeps after 15 min inactivity; ping `GET /healthz` every 10 min to keep warm during live demos.
- **Automation Schedule**: External cron pings `GET /healthz` every 10m; `POST /v1/admin/reconcile-scheduled` every 30–60m (`X-Reconcile-Secret`); `POST /v1/admin/daily-reset` daily.
- **Local Path**: `docker compose up --build` (API on `http://localhost:8000`, UI on `http://localhost:5173`).
- **Honest Limits**: Free-tier deployment, in-memory webhook deduplication (resets on container restart), PayPal sandbox only.

## Demo Mode

When `DEMO_MODE=true` (the default in sandbox setups), any visitor can select a persona in the UI, generate signed tokens for demo accounts, and trigger ledger tamper simulations. Disable demo mode in non-sandbox environments.

## PayPal Integration

PHALANX integrates with PayPal Orders v2 and webhook notifications:
- **Order Created Is Not Paid**: In the Orders v2 flow, creating an order reserves the intent and generates an approval link. Funds do not move until buyer approval and explicit capture occur.
- **Webhook Authenticity**: Inbound webhooks are validated against PayPal signature verification endpoints before event processing.
- **Sandbox Scope**: Payouts and disbursements require explicit permissions enabled on sandbox test accounts.

## Known Limits

- **Sandbox Only**: Built for sandbox environments with simulated and test funds; not for production money movement.
- **Database Scope**: Ledger integrity verification runs on the connected PostgreSQL instance.
- **Human Latency**: Step-up transactions pause until a human supervisor reviews and signs the canonical digest.

## Built With

Built with Google Antigravity and the Gemini models.

## License

Apache-2.0
