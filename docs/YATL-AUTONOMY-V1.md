# YATL Autonomous Lab — V1 (online-only, isolated by design)

**Status: PREPARATION ONLY.** This branch adds a GitHub-side policy, an offline CI gate, and an Issue template. It does **not** start an AI agent, install software on a VPS, contact Helius or a trading provider, configure GitHub secrets, publish to Hostinger, or change running YATL processes.

## Existing infrastructure and requirements
- Use the existing YATL Ubuntu VPS only in a **future, separately approved** phase.
- GitHub is the source of truth for code, issues, pull requests, and offline CI.
- Existing Hostinger hosting can later display a **read-only, sanitized** status dashboard.
- No access to laptop or phone at any phase. The browser-based VPS console is only a manual bootstrap option, not a continuing dependency.
- Existing P10 services, Smart Money V2, the halted six-wallet paper pilot, its Helius counter, and all research archives remain untouched.

## Target architecture (NOT yet installed)

```text
GitHub Issues / schedule
          |
          v
Orchestrator (separate, restricted YATL agent account/container on VPS)
    |---- Research agent (offline, evidence)
    |---- Developer agent (sandboxed working tree, branch + draft PR)
    |---- QA agent (offline test runner and static audit)
    '-- Ops agent (read-only telemetry and rollback proposals)
          |
          v
GitHub Branch -> Draft PR -> offline CI -> HUMAN APPROVAL GATE
          |
          v
Separate staging checkout (no live mounts or secrets)
          |
          v
Explicitly approved, scoped VPS pull/deploy service
          |
          v
Sanitized read-only status export -> Hostinger
```

Each role is a **logical permission profile**, not evidence that autonomous models already run. External LLM inference requires an explicit provider/authentication and consumption budget.

## V1 deliverables already in this PR
1. `AGENTS.md`: instruction boundary for code-generation agents.
2. `infra/autonomy/policy.json`: fixed fail-closed V1 capabilities and allowed paths.
3. `infra/autonomy/policy_gate.py`: stdlib-only policy/path validation, no network or subprocess.
4. `tests/test_yatl_autonomy_policy.py`: deterministic offline checks.
5. `.github/workflows/yatl-autonomy-safety.yml`: GitHub-hosted CI only, `contents: read`, no secrets, no SSH, no deployment.
6. `.github/ISSUE_TEMPLATE/yatl-autonomy-task.yml`: bounded task intake (available in GitHub's issue picker only once present on its default branch).

All of these are **preparatory controls**. A JSON policy cannot isolate a process at the OS level, and a CI gate alone does not enforce a deploy approval. Branch protection / required review should be configured before enabling autonomous code changes.

## Proposed VPS isolation in V2 — NOT AUTHORIZED BY THIS PR
- Inventory existing `systemd`, `tmux`, listeners, users, disk and memory **read-only**; validate capacity before installation.
- Use a dedicated unprivileged user and a container (or rootless container engine) with read-only root filesystem, no host Docker socket, no host PID namespace, no sudo, no root, and no mounts of production home, env, wallet, Helius ledger or YATL archives.
- Dedicated working directory such as `/srv/yatl-agents`; no writes to live YATL checkouts or service definitions.
- Default-deny outbound egress except minimal audited endpoints for GitHub and chosen LLM provider. No provider API requests from Research/QA by default.
- Resource ceilings: CPU, RAM, disk, processes, job concurrency, network request and monetary quotas. One task at a time initially; zero recurring paid inference before budget approval.
- Keep deployment as a distinct pull-based service with an allowlisted release SHA, staged validation, explicit approval, snapshot/rollback, and credentials inaccessible to code-writing agents.
- Agents cannot restart existing collectors, reset Helius counters, bypass history-gap halts, or submit orders.
- Use branch-bound GitHub App or narrowly scoped repository identity; never give broad GitHub account PAT or SSH root credentials to agents.
- If the VPS cannot isolate agent workloads safely, use GitHub-hosted CI for code/tests; do not co-locate an unrestricted runner with live research.

## Phases & operational acceptance
| Phase | Deliverable | May change VPS? |
| --- | --- | --- |
| V1 (this branch) | Written policy, draft PR, offline tests | **No** |
| V2 (separate authorization) | Read-only VPS inventory, sandbox user/container, quotas | Only approved new sandbox resources |
| V3 (separate authorization) | Issue queue, bounded agent execution, draft PR automation | Sandbox only |
| V4 (separate authorization) | Staging pull of approved commit, immutable logs, rollback | Approved staging only |
| V5 (separate authorization) | Human-gated, narrow production deployment + sanitized Hostinger reporting | Yes, with explicit release approval |

## Failure and spending rules
- Always preserve a paper-only workflow. Do not infer profitable copy-trading from unverified history or indicative quotes.
- Treat `UNVERIFIABLE_TRANSACTION_HISTORY_GAP` as a research blocker, not an excuse to turn off safety checks.
- No purchases, upgrades, new paid API calls, Helius quota resets, or live trading without a separately approved change.
- "CI green" means only that these narrow code checks passed. It does not imply the VPS is safe, that an agent ran, or that trading alpha exists.

## Verification
From repository root, using Python 3.12:
```bash
python3 infra/autonomy/policy_gate.py --policy infra/autonomy/policy.json
python3 -m unittest discover -s tests -p 'test_yatl_autonomy_policy.py' -v
```
The CI workflow also checks changed paths against the audited V1 allowlist.
