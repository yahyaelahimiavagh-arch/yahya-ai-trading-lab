# YATL Independent Audit Report — Template

## Header
- Audit type (ENG / DATA / QUANT / SECURITY / INDEPENDENT):
- Reviewer identity/context (independent from patch author? how):
- UTC audit date:
- Repository; base SHA; candidate HEAD SHA; PR:
- Scope / explicit exclusions:
- Relevant authoritative contracts:
- Environment / data partition used (SYNTHETIC / DEVELOPMENT / NONE):

## Evidence table
| Claim | Author-reported source | Directly inspected evidence (path + SHA/run ID) | Independently reproduced? | Result | Gap |
|---|---|---|---|---|---|
| ... | ... | ... | YES/NO/NOT_RUN | PASS/FAIL/UNKNOWN | ... |

## Boundary assertions
| Boundary | Review evidence | Disposition |
|---|---|---|
| LIVE_MASTER_LOCK=OFF, PAPER ONLY | ... | ... |
| P10 unchanged and P11 locked | ... | ... |
| No order/withdrawal/futures/leverage/short/AI direct execution | ... | ... |
| No sealed Fresh OOS/recent reserve access | ... | ... |
| Freeze/provenance hashes correct | ... | ... |
| No hidden trials or outcome-based rescue | ... | ... |
| No secrets, undeclared network or deployment | ... | ... |

## Tests actually executed
- Command:
- Exact SHA:
- Date and environment:
- Data identity and partition:
- Number passed/failed/skipped:
- Output/run URL:
- NOT_RUN and reason:

## Findings (ordered by severity)
1. Finding — proof / uncertainty / consequence / recommended narrowly scoped action.
2. ...

## Decisions — never conflate
- ENGINEERING: PASS / FAIL / BLOCKED / INSUFFICIENT_EVIDENCE
- RESEARCH / ECONOMIC: NOT_EVALUATED / INSUFFICIENT_EVIDENCE / REJECTED / accepted under explicitly cited protocol
- P10 FORWARD: UNCHANGED / NOT_VERIFIED / separate canonical status with exact evidence
- P11 / LIVE: LOCKED
- Merge authorization: NOT_GRANTED by this report
- Allowed next action:
- Human/Director approval still required:

## Integrity note
An agent opinion is not an independent CI run. Missing evidence stays missing. Historical documentation is not proof of current service health. No invented test, benchmark, economic or live-trading claims.
