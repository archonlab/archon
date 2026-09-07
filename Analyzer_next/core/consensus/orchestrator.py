"""Pure coordination of memory update, scoring, and report projection."""
from __future__ import annotations

from .contracts import ConsensusInputs, ConsensusPaths, ConsensusRunResult
from .database import ensure_database_shape, update_database
from .reporting import render_database_md, render_report_md
from .scoring import compute_consensus_report


class ConsensusOrchestrator:
    def run(
        self,
        paths: ConsensusPaths,
        inputs: ConsensusInputs,
    ) -> ConsensusRunResult:
        database = ensure_database_shape(
            inputs.database,
            paths.root,
            paths.results,
        )
        database = update_database(
            database,
            inputs.evidence,
            inputs.profiles_by_rule,
            inputs.aliases,
        )
        report = compute_consensus_report(
            database,
            inputs.counterexample_coverage,
            inputs.replication_context,
        )
        return ConsensusRunResult(
            database=database,
            report=report,
            database_markdown=render_database_md(database),
            report_markdown=render_report_md(report),
        )
