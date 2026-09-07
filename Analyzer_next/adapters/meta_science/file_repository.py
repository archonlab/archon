"""Filesystem implementation of the Meta Science repository port."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from Analyzer_next.core.meta_science.contracts import (
    MetaScienceInputs,
    MetaSciencePaths,
    MetaScienceRunResult,
)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def _load_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _profile_payload(results: Path) -> dict[str, Any]:
    for name in ("observer_profiles_v31.json", "observer_profiles_v30.json"):
        candidate = results / name
        if candidate.exists():
            payload = _load_json(candidate, {})
            return payload if isinstance(payload, dict) else {}
    return {}


class FileMetaScienceRepository:
    def load(self, paths: MetaSciencePaths) -> MetaScienceInputs:
        root = paths.root
        knowledge = paths.knowledge_root
        return MetaScienceInputs(
            consensus=_load_json(root / "consensus_report.json", {}),
            consensus_database=_load_json(knowledge / "consensus_database.json", {}),
            evidence=_load_json(root / "evidence_report.json", {}),
            general_principles=_load_json(root / "general_principles.json", {}),
            research_atlas=_load_json(knowledge / "research_atlas.json", {}),
            theory_report=_load_text(root / "theory_report.md"),
            profiles=_profile_payload(paths.results),
            knowledge_base=_load_json(knowledge / "knowledge_base.json", {}),
            prediction_database=_load_json(knowledge / "prediction_database.json", {}),
            validation_report=_load_json(root / "validation_report.json", {}),
            experiment_plan=_load_json(root / "experiment_plan.json", {}),
            knowledge_integrity=_load_json(knowledge / "knowledge_base_integrity.json", {}),
            reference_controls=_load_json(knowledge / "reference_control_registry.json", {}),
            history=_load_json(paths.history, {}),
        )

    def save(self, paths: MetaSciencePaths, result: MetaScienceRunResult) -> None:
        paths.root.mkdir(parents=True, exist_ok=True)
        paths.knowledge_root.mkdir(parents=True, exist_ok=True)
        paths.report_json.parent.mkdir(parents=True, exist_ok=True)
        paths.report_markdown.parent.mkdir(parents=True, exist_ok=True)
        paths.history.parent.mkdir(parents=True, exist_ok=True)
        paths.history.write_text(
            json.dumps(result.history, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        paths.report_json.write_text(
            json.dumps(result.report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        paths.report_markdown.write_text(result.report_markdown, encoding="utf-8")
