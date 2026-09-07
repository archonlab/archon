#!/usr/bin/env python3
"""Target-aware Stage 6.3 wrapper around the frozen plan commit owner."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

legacy = importlib.import_module(
    "Analyzer_next.compatibility.legacy_analyzer.experiment_plan_commit"
)
from Analyzer_next.core.experimental_evidence.targeting import (  # noqa: E402
    validate_scientific_target,
)


_ORIGINAL_VALIDATE = legacy.validate_approved_draft
_ORIGINAL_BUILD = legacy.build_plan_manifest


def validate_approved_draft(draft: Dict[str, Any]) -> List[str]:
    errors = _ORIGINAL_VALIDATE(draft)
    target = draft.get("scientific_target")
    if target is None:
        return errors
    valid, failures = validate_scientific_target(target)
    errors.extend(failures if not valid else ())
    if draft.get("scientific_target_hash") != target.get("target_hash"):
        errors.append("SCIENTIFIC_TARGET_REFERENCE_HASH_MISMATCH")
    return sorted(set(errors))


def build_plan_manifest(
    draft: Dict[str, Any],
    commit_id: str,
    requested_by: str,
) -> Dict[str, Any]:
    manifest = _ORIGINAL_BUILD(draft, commit_id, requested_by)
    target = draft.get("scientific_target")
    if not isinstance(target, dict):
        return manifest
    valid, failures = validate_scientific_target(target)
    if not valid:
        raise RuntimeError(
            "Invalid ScientificTarget: " + ", ".join(failures)
        )
    plan = legacy.as_dict(manifest.get("plan"))
    plan["scientific_target"] = target
    plan["scientific_target_hash"] = target["target_hash"]
    manifest["plan"] = plan
    manifest["plan_hash"] = legacy.canonical_hash(plan)
    policy = legacy.as_dict(manifest.get("policy"))
    policy.update({
        "scientific_target_immutable": True,
        "scientific_target_hash_verified": True,
        "target_intent_is_not_support": True,
    })
    manifest["policy"] = policy
    return manifest


def main() -> int:
    legacy.validate_approved_draft = validate_approved_draft
    legacy.build_plan_manifest = build_plan_manifest
    return int(legacy.main())


if __name__ == "__main__":
    raise SystemExit(main())
