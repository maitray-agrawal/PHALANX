# Contributing to PHALANX

Thank you for your interest in contributing to **PHALANX** — the authorization and governance layer for autonomous financial agents.

Please read this document before proposing changes.

---

## 1. Architectural Invariants

Every contribution must preserve these core invariants:

1. **Domain Purity:**  
   `app/domain` is strictly pure. It must not import any I/O, database libraries, network clients, system clocks, or randomness generators. Enforced by automated AST tests in CI (`tests/unit/test_domain_purity.py`).

2. **Layer Hierarchy:**  
   `api` → `application` → `domain` ← `infrastructure`.  
   All external requests (HTTP, UI, MCP) route through `app/application`. The domain is independent of frameworks.

3. **LLM Non-Authority:**  
   The LLM is never in the authorization path. Heuristic or ML risk signals can only *tighten* decisions (`ALLOW` → `STEP_UP` → `DENY`), never relax them.

4. **Monetary Integrity:**  
   Monetary values are strictly non-negative integer minor units (cents). Floating-point math in financial domain paths is prohibited.

5. **Injected Time:**  
   `datetime.now()` calls in business logic are prohibited; all temporal evaluations receive an explicit UTC clock dependency (`UtcClock`).

6. **Fail-Closed Security:**  
   Missing configurations, cryptographic signature mismatches, and unparseable intents must fail closed with explicit, non-revealing error responses.

---

## 2. Development Setup

### Prerequisites
- **Python:** 3.12+ (managed with `uv` recommended)
- **Node.js:** 20+ and npm 10+
- **Docker & Docker Compose:** for local PostgreSQL

### Step-by-Step Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/maitray-agrawal/PHALANX.git
   cd PHALANX
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env to set local passwords and sandbox credentials
   ```

3. **Install Python backend:**
   ```bash
   uv sync
   # or with pip: pip install -e ".[dev]"
   ```

4. **Start local PostgreSQL:**
   ```bash
   docker compose up -d db
   ```

5. **Run database migrations:**
   ```bash
   uv run alembic upgrade head
   ```

6. **Install frontend dependencies:**
   ```bash
   cd web
   npm ci
   cd ..
   ```

7. **Start local servers:**
   - **Backend:** `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
   - **Frontend:** `cd web && npm run dev`

---

## 3. Verification & Quality Gates

All checks must pass before opening a Pull Request:

### Backend Checks
```bash
# 1. Complete test suite
uv run pytest -q -rs

# 2. Red-team adversarial suite
uv run pytest -q -m redteam

# 3. Model Context Protocol (MCP) suite
uv run pytest -q tests/unit/test_mcp_server.py tests/integration/test_mcp_vs_http.py

# 4. Linting and formatting
uv run ruff check .
uv run ruff format --check .

# 5. Static type checking
uv run mypy app

# 6. Security AST analysis
uv run bandit -r app
```

### Frontend Checks
```bash
cd web

# 1. Component unit and integration tests
npm test -- --run

# 2. TypeScript type check
npx tsc --noEmit

# 3. ESLint
npm run lint

# 4. Production build
npm run build
```

---

## 4. Git & Commit Guidelines

- **Branching:** Create feature branches off `dev`. Never commit directly to `main`.
- **Commit Messages:**  
  - Lowercase, maximum 60 characters.
  - Plain imperative verb first (e.g., `fix budget race in reserve`, `add verify endpoint`).
  - No conventional commit prefixes (e.g. `feat:`, `fix:`) and no marketing adjectives.
- **Pull Requests:** Ensure CI is green before requesting review. Provide clear test evidence and command output in PR descriptions.

