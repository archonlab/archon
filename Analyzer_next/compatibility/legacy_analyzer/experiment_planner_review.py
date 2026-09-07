#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VERSION = "1.0"
TITLE = "ARCHON Stage 6.2 Planner Review and Experiment Draft Generation"


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
        ) + "\n",
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


def build_default_draft(
    intake_record: Dict[str, Any],
    prior: Dict[str, Any],
) -> Dict[str, Any]:
    intake_id = str(intake_record.get("intake_id") or "")
    action = as_dict(intake_record.get("action"))
    intent = as_dict(intake_record.get("experiment_intent"))
    provenance = as_dict(intake_record.get("provenance"))

    source_fingerprint = str(
        intake_record.get("fingerprint") or
        canonical_hash({
            "intake_id": intake_id,
            "action": action,
            "intent": intent,
            "provenance": provenance,
        })
    )
    draft_id = (
        prior.get("draft_id")
        or f"EXD-{canonical_hash({'intake_id': intake_id})[:16].upper()}"
    )

    editable = as_dict(prior.get("editable"))
    if not editable:
        editable = {
            "title": (
                f"Experiment for {action.get('action_id')}: "
                f"{action.get('title') or 'Untitled action'}"
            ),
            "experiment_type": intent.get("experiment_type"),
            "hypothesis": intent.get("hypothesis_prompt"),
            "target_description": intent.get("target_description"),
            "variables": as_list(intent.get("variables")),
            "controls": as_list(intent.get("required_controls")),
            "protocol": as_list(intent.get("protocol_requirements")),
            "success_criteria": as_list(intent.get("success_criteria")),
            "evidence_channels": as_list(intent.get("evidence_channels")),
            "runtime_hint": intent.get("runtime_hint"),
            "cost_hint": intent.get("cost_hint"),
            "automation_hint": intent.get("automation_hint"),
            "priority": intent.get("priority"),
            "strategic_score": intent.get("strategic_score"),
            "notes": None,
        }

    planner_review = as_dict(prior.get("planner_review"))
    if not planner_review:
        planner_review = {
            "decision": "PENDING",
            "reviewed_at": None,
            "reviewed_by": None,
            "decision_reason": None,
            "required_changes": [],
        }

    source_active = bool(intake_record.get("active"))
    source_status = str(intake_record.get("status") or "")

    if source_active:
        status = (
            prior.get("status")
            if prior.get("status") in {
                "DRAFT_PENDING_REVIEW",
                "DRAFT_APPROVED",
                "DRAFT_CHANGES_REQUESTED",
                "DRAFT_REJECTED",
            }
            else "DRAFT_PENDING_REVIEW"
        )
    else:
        status = "SOURCE_INACTIVE"

    draft_hash = canonical_hash({
        "draft_id": draft_id,
        "editable": editable,
        "planner_review": planner_review,
        "source_fingerprint": source_fingerprint,
    })

    return {
        "draft_id": draft_id,
        "intake_id": intake_id,
        "source_fingerprint": source_fingerprint,
        "status": status,
        "source_active": source_active,
        "source_status": source_status,
        "created_at": prior.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "editable": editable,
        "planner_review": planner_review,
        "provenance": {
            "source_action_id": provenance.get("source_action_id"),
            "source_proposal_id": provenance.get("source_proposal_id"),
            "source_review_id": provenance.get("source_review_id"),
            "source_commit_id": provenance.get("source_commit_id"),
            "source_application_id": provenance.get("source_application_id"),
            "source_manifest_id": provenance.get("source_manifest_id"),
            "source_recommendation_ids": as_list(
                provenance.get("source_recommendation_ids")
            ),
            "source_principle_ids": as_list(
                provenance.get("source_principle_ids")
            ),
            "source_consensus_signals": as_list(
                provenance.get("source_consensus_signals")
            ),
            "action_snapshot_hash": provenance.get("action_snapshot_hash"),
            "director_report_path": provenance.get("director_report_path"),
        },
        "draft_hash": draft_hash,
        "policy": {
            "editable_by_planner": True,
            "governance_fields_immutable": True,
            "execution_authorized": False,
            "creates_experiment_record": False,
            "requires_explicit_planner_decision": True,
        },
    }


def validate_draft(draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    editable = as_dict(draft.get("editable"))
    provenance = as_dict(draft.get("provenance"))

    required_text = (
        "title",
        "experiment_type",
        "hypothesis",
    )
    for field_name in required_text:
        if not normalize_text(editable.get(field_name)):
            errors.append({
                "field": field_name,
                "reason": "REQUIRED_TEXT_MISSING",
            })

    required_lists = (
        "variables",
        "controls",
        "protocol",
        "evidence_channels",
    )
    for field_name in required_lists:
        if not as_list(editable.get(field_name)):
            errors.append({
                "field": field_name,
                "reason": "REQUIRED_LIST_EMPTY",
            })

    required_provenance = (
        "source_action_id",
        "source_proposal_id",
        "source_review_id",
        "source_commit_id",
        "source_application_id",
        "source_manifest_id",
        "action_snapshot_hash",
    )
    for field_name in required_provenance:
        if not provenance.get(field_name):
            errors.append({
                "field": f"provenance.{field_name}",
                "reason": "PROVENANCE_MISSING",
            })

    if draft.get("source_active") is not True:
        errors.append({
            "field": "source_active",
            "reason": "SOURCE_NOT_ACTIVE",
        })

    return errors


def load_review_editor(path: Path) -> Dict[str, Any]:
    payload = load_json(path, {})
    return payload if isinstance(payload, dict) else {}


def apply_review_editor(
    drafts: Dict[str, Dict[str, Any]],
    editor_payload: Dict[str, Any],
) -> Dict[str, Any]:
    rows = as_list(editor_payload.get("rows"))
    applied = 0
    blocked: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        draft_id = str(row.get("draft_id") or "")
        draft = drafts.get(draft_id)
        if draft is None:
            blocked.append({
                "draft_id": draft_id or None,
                "reason": "DRAFT_NOT_FOUND",
            })
            continue

        expected_hash = row.get("expected_draft_hash")
        if expected_hash and expected_hash != draft.get("draft_hash"):
            blocked.append({
                "draft_id": draft_id,
                "reason": "DRAFT_HASH_MISMATCH",
                "expected": expected_hash,
                "actual": draft.get("draft_hash"),
            })
            continue

        if not draft.get("source_active"):
            blocked.append({
                "draft_id": draft_id,
                "reason": "SOURCE_INACTIVE",
            })
            continue

        editable_patch = as_dict(row.get("editable_patch"))
        allowed_fields = {
            "title",
            "experiment_type",
            "hypothesis",
            "target_description",
            "variables",
            "controls",
            "protocol",
            "success_criteria",
            "evidence_channels",
            "runtime_hint",
            "cost_hint",
            "automation_hint",
            "priority",
            "strategic_score",
            "notes",
        }
        for key, value in editable_patch.items():
            if key in allowed_fields:
                draft["editable"][key] = value

        decision = str(row.get("decision") or "").upper()
        if decision not in {
            "PENDING",
            "APPROVED",
            "CHANGES_REQUESTED",
            "REJECTED",
        }:
            blocked.append({
                "draft_id": draft_id,
                "reason": "INVALID_DECISION",
                "actual": decision,
            })
            continue

        draft["planner_review"] = {
            "decision": decision,
            "reviewed_at": row.get("reviewed_at") or now_iso(),
            "reviewed_by": row.get("reviewed_by"),
            "decision_reason": row.get("decision_reason"),
            "required_changes": as_list(row.get("required_changes")),
        }

        status_map = {
            "PENDING": "DRAFT_PENDING_REVIEW",
            "APPROVED": "DRAFT_APPROVED",
            "CHANGES_REQUESTED": "DRAFT_CHANGES_REQUESTED",
            "REJECTED": "DRAFT_REJECTED",
        }
        draft["status"] = status_map[decision]
        draft["updated_at"] = now_iso()
        draft["draft_hash"] = canonical_hash({
            "draft_id": draft["draft_id"],
            "editable": draft["editable"],
            "planner_review": draft["planner_review"],
            "source_fingerprint": draft["source_fingerprint"],
        })
        applied += 1

    return {
        "schema": "archon_planner_review_import_result_v1",
        "applied_count": applied,
        "blocked_count": len(blocked),
        "blocked": blocked,
    }


def build_planner_review(
    intake_path: Path,
    drafts_path: Path,
    editor_path: Path,
) -> Dict[str, Any]:
    intake = load_json(intake_path, {})
    if not isinstance(intake, dict) or not intake:
        raise RuntimeError(f"Missing or invalid planner intake: {intake_path}")

    existing = load_json(drafts_path, {})
    if not isinstance(existing, dict):
        existing = {}

    existing_by_intake = {
        str(item.get("intake_id")): item
        for item in as_list(existing.get("drafts"))
        if isinstance(item, dict) and item.get("intake_id")
    }

    drafts: Dict[str, Dict[str, Any]] = {}
    for intake_record in as_list(intake.get("records")):
        if not isinstance(intake_record, dict):
            continue
        intake_id = str(intake_record.get("intake_id") or "")
        if not intake_id:
            continue

        prior = existing_by_intake.get(intake_id, {})
        draft = build_default_draft(intake_record, prior)
        drafts[draft["draft_id"]] = draft

    editor_payload = load_review_editor(editor_path)
    import_result = apply_review_editor(drafts, editor_payload)

    validation_rows: List[Dict[str, Any]] = []
    for draft in drafts.values():
        errors = validate_draft(draft)
        validation_rows.append({
            "draft_id": draft.get("draft_id"),
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "errors": errors,
        })

    validation_by_id = {
        row["draft_id"]: row
        for row in validation_rows
    }

    for draft in drafts.values():
        validation = validation_by_id[draft["draft_id"]]
        draft["validation"] = validation
        if (
            draft.get("source_active")
            and draft.get("status") == "DRAFT_APPROVED"
            and not validation.get("valid")
        ):
            draft["status"] = "DRAFT_APPROVED_INVALID"

    ordered = sorted(
        drafts.values(),
        key=lambda item: (
            not bool(item.get("source_active")),
            str(item.get("draft_id")),
        ),
    )

    counts = {
        "draft_count": len(ordered),
        "active_source_count": sum(
            1 for item in ordered if item.get("source_active")
        ),
        "inactive_source_count": sum(
            1 for item in ordered if not item.get("source_active")
        ),
        "pending_count": sum(
            1 for item in ordered
            if item.get("status") == "DRAFT_PENDING_REVIEW"
        ),
        "approved_count": sum(
            1 for item in ordered
            if item.get("status") == "DRAFT_APPROVED"
        ),
        "changes_requested_count": sum(
            1 for item in ordered
            if item.get("status") == "DRAFT_CHANGES_REQUESTED"
        ),
        "rejected_count": sum(
            1 for item in ordered
            if item.get("status") == "DRAFT_REJECTED"
        ),
        "source_inactive_count": sum(
            1 for item in ordered
            if item.get("status") == "SOURCE_INACTIVE"
        ),
        "valid_count": sum(
            1 for row in validation_rows if row.get("valid")
        ),
        "invalid_count": sum(
            1 for row in validation_rows if not row.get("valid")
        ),
    }

    payload = {
        "schema": "archon_experiment_planner_drafts_v1",
        "version": VERSION,
        "generated_at": now_iso(),
        "mode": "PLANNER_REVIEW_ONLY",
        "summary": counts,
        "drafts": ordered,
        "validation": validation_rows,
        "review_import_result": import_result,
        "source_intake": {
            "path": str(intake_path),
            "content_hash": intake.get("content_hash"),
            "lifecycle_status": as_dict(
                intake.get("summary")
            ).get("lifecycle_status"),
        },
        "policy": {
            "drafts_are_non_executable": True,
            "planner_review_required": True,
            "governance_provenance_immutable": True,
            "does_not_change_governance_state": True,
            "does_not_change_scientific_metrics": True,
            "does_not_create_experiment_records": True,
        },
    }
    payload["content_hash"] = canonical_hash({
        "summary": counts,
        "drafts": ordered,
        "validation": validation_rows,
        "source_intake": payload["source_intake"],
    })
    return payload


def build_editor_template(payload: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    for draft in as_list(payload.get("drafts")):
        if not isinstance(draft, dict):
            continue
        rows.append({
            "draft_id": draft.get("draft_id"),
            "expected_draft_hash": draft.get("draft_hash"),
            "decision": as_dict(
                draft.get("planner_review")
            ).get("decision") or "PENDING",
            "reviewed_at": None,
            "reviewed_by": None,
            "decision_reason": None,
            "required_changes": [],
            "editable_patch": {},
            "instructions": {
                "allowed_decisions": [
                    "PENDING",
                    "APPROVED",
                    "CHANGES_REQUESTED",
                    "REJECTED",
                ],
                "editable_fields": [
                    "title",
                    "experiment_type",
                    "hypothesis",
                    "target_description",
                    "variables",
                    "controls",
                    "protocol",
                    "success_criteria",
                    "evidence_channels",
                    "runtime_hint",
                    "cost_hint",
                    "automation_hint",
                    "priority",
                    "strategic_score",
                    "notes",
                ],
                "immutable_fields": [
                    "draft_id",
                    "intake_id",
                    "provenance",
                    "source_fingerprint",
                ],
            },
        })

    return {
        "schema": "archon_planner_review_editor_v1",
        "generated_at": now_iso(),
        "mode": "SAFE_EDITOR",
        "rows": rows,
    }


def render_markdown(payload: Dict[str, Any]) -> str:
    summary = as_dict(payload.get("summary"))
    lines = [
        f"# {TITLE}",
        "",
        f"- Generated: `{payload.get('generated_at')}`",
        f"- Mode: **{payload.get('mode')}**",
        f"- Drafts: **{summary.get('draft_count', 0)}**",
        f"- Pending: **{summary.get('pending_count', 0)}**",
        f"- Approved: **{summary.get('approved_count', 0)}**",
        f"- Changes requested: **{summary.get('changes_requested_count', 0)}**",
        f"- Rejected: **{summary.get('rejected_count', 0)}**",
        f"- Source inactive: **{summary.get('source_inactive_count', 0)}**",
        f"- Valid: **{summary.get('valid_count', 0)}**",
        f"- Invalid: **{summary.get('invalid_count', 0)}**",
        "",
        "## Drafts",
        "",
    ]

    drafts = as_list(payload.get("drafts"))
    if not drafts:
        lines.append("No planner drafts are available.")
    else:
        lines.extend([
            "| Draft | Intake | Status | Type | Valid |",
            "| --- | --- | --- | --- | --- |",
        ])
        for draft in drafts:
            editable = as_dict(draft.get("editable"))
            validation = as_dict(draft.get("validation"))
            lines.append(
                f"| `{draft.get('draft_id')}` | "
                f"`{draft.get('intake_id')}` | "
                f"{draft.get('status')} | "
                f"{editable.get('experiment_type')} | "
                f"{validation.get('valid')} |"
            )

    lines.extend([
        "",
        "## Safety boundary",
        "",
        "- Draft generation does not create an executable experiment.",
        "- Planner may edit experiment design fields only.",
        "- Governance provenance is immutable.",
        "- An explicit planner decision is required.",
        "- Approved drafts remain non-executable until a later commit stage.",
        "",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument(
        "--analysis-root",
        required=True,
        help="Path to Results/Analysis",
    )
    parser.add_argument(
        "--intake",
        default=None,
        help=(
            "Planner intake JSON. Default: "
            "<analysis-root>/Experiments/experiment_planner_intake.json"
        ),
    )
    parser.add_argument(
        "--drafts-output",
        default=None,
        help=(
            "Draft output JSON. Default: "
            "<analysis-root>/Experiments/experiment_planner_drafts.json"
        ),
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help=(
            "Draft output Markdown. Default: "
            "<analysis-root>/Experiments/experiment_planner_drafts.md"
        ),
    )
    parser.add_argument(
        "--editor",
        default=None,
        help=(
            "Planner review editor JSON. Default: "
            "<analysis-root>/Experiments/experiment_planner_review_editor.json"
        ),
    )
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).resolve()
    experiments_root = analysis_root / "Experiments"

    intake_path = (
        Path(args.intake).resolve()
        if args.intake
        else experiments_root / "experiment_planner_intake.json"
    )
    drafts_path = (
        Path(args.drafts_output).resolve()
        if args.drafts_output
        else experiments_root / "experiment_planner_drafts.json"
    )
    markdown_path = (
        Path(args.markdown_output).resolve()
        if args.markdown_output
        else experiments_root / "experiment_planner_drafts.md"
    )
    editor_path = (
        Path(args.editor).resolve()
        if args.editor
        else experiments_root / "experiment_planner_review_editor.json"
    )

    payload = build_planner_review(
        intake_path,
        drafts_path,
        editor_path,
    )
    atomic_write_json(drafts_path, payload)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(
        render_markdown(payload),
        encoding="utf-8",
    )

    if not editor_path.exists():
        atomic_write_json(
            editor_path,
            build_editor_template(payload),
        )

    summary = as_dict(payload.get("summary"))
    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(
        f"Drafts:       {summary.get('draft_count', 0)} total | "
        f"{summary.get('pending_count', 0)} pending | "
        f"{summary.get('approved_count', 0)} approved"
    )
    print(
        f"Validation:   {summary.get('valid_count', 0)} valid | "
        f"{summary.get('invalid_count', 0)} invalid"
    )
    print(
        f"Sources:      {summary.get('active_source_count', 0)} active | "
        f"{summary.get('inactive_source_count', 0)} inactive"
    )
    print("Draft mode:   PLANNER_REVIEW_ONLY")
    print(f"Output JSON:  {drafts_path}")
    print(f"Output MD:    {markdown_path}")
    print(f"Editor JSON:  {editor_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
