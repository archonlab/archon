#!/usr/bin/env python3
"""Read-only diagnostic for ARCHON Observer Launcher 2.0 Experiments pipeline.

Inspects the real Research Director / planner / runtime registries and canonical
telemetry SQLite without modifying project state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from collections import Counter, defaultdict
from typing import Any
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.observer.experiment_runtime_policy_compat_fix4 import inspect_runtime_policy


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        return {"__read_error__": f"{type(exc).__name__}: {exc}"}


def rows(container: Any, *keys: str) -> list[dict[str, Any]]:
    cur = container
    for key in keys:
        if not isinstance(cur, dict):
            return []
        cur = cur.get(key)
    return [item for item in cur if isinstance(item, dict)] if isinstance(cur, list) else []


def s(value: Any, default: str = "-") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def sqlite_snapshot(db: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": str(db),
        "exists": db.is_file(),
        "tables": [],
        "counts": {},
        "experiment_ids": [],
        "error": None,
    }
    if not db.is_file():
        return out
    try:
        uri = f"file:{db.as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=0.25)
        con.row_factory = sqlite3.Row
        try:
            tables = {str(r[0]) for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            out["tables"] = sorted(tables)
            for table in ("experiments", "experimental_conditions", "experiment_runs"):
                if table in tables:
                    out["counts"][table] = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                else:
                    out["counts"][table] = None
            if "experiments" in tables:
                out["experiment_ids"] = [
                    str(r[0]) for r in con.execute("SELECT experiment_id FROM experiments ORDER BY experiment_id")
                ]
        finally:
            con.close()
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def inspect(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    analysis = root / "Results" / "Analysis"
    experiments = analysis / "Experiments"
    db = root / "Results" / "Universe_Search" / "observation_logs" / "telemetry.sqlite"

    report = load_json(analysis / "research_director_report.json") or {}
    actions = {s(x.get("action_id"), ""): x for x in rows(report, "actions") if x.get("action_id")}
    proposals = rows(report, "recommendation_patch_proposals", "proposals")
    validations = {s(x.get("proposal_id"), ""): x for x in rows(report, "patch_proposal_validation", "validations") if x.get("proposal_id")}
    resolutions = {s(x.get("proposal_id"), ""): x for x in rows(report, "patch_conflict_resolution_plan", "plans") if x.get("proposal_id")}
    reviews = {s(x.get("proposal_id"), ""): x for x in rows(report, "human_review_queue", "queue") if x.get("proposal_id")}

    proposal_rows: list[dict[str, Any]] = []
    validation_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    ui_counts: Counter[str] = Counter()
    for p in proposals:
        pid = s(p.get("proposal_id"), "")
        aid = s(p.get("target_action_id"), "")
        val = s(validations.get(pid, {}).get("status"), "UNKNOWN").upper()
        decision = s(reviews.get(pid, {}).get("decision"), "PENDING_REVIEW").upper()
        if decision == "REJECTED":
            ui = "REJECTED"
        elif decision == "DEFERRED":
            ui = "DEFERRED"
        elif val == "VALID":
            ui = "APPROVED" if decision == "APPROVED" else "READY"
        elif val == "CONFLICTING":
            ui = "NEEDS REVIEW"
        elif val == "BLOCKED":
            ui = "BLOCKED"
        else:
            ui = val
        validation_counts[val] += 1
        decision_counts[decision] += 1
        ui_counts[ui] += 1
        proposal_rows.append({
            "proposal_id": pid,
            "action_id": aid,
            "title": s(actions.get(aid, {}).get("title") or p.get("target_action_title"), pid),
            "validation": val,
            "decision": decision,
            "ui_status": ui,
            "issue_count": int(validations.get(pid, {}).get("issue_count") or 0),
            "resolution_type": s(resolutions.get(pid, {}).get("resolution_type")),
            "preferred_resolution": s(resolutions.get(pid, {}).get("preferred_resolution")),
            "can_prepare": val == "VALID" and decision != "REJECTED",
        })

    decisions_file = load_json(analysis / "human_review_decisions.json") or {}
    decision_records = rows(decisions_file, "records")

    planner_drafts_doc = load_json(experiments / "experiment_planner_drafts.json") or {}
    planner_drafts = rows(planner_drafts_doc, "drafts")
    draft_counts = Counter(s(x.get("status"), "UNKNOWN") for x in planner_drafts)
    drafts_by_proposal: dict[str, int] = defaultdict(int)
    for d in planner_drafts:
        prov = d.get("provenance") if isinstance(d.get("provenance"), dict) else {}
        pid = s(prov.get("source_proposal_id"), "")
        if pid:
            drafts_by_proposal[pid] += 1

    plan_reg = load_json(experiments / "experiment_plan_registry.json") or {}
    plan_commits = rows(plan_reg, "commits")
    target_reg = load_json(experiments / "scientific_target_resolution_registry.json") or {}
    target_resolutions = rows(target_reg, "resolutions")
    runtime_reg = load_json(experiments / "experiment_runtime_registry.json") or {}
    runtime_packages = rows(runtime_reg, "packages")
    runtime_counts = Counter(s(x.get("status"), "UNKNOWN") for x in runtime_packages)
    protocol_reg = load_json(experiments / "scientific_protocol_resolution_registry.json") or {}
    protocol_resolutions = rows(protocol_reg, "resolutions")
    protocol_by_plan = {s(x.get("plan_id"), ""): x for x in protocol_resolutions if x.get("plan_id")}
    runtime_policy_path = experiments / "runtime_materialization_policy.json"
    runtime_policy_state = inspect_runtime_policy(runtime_policy_path)
    plan_entry_by_id = {s(x.get("plan_id"), ""): x for x in plan_commits if x.get("plan_id")}
    target_details = []
    for item in target_resolutions:
        identities = item.get("identities") if isinstance(item.get("identities"), dict) else {}
        plan_id = s(item.get("plan_id"), "")
        manifest_path = Path(str(plan_entry_by_id.get(plan_id, {}).get("manifest_path") or ""))
        manifest = load_json(manifest_path) if manifest_path.is_file() else {}
        plan = manifest.get("plan") if isinstance(manifest, dict) and isinstance(manifest.get("plan"), dict) else {}
        protocol_row = protocol_by_plan.get(plan_id, {})
        target_details.append({
            "plan_id": plan_id or "-",
            "status": s(item.get("status"), "UNKNOWN"),
            "reasons": [str(x) for x in item.get("reasons", [])] if isinstance(item.get("reasons"), list) else [],
            "experiment_id": s(identities.get("experiment_id")),
            "condition_id": s(identities.get("condition_id")),
            "rule_ids": identities.get("rule_ids") if isinstance(identities.get("rule_ids"), list) else [],
            "experiment_type": s(plan.get("experiment_type"), "UNKNOWN"),
            "source_action_id": s((plan.get("provenance") or {}).get("source_action_id") if isinstance(plan.get("provenance"), dict) else None),
            "protocol_status": s(protocol_row.get("status"), "MISSING"),
            "protocol_reasons": [str(x) for x in protocol_row.get("reasons", [])] if isinstance(protocol_row.get("reasons"), list) else [],
        })
    runtime_details = []
    for item in runtime_packages:
        unresolved = []
        package_path = Path(str(item.get("package_path") or ""))
        package = load_json(package_path) if package_path.is_file() else None
        if isinstance(package, dict):
            raw = package.get("unresolved_fields")
            if isinstance(raw, list):
                unresolved = [x for x in raw if isinstance(x, dict)]
        runtime_details.append({
            "runtime_id": s(item.get("runtime_id")),
            "plan_id": s(item.get("plan_id")),
            "status": s(item.get("status"), "UNKNOWN"),
            "unresolved_count": int(item.get("unresolved_count") or len(unresolved)),
            "unresolved_fields": unresolved,
            "run_count": int(item.get("run_count") or 0),
        })

    sqlite = sqlite_snapshot(db)
    sqlite_ids = set(sqlite.get("experiment_ids") or [])
    file_experiment_ids: set[str] = set()
    for r in target_resolutions:
        identities = r.get("identities") if isinstance(r.get("identities"), dict) else {}
        eid = s(identities.get("experiment_id"), "")
        if eid:
            file_experiment_ids.add(eid)

    review_commit_result = load_json(analysis / "human_review_commit_result.json") or {}
    review_receipt = load_json(analysis / "human_review_receipt_verification.json") or {}
    patch_manifest = load_json(analysis / "patch_application_manifest.json") or {}
    patch_result = load_json(analysis / "patch_application_result.json") or {}
    patch_receipt = load_json(analysis / "patch_application_receipt_verification.json") or {}
    lifecycle = load_json(analysis / "patch_lifecycle_closure.json") or {}

    blockers: list[str] = []
    if not (analysis / "research_director_report.json").is_file():
        blockers.append("research_director_report.json is missing")
    if proposals and validation_counts.get("VALID", 0) == 0:
        blockers.append("Research Director currently exposes no VALID proposal, so Prepare/Materialize has no executable input")
    if validation_counts.get("CONFLICTING", 0):
        blockers.append(
            "CONFLICTING proposals still require explicit field-level resolution; a generic NEEDS_REVISION decision cannot make a true replacement/mixed-operation conflict VALID"
        )
    if file_experiment_ids and not sqlite_ids:
        blockers.append(
            "file-based experiment identities exist in Results/Analysis/Experiments but canonical SQLite contains no experiments; Execution tab is SQLite-only and will look empty"
        )
    elif file_experiment_ids - sqlite_ids:
        blockers.append(
            f"{len(file_experiment_ids - sqlite_ids)} file-based experiment identity/identities are absent from canonical SQLite and are invisible to Execution"
        )
    if sqlite.get("error"):
        blockers.append(f"canonical SQLite could not be inspected read-only: {sqlite['error']}")

    return {
        "schema": "archon.ol2.experiments-diagnostic.v2",
        "project_root": str(root),
        "paths": {
            "analysis_root": str(analysis),
            "experiments_root": str(experiments),
            "telemetry_database": str(db),
        },
        "director": {
            "report_exists": (analysis / "research_director_report.json").is_file(),
            "proposal_count": len(proposal_rows),
            "validation_counts": dict(sorted(validation_counts.items())),
            "decision_counts": dict(sorted(decision_counts.items())),
            "ui_status_counts": dict(sorted(ui_counts.items())),
            "proposals": proposal_rows,
        },
        "human_review": {
            "decision_record_count": len(decision_records),
            "records": decision_records,
            "latest_commit_status": s(review_commit_result.get("status")),
            "latest_receipt_status": s(review_receipt.get("status")),
        },
        "governance": {
            "patch_manifest_available": bool(patch_manifest.get("available")),
            "patch_manifest_final_ready": bool(patch_manifest.get("final_ready")),
            "patch_result_status": s(patch_result.get("status")),
            "patch_receipt_status": s(patch_receipt.get("status")),
            "patch_lifecycle_status": s(lifecycle.get("status")),
        },
        "planner": {
            "draft_count": len(planner_drafts),
            "draft_status_counts": dict(sorted(draft_counts.items())),
            "drafts_by_proposal": dict(sorted(drafts_by_proposal.items())),
            "plan_commit_count": len(plan_commits),
            "target_resolution_count": len(target_resolutions),
            "target_details": target_details,
            "file_experiment_ids": sorted(file_experiment_ids),
            "runtime_package_count": len(runtime_packages),
            "runtime_status_counts": dict(sorted(runtime_counts.items())),
            "runtime_details": runtime_details,
            "runtime_policy": {
                "path": str(runtime_policy_path),
                "code": runtime_policy_state.code,
                "message": runtime_policy_state.message,
                "previous_initial_state_mode": runtime_policy_state.previous_initial_state_mode,
                "effective_initial_state_mode": runtime_policy_state.effective_initial_state_mode,
            },
        },
        "canonical_sqlite": sqlite,
        "cross_check": {
            "file_experiments_not_in_sqlite": sorted(file_experiment_ids - sqlite_ids),
            "sqlite_experiments_without_file_resolution": sorted(sqlite_ids - file_experiment_ids),
        },
        "blockers": blockers,
    }


def print_human(report: dict[str, Any], *, verbose: bool) -> None:
    print("=" * 78)
    print("ARCHON Observer Launcher 2.0 Experiments diagnostic (READ ONLY)")
    print("=" * 78)
    print(f"Project: {report['project_root']}")
    d = report["director"]
    print("\n[Research Director]")
    print(f"  report:      {'YES' if d['report_exists'] else 'NO'}")
    print(f"  proposals:   {d['proposal_count']}")
    print(f"  validation:  {d['validation_counts']}")
    print(f"  decisions:   {d['decision_counts']}")
    print(f"  UI states:   {d['ui_status_counts']}")
    if verbose:
        for row in d["proposals"]:
            marker = "READY" if row["can_prepare"] else "----"
            print(
                f"    {marker:5s} {row['proposal_id']:<28} "
                f"val={row['validation']:<12} decision={row['decision']:<15} "
                f"ui={row['ui_status']:<12} action={row['action_id']}"
            )
            if row["validation"] in {"CONFLICTING", "BLOCKED"}:
                print(f"          resolution={row['resolution_type']} :: {row['preferred_resolution']}")

    h = report["human_review"]
    print("\n[Human review / governance]")
    print(f"  decision records: {h['decision_record_count']}")
    print(f"  latest review:    {h['latest_commit_status']} / receipt {h['latest_receipt_status']}")
    g = report["governance"]
    print(
        f"  patch:            manifest available={g['patch_manifest_available']} "
        f"final_ready={g['patch_manifest_final_ready']} result={g['patch_result_status']} "
        f"receipt={g['patch_receipt_status']} lifecycle={g['patch_lifecycle_status']}"
    )

    p = report["planner"]
    print("\n[Planner / materialization]")
    print(f"  drafts:       {p['draft_count']} {p['draft_status_counts']}")
    print(f"  plans:        {p['plan_commit_count']}")
    print(f"  targets:      {p['target_resolution_count']}")
    print(f"  runtimes:     {p['runtime_package_count']} {p['runtime_status_counts']}")
    policy = p.get("runtime_policy", {})
    print(f"  runtime policy: {policy.get('code')} :: {policy.get('message')}")
    print(f"  file EXP IDs: {len(p['file_experiment_ids'])}")
    if verbose:
        print("  target details:")
        for item in p.get("target_details", []):
            reasons = ", ".join(item.get("reasons") or []) or "-"
            protocol_reasons = ", ".join(item.get("protocol_reasons") or []) or "-"
            print(
                f"    {item.get('plan_id')}: {item.get('status')} type={item.get('experiment_type')} "
                f"action={item.get('source_action_id')} exp={item.get('experiment_id')} cond={item.get('condition_id')} "
                f"rules={item.get('rule_ids')} reasons={reasons}"
            )
            print(
                f"      protocol={item.get('protocol_status')} reasons={protocol_reasons}"
            )
        print("  runtime details:")
        for item in p.get("runtime_details", []):
            print(
                f"    {item.get('runtime_id')} / {item.get('plan_id')}: "
                f"{item.get('status')} runs={item.get('run_count')} unresolved={item.get('unresolved_count')}"
            )
            for field in item.get("unresolved_fields", []):
                print(f"      - {field.get('field')}: {field.get('reason')}")

    q = report["canonical_sqlite"]
    print("\n[Canonical SQLite used by Experiments / Execution]")
    print(f"  path:         {q['path']}")
    print(f"  exists:       {q['exists']}")
    print(f"  counts:       {q['counts']}")
    if q.get("error"):
        print(f"  ERROR:        {q['error']}")
    cross = report["cross_check"]
    print(f"  file→SQLite missing: {len(cross['file_experiments_not_in_sqlite'])}")

    print("\n[Blockers / findings]")
    if report["blockers"]:
        for i, item in enumerate(report["blockers"], 1):
            print(f"  {i}. {item}")
    else:
        print("  None detected by static state inspection.")
    print("\nNo project files were modified.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--verbose", action="store_true", help="show every proposal")
    args = parser.parse_args()
    report = inspect(args.project_root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
