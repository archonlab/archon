"""Per-mutation dependency discovery and reusable-report validation."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .baseline import discover_baseline_samples
from .constants import CONTROL_RESOLUTION_FILENAME, REPORT_SCHEMA
from .lifecycle import _passport_identity, _samples_run_id
from .experimental import resolve_experimental_mutation, write_resolution_receipt
from .utils import is_inside, normalize_rule_id, read_json

_PASSPORT_FILE_CATALOG: dict[str, list[Path]] = {}

def _declared_passport_paths(
    manifest: dict[str, Any],
    paths: dict[str, Any],
    run_dir: Path,
    *,
    role: str,
) -> list[Path]:
    keys = (
        (
            "baseline_passport",
            "baseline_passport_path",
            "canonical_passport",
        )
        if role == "baseline"
        else (
            "mutant_passport",
            "mutant_passport_path",
            "passport",
            "passport_path",
            "observer_passport",
            "lifecycle_passport",
        )
    )
    declared: list[Path] = []
    for key in keys:
        value = manifest.get(key)
        if value in {None, ""}:
            value = paths.get(key)
        if value in {None, ""}:
            continue
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = run_dir / path
        declared.append(path)
    return declared


def _mutation_identity(
    manifest_path: Path,
) -> tuple[str | None, str]:
    manifest = read_json(manifest_path, {})
    if not isinstance(manifest, dict):
        manifest = {}
    return (
        normalize_rule_id(manifest.get("canonical_parent_rule_id")),
        str(manifest.get("mutation_id") or manifest_path.parent.name),
    )


def _mutation_cache_key(manifest_path: Path) -> str:
    rule_id, mutation_id = _mutation_identity(manifest_path)
    return f"rule_{rule_id or 'unknown'}/{mutation_id}"


def _mutation_report_path(
    manifest_path: Path,
    output_root: Path,
) -> Path:
    rule_id, mutation_id = _mutation_identity(manifest_path)
    return (
        output_root
        / f"rule_{rule_id or 'unknown'}"
        / mutation_id
        / "mutation_report.json"
    )


def _catalog_passports(root: Path) -> list[Path]:
    try:
        resolved = root.resolve()
    except OSError:
        resolved = root
    key = str(resolved)
    cached = _PASSPORT_FILE_CATALOG.get(key)
    if cached is not None:
        return cached
    if not resolved.is_dir():
        paths: list[Path] = []
    else:
        paths = sorted(resolved.rglob("*passport*.json"))
    _PASSPORT_FILE_CATALOG[key] = paths
    return paths


def _existing_declared_path(value: Any, run_dir: Path) -> Path | None:
    if value in {None, ""}:
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = run_dir / path
    try:
        return path.resolve() if path.is_file() else None
    except OSError:
        return None


def _existing_declared_directory(
    value: Any,
    run_dir: Path,
) -> Path | None:
    if value in {None, ""}:
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = run_dir / path
    try:
        return path.resolve() if path.is_dir() else None
    except OSError:
        return None


def _required_control_resolution(
    run_dir: Path,
    *,
    mutation_id: str | None = None,
    parent_rule_id: str | None = None,
) -> tuple[dict[str, Any], Path | None, Path | None]:
    """Load a completed, explicitly linked canonical control.

    Required controls are deliberate replacements for an incomplete frozen
    baseline.  Keeping the link beside the mutation manifest lets one control
    invalidate only the mutation that requested it.
    """

    resolution_path = run_dir / CONTROL_RESOLUTION_FILENAME
    payload = read_json(resolution_path, {})
    if not isinstance(payload, dict):
        return {}, None, None
    if payload.get("schema") != "archon_required_control_resolution_v1":
        return {}, None, None
    if (
        mutation_id
        and str(payload.get("source_mutation_id") or "") != mutation_id
    ):
        return {}, None, None
    if (
        parent_rule_id
        and normalize_rule_id(payload.get("canonical_rule_id"))
        != normalize_rule_id(parent_rule_id)
    ):
        return {}, None, None

    samples_path = _existing_declared_path(
        payload.get("samples_path"),
        run_dir,
    )
    passport_path = _existing_declared_path(
        payload.get("passport_path"),
        run_dir,
    )
    if samples_path is None:
        return {}, None, None
    return payload, samples_path, passport_path


def _locked_legacy_baseline(
    report_path: Path,
    results_root: Path,
    mutation_root: Path,
    parent_rule_id: str | None,
) -> Path | None:
    """Reuse the baseline already selected for a legacy mutation report.

    Older manifests did not declare an immutable baseline.  Once such a run
    has been analyzed, its report becomes the provenance record for the
    selected control.  Keeping that path stable prevents later Observer
    passports or canonical runs from silently changing an old experiment.
    """

    report = read_json(report_path, {})
    if not isinstance(report, dict):
        return None
    match = (
        report.get("baseline_match")
        if isinstance(report.get("baseline_match"), dict)
        else {}
    )
    value = match.get("path")
    if value in {None, ""}:
        return None
    try:
        path = Path(str(value)).expanduser().resolve()
        if not path.is_file() or is_inside(path, mutation_root):
            return None
        if not is_inside(path, results_root):
            return None
    except OSError:
        return None

    if parent_rule_id:
        expected = re.compile(
            rf"^rule_{re.escape(parent_rule_id)}_.*_samples\.csv$",
            re.I,
        )
        if expected.match(path.name) is None:
            return None
    return path


def collect_mutation_dependencies(
    manifest_path: Path,
    results_root: Path,
    mutation_root: Path,
    output_root: Path,
) -> list[Path]:
    """Return only the files that can affect one mutation report.

    Declared baselines are isolated from later canonical runs.  Legacy
    mutations without a declared baseline depend on all candidate baselines
    for their parent rule because candidate ranking can legitimately change.
    """

    manifest_path = manifest_path.resolve()
    run_dir = manifest_path.parent
    manifest = read_json(manifest_path, {})
    if not isinstance(manifest, dict):
        manifest = {}
    paths = (
        manifest.get("paths")
        if isinstance(manifest.get("paths"), dict)
        else {}
    )
    parent_rule_id = normalize_rule_id(
        manifest.get("canonical_parent_rule_id")
    )
    mutation_id = str(
        manifest.get("mutation_id") or run_dir.name
    )
    dependencies: set[Path] = {manifest_path}
    experimental_resolution = resolve_experimental_mutation(
        manifest=manifest,
        results_root=results_root,
        run_dir=run_dir,
    )
    if experimental_resolution is not None:
        receipt_path = (
            _mutation_report_path(manifest_path, output_root).parent
            / "experimental_match_resolution.json"
        )
        dependencies.add(
            write_resolution_receipt(receipt_path, experimental_resolution)
        )
        for value in experimental_resolution.get("dependencies", []):
            try:
                path = Path(str(value)).expanduser().resolve()
                if path.is_file():
                    dependencies.add(path)
            except OSError:
                pass

    resolution_file = run_dir / CONTROL_RESOLUTION_FILENAME
    resolution, resolution_samples, resolution_passport = (
        _required_control_resolution(
            run_dir,
            mutation_id=mutation_id,
            parent_rule_id=parent_rule_id,
        )
    )
    if resolution_file.is_file():
        dependencies.add(resolution_file.resolve())
    if resolution_samples is not None:
        dependencies.add(resolution_samples.resolve())
    if resolution_passport is not None:
        dependencies.add(resolution_passport.resolve())

    for fallback_name, key in (
        ("original_rule.json", "original_rule"),
        ("mutated_rule.json", "mutated_rule"),
        ("mutation_diff.json", "mutation_diff"),
    ):
        fallback = run_dir / fallback_name
        declared = paths.get(key)
        declared_path = (
            Path(str(declared)).expanduser()
            if declared not in {None, ""}
            else None
        )
        chosen = (
            declared_path
            if declared_path is not None and declared_path.is_file()
            else fallback
        )
        if chosen.is_file():
            dependencies.add(chosen.resolve())

    declared_output = _existing_declared_directory(
        paths.get("run_output_directory"),
        run_dir,
    )
    mutant_roots = [run_dir]
    if declared_output is not None and declared_output.is_dir():
        mutant_roots.append(declared_output)
    mutant_samples = sorted({
        path.resolve()
        for root in mutant_roots
        for path in root.rglob("*_samples.csv")
    })
    dependencies.update(path.resolve() for path in mutant_samples)

    explicit_baseline_value = (
        manifest.get("baseline_samples")
        or manifest.get("baseline_path")
        or paths.get("baseline_samples")
    )
    explicit_baseline = _existing_declared_path(
        explicit_baseline_value,
        run_dir,
    )
    report_path = _mutation_report_path(manifest_path, output_root)
    locked_legacy_baseline = (
        _locked_legacy_baseline(
            report_path,
            results_root,
            mutation_root,
            parent_rule_id,
        )
        if explicit_baseline is None
        else None
    )
    baseline_samples: list[Path] = []
    if experimental_resolution is not None:
        experimental_baseline = _existing_declared_path(
            experimental_resolution.get("baseline_samples"),
            run_dir,
        )
        if experimental_baseline is not None:
            baseline_samples = [experimental_baseline]
    elif resolution_samples is not None:
        baseline_samples = [resolution_samples]
    elif explicit_baseline is not None:
        baseline_samples = [explicit_baseline]
    elif locked_legacy_baseline is not None:
        baseline_samples = [locked_legacy_baseline]
    elif parent_rule_id:
        baseline_samples = discover_baseline_samples(
            results_root,
            mutation_root,
            parent_rule_id,
        )
    dependencies.update(path.resolve() for path in baseline_samples)

    baseline_declared_passports = (
        [resolution_passport]
        if resolution_passport is not None
        else _declared_passport_paths(
            manifest,
            paths,
            run_dir,
            role="baseline",
        )
    )
    declared_passports = [
        *baseline_declared_passports,
        *_declared_passport_paths(
            manifest,
            paths,
            run_dir,
            role="mutant",
        ),
    ]
    for path in declared_passports:
        try:
            if path.is_file():
                dependencies.add(path.resolve())
        except OSError:
            pass

    provenance = (
        manifest.get("baseline_provenance")
        if isinstance(manifest.get("baseline_provenance"), dict)
        else {}
    )
    for key in ("samples_path", "passport_path"):
        path = _existing_declared_path(provenance.get(key), run_dir)
        if path is not None:
            dependencies.add(path)

    # Existing reports identify the exact fallback baseline/passports selected
    # before Stage 2G.1, allowing a clean bootstrap without a full recompute.
    old_report = read_json(report_path, {})
    if isinstance(old_report, dict):
        old_paths = [
            old_report.get("baseline_match", {}).get("path")
            if isinstance(old_report.get("baseline_match"), dict)
            else None,
            old_report.get(
                "perturbation_lifecycle_reconciliation", {}
            ).get("baseline", {}).get("passport_path")
            if isinstance(
                old_report.get("perturbation_lifecycle_reconciliation"),
                dict,
            )
            else None,
            old_report.get(
                "perturbation_lifecycle_reconciliation", {}
            ).get("mutant", {}).get("passport_path")
            if isinstance(
                old_report.get("perturbation_lifecycle_reconciliation"),
                dict,
            )
            else None,
        ]
        for value in old_paths:
            path = _existing_declared_path(value, run_dir)
            if path is not None:
                dependencies.add(path)

    if experimental_resolution is not None:
        experimental_treatment = _existing_declared_path(
            experimental_resolution.get("treatment_samples"),
            run_dir,
        )
        if experimental_treatment is not None:
            mutant_samples = sorted({*mutant_samples, experimental_treatment})
    target_samples = [*mutant_samples, *baseline_samples]
    target_run_ids = {
        _samples_run_id(path)
        for path in target_samples
    }
    expected_sources = {
        str(path.resolve())
        for path in dependencies
        if path.name == "mutated_rule.json"
    }
    passport_roots = [
        results_root / "observation_logs",
        run_dir,
        *(
            [declared_output]
            if declared_output is not None and declared_output.is_dir()
            else []
        ),
        *(path.parent for path in baseline_samples),
    ]
    for root in passport_roots:
        for passport_path in _catalog_passports(root):
            identity = _passport_identity(passport_path)
            source = identity.get("source")
            try:
                resolved_source = (
                    str(Path(source).expanduser().resolve())
                    if source
                    else ""
                )
            except OSError:
                resolved_source = str(source or "")
            if (
                identity.get("run_id") in target_run_ids
                or any(
                    passport_path.name.startswith(run_id)
                    for run_id in target_run_ids
                )
                or resolved_source in expected_sources
            ):
                dependencies.add(passport_path.resolve())

    return sorted(dependencies, key=str)


def _load_reusable_report(
    report_path: Path,
    manifest_path: Path,
    dependencies: Iterable[Path],
    *,
    require_newer_than_inputs: bool,
) -> dict[str, Any] | None:
    report = read_json(report_path, {})
    rule_id, mutation_id = _mutation_identity(manifest_path)
    if (
        not isinstance(report, dict)
        or report.get("schema") != REPORT_SCHEMA
        or str(report.get("mutation_id")) != mutation_id
        or normalize_rule_id(report.get("parent_rule_id")) != rule_id
    ):
        return None
    if require_newer_than_inputs:
        try:
            newest_input = max(
                (path.stat().st_mtime_ns for path in dependencies),
                default=0,
            )
            if report_path.stat().st_mtime_ns < newest_input:
                return None
        except OSError:
            return None
    return report


