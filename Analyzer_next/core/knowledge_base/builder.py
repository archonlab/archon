"""Pure normalized knowledge graph construction."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from Analyzer_next.core.scientific_data.contracts import ScientificDataSnapshot

from .aliases import (
    ALIAS_SCHEMA,
    canonical_rule_id,
    canonical_rule_set,
    canonicalize_rule_references,
)
from .contracts import KnowledgeBasePaths
from .registries import mechanism_global_id, merge_prediction_validation


SCHEMA = "archon_knowledge_base_v3_1"


def _deduplicate_relations(
    rows: list[dict[str, str]],
    left: str,
    right: str,
) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        pair = (str(row.get(left, "")), str(row.get(right, "")))
        if pair in seen:
            continue
        seen.add(pair)
        out.append(row)
    return out


def build_knowledge_base(
    data: ScientificDataSnapshot,
    paths: KnowledgeBasePaths,
    aliases: dict[str, str],
    predictions: dict[str, dict[str, Any]],
    validations: dict[str, dict[str, Any]],
    *,
    generated: str | None = None,
) -> dict[str, Any]:
    principle_registry = canonicalize_rule_references(
        dict(data.principles),
        aliases,
    )
    validation_registry = canonicalize_rule_references(
        validations,
        aliases,
    )
    prediction_registry = canonicalize_rule_references(
        merge_prediction_validation(predictions, validation_registry),
        aliases,
    )

    discovery_registry: dict[str, dict[str, Any]] = {}
    mechanism_registry: dict[str, dict[str, Any]] = {}
    rules: dict[str, dict[str, Any]] = {}
    rule_principles: list[dict[str, str]] = []
    rule_predictions: list[dict[str, str]] = []
    rule_validations: list[dict[str, str]] = []
    rule_discoveries: list[dict[str, str]] = []
    rule_mechanisms: list[dict[str, str]] = []

    for source_rule_id in data.rule_ids:
        rule_id = canonical_rule_id(source_rule_id, aliases)
        if not rule_id:
            continue
        passport = canonicalize_rule_references(
            data.passports.get(source_rule_id, {}), aliases
        )
        atlas = canonicalize_rule_references(
            data.atlas.get(source_rule_id, {}), aliases
        )
        notebook = canonicalize_rule_references(
            data.notebook(source_rule_id), aliases
        )
        mechanism_payload = canonicalize_rule_references(
            data.mechanism(source_rule_id), aliases
        )
        principle_ids = data.principle_ids_for_rule(source_rule_id)

        prediction_ids: list[str] = []
        for prediction_id, prediction in prediction_registry.items():
            target_rules = (
                prediction.get("rules")
                or prediction.get("target_rules")
                or []
            )
            normalized_targets = canonical_rule_set(target_rules, aliases)
            principle_targets: set[str] = set()
            for principle_id in prediction.get("principle_ids", []) or []:
                principle = principle_registry.get(str(principle_id), {})
                principle_targets.update(
                    canonical_rule_set(principle.get("rules", []), aliases)
                )
            linked_targets = normalized_targets | principle_targets
            if linked_targets and rule_id in linked_targets:
                prediction_ids.append(prediction_id)

        validation_ids: list[str] = []
        for validation_id, validation in validation_registry.items():
            target_rule = canonical_rule_id(
                validation.get("rule") or validation.get("rule_id"),
                aliases,
            )
            if target_rule == rule_id or validation_id in prediction_ids:
                validation_ids.append(validation_id)

        discovery_ids: list[str] = []
        source_discoveries = (
            data.discoveries.get(source_rule_id)
            or data.discoveries.get(rule_id)
            or []
        )
        for raw_discovery in source_discoveries:
            discovery = canonicalize_rule_references(raw_discovery, aliases)
            discovery_id = str(
                discovery.get("id")
                or f"DISC-{rule_id}-{len(discovery_ids) + 1:03d}"
            )
            discovery_registry[discovery_id] = discovery
            discovery_ids.append(discovery_id)

        mechanism_ids: list[str] = []
        for index, mechanism in enumerate(
            mechanism_payload.get("mechanisms", []),
            start=1,
        ):
            global_id = mechanism_global_id(
                rule_id,
                mechanism.get("id"),
                index,
            )
            mechanism_registry[global_id] = {
                "id": global_id,
                "rule_id": rule_id,
                "local_id": mechanism.get("id"),
                "title": mechanism.get("title"),
                "confidence": mechanism.get("confidence"),
                "claim": mechanism.get("claim"),
            }
            mechanism_ids.append(global_id)

        rule_principles.extend(
            {"rule_id": rule_id, "principle_id": item}
            for item in principle_ids
        )
        rule_predictions.extend(
            {"rule_id": rule_id, "prediction_id": item}
            for item in prediction_ids
        )
        rule_validations.extend(
            {"rule_id": rule_id, "validation_id": item}
            for item in validation_ids
        )
        rule_discoveries.extend(
            {"rule_id": rule_id, "discovery_id": item}
            for item in discovery_ids
        )
        rule_mechanisms.extend(
            {"rule_id": rule_id, "mechanism_id": item}
            for item in mechanism_ids
        )

        existing_rule = rules.get(rule_id, {})
        rules[rule_id] = {
            **existing_rule,
            "rule_id": rule_id,
            "source_rule_id": source_rule_id,
            "canonicalized_from_alias": (
                source_rule_id if source_rule_id != rule_id else None
            ),
            "status": atlas.get("status") or "Active",
            "family": atlas.get("family"),
            "tags": atlas.get("tags", []),
            "passport": passport,
            "atlas": atlas,
            "notebook": notebook,
            "mechanism_scores": mechanism_payload.get("scores", {}),
            "principle_ids": sorted(principle_ids),
            "prediction_ids": sorted(prediction_ids),
            "validation_ids": sorted(validation_ids),
            "discovery_ids": sorted(discovery_ids),
            "mechanism_ids": sorted(mechanism_ids),
        }

    relations = {
        "rule_principles": _deduplicate_relations(
            rule_principles, "rule_id", "principle_id"
        ),
        "rule_predictions": _deduplicate_relations(
            rule_predictions, "rule_id", "prediction_id"
        ),
        "rule_validations": _deduplicate_relations(
            rule_validations, "rule_id", "validation_id"
        ),
        "rule_discoveries": _deduplicate_relations(
            rule_discoveries, "rule_id", "discovery_id"
        ),
        "rule_mechanisms": _deduplicate_relations(
            rule_mechanisms, "rule_id", "mechanism_id"
        ),
    }
    summary = {
        "rules": len(rules),
        "principles": len(principle_registry),
        "predictions": len(prediction_registry),
        "validations": len(validation_registry),
        "discoveries": len(discovery_registry),
        "mechanisms": len(mechanism_registry),
        "rules_with_discoveries": sum(
            1 for rule in rules.values() if rule["discovery_ids"]
        ),
        "rules_with_mechanisms": sum(
            1 for rule in rules.values() if rule["mechanism_ids"]
        ),
        "relation_counts": {
            key: len(value) for key, value in relations.items()
        },
    }
    return {
        "schema": SCHEMA,
        "version": "Universe Search Knowledge Base v3.2 Alias Canonicalization",
        "generated": generated or datetime.now().isoformat(timespec="seconds"),
        "source": {
            "results_folder": str(paths.results_root),
            "analysis_root": str(paths.analysis_root),
            "knowledge_root": str(paths.knowledge_root),
            "atlas": str(paths.atlas_path),
            "rule_aliases": str(
                paths.knowledge_root / "duplicate_rule_aliases.json"
            ),
        },
        "alias_resolution": {
            "schema": ALIAS_SCHEMA,
            "alias_count": len(aliases),
            "aliases": aliases,
        },
        "summary": summary,
        "rules": rules,
        "principles": principle_registry,
        "predictions": prediction_registry,
        "validations": validation_registry,
        "discoveries": discovery_registry,
        "mechanisms": mechanism_registry,
        "relations": relations,
    }
