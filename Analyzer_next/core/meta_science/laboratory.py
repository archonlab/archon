"""Laboratory state projection from already-loaded knowledge inputs."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.meta_science.contracts import MetaScienceInputs
from Analyzer_next.core.meta_science.numeric import si, ss


def build_laboratory_state(inputs: MetaScienceInputs) -> dict[str, Any]:
    kb = inputs.knowledge_base
    prediction_db = inputs.prediction_database
    validation = inputs.validation_report
    experiment_plan = inputs.experiment_plan
    integrity = inputs.knowledge_integrity
    reference_controls = inputs.reference_controls

    kb_summary = kb.get("summary", {}) if isinstance(kb, dict) else {}
    rules = kb.get("rules", {}) if isinstance(kb, dict) else {}
    if not isinstance(rules, dict):
        rules = {}

    predictions = prediction_db.get("predictions", {}) if isinstance(prediction_db, dict) else {}
    if isinstance(predictions, list):
        predictions = {
            ss(item.get("id")): item
            for item in predictions
            if isinstance(item, dict) and item.get("id")
        }
    if not isinstance(predictions, dict):
        predictions = {}

    validation_items = validation.get("results", []) if isinstance(validation, dict) else []
    if not isinstance(validation_items, list):
        validation_items = []

    plan_items = experiment_plan.get("plan", []) if isinstance(experiment_plan, dict) else []
    if not isinstance(plan_items, list):
        plan_items = []

    prediction_statuses: dict[str, int] = {}
    for item in predictions.values():
        if not isinstance(item, dict):
            continue
        status = ss(item.get("status"), "Open")
        prediction_statuses[status] = prediction_statuses.get(status, 0) + 1

    validation_statuses: dict[str, int] = {}
    for item in validation_items:
        if not isinstance(item, dict):
            continue
        status = ss(item.get("status_after"), "Open")
        validation_statuses[status] = validation_statuses.get(status, 0) + 1

    experiment_priorities: dict[str, int] = {}
    for item in plan_items:
        if not isinstance(item, dict):
            continue
        priority = si(item.get("priority"))
        label = "critical" if priority >= 5 else "high" if priority == 4 else "medium" if priority == 3 else "low"
        experiment_priorities[label] = experiment_priorities.get(label, 0) + 1

    rule_count = si(kb_summary.get("rules"), len(rules))
    passport_count = sum(
        1 for rule in rules.values()
        if isinstance(rule, dict) and bool(rule.get("passport"))
    )
    atlas_count = sum(
        1 for rule in rules.values()
        if isinstance(rule, dict) and bool(rule.get("atlas"))
    )
    mechanism_rule_count = si(kb_summary.get("rules_with_mechanisms"))
    discovery_rule_count = si(kb_summary.get("rules_with_discoveries"))

    validations_total = len(validation_items)
    predictions_total = len(predictions)
    confirmed = validation_statuses.get("Confirmed", 0)
    testing = validation_statuses.get("Still testing", 0) + validation_statuses.get("Testing", 0)
    rejected = validation_statuses.get("Rejected", 0)
    open_count = validation_statuses.get("Open", 0)

    integrity_ok = bool(integrity.get("ok")) if isinstance(integrity, dict) else False
    broken_refs = si(integrity.get("broken_reference_count")) if isinstance(integrity, dict) else 0
    duplicate_links = si(integrity.get("duplicate_relation_count")) if isinstance(integrity, dict) else 0

    def coverage(count: int) -> float:
        return round(100.0 * count / max(1, rule_count), 2)

    return {
        "laboratory_health": {
            "rules": rule_count,
            "passports": passport_count,
            "atlas_records": atlas_count,
            "mechanism_rules": mechanism_rule_count,
            "discoveries": si(kb_summary.get("discoveries")),
            "rules_with_discoveries": discovery_rule_count,
            "predictions": predictions_total,
            "validations": validations_total,
            "experiments_planned": len(plan_items),
            "integrity_ok": integrity_ok,
            "broken_references": broken_refs,
            "duplicate_links": duplicate_links,
        },
        "coverage": {
            "passport_percent": coverage(passport_count),
            "atlas_percent": coverage(atlas_count),
            "mechanism_percent": coverage(mechanism_rule_count),
            "discovery_percent": coverage(discovery_rule_count),
            "validation_percent": round(100.0 * validations_total / max(1, predictions_total), 2),
        },
        "prediction_pipeline": {
            "generated": predictions_total,
            "confirmed": confirmed,
            "testing": testing,
            "rejected": rejected,
            "open": open_count,
            "database_status_counts": prediction_statuses,
            "validation_status_counts": validation_statuses,
        },
        "experiment_queue": {
            "total": len(plan_items),
            "priority_counts": experiment_priorities,
            "items": [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "priority": si(item.get("priority")),
                    "type": item.get("type"),
                    "based_on_prediction": item.get("based_on_prediction"),
                }
                for item in plan_items
                if isinstance(item, dict)
            ],
        },
        "research_debt": {
            "rules_without_passports": max(0, rule_count - passport_count),
            "rules_without_atlas_records": max(0, rule_count - atlas_count),
            "rules_without_mechanisms": max(0, rule_count - mechanism_rule_count),
            "rules_without_discoveries": max(0, rule_count - discovery_rule_count),
            "unresolved_predictions": testing + open_count,
            "planned_experiments": len(plan_items),
        },
        "reference_controls": reference_controls if isinstance(reference_controls, dict) else {},
        "knowledge_integrity": {
            "ok": integrity_ok,
            "broken_references": broken_refs,
            "duplicate_links": duplicate_links,
            "unknown_rules": si(integrity.get("unknown_rule_count")) if isinstance(integrity, dict) else 0,
            "orphan_counts": integrity.get("orphan_counts", {}) if isinstance(integrity, dict) else {},
        },
    }
