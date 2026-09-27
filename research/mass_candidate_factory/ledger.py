"""Append-only result rows and strict batch closeout."""
from __future__ import annotations
import collections
import hashlib
import json
from pathlib import Path
from .models import MCFError, canonical, digest, guard_root

FINAL_STATES={"STRUCTURALLY_INVALID","DEVELOPMENT_FAIL","DEVELOPMENT_INTERESTING_NOT_QUALIFIED","DEVELOPMENT_GATE_PASS","DUPLICATE_OR_REDUNDANT","EXACT_RECOMPUTE_FAIL"}
SAFETY={"p10_read":False,"p10_write":False,"fresh_oos_read":False,"recent_reserve_read":False,"live_master_lock":"OFF"}
REQUIRED={"ordinal","candidate_id","candidate_spec_sha256","batch_id","shard_id","screening_engine_version","dataset_id","evidence_partition","result_state","failure_reasons","opportunity_metrics","base_economics","stress_economics","temporal_metrics","exact_recompute_state","safety","result_record_sha256"}

def make_result(candidate:dict,batch:dict,shard:dict,*,dataset_id:str,state:str, failure_reasons:list[str], metrics:dict|None=None):
    if state not in FINAL_STATES or not dataset_id or batch["evidence_partition"]!="DEVELOPMENT":
        raise MCFError("invalid final result/evidence")
    m=metrics or {}
    if m and m.get("dataset_id") != dataset_id:
        raise MCFError("screening evidence identity mismatch")
    row={"ordinal":candidate["ordinal"],"candidate_id":candidate["candidate_id"],"candidate_spec_sha256":candidate["candidate_spec_sha256"],"batch_id":batch["batch_id"],"shard_id":shard["shard_id"],"screening_engine_version":m.get("screening_engine_version","MCF_STRUCTURAL/1"),"dataset_id":dataset_id,"evidence_partition":"DEVELOPMENT","result_state":state,"failure_reasons":sorted(failure_reasons),"opportunity_metrics":m.get("opportunity_metrics",{}),"base_economics":m.get("base_economics",{}),"stress_economics":m.get("stress_economics",{}),"temporal_metrics":m.get("temporal_metrics",{}),"exact_recompute_state":m.get("exact_recompute_state","NOT_REQUIRED"),"safety":dict(SAFETY)}
    return {**row,"result_record_sha256":digest(row)}

def reconcile(batch:dict,registered:list[dict],artifacts:list[tuple[dict,Path,str]],*,dataset_id:str):
    """A partial/unknown/duplicate ledger is BATCH_INVALID, never canonical."""
    try:
        if batch["safety"] != SAFETY or batch["evidence_partition"]!="DEVELOPMENT" or len(registered)!=batch["raw_candidate_count"] or len(artifacts)!=len(batch["shard_layout"]):
            raise MCFError("batch metadata mismatch")
        if hashlib.sha256(b"".join(canonical(r) for r in registered)).hexdigest()!=batch["candidate_ledger_sha256"]:
            raise MCFError("registered ledger mismatch")
        expected={r["candidate_id"]:r for r in registered};found={}
        if len(expected)!=len(registered): raise MCFError("duplicate registration")
        if sum(r.get("state")=="STRUCTURALLY_INVALID" for r in registered)!=batch["structural_invalid_count"]:
            raise MCFError("structural count")
        if len(registered)-batch["structural_invalid_count"]!=batch["structural_valid_count"]:
            raise MCFError("valid count")
        shard_ids=set()
        for sh,path,sha in artifacts:
            guard_root(path.parent)
            if sh not in batch["shard_layout"] or sh["shard_id"] in shard_ids or path.is_symlink() or not path.name==f"{sh['shard_id']}-{sha}.jsonl":
                raise MCFError("unknown/duplicate shard")
            shard_ids.add(sh["shard_id"])
            payload=path.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=sha: raise MCFError("shard digest")
            rows=[json.loads(line) for line in payload.splitlines()]
            if len(rows)!=sh["end"]-sh["start"] or [r["ordinal"] for r in rows]!=list(range(sh["start"],sh["end"])):
                raise MCFError("incomplete shard")
            if payload != b"".join(canonical(r) for r in rows):raise MCFError("noncanonical rows")
            for row in rows:
                cid=row["candidate_id"]
                if cid in found or cid not in expected or set(row)!=REQUIRED or row["result_state"] not in FINAL_STATES or row["result_record_sha256"]!=digest({k:v for k,v in row.items() if k!="result_record_sha256"}) or row["candidate_spec_sha256"]!=expected[cid]["candidate_spec_sha256"] or row["batch_id"]!=batch["batch_id"] or row["shard_id"]!=sh["shard_id"] or row["dataset_id"]!=dataset_id or row["evidence_partition"]!="DEVELOPMENT" or row["safety"]!=SAFETY:
                    raise MCFError("invalid/unknown/duplicate candidate result")
                if expected[cid].get("state")=="STRUCTURALLY_INVALID" and row["result_state"]!="STRUCTURALLY_INVALID":
                    raise MCFError("structural failure was dropped")
                found[cid]=row
        if set(found)!=set(expected):raise MCFError("missing result")
        return {"status":"BATCH_COMPLETE","result_count":len(found),"failure_counts":dict(collections.Counter(reason for row in found.values() for reason in row["failure_reasons"])),"ledger_sha256":digest([found[k] for k in sorted(found)])}
    except (MCFError,OSError,KeyError,ValueError,TypeError,json.JSONDecodeError) as e:
        return {"status":"BATCH_INVALID","reason":str(e)}
