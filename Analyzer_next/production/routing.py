"""Fail-closed production routing for parity-approved Analyzer modules.

Every coordinator-managed Analyzer DAG entrypoint is now native.  The registry
remains the explicit allowlist for modular execution, while the legacy profile
continues to provide full rollback without weakening override validation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping


DEFAULT_PROFILE = "modular"
PROFILE_ENV = "ARCHON_ANALYZER_ENTRYPOINT_PROFILE"
MODULE_OVERRIDES_ENV = "ARCHON_ANALYZER_MODULE_OVERRIDES"
SUPPORTED_PROFILES = ("legacy", "modular")

MIGRATED_ROUTE_RELATIVE_PATHS = (
    "Analyzer_next/cli/experiment_analyzer.py",
    "Analyzer_next/cli/observer_profile_v31.py",
    "Analyzer_next/cli/causal_graph_builder.py",
    "Analyzer_next/cli/causal_mechanism_registry.py",
    "Analyzer_next/cli/composition_template_builder.py",
    "Analyzer_next/cli/discovery_engine.py",
    "Analyzer_next/cli/knowledge_base_engine.py",
    "Analyzer_next/cli/mechanism_engine.py",
    "Analyzer_next/cli/mechanism_evolution_graph.py",
    "Analyzer_next/cli/mechanism_timeline_builder.py",
    "Analyzer_next/cli/timeline_compression_engine.py",
    "Analyzer_next/cli/mutation_analyzer.py",
    "Analyzer_next/cli/morphology_analyzer.py",
    "Analyzer_next/cli/morphological_epoch_detector.py",
    "Analyzer_next/cli/morphological_event_detector.py",
    "Analyzer_next/cli/morphological_event_fusion_engine.py",
    "Analyzer_next/cli/morphological_evolution_engine.py",
    "Analyzer_next/cli/consensus_engine.py",
    "Analyzer_next/cli/prediction_engine.py",
    "Analyzer_next/cli/validation_engine.py",
    "Analyzer_next/cli/experiment_planner_engine.py",
    "Analyzer_next/cli/notebook_engine.py",
    "Analyzer_next/cli/research_notebook_index.py",
    "Analyzer_next/cli/meta_science_engine.py",
    "Analyzer_next/cli/research_director.py",
    "Analyzer_next/cli/reference_control_registry.py",
    "Analyzer_next/cli/atlas_engine.py",
    "Analyzer_next/cli/metric_independence_audit.py",
    "Analyzer_next/cli/evidence_engine.py",
    "Analyzer_next/cli/counterexample_engine.py",
    "Analyzer_next/cli/cohort_builder.py",
    "Analyzer_next/cli/general_principle_engine.py",
    "Analyzer_next/cli/theory_engine.py",
    "Analyzer_next/cli/scientific_view_integrity.py",
    "Analyzer_next/cli/alias_integrity_audit.py",
)
MIGRATED_ENTRYPOINTS = tuple(
    Path(relative).name for relative in MIGRATED_ROUTE_RELATIVE_PATHS
)


def validate_module_overrides(
    project_root: Path,
    overrides: Mapping[str, str | Path],
) -> Dict[str, Path]:
    """Normalize an override map and reject routes outside the modular CLI."""
    cli_root = (project_root / "Analyzer_next" / "cli").resolve()
    validated: Dict[str, Path] = {}
    for raw_name, raw_target in overrides.items():
        name = str(raw_name or "").strip()
        if not name or name != Path(name).name or not name.endswith(".py"):
            raise RuntimeError(f"Invalid Analyzer module override name: {raw_name!r}")
        if name not in MIGRATED_ENTRYPOINTS:
            raise RuntimeError(
                f"Analyzer module override is not parity-approved: {name}"
            )
        target = Path(raw_target).expanduser()
        if not target.is_absolute():
            target = project_root / target
        target = target.resolve()
        try:
            target.relative_to(cli_root)
        except ValueError as exc:
            raise RuntimeError(
                f"Analyzer module override escapes {cli_root}: {target}"
            ) from exc
        if target.name != name or not target.is_file():
            raise RuntimeError(
                "Analyzer module override is missing or mismatched: "
                f"{name} -> {target}"
            )
        validated[name] = target
    return validated


def build_module_overrides(project_root: Path) -> Dict[str, str]:
    """Return verified absolute CLI routes for every migrated entrypoint."""
    candidates: Dict[str, Path] = {}
    for relative in MIGRATED_ROUTE_RELATIVE_PATHS:
        target = (project_root / relative).resolve()
        candidates[target.name] = target
    validated = validate_module_overrides(project_root, candidates)
    return {name: str(path) for name, path in validated.items()}
