"""Before-outcome Cartesian expansion; immutable batch JSONL."""
from __future__ import annotations
import hashlib
import itertools
from datetime import datetime, timezone
from pathlib import Path
from .models import MCFError, canonical, digest, guard_root, write_once
from .manifest import validate, domain_values
from .shards import layout

VERSION = "MCF_GENERATOR/1.0.0"
OPS = {"LT": lambda a,b:a<b, "LE":lambda a,b:a<=b,"GT":lambda a,b:a>b,"GE":lambda a,b:a>=b,"EQ":lambda a,b:a==b,"NE":lambda a,b:a!=b}

def generate(manifests: list[dict], *, batch_id: str, evidence_partition: str="DEVELOPMENT", shard_size: int=1000):
    if not manifests or evidence_partition != "DEVELOPMENT" or not batch_id or any(x in batch_id.lower() for x in ("p10", "oos", "reserve")):
        raise MCFError("unbound batch/evidence")
    hashes = [validate(m) for m in manifests]
    if len(set(hashes)) != len(hashes):
        raise MCFError("duplicate family manifest")
    years = {int(m["generation_budget"]["batch_generation_id"][:4]) for m in manifests}
    generations = {int(m["generation_budget"]["batch_generation_id"][5:7]) for m in manifests}
    if len(years) != 1 or len(generations) != 1 or not 2000 <= next(iter(years)) <= 2100 or not 0 <= next(iter(generations)) <= 99:
        raise MCFError("batch generation ID must start YYYY-GG")
    prefix = f"MCF-{next(iter(years)):04d}-{next(iter(generations)):02d}"
    cost, evidence, universe = [[m[key] if key != "universe_policy_ref" else m["market_scope"][key] for m in manifests] for key in ("cost_policy_ref", "evidence_policy_ref", "universe_policy_ref")]
    if any(len(set(x)) != 1 for x in (cost,evidence,universe)):
        raise MCFError("mixed batch policies")
    candidates, invalid = [], []
    seen = set()
    for m, sha in zip(manifests, hashes):
        valid_count = 0
        ds = m["parameter_domains"]
        for tup in itertools.product(*(domain_values(d) for d in ds)):
            ordinal = len(candidates) + len(invalid)
            if ordinal > 999999:
                raise MCFError("candidate ID ordinal exhausted")
            vector = dict(zip((d["name"] for d in ds),tup))
            identity = {"generator_version":VERSION,"family_manifest_sha256":sha,"parameter_vector":vector,"market_assignment":m["market_scope"],"source_lineage":m["source_refs"],"cost_policy_ref":m["cost_policy_ref"],"evidence_partition":evidence_partition}
            spec_sha = digest(identity)
            row = {"ordinal":ordinal,"candidate_id":f"{prefix}-{ordinal:06d}","candidate_spec_sha256":spec_sha,"family_manifest_sha256":sha,"parameter_vector":vector,"batch_id":batch_id}
            reasons = []
            for c in m["structural_constraints"]:
                right = vector[c["right"]] if c["right"] in vector else c["right"]
                if not OPS[c["operator"]](vector[c["left"]], right):
                    reasons.append("STRUCTURAL_CONSTRAINT")
            if spec_sha in seen:
                reasons.append("DUPLICATE_SPEC")
            seen.add(spec_sha)
            if reasons:
                invalid.append({**row,"state":"STRUCTURALLY_INVALID","failure_reasons":sorted(set(reasons))})
            else:
                candidates.append(row); valid_count += 1
        if valid_count > m["generation_budget"]["maximum_valid_economic_trials"]:
            raise MCFError("valid economic trial budget exceeded")
    raw = sorted(candidates + invalid,key=lambda x:x["ordinal"])
    shards = layout(batch_id,len(raw),shard_size)
    ledger_sha = hashlib.sha256(b"".join(canonical(r) for r in raw)).hexdigest()
    batch = {"batch_id":batch_id,"generator_version":VERSION,"family_manifest_sha256":hashes,"evidence_policy_ref":evidence[0],"universe_policy_ref":universe[0],"cost_policy_ref":cost[0],"evidence_partition":evidence_partition,"raw_candidate_count":len(raw),"structural_valid_count":len(candidates),"structural_invalid_count":len(invalid),"shard_layout":shards,"candidate_ledger_sha256":ledger_sha,"safety":{"p10_read":False,"p10_write":False,"fresh_oos_read":False,"recent_reserve_read":False,"live_master_lock":"OFF"},"state":"ENGINEERING_ONLY_NO_SELECTION"}
    return batch, candidates, invalid

def write_batch(root: Path, batch: dict, candidates: list[dict], invalid: list[dict]):
    guard_root(root)
    # Artifacts are final and content addressed; reruns may only repeat identical bytes.
    raw = sorted(candidates+invalid,key=lambda x:x["ordinal"])
    output = {}
    for name, rows in (("candidates", candidates),("structural-invalid",invalid)):
        payload = b"".join(canonical(r) for r in rows)
        sha = hashlib.sha256(payload).hexdigest()
        root.mkdir(parents=True,exist_ok=True)
        target = root / f"{batch['batch_id']}-{name}-{sha}.jsonl"
        write_once(target,payload)
        output[name] = str(target)
    p = canonical(batch); target = root / f"{batch['batch_id']}-manifest-{hashlib.sha256(p).hexdigest()}.json"
    write_once(target,p)
    output["batch_manifest"] = str(target)
    return output
