"""Toolkit-independent analysis projection controller for OL2-MUTATIONS2."""
from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from Analyzer_next.execution.observer.shell2.mutations1.model import MutationRecord

from .model import MutationAnalysisRunOutcome, MutationAnalysisSnapshot, MutationAnalysisView


class MutationAnalysisReaderPort(Protocol):
    def read(self, record: MutationRecord) -> MutationAnalysisView | None: ...
    def has_report(self, record: MutationRecord) -> bool: ...


class MutationAnalysisRunnerPort(Protocol):
    def analyze(self, record: MutationRecord) -> MutationAnalysisRunOutcome: ...


class MutationAnalysisController:
    def __init__(
        self,
        reader: MutationAnalysisReaderPort,
        runner: MutationAnalysisRunnerPort,
    ) -> None:
        self.reader = reader
        self.runner = runner
        self._snapshot = MutationAnalysisSnapshot()

    @property
    def snapshot(self) -> MutationAnalysisSnapshot:
        return self._snapshot

    def _publish(self, **changes) -> MutationAnalysisSnapshot:
        self._snapshot = replace(
            self._snapshot,
            **changes,
            revision=self._snapshot.revision + 1,
        )
        return self._snapshot

    def select(self, record: MutationRecord | None) -> MutationAnalysisSnapshot:
        if record is None:
            return self._publish(
                selected_mutation_id=None,
                analysis=None,
                busy=False,
                status="Select an observed mutation to inspect scientific effect.",
            )
        analysis = self.reader.read(record)
        status = (
            f"Analysis loaded • {analysis.effect_primary} • {analysis.confidence_label}"
            if analysis is not None
            else (
                "Observed evidence is ready for Mutation Analyzer."
                if record.status in {"OBSERVED", "ANALYZED"}
                else "Run and save this mutation before scientific comparison."
            )
        )
        return self._publish(
            selected_mutation_id=record.mutation_id,
            analysis=analysis,
            busy=False,
            status=status,
        )

    def refresh(self, record: MutationRecord | None) -> MutationAnalysisSnapshot:
        return self.select(record)

    def reject(self, mutation_id: str | None, message: str) -> MutationAnalysisSnapshot:
        return self._publish(
            selected_mutation_id=mutation_id,
            analysis=None,
            busy=False,
            status=f"Analysis report rejected: {message}",
        )

    def can_analyze(self, record: MutationRecord | None) -> bool:
        return bool(
            record is not None
            and record.status in {"OBSERVED", "ANALYZED"}
            and not self._snapshot.busy
        )

    def begin(self, record: MutationRecord) -> MutationAnalysisSnapshot:
        if not self.can_analyze(record):
            raise ValueError("selected mutation is not ready for analysis")
        return self._publish(
            selected_mutation_id=record.mutation_id,
            busy=True,
            status=f"Analyzing {record.mutation_id} against canonical baseline…",
        )

    def run(self, record: MutationRecord) -> MutationAnalysisRunOutcome:
        return self.runner.analyze(record)

    def finish(
        self,
        record: MutationRecord,
        outcome: MutationAnalysisRunOutcome,
    ) -> MutationAnalysisSnapshot:
        analysis = self.reader.read(record)
        if outcome.ok and analysis is not None:
            status = f"Analysis complete • {analysis.effect_primary} • {analysis.confidence_label}"
        elif analysis is not None:
            status = (
                f"Analyzer exited with code {outcome.exit_code}, but a valid report is available • "
                f"{analysis.effect_primary}"
            )
        else:
            detail = (outcome.stderr or outcome.stdout or "Mutation Analyzer did not publish a report.").strip()
            status = f"Analysis failed: {detail[-500:]}"
        return self._publish(
            selected_mutation_id=record.mutation_id,
            analysis=analysis,
            busy=False,
            status=status,
        )


__all__ = [
    "MutationAnalysisController",
    "MutationAnalysisReaderPort",
    "MutationAnalysisRunnerPort",
]
