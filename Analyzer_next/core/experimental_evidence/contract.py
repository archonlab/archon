"""Normalized ExperimentalEvidenceRecord production and validation.

BRIDGE5.4 moved evidence normalization to the producing analyzers. BRIDGE5.6
adds a hash-protected, adjacent-only lineage graph so an observed effect can
be interpreted as a claim signal and only a claim signal can be interpreted
as a principle signal. Evidence Engine consumes that graph; it never rebuilds
scientific meaning from raw producer reports.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, Iterable

from Analyzer_next.core.scientific_claims import CLAIM_SPECS, evaluate_claim

from .targeting import canonical_hash, validate_scientific_target


RECORD_SCHEMA = "archon_experimental_evidence_record_v2"
CONTRACT_SCHEMA = "archon_experimental_evidence_contract_v2"
CONTRACT_VERSION = "2.0"

INTERPRETATION_LEVELS = {
    "OBSERVED_EFFECT",
    "CLAIM_SIGNAL",
    "PRINCIPLE_SIGNAL",
}
LINEAGE_TRANSITIONS = {
    "OBSERVED_EFFECT": "ROOT_OBSERVATION",
    "CLAIM_SIGNAL": "OBSERVED_EFFECT_TO_CLAIM_SIGNAL",
    "PRINCIPLE_SIGNAL": "CLAIM_SIGNAL_TO_PRINCIPLE_SIGNAL",
}
LINEAGE_PARENT_LEVELS = {
    "CLAIM_SIGNAL": "OBSERVED_EFFECT",
    "PRINCIPLE_SIGNAL": "CLAIM_SIGNAL",
}
CONFIDENCE_LEVELS = {
    "NONE",
    "LOW",
    "PRELIMINARY",
    "MEDIUM",
    "HIGH",
    "VERY_HIGH",
}
TARGET_DIRECTIONS = {
    "SUPPORTED": "supportive",
    "CONTRADICTED": "challenging",
    "MIXED": "mixed",
    "NON_DIAGNOSTIC": "non_diagnostic",
    "INSUFFICIENT_DATA": "insufficient",
}
CLAIM_DIRECTIONS = {
    "SUPPORTED": "supportive",
    "MIXED": "mixed",
    "NOT_SUPPORTED": "neutral",
}
_CONFIDENCE_RANK = {
    "NONE": 0,
    "LOW": 1,
    "PRELIMINARY": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "VERY_HIGH": 4,
}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _confidence(value: Any) -> str:
    normalized = _text(value, "NONE").upper().replace(" ", "_")
    return normalized if normalized in CONFIDENCE_LEVELS else "NONE"


def _unique_text(values: Iterable[Any]) -> list[str]:
    return sorted({
        text
        for value in values
        if (text := _text(value))
    })


def _canonical_rule_id(value: Any) -> str | None:
    text = _text(value)
    if text.lower().startswith("rule_"):
        text = text[5:]
    try:
        return f"{int(text):05d}"
    except (TypeError, ValueError):
        return None


def _scientific_source(value: Any) -> Any:
    """Exclude execution-only values from producer provenance hashes."""
    if isinstance(value, Mapping):
        return {
            str(key): _scientific_source(item)
            for key, item in value.items()
            if key not in {"generated", "paths", "incremental"}
        }
    if isinstance(value, (list, tuple)):
        return [_scientific_source(item) for item in value]
    return value


def evidence_record_hash(record: Mapping[str, Any]) -> str:
    immutable = {
        key: value
        for key, value in record.items()
        if key not in {"evidence_record_id", "record_hash"}
    }
    return canonical_hash(immutable)


def build_evidence_record(
    *,
    source_kind: str,
    interpretation_level: str,
    experiment_id: str,
    target_id: str | None,
    claim_id: str | None,
    effect: Mapping[str, Any],
    direction: str,
    relevance: str,
    confidence: Any,
    matched_control_status: Any,
    replication_status: Any,
    causal_status: Any,
    supporting_metrics: Iterable[Any],
    contradicting_metrics: Iterable[Any],
    limitations: Iterable[Any],
    provenance: Mapping[str, Any],
    parent_record_ids: Iterable[Any] = (),
    eligibility: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic, hash-protected evidence record."""
    normalized_provenance = _scientific_source(_as_dict(provenance))
    level = _text(interpretation_level).upper()
    parents = _unique_text(parent_record_ids)
    record: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "version": CONTRACT_VERSION,
        "source_kind": _text(source_kind),
        "interpretation_level": level,
        "experiment_id": _text(experiment_id),
        "target_id": _text(target_id) or None,
        "claim_id": _text(claim_id) or None,
        "effect": _scientific_source(_as_dict(effect)),
        "direction": _text(direction).lower(),
        "relevance": _text(relevance).upper(),
        "confidence": _confidence(confidence),
        "matched_control_status": (
            _text(matched_control_status, "UNKNOWN").upper() or "UNKNOWN"
        ),
        "replication_status": (
            _text(replication_status, "UNASSESSED").upper() or "UNASSESSED"
        ),
        "causal_status": (
            _text(causal_status, "NON_CAUSAL_OR_UNVERIFIED").upper()
            or "NON_CAUSAL_OR_UNVERIFIED"
        ),
        "supporting_metrics": _unique_text(supporting_metrics),
        "contradicting_metrics": _unique_text(contradicting_metrics),
        "limitations": _unique_text(limitations),
        "eligibility": _scientific_source(_as_dict(eligibility) or {
            "status": "ELIGIBLE",
            "reason": "normalized_by_producer",
        }),
        "context": _scientific_source(_as_dict(context)),
        "lineage": {
            "transition": LINEAGE_TRANSITIONS.get(level, "INVALID"),
            "parent_record_ids": parents,
        },
        "provenance": normalized_provenance,
        "provenance_hash": canonical_hash(normalized_provenance),
        "scientific_policy": {
            "target_provenance_is_not_support": True,
            "raw_report_ingestion_by_evidence_engine": False,
            "observational_counts_changed": False,
            "automatic_promotion": False,
            "adjacent_lineage_required": True,
            "level_skipping_forbidden": True,
        },
    }
    record["record_hash"] = evidence_record_hash(record)
    record["evidence_record_id"] = (
        "EER-" + record["record_hash"][:20].upper()
    )
    return record


def validate_evidence_record(
    value: Any,
) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        return False, ("EVIDENCE_RECORD_NOT_OBJECT",)
    failures: list[str] = []
    required = (
        "experiment_id",
        "effect",
        "direction",
        "relevance",
        "confidence",
        "matched_control_status",
        "replication_status",
        "causal_status",
        "supporting_metrics",
        "contradicting_metrics",
        "limitations",
        "lineage",
        "provenance_hash",
    )
    if value.get("schema") != RECORD_SCHEMA:
        failures.append("EVIDENCE_RECORD_SCHEMA_INVALID")
    for field in required:
        if field not in value:
            failures.append(f"EVIDENCE_RECORD_FIELD_MISSING:{field}")
    if not _text(value.get("source_kind")):
        failures.append("EVIDENCE_RECORD_SOURCE_KIND_MISSING")
    if _text(value.get("interpretation_level")).upper() not in INTERPRETATION_LEVELS:
        failures.append("EVIDENCE_RECORD_INTERPRETATION_LEVEL_INVALID")
    if not _text(value.get("experiment_id")):
        failures.append("EVIDENCE_RECORD_EXPERIMENT_ID_MISSING")
    if not isinstance(value.get("effect"), Mapping):
        failures.append("EVIDENCE_RECORD_EFFECT_INVALID")
    elif not _text(value.get("effect", {}).get("status")):
        failures.append("EVIDENCE_RECORD_EFFECT_STATUS_MISSING")
    if _confidence(value.get("confidence")) != value.get("confidence"):
        failures.append("EVIDENCE_RECORD_CONFIDENCE_INVALID")
    for field in (
        "supporting_metrics",
        "contradicting_metrics",
        "limitations",
    ):
        raw = value.get(field)
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            failures.append(f"EVIDENCE_RECORD_LIST_INVALID:{field}")
    provenance = value.get("provenance")
    if not isinstance(provenance, Mapping):
        failures.append("EVIDENCE_RECORD_PROVENANCE_INVALID")
    elif value.get("provenance_hash") != canonical_hash(provenance):
        failures.append("EVIDENCE_RECORD_PROVENANCE_HASH_MISMATCH")
    expected_hash = evidence_record_hash(value)
    if value.get("record_hash") != expected_hash:
        failures.append("EVIDENCE_RECORD_HASH_MISMATCH")
    expected_id = "EER-" + expected_hash[:20].upper()
    if value.get("evidence_record_id") != expected_id:
        failures.append("EVIDENCE_RECORD_ID_MISMATCH")
    eligibility = value.get("eligibility")
    if not isinstance(eligibility, Mapping) or _text(eligibility.get("status")).upper() not in {
        "ELIGIBLE", "REJECTED"
    }:
        failures.append("EVIDENCE_RECORD_ELIGIBILITY_INVALID")
    level = _text(value.get("interpretation_level")).upper()
    lineage = value.get("lineage")
    if not isinstance(lineage, Mapping):
        failures.append("EVIDENCE_RECORD_LINEAGE_INVALID")
    else:
        expected_transition = LINEAGE_TRANSITIONS.get(level)
        if lineage.get("transition") != expected_transition:
            failures.append("EVIDENCE_RECORD_LINEAGE_TRANSITION_INVALID")
        parents = lineage.get("parent_record_ids")
        if (
            not isinstance(parents, list)
            or any(not _text(parent) for parent in parents)
            or len(parents) != len(set(parents))
        ):
            failures.append("EVIDENCE_RECORD_LINEAGE_PARENTS_INVALID")
        elif level == "OBSERVED_EFFECT" and parents:
            failures.append("OBSERVED_EFFECT_MUST_BE_LINEAGE_ROOT")
        elif level in LINEAGE_PARENT_LEVELS and not parents:
            failures.append("EVIDENCE_RECORD_LINEAGE_PARENT_REQUIRED")
    return not failures, tuple(sorted(set(failures)))


def experimental_evidence_contract_hash(contract: Mapping[str, Any]) -> str:
    immutable = {
        key: value
        for key, value in contract.items()
        if key != "contract_hash"
    }
    return canonical_hash(immutable)


def build_evidence_contract(
    *,
    source_kind: str,
    source_schema: Any,
    records: Iterable[Mapping[str, Any]],
    normalization_rejections: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    normalized_records = sorted(
        (dict(record) for record in records),
        key=lambda item: _text(item.get("evidence_record_id")),
    )
    rejections = sorted(
        (_scientific_source(dict(item)) for item in normalization_rejections),
        key=lambda item: canonical_hash(item),
    )
    effect_counts = Counter(
        _text(record.get("effect", {}).get("status"), "UNKNOWN").upper()
        for record in normalized_records
    )
    level_counts = Counter(
        _text(record.get("interpretation_level"), "UNKNOWN").upper()
        for record in normalized_records
    )
    transition_counts = Counter(
        _text(record.get("lineage", {}).get("transition"), "UNKNOWN")
        for record in normalized_records
    )
    eligibility_counts = Counter(
        _text(record.get("eligibility", {}).get("status"), "UNKNOWN").upper()
        for record in normalized_records
    )
    contract: dict[str, Any] = {
        "schema": CONTRACT_SCHEMA,
        "version": CONTRACT_VERSION,
        "source_kind": _text(source_kind),
        "source_schema": _text(source_schema) or None,
        "record_count": len(normalized_records),
        "records": normalized_records,
        "normalization_rejections": rejections,
        "summary": {
            "effect_statuses": dict(sorted(effect_counts.items())),
            "interpretation_levels": dict(sorted(level_counts.items())),
            "lineage_transitions": dict(sorted(transition_counts.items())),
            "eligibility_statuses": dict(sorted(eligibility_counts.items())),
            "normalization_rejections": len(rejections),
        },
        "scientific_policy": {
            "normalized_by_producer": True,
            "consumer_reads_raw_reports": False,
            "fail_closed_on_integrity_error": True,
            "target_provenance_is_not_support": True,
            "automatic_promotion": False,
            "adjacent_lineage_required": True,
            "level_skipping_forbidden": True,
        },
    }
    contract["contract_hash"] = experimental_evidence_contract_hash(contract)
    return contract


def validate_evidence_contract(
    value: Any,
) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        return False, ("EXPERIMENTAL_EVIDENCE_CONTRACT_NOT_OBJECT",)
    failures: list[str] = []
    if value.get("schema") != CONTRACT_SCHEMA:
        failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_SCHEMA_INVALID")
    if value.get("version") != CONTRACT_VERSION:
        failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_VERSION_INVALID")
    if not _text(value.get("source_kind")):
        failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_SOURCE_KIND_MISSING")
    records = value.get("records")
    if not isinstance(records, list):
        failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_RECORDS_INVALID")
        records = []
    if value.get("record_count") != len(records):
        failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_COUNT_MISMATCH")
    seen: set[str] = set()
    records_by_id: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records):
        valid, record_failures = validate_evidence_record(record)
        if not valid:
            failures.extend(
                f"RECORD[{index}]:{reason}" for reason in record_failures
            )
        record_id = _text(
            record.get("evidence_record_id") if isinstance(record, Mapping) else None
        )
        if record_id in seen:
            failures.append(f"RECORD[{index}]:EVIDENCE_RECORD_ID_DUPLICATE")
        seen.add(record_id)
        if record_id and isinstance(record, Mapping):
            records_by_id[record_id] = record
            if _text(record.get("source_kind")) != _text(value.get("source_kind")):
                failures.append(
                    f"RECORD[{index}]:EVIDENCE_RECORD_SOURCE_KIND_MISMATCH"
                )
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            continue
        level = _text(record.get("interpretation_level")).upper()
        lineage = _as_dict(record.get("lineage"))
        parents = _as_list(lineage.get("parent_record_ids"))
        expected_parent_level = LINEAGE_PARENT_LEVELS.get(level)
        for parent_id in parents:
            parent = records_by_id.get(_text(parent_id))
            if parent is None:
                failures.append(
                    f"RECORD[{index}]:EVIDENCE_LINEAGE_PARENT_NOT_FOUND"
                )
                continue
            if _text(parent.get("interpretation_level")).upper() != expected_parent_level:
                failures.append(
                    f"RECORD[{index}]:EVIDENCE_LINEAGE_LEVEL_SKIP"
                )
            if _text(parent.get("experiment_id")) != _text(record.get("experiment_id")):
                failures.append(
                    f"RECORD[{index}]:EVIDENCE_LINEAGE_EXPERIMENT_MISMATCH"
                )
            if _text(parent.get("source_kind")) != _text(record.get("source_kind")):
                failures.append(
                    f"RECORD[{index}]:EVIDENCE_LINEAGE_SOURCE_KIND_MISMATCH"
                )
    summary = value.get("summary")
    if not isinstance(summary, Mapping):
        failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_SUMMARY_INVALID")
    else:
        actual_levels = dict(sorted(Counter(
            _text(record.get("interpretation_level"), "UNKNOWN").upper()
            for record in records if isinstance(record, Mapping)
        ).items()))
        actual_transitions = dict(sorted(Counter(
            _text(_as_dict(record.get("lineage")).get("transition"), "UNKNOWN")
            for record in records if isinstance(record, Mapping)
        ).items()))
        if summary.get("interpretation_levels") != actual_levels:
            failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_LEVEL_SUMMARY_MISMATCH")
        if summary.get("lineage_transitions") != actual_transitions:
            failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_LINEAGE_SUMMARY_MISMATCH")
        if summary.get("normalization_rejections") != len(
            _as_list(value.get("normalization_rejections"))
        ):
            failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_REJECTION_SUMMARY_MISMATCH")
    expected = experimental_evidence_contract_hash(value)
    if value.get("contract_hash") != expected:
        failures.append("EXPERIMENTAL_EVIDENCE_CONTRACT_HASH_MISMATCH")
    return not failures, tuple(sorted(set(failures)))


def contract_records(
    source_payload: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any] | None]:
    """Read only a valid producer contract; raw-source fallback is forbidden."""
    if not isinstance(source_payload, Mapping):
        return [], [], None
    contract = source_payload.get("experimental_evidence_contract")
    if not isinstance(contract, Mapping):
        return [], [{
            "record_id": "*",
            "reason": "experimental_evidence_contract_missing",
        }], None
    valid, failures = validate_evidence_contract(contract)
    if not valid:
        return [], [
            {"record_id": "*", "reason": reason}
            for reason in failures
        ], dict(contract)
    return [dict(record) for record in contract.get("records", [])], [], dict(contract)


def _replication_status(experiment: Mapping[str, Any]) -> str:
    mode = _text(experiment.get("analysis_mode")).lower()
    rule_ids = _as_list(experiment.get("rule_ids"))
    if mode in {"reproducibility_only", "replication_baseline"}:
        return "REPLICATION_DESIGN"
    if len(rule_ids) > 1:
        return "MULTI_RULE_NOT_INDEPENDENTLY_AGGREGATED"
    return "SINGLE_RULE" if rule_ids else "UNASSESSED"


def _experiment_matched_control(experiment: Mapping[str, Any]) -> str:
    audit = _as_dict(experiment.get("runtime_contrast_audit"))
    status = _text(audit.get("status"))
    if status:
        return status
    mode = _text(experiment.get("analysis_mode")).lower()
    if mode == "controlled_comparison":
        return "DISTINCT_TREATMENT_CONTRAST"
    if mode in {"reproducibility_only", "replication_baseline"}:
        return "REPLICATION_CONTROL_ONLY"
    return "UNKNOWN"


def _target_interpretation_provenance_valid(
    interpretation: Mapping[str, Any],
    experiment: Mapping[str, Any],
) -> bool:
    provenance: dict[str, Any] = {
        "experiment_id": _text(interpretation.get("experiment_id")),
        "target_hash": interpretation.get("target_hash"),
        "run_ids": sorted(_text(value) for value in _as_list(experiment.get("run_ids"))),
        "observed_effect_ids": list(interpretation.get("observed_effect_ids", [])),
        "design_status": _as_dict(interpretation.get("design")).get("status"),
    }
    recovery = _as_dict(interpretation.get("target_recovery"))
    if recovery:
        provenance["target_recovery_hash"] = recovery.get("recovery_hash")
    return interpretation.get("provenance_hash") == canonical_hash(provenance)


def build_experiment_evidence_contract(
    knowledge_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize Experiment Knowledge at the producer boundary."""
    experiments = _as_dict(knowledge_payload.get("experiments"))
    claims = _as_dict(knowledge_payload.get("claims"))
    outcomes = _as_dict(knowledge_payload.get("outcomes"))
    targets = _as_dict(knowledge_payload.get("scientific_targets"))
    interpretations = _as_dict(knowledge_payload.get("target_interpretations"))
    target_effects = _as_dict(knowledge_payload.get("observed_effects"))
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    outcome_record_ids: dict[str, str] = {}

    # Outcomes are observations, never claims. They are serialized first so
    # every generic experimental claim can cite immutable record ids instead
    # of loose outcome registry keys.
    for outcome_id, raw_value in sorted(outcomes.items()):
        raw = _as_dict(raw_value)
        experiment_id = _text(raw.get("experiment_id"))
        experiment = _as_dict(experiments.get(experiment_id))
        if not raw or not experiment:
            rejected.append({
                "source_id": _text(outcome_id),
                "source_type": "experiment_outcome",
                "reason": "outcome_missing_or_unknown_experiment",
            })
            continue
        target_ref = _as_dict(raw.get("scientific_target_ref"))
        metric = _text(raw.get("metric"))
        record = build_evidence_record(
            source_kind="experiment_knowledge",
            interpretation_level="OBSERVED_EFFECT",
            experiment_id=experiment_id,
            target_id=_text(target_ref.get("target_id")) or None,
            claim_id=None,
            effect={
                "status": _text(raw.get("status"), "UNKNOWN").upper(),
                "outcome_id": _text(outcome_id),
                "outcome_type": _text(raw.get("outcome_type"), "unknown"),
                "metric": metric or None,
                "observation": raw,
            },
            direction="descriptive",
            relevance="EXPERIMENT_OBSERVATION",
            confidence=raw.get("confidence") or experiment.get("design_confidence"),
            matched_control_status=_experiment_matched_control(experiment),
            replication_status=_replication_status(experiment),
            causal_status="OBSERVED_COMPARISON_ONLY",
            supporting_metrics=[metric] if metric else (),
            contradicting_metrics=(),
            limitations=_as_list(experiment.get("limitations")),
            provenance={
                "source_schema": knowledge_payload.get("schema"),
                "source_outcome_id": _text(outcome_id),
                "source_outcome_hash": canonical_hash(raw),
            },
            context={
                "outcome_id": _text(outcome_id),
                "outcome_type": _text(raw.get("outcome_type"), "unknown"),
                "metric": metric or None,
                "rule_ids": [
                    normalized
                    for value in _as_list(experiment.get("rule_ids"))
                    if (normalized := _canonical_rule_id(value)) is not None
                ],
                "run_ids": list(experiment.get("run_ids", [])),
            },
        )
        records.append(record)
        outcome_record_ids[_text(outcome_id)] = record["evidence_record_id"]

    for interpretation_id, raw_value in sorted(interpretations.items()):
        raw = _as_dict(raw_value)
        experiment_id = _text(raw.get("experiment_id"))
        target_hash = _text(raw.get("target_hash"))
        target_id = _text(raw.get("target_id"))
        status = _text(raw.get("status")).upper()
        experiment = _as_dict(experiments.get(experiment_id))
        target = _as_dict(targets.get(target_hash))
        valid_target, target_failures = validate_scientific_target(target)
        reason = ""
        if not raw:
            reason = "target_interpretation_not_object"
        elif not experiment:
            reason = "target_interpretation_unknown_experiment"
        elif not valid_target:
            reason = "scientific_target_invalid:" + ",".join(target_failures)
        elif _text(target.get("target_id")) != target_id:
            reason = "target_interpretation_target_id_mismatch"
        elif status not in TARGET_DIRECTIONS:
            reason = "target_interpretation_status_invalid"
        elif not _target_interpretation_provenance_valid(raw, experiment):
            reason = "target_interpretation_provenance_hash_mismatch"
        if reason:
            rejected.append({
                "source_id": _text(interpretation_id),
                "source_type": "target_interpretation",
                "reason": reason,
            })
            continue

        design = _as_dict(raw.get("design"))
        recovery = _as_dict(raw.get("target_recovery"))
        observed_effect_ids = [
            _text(value) for value in _as_list(raw.get("observed_effect_ids"))
        ]
        target_parent_ids: list[str] = []
        design_observation = build_evidence_record(
            source_kind="experiment_knowledge",
            interpretation_level="OBSERVED_EFFECT",
            experiment_id=experiment_id,
            target_id=target_id,
            claim_id=None,
            effect={
                "status": (
                    "TARGET_OBSERVATIONS_CAPTURED"
                    if observed_effect_ids
                    else "TARGET_OBSERVATIONS_UNAVAILABLE"
                ),
                "observed_effect_ids": observed_effect_ids,
                "design_status": design.get("status"),
                "reason_codes": list(raw.get("reason_codes", [])),
            },
            direction="descriptive",
            relevance="TARGET_DESIGN_OBSERVATION",
            confidence=raw.get("confidence"),
            matched_control_status=design.get("matched_control_status"),
            replication_status=_replication_status(experiment),
            causal_status="DESIGN_AND_COVERAGE_OBSERVATION",
            supporting_metrics=(),
            contradicting_metrics=(),
            limitations=_as_list(raw.get("limitations")),
            provenance={
                "source_schema": raw.get("schema"),
                "source_interpretation_id": _text(interpretation_id),
                "source_interpretation_provenance_hash": raw.get("provenance_hash"),
                "observation_role": "target_design_and_coverage",
            },
            context={
                "target_hash": target_hash,
                "target_interpretation_id": _text(interpretation_id),
                "question_type": raw.get("question_type"),
            },
        )
        records.append(design_observation)
        target_parent_ids.append(design_observation["evidence_record_id"])

        for effect_id in observed_effect_ids:
            effect = _as_dict(target_effects.get(effect_id))
            if not effect:
                rejected.append({
                    "source_id": effect_id,
                    "source_type": "target_observed_effect",
                    "reason": "target_observed_effect_missing",
                })
                continue
            metric = _text(effect.get("metric"))
            observation = build_evidence_record(
                source_kind="experiment_knowledge",
                interpretation_level="OBSERVED_EFFECT",
                experiment_id=experiment_id,
                target_id=target_id,
                claim_id=None,
                effect={
                    "status": _text(effect.get("direction"), "UNKNOWN").upper(),
                    "effect_id": effect_id,
                    "metric": metric or None,
                    "baseline_value": effect.get("baseline_value"),
                    "treatment_value": effect.get("treatment_value"),
                    "absolute_effect": effect.get("absolute_effect"),
                    "relative_effect": effect.get("relative_effect"),
                    "treatment_arm": effect.get("treatment_arm"),
                },
                direction=_text(effect.get("direction"), "descriptive"),
                relevance="TARGET_METRIC_OBSERVATION",
                confidence=raw.get("confidence"),
                matched_control_status=design.get("matched_control_status"),
                replication_status=_replication_status(experiment),
                causal_status=(
                    "CONTROLLED_INTERVENTION_OBSERVATION"
                    if design.get("status") == "MATCHED_CONTROLLED_INTERVENTION"
                    else "NON_CAUSAL_OR_UNVERIFIED"
                ),
                supporting_metrics=[metric] if metric else (),
                contradicting_metrics=(),
                limitations=_as_list(raw.get("limitations")),
                provenance={
                    "source_schema": effect.get("schema"),
                    "source_effect_id": effect_id,
                    "source_effect_hash": canonical_hash(effect),
                    "source_interpretation_id": _text(interpretation_id),
                },
                context={
                    "target_hash": target_hash,
                    "target_interpretation_id": _text(interpretation_id),
                    "metric": metric or None,
                },
            )
            records.append(observation)
            target_parent_ids.append(observation["evidence_record_id"])
        context = {
            "target_hash": target_hash,
            "target_interpretation_id": _text(interpretation_id),
            "action_id": raw.get("action_id"),
            "question_type": raw.get("question_type"),
            "rule_ids": [
                normalized
                for value in _as_list(experiment.get("rule_ids"))
                if (normalized := _canonical_rule_id(value)) is not None
            ],
            "run_ids": list(experiment.get("run_ids", [])),
            "condition_ids": list(experiment.get("condition_ids", [])),
            "experiment_type": experiment.get("experiment_type"),
            "design_confidence": experiment.get("design_confidence"),
            "target_recovery": recovery or None,
        }
        target_claim = build_evidence_record(
            source_kind="experiment_knowledge",
            interpretation_level="CLAIM_SIGNAL",
            experiment_id=experiment_id,
            target_id=target_id,
            claim_id=f"TCS::{_text(interpretation_id)}",
            effect={
                "status": status,
                "arm_evaluations": list(raw.get("arm_evaluations", [])),
                "reason_codes": list(raw.get("reason_codes", [])),
            },
            direction=TARGET_DIRECTIONS[status],
            relevance="TARGET_INTERPRETATION",
            confidence=raw.get("confidence"),
            matched_control_status=design.get("matched_control_status"),
            replication_status=_replication_status(experiment),
            causal_status=(
                "CONTROLLED_INTERVENTION_CLAIM_SIGNAL"
                if design.get("status") == "MATCHED_CONTROLLED_INTERVENTION"
                else "NON_CAUSAL_OR_UNVERIFIED"
            ),
            supporting_metrics=_as_list(raw.get("supporting_metrics")),
            contradicting_metrics=_as_list(raw.get("contradicting_metrics")),
            limitations=_as_list(raw.get("limitations")),
            provenance={
                "source_schema": raw.get("schema"),
                "source_interpretation_id": _text(interpretation_id),
                "source_interpretation_provenance_hash": raw.get("provenance_hash"),
                "target_hash": target_hash,
            },
            parent_record_ids=target_parent_ids,
            context={
                "target_hash": target_hash,
                "target_interpretation_id": _text(interpretation_id),
                "question_type": raw.get("question_type"),
                "claim_role": "target_specific_experimental_interpretation",
            },
        )
        records.append(target_claim)
        records.append(build_evidence_record(
            source_kind="experiment_knowledge",
            interpretation_level="PRINCIPLE_SIGNAL",
            experiment_id=experiment_id,
            target_id=target_id,
            claim_id=target_id,
            effect={
                "status": status,
                "observed_effect_ids": list(raw.get("observed_effect_ids", [])),
                "reason_codes": list(raw.get("reason_codes", [])),
            },
            direction=TARGET_DIRECTIONS[status],
            relevance="DIRECT_TARGET",
            confidence=raw.get("confidence"),
            matched_control_status=design.get("matched_control_status"),
            replication_status=_replication_status(experiment),
            causal_status=(
                "CONTROLLED_INTERVENTION_SIGNAL"
                if design.get("status") == "MATCHED_CONTROLLED_INTERVENTION"
                else "NON_CAUSAL_OR_UNVERIFIED"
            ),
            supporting_metrics=_as_list(raw.get("supporting_metrics")),
            contradicting_metrics=_as_list(raw.get("contradicting_metrics")),
            limitations=_as_list(raw.get("limitations")),
            provenance={
                "source_schema": raw.get("schema"),
                "source_interpretation_id": _text(interpretation_id),
                "source_interpretation_provenance_hash": raw.get("provenance_hash"),
                "target_hash": target_hash,
                "target_recovery_hash": recovery.get("recovery_hash") if recovery else None,
                "source_claim_signal_id": target_claim["evidence_record_id"],
            },
            parent_record_ids=[target_claim["evidence_record_id"]],
            context=context,
        ))

    for claim_id, raw_value in sorted(claims.items()):
        raw = _as_dict(raw_value)
        experiment_id = _text(raw.get("experiment_id"))
        experiment = _as_dict(experiments.get(experiment_id))
        outcome_ids = [_text(value) for value in _as_list(raw.get("supported_by_outcome_ids"))]
        raw_status = _text(raw.get("status")).lower()
        status = {
            "supported": "SUPPORTED",
            "mixed": "MIXED",
            "not_supported": "NOT_SUPPORTED",
        }.get(raw_status)
        reason = ""
        if not raw:
            reason = "claim_not_object"
        elif not experiment:
            reason = "claim_missing_or_unknown_experiment"
        elif not outcome_ids:
            reason = "claim_missing_outcome_provenance"
        elif any(outcome_id not in outcomes for outcome_id in outcome_ids):
            reason = "claim_unknown_outcome_reference"
        elif any(outcome_id not in outcome_record_ids for outcome_id in outcome_ids):
            reason = "claim_outcome_not_normalized"
        elif raw.get("automatic_promotion") is not False:
            reason = "claim_automatic_promotion_not_disabled"
        elif raw.get("causal_interpretation") is not False:
            reason = "claim_causal_interpretation_not_disabled"
        elif status is None:
            reason = "claim_status_invalid"
        scope = _as_dict(raw.get("scope"))
        rule_ids = [
            normalized
            for value in _as_list(scope.get("rule_ids"))
            if (normalized := _canonical_rule_id(value)) is not None
        ]
        if not reason and not rule_ids:
            reason = "claim_canonical_rule_scope_missing"
        if reason:
            rejected.append({
                "source_id": _text(claim_id),
                "source_type": "experiment_claim",
                "reason": reason,
            })
            continue

        target_ref = _as_dict(raw.get("scientific_target_ref"))
        target_id = _text(target_ref.get("target_id")) or None
        records.append(build_evidence_record(
            source_kind="experiment_knowledge",
            interpretation_level="CLAIM_SIGNAL",
            experiment_id=experiment_id,
            target_id=target_id,
            claim_id=_text(claim_id),
            effect={
                "status": status,
                "statement": _text(raw.get("statement")),
                "claim_type": _text(raw.get("claim_type"), "unknown"),
                "outcome_ids": outcome_ids,
            },
            direction=CLAIM_DIRECTIONS[status],
            relevance=(
                "TARGET_COMPONENT" if target_id else "EXPLICIT_POLICY_CANDIDATE"
            ),
            confidence=raw.get("confidence"),
            matched_control_status=_experiment_matched_control(experiment),
            replication_status=_replication_status(experiment),
            causal_status="NON_CAUSAL_CLAIM_SIGNAL",
            supporting_metrics=_as_list(raw.get("supporting_metrics")),
            contradicting_metrics=_as_list(raw.get("contradicting_metrics")),
            limitations=_as_list(raw.get("limitations")),
            provenance={
                "source_schema": knowledge_payload.get("schema"),
                "source_claim_hash": canonical_hash(raw),
                "outcome_ids": outcome_ids,
                "target_hash": target_ref.get("target_hash"),
                "target_interpretation_id": target_ref.get("target_interpretation_id"),
            },
            parent_record_ids=[outcome_record_ids[value] for value in outcome_ids],
            context={
                "claim_type": _text(raw.get("claim_type"), "unknown"),
                "statement": _text(raw.get("statement")),
                "rule_ids": rule_ids,
                "horizon": scope.get("horizon"),
                "geometries": list(scope.get("geometries", [])),
                "initial_state_modes": list(scope.get("initial_state_modes", [])),
                "outcome_ids": outcome_ids,
                "design_confidence": experiment.get("design_confidence"),
                "experiment_type": experiment.get("experiment_type"),
                "run_ids": list(experiment.get("run_ids", [])),
                "condition_ids": list(experiment.get("condition_ids", [])),
                "scientific_target_ref": target_ref or None,
            },
        ))

    return build_evidence_contract(
        source_kind="experiment_knowledge",
        source_schema=knowledge_payload.get("schema"),
        records=records,
        normalization_rejections=rejected,
    )


def _mutation_arm_profile(report: Mapping[str, Any], arm: str) -> dict[str, Any]:
    metrics_key = "baseline_metrics" if arm == "baseline" else "mutant_metrics"
    metrics = _as_dict(report.get(metrics_key))
    profile: dict[str, Any] = {}
    for section in ("tail_median", "final"):
        for key, value in _as_dict(metrics.get(section)).items():
            profile.setdefault(str(key), value)
    profile.update(_as_dict(metrics.get("categorical_final")))

    metric_delta = _as_dict(report.get("metric_delta"))
    for section in ("tail_median", "final"):
        for key, item in _as_dict(metric_delta.get(section)).items():
            values = _as_dict(item)
            if arm in values:
                profile[str(key)] = values.get(arm)
    for key, item in _as_dict(metric_delta.get("categorical_transitions")).items():
        values = _as_dict(item)
        if arm in values:
            profile[str(key)] = values.get(arm)
    aligned = _as_dict(report.get("aligned_trajectory_delta"))
    for key, item in _as_dict(
        aligned.get("categorical_at_last_common_tick")
    ).items():
        values = _as_dict(item)
        if arm in values:
            profile[str(key)] = values.get(arm)
    return profile


def _mutation_eligibility(report: Mapping[str, Any]) -> tuple[str, str]:
    if report.get("required_control"):
        return "REJECTED", "required_control_pending"
    confidence = _confidence(_as_dict(report.get("comparison_confidence")).get("grade"))
    if _CONFIDENCE_RANK.get(confidence, 0) < _CONFIDENCE_RANK["HIGH"]:
        return "REJECTED", "comparison_confidence_below_high"
    if not _text(report.get("parent_rule_id")):
        return "REJECTED", "missing_parent_rule"
    scope = report.get("scientific_scope")
    if isinstance(scope, Mapping):
        if scope.get("direct_claim_eligible") is not True:
            return "REJECTED", "scientific_scope_not_direct_claim_target"
        if not _text(scope.get("direct_claim_id")):
            return "REJECTED", "scientific_scope_claim_id_missing"
    return "ELIGIBLE", "eligible"


def _perturbation_outcome(baseline_status: str, treatment_status: str) -> str:
    return {
        ("support", "support"): "preserved_support",
        ("support", "neutral"): "disrupted_support",
        ("support", "counterexample"): "induced_counterexample",
        ("neutral", "support"): "induced_support",
        ("neutral", "counterexample"): "induced_counterexample",
        ("counterexample", "counterexample"): "preserved_counterexample",
        ("counterexample", "neutral"): "counterexample_resolved",
        ("counterexample", "support"): "counterexample_resolved",
    }.get((baseline_status, treatment_status), "no_claim_transition")


def _perturbation_direction(outcome: str) -> str:
    if outcome in {"disrupted_support", "induced_counterexample", "preserved_counterexample"}:
        return "challenging"
    if outcome in {"preserved_support", "induced_support", "counterexample_resolved"}:
        return "supportive"
    return "neutral"


def build_mutation_evidence_contract(
    mutation_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize Mutation Analysis comparisons at the producer boundary."""
    reports = _as_list(mutation_payload.get("reports"))
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, raw_value in enumerate(reports):
        report = _as_dict(raw_value)
        if not report:
            rejected.append({
                "source_id": str(index),
                "source_type": "mutation_report",
                "reason": "mutation_report_not_object",
            })
            continue
        mutation_id = _text(report.get("mutation_id"), f"MUTATION-{index}")
        scope = _as_dict(report.get("scientific_scope"))
        direct_claim_id = (
            _text(scope.get("direct_claim_id"))
            if scope.get("direct_claim_eligible") is True
            else ""
        ) or None
        experimental_match = _as_dict(report.get("experimental_match"))
        experiment_id = (
            _text(experimental_match.get("experiment_id"))
            or _text(scope.get("source_experiment_id"))
            or mutation_id
        )
        eligibility_status, eligibility_reason = _mutation_eligibility(report)
        comparison_confidence = _as_dict(report.get("comparison_confidence"))
        baseline_match = _as_dict(report.get("baseline_match"))
        baseline_profile = _mutation_arm_profile(report, "baseline")
        treatment_profile = _mutation_arm_profile(report, "mutant")
        matched_status = _text(baseline_match.get("match_type"), "UNKNOWN")
        if (
            experimental_match.get("status") == "RESOLVED"
            and matched_status == "matched_experiment_control"
        ):
            matched_status = "AUTHORITATIVE_MATCHED_CONTROL"
        relevance = (
            "DIRECT_CLAIM_TARGET" if direct_claim_id
            else "SUPPORTING_PROGRAM_CONTEXT" if scope
            else "LEGACY_UNSCOPED"
        )
        limitations = list(report.get("warnings", []))
        if report.get("required_control"):
            limitations.append("required_control_pending")
        if direct_claim_id is None:
            limitations.append("principle_direction_not_assigned_by_mutation_analyzer")
        same_seed = baseline_match.get("same_seed")
        if same_seed is None:
            same_seed = experimental_match.get("same_seed")
        observation = build_evidence_record(
            source_kind="mutation_analysis",
            interpretation_level="OBSERVED_EFFECT",
            experiment_id=experiment_id,
            target_id=direct_claim_id,
            claim_id=direct_claim_id,
            effect={
                "status": _text(
                    _as_dict(report.get("effect_interpretation")).get("primary"),
                    "unknown",
                ).upper(),
                "primary": _text(
                    _as_dict(report.get("effect_interpretation")).get("primary"),
                    "unknown",
                ),
                "comparison": {
                    "baseline_profile": baseline_profile,
                    "treatment_profile": treatment_profile,
                    "comparison_score": comparison_confidence.get("score"),
                    "same_seed": same_seed,
                    "same_horizon": experimental_match.get("same_horizon"),
                    "coverage_ratio": baseline_match.get("coverage_ratio"),
                },
            },
            direction="descriptive",
            relevance=relevance,
            confidence=comparison_confidence.get("grade"),
            matched_control_status=matched_status,
            replication_status=(
                "INDEPENDENT_REPLICATION"
                if report.get("independent_replication") is True
                else "NOT_INDEPENDENT"
            ),
            causal_status=(
                "CONTROLLED_COMPARISON"
                if eligibility_status == "ELIGIBLE" and same_seed is True
                else "NON_CAUSAL_OR_UNVERIFIED"
            ),
            supporting_metrics=(),
            contradicting_metrics=(),
            limitations=limitations,
            provenance={
                "source_schema": report.get("schema"),
                "source_report_hash": canonical_hash(_scientific_source(report)),
                "mutation_id": mutation_id,
                "parent_rule_id": _text(report.get("parent_rule_id")),
                "canonical_parent_hash": report.get("canonical_parent_hash"),
                "mutated_hash": report.get("mutated_hash"),
                "source_runtime_id": scope.get("source_runtime_id"),
            },
            eligibility={
                "status": eligibility_status,
                "reason": eligibility_reason,
            },
            context={
                "mutation_id": mutation_id,
                "parent_rule_id": _text(report.get("parent_rule_id")),
                "mutation_parameter": _text(report.get("mutation_parameter"), "unknown"),
                "mutation_mode": _text(report.get("mutation_mode"), "unknown"),
                "baseline_match": matched_status,
                "scientific_scope": scope or None,
            },
        )
        records.append(observation)

        if direct_claim_id:
            claim_ids = [direct_claim_id]
        elif scope:
            # A supporting-program comparison remains contextual observation;
            # the producer is not authorized to turn it into claim evidence.
            claim_ids = []
        else:
            # Preserve explicitly labelled legacy behavior, but normalize the
            # claim interpretation at the producer boundary exactly once.
            claim_ids = sorted(CLAIM_SPECS)

        for scientific_claim_id in claim_ids:
            spec = CLAIM_SPECS.get(scientific_claim_id)
            if spec is None:
                rejected.append({
                    "source_id": mutation_id,
                    "source_type": "mutation_claim_signal",
                    "reason": f"scientific_claim_spec_missing:{scientific_claim_id}",
                })
                continue
            baseline_status, baseline_strength, baseline_reason = evaluate_claim(
                scientific_claim_id, baseline_profile
            )
            treatment_status, treatment_strength, treatment_reason = evaluate_claim(
                scientific_claim_id, treatment_profile
            )
            outcome = _perturbation_outcome(
                baseline_status, treatment_status
            )
            direction = _perturbation_direction(outcome)
            claim_limitations = list(limitations)
            if baseline_status == "unavailable":
                claim_limitations.append("baseline_claim_measurements_unavailable")
            if treatment_status == "unavailable":
                claim_limitations.append("treatment_claim_measurements_unavailable")
            records.append(build_evidence_record(
                source_kind="mutation_analysis",
                interpretation_level="CLAIM_SIGNAL",
                experiment_id=experiment_id,
                target_id=scientific_claim_id,
                claim_id=scientific_claim_id,
                effect={
                    "status": "PERTURBATION_CLAIM_SIGNAL",
                    "outcome": outcome,
                    "primary": _text(
                        _as_dict(report.get("effect_interpretation")).get("primary"),
                        "unknown",
                    ),
                    "baseline_claim": {
                        "status": baseline_status,
                        "strength": round(float(baseline_strength), 6),
                        "reason": baseline_reason,
                    },
                    "treatment_claim": {
                        "status": treatment_status,
                        "strength": round(float(treatment_strength), 6),
                        "reason": treatment_reason,
                    },
                },
                direction=direction,
                relevance=(
                    "DIRECT_CLAIM_TARGET"
                    if direct_claim_id
                    else "LEGACY_UNSCOPED_CLAIM_INTERPRETATION"
                ),
                confidence=comparison_confidence.get("grade"),
                matched_control_status=matched_status,
                replication_status=(
                    "INDEPENDENT_REPLICATION"
                    if report.get("independent_replication") is True
                    else "NOT_INDEPENDENT"
                ),
                causal_status=(
                    "CONTROLLED_COMPARISON_CLAIM_SIGNAL"
                    if eligibility_status == "ELIGIBLE" and same_seed is True
                    else "NON_CAUSAL_OR_UNVERIFIED"
                ),
                supporting_metrics=(
                    spec.required_fields if direction == "supportive" else ()
                ),
                contradicting_metrics=(
                    spec.required_fields if direction == "challenging" else ()
                ),
                limitations=claim_limitations,
                provenance={
                    "source_schema": report.get("schema"),
                    "source_report_hash": canonical_hash(_scientific_source(report)),
                    "source_observation_record_id": observation["evidence_record_id"],
                    "mutation_id": mutation_id,
                    "scientific_claim_id": scientific_claim_id,
                    "scientific_claim_version": spec.version,
                },
                parent_record_ids=[observation["evidence_record_id"]],
                eligibility={
                    "status": eligibility_status,
                    "reason": eligibility_reason,
                },
                context={
                    "mutation_id": mutation_id,
                    "parent_rule_id": _text(report.get("parent_rule_id")),
                    "mutation_parameter": _text(report.get("mutation_parameter"), "unknown"),
                    "mutation_mode": _text(report.get("mutation_mode"), "unknown"),
                    "baseline_match": matched_status,
                    "comparison_score": comparison_confidence.get("score"),
                    "scientific_scope": scope or None,
                    "claim_family": spec.family,
                },
            ))

    return build_evidence_contract(
        source_kind="mutation_analysis",
        source_schema=mutation_payload.get("schema"),
        records=records,
        normalization_rejections=rejected,
    )


__all__ = [
    "CONTRACT_SCHEMA",
    "CONTRACT_VERSION",
    "LINEAGE_PARENT_LEVELS",
    "LINEAGE_TRANSITIONS",
    "RECORD_SCHEMA",
    "TARGET_DIRECTIONS",
    "build_evidence_contract",
    "build_evidence_record",
    "build_experiment_evidence_contract",
    "build_mutation_evidence_contract",
    "contract_records",
    "evidence_record_hash",
    "experimental_evidence_contract_hash",
    "validate_evidence_contract",
    "validate_evidence_record",
]
