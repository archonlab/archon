"""Content-aware incremental state machine for the production Analyzer DAG."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from Analyzer_next.production.fingerprints import (
    DEFAULT_FINGERPRINT_POLICY,
    FingerprintPolicy,
    expand_files,
    snapshot_delta,
    snapshot_digest,
)


STATE_SCHEMA = 1
_CACHED_DIGEST_FIELDS = (
    "sha256",
    "semantic_sha256",
    "metadata_sha256",
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


class ContentDigests:
    """Persist fingerprints keyed by path, size, and nanosecond timestamps."""

    def __init__(
        self,
        path: Path,
        *,
        policy: FingerprintPolicy = DEFAULT_FINGERPRINT_POLICY,
    ):
        self.path = path
        self.policy = policy
        raw = _load_json(path, {"schema": STATE_SCHEMA, "files": {}})
        if raw.get("schema") != STATE_SCHEMA or not isinstance(
            raw.get("files"), dict
        ):
            raw = {"schema": STATE_SCHEMA, "files": {}}
        self.data = raw
        self.dirty = False

    def digest(self, path: Path, *, semantic: bool = False) -> str:
        path = path.resolve()
        stat = path.stat()
        key = str(path)
        previous = self.data["files"].get(key, {})
        digest_key = self.policy.cache_field(stat, semantic=semantic)
        metadata_unchanged = (
            previous.get("size") == stat.st_size
            and previous.get("mtime_ns") == stat.st_mtime_ns
            and previous.get("ctime_ns") == stat.st_ctime_ns
        )
        if metadata_unchanged and isinstance(previous.get(digest_key), str):
            return previous[digest_key]

        fingerprint = self.policy.fingerprint(
            path,
            stat,
            semantic=semantic,
        )
        current = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns,
            "digest_mode": fingerprint.mode,
        }
        if metadata_unchanged:
            current.update({
                name: previous[name]
                for name in _CACHED_DIGEST_FIELDS
                if isinstance(previous.get(name), str)
            })
        current[fingerprint.cache_field] = fingerprint.value
        self.data["files"][key] = current
        self.dirty = True
        return fingerprint.value

    def snapshot(
        self,
        paths: Iterable[Path],
        *,
        semantic_paths: set[Path] | None = None,
    ) -> dict[str, str]:
        semantic_paths = semantic_paths or set()
        return {
            str(path): self.digest(path, semantic=path in semantic_paths)
            for path in expand_files(paths)
        }

    def save(self) -> None:
        if self.dirty:
            _atomic_json(self.path, self.data)
            self.dirty = False


@dataclass(frozen=True)
class Decision:
    current: bool
    input_files: dict[str, str]
    input_digest: str
    output_files: dict[str, str]
    output_digest: str
    delta: dict[str, int]


class AnalyzerDAG:
    """Persist and compare one dependency snapshot per Analyzer step."""

    def __init__(
        self,
        analysis_dir: Path,
        *,
        semantic_paths: Iterable[Path] = (),
        fingerprint_policy: FingerprintPolicy = DEFAULT_FINGERPRINT_POLICY,
    ):
        integrity = analysis_dir / "Integrity"
        self.state_path = integrity / "analyzer_dag_state.json"
        self.digest_cache = ContentDigests(
            integrity / "analyzer_digest_cache.json",
            policy=fingerprint_policy,
        )
        self.semantic_paths = {
            Path(path).resolve() for path in semantic_paths
        }
        raw = _load_json(
            self.state_path,
            {"schema": STATE_SCHEMA, "steps": {}},
        )
        if raw.get("schema") != STATE_SCHEMA or not isinstance(
            raw.get("steps"), dict
        ):
            raw = {"schema": STATE_SCHEMA, "steps": {}}
        self.state = raw
        self._migrate_digest_policy(fingerprint_policy.version)

    def _snapshot(self, paths: Iterable[Path]) -> dict[str, str]:
        return self.digest_cache.snapshot(
            paths,
            semantic_paths=self.semantic_paths,
        )

    def _migrate_digest_policy(self, policy_version: int) -> None:
        """Reindex existing state once without recomputing Analyzer stages."""
        if self.state.get("digest_policy") == policy_version:
            return
        for step in self.state["steps"].values():
            for field, digest_field in (
                ("input_files", "input_digest"),
                ("output_files", "output_digest"),
            ):
                previous = step.get(field, {})
                paths = [
                    Path(path)
                    for path in previous
                    if Path(path).is_file()
                ]
                snapshot = self._snapshot(paths)
                step[field] = snapshot
                step[digest_field] = snapshot_digest(snapshot)
        self.state["digest_policy"] = policy_version
        _atomic_json(self.state_path, self.state)
        self.digest_cache.save()

    def has_step(self, key: str) -> bool:
        return key in self.state["steps"]

    def inspect(
        self,
        key: str,
        *,
        inputs: Iterable[Path],
        outputs: Iterable[Path],
    ) -> Decision:
        input_files = self._snapshot(inputs)
        output_files = self._snapshot(outputs)
        input_digest = snapshot_digest(input_files)
        output_digest = snapshot_digest(output_files)
        previous = self.state["steps"].get(key, {})
        previous_inputs = previous.get("input_files", {})
        expected_outputs = [str(Path(path).resolve()) for path in outputs]
        outputs_exist = bool(expected_outputs) and all(
            Path(path).exists() for path in expected_outputs
        )
        current = (
            outputs_exist
            and previous.get("status") == "ok"
            and previous.get("input_digest") == input_digest
            and previous.get("output_digest") == output_digest
        )
        return Decision(
            current=current,
            input_files=input_files,
            input_digest=input_digest,
            output_files=output_files,
            output_digest=output_digest,
            delta=snapshot_delta(previous_inputs, input_files),
        )

    def record(
        self,
        key: str,
        *,
        decision: Decision,
        outputs: Iterable[Path],
        status: str,
    ) -> tuple[bool, str]:
        previous = self.state["steps"].get(key, {})
        output_files = self._snapshot(outputs)
        output_digest = snapshot_digest(output_files)
        output_changed = previous.get("output_digest") != output_digest
        self.state["steps"][key] = {
            "status": status,
            "input_files": decision.input_files,
            "input_digest": decision.input_digest,
            "output_files": output_files,
            "output_digest": output_digest,
        }
        _atomic_json(self.state_path, self.state)
        self.digest_cache.save()
        return output_changed, output_digest

    def flush(self) -> None:
        self.digest_cache.save()


__all__ = ["AnalyzerDAG", "ContentDigests", "Decision", "STATE_SCHEMA"]
