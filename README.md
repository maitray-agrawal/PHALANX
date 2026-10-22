# PHALANX

**Authorization & Governance Layer for Autonomous Financial Agents**

PHALANX acts as an immutable shield between autonomous AI agents and financial execution APIs (e.g. PayPal Sandbox).
Agents propose transactions; deterministic policies evaluate requests; human supervisors inspect exceptions via step-up challenges; every decision leaves cryptographic evidence on an append-only ledger.

> Entry for PayPal AI Hackathon 2026. Sandbox only, no real money.

## Architecture

- `app/domain`: Pure financial entities, value objects, ports, and policy evaluators (zero I/O, no system clock, no randomness).
- `app/application`: Use cases, policy orchestration, audit trail dispatch.
- `app/infrastructure`: Concrete adapters (PostgreSQL, PayPal sandbox client).
- `app/api`: FastAPI HTTP routers and security filters.
- `web`: React + Vite + TypeScript operator console with AG Grid.

## Quickstart

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker & Docker Compose

### Commands
```bash
# Database
docker compose up -d db

# Run tests
pytest -q

# Run red team security tests
pytest -q -m redteam

# Code quality
ruff check . && ruff format --check .
mypy app

# Web console
cd web
npm ci
npm run lint
npx tsc --noEmit
npm test -- --run
npm run build
```
