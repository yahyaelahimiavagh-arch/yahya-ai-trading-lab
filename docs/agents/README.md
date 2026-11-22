# YATL — Agent Quality System (documentation-only pilot)

Created 2026-11-22 from main at 026489f5ae1790d6661ab302c77aa8308422e34b.
Purpose: graft focused review roles onto existing YATL evidence gates WITHOUT creating a second source of policy, a trading system, an always-on multi-agent service, or paid infrastructure.

## Scope and status
- This is an instruction/runbook pilot, not proof that agents have executed independent audits or that tests have passed.
- No runtime code, data, manifests, CI workflows, VPS settings or trading permissions are modified in this branch.
- Read-only baseline: BASELINE-AUDIT-2026-11-22.md.
- Worked dry-run scope: PILOT-PR186-READONLY.md.
- Upstream inspiration: https://github.com/msitarzewski/agency-agents (not a source of authority over YATL).

## Roles (use only when material)
1. product-manager-yatl.md — question value/cost/scope before expanding research infrastructure.
2. data-engineer-yatl.md — provenance, gaps, point-in-time and frozen dataset identities.
3. quant-research-auditor.md — backtest and research integrity, multiple-testing and economic inference.
4. security-auditor-yatl.md — capability/secret isolation, fail-closed and forward/live locks.
5. reality-checker-yatl.md — independent final skeptical evidence audit.

Reviewers must receive exact commit/diff and independently accessible evidence. A request for a review is not permission to run production code or examine sealed data. For small documentation-only changes use proportional checks rather than five duplicated reviews.

## Pilot workflow for a proposed PR
1. Director chooses a bounded task and exact base/head commits. No silent broadening.
2. Contributor submits narrowly scoped change, test plan, evidence and known limitations.
3. Data/Quant reviewers challenge time semantics, preserved boundaries, cost assumptions and no-leakage claims, when relevant.
4. Security checks all new capabilities and frozen boundaries. Reject unsafe paths.
5. Reality Checker compares source/diff, relevant test code, CI and artifact identities. In an isolated context when feasible, reproduce *only* tests with permitted public/synthetic inputs. Missing environment -> INS UFFICIENT_EVIDENCE, not PASS.
6. Record one audit using audit-report-template.md. Publish an engineering disposition independent of any research/economic disposition.
7. Only an explicit Director decision can authorize merge or the next gated stage. Even a clean PR is not approval to run 6,852 candidates, P10/P11 or trade.

## Locally runnable test commands (only where dependencies and scope permit)
- `uv sync --locked` (may need network/cached packages; ask before installing new tools)
- `uv run --locked python -m unittest discover -s tests -v`
- `uv run --locked python -m unittest discover -s tests -p 'test_mcf_production_features.py' -v`
- `uv run --locked python -m unittest discover -s tests -p 'test_mcf_safety.py' -v`
- `uv run --locked python -m unittest discover -s tests -p 'test_validation_gate.py' -v`
Never infer CI success merely from the presence of a workflow. Record exact run URL and tested commit; a blank commit-status response is not a completed test run.

## Adoption milestones
A. Review this documentation and the read-only PR #186 pilot.
B. If approved, use the template in one new read-only/engineering PR review; measure whether it finds useful defects with a reasonable review cost.
C. Only if useful, evaluate an opt-in CI check or more agent roles via a separately scoped change. No automatic merges, deployment or paid services.

## Status vocabulary
Engineering: PASS / FAIL / BLOCKED / INSUFFICIENT_EVIDENCE.
Economic/research: NOT_EVALUATED / INSUFFICIENT_EVIDENCE / REJECTED / protocol-defined accepted only with authorized canonical evidence.
Deployment/P11: LOCKED unless explicit authorized independent gate, never inferred from the two statuses above.
