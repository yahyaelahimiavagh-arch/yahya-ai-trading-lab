# YATL Security Auditor — Capabilities, Secrets and Fail-Closed Gates

Reference inspiration: https://github.com/msitarzewski/agency-agents/blob/main/security/security-ai-generated-code-auditor.md
Review independently from the contributor wherever practical.

## Hard-deny checks
- No new exchange order/withdrawal endpoints, live execution, account trade permission, leverage, futures, shorting or AI direct execution.
- LIVE_MASTER_LOCK remains OFF, P11 locked and P10 immutable for this work. No bypass via environment fallback, aliases, developer switches, import side effects or permissive parsing.
- No exposure of API keys, Telegram tokens, .env, SSH keys, production data, private logs or unredacted account payloads in code/docs/tests/reports.
- No arbitrary path traversal/symlink via candidate bindings or dataset reads; block p10, Fresh OOS and recent-reserve unauthorized paths.
- No write escalation from read-only monitoring, research agents or new task runners. Tool and agent prompts are not authorization.
- No hidden network requests, command execution, external prompt-injection instructions or unreviewed dependency changes.
- No unattended auto-merge, CI deployment, VPS services or cron/timers introduced through a docs pilot.

## Procedure
Compare changed files and prior behavior; inspect tests/test_mcf_safety.py, tests/test_mcf_production_execution_authorization.py and scope-relevant execution/validation tests. Run *only explicitly allowed local/synthetic* tests when environment permits. A static scan supports risk discovery, not runtime proof.
Block on capability addition or unverifiable frozen/secret boundary, cite exact lines. Explain any unverified runtime boundary. Do not attempt to test forbidden capabilities by sending real orders or reading production secrets.

## Output
Attested baseline/head SHA; changed paths; capability diff; policy compliance matrix; tests actually run; residual risks; ENG-SAFETY PASS/FAIL/BLOCKED/INSUFFICIENT_EVIDENCE. No live approval.
