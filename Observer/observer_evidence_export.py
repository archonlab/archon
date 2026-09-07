#!/usr/bin/env python3
"""Evidence export utilities for Project ARCHON Observer.

This module writes a complete Evidence Framework result to a stable directory
layout without changing any scientific content.

Default layout
--------------
Evidence/
└── <world_id>/
    └── <run_id>/
        ├── evidence_report.json
        ├── observations.json
        ├── evidence.json
        ├── evidence_groups.json
        ├── hypotheses.json
        ├── unknowns.json
        ├── conflicts.json
        ├── confidence_audits.json
        ├── pipeline_diagnostics.json
        └── manifest.json

Design boundary
---------------
The exporter serializes, validates, and atomically writes data. It does not
recalculate confidence, reinterpret evidence, select hypotheses, or alter IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

try:
    from .evidence_models import EvidenceReport
    from .observer_evidence_pipeline import EvidencePipelineResult
except ImportError:  # Direct execution from the Observer directory.
    from evidence_models import EvidenceReport
    from observer_evidence_pipeline import EvidencePipelineResult


OBSERVER_EVIDENCE_EXPORT_VERSION = "1.0.0"


class EvidenceExportError(RuntimeError):
    """Raised when evidence data cannot be exported safely."""


@dataclass(frozen=True, slots=True)
class ExportedArtifact:
    """Metadata for one file produced by an export run."""

    name: str
    relative_path: str
    sha256: str
    size_bytes: int
    record_count: int | None = None


@dataclass(frozen=True, slots=True)
class EvidenceExportResult:
    """Summary of one completed export."""

    export_dir: str
    manifest_path: str
    artifacts: tuple[ExportedArtifact, ...]
    world_id: str
    run_id: str
    report_id: str


@dataclass(frozen=True, slots=True)
class EvidenceExportConfig:
    """Configuration for evidence export."""

    root_dir_name: str = "Evidence"
    indent: int = 2
    ensure_ascii: bool = False
    overwrite: bool = False
    include_split_files: bool = True
    include_pipeline_diagnostics: bool = True
    include_confidence_audits: bool = True
    write_latest_pointer: bool = True

    def __post_init__(self) -> None:
        root = str(self.root_dir_name).strip()
        if not root:
            raise EvidenceExportError("root_dir_name must not be empty")
        if self.indent < 0:
            raise EvidenceExportError("indent must be >= 0")
        object.__setattr__(self, "root_dir_name", root)


class EvidenceExporter:
    """Export EvidenceReport or EvidencePipelineResult to JSON artifacts."""

    def __init__(self, config: EvidenceExportConfig | None = None) -> None:
        self.config = config or EvidenceExportConfig()

    def export_pipeline_result(
        self,
        result: EvidencePipelineResult,
        *,
        output_root: str | Path,
        extra_manifest_metadata: Mapping[str, Any] | None = None,
    ) -> EvidenceExportResult:
        """Export a complete pipeline result."""

        if not isinstance(result, EvidencePipelineResult):
            raise EvidenceExportError(
                "result must be an EvidencePipelineResult"
            )

        report = result.report
        split_payloads = self._split_report_payloads(report)

        if self.config.include_confidence_audits:
            split_payloads["confidence_audits.json"] = [
                self._jsonable(item)
                for item in result.evidence_confidence_audits
            ]

        if self.config.include_pipeline_diagnostics:
            split_payloads["pipeline_diagnostics.json"] = {
                "pipeline": self._jsonable(result.diagnostics),
                "hypothesis_competition": self._jsonable(
                    result.hypothesis_competition
                ),
                "consistency_report": self._jsonable(
                    result.consistency_report
                ),
                "baseline_unknown_detections": self._jsonable(
                    result.baseline_unknown_detections
                ),
            }

        return self._export(
            report=report,
            output_root=output_root,
            split_payloads=split_payloads,
            extra_manifest_metadata=extra_manifest_metadata,
        )

    def export_report(
        self,
        report: EvidenceReport,
        *,
        output_root: str | Path,
        extra_manifest_metadata: Mapping[str, Any] | None = None,
    ) -> EvidenceExportResult:
        """Export a validated EvidenceReport without pipeline diagnostics."""

        if not isinstance(report, EvidenceReport):
            raise EvidenceExportError("report must be an EvidenceReport")

        return self._export(
            report=report,
            output_root=output_root,
            split_payloads=self._split_report_payloads(report),
            extra_manifest_metadata=extra_manifest_metadata,
        )

    def _export(
        self,
        *,
        report: EvidenceReport,
        output_root: str | Path,
        split_payloads: Mapping[str, Any],
        extra_manifest_metadata: Mapping[str, Any] | None,
    ) -> EvidenceExportResult:
        output_root = Path(output_root).expanduser().resolve()
        export_dir = (
            output_root
            / self.config.root_dir_name
            / _safe_component(report.world_id, "world_id")
            / _safe_component(report.run_id, "run_id")
        )

        if export_dir.exists() and any(export_dir.iterdir()):
            if not self.config.overwrite:
                raise EvidenceExportError(
                    f"Export directory already exists and is not empty: "
                    f"{export_dir}"
                )
        export_dir.mkdir(parents=True, exist_ok=True)

        artifacts: list[ExportedArtifact] = []

        # Canonical report first. Its own serializer is authoritative.
        try:
            report_payload = json.loads(report.to_json())
        except Exception as exc:
            raise EvidenceExportError(
                f"Could not serialize EvidenceReport: {exc}"
            ) from exc

        artifacts.append(
            self._write_json_artifact(
                export_dir,
                "evidence_report.json",
                report_payload,
                record_count=1,
            )
        )

        if self.config.include_split_files:
            for filename, payload in split_payloads.items():
                artifacts.append(
                    self._write_json_artifact(
                        export_dir,
                        filename,
                        payload,
                        record_count=(
                            len(payload)
                            if isinstance(payload, (list, tuple))
                            else 1
                        ),
                    )
                )

        manifest_payload = {
            "schema": "archon.evidence_export_manifest.v1",
            "exporter_version": OBSERVER_EVIDENCE_EXPORT_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "world_id": report.world_id,
            "run_id": report.run_id,
            "observer_version": report.observer_version,
            "report_id": report.report_id,
            "artifacts": [
                self._jsonable(item)
                for item in artifacts
            ],
            "counts": {
                "observations": len(report.observations),
                "evidence": len(report.evidence),
                "groups": len(report.groups),
                "hypotheses": len(report.hypotheses),
                "unknowns": len(report.unknowns),
                "conflicts": len(report.conflicts),
            },
            "report_metadata": self._jsonable(report.metadata),
            "extra_metadata": self._jsonable(
                dict(extra_manifest_metadata or {})
            ),
        }

        manifest_artifact = self._write_json_artifact(
            export_dir,
            "manifest.json",
            manifest_payload,
            record_count=1,
        )
        artifacts.append(manifest_artifact)

        if self.config.write_latest_pointer:
            self._write_latest_pointer(
                export_dir=export_dir,
                output_root=output_root,
                report=report,
            )

        return EvidenceExportResult(
            export_dir=str(export_dir),
            manifest_path=str(export_dir / "manifest.json"),
            artifacts=tuple(artifacts),
            world_id=report.world_id,
            run_id=report.run_id,
            report_id=report.report_id,
        )

    @staticmethod
    def _split_report_payloads(
        report: EvidenceReport,
    ) -> dict[str, Any]:
        return {
            "observations.json": [
                EvidenceExporter._jsonable(item)
                for item in report.observations
            ],
            "evidence.json": [
                EvidenceExporter._jsonable(item)
                for item in report.evidence
            ],
            "evidence_groups.json": [
                EvidenceExporter._jsonable(item)
                for item in report.groups
            ],
            "hypotheses.json": [
                EvidenceExporter._jsonable(item)
                for item in report.hypotheses
            ],
            "unknowns.json": [
                EvidenceExporter._jsonable(item)
                for item in report.unknowns
            ],
            "conflicts.json": [
                EvidenceExporter._jsonable(item)
                for item in report.conflicts
            ],
        }

    def _write_json_artifact(
        self,
        export_dir: Path,
        filename: str,
        payload: Any,
        *,
        record_count: int | None,
    ) -> ExportedArtifact:
        path = export_dir / filename
        encoded = json.dumps(
            self._jsonable(payload),
            ensure_ascii=self.config.ensure_ascii,
            indent=self.config.indent,
            sort_keys=True,
        ) + "\n"
        data = encoded.encode("utf-8")
        _atomic_write_bytes(path, data)

        return ExportedArtifact(
            name=filename,
            relative_path=filename,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            record_count=record_count,
        )

    def _write_latest_pointer(
        self,
        *,
        export_dir: Path,
        output_root: Path,
        report: EvidenceReport,
    ) -> None:
        world_dir = (
            output_root
            / self.config.root_dir_name
            / _safe_component(report.world_id, "world_id")
        )
        pointer_path = world_dir / "latest.json"
        pointer_payload = {
            "schema": "archon.evidence_latest_pointer.v1",
            "world_id": report.world_id,
            "run_id": report.run_id,
            "report_id": report.report_id,
            "relative_export_dir": export_dir.name,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        encoded = json.dumps(
            pointer_payload,
            ensure_ascii=self.config.ensure_ascii,
            indent=self.config.indent,
            sort_keys=True,
        ) + "\n"
        _atomic_write_bytes(pointer_path, encoded.encode("utf-8"))

    @staticmethod
    def _jsonable(value: Any) -> Any:
        """Convert ARCHON models and diagnostics into JSON-safe values."""

        if value is None or isinstance(
            value,
            (str, int, float, bool),
        ):
            return value
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Path):
            return str(value)
        if is_dataclass(value):
            return {
                item.name: EvidenceExporter._jsonable(
                    getattr(value, item.name)
                )
                for item in fields(value)
            }
        if isinstance(value, Mapping):
            return {
                str(key): EvidenceExporter._jsonable(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set, frozenset)):
            return [
                EvidenceExporter._jsonable(item)
                for item in value
            ]
        if hasattr(value, "to_dict") and callable(value.to_dict):
            return EvidenceExporter._jsonable(value.to_dict())
        if hasattr(value, "__dict__"):
            return {
                str(key): EvidenceExporter._jsonable(item)
                for key, item in vars(value).items()
                if not str(key).startswith("_")
            }
        raise EvidenceExportError(
            f"Object is not JSON serializable: {type(value).__name__}"
        )


def _safe_component(value: str, name: str) -> str:
    value = str(value).strip()
    if not value:
        raise EvidenceExportError(f"{name} must not be empty")
    if value in {".", ".."}:
        raise EvidenceExportError(f"Unsafe {name}: {value!r}")
    forbidden = {"/", "\\", "\x00"}
    if any(char in value for char in forbidden):
        raise EvidenceExportError(
            f"Unsafe path characters in {name}: {value!r}"
        )
    return value


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically in the destination directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, path)
    except Exception as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise EvidenceExportError(
            f"Could not write {path}: {exc}"
        ) from exc


def export_evidence_pipeline(
    result: EvidencePipelineResult,
    *,
    output_root: str | Path,
    config: EvidenceExportConfig | None = None,
    extra_manifest_metadata: Mapping[str, Any] | None = None,
) -> EvidenceExportResult:
    """Convenience function for exporting a complete pipeline result."""

    return EvidenceExporter(config).export_pipeline_result(
        result,
        output_root=output_root,
        extra_manifest_metadata=extra_manifest_metadata,
    )


def export_evidence_report(
    report: EvidenceReport,
    *,
    output_root: str | Path,
    config: EvidenceExportConfig | None = None,
    extra_manifest_metadata: Mapping[str, Any] | None = None,
) -> EvidenceExportResult:
    """Convenience function for exporting one EvidenceReport."""

    return EvidenceExporter(config).export_report(
        report,
        output_root=output_root,
        extra_manifest_metadata=extra_manifest_metadata,
    )


__all__ = [
    "OBSERVER_EVIDENCE_EXPORT_VERSION",
    "EvidenceExportError",
    "ExportedArtifact",
    "EvidenceExportResult",
    "EvidenceExportConfig",
    "EvidenceExporter",
    "export_evidence_pipeline",
    "export_evidence_report",
]
