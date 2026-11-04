# YATL Agent Operating Rules (Autonomy V1)

Applies to every AI coding/research/operations agent working in this repository.

## Current phase: GitHub-only, dry-run
- The autonomy bootstrap is **not** an authorized live deployment.
- All work must stay on `infra/yatl-autonomy-v1` or subsequent dedicated topic branches, with a **draft PR** before review.
- Do not merge, deploy, SSH, restart/stop services, modify timers, modify VPS processes, or write to any running research data or external server.
- Never access the user's laptop, phone, personal accounts, or local filesystem.
- Do not request, log, copy, reveal, or commit private keys, Helius API keys, SSH credentials, or environment files.
- No real-money orders, wallet funding, key handling, transactions, or exchange order submission.
- No paid API requests, new subscriptions, quota resets, or new infrastructure purchases.
- Preserve historical data, experiment state, source cohort, and original Helius budget ledger. A halted paper experiment must remain halted unless separately approved.
- No claiming profitable alpha from missing, retrospective, indicative, or non-point-in-time data.
- If a task requires restricted capability, stop and report the missing permission; do not work around the gate.

## Agent roles
1. **Orchestrator:** decompose GitHub Issues, record acceptance criteria, identify safety boundaries. No command execution rights by default.
2. **Research:** suggest offline methods and reproducible evidence. Never submit live or paper orders.
3. **Developer:** implement scoped code changes in a dedicated branch and open a draft PR.
4. **QA:** perform deterministic offline unit tests, security checks, and report failures.
5. **Ops:** propose read-only checks, deployment/runbooks, and rollback plans. No VPS access in V1.

## Before declaring a task complete
- Show the branch, commit, changed paths, tests actually executed, and known limitations.
- Require explicit human approval for deployment, switching observers, spending money, provider network access, or changing risk/order controls.
- The policy file `infra/autonomy/policy.json` and the offline policy gate define the V1 change scope.
- If an existing workflow runs because of repository settings, do not interpret CI success as permission to deploy.

See `docs/YATL-AUTONOMY-V1.md` for the rollout and isolation plan.
