"""Filesystem repository for persistent Prediction Engine v2."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from Analyzer_next.core.prediction_registry.contracts import (
    PredictionRegistryInputs,
    PredictionRegistryPaths,
    PredictionRegistryRunResult,
)


def load_json(path: Path, default: Any = None) -> Any:
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_atomic(path: Path, payload: Any, *, pretty: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2 if pretty else None,
                separators=None if pretty else (",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def load_principles(
    explicit: Path | None,
    analysis_root: Path,
    kb: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if isinstance(kb.get("principles"), dict) and kb["principles"]:
        return {
            str(pid): item
            for pid, item in kb["principles"].items()
            if isinstance(item, dict)
        }

    path = explicit or analysis_root / "general_principles.json"
    payload = load_json(path, {})
    return {
        str(item.get("id")): item
        for item in payload.get("principles", [])
        if isinstance(item, dict) and item.get("id")
    }


def load_validations(
    analysis_root: Path,
    kb: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    payload = load_json(analysis_root / "validation_report.json", {})
    if not payload:
        payload = load_json(analysis_root / "validation_results.json", {})

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("results")
            or payload.get("predictions")
            or payload.get("validation")
            or []
        )
    else:
        items = []

    out = {
        str(item.get("id")): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }

    if not out and isinstance(kb.get("validations"), dict):
        out = {
            str(pid): item
            for pid, item in kb["validations"].items()
            if isinstance(item, dict)
        }
    return out


class FilePredictionRegistryRepository:
    def load(self, paths: PredictionRegistryPaths) -> PredictionRegistryInputs:
        knowledge_base = load_json(paths.knowledge_base, {})
        return PredictionRegistryInputs(
            atlas=load_json(paths.atlas, {}),
            knowledge_base=knowledge_base,
            principles=load_principles(
                paths.principles,
                paths.analysis_root,
                knowledge_base,
            ),
            validations=load_validations(paths.analysis_root, knowledge_base),
            database=load_json(paths.database_json, {}),
        )

    def save(
        self,
        paths: PredictionRegistryPaths,
        result: PredictionRegistryRunResult,
    ) -> None:
        write_json_atomic(paths.database_json, result.database, pretty=True)
        paths.database_markdown.write_text(
            result.database_markdown,
            encoding="utf-8",
        )
        write_json_atomic(paths.output_json, result.compatibility, pretty=True)
        paths.output_markdown.write_text(result.output_markdown, encoding="utf-8")


__all__ = [
    "FilePredictionRegistryRepository",
    "load_json",
    "load_principles",
    "load_validations",
    "write_json_atomic",
]
