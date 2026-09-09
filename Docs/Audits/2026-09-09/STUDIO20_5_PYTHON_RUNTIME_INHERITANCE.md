# STUDIO20.5 Python Runtime Inheritance Audit

## Root cause

`Tools/archon_runtime_python.py` selected `sys.executable` and then called
`Path.resolve()`. On macOS, `.venv/bin/python` is normally a symlink to the
Homebrew installation. Dereferencing it changed the executable spelling from
the virtual-environment owner to the physical Homebrew Python, so NumPy installed
in `.venv` was no longer importable by Embedded Universe Search.

The fix makes the interpreter path absolute without dereferencing symlinks and
propagates it as `ARCHON_PYTHON_EXECUTABLE` with `ARCHON_PYTHON_SOURCE`.

## Canonical selection contract

1. Valid `ARCHON_RUNTIME_PYTHON` configured override.
2. Valid propagated `ARCHON_PYTHON_EXECUTABLE` owner.
3. Valid private `Runtime/python` interpreter.
4. The parent process `sys.executable`, preserving its venv path spelling.
5. A reported PATH fallback only when none of the owned choices exists.

Every child environment starts from a copy of the parent environment. Commands
are argument arrays, including Windows paths containing spaces.

## Launch-path audit

Studio desktop snapshot preparation, Studio backend snapshot refresh, Embedded
Search, native Search Launcher, Embedded Observer, native Observer, Analyzer,
managed cohort Search materialization/dispatch/resume, experiment authorization,
automatic scientific refresh, Research Director pipeline stages, mutation
analysis, and Analyzer DAG subprocesses were inspected. Studio-owned Python
launches use the canonical resolver. Observer-internal `sys.executable` launches
run inside the already selected Observer interpreter and therefore retain the
same runtime. Platform shell/batch entrypoints remain bootstrap boundaries;
packaged Windows explicitly selects `Runtime/python/python.exe`.

The `python3` value in the Studio adapter-manifest example is third-party adapter
metadata, not a Studio process launch. Shebangs and verifier commands are also
not runtime child selection.

## Dependency and scientific integrity

Studio and native Search Launcher execute a NumPy/CuPy import preflight with the
exact interpreter command that will run Search. Failure is an explicit
`DEPENDENCY_ERROR` and no Search process starts.

Universe Search also checks its selected field backend before loading caches,
allocating IDs, evaluating candidates, or writing checkpoints. Typed field-backend failures propagate out of worker
evaluation and are never converted to `CRASHED score=-1000000000`. Genuine
candidate exceptions retain the distinct `CANDIDATE_ERROR` status and existing
exclusion from clean results.

Scientific scoring, mutation, population selection, Observer semantics,
Analyzer semantics, and experiment semantics were not changed.

## Verification

`Tools/verify_python_runtime_inheritance.py` covers the macOS venv-symlink
reproduction, configured/packaged/inherited precedence, environment retention,
Embedded and native Studio launch commands, Observer and Analyzer commands,
dependency preflight, scientific failure classification, Linux execution, and
Windows argument-array construction with spaces.
