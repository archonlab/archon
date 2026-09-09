"""Explicit audited Research Director → experiment materialization adapter.

OL2-FUNCTIONS1F uses this adapter only after an explicit human action.  It
reuses ARCHON's existing governance/planner/materializer modules rather than
re-implementing scientific policy inside the Launcher.  The adapter stops at
runtime materialization: it does not authorize launch, dispatch jobs, or start
Observer processes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace
from typing import Any, Callable, Iterable
from Tools.archon_runtime_python import runtime_python_command, runtime_python_environment
from Analyzer_next.execution.observer.shell2.functions1f.model import ExperimentPipelineResult
from Analyzer_next.research.cycle.authoritative_lifecycle import (
    AuthoritativeLifecycleError,
    AuthoritativeLifecyclePaths,
    ensure_proposed_cycle,
    find_authoritative_cycle,
    transition_authoritative_cycle,
)
from Analyzer_next.research.director.execution_readiness import (
    classify_action_execution_readiness,
)
from Analyzer_next.production.runtime_routes import (
    cli_route,
)

Progress = Callable[[str, str], None]


class ResearchExperimentPipelineError(RuntimeError):
    pass


class _DefaultRunner:
    """Small subprocess adapter local to this integration boundary."""

    def run(self, *, command, cwd, environment, timeout):
        try:
            completed = subprocess.run(
                list(command),
                cwd=str(cwd),
                env=dict(environment),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=int(timeout),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return SimpleNamespace(returncode=124, output=str(exc.stdout or ""))
        return SimpleNamespace(returncode=int(completed.returncode), output=completed.stdout or "")



def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {} if default is None else default
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchExperimentPipelineError(f"cannot read {path}: {exc}") from exc


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _token(prefix: str, *parts: str) -> str:
    raw = "|".join(parts + (_now(),)).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:16].upper()}"


class AuditedResearchExperimentPipeline:
    """Drive the existing audited experiment pipeline up to materialization."""

    def __init__(
        self,
        project_root: Path,
        telemetry_database: Path,
        *,
        runner: Any | None = None,
        timeout: int = 300,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.analysis_root = self.project_root / "Results" / "Analysis"
        self.experiments_root = self.analysis_root / "Experiments"
        self.results_dir = self.project_root / "Results" / "Universe_Search"
        self.telemetry_database = Path(telemetry_database).resolve()
        self.runner = runner or _DefaultRunner()
        self.timeout = int(timeout)

        self.director_cli = cli_route("research_director.py")
        self.planner_intake = cli_route(
            "approved_action_planner_intake_compat.py"
        )
        self.planner_review = cli_route("experiment_planner_review.py")
        self.plan_commit = cli_route("experiment_plan_commit.py")
        self.target_resolver = cli_route("scientific_target_resolver.py")
        self.protocol_resolver = cli_route("scientific_protocol_resolver.py")
        self.runtime_materializer = cli_route(
            "experiment_runtime_materializer.py"
        )
        self.authoritative_cycle_paths = AuthoritativeLifecyclePaths(
            project_root=self.project_root,
            analysis_root=self.analysis_root,
        )
        # Enabled only by the production OL2 Fix6 composition.  Base/frozen
        # adapter tests and legacy callers remain behaviorally unchanged.
        self.authoritative_cycle_tracking_enabled = False

    # ------------------------------------------------------------------
    # BRIDGE5.8 authoritative lifecycle synchronization
    # ------------------------------------------------------------------
    def _authoritative_reference(self, kind: str, ident: str, path: Path) -> dict[str, Any]:
        return {"kind": kind, "id": str(ident), "path": str(Path(path).resolve())}

    def _proposal_action_id(self, proposal_id: str) -> str | None:
        report = _load(self.analysis_root / "research_director_report.json", {})
        candidates: list[dict[str, Any]] = []
        if isinstance(report, dict):
            for key in ("recommendation_patch_proposals", "action_review_proposals"):
                block = report.get(key)
                if isinstance(block, dict):
                    rows = block.get("proposals") or block.get("rows") or []
                    if isinstance(rows, list):
                        candidates.extend(row for row in rows if isinstance(row, dict))
            for key in ("proposals", "review_proposals"):
                rows = report.get(key)
                if isinstance(rows, list):
                    candidates.extend(row for row in rows if isinstance(row, dict))
        for row in candidates:
            if str(row.get("proposal_id") or "") != proposal_id:
                continue
            return str(
                row.get("target_action_id")
                or row.get("action_id")
                or row.get("source_action_id")
                or ""
            ).strip() or None
        return None

    def _sync_authoritative_cycle(
        self,
        proposal_id: str,
        *,
        through_state: str,
        plan_ids: Iterable[str] = (),
        experiment_ids: Iterable[str] = (),
        runtime_ids: Iterable[str] = (),
    ) -> None:
        """Advance one proposal-owned cycle using only already-written artifacts.

        This reconciler is intentionally idempotent.  If a process crashes after
        an upstream owner commits its receipt but before this adapter updates the
        cycle projection, rerunning the action attaches the same artifact hashes
        to the same cycle instead of creating a duplicate.
        """
        if not self.authoritative_cycle_tracking_enabled:
            return
        proposal_id = str(proposal_id).strip()
        plan_ids = tuple(dict.fromkeys(str(value) for value in plan_ids if value))
        experiment_ids = tuple(dict.fromkeys(str(value) for value in experiment_ids if value))
        runtime_ids = tuple(dict.fromkeys(str(value) for value in runtime_ids if value))
        if len(plan_ids) > 1:
            raise ResearchExperimentPipelineError(
                "authoritative ResearchCycle requires exactly one plan per proposal; "
                f"{proposal_id} resolved {len(plan_ids)} plans"
            )
        if len(runtime_ids) > 1:
            raise ResearchExperimentPipelineError(
                "authoritative ResearchCycle requires exactly one runtime per proposal; "
                f"{proposal_id} resolved {len(runtime_ids)} runtimes"
            )
        if len(experiment_ids) > 1:
            raise ResearchExperimentPipelineError(
                "authoritative ResearchCycle requires exactly one canonical experiment per proposal; "
                f"{proposal_id} resolved {len(experiment_ids)} experiments"
            )

        report_path = self.analysis_root / "research_director_report.json"
        try:
            record = ensure_proposed_cycle(
                self.authoritative_cycle_paths,
                proposal_id=proposal_id,
                action_id=self._proposal_action_id(proposal_id),
                event_id=f"BRIDGE5.8:{proposal_id}:PROPOSED",
                proposal_reference=self._authoritative_reference(
                    "ResearchActionProposal", proposal_id, report_path
                ),
            )

            wanted = {
                "REVIEWED": 1,
                "PLANNED": 2,
                "MATERIALIZED": 3,
            }
            if through_state not in wanted:
                return

            # REVIEWED: prefer the explicit commit/result verification pair.
            if record.get("lifecycle_state") == "PROPOSED":
                review_refs = []
                result_path = self.analysis_root / "human_review_commit_result.json"
                verify_path = self.analysis_root / "human_review_receipt_verification.json"
                decisions_path = self.analysis_root / "human_review_decisions.json"
                if result_path.is_file() and verify_path.is_file():
                    review_refs.extend([
                        self._authoritative_reference("HumanReviewCommitResult", proposal_id, result_path),
                        self._authoritative_reference("HumanReviewReceiptVerification", proposal_id, verify_path),
                    ])
                elif decisions_path.is_file():
                    review_refs.append(
                        self._authoritative_reference("HumanReviewDecisionStore", proposal_id, decisions_path)
                    )
                    patch_verify = self.analysis_root / "patch_application_receipt_verification.json"
                    if patch_verify.is_file():
                        review_refs.append(
                            self._authoritative_reference("PatchReceiptVerification", proposal_id, patch_verify)
                        )
                else:
                    # REDUNDANT governance can carry its committed decision in
                    # the current Director report.  The proposal itself is still
                    # hash-bound to that report, so reuse remains explicit.
                    review_refs.append(
                        self._authoritative_reference("HumanReviewDecisionSnapshot", proposal_id, report_path)
                    )
                record = transition_authoritative_cycle(
                    self.authoritative_cycle_paths,
                    cycle_id=str(record["cycle_id"]),
                    to_state="REVIEWED",
                    event_id=f"BRIDGE5.8:{proposal_id}:REVIEWED",
                    references=review_refs,
                )
            if wanted[through_state] < wanted["PLANNED"]:
                return

            if record.get("lifecycle_state") == "REVIEWED":
                if len(plan_ids) != 1:
                    raise ResearchExperimentPipelineError(
                        f"cannot mark {proposal_id} PLANNED without one plan_id"
                    )
                plan_id = plan_ids[0]
                manifest_path = self.experiments_root / "PlanManifests" / f"{plan_id}.json"
                manifest = _load(manifest_path, {})
                plan = manifest.get("plan", {}) if isinstance(manifest, dict) else {}
                provenance = plan.get("provenance", {}) if isinstance(plan, dict) else {}
                action_id = str(provenance.get("source_action_id") or "").strip() or None
                record = transition_authoritative_cycle(
                    self.authoritative_cycle_paths,
                    cycle_id=str(record["cycle_id"]),
                    to_state="PLANNED",
                    event_id=f"BRIDGE5.8:{proposal_id}:PLANNED:{plan_id}",
                    references=[self._authoritative_reference("ExperimentPlanManifest", plan_id, manifest_path)],
                    identity_updates={"plan_id": plan_id, "action_id": action_id},
                )
            if wanted[through_state] < wanted["MATERIALIZED"]:
                return

            if record.get("lifecycle_state") == "PLANNED":
                if len(runtime_ids) != 1 or len(experiment_ids) != 1:
                    raise ResearchExperimentPipelineError(
                        f"cannot mark {proposal_id} MATERIALIZED without one runtime and experiment"
                    )
                runtime_id = runtime_ids[0]
                experiment_id = experiment_ids[0]
                registry_path = self.experiments_root / "experiment_runtime_registry.json"
                registry = _load(registry_path, {})
                packages = registry.get("packages", []) if isinstance(registry, dict) else []
                row = next(
                    (
                        item for item in packages
                        if isinstance(item, dict)
                        and str(item.get("runtime_id") or "") == runtime_id
                    ),
                    None,
                )
                runtime_path = None
                if isinstance(row, dict) and row.get("package_path"):
                    candidate = Path(str(row["package_path"]))
                    if not candidate.is_absolute():
                        candidate = (self.project_root / candidate).resolve()
                    if candidate.is_file():
                        runtime_path = candidate
                reference_path = runtime_path or registry_path
                record = transition_authoritative_cycle(
                    self.authoritative_cycle_paths,
                    cycle_id=str(record["cycle_id"]),
                    to_state="MATERIALIZED",
                    event_id=f"BRIDGE5.8:{proposal_id}:MATERIALIZED:{runtime_id}",
                    references=[self._authoritative_reference("RuntimePackage", runtime_id, reference_path)],
                    identity_updates={
                        "runtime_id": runtime_id,
                        "experiment_id": experiment_id,
                    },
                )
        except AuthoritativeLifecycleError as exc:
            raise ResearchExperimentPipelineError(
                f"authoritative ResearchCycle refused transition: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------
    def record_review_decision(
        self,
        proposal_id: str,
        *,
        decision: str,
        reason: str,
        progress: Progress | None = None,
    ) -> ExperimentPipelineResult:
        proposal_id = str(proposal_id).strip()
        decision = str(decision).upper().strip()
        if decision not in {"NEEDS_REVISION", "DEFERRED", "REJECTED"}:
            raise ResearchExperimentPipelineError(f"unsupported review decision: {decision}")
        self._emit(progress, "review", f"Staging {decision} for {proposal_id}")
        self._ensure_review_interface(progress)
        self._stage_review_candidate(proposal_id, decision, reason)
        # Generate a verifiable commit manifest, then commit the human decision.
        self._run_director("review manifest", progress)
        self._commit_review_candidate(proposal_id, progress)
        self._run_director("review decision commit", progress)
        self._verify_review_commit(proposal_id)
        self._sync_authoritative_cycle(proposal_id, through_state="REVIEWED")
        self._emit(progress, "refresh", "Human review decision committed; Research Director refreshed")
        return ExperimentPipelineResult(
            proposal_id=proposal_id,
            status=decision,
            message=f"{proposal_id}: {decision} committed; no experiment was launched",
        )

    def approve_and_materialize(
        self,
        proposal_id: str,
        *,
        decision_reason: str,
        progress: Progress | None = None,
    ) -> ExperimentPipelineResult:
        proposal_id = str(proposal_id).strip()
        if not proposal_id:
            raise ResearchExperimentPipelineError("proposal_id is required")

        self._emit(progress, "review", f"Preparing audited approval for {proposal_id}")
        self._ensure_review_interface(progress)
        self._assert_proposal_valid(proposal_id)
        self._stage_review_candidate(proposal_id, "APPROVED", decision_reason)

        self._run_director("review manifest", progress)
        self._commit_review_candidate(proposal_id, progress)
        self._run_director("review decision commit", progress)
        self._verify_review_commit(proposal_id)
        self._sync_authoritative_cycle(proposal_id, through_state="REVIEWED")

        self._emit(progress, "governance", "Applying verified Research Director action patch")
        self._apply_verified_patch(proposal_id, progress)

        self._emit(progress, "planner", "Building governance-verified planner intake")
        self._run_stage(self.planner_intake, ["--analysis-root", str(self.analysis_root)], "planner intake", progress)
        self._run_stage(self.planner_review, ["--analysis-root", str(self.analysis_root)], "planner review", progress)
        draft_ids = self._approve_matching_planner_drafts(proposal_id)
        if not draft_ids:
            raise ResearchExperimentPipelineError(
                f"no active valid planner draft was produced for {proposal_id}"
            )
        self._run_stage(self.planner_review, ["--analysis-root", str(self.analysis_root)], "planner approval reconciliation", progress)

        self._emit(progress, "commit", f"Committing {len(draft_ids)} approved experiment plan(s)")
        plan_ids = self._commit_matching_plans(proposal_id, draft_ids, progress)
        if not plan_ids:
            raise ResearchExperimentPipelineError(f"no experiment plan was committed for {proposal_id}")
        self._sync_authoritative_cycle(
            proposal_id, through_state="PLANNED", plan_ids=plan_ids
        )

        self._emit(progress, "targets", "Resolving scientific target identities into canonical telemetry")
        # Reconcile the complete committed-plan registry here.  The legacy
        # resolver writes one authoritative registry file; running it in scoped
        # mode would replace that file with only the newly selected plan(s),
        # which makes older runtime packages fail verification with
        # TARGET_RESOLUTION_COUNT_INVALID:0.  Full reconciliation is still
        # bounded to committed experiment plans and does not launch Observer.
        target_args = [
            "--analysis-root", str(self.analysis_root),
            "--telemetry-database", str(self.telemetry_database),
            "--confirmation", "RESOLVE_SCIENTIFIC_TARGETS",
        ]
        target_result = self._run_stage(
            self.target_resolver,
            target_args,
            "scientific target resolver (full registry reconciliation)",
            progress,
            accepted=(0, 1),
        )
        experiment_ids, target_status = self._target_identities(plan_ids)
        if not experiment_ids:
            raise ResearchExperimentPipelineError(
                "scientific target resolution did not register a canonical experiment: "
                + target_status
            )

        self._emit(progress, "protocol", "Resolving scientific protocol")
        protocol_args = [
            "--analysis-root", str(self.analysis_root),
            "--confirmation", "RESOLVE_SCIENTIFIC_PROTOCOLS",
        ]
        self._run_stage(
            self.protocol_resolver,
            protocol_args,
            "scientific protocol resolver (full registry reconciliation)",
            progress,
            accepted=(0, 1),
        )

        self._emit(progress, "materialize", "Materializing runtime package; launch remains unauthorized")
        self._run_stage(
            self.runtime_materializer,
            ["--analysis-root", str(self.analysis_root)],
            "runtime materializer",
            progress,
            accepted=(0, 1),
        )
        runtime_ids, runtime_status = self._runtime_ids(plan_ids)
        self._sync_authoritative_cycle(
            proposal_id,
            through_state="MATERIALIZED",
            plan_ids=plan_ids,
            experiment_ids=experiment_ids,
            runtime_ids=runtime_ids,
        )
        overall = "MATERIALIZED" if runtime_status == "READY_FOR_LAUNCH_REVIEW" else runtime_status
        message = (
            f"{proposal_id}: {len(plan_ids)} plan(s), {len(experiment_ids)} canonical experiment(s), "
            f"{len(runtime_ids)} runtime package(s) • {overall} • launch not authorized"
        )
        self._emit(progress, "done", message)
        return ExperimentPipelineResult(
            proposal_id=proposal_id,
            status=overall,
            plan_ids=tuple(plan_ids),
            experiment_ids=tuple(experiment_ids),
            runtime_ids=tuple(runtime_ids),
            message=message,
        )

    def refresh_director(
        self,
        *,
        progress: Progress | None = None,
    ) -> ExperimentPipelineResult:
        """Re-run the modular Research Director without approving anything."""
        self._emit(progress, "director", "Revalidating Research Director proposals")
        self._run_director("proposal revalidation", progress)
        report = _load(self.analysis_root / "research_director_report.json", {})
        validation = report.get("patch_proposal_validation", {}) if isinstance(report, dict) else {}
        counts = validation.get("status_counts", {}) if isinstance(validation, dict) else {}
        status_summary = ", ".join(
            f"{key}={int(value)}"
            for key, value in sorted(counts.items())
            if isinstance(value, (int, float)) and int(value)
        )
        action_count = len(
            report.get("actions", [])
            if isinstance(report, dict)
            and isinstance(report.get("actions"), list)
            else []
        )
        proposal_count = int(
            validation.get("proposal_count", 0)
            if isinstance(validation, dict)
            else 0
        )
        summary = (
            f"actions={action_count}, proposals={proposal_count}"
            + (f" • {status_summary}" if status_summary else "")
        )
        message = f"Research Director revalidated • {summary}"
        self._emit(progress, "done", message)
        return ExperimentPipelineResult(
            proposal_id="DIRECTOR-REVALIDATION",
            status="REFRESHED",
            message=message,
        )

    def reconcile_existing(
        self,
        *,
        progress: Progress | None = None,
    ) -> ExperimentPipelineResult:
        """Reconcile committed plan/target/protocol/runtime registries.

        This deliberately skips Research Director approval and planner writes.
        It is a recovery action for already committed plans and never performs
        launch authorization, dispatch, or Observer execution.
        """
        self._emit(progress, "targets", "Reconciling all committed scientific target identities")
        self._run_stage(
            self.target_resolver,
            [
                "--analysis-root", str(self.analysis_root),
                "--telemetry-database", str(self.telemetry_database),
                "--confirmation", "RESOLVE_SCIENTIFIC_TARGETS",
            ],
            "scientific target resolver (existing full reconciliation)",
            progress,
            accepted=(0, 1),
        )
        self._emit(progress, "protocol", "Reconciling all committed scientific protocols")
        self._run_stage(
            self.protocol_resolver,
            [
                "--analysis-root", str(self.analysis_root),
                "--confirmation", "RESOLVE_SCIENTIFIC_PROTOCOLS",
            ],
            "scientific protocol resolver (existing full reconciliation)",
            progress,
            accepted=(0, 1),
        )
        self._emit(progress, "materialize", "Re-materializing committed runtime packages without launch")
        self._run_stage(
            self.runtime_materializer,
            ["--analysis-root", str(self.analysis_root)],
            "runtime materializer (existing full reconciliation)",
            progress,
            accepted=(0, 1),
        )

        target_registry = _load(self.experiments_root / "scientific_target_resolution_registry.json", {})
        target_rows = target_registry.get("resolutions", []) if isinstance(target_registry, dict) else []
        experiment_ids: list[str] = []
        target_statuses: list[str] = []
        for row in target_rows if isinstance(target_rows, list) else []:
            if not isinstance(row, dict):
                continue
            target_statuses.append(str(row.get("status") or "UNKNOWN"))
            identities = row.get("identities", {}) if isinstance(row.get("identities"), dict) else {}
            experiment_id = str(identities.get("experiment_id") or "")
            if experiment_id:
                experiment_ids.append(experiment_id)

        runtime_registry = _load(self.experiments_root / "experiment_runtime_registry.json", {})
        packages = runtime_registry.get("packages", []) if isinstance(runtime_registry, dict) else []
        runtime_ids: list[str] = []
        ready = unresolved = 0
        for row in packages if isinstance(packages, list) else []:
            if not isinstance(row, dict):
                continue
            runtime_id = str(row.get("runtime_id") or "")
            if runtime_id:
                runtime_ids.append(runtime_id)
            status = str(row.get("status") or "UNKNOWN")
            ready += int(status == "READY_FOR_LAUNCH_REVIEW")
            unresolved += int(status == "NEEDS_RUNTIME_RESOLUTION")

        resolved_targets = sum(status == "RESOLVED" for status in target_statuses)
        message = (
            f"Existing experiment state reconciled • targets {resolved_targets}/{len(target_statuses)} resolved • "
            f"canonical experiments {len(set(experiment_ids))} • runtimes ready={ready} unresolved={unresolved} • "
            "launch not authorized"
        )
        self._emit(progress, "done", message)
        return ExperimentPipelineResult(
            proposal_id="EXISTING-EXPERIMENTS",
            status="RECONCILED" if ready or experiment_ids else "NEEDS_RESOLUTION",
            experiment_ids=tuple(dict.fromkeys(experiment_ids)),
            runtime_ids=tuple(dict.fromkeys(runtime_ids)),
            message=message,
        )

    # ------------------------------------------------------------------
    # Governance
    # ------------------------------------------------------------------
    def _ensure_review_interface(self, progress: Progress | None) -> None:
        path = self.analysis_root / "human_review_editing_interface.json"
        if path.is_file():
            return
        self._emit(progress, "review", "Refreshing Research Director review interface")
        self._run_director("review interface refresh", progress)
        if not path.is_file():
            raise ResearchExperimentPipelineError("Research Director did not produce human_review_editing_interface.json")

    def _assert_proposal_valid(self, proposal_id: str) -> None:
        # Defense in depth for a stale OL2 projection: execution readiness is
        # recomputed from the current Planner artifact before any human approval
        # is staged.  Revalidate Director will update the visible proposal state,
        # but this gateway must remain safe even if the old report is still open.
        plan_payload = _load(self.analysis_root / "experiment_plan.json", {})
        plan_rows = (
            plan_payload.get("plan", [])
            if isinstance(plan_payload, dict)
            else []
        )
        readiness = classify_action_execution_readiness(
            plan_rows if isinstance(plan_rows, list) else []
        )
        action_id = self._proposal_action_id(proposal_id)
        execution = readiness.get(str(action_id or ""), {})
        execution_status = str(execution.get("status") or "UNKNOWN").upper()
        if execution_status in {"SUPERSEDED", "WAITING_FOR_TARGET", "NEEDS_REVISION"}:
            reason = str(execution.get("reason") or execution_status)
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} is not executable: {reason}"
            )

        report = _load(self.analysis_root / "research_director_report.json", {})
        validations = {
            str(row.get("proposal_id")): str(row.get("status") or "UNKNOWN").upper()
            for row in ((report.get("patch_proposal_validation") or {}).get("validations") or [])
            if isinstance(row, dict) and row.get("proposal_id")
        }
        status = validations.get(proposal_id, "UNKNOWN")
        if status != "VALID":
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} is {status}; only VALID proposals can be approved for materialization"
            )

    def _stage_review_candidate(self, proposal_id: str, decision: str, reason: str) -> None:
        editing_path = self.analysis_root / "human_review_editing_interface.json"
        editing = _load(editing_path, {})
        rows = editing.get("rows", []) if isinstance(editing, dict) else []
        baseline = next(
            (dict(row) for row in rows if isinstance(row, dict) and str(row.get("proposal_id") or "") == proposal_id),
            None,
        )
        if baseline is None:
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} is absent from human_review_editing_interface.json"
            )
        candidate = dict(baseline)
        candidate.update({
            "current_decision": decision,
            "decision_reason": str(reason),
            "reviewed_by": "observer_launcher_2_human",
            "reviewed_at": _now(),
            "selected_resolution": baseline.get("selected_resolution"),
            "revision_notes": (
                "Conflict-aware review recorded by Observer Launcher 2.0."
                if decision == "NEEDS_REVISION"
                else "Explicit human decision recorded by Observer Launcher 2.0."
            ),
        })
        _atomic_json(
            self.analysis_root / "human_review_import_candidate.json",
            {
                "schema": "archon_review_import_candidate_v1",
                "rows": [candidate],
                "instructions": {
                    "source": "Observer Launcher 2.0 Experiments",
                    "automatic_import": False,
                    "automatic_patch_application": False,
                    "immutable_fields_preserved": True,
                },
            },
        )

    def _commit_review_candidate(self, proposal_id: str, progress: Progress | None) -> None:
        manifest = _load(self.analysis_root / "human_review_commit_manifest.json", {})
        if not isinstance(manifest, dict) or not manifest.get("available"):
            raise ResearchExperimentPipelineError("no importable Research Director review commit manifest is available")
        rows = manifest.get("rows", []) if isinstance(manifest.get("rows"), list) else []
        if proposal_id not in {str(row.get("proposal_id") or "") for row in rows if isinstance(row, dict)}:
            raise ResearchExperimentPipelineError("review commit manifest does not contain the selected proposal")
        required = (manifest.get("commit_id"), manifest.get("candidate_hash"), manifest.get("expected_decision_store_hash"))
        if not all(required):
            raise ResearchExperimentPipelineError("review commit manifest is missing identity/hash fields")
        _atomic_json(
            self.analysis_root / "human_review_commit_request.json",
            {
                "schema": "archon_review_commit_request_v1",
                "commit": True,
                "commit_id": manifest["commit_id"],
                "candidate_hash": manifest["candidate_hash"],
                "expected_decision_store_hash": manifest["expected_decision_store_hash"],
                "requested_at": _now(),
                "requested_by": "observer_launcher_2_human",
                "confirmation": "COMMIT_REVIEW_DECISIONS",
                "last_consumed_commit_id": None,
            },
        )
        self._emit(progress, "review", f"Commit request prepared for {proposal_id}")

    def _verify_review_commit(self, proposal_id: str) -> None:
        result = _load(self.analysis_root / "human_review_commit_result.json", {})
        receipt = _load(self.analysis_root / "human_review_receipt_verification.json", {})
        if result.get("status") != "COMMITTED" or receipt.get("status") not in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}:
            raise ResearchExperimentPipelineError(
                f"human review commit for {proposal_id} was not verified: result={result.get('status')} receipt={receipt.get('status')}"
            )

    def _apply_verified_patch(self, proposal_id: str, progress: Progress | None) -> None:
        manifest = _load(self.analysis_root / "patch_application_manifest.json", {})
        if not manifest.get("available") or not manifest.get("final_ready"):
            raise ResearchExperimentPipelineError("approved review has no safe final-ready patch application manifest")
        required = (manifest.get("application_manifest_id"), manifest.get("manifest_hash"), manifest.get("source_commit_id"))
        if not all(required):
            raise ResearchExperimentPipelineError("patch application manifest is missing required identities")
        _atomic_json(
            self.analysis_root / "patch_application_request.json",
            {
                "schema": "archon_patch_application_request_v1",
                "apply": True,
                "application_manifest_id": manifest["application_manifest_id"],
                "manifest_hash": manifest["manifest_hash"],
                "source_commit_id": manifest["source_commit_id"],
                "requested_at": _now(),
                "requested_by": "observer_launcher_2_human",
                "confirmation": "APPLY_RESEARCH_ACTION_PATCHES",
            },
        )
        self._run_director("patch application", progress)
        result = _load(self.analysis_root / "patch_application_result.json", {})
        receipt = _load(self.analysis_root / "patch_application_receipt_verification.json", {})
        lifecycle = _load(self.analysis_root / "patch_lifecycle_closure.json", {})
        if (
            result.get("status") != "APPLIED"
            or receipt.get("status") not in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}
            or lifecycle.get("status") != "ACTIVE"
        ):
            raise ResearchExperimentPipelineError(
                "verified governance patch did not reach ACTIVE lifecycle "
                f"(result={result.get('status')}, receipt={receipt.get('status')}, lifecycle={lifecycle.get('status')})"
            )
        self._emit(progress, "governance", f"Governance ACTIVE for {proposal_id}")

    # ------------------------------------------------------------------
    # Planner + materializer
    # ------------------------------------------------------------------
    def _approve_matching_planner_drafts(self, proposal_id: str) -> tuple[str, ...]:
        drafts_path = self.experiments_root / "experiment_planner_drafts.json"
        drafts = _load(drafts_path, {})
        rows = []
        ids = []
        for draft in drafts.get("drafts", []) if isinstance(drafts, dict) else []:
            if not isinstance(draft, dict):
                continue
            provenance = draft.get("provenance", {}) if isinstance(draft.get("provenance"), dict) else {}
            if str(provenance.get("source_proposal_id") or "") != proposal_id:
                continue
            if draft.get("source_active") is not True:
                continue
            validation = draft.get("validation", {}) if isinstance(draft.get("validation"), dict) else {}
            if validation.get("valid") is False:
                continue
            draft_id = str(draft.get("draft_id") or "")
            draft_hash = draft.get("draft_hash")
            if not draft_id or not draft_hash:
                continue
            ids.append(draft_id)
            rows.append({
                "draft_id": draft_id,
                "expected_draft_hash": draft_hash,
                "decision": "APPROVED",
                "reviewed_at": _now(),
                "reviewed_by": "observer_launcher_2_human",
                "decision_reason": "Covered by explicit Research Director proposal approval in Observer Launcher 2.0.",
                "required_changes": [],
                "editable_patch": {},
            })
        if rows:
            _atomic_json(
                self.experiments_root / "experiment_planner_review_editor.json",
                {
                    "schema": "archon_planner_review_editor_v1",
                    "generated_at": _now(),
                    "mode": "SAFE_EDITOR",
                    "rows": rows,
                },
            )
        return tuple(ids)

    def _commit_matching_plans(
        self,
        proposal_id: str,
        draft_ids: Iterable[str],
        progress: Progress | None,
    ) -> tuple[str, ...]:
        drafts = _load(self.experiments_root / "experiment_planner_drafts.json", {})
        draft_map = {
            str(row.get("draft_id")): row
            for row in drafts.get("drafts", []) if isinstance(drafts, dict)
            for row in [row] if isinstance(row, dict) and row.get("draft_id")
        }
        registry_path = self.experiments_root / "experiment_plan_registry.json"
        registry = _load(registry_path, {})
        existing_by_draft = {
            str(row.get("draft_id")): str(row.get("plan_id"))
            for row in registry.get("commits", []) if isinstance(registry, dict)
            if isinstance(row, dict) and row.get("draft_id") and row.get("plan_id")
        }
        plan_ids: list[str] = []
        for draft_id in draft_ids:
            if draft_id in existing_by_draft:
                plan_ids.append(existing_by_draft[draft_id])
                continue
            draft = draft_map.get(draft_id)
            if not draft or draft.get("status") != "DRAFT_APPROVED":
                raise ResearchExperimentPipelineError(f"planner draft {draft_id} is not DRAFT_APPROVED")
            provenance = draft.get("provenance", {}) if isinstance(draft.get("provenance"), dict) else {}
            if str(provenance.get("source_proposal_id") or "") != proposal_id:
                raise ResearchExperimentPipelineError(f"planner draft {draft_id} provenance mismatch")
            request = {
                "schema": "archon_experiment_plan_commit_request_v1",
                "commit": True,
                "commit_id": _token("OL2-PLAN-COMMIT", proposal_id, draft_id),
                "draft_id": draft_id,
                "expected_draft_hash": draft.get("draft_hash"),
                "expected_drafts_file_hash": drafts.get("content_hash"),
                "requested_at": _now(),
                "requested_by": "observer_launcher_2_human",
                "confirmation": "COMMIT_EXPERIMENT_PLAN",
                "last_consumed_commit_id": None,
            }
            _atomic_json(self.experiments_root / "experiment_plan_commit_request.json", request)
            self._run_stage(
                self.plan_commit,
                ["--analysis-root", str(self.analysis_root)],
                f"plan commit {draft_id}",
                progress,
            )
            result = _load(self.experiments_root / "experiment_plan_commit_result.json", {})
            verification = _load(self.experiments_root / "experiment_plan_commit_receipt_verification.json", {})
            if result.get("status") != "COMMITTED" or verification.get("status") not in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}:
                raise ResearchExperimentPipelineError(
                    f"plan commit failed for {draft_id}: {result.get('status')} / {verification.get('status')}"
                )
            plan_id = str(result.get("plan_id") or "")
            if not plan_id:
                raise ResearchExperimentPipelineError(f"plan commit for {draft_id} produced no plan_id")
            plan_ids.append(plan_id)
        return tuple(dict.fromkeys(plan_ids))

    def _target_identities(self, plan_ids: Iterable[str]) -> tuple[tuple[str, ...], str]:
        selected = set(plan_ids)
        registry = _load(self.experiments_root / "scientific_target_resolution_registry.json", {})
        experiment_ids: list[str] = []
        statuses = []
        for row in registry.get("resolutions", []) if isinstance(registry, dict) else []:
            if not isinstance(row, dict) or str(row.get("plan_id") or "") not in selected:
                continue
            statuses.append(str(row.get("status") or "UNKNOWN"))
            identities = row.get("identities", {}) if isinstance(row.get("identities"), dict) else {}
            experiment_id = str(identities.get("experiment_id") or "")
            if experiment_id:
                experiment_ids.append(experiment_id)
        status = ", ".join(statuses) or "NO_TARGET_RESOLUTION"
        return tuple(dict.fromkeys(experiment_ids)), status

    def _runtime_ids(self, plan_ids: Iterable[str]) -> tuple[tuple[str, ...], str]:
        selected = set(plan_ids)
        registry = _load(self.experiments_root / "experiment_runtime_registry.json", {})
        ids: list[str] = []
        statuses: list[str] = []
        for row in registry.get("packages", []) if isinstance(registry, dict) else []:
            if not isinstance(row, dict) or str(row.get("plan_id") or "") not in selected:
                continue
            runtime_id = str(row.get("runtime_id") or "")
            if runtime_id:
                ids.append(runtime_id)
            statuses.append(str(row.get("status") or "UNKNOWN"))
        if statuses and all(item == "READY_FOR_LAUNCH_REVIEW" for item in statuses):
            status = "READY_FOR_LAUNCH_REVIEW"
        elif any(item == "NEEDS_RUNTIME_RESOLUTION" for item in statuses):
            status = "NEEDS_RUNTIME_RESOLUTION"
        else:
            status = statuses[0] if statuses else "NO_RUNTIME_PACKAGE"
        return tuple(dict.fromkeys(ids)), status

    # ------------------------------------------------------------------
    # Process helpers
    # ------------------------------------------------------------------
    def _run_director(self, label: str, progress: Progress | None) -> None:
        self._run_stage(
            self.director_cli,
            [str(self.results_dir), "--root", str(self.analysis_root)],
            f"Research Director {label}",
            progress,
        )

    def _run_stage(
        self,
        module: Path,
        args: list[str],
        label: str,
        progress: Progress | None,
        *,
        accepted: tuple[int, ...] = (0,),
    ) -> Any:
        if not module.is_file():
            raise ResearchExperimentPipelineError(f"required module missing: {module}")
        command = [*runtime_python_command(self.project_root), str(module), *args]
        self._emit(progress, "process", label)
        result = self.runner.run(
            command=command,
            cwd=self.project_root,
            environment=runtime_python_environment(self.project_root),
            timeout=self.timeout,
        )
        if int(result.returncode) not in accepted:
            tail = "\n".join(str(result.output).splitlines()[-30:])
            raise ResearchExperimentPipelineError(
                f"{label} failed with exit code {result.returncode}" + (f"\n{tail}" if tail else "")
            )
        return result

    @staticmethod
    def _emit(progress: Progress | None, stage: str, message: str) -> None:
        if progress is not None:
            progress(str(stage), str(message))


__all__ = ["AuditedResearchExperimentPipeline", "ResearchExperimentPipelineError"]

# ARCHON RELEASE2.4 source-proven relocated compatibility dependencies.
_ARCHON_RELEASE2_RELOCATED_COMPATIBILITY_FILES = (
    'Analyzer_next/compatibility/legacy_analyzer/approved_action_planner_intake.py',
)
