#!/usr/bin/env python3
"""Target-aware Stage 6.2 wrapper around the frozen Planner Review."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

legacy = importlib.import_module(
    "Analyzer_next.compatibility.legacy_analyzer.experiment_planner_review"
)
from Analyzer_next.core.experimental_evidence.targeting import (  # noqa: E402
    validate_scientific_target,
)


_ORIGINAL_BUILD = legacy.build_default_draft
_ORIGINAL_VALIDATE = legacy.validate_draft
_ORIGINAL_APPLY_REVIEW = legacy.apply_review_editor


def build_default_draft(
    intake_record: Dict[str, Any],
    prior: Dict[str, Any],
) -> Dict[str, Any]:
    draft = _ORIGINAL_BUILD(intake_record, prior)
    target = intake_record.get("scientific_target")
    if not isinstance(target, dict):
        return draft
    valid, failures = validate_scientific_target(target)
    if not valid:
        draft["scientific_target_integrity"] = {
            "status": "INVALID",
            "reasons": list(failures),
        }
        return draft
    draft["scientific_target"] = target
    draft["scientific_target_hash"] = target["target_hash"]
    draft["scientific_target_integrity"] = {
        "status": "VERIFIED",
        "reasons": [],
    }
    draft["draft_hash"] = legacy.canonical_hash({
        "draft_id": draft["draft_id"],
        "editable": draft["editable"],
        "planner_review": draft["planner_review"],
        "source_fingerprint": draft["source_fingerprint"],
        "scientific_target": target,
    })
    return draft


def validate_draft(draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    errors = _ORIGINAL_VALIDATE(draft)
    target = draft.get("scientific_target")
    if target is None:
        return errors
    valid, failures = validate_scientific_target(target)
    for reason in failures if not valid else ():
        errors.append({
            "field": "scientific_target",
            "reason": reason,
        })
    if draft.get("scientific_target_hash") != target.get("target_hash"):
        errors.append({
            "field": "scientific_target_hash",
            "reason": "SCIENTIFIC_TARGET_REFERENCE_HASH_MISMATCH",
        })
    return errors


def apply_review_editor(
    drafts: Dict[str, Dict[str, Any]],
    editor_payload: Dict[str, Any],
) -> Dict[str, Any]:
    result = _ORIGINAL_APPLY_REVIEW(drafts, editor_payload)
    for draft in drafts.values():
        target = draft.get("scientific_target")
        if not isinstance(target, dict):
            continue
        draft["draft_hash"] = legacy.canonical_hash({
            "draft_id": draft["draft_id"],
            "editable": draft["editable"],
            "planner_review": draft["planner_review"],
            "source_fingerprint": draft["source_fingerprint"],
            "scientific_target": target,
        })
    return result


def main() -> int:
    legacy.build_default_draft = build_default_draft
    legacy.validate_draft = validate_draft
    legacy.apply_review_editor = apply_review_editor
    return int(legacy.main())


if __name__ == "__main__":
    raise SystemExit(main())
