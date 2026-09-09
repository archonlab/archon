"""Read-only Mutation Analyzer projection and explicit single-report runner for OL2-MUTATIONS2."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from Tools.archon_runtime_python import runtime_python_command, runtime_python_environment

from Analyzer_next.core.mutation.constants import REPORT_SCHEMA
from Analyzer_next.execution.observer.shell2.mutations1.model import MutationRecord
from Analyzer_next.execution.observer.shell2.mutations2.model import (
    MutationAnalysisRunOutcome,
    MutationAnalysisView,
    MutationMetricDelta,
)

_CORE_METRICS = (
    "total_living_mass",
    "objects",
    "stability_index",
    "evo_extinction_risk",
    "knowledge_score",
    "feedback_score",
    "emergence_score",
    "validation_quality",
    "morphology_change_rate",
    "total_drift",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return int(parsed) if parsed.is_integer() else parsed


class JSONMutationAnalysisReader:
    """Strict read-only projection of existing per-mutation Analyzer reports."""

    def __init__(self, output_root: str | Path) -> None:
        self.output_root = Path(output_root).expanduser().resolve()
        self._cache: dict[str, tuple[int, int, MutationAnalysisView]] = {}

    def report_path(self, record: MutationRecord) -> Path:
        return (
            self.output_root
            / f"rule_{record.parent_rule_id:05d}"
            / record.mutation_id
            / "mutation_report.json"
        )

    def has_report(self, record: MutationRecord) -> bool:
        return self.report_path(record).is_file()

    def read(self, record: MutationRecord) -> MutationAnalysisView | None:
        path = self.report_path(record)
        try:
            stat = path.stat()
        except OSError:
            return None
        key = str(path)
        cached = self._cache.get(key)
        signature = (int(stat.st_mtime_ns), int(stat.st_size))
        if cached and cached[:2] == signature:
            return cached[2]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid mutation analysis report: {path}: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("schema") != REPORT_SCHEMA:
            raise ValueError(f"Unsupported mutation analysis report: {path}")
        if str(payload.get("mutation_id") or "") != record.mutation_id:
            raise ValueError("Mutation analysis identity mismatch")
        try:
            parent = int(str(payload.get("parent_rule_id")))
        except (TypeError, ValueError) as exc:
            raise ValueError("Mutation analysis parent rule is invalid") from exc
        if parent != record.parent_rule_id:
            raise ValueError("Mutation analysis parent rule mismatch")

        confidence = payload.get("comparison_confidence") if isinstance(payload.get("comparison_confidence"), dict) else {}
        baseline = payload.get("baseline_match") if isinstance(payload.get("baseline_match"), dict) else {}
        effect = payload.get("effect_interpretation") if isinstance(payload.get("effect_interpretation"), dict) else {}
        horizon = payload.get("comparison_horizon") if isinstance(payload.get("comparison_horizon"), dict) else {}
        lifecycle = payload.get("perturbation_lifecycle_reconciliation") if isinstance(payload.get("perturbation_lifecycle_reconciliation"), dict) else {}
        control = payload.get("required_control") if isinstance(payload.get("required_control"), dict) else None
        delta_root = payload.get("metric_delta") if isinstance(payload.get("metric_delta"), dict) else {}
        tail = delta_root.get("tail_median") if isinstance(delta_root.get("tail_median"), dict) else {}

        metric_rows: list[MutationMetricDelta] = []
        for metric in _CORE_METRICS:
            row = tail.get(metric)
            if not isinstance(row, dict):
                continue
            rel = row.get("relative_delta")
            metric_rows.append(
                MutationMetricDelta(
                    metric=metric,
                    baseline=_number(row.get("baseline")),
                    mutant=_number(row.get("mutant")),
                    absolute_delta=_number(row.get("absolute_delta")),
                    relative_delta=(float(rel) if isinstance(rel, (int, float)) else None),
                )
            )

        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        markdown_value = output.get("markdown")
        markdown = Path(str(markdown_value)).expanduser().resolve() if markdown_value else path.with_suffix(".md")
        if not markdown.is_file():
            markdown = None

        view = MutationAnalysisView(
            mutation_id=record.mutation_id,
            parent_rule_id=record.parent_rule_id,
            generated=str(payload.get("generated") or "—"),
            effect_primary=str(effect.get("primary") or "unknown"),
            effect_labels=tuple(str(item) for item in effect.get("labels", ()) if str(item)),
            evidence=tuple(str(item) for item in effect.get("evidence", ()) if str(item)),
            confidence_grade=str(confidence.get("grade") or "MISSING"),
            confidence_score=_safe_float(confidence.get("score"), -1.0),
            confidence_reasons=tuple(str(item) for item in confidence.get("reasons", ()) if str(item)),
            baseline_match_type=str(baseline.get("match_type") or "missing"),
            baseline_same_seed=(baseline.get("same_seed") if isinstance(baseline.get("same_seed"), bool) else None),
            baseline_coverage=_safe_float(baseline.get("coverage_ratio"), 0.0),
            comparison_end_tick=_safe_int(horizon.get("end_tick")),
            lifecycle_status=str(lifecycle.get("verification_status") or "unavailable"),
            required_control=control is not None,
            required_control_reason=(str(control.get("reason")) if control and control.get("reason") else None),
            required_control_target_ticks=(_safe_int(control.get("target_ticks")) if control else None),
            required_control_sample_interval=(_safe_int(control.get("sample_interval")) if control else None),
            warnings=tuple(str(item) for item in payload.get("warnings", ()) if str(item)),
            metric_deltas=tuple(metric_rows),
            report_json=path.resolve(),
            report_markdown=markdown,
        )
        self._cache[key] = (signature[0], signature[1], view)
        return view


class MutationAnalysisProcessRunner:
    """Explicit user-action runner for one existing scientific mutation report."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).expanduser().resolve()

    def command_for(self, record: MutationRecord) -> tuple[str, ...]:
        return (
            *runtime_python_command(self.project_root),
            str(self.project_root / "Analyzer_next/cli/mutation_report_one.py"),
            "--manifest",
            str(record.manifest_file.resolve()),
        )

    def analyze(self, record: MutationRecord) -> MutationAnalysisRunOutcome:
        proc = subprocess.run(
            self.command_for(record),
            cwd=self.project_root,
            env=runtime_python_environment(self.project_root),
            text=True,
            capture_output=True,
            check=False,
        )
        return MutationAnalysisRunOutcome(
            exit_code=int(proc.returncode),
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )


__all__ = ["JSONMutationAnalysisReader", "MutationAnalysisProcessRunner"]
