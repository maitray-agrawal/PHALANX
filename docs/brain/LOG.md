# LOG (newest last; five lines per session: date | task | what changed | commands run and results | next)
2026-11-09 | T1: Confirm F2 and F1b results against running container and PostgreSQL.
Changed: Brain files updated with verified evidence; no production code modified.
Commands: pytest test_demo_dataset_alignment (1 pass), test_fail_closed (2 pass), test_keys (3 pass), test_mandate_integrity (5 pass), test_proxy_rate_limiting (4 pass), test_migration_upgrade (1 pass), test_reconciliation (11 pass), test_negative_controls (7 pass), playwright against container (0 CSP violations, 12 pass, 3 fail on empty queue expectations).
Findings closed: G1, G4, G5, G6, U2, U3, U5. Open: G7, G8, U1, U4.
Next: T2 (F1c-fix).
2026-11-09 | T2: Fix reconciler invariants (a, b, c, d), fail-closed credentials, proof enforcement.
Changed: db_budget_repo.py, services.py, paypal.py, reconciler.py, routes.py, scripts/reconcile.py.
Commands: pytest test_reconciliation.py (15 passed); full pytest -q (363 passed in 177s); pytest -q -m redteam (105 passed); npm test (28 passed); ruff check (clean); mypy app (39 files clean).
Findings closed: H1, H2, H3, H4, H5, H6, H7, G2.
Next: T3 (F1b fail closed, keys, schema, test DB, audits) & T4 (env alignment).
