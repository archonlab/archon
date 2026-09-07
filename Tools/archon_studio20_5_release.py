#!/usr/bin/env python3
"""Build deterministic STUDIO20.5 full and WORLD1 delta archives."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
LIST=Path("Release/STUDIO20.5/packaging_whitelist.txt")
def rows(p): return [x.strip() for x in p.read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def archive(root, paths, output):
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
        for rel in sorted(paths):
            info=zipfile.ZipInfo(rel,date_time=(1980,1,1,0,0,0)); info.create_system=3
            info.external_attr=(0o100755 if rel.endswith((".sh",".command")) else 0o100644)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            zf.writestr(info,(root/rel).read_bytes(),compresslevel=9)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,default=ROOT); ap.add_argument("--baseline",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    root=a.root.resolve(); baseline=a.baseline.resolve(); output=a.output.resolve(); paths=rows(root/LIST)
    old_list=baseline/"Release/STUDIO20.4/packaging_whitelist.txt"; old_paths=set(rows(old_list)) if old_list.is_file() else set()
    delta=[]
    for rel in paths:
        old=baseline/rel
        if rel not in old_paths or not old.is_file() or sha(root/rel)!=sha(old): delta.append(rel)
    output.mkdir(parents=True,exist_ok=False)
    full=output/"ARCHON_STUDIO20.5_RELEASE.zip"; patch=output/"ARCHON_STUDIO20.5_WORLD1_DELTA.zip"
    archive(root,paths,full); archive(root,delta,patch)
    receipt={"schema":"archon_studio20_5_artifacts_v1","release_files":len(paths),"delta_files":len(delta),"artifacts":{full.name:sha(full),patch.name:sha(patch)}}
    (output/"ARTIFACTS.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n"); print(json.dumps(receipt,indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
