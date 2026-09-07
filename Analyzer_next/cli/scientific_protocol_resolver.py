#!/usr/bin/env python3
"""Candidate scientific protocol resolver for BRIDGE5.1.

The frozen Analyzer resolver requires ``based_on_prediction`` on the canonical
source action.  A committed metric-validation baseline can intentionally omit
that field while still pinning its target rules to one perturbation program.
BRIDGE5.1 resolves that indirect binding only when the committed canonical plan
contains exactly one perturbation program whose selected parent rules exactly
match the resolved target rules.  Ambiguous or missing bindings remain
fail-closed.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.compatibility.legacy_analyzer import (  # noqa: E402
    scientific_protocol_resolver as _legacy,
)
_legacy_build_protocol = _legacy.build_protocol

VERSION = "1.1-BRIDGE5.1"
BINDING_METHOD = "TARGET_RULES_UNIQUE_PERTURBATION_PROGRAM_MATCH"


def _rule_set(values: Any) -> set[int]:
    result: set[int] = set()
    for item in _legacy.as_list(values):
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            result.add(value)
    return result


def _target_rules(target_resolution: Dict[str, Any]) -> set[int]:
    identities = _legacy.as_dict(target_resolution.get("identities"))
    rules = _rule_set(identities.get("rule_ids"))
    if not rules:
        try:
            value = int(identities.get("rule_id"))
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            rules.add(value)
    return rules


def _indirect_program_binding(
    *,
    action: Dict[str, Any],
    target_resolution: Dict[str, Any],
    canonical_plan: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str], Dict[str, Any]]:
    target_rules = _target_rules(target_resolution)
    action_rules = _rule_set(action.get("target_rules"))
    evidence: Dict[str, Any] = {
        "method": BINDING_METHOD,
        "binding_role": "supporting_program",
        "direct_claim_target": False,
        "target_rule_ids": sorted(target_rules),
        "source_action_target_rules": sorted(action_rules),
    }
    if not target_rules:
        return None, ["PERTURBATION_PROGRAM_BINDING_TARGET_RULES_MISSING"], evidence
    if not action_rules:
        return None, ["PERTURBATION_PROGRAM_BINDING_ACTION_RULES_MISSING"], evidence
    if action_rules != target_rules:
        return None, ["PERTURBATION_PROGRAM_BINDING_ACTION_TARGET_MISMATCH"], evidence

    matches: List[Dict[str, Any]] = []
    for item in _legacy.as_list(canonical_plan.get("perturbation_programs")):
        if not isinstance(item, dict):
            continue
        selected = _rule_set(
            _legacy.as_dict(item.get("parent_selection")).get(
                "selected_parent_rules"
            )
        )
        if selected == target_rules:
            matches.append(item)

    evidence["candidate_program_ids"] = [
        str(item.get("id") or "") for item in matches
    ]
    if not matches:
        return None, ["PERTURBATION_PROGRAM_BINDING_NOT_FOUND"], evidence
    if len(matches) != 1:
        return None, [f"PERTURBATION_PROGRAM_BINDING_AMBIGUOUS:{len(matches)}"], evidence

    program = matches[0]
    claim_id = _legacy.text(program.get("claim_id"))
    program_id = _legacy.text(program.get("id"))
    if not claim_id or not program_id:
        return None, ["PERTURBATION_PROGRAM_BINDING_IDENTITY_MISSING"], evidence
    if program_id != f"PERT-{claim_id}":
        return None, ["PERTURBATION_PROGRAM_BINDING_IDENTITY_MISMATCH"], evidence
    evidence.update({
        "claim_id": claim_id,
        "program_id": program_id,
        "program_hash": _legacy.canonical_hash(program),
    })
    return program, [], evidence


def build_protocol(
    *,
    manifest: Dict[str, Any],
    target_resolution: Dict[str, Any],
    canonical_plan: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str], Dict[str, Any]]:
    plan = _legacy.as_dict(manifest.get("plan"))
    action_id = _legacy.text(_legacy.as_dict(plan.get("provenance")).get("source_action_id"))
    if not action_id:
        return _legacy_build_protocol(
            manifest=manifest,
            target_resolution=target_resolution,
            canonical_plan=canonical_plan,
        )

    action, action_failures = _legacy.exact_item(
        _legacy.as_list(canonical_plan.get("plan")), "id", action_id
    )
    if action is None:
        return None, action_failures, {
            "source_action_id": action_id,
            "target_resolution_id": target_resolution.get("resolution_id"),
        }

    if _legacy.text(action.get("based_on_prediction")):
        return _legacy_build_protocol(
            manifest=manifest,
            target_resolution=target_resolution,
            canonical_plan=canonical_plan,
        )

    program, reasons, binding = _indirect_program_binding(
        action=action,
        target_resolution=target_resolution,
        canonical_plan=canonical_plan,
    )
    evidence: Dict[str, Any] = {
        "source_action_id": action_id,
        "target_resolution_id": target_resolution.get("resolution_id"),
        "claim_binding": binding,
    }
    if program is None:
        return None, reasons or ["PERTURBATION_CLAIM_ID_MISSING"], evidence

    claim_id = str(program.get("claim_id"))
    bridged_plan = copy.deepcopy(canonical_plan)
    bridged_action, failures = _legacy.exact_item(
        _legacy.as_list(bridged_plan.get("plan")), "id", action_id
    )
    if bridged_action is None:
        return None, failures, evidence
    bridged_action["based_on_prediction"] = claim_id

    protocol, legacy_reasons, legacy_evidence = _legacy_build_protocol(
        manifest=manifest,
        target_resolution=target_resolution,
        canonical_plan=bridged_plan,
    )
    if protocol is None:
        evidence.update(legacy_evidence)
        evidence["claim_binding"] = binding
        return None, legacy_reasons, evidence

    # Preserve the true committed source-action hash rather than hashing the
    # compatibility copy used only to reuse the frozen protocol builder.
    evidence.update(legacy_evidence)
    evidence["canonical_action_hash"] = _legacy.canonical_hash(action)
    evidence["claim_binding"] = binding

    protocol_core = {
        key: value
        for key, value in protocol.items()
        if key not in {"protocol_id", "protocol_hash"}
    }
    protocol_core["claim_binding"] = {
        "method": BINDING_METHOD,
        "binding_role": "supporting_program",
        "direct_claim_target": False,
        "source_action_id": action_id,
        "claim_id": claim_id,
        "program_id": program.get("id"),
        "target_rule_ids": sorted(_target_rules(target_resolution)),
    }
    protocol_hash = _legacy.canonical_hash(protocol_core)
    protocol = {
        "protocol_id": f"PROTO-{protocol_hash[:20].upper()}",
        **protocol_core,
        "protocol_hash": protocol_hash,
    }
    return protocol, [], evidence


# Reuse the frozen registry/CLI semantics with only the protocol binding
# function replaced.  Analyzer/ remains byte-for-byte untouched.
_legacy.VERSION = VERSION
_legacy.build_protocol = build_protocol


def main() -> int:
    return _legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
