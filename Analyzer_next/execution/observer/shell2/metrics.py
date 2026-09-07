"""Frozen scientific metric bindings consumed by the SHELL1 mock store."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REGISTRY = (
    PROJECT_ROOT
    / "Documentation/ObserverLauncher2/observer_launcher_2_0_metric_registry.json"
)


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: str
    label: str
    source: str
    kind: str
    value_format: str
    secondary_source: str | None = None


@dataclass(frozen=True, slots=True)
class MetricSample:
    definition: MetricDefinition
    value: float
    previous_value: float
    history: tuple[float, ...]
    unit: str
    secondary_value: float | None = None

    @property
    def delta(self) -> float:
        return self.value - self.previous_value


def load_default_metric_definitions(
    registry_path: Path = DEFAULT_REGISTRY,
) -> tuple[MetricDefinition, ...]:
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "archon_observer_launcher_2_metric_registry_v1":
        raise ValueError("unsupported Observer Launcher 2 metric registry")
    if payload.get("source_contract", {}).get("scientific_access") != "read_only":
        raise ValueError("metric registry must be read-only")
    definitions = []
    for row in payload.get("default_cards", []):
        if row.get("kind") != "persisted":
            raise ValueError(f"default metric is not persisted: {row}")
        source = str(row.get("source", ""))
        if not source.startswith("samples."):
            raise ValueError(f"default metric source is not canonical: {source}")
        definitions.append(
            MetricDefinition(
                metric_id=str(row["id"]),
                label=str(row["label"]),
                source=source,
                kind=str(row["kind"]),
                value_format=str(row["format"]),
                secondary_source=(
                    str(row["secondary_source"])
                    if row.get("secondary_source")
                    else None
                ),
            )
        )
    if len(definitions) != 6:
        raise ValueError(f"six default metric cards required: {len(definitions)}")
    if len({item.metric_id for item in definitions}) != len(definitions):
        raise ValueError("duplicate default metric identifier")
    return tuple(definitions)


def format_metric(sample: MetricSample) -> str:
    if sample.definition.value_format == "integer":
        return f"{int(round(sample.value)):,}"
    if sample.definition.value_format == "score_0_1":
        return f"{sample.value:.3f}"
    raise ValueError(f"unsupported metric format: {sample.definition.value_format}")


def format_delta(sample: MetricSample) -> str:
    if sample.definition.value_format == "integer":
        value = int(round(sample.delta))
        return f"{value:+,} vs previous"
    return f"{sample.delta:+.3f} vs previous"
