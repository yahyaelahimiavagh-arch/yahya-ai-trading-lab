"""MCF CLI: validation and frozen candidate generation only."""
import argparse
import json
from pathlib import Path
from .manifest import load
from .generator import generate, write_batch

def main(argv=None):
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    v=sub.add_parser("validate-manifest"); v.add_argument("manifest");v.add_argument("--root",required=True)
    g=sub.add_parser("generate");g.add_argument("manifests",nargs="+");g.add_argument("--root",required=True);g.add_argument("--output",required=True);g.add_argument("--batch-id",required=True);g.add_argument("--shard-size",type=int,default=1000)
    a=p.parse_args(argv)
    if a.command=="validate-manifest":
        _,sha=load(Path(a.manifest),Path(a.root));print(json.dumps({"manifest_sha256":sha},sort_keys=True));return
    records=[load(Path(x),Path(a.root))[0] for x in a.manifests]
    batch,rows,bad=generate(records,batch_id=a.batch_id,shard_size=a.shard_size)
    print(json.dumps(write_batch(Path(a.output),batch,rows,bad),sort_keys=True))
if __name__=="__main__": main()
