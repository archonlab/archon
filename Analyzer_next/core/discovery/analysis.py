"""Deterministic discovery rules and database projection."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from .contracts import DiscoveryInputs


def impact_stars(score: int) -> str:
    score = max(1, min(5, int(score)))
    return "★" * score + "☆" * (5 - score)


def discovery_id(rule: str, local_id: str) -> str:
    return f"DISC-{rule}-{local_id}"


def build_discoveries(
    rule: str,
    passport: dict[str, Any],
    atlas: dict[str, Any],
    questions: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    discoveries: list[dict[str, Any]] = []
    lifetime_value = passport.get("lifetime")
    if lifetime_value in (None, ""):
        lifetime_value = atlas.get("lifetime")
    lifetime = int(0 if lifetime_value in (None, "") else lifetime_value)

    dynamic_value = passport.get("dynamic_score")
    if dynamic_value in (None, ""):
        dynamic_value = atlas.get("dynamic_score")
    dynamic = float(0.0 if dynamic_value in (None, "") else dynamic_value)

    breathing_value = passport.get("breathing_score")
    if breathing_value in (None, ""):
        breathing_value = atlas.get("breathing_score")
    breathing = float(0.0 if breathing_value in (None, "") else breathing_value)
    collapse = passport.get("collapse") or atlas.get("collapse")
    split = int(passport.get("split_birth") or atlas.get("split_birth") or 0)
    merge = int(passport.get("merge_death") or atlas.get("merge_death") or 0)
    objects = passport.get("objects") or atlas.get("objects")
    emg = float(atlas.get("emergence_score") or 0.0)
    validation = float(atlas.get("validation_quality") or 0.0)
    research_value = float(atlas.get("research_value") or 0.0)

    def add(local_id: str, **payload: Any) -> None:
        discoveries.append({
            "id": discovery_id(rule, local_id),
            "local_id": local_id,
            "rule_id": rule,
            **payload,
        })

    if lifetime >= 100000 and dynamic >= 0.8 and collapse == "No":
        add(
            "D1",
            title="Long-lived dynamic attractor candidate",
            category="long_lived_attractor",
            impact=5,
            confidence="High",
            finding=(
                f"Rule {rule} survived {lifetime:,} ticks with no observed "
                f"collapse and dynamic score {dynamic:.3f}."
            ),
            why_it_matters=(
                "The rule sustains non-static organization over long time scales."
            ),
            evidence=[
                f"Lifetime: {lifetime:,} ticks",
                f"Dynamic score: {dynamic:.3f}",
                "Collapse: No",
                f"Classification: {passport.get('classification') or atlas.get('classification')}",
            ],
            next_test="Run to 250k and 1M ticks; compare morphology snapshots.",
        )

    if objects and split + merge >= 20:
        add(
            "D2",
            title="Bounded object turnover",
            category="bounded_turnover",
            impact=4,
            confidence="Medium-High",
            finding=(
                f"Object count stayed bounded around {objects} while "
                f"{split + merge} split/merge events accumulated."
            ),
            why_it_matters=(
                "Bounded turnover may indicate regulation rather than collapse "
                "or runaway growth."
            ),
            evidence=[
                f"Objects: {objects}",
                f"Split/birth events: {split}",
                f"Merge/death events: {merge}",
            ],
            next_test="Track object identities and event intervals over time.",
        )

    if breathing >= 0.7:
        add(
            "D3",
            title="Breathing scaffold behaviour",
            category="breathing_scaffold",
            impact=4,
            confidence="Medium",
            finding=(
                f"Breathing score is {breathing:.3f}, suggesting recurring "
                "structural turnover."
            ),
            why_it_matters=(
                "The world may preserve macro-structure while replacing local components."
            ),
            evidence=[
                f"Breathing score: {breathing:.3f}",
                f"Dynamic score: {dynamic:.3f}",
            ],
            next_test="Run cycle detection on event intervals and morphology snapshots.",
        )

    if emg >= 0.65 and validation >= 0.70:
        add(
            "D4",
            title="Validated emergence candidate",
            category="validated_emergence",
            impact=5,
            confidence="High" if validation >= 0.85 else "Medium-High",
            finding=(
                f"Emergence score {emg:.3f} is supported by validation "
                f"quality {validation:.3f}."
            ),
            why_it_matters=(
                "This separates credible organization from visually complex texture."
            ),
            evidence=[
                f"EMG: {emg:.3f}",
                f"Validation: {validation:.3f}",
                f"Research value: {research_value:.3f}",
            ],
            next_test="Replicate on neighbouring and unrelated rule families.",
        )

    hypotheses = questions.get("hypotheses", [])
    high_priority = questions.get("high_priority", [])
    if hypotheses or high_priority:
        add(
            "D5",
            title="Rule-specific research program generated",
            category="research_program",
            impact=3,
            confidence="High",
            finding=(
                f"{len(hypotheses)} hypotheses and "
                f"{len(high_priority)} high-priority questions are linked to this rule."
            ),
            why_it_matters=(
                "The system produces testable follow-up work rather than metrics alone."
            ),
            evidence=[
                f"Hypotheses: {len(hypotheses)}",
                f"High-priority questions: {len(high_priority)}",
            ],
            next_test="Feed confirmed or rejected results back into the notebook.",
        )

    if collapse not in (None, "No") and lifetime <= 1000:
        add(
            "D6",
            title="Rapid-collapse benchmark",
            category="benchmark_control",
            impact=3,
            confidence="High",
            finding=f"Rule {rule} collapsed at approximately tick {collapse}.",
            why_it_matters=(
                "Rapid-collapse worlds are useful benchmark controls and false-positive guards."
            ),
            evidence=[
                f"Lifetime: {lifetime}",
                f"Collapse: {collapse}",
                f"EMG: {emg:.3f}",
                f"Validation: {validation:.3f}",
            ],
            next_test="Compare against long-lived candidates using identical observers.",
        )
    return discoveries


def build_database(
    inputs: DiscoveryInputs,
    *,
    generated: str | None = None,
) -> dict[str, Any]:
    discoveries_by_rule: dict[str, dict[str, Any]] = {}
    flat: list[dict[str, Any]] = []
    empty_questions = {
        "high_priority": [],
        "hypotheses": [],
        "next_actions": [],
    }

    for rule in inputs.rule_ids:
        discoveries = build_discoveries(
            rule,
            inputs.passports.get(rule, {}),
            inputs.atlas.get(rule, {}),
            inputs.questions_by_rule.get(rule, empty_questions),
        )
        discoveries_by_rule[rule] = {
            "rule_id": rule,
            "discovery_count": len(discoveries),
            "discoveries": discoveries,
        }
        flat.extend(discoveries)

    category_counts = Counter(item["category"] for item in flat)
    top = sorted(
        flat,
        key=lambda item: (
            int(item.get("impact", 0)),
            item.get("confidence") in {"High", "Very High"},
            inputs.atlas.get(item["rule_id"], {}).get("research_value", 0),
        ),
        reverse=True,
    )[:40]
    return {
        "schema": "archon_discovery_database_v2",
        "generated": generated or datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "rules_analyzed": len(inputs.rule_ids),
            "rules_with_discoveries": sum(
                1
                for payload in discoveries_by_rule.values()
                if payload["discovery_count"] > 0
            ),
            "discovery_count": len(flat),
            "high_impact_count": sum(
                1 for item in flat if int(item.get("impact", 0)) >= 5
            ),
            "category_counts": dict(sorted(category_counts.items())),
        },
        "top_discoveries": top,
        "discoveries_by_rule": discoveries_by_rule,
        "global_next_actions": inputs.questions_by_rule.get(
            "_global", {}
        ).get("next_actions", []),
    }
