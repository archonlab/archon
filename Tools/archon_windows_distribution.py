#!/usr/bin/env python3
"""Exact, deterministic Windows portable staging and native runtime validation."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from archon_distribution_stage import read_whitelist, copy_tree_exact, sha256

ROOT = Path(__file__).resolve().parents[1]
LIST = 'Release/STUDIO20.5/packaging_whitelist.txt'
MANIFEST = 'WINDOWS_DISTRIBUTION.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inventory(root):
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise RuntimeError(f'symlink not permitted: {p.name}')
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if any(part in {'.git', '__pycache__'} for part in p.relative_to(root).parts) or p.suffix == '.pyc':
                raise RuntimeError(f'cache/development file in runtime: {rel}')
            result[rel] = sha256(p)
    return result


def stage(root, output, runtime=None, lock=None):
    root, output = root.resolve(), output.resolve()
    if output.exists() or output == root or root.is_relative_to(output):
        raise RuntimeError('stage output must be new and must not contain the source')
    paths = read_whitelist(root / LIST)
    # Validate all inputs before materializing anything.
    for rel in paths:
        p = root / rel
        if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(root):
            raise RuntimeError(f'invalid payload source: {rel}')
    runtime_hashes = {}
    if runtime:
        runtime = runtime.resolve()
        if not lock:
            raise RuntimeError('bundled runtime requires --runtime-lock with exact file hashes')
        runtime_hashes = inventory(runtime)
        recorded = json.loads(lock.read_text())
        if recorded.get('files') != runtime_hashes or not recorded.get('identity'):
            raise RuntimeError('runtime lock does not match exact runtime bytes/identity')
        if not {'python.exe', 'pythonw.exe'}.issubset(runtime_hashes):
            raise RuntimeError('complete Windows Python runtime requires python.exe and pythonw.exe')
        if not (runtime / 'python.exe').read_bytes().startswith(b'MZ'):
            raise RuntimeError('Windows runtime is not a PE executable')
    output.mkdir(parents=True)
    hashes = copy_tree_exact(root, output, paths)
    if runtime:
        shutil.copytree(runtime, output / 'Runtime/python')
        hashes.update({f'Runtime/python/{k}': v for k, v in runtime_hashes.items()})
    manifest = {
        'schema': 'archon_windows_distribution_v1', 'milestone': 'STUDIO20.5', 'version': '1.0.0',
        'platform': 'windows-x64', 'mode': 'writable-portable',
        'source_identity': digest({k: hashes[k] for k in paths}),
        'whitelist_sha256': sha256(root / LIST),
        'runtime_identity': recorded['identity'] if runtime else None,
        'runtime_sha256': digest(runtime_hashes) if runtime else None,
        'native_acceptance': 'NOT_YET_NATIVELY_EXECUTED_ON_WINDOWS',
        'files': hashes,
    }
    (output / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    verify(output)
    return manifest


def verify(output):
    manifest = json.loads((output / MANIFEST).read_text())
    actual = inventory(output)
    actual.pop(MANIFEST)
    if actual != manifest['files']:
        raise RuntimeError('stage differs from exact manifest (missing, extra or modified files)')
    paths = read_whitelist(output / LIST)
    payload = {key: actual[key] for key in paths}
    if digest(payload) != manifest['source_identity'] or sha256(output / LIST) != manifest['whitelist_sha256']:
        raise RuntimeError('source identity/whitelist mismatch')
    if any(key not in payload and not key.startswith('Runtime/python/') for key in actual):
        raise RuntimeError('unexpected payload path')
    integration = json.loads((output / 'Release/STUDIO20.5/studio_release_integration.json').read_text())
    expected = {k:v for k,v in payload.items() if k != 'Release/STUDIO20.5/studio_release_integration.json'}
    if integration['file_hashes'] != expected:
        raise RuntimeError('release integration hash closure mismatch')
    return manifest


def probe(runtime):
    executable = runtime.resolve() / ('python.exe' if os.name == 'nt' else 'bin/python3')
    if not executable.is_file():
        raise RuntimeError(f'ARCHON private Python missing: {executable}. Supply a complete runtime including Tk/Tcl, numpy and Pillow.')
    code = '''import sys,json,platform,tkinter,sqlite3,multiprocessing,numpy,PIL
from pathlib import Path
if sys.platform == 'win32':
    private = Path(sys.executable).resolve().parent
    assert Path(sys.base_prefix).resolve() == private, 'Runtime depends on external base Python'
    for module in (tkinter,numpy,PIL):
        assert Path(module.__file__).resolve().is_relative_to(private), 'Runtime module escapes private Python'
from importlib.metadata import version
assert sys.version_info >= (3,12), 'Python 3.12 or newer required'
t = tkinter.Tcl(); t.eval('info patchlevel')
print(json.dumps({'python':platform.python_version(),'platform':sys.platform,'bits':64 if sys.maxsize>2**32 else 32,'numpy':version('numpy'),'Pillow':version('Pillow'),'tcl':t.eval('info patchlevel')},sort_keys=True))'''
    env = {k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH'}}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    result = subprocess.run([str(executable), '-I', '-B', '-c', code], env=env, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('ARCHON runtime dependency validation failed (Python, Tk/Tcl, numpy, Pillow, SQLite): '+result.stderr[-3000:])
    receipt = json.loads(result.stdout)
    if os.name == 'nt' and (receipt['platform'] != 'win32' or receipt['bits'] != 64):
        raise RuntimeError('Windows x64 Python required')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['stage','verify','probe','lock','installer-files'])
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--output',type=Path)
    p.add_argument('--runtime-root',type=Path)
    p.add_argument('--runtime-lock',type=Path)
    p.add_argument('--identity')
    a=p.parse_args()
    if a.action=='stage':
        if not a.output: p.error('--output required')
        result=stage(a.root,a.output,a.runtime_root,a.runtime_lock)
        print(f"PASS: exact Windows stage: {len(result['files'])} files; bundled runtime: {bool(result['runtime_identity'])}")
    elif a.action=='verify':
        verify(a.output); print('PASS: exact Windows stage hashes and closure')
    elif a.action=='probe':
        if not a.runtime_root:p.error('--runtime-root required')
        print(json.dumps(probe(a.runtime_root),sort_keys=True))
    elif a.action=='lock':
        if not a.runtime_root or not a.output or not a.identity:p.error('--runtime-root, --output and --identity required')
        if a.output.exists():raise RuntimeError('refusing to replace runtime lock')
        a.output.write_text(json.dumps({'identity':a.identity,'files':inventory(a.runtime_root)},sort_keys=True,indent=2)+'\n')
    else:
        m=verify(a.root)
        if not m['runtime_identity']:raise RuntimeError('installer requires locked bundled runtime')
        lines=[]
        for rel in sorted([*m['files'], MANIFEST]):
            if any(c in rel for c in '\";{}\r\n'):raise RuntimeError('unsafe installer filename')
            win=rel.replace('/', '\\'); parent=str(Path(rel).parent).replace('/', '\\')
            dest='{app}' + ('\\'+parent if parent!='.' else '')
            lines.append(f'Source: "{{#StageDir}}\\{win}"; DestDir: "{dest}"; Flags: ignoreversion')
        a.output.write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(f'BLOCKED: {exc}',file=sys.stderr);sys.exit(2)
