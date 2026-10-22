# TESTING - Testing Strategy, Adversarial Catalog & Commit Guidelines

Owner prompt: P1, updated in P9

## Testing Principles
1. **Domain Purity**: A dedicated AST test (`tests/unit/test_domain_purity.py`) inspects `app/domain` to ensure zero outer layer imports (`app.api`, `app.application`, `app.infrastructure`) and zero non-deterministic or I/O modules (`socket`, `requests`, `urllib`, `random`, direct un-injected wall clocks).
2. **Deterministic Domain Tests**: All domain unit tests must pass without network access or database connections.
3. **Application & Boundary Tests**: All HTTP and entry-point tests invoke `app/application` use cases and enforce `extra="forbid"` on Pydantic payloads.
4. **Red Team Suite (`-m redteam`)**: Tests tagged with `@pytest.mark.redteam` simulate adversary actions:
   - Prompt injection attempts attempting to override policies.
   - Manipulation attempts aiming to downgrade `STEP_UP` or `DENY` to `ALLOW`.
   - Integer overflow and negative amount attacks.
5. **No Regressions**: Any change to crypto, auth, money movement, or CI must include a test that fails without the change.

## Running Tests
```bash
# Standard test suite
pytest -q

# Red team security tests
pytest -q -m redteam
```

## Commit Message Style
Commit messages must be concise, plain, and descriptive without fluff:
- Format: `<type>(<scope>): <summary>`
- Types: `feat`, `fix`, `test`, `refactor`, `docs`, `ci`, `chore`
- Examples:
  - `feat(bootstrap): initialize repository structure and documentation`
  - `test(domain): verify domain layer purity and layer isolation`
  - `fix(policy): reject negative minor unit amounts in velocity rule`
