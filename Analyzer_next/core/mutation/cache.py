"""Per-mutation content cache independent of the pipeline DAG."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from Analyzer_next.common.content_digests import ContentDigests

STATE_SCHEMA = 1


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


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


def _digest_snapshot(
    files: dict[str, str],
    *,
    analysis_version: int,
) -> str:
    payload = {
        "analysis_version": analysis_version,
        "files": files,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class IncrementalMutationCache:
    """Track the exact scientific inputs for every mutation comparison."""

    def __init__(
        self,
        output_root: Path,
        *,
        analysis_version: int,
    ):
        self.output_root = Path(output_root).resolve()
        self.analysis_version = int(analysis_version)
        self.cache_dir = self.output_root / ".incremental"
        self.state_path = self.cache_dir / "mutation_cache_state.json"
        digest_path = self.cache_dir / "mutation_digest_cache.json"

        raw = _load_json(
            self.state_path,
            {"schema": STATE_SCHEMA, "entries": {}},
        )
        if (
            raw.get("schema") != STATE_SCHEMA
            or not isinstance(raw.get("entries"), dict)
        ):
            raw = {"schema": STATE_SCHEMA, "entries": {}}
        self.state = raw

        # Stage 2G already hashed the large CSV inputs.  On first installation
        # seed the private cache from that index so Stage 2G.1 does not hash the
        # entire history a second time.  Later writes stay private because the
        # parent Analyzer process owns the global DAG cache in memory.
        if digest_path.exists():
            self.digests = ContentDigests(digest_path)
        else:
            global_digest_path = (
                self.output_root.parent
                / "Integrity"
                / "analyzer_digest_cache.json"
            )
            self.digests = ContentDigests(global_digest_path)
            self.digests.path = digest_path

    def snapshot(
        self,
        paths: Iterable[Path],
    ) -> tuple[dict[str, str], str]:
        unique: dict[str, Path] = {}
        for raw in paths:
            path = Path(raw).expanduser()
            try:
                if path.is_file():
                    resolved = path.resolve()
                    unique[str(resolved)] = resolved
            except OSError:
                continue
        files = {
            key: self.digests.digest(path)
            for key, path in sorted(unique.items())
        }
        return files, _digest_snapshot(
            files,
            analysis_version=self.analysis_version,
        )

    def previous(self, key: str) -> dict[str, Any] | None:
        entry = self.state["entries"].get(key)
        return entry if isinstance(entry, dict) else None

    def is_current(
        self,
        key: str,
        *,
        input_digest: str,
        report_path: Path,
    ) -> bool:
        entry = self.previous(key)
        return bool(
            entry
            and entry.get("status") == "ok"
            and entry.get("analysis_version") == self.analysis_version
            and entry.get("input_digest") == input_digest
            and Path(report_path).is_file()
        )

    def record_success(
        self,
        key: str,
        *,
        input_files: dict[str, str],
        input_digest: str,
        report_path: Path,
        bootstrapped: bool = False,
    ) -> None:
        self.state["entries"][key] = {
            "status": "ok",
            "analysis_version": self.analysis_version,
            "input_files": input_files,
            "input_digest": input_digest,
            "report_path": str(Path(report_path).resolve()),
            "bootstrapped": bool(bootstrapped),
        }

    def record_failure(
        self,
        key: str,
        *,
        input_files: dict[str, str],
        input_digest: str,
        failure: dict[str, str],
    ) -> None:
        self.state["entries"][key] = {
            "status": "failed",
            "analysis_version": self.analysis_version,
            "input_files": input_files,
            "input_digest": input_digest,
            "failure": failure,
        }

    def remove_absent(self, active_keys: set[str]) -> int:
        stale = [
            key
            for key in self.state["entries"]
            if key not in active_keys
        ]
        for key in stale:
            del self.state["entries"][key]
        return len(stale)

    def flush(self) -> None:
        _atomic_json(self.state_path, self.state)
        self.digests.save()


