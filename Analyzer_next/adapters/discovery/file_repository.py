"""Filesystem repository preserving Discovery Engine v2 intake semantics."""
from __future__ import annotations

from Analyzer_next.adapters.scientific_data.file_repository import (
    FileScientificDataRepository,
)
from Analyzer_next.adapters.scientific_data.io import (
    find_file,
    read_text,
    write_json_atomic,
)
from Analyzer_next.core.discovery.contracts import (
    DiscoveryInputs,
    DiscoveryPaths,
    DiscoveryRunResult,
)
from Analyzer_next.core.discovery.questions import parse_research_questions
from Analyzer_next.core.scientific_data.contracts import (
    ScientificDataPaths,
    ScientificDataRepository,
)


class FileDiscoveryRepository:
    def __init__(
        self,
        scientific_repository: ScientificDataRepository | None = None,
    ) -> None:
        self._scientific_repository = (
            scientific_repository or FileScientificDataRepository()
        )

    def load(self, paths: DiscoveryPaths) -> DiscoveryInputs:
        snapshot = self._scientific_repository.load(
            ScientificDataPaths.create(
                results_root=paths.results_root,
                analysis_root=paths.analysis_root,
                knowledge_root=paths.knowledge_root,
                atlas_path=paths.atlas_path,
            )
        )
        questions_path = (
            find_file(paths.analysis_root, "research_questions.md")
            or find_file(paths.results_root, "research_questions.md")
        )
        questions_text = read_text(questions_path) if questions_path else None
        return DiscoveryInputs(
            rule_ids=snapshot.rule_ids,
            passports=snapshot.passports,
            atlas=snapshot.atlas,
            questions_by_rule=parse_research_questions(questions_text),
        )

    def save(self, paths: DiscoveryPaths, result: DiscoveryRunResult) -> None:
        write_json_atomic(paths.database_json, result.database, pretty=True)
        paths.report_markdown.write_text(
            result.report_markdown,
            encoding="utf-8",
        )
