# FACTS (label every line; promote REPORTED to VERIFIED only with command output)
| ID | Fact | Source | Label |
| F1 | Hackathon: submissions close 12 Nov 12:00 pm Pacific; judging 1 to 15 Dec; stage one pass or fail on theme and PayPal use; stage two five equal criteria (technology, design, impact, innovation, presentation); judges may use text and video only; license must be visible; video under 3 minutes on YouTube; demo free until 15 Dec; 31,553 registered | Official rules page, fetched 6 Nov | VERIFIED |
| F2 | Database password rotated; admin and application passwords differ; SCRAM verified; init script needs a separate app password; .env untracked; containers healthy | User report, 7 Nov | REPORTED |
| F3 | PostgreSQL concurrency tests: 8 passed including two processes; mandates stored with fixed dates; persistence through restart and down/up; 4xx releases, 5xx and timeouts hold | F1 report | REPORTED |
| F4 | Reconciler, NEEDS_REVIEW state, credential check before reservation, 9 reconciliation tests, full suite 357 passed with 0 skipped, 105 red-team, ruff, mypy clean | F1c report (uncommitted) | REPORTED |
| F5 | Compose run used placeholder PayPal credentials; load tests used a stub server | Reports | REPORTED |
| F6 | PayPal sandbox: Orders create returned 201, retrieve 200; Payouts restricted; capture not shown | A review document | REPORTED |
| F7 | The old password exists in an old commit (c322100) and gitleaks did not flag it | F1 report | REPORTED |
| F8 | 24 Dependabot PRs open; main commits use the feat(scope) style; Trivy action tag fixed in d41cff0 | Screenshots, V3 report | REPORTED |
| F9 | F1b and F2 results verified: test_fail_closed (2/2 pass), test_keys (3/3 pass), test_demo_dataset_alignment (1/1 pass), test_proxy_rate_limiting (4/4 pass), test_migration_upgrade (1/1 pass), test_reconciliation (11/11 pass), test_negative_controls (7/7 pass), Playwright against container URL (0 CSP violations) | Command output in LOG | VERIFIED |
| F10 | T3/T4 password alignment verified; old passwords rejected live; positive webhook signature verified; deterministic smoke & walkthrough tests verified across all 6 browsers/viewports | Command output in LOG | VERIFIED |
| F11 | H8, H9, H10 verified: cert URL rejects userinfo/ports; resolve_needs_review refuses on lookup errors; scripts/boot.py seeds only on DEMO_SEED=true; admin reset disabled in production; distinct font weights installed; full pytest suite 387 passed; redteam 105 passed; smoke 30 passed | Command output in LOG | VERIFIED |
