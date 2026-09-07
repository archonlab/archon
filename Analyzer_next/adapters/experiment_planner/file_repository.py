"""Filesystem repository for Experiment Planner Engine v4.4."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from Analyzer_next.core.experiment_planner.contracts import (
    ExperimentPlannerArtifact,
    ExperimentPlannerInputs,
    ExperimentPlannerPaths,
    ExperimentPlannerSaveResult,
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


def save_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def find_project_roots(kb_path: Path, out_md: Path) -> tuple[Path, Path, Path]:
    if kb_path.parent.name == "Knowledge" and kb_path.parent.parent.name == "Atlas":
        project_root = kb_path.parent.parent.parent
    else:
        project_root = out_md.parent.parent.parent
    analysis_root = project_root / "Results" / "Analysis"
    knowledge_root = project_root / "Atlas" / "Knowledge"
    return project_root.resolve(), analysis_root.resolve(), knowledge_root.resolve()


def resolve_paths(
    knowledge_base: str,
    output: str,
    *,
    validation: str | None = None,
    predictions: str | None = None,
    cohort_targets: str | None = None,
    consensus: str | None = None,
    evidence: str | None = None,
    metric_audit: str | None = None,
) -> ExperimentPlannerPaths:
    kb_path = Path(knowledge_base).expanduser().resolve()
    out_md = Path(output).expanduser()
    if not out_md.is_absolute():
        out_md = kb_path.parent / out_md
    out_md = out_md.resolve()
    _, analysis_root, knowledge_root = find_project_roots(kb_path, out_md)

    def selected(value: str | None, fallback: Path) -> Path:
        return Path(value).expanduser().resolve() if value else fallback

    return ExperimentPlannerPaths(
        knowledge_base=kb_path,
        output_markdown=out_md,
        output_json=out_md.with_suffix(".json"),
        validation_report=selected(
            validation,
            analysis_root / "validation_report.json",
        ),
        prediction_database=selected(
            predictions,
            knowledge_root / "prediction_database.json",
        ),
        cohort_targets=selected(
            cohort_targets,
            analysis_root / "cohort_targets.json",
        ),
        consensus_report=selected(
            consensus,
            analysis_root / "consensus_report.json",
        ),
        evidence_report=selected(
            evidence,
            analysis_root / "evidence_report.json",
        ),
        metric_independence_audit=selected(
            metric_audit,
            analysis_root / "Integrity" / "metric_independence_audit.json",
        ),
    )


class FileExperimentPlannerRepository:
    def load(self, paths: ExperimentPlannerPaths) -> ExperimentPlannerInputs:
        return ExperimentPlannerInputs(
            paths=paths,
            knowledge_base=load_json(paths.knowledge_base, {}),
            validation_payload=load_json(paths.validation_report, {}),
            prediction_payload=load_json(paths.prediction_database, {}),
            cohort_payload=load_json(paths.cohort_targets, {}),
            consensus_payload=load_json(paths.consensus_report, {}),
            evidence_payload=load_json(paths.evidence_report, {}),
            metric_audit=load_json(paths.metric_independence_audit, {}),
            existing_output=load_json(paths.output_json, {}),
            output_markdown_exists=paths.output_markdown.exists(),
            generated=datetime.now().isoformat(timespec="seconds"),
        )

    def save(
        self,
        paths: ExperimentPlannerPaths,
        artifact: ExperimentPlannerArtifact,
    ) -> ExperimentPlannerSaveResult:
        if artifact.changed:
            paths.output_markdown.parent.mkdir(parents=True, exist_ok=True)
            paths.output_markdown.write_text(artifact.markdown, encoding="utf-8")
            save_json(artifact.payload, paths.output_json)
        return ExperimentPlannerSaveResult(artifact=artifact, paths=paths)


__all__ = [
    "FileExperimentPlannerRepository",
    "find_project_roots",
    "load_json",
    "resolve_paths",
    "save_json",
]
