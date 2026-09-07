"""Filesystem repository for Prediction Validation Engine v2.3."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from Analyzer_next.core.prediction_validation.contracts import (
    PredictionValidationInputs,
    PredictionValidationPaths,
    PredictionValidationRunResult,
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rule_aliases(atlas_path: Path) -> dict[str, str]:
    candidates = [
        atlas_path.parent / "duplicate_rule_aliases.json",
        atlas_path.parent.parent / "Knowledge" / "duplicate_rule_aliases.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = load_json(path)
        except Exception:
            continue
        raw = payload.get("aliases", {}) if isinstance(payload, dict) else {}
        if not isinstance(raw, dict):
            continue
        aliases: dict[str, str] = {}
        for old, new in raw.items():
            old_id = str(old).strip()
            new_id = str(new).strip()
            if old_id.isdigit():
                old_id = old_id.zfill(5)
            if new_id.isdigit():
                new_id = new_id.zfill(5)
            if old_id and new_id and old_id != new_id:
                aliases[old_id] = new_id
        return aliases
    return {}


class FilePredictionValidationRepository:
    def load(self, paths: PredictionValidationPaths) -> PredictionValidationInputs:
        prediction_payload = load_json(paths.predictions)
        return PredictionValidationInputs(
            atlas=load_json(paths.atlas),
            predictions=prediction_payload.get("predictions", []),
            aliases=load_rule_aliases(paths.atlas),
            generated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def save(
        self,
        paths: PredictionValidationPaths,
        result: PredictionValidationRunResult,
    ) -> None:
        paths.output_markdown.write_text(result.markdown, encoding="utf-8")
        paths.output_json.write_text(
            json.dumps(result.payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


__all__ = ["FilePredictionValidationRepository", "load_json", "load_rule_aliases"]
