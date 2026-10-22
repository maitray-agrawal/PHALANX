# TESTING - Testing Strategy, Adversarial Catalog & Commit Guidelines

Owner prompt: P1, updated in P9

---

## 1. Test Architecture & Layers

Testing in PHALANX is structured into five distinct verification layers:

```
┌────────────────────────────────────────────────────────────┐
│ Layer 5: Web Console (Vitest + RTL + AG Grid rendering)    │
├────────────────────────────────────────────────────────────┤
│ Layer 4: Red-Team Adversarial Suite (Catalog A1 to H2)     │
├────────────────────────────────────────────────────────────┤
│ Layer 3: Concurrency & Race Condition Suite                │
├────────────────────────────────────────────────────────────┤
│ Layer 2: API & Boundary Integration (FastAPI TestClient)   │
├────────────────────────────────────────────────────────────┤
│ Layer 1: Pure Domain Unit Tests & AST Purity Enforcement   │
└────────────────────────────────────────────────────────────┘
```

### Layer 1: Pure Domain Unit Tests (`tests/unit/`)
- Tests value objects ([Money](file:///d:/PHALANX/app/domain/models.py#L48-L64)), transaction intents, and decision escalation logic.
- Guaranteed zero I/O, no network calls, and deterministic wall-clock injection.
- Automated AST purity inspection (`test_domain_purity.py`) verifies that `app/domain` contains zero imports from `app.api`, `app.application`, `app.infrastructure`, or disallowed I/O modules (`socket`, `requests`, `urllib`, `random`, direct un-injected wall clocks).

### Layer 2: API & Integration Tests (`tests/integration/`)
- Tests FastAPI routes (`/healthz`, `/readyz`, `/api/v1/authorize`).
- Verifies strict Pydantic payload rejection on unknown keys (`extra="forbid"`).
- Tests dependency injection wiring with test doubles for clock and ledger ports.

### Layer 3: Concurrency & Race Tests (`tests/concurrency/`)
- Simulates concurrent transaction attempts against shared velocity budgets.
- Tests race conditions on balance reservations and idempotency key locks using `asyncio.gather`.

### Layer 4: Red-Team Adversarial Suite (`tests/redteam/`)
- Tagged with `@pytest.mark.redteam`.
- Executes attack scenarios from the threat model catalog (A1 through H2):
  - Direct and indirect prompt injection attempts.
  - Decision downgrade manipulation (`DENY` -> `ALLOW`, `STEP_UP` -> `ALLOW`).
  - Integer overflow, sub-cent floating point, and negative minor unit attacks.
  - Replay attacks on transaction IDs and PayPal webhook IDs.

### Layer 5: Web Console Tests (`web/src/App.test.tsx`)
- Executes in Vitest with JSDOM and React Testing Library.
- Verifies AG Grid audit log rendering, KPI summaries, and step-up queue states.

---

## 2. Test Execution Commands

```bash
# Standard test suite (fast unit, integration, concurrency)
pytest -q

# Red-team adversarial security suite
pytest -q -m redteam

# Full test suite with coverage report
pytest --cov=app --cov-report=term-missing

# Web frontend unit tests
cd web && npm test -- --run
```

---

## 3. Code Coverage Floors

Automated CI enforces the following coverage thresholds via `pytest-cov`:
- **`app/domain`**: **100% Statement and Branch Coverage**. Every invariant, validation branch, and money calculation must be covered without exception.
- **`app/application`**: **>= 90% Statement Coverage**. All use cases, DTO validations, and orchestration paths.
- **Overall Backend Core**: **>= 85% Total Statement Coverage**.

---

## 4. Commit Message Style (Manual Section 10)

Commit messages must be concise, plain, and descriptive without marketing fluff:
- **Format**: `<type>(<scope>): <summary>`
- **Types**:
  - `feat`: New capability or component.
  - `fix`: Bug fix or security hardening.
  - `test`: Addition or modification of unit, integration, or red-team tests.
  - `refactor`: Code change that neither fixes a bug nor adds a feature.
  - `docs`: Documentation updates or additions.
  - `ci`: CI pipeline, build configuration, or dependabot updates.
  - `chore`: Routine maintenance, dependency bumps, or cleanup.
- **Rules**:
  - Small commits (6 to 10 commits per phase).
  - Imperative, lower-case summaries.
  - Never commit to `main` without green CI.
  - Never force-push (`--force` prohibited).
- **Examples**:
  - `feat(policy): implement rolling 24h velocity cap in domain`
  - `test(redteam): add webhook signature forgery test D2`
  - `fix(ledger): revoke update and delete grants on ledger table`
