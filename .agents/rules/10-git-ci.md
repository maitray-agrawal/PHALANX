# Git and CI Operating Invariants

Always work and commit directly on `main`. Never create feature/fix branches. Never checkout new branches. All work, incremental commits, tests, and pushes must target `origin main` only. Before starting any task, run `git pull origin main`. Commit early and often directly on `main` once tests pass using clean conventional commit messages.
