# FINDINGS (OPEN unless marked). Close only with evidence in LOG. Files are as reported earlier; verify before editing.
| ID | Sev | Problem | Where | Done when | Status |
| G1 | P0 | Mandate service swallows database errors and falls back to the in-memory mandate; lru_cache can pin an in-memory service | app/api/dependencies.py get_mandate_service; app/application/services.py MandateService | Database down gives 503 with no decision; a revoked mandate is never resurrected; no cached fallback | CLOSED |
| G4 | P1 | Mandate Ed25519 key derived from SECRET_KEY, same secret as tokens; broad except may fall back to an ephemeral key | app/infrastructure/crypto.py | HKDF with separate labels, or MANDATE_SIGNING_KEY_HEX required outside test; keys differ; verification survives restart | CLOSED |
| G5 | P1 | Unique event_seq declared without an Alembic revision, duplicate index | app/infrastructure/models.py, alembic/versions | Revision added, duplicate removed, alembic check in CI, upgrade 001 to head test on empty PostgreSQL | CLOSED |
| G6 | P1 | Tests must never touch the demo database | tests/concurrency | TEST_DATABASE_URL points to phalanx_test; scripts/reset_demo.py restores a clean demo | CLOSED |
| G7 | P1 | pip-audit table had a placeholder advisory id; fixes deferred | CI, docs/security.md | Raw pip-audit JSON pasted; only real ids; patch and minor upgrades applied or reachability written | OPEN |
| G8 | P1 | Gitleaks reported 0 leaks although the old password is in history | docs/security.md | Documented; git rev-list --all --count vs scanned count recorded; never cited as proof of a clean history | OPEN |
| H1 | P0 | LOOKUP_FAILED counts as a confirmed failure and releases funds | app/infrastructure/db_budget_repo.py reconcile_reservation | A failed lookup, network error or 5xx keeps the reservation held; only explicit provider terminal states release | CLOSED |
| H2 | P1 | Credential check skipped by hasattr and isinstance guards | app/application/services.py | validate_configuration called directly; wrong result type fails closed with 503 before reservation | CLOSED |
| H3 | P1 | validate_configuration only checks non-empty variables | app/infrastructure/paypal.py | OAuth token probe; invalid credentials give 503 before reservation, never RECONCILE | CLOSED |
| H4 | P1 | Humans can set NEEDS_REVIEW to SETTLED without provider proof; items mixed into the approval queue | app/domain/state_machine.py, services, UI | Own Needs review list; actions are retry lookup and mark failed with a reason (principal or approver); SETTLED only from a lookup; ledger event with actor | CLOSED |
| H5 | P1 | No scheduled reconcile trigger | scripts/, app startup | scripts/reconcile.py and a 60 s loop when RECONCILER_ENABLED=true; documented | CLOSED |
| H6 | P2 | Error text names PayPal environment variables | services, routes | Generic 503; detail only in logs | CLOSED |
| H7 | P2 | Reconciler may use in-memory state | app/application/reconciler.py | Database only; a second instance resolves a request created by the first | CLOSED |
| H8 | P1 | Webhook cert-URL check accepts userinfo and non-standard ports | app/infrastructure/paypal.py:680-689 | Reject any cert URL containing userinfo or port != 443 | OPEN |
| H9 | P1 | resolve_needs_review MARK_FAILED allows LOOKUP_FAILED as provider failure | app/application/services.py:2210-2227 | LOOKUP_FAILED held as NEEDS_REVIEW, only terminal provider failure allows MARK_FAILED | OPEN |
| H10 | P1 | scripts/boot.py unconditionally seeds req_stepup_1001 without checking DEMO_SEED | scripts/boot.py:289-325 | Seeding occurs only when DEMO_SEED=true | OPEN |
| N1 | P0 | Password rotation split admin and app passwords; consumers may still use the old variable names | .env.example, scripts/init_db.sh, docker-compose.yml, .github/workflows/ci.yml, render.yaml, README | Every consumer uses the new names; CI service and smoke job use throwaway values; a fresh clone starts from the README; confirmed old password rejected | CLOSED |
| U1 | P0 | UI invents approvals when the queue is empty; UI, API and seed budgets disagreed ($100,000 / $25,000 / $10,000) | web ApprovalsScreen, scripts/boot.py | One dataset; test UI figures equal API figures; empty state shown; demo-mode Create sample request calls the real API | CLOSED |
| U2 | P1 | Rate limit keys on the socket IP, so behind Render everyone shares one bucket; demo-token limit raised for tests | app/api/middleware.py, routes.py | Trusted proxy setting; default 10 to 20 per minute per client; higher value only via test environment variable | CLOSED |
| U3 | P1 | CSP default-src self with Google Fonts and inline styles; Playwright never ran against the container | web/index.html, middleware | Fonts self-hosted; Playwright against the container URL passes with zero CSP violation events | CLOSED |
| U4 | P2 | Demo tamper and restore act on shared state | routes, ledger | Per-session copy, or a visible notice and a safe reset | OPEN |
| U5 | P2 | Obsolete AstraX names | web tests, examples | Renamed | CLOSED |
| L1 | P0 | The LLM backend may be a test double; classifier claims 100 percent on 12 samples | app/application/llm_client.py | Real provider adapter with env key, or a documented fallback; evidence of a real call; the 100 percent claim removed everywhere | OPEN |
| P1 | P0 | PayPal not shown working end to end in the running app | app/infrastructure/paypal.py, dependencies.py | Real sandbox order, buyer approval, capture, reconciled; webhook verified; evidence in docs/paypal-sandbox.md; UI shows true state | OPEN |
| C1 | P1 | CI status after the Trivy tag fix unknown | .github/workflows/ci.yml | Every job green on the final commit | OPEN |
| R2 | P1 | 24 Dependabot PRs | .github/dependabot.yml | All closed; monthly grouped config; majors ignored for fastapi, sqlalchemy, pydantic, vite, vitest, eslint, mypy, pytest, @types/node | OPEN |
| R3 | P1 | Repo reads as machine-made | root, docs, commits | Root tidy; reports under docs/evidence; no status banners; README under 150 lines; banned words absent | OPEN |
| D1 | P0 | No hosted demo | render.yaml | Hosted scenes pass from a cold start; persistence works; reset_demo run | OPEN |
| K1 | P2 | k6 numbers contradict Little's law | docs/evidence | Raw JSON saved; one consistent set | OPEN |
| X1 | P1 | UX only tested by agents | - | Three people did the 5-second test and tasks; fixes made | OPEN (YOU) |
| G2 | P0 | RECONCILE had no resolver | reconciler | Reconciler resolves to SETTLED, FAILED, or NEEDS_REVIEW; H1-H7 closed | CLOSED |
| G3 | P0 | Database password | - | Rotated and verified per user report; old password rejection confirmed under N1 | CLOSED |
