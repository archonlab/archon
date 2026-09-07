"""Pure orchestration for Experiment Planner Engine v4.4."""
from __future__ import annotations

from typing import Any

from .contracts import ExperimentPlannerArtifact, ExperimentPlannerInputs
from .planning import (
    ENGINE_VERSION,
    apply_feedback_metric_readiness,
    build_cohort_jobs,
    build_perturbation_programs,
    build_plan,
    render_markdown,
)


def prediction_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    predictions = payload.get("predictions", {})
    if isinstance(predictions, list):
        return {
            str(item.get("id")): item
            for item in predictions
            if isinstance(item, dict) and item.get("id")
        }
    if isinstance(predictions, dict):
        return predictions
    return {}


class ExperimentPlannerOrchestrator:
    def run(self, inputs: ExperimentPlannerInputs) -> ExperimentPlannerArtifact:
        validations = inputs.validation_payload.get("results", [])
        if not isinstance(validations, list):
            validations = []
        predictions = prediction_index(inputs.prediction_payload)
        plan = build_plan(inputs.knowledge_base, validations, predictions)
        search_jobs, mutation_jobs, cohort_tasks = build_cohort_jobs(
            inputs.cohort_payload
        )
        perturbation_programs, perturbation_jobs, perturbation_tasks = (
            build_perturbation_programs(
                inputs.consensus_payload,
                inputs.evidence_payload,
                inputs.cohort_payload,
            )
        )
        mutation_jobs.extend(perturbation_jobs)
        cohort_tasks.extend(perturbation_tasks)
        existing_ids = {str(item.get("id")) for item in plan}
        for task in cohort_tasks:
            if task["id"] not in existing_ids:
                plan.append(task)
                existing_ids.add(task["id"])
        plan, search_jobs, mutation_jobs, metric_readiness = (
            apply_feedback_metric_readiness(
                plan=plan,
                search_jobs=search_jobs,
                mutation_jobs=mutation_jobs,
                perturbation_programs=perturbation_programs,
                metric_audit=inputs.metric_audit,
            )
        )
        plan = sorted(
            plan,
            key=lambda item: (
                int(item.get("priority", 0)),
                item.get("based_on_prediction") is not None,
                item.get("id", ""),
            ),
            reverse=True,
        )
        paths = inputs.paths
        output_payload = {
            "version": ENGINE_VERSION,
            "generated": inputs.generated,
            "source": {
                "knowledge_base": str(paths.knowledge_base),
                "validation_report": str(paths.validation_report),
                "prediction_database": str(paths.prediction_database),
                "cohort_targets": str(paths.cohort_targets),
                "consensus_report": str(paths.consensus_report),
                "evidence_report": str(paths.evidence_report),
                "metric_independence_audit": str(
                    paths.metric_independence_audit
                ),
            },
            "plan_item_count": len(plan),
            "search_job_count": len(search_jobs),
            "mutation_job_count": len(mutation_jobs),
            "perturbation_program_count": len(perturbation_programs),
            "metric_readiness": metric_readiness,
            "plan": plan,
            "search_jobs": search_jobs,
            "mutation_jobs": mutation_jobs,
            "perturbation_programs": perturbation_programs,
        }
        comparable_existing = {
            key: value
            for key, value in inputs.existing_output.items()
            if key != "generated"
        }
        comparable_output = {
            key: value for key, value in output_payload.items() if key != "generated"
        }
        changed = (
            comparable_existing != comparable_output
            or not inputs.output_markdown_exists
        )
        return ExperimentPlannerArtifact(
            payload=output_payload,
            markdown=render_markdown(
                plan,
                inputs.knowledge_base,
                len(validations),
                search_jobs,
                mutation_jobs,
                perturbation_programs,
                inputs.generated,
            ),
            changed=changed,
            validation_count=len(validations),
        )


__all__ = ["ExperimentPlannerOrchestrator", "prediction_index"]
