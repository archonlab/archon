"""Pure coordination for batch mechanism inference."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .analysis import analyze_rule_genome, infer_mechanisms
from .contracts import MechanismInputs, MechanismPaths, MechanismRunResult
from .reporting import render_report


class MechanismOrchestrator:
    def run(
        self,
        paths: MechanismPaths,
        inputs: MechanismInputs,
    ) -> MechanismRunResult:
        aggregate: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        deferred: list[dict[str, str]] = []
        reports: dict[Any, str] = {}
        status_lines: list[str] = []
        total = len(inputs.behaviours)

        for index, behaviour in enumerate(inputs.behaviours, 1):
            rule_id = behaviour["rule"]
            try:
                if rule_id in inputs.rule_deferred:
                    reason = inputs.rule_deferred[rule_id]
                    deferred.append({
                        "rule": rule_id,
                        "status": "ATLAS_CONTEXT_UNAVAILABLE",
                        "reason": reason,
                    })
                    status_lines.append(
                        f"[{index:02d}/{total:02d}] Rule {rule_id}: "
                        f"DEFERRED: ATLAS_CONTEXT_UNAVAILABLE: {reason}"
                    )
                    continue
                if rule_id in inputs.rule_errors:
                    raise RuntimeError(inputs.rule_errors[rule_id])
                source = inputs.rule_sources[rule_id]
                genome = analyze_rule_genome(source.payload)
                mechanisms = infer_mechanisms(genome, behaviour)
                report_path = (
                    paths.output_directory
                    / f"mechanism_report_rule_{rule_id}.md"
                )
                reports[report_path] = render_report(
                    source.path,
                    genome,
                    behaviour,
                    mechanisms,
                    generated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                aggregate.append({
                    "rule": rule_id,
                    "source_rule_id": behaviour.get(
                        "source_rule_id", rule_id
                    ),
                    "canonicalized_from_alias": behaviour.get(
                        "canonicalized_from_alias"
                    ),
                    "source_profile": behaviour.get("source_profile"),
                    "rule_file": str(source.path),
                    "report_file": str(report_path),
                    "behaviour": behaviour,
                    "genome": genome,
                    "mechanisms": mechanisms,
                    "mechanism_count": len(mechanisms),
                })
                status_lines.append(
                    f"[{index:02d}/{total:02d}] Rule {rule_id}: "
                    f"{len(mechanisms)} mechanism candidate(s)"
                )
            except Exception as exc:
                failures.append({"rule": rule_id, "error": str(exc)})
                status_lines.append(
                    f"[{index:02d}/{total:02d}] Rule {rule_id}: FAILED: {exc}"
                )

        payload = {
            "schema": "mechanism_report_v2_2_alias_aware_batch",
            "generated": datetime.now().isoformat(timespec="seconds"),
            "results_folder": str(paths.results_root),
            "alias_resolution": {
                "schema": "archon_duplicate_rule_aliases_v1",
                "alias_count": len(inputs.aliases),
                "aliases": inputs.aliases,
            },
            "rules_queued": total,
            "rules_analyzed": len(aggregate),
            "rules_failed": len(failures),
            "rules_deferred": len(deferred),
            "rules_with_mechanisms": sum(
                1 for record in aggregate if record["mechanism_count"] > 0
            ),
            "mechanism_candidates": sum(
                record["mechanism_count"] for record in aggregate
            ),
            "records": aggregate,
            "deferred": deferred,
            "failures": failures,
        }
        return MechanismRunResult(
            aggregate=payload,
            reports=reports,
            status_lines=tuple(status_lines),
        )
