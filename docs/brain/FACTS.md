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
| F9 | F1b and F2 results not seen; hosted demo none; LLM backend unknown | - | UNKNOWN |
