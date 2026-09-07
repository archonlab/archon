#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'Tools/archon_studio_runtime.py'
DESKTOP=ROOT/'Tools/archon_studio_desktop.py'

def fail(msg:str)->None:
    raise SystemExit('FAIL: '+msg)

def require(cond:bool,msg:str)->None:
    if not cond: fail(msg)

def main()->int:
    launchers={
      'linux': ROOT/'ARCHON_STUDIO.sh',
      'windows': ROOT/'ARCHON_STUDIO.bat',
      'macos': ROOT/'ARCHON_STUDIO.command',
    }
    for name,path in launchers.items(): require(path.is_file(),f'missing {name} launcher: {path.name}')
    require(os.access(launchers['linux'],os.X_OK),'Linux launcher is not executable')
    require(os.access(launchers['macos'],os.X_OK),'macOS launcher is not executable')
    bat=launchers['windows'].read_bytes()
    require(b'\r\n' in bat,'Windows launcher is not CRLF')
    for path in launchers.values():
        text=path.read_text(errors='replace')
        require('archon_studio_desktop.py' in text,f'{path.name} does not target canonical desktop entrypoint')
    runtime=RUNTIME.read_text()
    require('command=["bash"' not in runtime,'Studio runtime still hard-codes bash engine launch')
    expected=[
      'Universe_Search" / "search_launcher.py',
      'Analyzer_next" / "cli" / "observer_launcher_profile.py',
      'Analyzer_next" / "cli" / "analyze_results.py',
    ]
    for needle in expected: require(needle in runtime,f'missing portable engine entrypoint: {needle}')
    require(runtime.count('command=[*self.python_command') >= 3,'engine launchers do not consistently use the portable child Python command')
    require('sys.platform == "darwin"' in runtime and 'os.name == "nt"' in runtime and 'sys.platform.startswith("linux")' in runtime,
            'desktop folder opening is not explicitly cross-platform')
    proc=subprocess.run([sys.executable,str(DESKTOP),'--root',str(ROOT),'--self-test'],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    require(proc.returncode==0,'desktop self-test failed: '+proc.stdout[-1200:])
    print('PASS: STUDIO18 removes the Bash dependency from Studio-owned engine launches, preserves canonical platform launchers, and passes the shared desktop self-test')
    return 0
if __name__=='__main__': raise SystemExit(main())
