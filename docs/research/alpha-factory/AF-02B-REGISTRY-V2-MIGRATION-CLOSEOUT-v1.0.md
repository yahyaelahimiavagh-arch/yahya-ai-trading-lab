# AF-02B — Candidate Registry v2 Migration Closeout

Status: **MIGRATION COMPLETE / NO PERFORMANCE AUTHORIZATION**

Date: 2026-09-27

## Scope

The bounded 31-candidate Generation-2 intake registry was migrated into:

`docs/research/research-intake/CANDIDATE-REGISTRY-V2-v1.0.json`

Legacy registry remains unchanged and authoritative as the historical source
snapshot.

## Migration rules

- preserve every legacy candidate ID;
- preserve source identity/title/hypothesis;
- do not invent missing source or method details;
- map unknown v2 fields to `UNASSESSED` / null;
- separate source-method state from YATL adaptation state;
- preserve existing source/reproducibility blockers;
- attach canonical GEN2-001/002/003 evidence without rewriting it;
- attach the RIE-CAND-0028 source-method/adaptation split;
- no migration status grants Development/OOS/Forward/Live authority.

## Validation

- legacy candidates: 31
- v2 candidates: 31
- duplicate candidate IDs: 0
- missing legacy IDs: 0
- newly invented candidate IDs: 0
- any authorization=true: 0

Lifecycle distribution:

- BLOCKED_REPRODUCIBILITY: 1
- BLOCKED_SOURCE: 1
- INVALIDATED_BEFORE_ECONOMICS: 1
- METHOD_SPECIFIED: 2
- REJECTED_NEGATIVE_EVIDENCE: 2
- SOURCE_BOUND: 24

Source-method distribution:

- BLOCKED_REPRODUCIBILITY: 1
- BLOCKED_SOURCE: 1
- SOURCE_BOUND: 24
- SOURCE_METHOD_SPECIFIED: 5

## Canonical evidence linked

- RIE-CAND-0030 -> GEN2-001 canonical negative evidence
- RIE-CAND-0025 -> GEN2-002 invalidated-before-economics evidence
- RIE-CAND-0027 -> GEN2-003 canonical negative evidence / REDUNDANT_EDGE
- RIE-CAND-0028 -> source method specified, YATL adaptation still blocked

## Conservative migration decisions

Broad legacy candidates remain `SOURCE_BOUND` unless stronger repository
evidence exists.

No capacity, regime scope, independent-family, venue-generalization or alpha
attribution claim was invented during migration.

`economic_mechanism_id` remains `LEGACY_UNCLASSIFIED` for the bounded legacy
set until later taxonomy/classification work.

## Safety

Migration performed no market-performance run and grants no performance
authority.

- Fresh OOS read: false
- recent reserve read: false
- P10 read/write: false/false
- P11: locked
- Live: unauthorized

## Exit state

AF-02B bounded legacy migration is complete.

Registry v2 is now available for Mass Candidate Factory integration. Future MCF
candidate records should be created directly in v2 form rather than forced
through the legacy registry.
