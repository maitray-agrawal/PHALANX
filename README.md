# PHALANX
### Authorization & Governance Layer for Autonomous Financial Agents

[![CI](https://github.com/maitray-agrawal/PHALANX/actions/workflows/ci.yml/badge.svg)](https://github.com/maitray-agrawal/PHALANX/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](pyproject.toml)
[![Frontend React](https://img.shields.io/badge/frontend-React%20%2B%20TS-61DAFB.svg)](web/)

> **AstraX product. PayPal AI Hackathon 2026 entry. Sandbox only, no real money.**

---

## The Thesis
**Agents propose. Policies decide. Humans authorize exceptions. Every transaction leaves cryptographic evidence.**

Giving autonomous AI agents raw API keys to move funds invites prompt injection, catastrophic hallucination, and run-away balance drains. PHALANX introduces a cryptographically verified security boundary:
1. **Ed25519-Signed Mandates**: Principals issue versioned, cryptographically sealed financial authority boundaries (capping single limits, instant thresholds, lifetime budgets, allowed payees, and expiry).
2. **Pure Deterministic Policy Core**: A pure domain engine (zero I/O, zero clock, zero randomness; 1.10 µs median latency) enforces hard invariants.
3. **The LLM is Never in the Authorization Path**: Untrusted user text is isolated inside delimiters. Auxiliary ML/heuristic signals can only *tighten* decisions (`ALLOW` -> `STEP_UP` -> `DENY`), never loosen them.
4. **Digest-Bound Step-Up Approvals**: Transactions exceeding instant thresholds require human supervisor authorization bound to the RFC 8785 canonical SHA-256 intent digest.
5. **Cryptographic Shield-Wall Ledger**: Every decision is chained (`prev_hash` -> `event_hash`). Any direct database SQL tampering breaks verification.

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker & Docker Compose

### 1. Backend Setup
```bash
# Clone repository
git clone https://github.com/maitray-agrawal/PHALANX.git
cd PHALANX

# Setup virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (using pip with dev optional dependencies or requirements-dev.txt)
pip install -e ".[dev]"
# Or: pip install -r requirements.txt -r requirements-dev.txt && pip install -e .

# Start PostgreSQL database (optional, in-memory ledger runs by default for tests)
docker compose up -d db

# Run FastAPI backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Web Console
```bash
cd web
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Running Verification & Tests

```bash
# Run all 245 backend tests (unit, integration, concurrency, and red-team)
pytest -q

# Run adversarial red-team suite only (67 threat catalog tests)
pytest -q -m redteam

# Run linters, formatters, and typecheckers
ruff check . && ruff format --check .
mypy app

# Run frontend test suite (11 tests) & production bundle build
cd web && npm run lint && npx tsc --noEmit && npm test -- --run && npm run build
```

---

## Judge Demo Guide (3 Hero Scenes)

1. **Scene 1: Autonomous Pre-Authorized Payment**:
   - Persona: `AGENT`
   - Amount: $25.00 ("Monthly subscription renewal")
   - Result: `ALLOW` instant dispatch via PayPal Sandbox, transaction ID generated, recorded to ledger.
2. **Scene 2: Human Step-Up Approval**:
   - Persona: `AGENT` submits $1,200.00 equipment invoice.
   - Result: `STEP_UP` review required.
   - Switch persona to `APPROVER`: Review canonical SHA-256 digest locking the intent details. Click Authorize to execute.
3. **Scene 3: Cryptographic Shield-Wall Ledger & Tamper Detection**:
   - Persona: `AUDITOR`
   - Open Audit Ledger and click **Verify Chain** -> Verification reports green (100% intact).
   - Click **Simulate Database Tamper** -> Blockchain visual immediately turns red at the broken link index, exposing the modified block!
   - Reset state anytime via `POST /v1/admin/reset`.

---

## Built With (AI Tools & Models Transparency)
In compliance with hackathon rules, this project utilized:
- **Google Antigravity IDE & Agentic Pair Programming**: Autonomous scaffolding, refactoring, and test writing.
- **Gemini 2.5 Flash**: Assisting in documentation synthesis, threat modeling, and red-team test vector creation.

---

## License
Apache-2.0
