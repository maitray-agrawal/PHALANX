# TESTING.md - PHALANX Testing Strategy & Commit Guidelines

## Testing Principles
1. **Domain Purity**: A dedicated test (`tests/test_domain_purity.py`) inspects AST / imports of `app/domain` to ensure no imports from outer layers (`app.api`, `app.application`, `app.infrastructure`) or non-deterministic/I/O standard library modules (`socket`, `requests`, `urllib`, `random`, direct un-injected wall clocks).
2. **Deterministic Domain Tests**: All domain unit tests must pass without any network access or database connection.
3. **Application & Boundary Tests**: All HTTP and entry-point tests invoke `app/application` use cases and enforce `extra="forbid"` on Pydantic payloads.
4. **Red Team Suite (`-m redteam`)**: Tests tagged with `@pytest.mark.redteam` simulate adversary actions:
   - Prompt injection attempts attempting to downgrade `STEP_UP` or `DENY` to `ALLOW`.
   - Replay attacks on transaction IDs or webhook IDs.
   - Integer overflow and negative amount attacks.
   - Timing manipulation.
5. **No Regressions**: Any change to crypto, auth, money movement, or CI must include a test that fails without the change.

## Running Tests
```bash
# Standard test suite
pytest -q

# Red team security tests
pytest -q -m redteam

# Full test coverage
pytest -v --tb=short
```

## Commit Message Style
Commit messages must be concise, plain, and descriptive without fluff:
- Format: `<type>(<scope>): <summary>`
- Types: `feat`, `fix`, `test`, `refactor`, `docs`, `ci`, `chore`
- Examples:
  - `feat(bootstrap): initialize repository structure and documentation`
  - `test(domain): verify domain layer purity and layer isolation`
  - `fix(policy): reject negative minor unit amounts in velocity rule`
- Do not commit to `main`. Every prompt works in its branch (e.g. `feat/...`, `fix/...`).
