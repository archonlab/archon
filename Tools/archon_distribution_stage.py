#!/usr/bin/env python3
"""Create an exact ARCHON Studio distribution staging tree."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys

PLATFORMS = {"windows", "macos", "linux"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_whitelist(path: Path) -> list[str]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if value and not value.startswith("#"):
            parsed = PurePosixPath(value)
            if parsed.is_absolute() or any(part in {"..", "."} for part in parsed.parts) or "\\" in value or ":" in value or parsed.as_posix() != value:
                raise RuntimeError(f"unsafe whitelist path: {value}")
            rows.append(value)
    if len(rows) != len(set(rows)):
        raise RuntimeError("packaging whitelist contains duplicate paths")
    return rows


def copy_tree_exact(root: Path, output: Path, paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for rel in paths:
        src = root / rel
        if src.is_symlink() or not src.resolve().is_relative_to(root.resolve()):
            raise RuntimeError(f"whitelist source escapes root or is a symlink: {rel}")
        if not src.is_file():
            raise RuntimeError(f"whitelisted file is missing: {rel}")
        dst = output / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        hashes[rel] = sha256(dst)
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    whitelist = root / "Release/STUDIO20.5/packaging_whitelist.txt"
    paths = read_whitelist(whitelist)
    output = args.output.resolve()
    if output == root or root.is_relative_to(output):
        raise RuntimeError("output must not be the source root or its ancestor")
    if args.runtime_root and (args.runtime_root.resolve().is_relative_to(output) or output.is_relative_to(args.runtime_root.resolve())):
        raise RuntimeError("runtime and output must not overlap")
    if output.exists():
        if not args.replace:
            raise RuntimeError(f"output already exists: {output}; use --replace")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    hashes = copy_tree_exact(root, output, paths)
    runtime_mode = "source-runtime"
    runtime_files = 0
    if args.runtime_root:
        runtime_root = args.runtime_root.resolve()
        if not runtime_root.is_dir():
            raise RuntimeError(f"runtime root is not a directory: {runtime_root}")
        destination = output / "Runtime/python"
        shutil.copytree(runtime_root, destination)
        runtime_files = sum(1 for p in destination.rglob("*") if p.is_file())
        runtime_mode = "bundled-python"

    manifest = {
        "schema": "archon_distribution_stage_v1",
        "studio_version": "STUDIO20.5",
        "platform": args.platform,
        "runtime_mode": runtime_mode,
        "release_files": len(paths),
        "runtime_files": runtime_files,
        "release_hashes": hashes,
    }
    (output / "DISTRIBUTION_STAGE.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"PASS: STUDIO20.5 {args.platform} distribution stage: {len(paths)} exact release files · {runtime_mode}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
