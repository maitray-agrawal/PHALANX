# context.md
Phase: P0   Branch: main   Last green CI: none
Architecture now: Foundation skeleton - app/{domain,application,infrastructure,api,mcp}, web/, tests/{unit,integration,concurrency,redteam}
Completed:
- Bootstrap repository structure, configuration, and documentation
- FastAPI with /healthz and /readyz endpoints
- Pure domain purity test
- Multi-stage Dockerfile and docker-compose.yml with postgres 16
- CI workflow and dependabot
- Repository cleanup and duplicate elimination
Current task: Repository structure cleanup (main)
Changed files: .agent/ (deleted duplicate), redundant .gitkeep removed, docs/ updated
Test status: pytest -q passed (28 tests), ruff passed, mypy passed, web build & tests passed
Deployment status: none
Known issues / unresolved risks: PayPal sandbox credentials to be wired in P2; Render deployment in P10
Decisions made this session: D-001 through D-010
Next recommended action: Proceed to P1 (Product quality review and core documentation)
