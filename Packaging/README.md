# ARCHON Studio distribution foundation

STUDIO19 separates the **scientific/runtime tree** from the **platform packaging shell**.
All three desktop distributions stage the same exact release whitelist. Platform tooling
may add a complete private Python runtime under `Runtime/python`, but it must not fork
Search, Observer, Analyzer, Studio snapshot, or frontend logic.

The final artifact names are reserved as:

- Windows: `ARCHON-Studio-1.0.0.exe`
- macOS: `ARCHON-Studio-1.0.0.dmg`
- Linux: `ARCHON-Studio-1.0.0.AppImage`

`Tools/archon_distribution_stage.py` creates a deterministic staging directory from the
STUDIO19 packaging whitelist. Use `--runtime-root` only with a complete, redistributable
Python runtime for the target platform. A source-runtime stage can be created without it
for contract and packaging tests.
