#!/usr/bin/env python3
"""Materialize verified STUDIO20 full/delta archives with stable ZIP metadata."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
import zipfile
from archon_distribution_stage import read_whitelist, sha256
from archon_windows_distribution import stage


def archive(root, paths, output):
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for rel in sorted(paths):
            info=zipfile.ZipInfo(rel,date_time=(1980,1,1,0,0,0))
            info.create_system=3
            executable=rel.endswith(('.sh','.command'))
            info.external_attr=(0o100755 if executable else 0o100644)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,(root/rel).read_bytes(),compresslevel=9)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--baseline',type=Path,required=True,help='exact original STUDIO19 materialization')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve();baseline=a.baseline.resolve();output=a.output.resolve()
    if output.exists():raise RuntimeError('output must be new')
    baseline_list=read_whitelist(baseline/'Release/STUDIO19/packaging_whitelist.txt')
    baseline_manifest=json.loads((baseline/'Release/STUDIO19/studio_release_integration.json').read_text())
    expected={rel:sha256(baseline/rel) for rel in baseline_list if rel!='Release/STUDIO19/studio_release_integration.json'}
    if baseline_manifest['file_hashes']!=expected:raise RuntimeError('baseline hash closure mismatch')
    with tempfile.TemporaryDirectory(prefix='archon-release-check-') as raw:
        stage(root,Path(raw)/'payload')
    paths=read_whitelist(root/'Release/STUDIO20/packaging_whitelist.txt')
    removed=sorted(set(baseline_list)-set(paths))
    if removed:raise RuntimeError('delta deletion handling required: '+repr(removed))
    delta=[rel for rel in paths if rel not in baseline_list or sha256(root/rel)!=sha256(baseline/rel)]
    output.mkdir(parents=True)
    archive(root,paths,output/'ARCHON_STUDIO20_RELEASE.zip')
    archive(root,delta,output/'ARCHON_STUDIO20_DELTA.zip')
    result={'schema':'archon_studio20_artifacts_v1','release_files':len(paths),'delta_files':len(delta),'removed_files':removed,
            'baseline_manifest_sha256':sha256(baseline/'Release/STUDIO19/studio_release_integration.json'),
            'native_windows':'NOT_YET_NATIVELY_EXECUTED_ON_WINDOWS',
            'artifacts':{f.name:sha256(f) for f in sorted(output.glob('*.zip'))}}
    (output/'ARTIFACTS.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=='__main__':main()
