#!/usr/bin/env python3
"""Fail-closed STUDIO20.3 open-source provenance policy verifier."""
from __future__ import annotations
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WHITELIST=ROOT/'Release/STUDIO20.3/packaging_whitelist.txt'
INTEGRATION=ROOT/'Release/STUDIO20.3/studio_release_integration.json'
def require(ok,msg):
    if not ok: raise AssertionError(msg)
def rows(p): return [x.strip() for x in p.read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')]
def run(*args,cwd=ROOT):
    p=subprocess.run([str(x) for x in args],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    require(p.returncode==0,p.stdout); return p.stdout
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    # New policy: modified code remains observable but runnable; corrupt provenance still blocks.
    run(sys.executable,'-B',ROOT/'Docs/Audits/2026-09-06/reproduce/test_source_tree_seal_policy.py')
    status=run(sys.executable,'-B',ROOT/'Analyzer_next/cli/observer_launcher_profile.py','--profile-status')
    require('integrity=MODIFIED_SOURCE_TREE' in status,'modified source status missing')
    headless=run(sys.executable,'-B',ROOT/'Analyzer_next/cli/observer_launcher_profile.py','--headless-check')
    require('"active_profile": "ol2"' in headless,'Observer OL2 headless launch did not reach runtime')

    # Preserve SCIENCEFIX1/2 semantic gates.
    for rel in [
        'Docs/Audits/2026-09-06/reproduce/test_mechanism_zero_values.py',
        'Docs/Audits/2026-09-06/reproduce/test_mechanism_scientific_semantics.py',
        'Docs/Audits/2026-09-06/reproduce/test_sciencefix2_value_semantics.py',
    ]: run(sys.executable,'-B',ROOT/rel)

    listed=rows(WHITELIST)
    require(len(listed)==len(set(listed)),'packaging whitelist duplicates')
    require(all((ROOT/r).is_file() for r in listed),'packaging whitelist missing file')
    for rel in listed:
        parts=Path(rel).parts
        require('__pycache__' not in parts and '.git' not in parts and '.agents' not in parts,f'dev/cache leak: {rel}')
        require(not rel.endswith(('.pyc','.zip','.tar','.tgz','.gz','.bz2','.xz')),f'archive/cache leak: {rel}')
        require(not rel.startswith('Artifacts/'),f'internal artifact leak: {rel}')

    integration=json.loads(INTEGRATION.read_text())
    require(integration['studio_version']=='STUDIO20.3' and integration['status']=='PASS','integration status mismatch')
    hashes=integration['file_hashes']; expected={r for r in listed if r!='Release/STUDIO20.3/studio_release_integration.json'}
    require(set(hashes)==expected,'hash closure mismatch')
    for rel in expected: require(hashes[rel]==sha(ROOT/rel),f'hash mismatch: {rel}')

    dist=json.loads((ROOT/'Packaging/distribution_contract.json').read_text())
    win=json.loads((ROOT/'Packaging/windows/distribution.json').read_text())
    require(dist['studio_version']=='STUDIO20.3','distribution version stale')
    require(dist['stage']['whitelist']=='Release/STUDIO20.3/packaging_whitelist.txt','distribution whitelist stale')
    require(win['milestone']=='STUDIO20.3','Windows milestone stale')

    with tempfile.TemporaryDirectory(prefix='archon-studio20.3-stage-') as raw:
        for platform in ('windows','macos','linux'):
            out=Path(raw)/platform
            text=run(sys.executable,'-B',ROOT/'Tools/archon_distribution_stage.py','--root',ROOT,'--platform',platform,'--output',out)
            require('PASS: STUDIO20.3' in text,f'{platform} stage stale')
            manifest=json.loads((out/'DISTRIBUTION_STAGE.json').read_text())
            require(manifest['release_files']==len(listed),f'{platform} file count mismatch')

    run(sys.executable,'-B',ROOT/'Tools/verify_studio18_platform_portability.py')
    run(sys.executable,'-B',ROOT/'Tools/archon_studio_runtime.py','--root',ROOT,'--self-test')
    run(sys.executable,'-B',ROOT/'Tools/archon_studio_desktop.py','--root',ROOT,'--headless-smoke','--port','0')
    print(f'PASS: STUDIO20.3 source-tree seal mismatches warn instead of blocking, corrupt provenance remains fail-closed, and {len(listed)} exact files stage cleanly')
    return 0
if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print(f'BLOCKED: {exc}',file=sys.stderr); raise SystemExit(2)
