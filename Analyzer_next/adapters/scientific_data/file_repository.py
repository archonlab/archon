"""Filesystem implementation of the read-only scientific Data Layer."""
from __future__ import annotations

from Analyzer_next.core.scientific_data.contracts import (
    ScientificDataPaths,
    ScientificDataSnapshot,
)

from .atlas import (
    group_atlas_by_rule,
    load_atlas_experiments,
    select_current_atlas_records,
)
from .discoveries import load_discoveries
from .io import find_file
from .mechanisms import find_mechanism_reports, parse_mechanism_report
from .notebooks import find_notebooks, parse_notebook
from .passports import (
    group_passports_by_rule,
    load_passport_records,
    select_best_passports,
)
from .science import load_predictions, load_principles, load_validations


class FileScientificDataRepository:
    """Load a parity-preserving snapshot from existing ARCHON products."""

    def load(self, paths: ScientificDataPaths) -> ScientificDataSnapshot:
        passport_path = (
            find_file(paths.analysis_root, "passport_analysis.md")
            or find_file(paths.results_root, "passport_analysis.md")
        )
        passport_records = load_passport_records(passport_path)
        passports_by_rule = group_passports_by_rule(passport_records)

        atlas_experiments = load_atlas_experiments(paths.atlas_path)
        atlas_by_rule = group_atlas_by_rule(atlas_experiments)

        mechanism_paths = find_mechanism_reports(
            paths.analysis_root,
            paths.results_root,
        )
        notebook_paths = find_notebooks(paths.results_root)

        return ScientificDataSnapshot(
            passport_records=passport_records,
            passports_by_rule=passports_by_rule,
            passports=select_best_passports(passports_by_rule),
            atlas_experiments=atlas_experiments,
            atlas_by_rule=atlas_by_rule,
            atlas=select_current_atlas_records(atlas_by_rule),
            mechanisms_by_rule={
                rule_id: parse_mechanism_report(path)
                for rule_id, path in mechanism_paths.items()
            },
            notebooks_by_rule={
                rule_id: parse_notebook(path)
                for rule_id, path in notebook_paths.items()
            },
            discoveries=load_discoveries(
                paths.results_root,
                paths.analysis_root,
            ),
            principles=load_principles(paths.analysis_root),
            predictions=load_predictions(paths.analysis_root),
            validations=load_validations(paths.analysis_root),
        )
