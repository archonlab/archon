"""Stable content-fingerprint policy for the production Analyzer DAG.

This module owns which file changes are scientifically meaningful.  State
persistence and step-current decisions live in ``incremental_dag`` so the
normalization policy can be characterized independently.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Iterable


DIGEST_POLICY = 3
VOLATILE_TOP_LEVEL_KEYS = frozenset({
    "created",
    "generated",
    "generated_at",
    "updated",
})
VOLATILE_MARKDOWN_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:created|generated|updated)\s*:"
    r"\s*[`*_]*\s*\d{4}-\d{2}-\d{2}",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FileFingerprint:
    """One digest plus the cache field and mode that produced it."""

    value: str
    cache_field: str
    mode: str


@dataclass(frozen=True)
class FingerprintPolicy:
    """Versioned rules for exact, semantic, and large-file fingerprints."""

    version: int = DIGEST_POLICY
    large_file_threshold: int = 512 * 1024 * 1024
    stream_chunk_size: int = 4 * 1024 * 1024

    @staticmethod
    def semantic_bytes(path: Path, raw: bytes) -> bytes:
        """Remove presentation-only run timestamps from Analyzer products."""
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return raw
            if isinstance(payload, dict):
                payload = {
                    key: value
                    for key, value in payload.items()
                    if key not in VOLATILE_TOP_LEVEL_KEYS
                }
            return json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        if suffix in {".md", ".markdown"}:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw
            stable_lines = [
                line
                for line in text.splitlines()
                if not VOLATILE_MARKDOWN_LINE.match(line)
            ]
            return "\n".join(stable_lines).encode("utf-8")
        return raw

    def _stream_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(self.stream_chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _metadata_digest(path: Path, stat: os.stat_result) -> str:
        payload = json.dumps(
            {
                "path": str(path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "metadata:" + hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    def fingerprint(
        self,
        path: Path,
        stat: os.stat_result,
        *,
        semantic: bool = False,
    ) -> FileFingerprint:
        """Fingerprint a file under this immutable policy."""
        if stat.st_size >= self.large_file_threshold:
            return FileFingerprint(
                value=self._metadata_digest(path, stat),
                cache_field="metadata_sha256",
                mode="metadata",
            )
        if semantic:
            return FileFingerprint(
                value=hashlib.sha256(
                    self.semantic_bytes(path, path.read_bytes())
                ).hexdigest(),
                cache_field="semantic_sha256",
                mode="semantic",
            )
        return FileFingerprint(
            value=self._stream_sha256(path),
            cache_field="sha256",
            mode="stream",
        )

    def cache_field(
        self,
        stat: os.stat_result,
        *,
        semantic: bool = False,
    ) -> str:
        if stat.st_size >= self.large_file_threshold:
            return "metadata_sha256"
        return "semantic_sha256" if semantic else "sha256"


DEFAULT_FINGERPRINT_POLICY = FingerprintPolicy()


def expand_files(paths: Iterable[Path]) -> tuple[Path, ...]:
    """Resolve files and recursively expand directory dependencies."""
    files: set[Path] = set()
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    files.add(child.resolve())
    return tuple(sorted(files, key=str))


def snapshot_digest(files: dict[str, str]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_delta(
    previous: dict[str, str],
    current: dict[str, str],
) -> dict[str, int]:
    old_keys = set(previous)
    new_keys = set(current)
    shared = old_keys & new_keys
    changed = sum(previous[key] != current[key] for key in shared)
    return {
        "new": len(new_keys - old_keys),
        "changed": changed,
        "removed": len(old_keys - new_keys),
        "reused": len(shared) - changed,
    }


__all__ = [
    "DEFAULT_FINGERPRINT_POLICY",
    "DIGEST_POLICY",
    "FileFingerprint",
    "FingerprintPolicy",
    "VOLATILE_MARKDOWN_LINE",
    "VOLATILE_TOP_LEVEL_KEYS",
    "expand_files",
    "snapshot_delta",
    "snapshot_digest",
]
