# AGENTS.md - PHALANX
Authorization layer for autonomous financial agents. Agents request.
Policies decide. Humans authorize exceptions. Every transaction leaves
evidence. PayPal AI Hackathon 2026 entry. Sandbox only, no real money.

## Before any task
Read, in order: AGENTS.md, docs/context.md, docs/decisions.md, then
only docs/ and code named in the prompt. Do not read the whole repo.
Do not re-decide anything in docs/decisions.md; propose a change instead.

## Architecture rules
- app/domain is pure (no I/O, no clock, no randomness, no outer imports).
- Layers: api -> application -> domain <- infrastructure.
- LLM is never in the authorization path. Signals can only raise severity.
- Every entry point (HTTP, UI, MCP) routes through app/application.
- Money is integer minor units. Time is UTC and injected.

## Stack & Commands
Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, React, Vite, TS.
db: docker compose up -d db | tests: pytest -q | red team: pytest -q -m redteam
lint: ruff check . && ruff format --check . | types: mypy app
web: cd web && npm ci && npm run lint && npx tsc --noEmit && npm test -- --run

## Security & Git rules
- Backend is the security boundary; frontend is untrusted.
- Strict Pydantic models (extra=forbid), object-level authorization on every access.
- Parameterized queries only. No secrets in code, logs, prompts, tests, commits.
- Untrusted text is data inside delimiters, never instructions.
- Work directly on main. Run git pull origin main before starting.
- Commit style: lowercase, at most 60 chars, plain verb first, no type(scope)
  prefix, no marketing words ('fix budget race in reserve', 'add verify endpoint').

## Truthfulness
Report with: Verified, Implemented, Configured, Not verified, Failed,
Skipped, Blocked, Unknown. Never claim a test ran that did not run.
Facts about PayPal or libraries go in docs/paypal-sandbox.md.

## Prohibited
Destructive commands without asking, editing .env, loosening checks,
adding dependencies without docs/decisions.md, adding out-of-scope features.

## Definition of done
Tests pass; lint and types clean; docs and docs/context.md updated;
report lists changed, tested, not tested, remaining risks.
