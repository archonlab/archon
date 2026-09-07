# STUDIO19 → STUDIO20 Windows distribution audit

Baseline: supplied STUDIO19 tree; exact 670-file staging preserved in the test workspace before changes. STUDIO18 and STUDIO19 verifiers PASS (local HTTP tests require socket access outside the sandbox). No historical archive used.

| Severity | Finding / source | Disposition |
|---|---|---|
| BLOCKER | Search `search_launcher.py:797`, Observer `runs/command_builder.py:89`, `experiment_runtime_handoff.py:721`, `cohort_search_runtime.py:269` launch `python3` | Route through STUDIO19 resolver. Upper-level tests miss this closure. |
| BLOCKER | Observer `shell2/analyze1/model.py:76` launches ANALYZER.sh through Bash | Launch canonical Analyzer Python entrypoint; retain launcher provenance. |
| BLOCKER | Root-relative writes across canonical science and Studio | Explicit writable portable root; do not advertise Program Files support. Avoid duplicating science or relocating only some writers. |
| HIGH | Windows terminate kills parent rather than POSIX process group; Search uses SIGTERM as graceful pause | Native acceptance required for descendants, checkpoints and queue transitions; Windows stop is not graceful pause. |
| HIGH | Search / automatic refresh use os.kill(pid, 0) for liveness | Windows needs a read-only process handle probe. Never use Windows os.kill for liveness. |
| HIGH | Bridge CORS wildcard and unguarded POST | Restrict browser origins and Host to loopback; retain constrained known engine actions. |
| HIGH | Reconnect checks version/capability, not project identity | Require matching canonical root identity before attaching. |
| HIGH | Runtime resolver checks file existence only; stage accepts arbitrary runtime tree | Native dependency probe and exact runtime file hashes required before installer build. Minimal embedded Python lacks Tk. |
| HIGH | Stage --replace can delete source/ancestor; whitelist does not reject traversal/symlinks | Fail closed before mutation; exact stage verifier must reject additions and modified bytes. |
| MEDIUM | Observer/Search folder openers use xdg-open | Shared portable opener. |
| MEDIUM | Build timestamp/runtime identity/dependency versions absent | Deterministic content manifests; native runtime receipt and artifact hashes. |
| CLEAN | Studio engine command lists, snapshot commands use resolver; no shell=True | Preserve argument arrays and canonical Python tree. |
| CLEAN | Desktop defaults to 127.0.0.1 and rejects unrelated occupied port | Test collision and root mismatch; no automatic firewall rule. |
| CLEAN | Pause/resume return unsupported outside POSIX | Preserve honest errors. |
| CLEAN | Production frontend already sealed, no Node needed | Preserve dist verification and live public assets. |
| CLEAN | Missing Atlas is represented as empty scientific state | Verify cold start on disposable exact stage. Existing-data tests must use fixtures, never user Results. |

## Process closure

Desktop → snapshot builder; in-process HTTP bridge → Search launcher/core, Observer profile router/adapter, Analyzer CLI, snapshot builder. Observer profile → OL2 → run command builder / Analyze1 / experiment authorization / cohort handoff → canonical Python scientific entrypoints. Analyzer coordinator and legacy adapters currently inherit a real interpreter via sys.executable: safe for the selected **unfrozen private Python** model, not a general freezing guarantee. Browser and folder opening are OS integration, not science. Search multiprocessing/native descendants require Windows acceptance.

## Writable-path inventory

`Results/Universe_Search`: checkpoints, search runs, observations, telemetry SQLite, research execution metadata; `Results/Analysis`: plans, evidence, experiments, locks and generated reports; `Results/Studio`: previews, readiness, browser profile and saved previews; `Config/Studio`: adapters/settings; `Config/ObserverLauncher`: bootstrapped profile/configuration and world catalog cache; `Atlas/Worlds`, `Atlas/Knowledge`: generated atlas/research state; `archon-studio/public/studio`: snapshot, sync metadata and preview assets; Python bytecode caches beside modules unless disabled. `archon_paths.ensure_layout` also creates Documentation/Legacy and canonical directories. Existing data must remain outside packaging whitelists.

## Distribution decision

STUDIO20 uses one-folder portable payload + complete private Python under Runtime/python. An optional per-user installer wraps that exact directory; no one-file freeze. Payload is immutable **as a release artifact**, while the extracted portable working tree is explicitly writable. Installed mode with immutable Program Files plus separate state is deferred, not silently claimed. No science duplication or fallback runtime tree. A runtime supplied by a builder must include Tk/Tcl and required scientific modules, with exact hashes and a native probe; no unverified downloads or inferred dependency lock.

Windows native compilation, actual GUI launch, descendant cleanup, existing real research fixtures and Windows filesystem behavior remain acceptance gates. Linux preparation is not Windows execution.

References: Python Windows documentation https://docs.python.org/3/using/windows.html ; Inno Setup non-admin mode https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm .

## Implemented disposition

The listed hardcoded Python/Bash process commands now use the common resolver, including nested Observer routes. Folder opening and PID liveness share a thin OS helper. The managed cohort resume guard now probes liveness on Windows too (previously `/proc`-only). Safe Search pause is visibly unsupported on Windows; close/stop messages no longer promise a checkpoint there. Loopback Host/Origin checks and root-specific reconnect are implemented. The exact staging pipeline, runtime lock, native dependency probe, explicit installer file list and deterministic release/delta builder are present.

Cross-platform regression: PASS, including STUDIO18/STUDIO19 unchanged test code. STUDIO20 packaging closure: 686 files; runtime whitelist: 622 files. Cumulative STUDIO19 stage adds the new platform helper (671 vs original 670). Cold-start bridge and production frontend smoke: PASS. Existing retained rule, experiment, validation evidence and readable discovery fixture: detected, source bytes preserved. Native Windows process-tree cleanup, safe checkpoint semantics, DLL relocation and interactive acceptance remain HIGH/PENDING; Program Files mode is deliberately unsupported.

## Launch repair after clean-install report

Actual shell-entrypoint testing exposed two missed issues: Observer's carried RELEASE6 authorization fingerprints were stale (including changes already present in STUDIO19), and legacy STUDIO.sh failed when port 8765 was occupied. STUDIO.sh now delegates to ARCHON_STUDIO.sh. The desktop chooses a free port on a default-port collision with another root/service; explicitly requested ports still fail closed. No foreign processes are killed. The release authorization now fingerprints the shipped tree and records the previous authorization hash plus every changed hash under maintenance_update; original acceptance provenance remains unchanged, and no fresh human/Windows acceptance is asserted. Regression covers production Observer routing, tamper rejection, real shell entrypoints and occupied-port fallback.
