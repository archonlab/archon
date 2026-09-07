"""Filesystem repository for the modular Knowledge Base engine."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from Analyzer_next.adapters.scientific_data.file_repository import (
    FileScientificDataRepository,
)
from Analyzer_next.adapters.scientific_data.io import (
    load_json,
    write_json_atomic,
)
from Analyzer_next.core.knowledge_base.contracts import (
    KnowledgeBaseInputs,
    KnowledgeBasePaths,
    KnowledgeBaseRunResult,
)
from Analyzer_next.core.scientific_data.contracts import (
    ScientificDataPaths,
    ScientificDataRepository,
)
from Analyzer_next.core.scientific_data.ids import normalize_rule_id


def _load_aliases(knowledge_root: Path) -> dict[str, str]:
    payload = load_json(knowledge_root / "duplicate_rule_aliases.json", {})
    raw = payload.get("aliases", {}) if isinstance(payload, dict) else {}
    aliases: dict[str, str] = {}
    if not isinstance(raw, dict):
        return aliases
    for old, new in raw.items():
        old_id = normalize_rule_id(old)
        new_id = normalize_rule_id(new)
        if old_id and new_id and old_id != new_id:
            aliases[old_id] = new_id
    return aliases


def _current_predictions(
    knowledge_root: Path,
    fallback: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    payload = load_json(knowledge_root / "prediction_database.json", {})
    raw = payload.get("predictions", {}) if isinstance(payload, dict) else {}
    if isinstance(raw, list):
        return {
            str(item.get("id")): item
            for item in raw
            if isinstance(item, dict) and item.get("id")
        }
    if isinstance(raw, dict) and raw:
        return {
            str(prediction_id): item
            for prediction_id, item in raw.items()
            if isinstance(item, dict)
        }
    return dict(fallback)


def _current_validations(
    analysis_root: Path,
    fallback: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    payload = load_json(analysis_root / "validation_report.json", {})
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
    current = {
        str(item.get("id")): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }
    return current or dict(fallback)


def _write_text_if_changed(path: Path, text: str) -> bool:
    if (
        path.exists()
        and path.read_text(encoding="utf-8", errors="replace") == text
    ):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _write_json_if_changed(
    path: Path,
    payload: dict[str, Any],
    *,
    pretty: bool,
) -> bool:
    if path.exists() and load_json(path, None) == payload:
        return False
    write_json_atomic(path, payload, pretty=pretty)
    return True


class FileKnowledgeBaseRepository:
    def __init__(
        self,
        scientific_repository: ScientificDataRepository | None = None,
    ) -> None:
        self._scientific_repository = (
            scientific_repository or FileScientificDataRepository()
        )

    def load(self, paths: KnowledgeBasePaths) -> KnowledgeBaseInputs:
        scientific_data = self._scientific_repository.load(
            ScientificDataPaths.create(
                results_root=paths.results_root,
                analysis_root=paths.analysis_root,
                knowledge_root=paths.knowledge_root,
                atlas_path=paths.atlas_path,
            )
        )
        return KnowledgeBaseInputs(
            scientific_data=scientific_data,
            aliases=_load_aliases(paths.knowledge_root),
            predictions=_current_predictions(
                paths.knowledge_root,
                scientific_data.predictions,
            ),
            validations=_current_validations(
                paths.analysis_root,
                scientific_data.validations,
            ),
            previous_knowledge_base=load_json(paths.output_json, {}),
            previous_integrity=load_json(paths.integrity_json, {}),
        )

    def save(
        self,
        paths: KnowledgeBasePaths,
        result: KnowledgeBaseRunResult,
    ) -> None:
        _write_json_if_changed(
            paths.output_json,
            result.knowledge_base,
            pretty=paths.pretty_json,
        )
        _write_json_if_changed(
            paths.integrity_json,
            result.integrity,
            pretty=True,
        )
        _write_text_if_changed(
            paths.output_markdown,
            result.report_markdown,
        )
