"""Pure Knowledge Base referential-integrity checks."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from Analyzer_next.core.scientific_data.ids import normalize_rule_id


def validate_integrity(
    kb: dict[str, Any],
    *,
    generated: str | None = None,
) -> dict[str, Any]:
    registries = {
        "rules": set(kb.get("rules", {})),
        "principles": set(kb.get("principles", {})),
        "predictions": set(kb.get("predictions", {})),
        "validations": set(kb.get("validations", {})),
        "discoveries": set(kb.get("discoveries", {})),
        "mechanisms": set(kb.get("mechanisms", {})),
    }
    relation_specs = {
        "rule_principles": ("rule_id", "principle_id", "rules", "principles"),
        "rule_predictions": ("rule_id", "prediction_id", "rules", "predictions"),
        "rule_validations": ("rule_id", "validation_id", "rules", "validations"),
        "rule_discoveries": ("rule_id", "discovery_id", "rules", "discoveries"),
        "rule_mechanisms": ("rule_id", "mechanism_id", "rules", "mechanisms"),
    }
    broken: list[dict[str, str]] = []
    duplicate_relations: list[dict[str, str]] = []
    for relation_name, spec in relation_specs.items():
        left_field, right_field, left_registry, right_registry = spec
        seen: set[tuple[str, str]] = set()
        for relation in kb.get("relations", {}).get(relation_name, []):
            left = str(relation.get(left_field, ""))
            right = str(relation.get(right_field, ""))
            pair = (left, right)
            if pair in seen:
                duplicate_relations.append({
                    "relation": relation_name,
                    left_field: left,
                    right_field: right,
                })
            seen.add(pair)
            if left not in registries[left_registry]:
                broken.append({
                    "relation": relation_name,
                    "field": left_field,
                    "value": left,
                })
            if right not in registries[right_registry]:
                broken.append({
                    "relation": relation_name,
                    "field": right_field,
                    "value": right,
                })
    unknown_rules = [
        rule_id
        for rule_id in registries["rules"]
        if normalize_rule_id(rule_id) is None
    ]
    orphan_counts = {}
    for registry_name in (
        "principles",
        "predictions",
        "validations",
        "discoveries",
        "mechanisms",
    ):
        referenced = set()
        for relation_name, spec in relation_specs.items():
            _, right_field, _, right_registry = spec
            if right_registry == registry_name:
                referenced.update(
                    str(item.get(right_field))
                    for item in kb["relations"][relation_name]
                )
        orphan_counts[registry_name] = len(
            registries[registry_name] - referenced
        )
    ok = not broken and not duplicate_relations and not unknown_rules
    return {
        "schema": "archon_knowledge_base_integrity_v1",
        "generated": generated or datetime.now().isoformat(timespec="seconds"),
        "ok": ok,
        "broken_reference_count": len(broken),
        "duplicate_relation_count": len(duplicate_relations),
        "unknown_rule_count": len(unknown_rules),
        "orphan_counts": orphan_counts,
        "broken_references": broken[:200],
        "duplicate_relations": duplicate_relations[:200],
        "unknown_rules": sorted(unknown_rules),
    }
