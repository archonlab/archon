# STUDIO20 build and acceptance

## Scope

One canonical Python/scientific tree. The release archive is an immutable artifact; the extracted **portable working directory is writable**. Program Files installation is unsupported and not selected by the installer. Optional Inno Setup installation uses `%LOCALAPPDATA%/ARCHON Studio` without elevation. State stays beside the payload in Results, Config, Atlas and archon-studio/public; there is no second science tree. Source launchers remain usable separately.

No bundled runtime is fabricated in this Linux release. An actual Windows runtime and native compiler are required to produce the final self-contained EXE. Browser remains an explicit visual-runtime prerequisite. Git Bash, WSL, Node/npm and system Python are not runtime requirements when the complete private runtime is supplied.

## Linux preparation

```
python3 -B Tools/verify_studio20_windows_distribution.py
python3 -B Tools/archon_windows_distribution.py stage --output /tmp/ARCHON-Windows-stage
python3 -B Tools/archon_windows_distribution.py verify --output /tmp/ARCHON-Windows-stage
```

The regression requires local loopback sockets. Headless and scientific fixture tests use temporary copies. No user Results are modified. Native Windows behavior cannot be inferred from these tests.

## Native Windows build

Supply an independently acquired, redistributable **complete Windows x64 Python** directory with python.exe, pythonw.exe, standard library, Tk/Tcl, numpy and Pillow (including their licenses and DLLs). A normal venv with external base paths is insufficient. The minimal embeddable Python ZIP lacks Tk/Tcl. The pipeline does not download or upgrade dependencies. Review the exact supplied runtime, then create its lock once:

```
C:\Build\Python\python.exe -B Tools\archon_windows_distribution.py lock --runtime-root C:\Build\Python --identity "CPython-version-and-reviewed-dependency-set" --output C:\Build\runtime.lock.json
```

The lock records every runtime file hash; it is a reproducibility input, not proof that the provider is trustworthy. Remove bytecode caches from the builder-owned runtime before locking, not from any user environment. Keep the lock with the build inputs. Changes require a new reviewed lock.

```
.\Packaging\windows\build.ps1 -RuntimeRoot C:\Build\Python -RuntimeLock C:\Build\runtime.lock.json -Output C:\Build\ARCHON20 -ISCC 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

The script validates runtime imports, stages exact bytes, runs native headless smoke in a disposable copy with spaces, generates explicit installer file entries, compiles `ARCHON-Studio-1.0.0.exe`, verifies the original stage and records runtime/dependency identity, compiler identity, stage hash and EXE hash in BUILD_RECEIPT.json. A zero-runtime preparation stage is never accepted for installer compilation. No recursive repository packaging occurs. The EXE is an installer around an unfrozen private Python runtime, not a renamed script.

Manifest JSON and release ZIP content/order/timestamps are deterministic for identical inputs. Inno compiler output is not claimed bit-for-bit deterministic: its exact binary hash and version are recorded. Build paths are excluded from the distribution manifest.

## Acceptance gates (STUDIO21)

NOT YET NATIVELY EXECUTED ON WINDOWS: build.ps1/ISCC compilation, double-click/shortcuts, Tk GUI and browser lifetime, multiprocessing, Search/Observer/Analyzer workloads, all descendants after stop/restart, reconnect after crash, locked files, Unicode/spaces, cold start and realistic existing research trees. Test the copied private runtime on a clean machine with no system Python. Verify DLL/Tcl relocation and licenses. Existing-data fixture tests establish preservation of fixture bytes, not complete scientific parity or real-user dataset acceptance.

Pause/resume are unsupported on Windows. Search safe checkpoint pause visibly reports unsupported. Studio Windows stop uses forced termination and explicitly does not promise a graceful checkpoint or descendant cleanup. This is an outstanding HIGH native runtime-hardening item; no fake success is reported. The artifact is a preparation milestone, not production Windows acceptance.

Installer updates copy only whitelisted payload/runtime files. No Results/Config/Atlas/public state deletion directives exist. Before upgrading a real research installation, native acceptance must verify preservation; the build smoke never uses it.

## Regression-manifest policy

STUDIO18/STUDIO19 verifier code is unchanged. STUDIO19's integration hashes are refreshed for cumulative source changes while retaining its assertions; the cumulative whitelist adds the required platform helper (671 files versus the baseline 670). New runtime helper files are listed explicitly in STUDIO20. Historical manifest documents remain provenance, not alternate runtime source archives.

## Release archives

With the original verified STUDIO19 materialization retained separately:

```
python3 -B Tools/archon_studio20_release.py --baseline /path/to/original-STUDIO19 --output /path/to/new-artifact-directory
```

The builder validates both baseline and final hash closure, emits full and additive delta ZIPs with stable timestamps/modes/order, and writes ARTIFACTS.json with SHA-256 and exact counts. The delta is applied over the original STUDIO19 tree, not a different milestone. Full ZIP contents equal the 686-entry packaging whitelist; generated staging metadata and user research data are excluded.
