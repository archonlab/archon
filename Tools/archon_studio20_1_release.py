#!/usr/bin/env python3
"""Build deterministic STUDIO20.1 full and delta archives from an exact baseline tree."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIST = Path("Release/STUDIO20.1/packaging_whitelist.txt")


def rows(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(root: Path, paths: list[str], output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in sorted(paths):
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100755 if rel.endswith((".sh", ".command")) else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, (root / rel).read_bytes(), compresslevel=9)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    root, baseline, output = a.root.resolve(), a.baseline.resolve(), a.output.resolve()
    paths = rows(root / LIST)
    baseline_paths = set()
    old_list = baseline / "Release/STUDIO20/packaging_whitelist.txt"
    if old_list.is_file():
        baseline_paths = set(rows(old_list))
    delta = []
    for rel in paths:
        old = baseline / rel
        if rel not in baseline_paths or not old.is_file() or sha(root / rel) != sha(old):
            delta.append(rel)
    output.mkdir(parents=True, exist_ok=False)
    full = output / "ARCHON_STUDIO20.1_RELEASE.zip"
    patch = output / "ARCHON_STUDIO20.1_SCIENCEFIX_DELTA.zip"
    archive(root, paths, full)
    archive(root, delta, patch)
    receipt = {
        "schema": "archon_studio20_1_artifacts_v1",
        "release_files": len(paths),
        "delta_files": len(delta),
        "artifacts": {full.name: sha(full), patch.name: sha(patch)},
    }
    (output / "ARTIFACTS.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
