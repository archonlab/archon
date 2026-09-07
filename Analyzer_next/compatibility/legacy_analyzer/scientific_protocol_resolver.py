#!/usr/bin/env python3
"""Resolve committed perturbation intents into immutable protocol matrices.

The resolver consumes the intervention design already produced by
``experiment_planner_engine``.  It never invents a perturbation parameter or
dose.  A perturbation plan is resolved only when its committed provenance,
scientific target, canonical action, and perturbation program agree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from Analyzer_next.compatibility.legacy_analyzer.experiment_runtime_materializer import (
    verified_target_resolution,
)


VERSION = "1.0"
TITLE = "ARCHON Scientific Protocol Resolver"
CONFIRMATION = "RESOLVE_SCIENTIFIC_PROTOCOLS"
SUPPORTED_PARAMETERS = {
    "diffusion",
    "inertia",
    "damping",
    "decay",
    "noise",
    "bias",
    "sharpen",
    "threshold_push",
    "w_avg_r1",
    "w_avg_r4",
    "w_avg_r12",
    "w_var_r1",
    "w_var_r4",
    "w_lap_r1",
    "w_lap_r4",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def verified_manifest(
    entry: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    path_value = text(entry.get("manifest_path"))
    if not path_value:
        return None, ["MANIFEST_PATH_MISSING"]
    manifest = as_dict(load_json(Path(path_value), {}))
    failures: List[str] = []
    if not manifest:
        return None, ["MANIFEST_MISSING_OR_INVALID"]
    plan = as_dict(manifest.get("plan"))
    if canonical_hash(manifest) != entry.get("manifest_hash"):
        failures.append("MANIFEST_HASH_MISMATCH")
    if not plan:
        failures.append("PLAN_MISSING")
    elif canonical_hash(plan) != manifest.get("plan_hash"):
        failures.append("PLAN_CONTENT_HASH_MISMATCH")
    if manifest.get("plan_hash") != entry.get("plan_hash"):
        failures.append("REGISTRY_PLAN_HASH_MISMATCH")
    if entry.get("verification_status") != "VERIFIED":
        failures.append("COMMIT_RECEIPT_NOT_VERIFIED")
    return (manifest if not failures else None), failures


def exact_item(
    items: List[Any], field: str, value: str
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    matches = [
        item
        for item in items
        if isinstance(item, dict) and str(item.get(field) or "") == value
    ]
    if len(matches) != 1:
        return None, [f"{field.upper()}_MATCH_COUNT_INVALID:{len(matches)}"]
    return matches[0], []


def build_protocol(
    *,
    manifest: Dict[str, Any],
    target_resolution: Dict[str, Any],
    canonical_plan: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str], Dict[str, Any]]:
    plan = as_dict(manifest.get("plan"))
    action_id = text(as_dict(plan.get("provenance")).get("source_action_id"))
    evidence: Dict[str, Any] = {
        "source_action_id": action_id,
        "target_resolution_id": target_resolution.get("resolution_id"),
    }
    reasons: List[str] = []
    if not action_id:
        return None, ["SOURCE_ACTION_ID_MISSING"], evidence

    action, action_failures = exact_item(
        as_list(canonical_plan.get("plan")), "id", action_id
    )
    reasons.extend(action_failures)
    if action is None:
        return None, reasons, evidence

    claim_id = text(action.get("based_on_prediction"))
    program_id = f"PERT-{claim_id}" if claim_id else None
    if not program_id:
        reasons.append("PERTURBATION_CLAIM_ID_MISSING")
        return None, reasons, evidence
    program, program_failures = exact_item(
        as_list(canonical_plan.get("perturbation_programs")),
        "id",
        program_id,
    )
    reasons.extend(program_failures)
    if program is None:
        return None, reasons, evidence

    identities = as_dict(target_resolution.get("identities"))
    target_rule_ids = {
        int(item)
        for item in as_list(identities.get("rule_ids"))
        if str(item).isdigit() and int(item) > 0
    }
    if not target_rule_ids and str(identities.get("rule_id") or "").isdigit():
        target_rule_ids.add(int(identities["rule_id"]))
    selected_rules = {
        int(item)
        for item in as_list(
            as_dict(program.get("parent_selection")).get(
                "selected_parent_rules"
            )
        )
        if str(item).isdigit()
    }
    missing_parent_rules = sorted(target_rule_ids - selected_rules)
    if missing_parent_rules:
        reasons.append(
            "TARGET_RULES_NOT_IN_PROTOCOL_PARENT_SELECTION:"
            + ",".join(str(item) for item in missing_parent_rules)
        )

    design = as_dict(program.get("intervention_design"))
    if design.get("mode") != "single_parameter":
        reasons.append("PERTURBATION_MODE_UNSUPPORTED")
    parameters = [
        str(item)
        for item in as_list(design.get("parameter_priority"))
        if str(item)
    ]
    if not parameters:
        reasons.append("PERTURBATION_PARAMETERS_MISSING")
    unsupported = sorted(set(parameters) - SUPPORTED_PARAMETERS)
    if unsupported:
        reasons.extend(
            f"PERTURBATION_PARAMETER_UNSUPPORTED:{item}"
            for item in unsupported
        )
    intensities: List[float] = []
    for item in as_list(design.get("intensity_sweep")):
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            intensities.append(value)
    if 0.5 not in intensities:
        reasons.append("SCREENING_INTENSITY_0_5_NOT_DECLARED")
    if reasons:
        return None, sorted(set(reasons)), evidence

    program_hash = canonical_hash(program)
    arms = [
        {
            "arm_id": f"SCREEN-{parameter.upper()}-I050",
            "mode": "single_parameter",
            "parameter": parameter,
            "intensity": 0.5,
            "application": "PRE_RUN_RULE_MUTATION",
        }
        for parameter in parameters
    ]
    immutable = {
        "plan_id": plan.get("plan_id"),
        "plan_hash": manifest.get("plan_hash"),
        "manifest_hash": canonical_hash(manifest),
        "source_action_id": action_id,
        "claim_id": claim_id,
        "program_id": program_id,
        "program_hash": program_hash,
        "target_resolution_id": target_resolution.get("resolution_id"),
        "target_resolution_hash": target_resolution.get("resolution_hash"),
        "target_rule_id": (
            next(iter(target_rule_ids))
            if len(target_rule_ids) == 1
            else None
        ),
        "target_rule_ids": sorted(target_rule_ids),
        "phase": "SCREENING",
        "intervention_kind": "PRE_RUN_RULE_PARAMETER_MUTATION",
        "arms": arms,
        "matched_control": {
            "required": True,
            "same_parent_rule": True,
            "same_initial_state_and_seed": True,
            "same_tick_horizon": True,
            "same_observer_configuration": True,
        },
        "execution_capability": {
            "required_adapter": "ARCHON_MUTATION_RULE_FILE_V2",
            "available": True,
            "adapter_version": "1.0",
            "materialization": "JUST_IN_TIME_PER_TREATMENT_TASK",
            "canonical_parent_mutation": False,
        },
    }
    protocol_hash = canonical_hash(immutable)
    protocol = {
        "protocol_id": f"PROTO-{protocol_hash[:20].upper()}",
        **immutable,
        "protocol_hash": protocol_hash,
    }
    evidence.update({
        "canonical_action_hash": canonical_hash(action),
        "program_id": program_id,
        "program_hash": program_hash,
    })
    return protocol, [], evidence


def build_registry(
    analysis_root: Path,
    selected_plan_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    experiments = analysis_root / "Experiments"
    plan_registry = as_dict(
        load_json(experiments / "experiment_plan_registry.json", {})
    )
    target_registry = as_dict(
        load_json(
            experiments / "scientific_target_resolution_registry.json", {}
        )
    )
    canonical_plan = as_dict(
        load_json(analysis_root / "experiment_plan.json", {})
    )
    selected = {
        str(item).strip()
        for item in (selected_plan_ids or [])
        if str(item).strip()
    }
    resolutions: List[Dict[str, Any]] = []

    for entry in as_list(plan_registry.get("commits")):
        if not isinstance(entry, dict):
            continue
        entry_plan_id = str(entry.get("plan_id") or "")
        if selected and entry_plan_id not in selected:
            continue
        manifest, failures = verified_manifest(entry)
        if manifest is None:
            resolutions.append({
                "plan_id": entry.get("plan_id"),
                "status": "REFUSED",
                "reasons": failures,
            })
            continue
        plan = as_dict(manifest.get("plan"))
        target, target_failures = verified_target_resolution(
            manifest, target_registry
        )
        if target is None:
            resolutions.append({
                "plan_id": plan.get("plan_id"),
                "status": "REFUSED",
                "reasons": target_failures or [
                    "SCIENTIFIC_TARGET_RESOLUTION_REQUIRED"
                ],
            })
            continue
        if plan.get("experiment_type") != "perturbation_recovery_test":
            immutable = {
                "plan_id": plan.get("plan_id"),
                "plan_hash": manifest.get("plan_hash"),
                "manifest_hash": canonical_hash(manifest),
                "target_resolution_id": target.get("resolution_id"),
                "target_resolution_hash": target.get("resolution_hash"),
                "protocol": None,
                "evidence": {
                    "reason": "PERTURBATION_PROTOCOL_NOT_REQUIRED"
                },
            }
            resolutions.append({
                "resolution_id": (
                    "PROTOCOL-" + canonical_hash(immutable)[:20].upper()
                ),
                "status": "NOT_REQUIRED",
                **immutable,
                "reasons": [],
                "resolution_hash": canonical_hash(immutable),
                "resolved_at": now_iso(),
            })
            continue

        protocol, reasons, evidence = build_protocol(
            manifest=manifest,
            target_resolution=target,
            canonical_plan=canonical_plan,
        )
        immutable = {
            "plan_id": plan.get("plan_id"),
            "plan_hash": manifest.get("plan_hash"),
            "manifest_hash": canonical_hash(manifest),
            "target_resolution_id": target.get("resolution_id"),
            "target_resolution_hash": target.get("resolution_hash"),
            "protocol": protocol,
            "evidence": evidence,
        }
        resolutions.append({
            "resolution_id": (
                "PROTOCOL-" + canonical_hash(immutable)[:20].upper()
            ),
            "status": "RESOLVED" if not reasons else "NEEDS_HUMAN_RESOLUTION",
            **immutable,
            "reasons": reasons,
            "resolution_hash": canonical_hash(immutable),
            "resolved_at": now_iso(),
        })

    resolutions.sort(key=lambda item: str(item.get("plan_id") or ""))
    blocking = [
        item
        for item in resolutions
        if item.get("status") not in {"RESOLVED", "NOT_REQUIRED"}
    ]
    summary = {
        "committed_plan_count": len(resolutions),
        "resolved_count": sum(
            item.get("status") == "RESOLVED" for item in resolutions
        ),
        "not_required_count": sum(
            item.get("status") == "NOT_REQUIRED" for item in resolutions
        ),
        "needs_human_resolution_count": sum(
            item.get("status") == "NEEDS_HUMAN_RESOLUTION"
            for item in resolutions
        ),
        "refused_count": sum(
            item.get("status") == "REFUSED" for item in resolutions
        ),
    }
    sources = {
        "plan_registry_hash": canonical_hash(plan_registry),
        "target_registry_hash": canonical_hash(target_registry),
        "canonical_plan_hash": canonical_hash(canonical_plan),
        "selected_plan_ids": sorted(selected),
    }
    policy = {
        "planner_declared_protocols_only": True,
        "screening_phase_only": True,
        "matched_control_required": True,
        "unsupported_parameters_fail_closed": True,
        "execution_capability_separate_from_protocol_resolution": True,
        "does_not_launch_observer": True,
        "scoped_resolution_supported": True,
    }
    payload = {
        "schema": "archon_scientific_protocol_resolution_registry_v1",
        "version": VERSION,
        "generated_at": now_iso(),
        "status": "RESOLVED" if resolutions and not blocking else (
            "NEEDS_HUMAN_RESOLUTION"
        ),
        "summary": summary,
        "resolutions": resolutions,
        "sources": sources,
        "policy": policy,
    }
    payload["content_hash"] = canonical_hash({
        "summary": summary,
        "resolutions": resolutions,
        "sources": sources,
        "policy": policy,
    })
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument(
        "--plan-id",
        action="append",
        default=[],
        help="Resolve only this committed plan (repeatable).",
    )
    args = parser.parse_args()
    analysis_root = Path(args.analysis_root).expanduser().resolve()
    experiments = analysis_root / "Experiments"
    experiments.mkdir(parents=True, exist_ok=True)
    registry_path = (
        experiments / "scientific_protocol_resolution_registry.json"
    )
    result_path = (
        experiments / "scientific_protocol_resolution_result.json"
    )
    if args.confirmation != CONFIRMATION:
        result = {
            "schema": "archon_scientific_protocol_resolution_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "reasons": ["CONFIRMATION_INVALID"],
            "resolved_at": now_iso(),
        }
        atomic_write_json(result_path, result)
        return 1
    registry = build_registry(
        analysis_root,
        selected_plan_ids=args.plan_id,
    )
    atomic_write_json(registry_path, registry)
    result = {
        "schema": "archon_scientific_protocol_resolution_result_v1",
        "version": VERSION,
        "status": registry.get("status"),
        "summary": registry.get("summary"),
        "registry_path": str(registry_path),
        "registry_hash": registry.get("content_hash"),
        "reasons": sorted({
            reason
            for item in as_list(registry.get("resolutions"))
            for reason in as_list(as_dict(item).get("reasons"))
        }),
        "resolved_at": now_iso(),
    }
    atomic_write_json(result_path, result)
    summary = as_dict(registry.get("summary"))
    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(
        f"Plans: {summary.get('committed_plan_count', 0)} | "
        f"resolved={summary.get('resolved_count', 0)} | "
        f"not-required={summary.get('not_required_count', 0)} | "
        "human="
        f"{summary.get('needs_human_resolution_count', 0)} | "
        f"refused={summary.get('refused_count', 0)}"
    )
    print(f"Status: {registry.get('status')}")
    print(f"Registry: {registry_path}")
    print("=" * 72)
    return 0 if registry.get("status") == "RESOLVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
