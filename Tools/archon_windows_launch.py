#!/usr/bin/env python3
"""Launch the canonical desktop using a private, unfrozen Python runtime."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root=Path(__file__).resolve().parents[1]
    from archon_windows_distribution import probe
    probe(root/'Runtime/python')
    # All canonical runtime writers use the explicitly writable portable tree.
    try:
        with tempfile.TemporaryFile(dir=root):
            pass
    except OSError as exc:
        raise RuntimeError('ARCHON portable folder must be writable. Move the entire application to a user-owned folder; Program Files is not supported.') from exc
    env=os.environ.copy()
    env.pop('PYTHONHOME',None)
    env.pop('PYTHONPATH',None)
    env['ARCHON_RUNTIME_PYTHON']=str(root/'Runtime/python/python.exe')
    env['PYTHONDONTWRITEBYTECODE']='1'
    env['PYTHONUNBUFFERED']='1'
    logs=root/'Results/Studio/runtime'
    logs.mkdir(parents=True,exist_ok=True)
    with (logs/'desktop.log').open('a',encoding='utf-8') as log:
        result=subprocess.run([env['ARCHON_RUNTIME_PYTHON'],'-B',str(root/'Tools/archon_studio_desktop.py'),'--root',str(root)],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'ARCHON desktop failed. See {logs / "desktop.log"}')
    return 0

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        message=str(exc)
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,message,'ARCHON Studio — launch failed',0x10)
        elif sys.stderr:
            print(message,file=sys.stderr)
        raise SystemExit(2)
