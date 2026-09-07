#!/usr/bin/env python3
"""Build-manifest helper for the ARCHON Studio production frontend bundle.

The browser bundle is immutable application code. Canonical research state is
*not* copied into it: /studio/snapshot.json and preview assets are served live by
the local Python runtime from archon-studio/public/studio.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit, unquote
from html.parser import HTMLParser
from pathlib import Path
import sys
from typing import Iterable

SCHEMA = "archon_studio_production_bundle_v1"
STUDIO_VERSION = "STUDIO20.5"
MANIFEST_NAME = "archon-studio-build.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_files(root: Path) -> list[Path]:
    studio = root / "archon-studio"
    explicit = [
        studio / "package.json",
        studio / "package-lock.json",
        studio / "vite.production.config.ts",
        studio / "production-src" / "index.html",
        studio / "production-src" / "main.tsx",
        studio / "app" / "page.tsx",
        studio / "app" / "globals.css",
        studio / "app" / "light-theme.css",
    ]
    trees = [studio / "lib"]
    files = [p for p in explicit if p.is_file()]
    for tree in trees:
        if tree.is_dir():
            files.extend(p for p in tree.rglob("*") if p.is_file() and p.suffix in {".ts", ".tsx", ".css", ".json"})
    return sorted(set(files))


def source_hash(root: Path) -> str:
    h = hashlib.sha256()
    for path in source_files(root):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        h.update(len(rel).to_bytes(4, "big")); h.update(rel)
        data = path.read_bytes()
        h.update(len(data).to_bytes(8, "big")); h.update(data)
    return h.hexdigest()


def bundle_files(dist: Path) -> Iterable[Path]:
    if dist.is_symlink():
        raise RuntimeError("production dist is a symlink")
    for path in sorted(dist.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"production bundle symlink: {path}")
        if path.is_file() and path != dist / MANIFEST_NAME:
            yield path


def inspect_bundle(root: Path, *, require_current: bool = True) -> dict:
    studio = root / "archon-studio"
    dist = studio / "dist"
    index = dist / "index.html"
    manifest_path = dist / MANIFEST_NAME
    if not index.is_file():
        raise RuntimeError("archon-studio/dist/index.html is missing")
    if not manifest_path.is_file():
        raise RuntimeError(f"archon-studio/dist/{MANIFEST_NAME} is missing")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA or payload.get("studio_version") != STUDIO_VERSION:
        raise RuntimeError("production bundle manifest schema/version is unsupported")
    # Development trees carry the frontend sources and therefore can prove the
    # bundle is current relative to those sources.  Clean release candidates
    # intentionally omit dev-only frontend sources; in that mode the sealed
    # dist file manifest remains authoritative and source freshness is proven
    # before materialization by STUDIO16 release integration.
    source_set = source_files(root)
    if require_current and source_set and payload.get("source_hash") != source_hash(root):
        raise RuntimeError("production frontend bundle is stale relative to current Studio sources")
    forbidden = [dist / "studio" / "snapshot.json", dist / "studio" / "previews"]
    if any(path.exists() for path in forbidden):
        raise RuntimeError("production bundle contains research state; public/studio must remain live/runtime-owned")
    recorded = payload.get("files") or []
    actual = []
    for path in bundle_files(dist):
        actual.append({
            "path": path.relative_to(dist).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    if recorded != actual:
        raise RuntimeError("production bundle file manifest does not match dist contents")
    html = index.read_text(encoding="utf-8", errors="replace")
    if "<div id=\"root\"></div>" not in html:
        raise RuntimeError("production index.html is missing the Studio root")
    if not any(item["path"].startswith("assets/") and item["path"].endswith(".js") for item in actual):
        raise RuntimeError("production bundle contains no JavaScript asset")
    class References(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if value and (key == "src" or (tag == "link" and key == "href")):
                    references.append((index, value))
    references = []
    References().feed(html)
    for path in dist.rglob("*.css"):
        for match in re.finditer(r"url\(\s*['\"]?([^)'\"\s]+)", path.read_text()):
            references.append((path, match.group(1)))
    for origin, value in references:
        url = urlsplit(value)
        if url.scheme == "data" or value.startswith("#"):
            continue
        if url.scheme or url.netloc:
            raise RuntimeError(f"external production asset: {value}")
        rel = unquote(url.path)
        asset = (dist / rel.lstrip("/")) if rel.startswith("/") else origin.parent / rel
        if not asset.resolve().is_relative_to(dist.resolve()) or not asset.is_file():
            raise RuntimeError(f"missing or unsafe production asset: {value}")
    return payload


def write_manifest(root: Path) -> dict:
    dist = root / "archon-studio" / "dist"
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError("Vite did not create archon-studio/dist/index.html")
    # publicDir=false is a release-safety requirement: user research state must
    # never be frozen into an application build.
    if (dist / "studio").exists():
        raise RuntimeError("dist/studio exists; production build accidentally copied live research state")
    files = [
        {"path": p.relative_to(dist).as_posix(), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
        for p in bundle_files(dist)
    ]
    payload = {
        "schema": SCHEMA,
        "studio_version": STUDIO_VERSION,
        "built_at": utc_now(),
        "source_hash": source_hash(root),
        "file_count": len(files),
        "bytes": sum(int(item["bytes"]) for item in files),
        "files": files,
        "runtime_data": {
            "snapshot": "/studio/snapshot.json",
            "previews": "/studio/previews/",
            "bundled": False,
        },
    }
    path = dist / MANIFEST_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inspect_bundle(root)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="ARCHON Studio production bundle manifest")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.write:
            payload = write_manifest(root)
            print(f"PASS: STUDIO20.5 production bundle sealed: {payload['file_count']} files · {payload['bytes']} bytes")
            return 0
        payload = inspect_bundle(root)
        print(f"PASS: STUDIO20.5 production bundle current: {payload['file_count']} files · {payload['bytes']} bytes")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
