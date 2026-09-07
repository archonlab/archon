#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VERSION = "1.1"
TITLE = "ARCHON Stage 6.3 Approved Draft → Experiment Plan Commit"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def normalize_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def build_request_template(
    drafts_payload: Dict[str, Any],
    existing: Dict[str, Any],
) -> Dict[str, Any]:
    approved = [
        item
        for item in as_list(drafts_payload.get("drafts"))
        if isinstance(item, dict)
        and item.get("status") == "DRAFT_APPROVED"
        and item.get("source_active") is True
        and as_dict(item.get("validation")).get("valid") is True
    ]

    selected = approved[0] if len(approved) == 1 else None
    return {
        "schema": "archon_experiment_plan_commit_request_v1",
        "commit": False,
        "commit_id": None,
        "draft_id": selected.get("draft_id") if selected else None,
        "expected_draft_hash": (
            selected.get("draft_hash") if selected else None
        ),
        "expected_drafts_file_hash": drafts_payload.get("content_hash"),
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_commit_id": existing.get(
            "last_consumed_commit_id"
        ),
        "instructions": {
            "required_confirmation": "COMMIT_EXPERIMENT_PLAN",
            "approved_active_valid_draft_required": True,
            "execution_authorized_after_commit": False,
            "manual_request_required": True,
            "inactive_template_auto_refresh": True,
        },
    }


def validate_approved_draft(draft: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if draft.get("status") != "DRAFT_APPROVED":
        errors.append("DRAFT_NOT_APPROVED")
    if draft.get("source_active") is not True:
        errors.append("SOURCE_INACTIVE")
    if as_dict(draft.get("validation")).get("valid") is not True:
        errors.append("DRAFT_VALIDATION_FAILED")

    editable = as_dict(draft.get("editable"))
    for field in ("title", "experiment_type", "hypothesis"):
        if not normalize_text(editable.get(field)):
            errors.append(f"REQUIRED_FIELD_MISSING:{field}")

    for field in ("variables", "controls", "protocol", "evidence_channels"):
        if not as_list(editable.get(field)):
            errors.append(f"REQUIRED_LIST_EMPTY:{field}")

    provenance = as_dict(draft.get("provenance"))
    for field in (
        "source_action_id",
        "source_proposal_id",
        "source_review_id",
        "source_commit_id",
        "source_application_id",
        "source_manifest_id",
        "action_snapshot_hash",
    ):
        if not provenance.get(field):
            errors.append(f"PROVENANCE_MISSING:{field}")

    if as_dict(draft.get("policy")).get("execution_authorized") is not False:
        errors.append("DRAFT_POLICY_EXECUTION_BOUNDARY_INVALID")

    return errors


def build_plan_manifest(
    draft: Dict[str, Any],
    commit_id: str,
    requested_by: str,
) -> Dict[str, Any]:
    editable = as_dict(draft.get("editable"))
    provenance = as_dict(draft.get("provenance"))
    planner_review = as_dict(draft.get("planner_review"))

    immutable_plan = {
        "plan_id": (
            f"EXP-PLAN-"
            f"{canonical_hash({'draft_id': draft.get('draft_id'), 'commit_id': commit_id})[:16].upper()}"
        ),
        "draft_id": draft.get("draft_id"),
        "intake_id": draft.get("intake_id"),
        "title": editable.get("title"),
        "experiment_type": editable.get("experiment_type"),
        "hypothesis": editable.get("hypothesis"),
        "target_description": editable.get("target_description"),
        "variables": as_list(editable.get("variables")),
        "controls": as_list(editable.get("controls")),
        "protocol": as_list(editable.get("protocol")),
        "success_criteria": as_list(editable.get("success_criteria")),
        "evidence_channels": as_list(editable.get("evidence_channels")),
        "runtime_hint": editable.get("runtime_hint"),
        "cost_hint": editable.get("cost_hint"),
        "automation_hint": editable.get("automation_hint"),
        "priority": editable.get("priority"),
        "strategic_score": editable.get("strategic_score"),
        "planner_notes": editable.get("notes"),
        "planner_review": {
            "decision": planner_review.get("decision"),
            "reviewed_at": planner_review.get("reviewed_at"),
            "reviewed_by": planner_review.get("reviewed_by"),
            "decision_reason": planner_review.get("decision_reason"),
        },
        "provenance": provenance,
        "execution_policy": {
            "execution_authorized": False,
            "requires_separate_launch_authorization": True,
            "requires_runtime_materialization": True,
            "governance_provenance_immutable": True,
        },
    }
    plan_hash = canonical_hash(immutable_plan)

    return {
        "schema": "archon_experiment_plan_manifest_v1",
        "version": VERSION,
        "commit_id": commit_id,
        "committed_at": now_iso(),
        "committed_by": requested_by,
        "source_draft_hash": draft.get("draft_hash"),
        "plan_hash": plan_hash,
        "plan": immutable_plan,
        "policy": {
            "immutable_manifest": True,
            "execution_authorized": False,
            "does_not_execute_experiment": True,
            "does_not_change_governance_state": True,
            "does_not_change_scientific_metrics": True,
        },
    }


def commit_plan(
    experiments_root: Path,
    drafts_payload: Dict[str, Any],
    request: Dict[str, Any],
    existing_registry: Dict[str, Any],
) -> Dict[str, Any]:
    if request.get("commit") is not True:
        return {
            "schema": "archon_experiment_plan_commit_result_v1",
            "status": "NO_COMMIT_REQUEST",
            "committed": False,
            "reason": None,
        }

    commit_id = normalize_text(request.get("commit_id"))
    draft_id = normalize_text(request.get("draft_id"))
    requested_by = normalize_text(request.get("requested_by"))
    confirmation = normalize_text(request.get("confirmation"))

    failures: List[str] = []
    if not commit_id:
        failures.append("COMMIT_ID_MISSING")
    if not draft_id:
        failures.append("DRAFT_ID_MISSING")
    if not requested_by:
        failures.append("REQUESTED_BY_MISSING")
    if confirmation != "COMMIT_EXPERIMENT_PLAN":
        failures.append("CONFIRMATION_INVALID")

    if request.get("expected_drafts_file_hash") != drafts_payload.get(
        "content_hash"
    ):
        failures.append("DRAFTS_FILE_HASH_MISMATCH")

    drafts = {
        str(item.get("draft_id")): item
        for item in as_list(drafts_payload.get("drafts"))
        if isinstance(item, dict) and item.get("draft_id")
    }
    draft = drafts.get(draft_id or "")
    if draft is None:
        failures.append("DRAFT_NOT_FOUND")
    else:
        if request.get("expected_draft_hash") != draft.get("draft_hash"):
            failures.append("DRAFT_HASH_MISMATCH")
        failures.extend(validate_approved_draft(draft))

    existing_commits = {
        str(item.get("commit_id")): item
        for item in as_list(existing_registry.get("commits"))
        if isinstance(item, dict) and item.get("commit_id")
    }
    existing_by_draft = {
        str(item.get("draft_id")): item
        for item in as_list(existing_registry.get("commits"))
        if isinstance(item, dict) and item.get("draft_id")
    }
    if commit_id and commit_id in existing_commits:
        failures.append("COMMIT_ID_REPLAY")
    if draft_id and draft_id in existing_by_draft:
        failures.append("DRAFT_ALREADY_COMMITTED")

    if failures:
        return {
            "schema": "archon_experiment_plan_commit_result_v1",
            "status": "REFUSED",
            "committed": False,
            "commit_id": commit_id,
            "draft_id": draft_id,
            "reasons": sorted(set(failures)),
        }

    assert draft is not None
    manifest = build_plan_manifest(draft, commit_id, requested_by)

    manifests_root = experiments_root / "PlanManifests"
    manifest_path = manifests_root / f"{manifest['plan']['plan_id']}.json"
    if manifest_path.exists():
        return {
            "schema": "archon_experiment_plan_commit_result_v1",
            "status": "REFUSED",
            "committed": False,
            "commit_id": commit_id,
            "draft_id": draft_id,
            "reasons": ["PLAN_MANIFEST_ALREADY_EXISTS"],
        }

    atomic_write_json(manifest_path, manifest)

    receipt = {
        "schema": "archon_experiment_plan_commit_receipt_v1",
        "status": "COMMITTED",
        "commit_id": commit_id,
        "draft_id": draft_id,
        "plan_id": manifest["plan"]["plan_id"],
        "plan_hash": manifest["plan_hash"],
        "manifest_hash": canonical_hash(manifest),
        "manifest_path": str(manifest_path),
        "committed_at": manifest["committed_at"],
        "committed_by": requested_by,
        "execution_authorized": False,
    }
    receipts_root = experiments_root / "PlanCommitReceipts"
    receipt_path = receipts_root / f"{commit_id}.json"
    atomic_write_json(receipt_path, receipt)

    return {
        "schema": "archon_experiment_plan_commit_result_v1",
        "status": "COMMITTED",
        "committed": True,
        "commit_id": commit_id,
        "draft_id": draft_id,
        "plan_id": manifest["plan"]["plan_id"],
        "plan_hash": manifest["plan_hash"],
        "manifest_hash": receipt["manifest_hash"],
        "manifest_path": str(manifest_path),
        "receipt_path": str(receipt_path),
        "execution_authorized": False,
    }


def verify_receipt(result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("status") != "COMMITTED":
        return {
            "schema": "archon_experiment_plan_commit_receipt_verification_v1",
            "status": "NO_COMMITTED_PLAN",
            "verified": False,
        }

    manifest_path = Path(str(result.get("manifest_path")))
    receipt_path = Path(str(result.get("receipt_path")))
    manifest = load_json(manifest_path, {})
    receipt = load_json(receipt_path, {})

    failures: List[str] = []
    if not manifest:
        failures.append("MANIFEST_MISSING_OR_INVALID")
    if not receipt:
        failures.append("RECEIPT_MISSING_OR_INVALID")

    if manifest:
        if canonical_hash(manifest) != result.get("manifest_hash"):
            failures.append("MANIFEST_HASH_MISMATCH")
        if manifest.get("plan_hash") != result.get("plan_hash"):
            failures.append("PLAN_HASH_MISMATCH")
        if canonical_hash(as_dict(manifest.get("plan"))) != manifest.get(
            "plan_hash"
        ):
            failures.append("PLAN_CONTENT_HASH_MISMATCH")
        if as_dict(manifest.get("policy")).get(
            "execution_authorized"
        ) is not False:
            failures.append("MANIFEST_EXECUTION_POLICY_INVALID")

    if receipt:
        if receipt.get("commit_id") != result.get("commit_id"):
            failures.append("RECEIPT_COMMIT_ID_MISMATCH")
        if receipt.get("plan_id") != result.get("plan_id"):
            failures.append("RECEIPT_PLAN_ID_MISMATCH")
        if receipt.get("plan_hash") != result.get("plan_hash"):
            failures.append("RECEIPT_PLAN_HASH_MISMATCH")
        if receipt.get("manifest_hash") != result.get("manifest_hash"):
            failures.append("RECEIPT_MANIFEST_HASH_MISMATCH")
        if receipt.get("execution_authorized") is not False:
            failures.append("RECEIPT_EXECUTION_POLICY_INVALID")

    return {
        "schema": "archon_experiment_plan_commit_receipt_verification_v1",
        "status": "VERIFIED" if not failures else "FAILED",
        "verified": not failures,
        "failures": failures,
        "commit_id": result.get("commit_id"),
        "draft_id": result.get("draft_id"),
        "plan_id": result.get("plan_id"),
        "plan_hash": result.get("plan_hash"),
        "manifest_hash": result.get("manifest_hash"),
    }


def update_registry(
    existing: Dict[str, Any],
    result: Dict[str, Any],
    verification: Dict[str, Any],
) -> Dict[str, Any]:
    commits = [
        item
        for item in as_list(existing.get("commits"))
        if isinstance(item, dict)
    ]

    if result.get("status") == "COMMITTED":
        commits.append({
            "commit_id": result.get("commit_id"),
            "draft_id": result.get("draft_id"),
            "plan_id": result.get("plan_id"),
            "plan_hash": result.get("plan_hash"),
            "manifest_hash": result.get("manifest_hash"),
            "manifest_path": result.get("manifest_path"),
            "receipt_path": result.get("receipt_path"),
            "verification_status": verification.get("status"),
            "committed_at": now_iso(),
            "execution_authorized": False,
        })

    unique: Dict[str, Dict[str, Any]] = {}
    for item in commits:
        commit_id = str(item.get("commit_id") or "")
        if commit_id:
            unique[commit_id] = item

    ordered = sorted(unique.values(), key=lambda x: str(x.get("commit_id")))
    payload = {
        "schema": "archon_experiment_plan_registry_v1",
        "version": VERSION,
        "updated_at": now_iso(),
        "commit_count": len(ordered),
        "commits": ordered,
        "policy": {
            "registry_is_non_executable": True,
            "execution_authorized": False,
            "separate_launch_stage_required": True,
        },
    }
    payload["content_hash"] = canonical_hash({
        "commits": ordered,
        "policy": payload["policy"],
    })
    return payload


def render_markdown(
    result: Dict[str, Any],
    verification: Dict[str, Any],
    registry: Dict[str, Any],
) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Commit status: **{result.get('status')}**",
        f"- Verification: **{verification.get('status')}**",
        f"- Commit ID: `{result.get('commit_id') or '-'}`",
        f"- Draft ID: `{result.get('draft_id') or '-'}`",
        f"- Plan ID: `{result.get('plan_id') or '-'}`",
        f"- Registry commits: **{registry.get('commit_count', 0)}**",
        "",
        "## Safety boundary",
        "",
        "- The committed plan is immutable.",
        "- Commit does not execute the experiment.",
        "- Execution remains unauthorized.",
        "- A separate launch authorization stage is required.",
        "- Governance and scientific state are not modified.",
        "",
    ]
    if result.get("reasons"):
        lines.extend([
            "## Refusal reasons",
            "",
        ])
        for reason in result.get("reasons", []):
            lines.append(f"- `{reason}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument(
        "--analysis-root",
        required=True,
        help="Path to Results/Analysis",
    )
    parser.add_argument(
        "--drafts",
        default=None,
        help=(
            "Planner drafts JSON. Default: "
            "<analysis-root>/Experiments/experiment_planner_drafts.json"
        ),
    )
    parser.add_argument(
        "--request",
        default=None,
        help=(
            "Plan commit request JSON. Default: "
            "<analysis-root>/Experiments/experiment_plan_commit_request.json"
        ),
    )
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).resolve()
    experiments_root = analysis_root / "Experiments"
    drafts_path = (
        Path(args.drafts).resolve()
        if args.drafts
        else experiments_root / "experiment_planner_drafts.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments_root / "experiment_plan_commit_request.json"
    )
    registry_path = experiments_root / "experiment_plan_registry.json"
    result_path = experiments_root / "experiment_plan_commit_result.json"
    verification_path = (
        experiments_root
        / "experiment_plan_commit_receipt_verification.json"
    )
    markdown_path = experiments_root / "experiment_plan_commit.md"

    drafts_payload = load_json(drafts_path, {})
    if not isinstance(drafts_payload, dict) or not drafts_payload:
        raise RuntimeError(f"Missing or invalid planner drafts: {drafts_path}")

    existing_registry = load_json(registry_path, {})
    if not isinstance(existing_registry, dict):
        existing_registry = {}

    existing_request = load_json(request_path, {})
    if not isinstance(existing_request, dict):
        existing_request = {}

    # Refresh only inactive request templates so newly approved drafts are
    # discoverable after restart or sandbox copy. Never rewrite an active
    # manual commit request.
    if (
        not request_path.exists()
        or existing_request.get("commit") is not True
    ):
        atomic_write_json(
            request_path,
            build_request_template(drafts_payload, existing_request),
        )

    request = load_json(request_path, {})
    if not isinstance(request, dict):
        request = {}

    result = commit_plan(
        experiments_root,
        drafts_payload,
        request,
        existing_registry,
    )
    verification = verify_receipt(result)
    registry = update_registry(
        existing_registry,
        result,
        verification,
    )

    atomic_write_json(result_path, result)
    atomic_write_json(verification_path, verification)
    atomic_write_json(registry_path, registry)
    markdown_path.write_text(
        render_markdown(result, verification, registry),
        encoding="utf-8",
    )

    if result.get("status") == "COMMITTED":
        atomic_write_json(
            request_path,
            {
                "schema": "archon_experiment_plan_commit_request_v1",
                "commit": False,
                "commit_id": None,
                "draft_id": None,
                "expected_draft_hash": None,
                "expected_drafts_file_hash": None,
                "requested_at": None,
                "requested_by": None,
                "confirmation": None,
                "last_consumed_commit_id": result.get("commit_id"),
                "instructions": {
                    "required_confirmation": "COMMIT_EXPERIMENT_PLAN",
                    "approved_active_valid_draft_required": True,
                    "execution_authorized_after_commit": False,
                    "manual_request_required": True,
                    "inactive_template_auto_refresh": True,
                },
            },
        )

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Status:       {result.get('status')}")
    print(f"Verification: {verification.get('status')}")
    print(f"Commit ID:    {result.get('commit_id') or '-'}")
    print(f"Draft ID:     {result.get('draft_id') or '-'}")
    print(f"Plan ID:      {result.get('plan_id') or '-'}")
    print(f"Registry:     {registry.get('commit_count', 0)} committed plans")
    print("Execution:    NOT AUTHORIZED")
    print(f"Result JSON:  {result_path}")
    print(f"Registry:     {registry_path}")
    print(f"Request:      {request_path}")
    print("=" * 72)

    return 0 if result.get("status") != "REFUSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
