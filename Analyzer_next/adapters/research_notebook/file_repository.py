"""Filesystem repository for Research Notebook Engine v4."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from Analyzer_next.core.research_notebook.contracts import (
    ResearchNotebookInputs,
    ResearchNotebookPaths,
    ResearchNotebookRunResult,
    ResearchNotebookSaveResult,
    ResearchNotebookSavedArtifact,
)


def find_passport_analysis(
    results_folder: Path,
    analysis_root: Path | None = None,
) -> Path:
    folder = Path(results_folder)
    if analysis_root:
        preferred = Path(analysis_root) / "passport_analysis.md"
        if preferred.exists():
            return preferred
    sibling = folder.parent / "Analysis" / "passport_analysis.md"
    if sibling.exists():
        return sibling
    direct = folder / "passport_analysis.md"
    if direct.exists():
        return direct
    matches = list(folder.rglob("passport_analysis.md"))
    if matches:
        return matches[0]
    raise FileNotFoundError("passport_analysis.md not found")


def read_optional(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_mechanism_reports(
    results_folder: Path,
    analysis_root: Path,
) -> tuple[dict[str, str], str]:
    reports: dict[str, str] = {}
    result_paths = sorted(results_folder.glob("mechanism_report_rule_*.md"))
    for root in (results_folder, analysis_root):
        for path in sorted(root.glob("mechanism_report_rule_*.md")):
            match = re.fullmatch(r"mechanism_report_rule_(\d+)\.md", path.name)
            if match:
                reports[match.group(1).zfill(5)] = read_optional(path)
    fallback = read_optional(result_paths[0]) if result_paths else ""
    return reports, fallback


def preserve_research_notes(old: str, rendered: str) -> str:
    marker = "## Research Notes"
    if marker in old and marker in rendered:
        old_notes = old.split(marker, 1)[1]
        if old_notes.strip() and "Add manual notes here." not in old_notes:
            return rendered.split(marker, 1)[0] + marker + old_notes
    return rendered


class FileResearchNotebookRepository:
    def load(self, paths: ResearchNotebookPaths) -> ResearchNotebookInputs:
        passport_path = find_passport_analysis(
            paths.results_folder,
            paths.analysis_root,
        )
        mechanisms, fallback = load_mechanism_reports(
            paths.results_folder,
            paths.analysis_root,
        )
        return ResearchNotebookInputs(
            passport_source_name=passport_path.name,
            passport_text=read_optional(passport_path),
            generated_date=datetime.now().strftime("%Y-%m-%d"),
            results_folder_display=str(paths.results_folder),
            questions_text=read_optional(
                paths.analysis_root / "research_questions.md"
            ),
            discoveries_text=read_optional(
                paths.results_folder / "discovery_report.md"
            ),
            mechanism_reports=mechanisms,
            fallback_mechanism_text=fallback,
            principles_text=read_optional(
                paths.analysis_root / "general_principles.md"
            ),
            predictions_text=read_optional(
                paths.analysis_root / "predictions.md"
            ),
        )

    def save(
        self,
        paths: ResearchNotebookPaths,
        result: ResearchNotebookRunResult,
    ) -> ResearchNotebookSaveResult:
        output_directory = paths.results_folder / "ResearchNotebook"
        output_directory.mkdir(parents=True, exist_ok=True)
        saved: list[ResearchNotebookSavedArtifact] = []
        manifest_items = []
        for artifact in result.artifacts:
            rule = artifact.notebook["experiment"].get("rule") or "unknown"
            output = output_directory / f"experiment_{rule}.md"
            rendered = artifact.markdown
            if output.exists():
                rendered = preserve_research_notes(
                    output.read_text(encoding="utf-8", errors="replace"),
                    rendered,
                )
            output.write_text(rendered, encoding="utf-8")
            saved.append(
                ResearchNotebookSavedArtifact(
                    notebook=artifact.notebook,
                    path=output,
                )
            )
            manifest_items.append(
                {
                    "rule": artifact.notebook["experiment"].get("rule"),
                    "file": output.name,
                    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                }
            )
        manifest_path = output_directory / "notebook_manifest.json"
        payload = {
            "schema_version": 1,
            "engine": "notebook_engine_v4",
            "source": result.passport_source_name,
            "notebook_count": len(manifest_items),
            "notebooks": manifest_items,
        }
        manifest = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        if (
            not manifest_path.exists()
            or manifest_path.read_text(encoding="utf-8", errors="replace")
            != manifest
        ):
            manifest_path.write_text(manifest, encoding="utf-8")
        return ResearchNotebookSaveResult(
            outputs=tuple(saved),
            manifest_path=manifest_path,
            source_path=find_passport_analysis(
                paths.results_folder,
                paths.analysis_root,
            ),
        )


__all__ = [
    "FileResearchNotebookRepository",
    "find_passport_analysis",
    "load_mechanism_reports",
    "preserve_research_notes",
    "read_optional",
]
