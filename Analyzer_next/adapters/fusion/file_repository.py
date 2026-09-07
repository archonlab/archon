"""Filesystem source and artifact sink implementing Fusion ports."""
from __future__ import annotations

import json

from Analyzer_next.core.fusion.contracts import (
    FusionInputs,
    FusionPaths,
    FusionRunResult,
)


class FileFusionSource:
    def load(self, paths: FusionPaths) -> FusionInputs:
        compact = paths.results_dir / "morphological_events.json"
        report = paths.results_dir / "morphological_event_report.json"
        if compact.exists():
            return FusionInputs(
                event_source=json.loads(compact.read_text(encoding="utf-8"))
            )
        if report.exists():
            raw = json.loads(report.read_text(encoding="utf-8"))
            converted = {
                "schema": "converted_from_event_report",
                "results_dir": raw.get("results_dir"),
                "rules_analyzed": raw.get("rules_analyzed"),
                "events": {},
            }
            for item in raw.get("rules", []):
                best_run = item.get("best_run", {})
                rule_id = best_run.get("rule_id")
                if rule_id:
                    converted["events"][rule_id] = {
                        "summary": best_run.get("event_summary", {}),
                        "events": best_run.get("events", []),
                        "sparklines": best_run.get("sparklines", {}),
                    }
            return FusionInputs(event_source=converted)
        raise FileNotFoundError(
            "Cannot find morphological_events.json or "
            f"morphological_event_report.json in {paths.results_dir}"
        )


class FileFusionArtifactRepository:
    def save(self, paths: FusionPaths, result: FusionRunResult) -> None:
        paths.results_dir.mkdir(parents=True, exist_ok=True)
        for name, content in result.artifacts.items():
            (paths.results_dir / name).write_text(content, encoding="utf-8")

