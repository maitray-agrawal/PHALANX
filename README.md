# PHALANX

Authorization & Governance Layer for Autonomous Financial Agents.

> AstraX product. PayPal AI Hackathon 2026 entry. Sandbox only, no real money.

## Core Rules
- **Agents propose. Policies decide. Humans authorize exceptions.**
- Every transaction leaves cryptographic evidence on an immutable append-only ledger (`ledger_events`).
- The LLM is never in the authorization path. Signals only tighten decisions (`ALLOW` -> `STEP_UP` -> `DENY`), never lower them.

## Architecture
- `app/domain`: Pure business logic (zero I/O, no system clocks, no randomness).
- `app/application`: Orchestration, policy coordination, audit trail dispatch.
- `app/infrastructure`: PostgreSQL adapters, sandbox connectors, UTC clock.
- `app/api`: FastAPI HTTP routers (`/healthz`, `/readyz`, `/api/v1/authorize`).
- `app/mcp`: Model Context Protocol integration layer.
- `web`: Operator review dashboard (React, Vite, TypeScript, AG Grid).

## Development Commands
```bash
# Start PostgreSQL Database
docker compose up -d db

# Run Backend Test Suite
pytest -q

# Run Red Team Security Suite
pytest -q -m redteam

# Lint and Typecheck
ruff check . && ruff format --check .
mypy app

# Frontend Web Console
cd web && npm ci && npm run lint && npx tsc --noEmit && npm test -- --run && npm run build
```

## License
Apache-2.0
