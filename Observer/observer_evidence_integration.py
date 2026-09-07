#!/usr/bin/env python3
"""Live Observer adapter for ARCHON Evidence Framework v1.

This module translates the current LifeObserver snapshot into explicit,
traceable Observation and Evidence objects, runs the integrated evidence
pipeline, exports the result, and optionally maintains an in-memory timeline
across checkpoints.

The adapter is intentionally conservative. It uses only metrics already
computed by LifeObserver and does not modify cellular-automaton dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

try:
    from .evidence_models import (
        Evidence,
        EvidenceCategory,
        EvidenceGroup,
        EvidenceQuality,
        Observation,
        Provenance,
        SensorType,
    )
    from .observer_evidence import EvidenceCollector
    from .observer_evidence_export import (
        EvidenceExportConfig,
        EvidenceExportResult,
        EvidenceExporter,
    )
    from .observer_evidence_pipeline import (
        EvidencePipeline,
        EvidencePipelineResult,
    )
    from .observer_evidence_timeline import (
        EvidenceTimeline,
        TimelineCheckpoint,
        build_evidence_timeline,
    )
    from .observer_life_evidence_alignment import (
        LifeEvidenceAlignment,
        build_life_evidence_alignment,
    )
except ImportError:
    from evidence_models import (
        Evidence,
        EvidenceCategory,
        EvidenceGroup,
        EvidenceQuality,
        Observation,
        Provenance,
        SensorType,
    )
    from observer_evidence import EvidenceCollector
    from observer_evidence_export import (
        EvidenceExportConfig,
        EvidenceExportResult,
        EvidenceExporter,
    )
    from observer_evidence_pipeline import (
        EvidencePipeline,
        EvidencePipelineResult,
    )
    from observer_evidence_timeline import (
        EvidenceTimeline,
        TimelineCheckpoint,
        build_evidence_timeline,
    )
    from observer_life_evidence_alignment import (
        LifeEvidenceAlignment,
        build_life_evidence_alignment,
    )


OBSERVER_EVIDENCE_INTEGRATION_VERSION = "1.0.0"


class EvidenceIntegrationError(RuntimeError):
    """Raised when a live Observer snapshot cannot be converted or exported."""


@dataclass(frozen=True, slots=True)
class EvidenceCheckpointResult:
    """Artifacts produced by one live checkpoint."""

    tick: int
    pipeline_result: EvidencePipelineResult
    export_result: EvidenceExportResult
    timeline: EvidenceTimeline | None
    timeline_path: str | None
    life_evidence_alignment: LifeEvidenceAlignment
    life_evidence_alignment_path: str


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _quality(confidence: float) -> EvidenceQuality:
    if confidence >= 0.90:
        return EvidenceQuality.VERY_HIGH
    if confidence >= 0.75:
        return EvidenceQuality.HIGH
    if confidence >= 0.55:
        return EvidenceQuality.MEDIUM
    if confidence >= 0.35:
        return EvidenceQuality.LOW
    return EvidenceQuality.VERY_LOW


class LiveObserverEvidenceSession:
    """Run-local bridge between LifeObserver and Evidence Framework."""

    def __init__(
        self,
        *,
        world_id: str,
        run_id: str,
        observer_version: str,
        output_root: str | Path,
        enable_timeline: bool = True,
    ) -> None:
        self.world_id = str(world_id)
        self.run_id = str(run_id)
        self.observer_version = str(observer_version)
        self.output_root = Path(output_root)
        self.enable_timeline = bool(enable_timeline)
        self.pipeline = EvidencePipeline()
        self.exporter = EvidenceExporter(
            EvidenceExportConfig(overwrite=True)
        )
        self.checkpoints: list[TimelineCheckpoint] = []
        self.last_result: EvidenceCheckpointResult | None = None

    def checkpoint(
        self,
        *,
        current: Mapping[str, Any],
        tick: int,
        rule_record: Mapping[str, Any],
        reason: str,
    ) -> EvidenceCheckpointResult:
        collector = self._collector_from_snapshot(
            current=current,
            tick=tick,
            rule_record=rule_record,
        )
        pipeline_result = self.pipeline.run(
            collector,
            metadata={
                "integration_version": OBSERVER_EVIDENCE_INTEGRATION_VERSION,
                "checkpoint_reason": reason,
                "checkpoint_tick": int(tick),
                "source_observer": "LifeObserver",
            },
        )
        export_result = self.exporter.export_pipeline_result(
            pipeline_result,
            output_root=self.output_root,
            extra_manifest_metadata={
                "checkpoint_reason": reason,
                "checkpoint_tick": int(tick),
            },
        )
        alignment = build_life_evidence_alignment(
            current=current,
            report=pipeline_result.report,
            tick=tick,
        )
        alignment_file = (
            Path(export_result.export_dir)
            / "life_evidence_alignment.json"
        )
        alignment_file.write_text(
            alignment.to_json(indent=2) + "\n",
            encoding="utf-8",
        )

        timeline = None
        timeline_path = None
        if self.enable_timeline:
            checkpoint = TimelineCheckpoint(
                tick=int(tick),
                report=pipeline_result.report,
                label=reason,
                metadata={"reason": reason},
            )
            self.checkpoints = [
                item for item in self.checkpoints if item.tick != int(tick)
            ]
            self.checkpoints.append(checkpoint)
            self.checkpoints.sort(key=lambda item: item.tick)

            timeline = build_evidence_timeline(
                tuple(self.checkpoints),
                metadata={
                    "integration_version": OBSERVER_EVIDENCE_INTEGRATION_VERSION,
                },
            )
            timeline_file = Path(export_result.export_dir) / "evidence_timeline.json"
            timeline_file.write_text(
                timeline.to_json(indent=2) + "\n",
                encoding="utf-8",
            )
            timeline_path = str(timeline_file)

        result = EvidenceCheckpointResult(
            tick=int(tick),
            pipeline_result=pipeline_result,
            export_result=export_result,
            timeline=timeline,
            timeline_path=timeline_path,
            life_evidence_alignment=alignment,
            life_evidence_alignment_path=str(alignment_file),
        )
        self.last_result = result
        return result

    def _collector_from_snapshot(
        self,
        *,
        current: Mapping[str, Any],
        tick: int,
        rule_record: Mapping[str, Any],
    ) -> EvidenceCollector:
        collector = EvidenceCollector(
            world_id=self.world_id,
            run_id=self.run_id,
            observer_version=self.observer_version,
            module_name="observer_evidence_integration",
            metadata={
                "rule_id": rule_record.get("rule_id"),
                "score": rule_record.get("score"),
                "source": rule_record.get("source"),
            },
        )

        specs = self._observation_specs(current)
        observations: dict[str, Observation] = {}

        for spec in specs:
            observation_id = _stable_id(
                "OBS",
                self.world_id,
                self.run_id,
                spec["name"],
            )
            confidence = _clamp(spec["confidence"], 0.5)
            observation = Observation(
                sensor=spec["sensor"],
                category=spec["category"],
                name=spec["name"],
                value=spec["value"],
                confidence=confidence,
                tick=int(tick),
                quality=_quality(confidence),
                description=spec["description"],
                units=spec.get("units"),
                world_id=self.world_id,
                run_id=self.run_id,
                details=spec.get("details", {}),
                provenance=Provenance(
                    module="observer_evidence_integration",
                    algorithm=spec.get("algorithm", "snapshot_adapter"),
                    version=OBSERVER_EVIDENCE_INTEGRATION_VERSION,
                    source_ids=(),
                    metadata={"metric_key": spec.get("metric_key", spec["name"])},
                ),
                observation_id=observation_id,
            )
            collector._register_unique(
                collector._observations,
                observation.observation_id,
                observation,
                "observation",
            )
            observations[spec["name"]] = observation

        evidence_specs = self._evidence_specs(current)
        evidence_items: dict[str, Evidence] = {}
        for spec in evidence_specs:
            source_names = tuple(spec["observations"])
            source_ids = tuple(
                observations[name].observation_id
                for name in source_names
                if name in observations
            )
            if not source_ids:
                continue

            evidence_id = _stable_id(
                "EVD",
                self.world_id,
                self.run_id,
                spec["key"],
            )
            confidence = _clamp(spec["confidence"], 0.5)
            evidence = Evidence(
                category=spec["category"],
                title=spec["title"],
                description=spec["description"],
                observation_ids=source_ids,
                confidence=confidence,
                quality=_quality(confidence),
                limitations=tuple(spec.get("limitations", ())),
                tags=tuple(spec.get("tags", ())),
                provenance=Provenance(
                    module="observer_evidence_integration",
                    algorithm=spec.get("algorithm", "snapshot_evidence_adapter"),
                    version=OBSERVER_EVIDENCE_INTEGRATION_VERSION,
                    source_ids=source_ids,
                    metadata={"evidence_key": spec["key"]},
                ),
                evidence_id=evidence_id,
            )
            collector._register_unique(
                collector._evidence,
                evidence.evidence_id,
                evidence,
                "evidence",
            )
            evidence_items[spec["key"]] = evidence

        group_specs = (
            ("identity_continuity", EvidenceCategory.IDENTITY),
            ("morphology_structure", EvidenceCategory.MORPHOLOGY),
            ("adaptive_regulation", EvidenceCategory.ADAPTATION),
            ("memory_information", EvidenceCategory.MEMORY),
            ("population_dynamics", EvidenceCategory.DYNAMICS),
        )
        for key, category in group_specs:
            ids = tuple(
                item.evidence_id
                for item in evidence_items.values()
                if item.category is category
            )
            if not ids:
                continue
            group = EvidenceGroup(
                name=key.replace("_", " ").title(),
                description=(
                    "Potentially correlated evidence generated from the same "
                    "live Observer metric family."
                ),
                evidence_ids=ids,
                independence_key=key,
                category=category,
                group_id=_stable_id(
                    "GRP",
                    self.world_id,
                    self.run_id,
                    key,
                ),
            )
            collector._register_unique(
                collector._groups,
                group.group_id,
                group,
                "group",
            )

        return collector

    @staticmethod
    def _observation_specs(current: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
        val_conf = _clamp(current.get("validation_quality"), 0.55)
        sensor_conf = max(0.35, val_conf)

        return (
            {
                "sensor": SensorType.IDENTITY,
                "category": EvidenceCategory.IDENTITY,
                "name": "identity_persistence",
                "value": _clamp(current.get("identity_persistence")),
                "confidence": sensor_conf,
                "description": "Mean persistence of tracked organizational identity.",
                "metric_key": "identity_persistence",
            },
            {
                "sensor": SensorType.ECOSYSTEM,
                "category": EvidenceCategory.STABILITY,
                "name": "ecosystem_stability",
                "value": _clamp(current.get("stability_index")),
                "confidence": sensor_conf,
                "description": "Rolling stability of population and living mass.",
                "metric_key": "stability_index",
            },
            {
                "sensor": SensorType.MORPHOLOGY,
                "category": EvidenceCategory.MORPHOLOGY,
                "name": "morphology_symmetry",
                "value": _clamp(current.get("morphology_symmetry")),
                "confidence": sensor_conf,
                "description": "Symmetry of the observed living morphology.",
            },
            {
                "sensor": SensorType.MORPHOLOGY,
                "category": EvidenceCategory.MORPHOLOGY,
                "name": "morphology_change_rate",
                "value": _clamp(current.get("morphology_change_rate")),
                "confidence": sensor_conf,
                "description": "Rate of morphological change between samples.",
            },
            {
                "sensor": SensorType.MORPHOLOGY,
                "category": EvidenceCategory.MORPHOLOGY,
                "name": "morphology_lattice_score",
                "value": _clamp(current.get("morphology_lattice_score")),
                "confidence": sensor_conf,
                "description": "Degree of lattice-like or crystalline organization.",
            },
            {
                "sensor": SensorType.EVOLUTION,
                "category": EvidenceCategory.ADAPTATION,
                "name": "evolutionary_adaptation",
                "value": _clamp(current.get("evo_adapt")),
                "confidence": sensor_conf,
                "description": "Observer proxy for adaptation under evolutionary pressure.",
            },
            {
                "sensor": SensorType.EVOLUTION,
                "category": EvidenceCategory.REPAIR,
                "name": "evolutionary_recovery",
                "value": _clamp(current.get("evo_recovery")),
                "confidence": sensor_conf,
                "description": "Observed recovery following ecological pressure.",
            },
            {
                "sensor": SensorType.MEMORY,
                "category": EvidenceCategory.MEMORY,
                "name": "knowledge_memory",
                "value": _clamp(current.get("knowledge_memory")),
                "confidence": sensor_conf,
                "description": "Persistence of useful information within tracked families.",
            },
            {
                "sensor": SensorType.MEMORY,
                "category": EvidenceCategory.INFORMATION,
                "name": "information_survival",
                "value": _clamp(current.get("information_survival")),
                "confidence": sensor_conf,
                "description": "Survival of organizational information through time or collapse.",
            },
            {
                "sensor": SensorType.LINEAGE,
                "category": EvidenceCategory.REPRODUCTION,
                "name": "lineage_births",
                "value": int(current.get("demo_born_total", 0) or 0),
                "confidence": sensor_conf,
                "description": "Total tracked colony births.",
                "units": "colonies",
            },
            {
                "sensor": SensorType.LINEAGE,
                "category": EvidenceCategory.REPRODUCTION,
                "name": "deepest_generation",
                "value": int(current.get("deepest_generation", 0) or 0),
                "confidence": sensor_conf,
                "description": "Deepest tracked lineage generation.",
                "units": "generations",
            },
            {
                "sensor": SensorType.DYNAMICS,
                "category": EvidenceCategory.DYNAMICS,
                "name": "changed_cells",
                "value": int(current.get("changed", 0) or 0),
                "confidence": sensor_conf,
                "description": "Cells changing in the current sampled interval.",
                "units": "cells",
            },
            {
                "sensor": SensorType.ECOSYSTEM,
                "category": EvidenceCategory.BOUNDED_ORGANIZATION,
                "name": "dominance_ratio",
                "value": _clamp(current.get("dominance_ratio")),
                "confidence": sensor_conf,
                "description": "Share of living mass concentrated in the largest colony.",
            },
            {
                "sensor": SensorType.EMERGENCE,
                "category": EvidenceCategory.OTHER,
                "name": "legacy_emergence_score",
                "value": _clamp(current.get("emergence_score")),
                "confidence": val_conf,
                "description": "Legacy emergence score retained for calibration comparison.",
            },
            {
                "sensor": SensorType.VALIDATION,
                "category": EvidenceCategory.VALIDATION,
                "name": "validation_quality",
                "value": val_conf,
                "confidence": max(0.50, val_conf),
                "description": "Internal quality estimate of the legacy Observer verdict.",
            },
        )

    @staticmethod
    def _evidence_specs(current: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
        identity = _clamp(current.get("identity_persistence"))
        stability = _clamp(current.get("stability_index"))
        lattice = _clamp(current.get("morphology_lattice_score"))
        change = _clamp(current.get("morphology_change_rate"))
        adapt = _clamp(current.get("evo_adapt"))
        recovery = _clamp(current.get("evo_recovery"))
        memory = max(
            _clamp(current.get("knowledge_memory")),
            _clamp(current.get("information_survival")),
        )
        births = int(current.get("demo_born_total", 0) or 0)
        generation = int(current.get("deepest_generation", 0) or 0)
        changed = int(current.get("changed", 0) or 0)
        val = max(0.35, _clamp(current.get("validation_quality"), 0.55))

        return (
            {
                "key": "persistent_identity",
                "category": EvidenceCategory.IDENTITY,
                "title": "Persistent identity",
                "description": "Tracked organization maintains continuity through time.",
                "observations": ("identity_persistence",),
                "confidence": identity * val,
                "tags": ("persistent",) if identity >= 0.55 else ("unstable",),
                "limitations": ("Identity is inferred from probabilistic tracking.",),
            },
            {
                "key": "persistent_stability",
                "category": EvidenceCategory.STABILITY,
                "title": "Persistent ecosystem stability",
                "description": "Population and mass remain comparatively stable.",
                "observations": ("ecosystem_stability",),
                "confidence": stability * val,
                "tags": ("persistent",) if stability >= 0.55 else ("unstable",),
            },
            {
                "key": "crystalline_morphology",
                "category": EvidenceCategory.MORPHOLOGY,
                "title": "Crystalline morphology",
                "description": "Morphology exhibits lattice-like order.",
                "observations": (
                    "morphology_lattice_score",
                    "morphology_symmetry",
                ),
                "confidence": lattice * val,
                "tags": ("crystalline",) if lattice >= 0.55 else ("non_crystalline",),
            },
            {
                "key": "morphological_plasticity",
                "category": EvidenceCategory.MORPHOLOGY,
                "title": "Morphological plasticity",
                "description": "The organization changes form rather than remaining rigid.",
                "observations": ("morphology_change_rate",),
                "confidence": change * val,
                "tags": ("plastic",) if change >= 0.30 else ("rigid",),
            },
            {
                "key": "context_sensitive_adaptation",
                "category": EvidenceCategory.ADAPTATION,
                "title": "Context-sensitive adaptation",
                "description": "Evolutionary response changes under observed pressure.",
                "observations": ("evolutionary_adaptation",),
                "confidence": adapt * val,
                "tags": (
                    ("context_sensitive",)
                    if adapt >= 0.45
                    else ("context_insensitive",)
                ),
                "limitations": ("Adaptation remains a proxy until perturbation tests exist.",),
            },
            {
                "key": "active_repair",
                "category": EvidenceCategory.REPAIR,
                "title": "Active repair",
                "description": "The organization recovers following ecological stress.",
                "observations": ("evolutionary_recovery",),
                "confidence": recovery * val,
                "tags": ("active_repair",) if recovery >= 0.45 else ("no_recovery",),
                "limitations": ("Recovery is observational, not yet intervention-based.",),
            },
            {
                "key": "functional_memory",
                "category": EvidenceCategory.MEMORY,
                "title": "Functional memory",
                "description": "Prior organizational information persists into later behavior.",
                "observations": ("knowledge_memory", "information_survival"),
                "confidence": memory * val,
                "tags": ("functional_memory",) if memory >= 0.45 else ("memory_absent",),
                "limitations": ("Causal memory tests are not yet included.",),
            },
            {
                "key": "lineage_reproduction",
                "category": EvidenceCategory.REPRODUCTION,
                "title": "Tracked lineage reproduction",
                "description": "The lineage tracker records descendants across generations.",
                "observations": ("lineage_births", "deepest_generation"),
                "confidence": (
                    min(1.0, births / 10.0) * 0.5
                    + min(1.0, generation / 3.0) * 0.5
                ) * val,
                "tags": (
                    ("reproduction",)
                    if births > 0 and generation > 0
                    else ("no_viable_descendants",)
                ),
                "limitations": (
                    "Tracked births do not yet prove faithful self-reproduction.",
                ),
            },
            {
                "key": "active_dynamics",
                "category": EvidenceCategory.DYNAMICS,
                "title": "Active dynamics",
                "description": "The world continues to produce non-trivial state changes.",
                "observations": ("changed_cells",),
                "confidence": min(1.0, changed / 100.0) * val,
                "tags": ("active",) if changed > 0 else ("inactive",),
            },
        )


__all__ = [
    "OBSERVER_EVIDENCE_INTEGRATION_VERSION",
    "EvidenceIntegrationError",
    "EvidenceCheckpointResult",
    "LiveObserverEvidenceSession",
]
