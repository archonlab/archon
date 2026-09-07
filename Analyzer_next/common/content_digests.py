"""Content digests used by modular incremental caches."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

STATE_SCHEMA = 1

VOLATILE_TOP_LEVEL_KEYS = {
    "created",
    "generated",
    "generated_at",
    "updated",
}

VOLATILE_MARKDOWN_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:created|generated|updated)\s*:"
    r"\s*[`*_]*\s*\d{4}-\d{2}-\d{2}",
    re.IGNORECASE,
)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _expand_files(paths: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    files.add(child.resolve())
    return sorted(files, key=str)


class ContentDigests:
    """SHA-256 cache keyed by path, size and nanosecond mtime."""

    def __init__(self, path: Path):
        self.path = path
        raw = _load_json(path, {"schema": STATE_SCHEMA, "files": {}})
        if raw.get("schema") != STATE_SCHEMA or not isinstance(raw.get("files"), dict):
            raw = {"schema": STATE_SCHEMA, "files": {}}
        self.data = raw
        self.dirty = False

    @staticmethod
    def _semantic_bytes(path: Path, raw: bytes) -> bytes:
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

    LARGE_FILE_THRESHOLD = 512 * 1024 * 1024
    STREAM_CHUNK_SIZE = 4 * 1024 * 1024

    @classmethod
    def _stream_sha256(cls, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(cls.STREAM_CHUNK_SIZE)
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

    def digest(self, path: Path, *, semantic: bool = False) -> str:
        path = path.resolve()
        stat = path.stat()
        key = str(path)
        previous = self.data["files"].get(key, {})

        large_file = stat.st_size >= self.LARGE_FILE_THRESHOLD
        if large_file:
            digest_key = "metadata_sha256"
        else:
            digest_key = "semantic_sha256" if semantic else "sha256"

        if (
            previous.get("size") == stat.st_size
            and previous.get("mtime_ns") == stat.st_mtime_ns
            and previous.get("ctime_ns") == stat.st_ctime_ns
            and isinstance(previous.get(digest_key), str)
        ):
            return previous[digest_key]

        if large_file:
            value = self._metadata_digest(path, stat)
        elif semantic:
            raw = path.read_bytes()
            value = hashlib.sha256(
                self._semantic_bytes(path, raw)
            ).hexdigest()
        else:
            value = self._stream_sha256(path)

        current = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns,
            "digest_mode": (
                "metadata"
                if large_file
                else "semantic"
                if semantic
                else "stream"
            ),
        }
        if (
            previous.get("size") == stat.st_size
            and previous.get("mtime_ns") == stat.st_mtime_ns
            and previous.get("ctime_ns") == stat.st_ctime_ns
        ):
            current.update({
                name: previous[name]
                for name in (
                    "sha256",
                    "semantic_sha256",
                    "metadata_sha256",
                )
                if isinstance(previous.get(name), str)
            })
        current[digest_key] = value
        self.data["files"][key] = current
        self.dirty = True
        return value

    def snapshot(
        self,
        paths: Iterable[Path],
        *,
        semantic_paths: set[Path] | None = None,
    ) -> dict[str, str]:
        semantic_paths = semantic_paths or set()
        return {
            str(path): self.digest(path, semantic=path in semantic_paths)
            for path in _expand_files(paths)
        }

    def save(self) -> None:
        if self.dirty:
            _atomic_json(self.path, self.data)
            self.dirty = False


