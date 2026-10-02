# MCF candidate-specific forward evidence binding v1.0

Work unit: MCF-FORWARD-BINDING-IMPLEMENTATION-001.
Verified base main: `37ed99d4c636646909cb23cf59b0f9ad554fedb0`.
Scope: deterministic metadata contract and fail-closed adjudication prerequisite.
PAPER / RESEARCH ONLY. No performance evaluation or forward collection is added.

## Existing lineage, inspected before implementation

| Stage | Existing source and authoritative identity |
|---|---|
| Candidate | `production.py`: `FrozenCandidateBinding`, candidate ID/spec SHA membership in `PreOutcomeFreeze` |
| Development evidence | `production.py`: `ProductionUniverseBinding`; `production_runner_input.py`: `freeze_input`, evidence binding and cost SHA |
| Runner | `production_runner_input.py`: `FrozenRunnerInput`, `runner_input_sha256`, runtime code SHA map, executable/candidate ledger/neighbor/evidence identities |
| Development survivor | `adjudication.py`: `freeze_survivor`, spec/universe/evidence/cost/statistical hashes and `freeze_sha256` |
| Existing baseline forward system | `yatl/validation/registration.py`: fixed `CandidateFreeze`; `yatl/validation/gate.py`: window/candidate/registry/run/economics/snapshot hashes |
| MCF adjudication | `adjudication_runner.py`: Development representatives pending Director reality review; no generic MCF forward producer or forward promotion path existed |

Only baseline source contracts were inspected. No P10 runtime artifacts, Fresh
OOS, P11 or reserved evidence were read. Development acceptance remains intact:
a Development freeze does not claim forward validation.

## Identity contract and trust boundary

`forward_binding.ForwardIdentity` is an immutable metadata value. All identifiers
are required; SHA values must be lowercase 64-digit hexadecimal values.

| Field | Authoritative source / meaning |
|---|---|
| `candidate_id`, `candidate_spec_sha256` | Exact registered candidate and canonical specification |
| `freeze_sha256` | Exact accepted Development survivor freeze; transitively pins its universe, evidence, cost and statistical artifact |
| `evidence_binding_sha256` | Existing evaluated Development dataset/evidence binding |
| `runner_input_sha256` | Existing frozen evaluated runner input; incompatible inputs invalidate the claim |
| `runtime_code_sha256` | Complete applicable evaluated code path-to-SHA map; expected context must include forward producer/runner and adjudication contract code as applicable |
| `forward_registration_sha256` | Sealed candidate-specific forward registration, established before observations; binds the above candidate/freeze/input/code and the window/registry. A new registration invalidates old claims |
| `window_sha256` | Exact current forward observation window |
| `ingestion_snapshot_sha256` | Exact evaluated forward dataset snapshot; distinct from the Development evidence identity |
| `gate_registry_sha256` | Exact applicable forward policy/criteria registry |
| `forward_report_sha256` | Exact authoritative evaluated forward report, including its run/economics identities and disposition |

These reuse existing identity concepts. Forward registration is the necessary
new candidate-specific registration reference: it is not a second candidate ID.
The existing fixed baseline freeze cannot serve as such a registration for an
MCF candidate. No existing baseline report is migrated or relabeled.

The caller must independently resolve the current expected identity from trusted
candidate/spec/freeze/runner/forward registration and verified report artifacts.
Verify their existing internal hashes and cross-links before constructing this
value. In particular, the forward registration and report must actually name
this candidate/spec/runner and evidence; attaching arbitrary labels to a report
from a different strategy is prohibited. Never construct expected identity by
copying the submitted binding, nor accept a caller-controlled expected context.

The binding is an integrity/provenance prerequisite, not a signature or a
performance attestation. Hash-only metadata cannot establish the truth of a
fabricated report. This implementation adds no MCF forward producer, source
resolver, registration writer, performance evaluator or collection permission.
Any future authorized producer must fulfill the above contract and any future
consumer must use the mandatory prerequisite, then verify forward economic
gates and Director approval independently. No empirical forward coverage is
created for existing survivors by adding this module.

## Fail-closed adjudication

`bind_forward_evidence(identity)` seals producer metadata.
`assess_forward_binding(expected, artifact)` reports an explicit state:
`BOUND_MATCH`, `MISSING_BINDING`, `LEGACY_UNBOUND`, `UNSUPPORTED_SCHEMA`,
`INVALID_BINDING`, or `BINDING_MISMATCH` (with sorted mismatched field names).
`require_forward_binding` raises `MCFError` on every state except `BOUND_MATCH`.

`adjudication.adjudicate_forward_provenance` is the MCF forward provenance claim
entry point. It always invokes the requirement, returns a hashed provenance-only
decision and explicitly sets `promotion_authorized=False`, `live_authorized=False`.
An economic PASS alone, a missing field, another candidate/spec, a different
dataset/input/code, or a stale report/registration/window/registry cannot pass.
There is no baseline fallback. Staleness means inconsistency with independently
resolved current sealed lineage; there is no arbitrary time-to-live threshold.

## Schema, serialization and migration

Binding schema: `MCF_FORWARD_EVIDENCE_BINDING/1.0.0`.
Envelope has exactly `schema`, `identity`, `binding_sha256`.
Binding hash uses existing `models.digest` over schema and identity, excluding
the hash field: sorted-key UTF-8 compact JSON, finite values only, trailing newline.
Code paths must be canonical relative paths; duplicate/ambiguous code identities
are rejected. Identity stores sorted immutable tuples; serialization returns
detached dictionaries. No performance values or dataset paths are emitted.

Decision schema: `MCF_FORWARD_PROVENANCE_ADJUDICATION/1.0.0`; its SHA likewise
excludes its own hash field. It records candidate, binding and provenance state.

Existing Development, runner and baseline schemas are unchanged. Legacy forward
artifacts remain unbound or unsupported and cannot confer candidate-specific
credibility. Migration requires a separately authorized candidate-specific
registration/production process; no automated backfill or silent interpretation.
Unknown future schema versions fail closed pending an explicit migration policy.

## Safety and verification

No changes to safety settings, LIVE_MASTER_LOCK, order/AI endpoints, futures,
leverage, shorting, P11 locks, reserved evidence guards or P10 paths. This module
only processes supplied metadata in memory and adds no I/O or execution path.
Focused tests use synthetic hashes only, covering exact match, every identity
substitution, stale lineage, missing/unknown fields, unsupported/legacy schemas,
tampering, deterministic serialization and immutable provenance. Existing
Development regression tests must continue to pass without forward evidence.

Can candidate A forward evidence provide validation credibility to candidate B?
**No**, when resolved expected identity is B: the mandatory claim gate rejects
candidate A even if its envelope is intact or resealed.
