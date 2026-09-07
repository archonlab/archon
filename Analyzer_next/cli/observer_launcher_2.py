#!/usr/bin/env python3
"""Production entrypoint for ARCHON Observer Launcher 2.0.

Direct production launch is guarded by OL2-CUTOVER1 acceptance.  ``--candidate``
opens the exact same composition for manual visual/operational acceptance before
activation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.execution.observer.shell2.analyze1 import AnalysisLaunchPlan
from Analyzer_next.execution.observer.shell2.cutover1 import CutoverError, CutoverService, LauncherProfile
from Analyzer_next.execution.observer.shell2.theme import ThemeMode

DEFAULT_DATABASE = PROJECT_ROOT / "Results/Universe_Search/observation_logs/telemetry.sqlite"


def headless_contract(database: Path, *, candidate: bool, active_profile: str) -> dict[str, object]:
    plan = AnalysisLaunchPlan.create(PROJECT_ROOT)
    contract: dict[str, object] = {
        "milestone": "OL2-CUTOVER1",
        "entrypoint": "Analyzer_next/cli/observer_launcher_2.py",
        "candidate_mode": bool(candidate),
        "active_profile": active_profile,
        "production_cutover": (not candidate and active_profile == LauncherProfile.OL2.value),
        "observation_frame": "real-legacy-live-presentation-stream",
        "legacy_observer_window": False,
        "instrument_source": "legacy-WorldViewer-computed-labels",
        "presentation_transport": "CONTROL1-captured-stdout",
        "scientific_runtime": "canonical-legacy-Observer-unchanged",
        "process_owner": "CONTROL1",
        "queue_owner": "QUEUE1",
        "queue_ui_milestone": "OL2-QUEUE2",
        "queue_clear_policy": "active-view-cleanup-durable-terminal-history-retained",
        "queue_clear_completed": "completed-success-only-active-view-durable-history-retained",
        "queue_save_visibility": "horizon-plus-autosave-final-max-tick-checkpoint",
        "queue_completion_polling": "route-independent-terminal-reconciliation-and-next-row-dispatch",
        "save_policy_milestone": "OL2-SAVE-POLICY1",
        "dialogs_milestone": "OL2-DIALOGS1",
        "dialog_surface": "launcher-themed-modal-light-dark",
        "dialog_labels": "english-yes-no-ok-enter-confirm-escape-cancel",
        "save_policy": "pre-review-autosave-finite-final-at-max-queue-read-only",
        "mutation_save_policy": "periodic-autosave-manual-final-via-save-and-stop",
        "experiments_save_policy": "deferred-to-separate-experiments-track",
        "experiments_fix_milestone": "OL2-EXPERIMENTS-FIX8",
        "experiments_search_handoff_milestone": "OL2-BRIDGE4",
        "experiments_search_handoff": "verified-search-authorization-direct-universe-search-dispatch-no-observer-queue",
        "experiments_queue_refresh": "stale-terminal-active-view-replacement-durable-history-retained",
        "experiments_runtime_telemetry_binding": "per-row-files-canonical-experiment-sqlite",
        "experiments_authorization_reconciliation": "preserve-verified-unchanged-runtime-supersede-stale-rematerialized-receipts",
        "experiments_catalog_compatibility": "read-only-runtime-schema-adaptation-no-sqlite-migration",
        "experiments_runtime_policy": "explicit-legacy-canonical-or-implicit-fallback-multireplicate-repair-to-random-seed",
        "experiments_authorization_ui_handoff": "worker-io-main-thread-result-poll-visible-fail-closed",
        "experiments_planner_revision": "kind-stable-approved-proposal-rebuild-without-governance-recommit",
        "experiments_runs_preview": "exact-ready-runtime-matrix-first-row-review-multirun-execution-via-queue",
        "experiments_target_handoff": "registered-single-canonical-target-auto-selects-config1-world",
        "experiments_conflict_policy": "append-unique-cross-proposals-merge-safe-true-replace-conflicts-fail-closed",
        "experiments_registry_reconciliation": "full-committed-plan-target-protocol-runtime-no-launch",
        "automatic_scientific_refresh_milestone": "BRIDGE5.7",
        "automatic_scientific_refresh_trigger": "experimental-queue-finished",
        "automatic_scientific_refresh_modes": "intake-then-scientific-refresh",
        "automatic_scientific_refresh_deduplication": "completed-run-registry-and-request-hash",
        "automatic_scientific_refresh_process": "detached-durable-request-and-attested-receipt",
        "manual_analysis_post_run_parity": "finished-uncovered-experimental-queue-converges-to-bridge5.7",
        "manual_analysis_partial_queue_policy": "fail-closed-no-partial-experimental-interpretation",
        "manual_analysis_no_pending_policy": "full-technical-analyzer-rerun",
        "single_active_process": True,
        "shutdown_milestone": "OL2-FINAL6",
        "launcher_close_process_policy": "graceful-stop-bounded-wait-force-kill-owned-process-group-no-silent-orphan",
        "launcher_close_queue_policy": "persist-active-terminal-before-destroy-preserve-waiting-no-auto-resume",
        "telemetry_identity_binding": "first-canonical-run-id-must-match-reviewed-rule-conflicts-rejected",
        "telemetry_backend": "canonical-sqlite-read-only",
        "database": str(database.resolve()),
        "analysis_backend": "real-on-user-action",
        "observer_backend": "real-on-explicit-user-or-queue-action",
        "rollback": "launcher-profile-only",
        "layout_milestone": "OL2-LAYOUT1",
        "layout_policy": "stable-viewer-user-resizable-rail",
        "rail_scroll": "mouse-wheel-no-visible-scrollbar",
        "launch_action": "single-canonical-control",
        "interaction_milestone": "OL2-INTERACT1",
        "pause_resume": "acknowledged-legacy-runtime-control",
        "runtime_speed": "acknowledged-legacy-runtime-control",
        "viewer_controls": "zoom-grid-fullscreen-local-presentation",
        "overflow_menu": "copy-run-id-save-checkpoint-reset-zoom-fullscreen",
        "visualization_milestone": "OL2-VIS1",
        "visualization_control": "session-local-field-render-toggle-simulation-telemetry-instruments-autosave-continue",
        "overflow_surface": "launcher-themed-light-dark-popover",
        "functions_milestone": "OL2-FUNCTIONS1A",
        "world_search": "live-filter-normalized-numeric-rule-id",
        "performance_milestone": "OL2-PERF1",
        "telemetry_polling": "background-read-only-worker-short-busy-timeout",
        "observation_renderer": "single-photoimage-grid-overlay",
        "mutation_hot_path": "session-cached-baseline-and-manifest-discovery",
        "sequential_run_handoff": "fresh-review-bound-to-selected-world",
        "functions_stop_milestone": "OL2-FUNCTIONS1B",
        "stop_workflow": "explicit-save-and-stop-or-stop-without-saving",
        "save_stop_policy": "checkpoint-ack-before-termination",
        "functions_settings_milestone": "OL2-FUNCTIONS1C",
        "settings_route": "launcher-local-persistent-preferences",
        "observable_configuration": "six-frozen-canonical-cards-visibility-only",
        "functions_experiments_milestone": "OL2-FUNCTIONS1D",
        "experiments_route": "canonical-sqlite-read-only-browser-explicit-config1-handoff",
        "functions_experiment_workflow_milestone": "OL2-FUNCTIONS1E",
        "experiment_workflow": "research-director-proposals-to-review-to-execution",
        "proposal_source": "research_director_report-read-only",
        "functions_experiment_materialization_milestone": "OL2-FUNCTIONS1F",
        "proposal_materialization": "explicit-human-audited-governance-planner-target-runtime-no-launch",
        "catalog_milestone": "OL2-CATALOG1",
        "world_catalog_cache": "validated-persistent-cache-bounded-source-signature-single-scan-cold-path",
        "catalog_refresh": "explicit-refresh-forces-cold-rebuild-and-cache-rewrite",
        "mutations_milestone": "OL2-MUTATIONS2",
        "mutations_base_milestone": "OL2-MUTATIONS1",
        "mutations_workflow": "source-to-mutation-to-execution-isolated-no-canonical-promotion",
        "mutation_source_catalog": "reuse-config1-snapshot-no-route-filesystem-scan",
        "mutation_execution": "explicit-selected-run-through-CONTROL1-manual-stop-shared-horizon",
        "mutation_live_telemetry": "isolated-run-local-sqlite-read-only-routed-by-canonical-run-id",
        "mutation_analysis": "explicit-user-action-existing-core-per-mutation-report-no-aggregate-rewrite",
        "mutation_analysis_projection": "read-only-effect-confidence-baseline-control-core-deltas",
        "campaigns_milestone": "OL2-CAMPAIGNS1",
        "campaigns_workflow": "canonical-multiworld-batch-to-QUEUE1-no-auto-start",
        "campaigns_select_not_observed": "visible-catalog-worldrecord-observed-false-selection-only",
        "campaign_authorization": "canonical_queue-only-experimental-production-fail-closed",
        "analyzer_launcher_sha256": plan.launcher_sha256,
    }
    # Experiments is being developed as a separate track.  If FUNCTIONS1G is
    # installed on top of this baseline, keep its production contract visible
    # without making MUTATIONS1 depend on it.
    functions1g_app = PROJECT_ROOT / "Analyzer_next/execution/observer/shell2/functions1g/app.py"
    if functions1g_app.is_file():
        contract.update({
            "functions_experiment_queue_milestone": "OL2-FUNCTIONS1G",
            "experiment_runtime_handoff": "verified-stage6.5-authorization-to-queue-no-auto-dispatch",
            "experimental_queue_authorization": "durable-verified-receipt-revalidation",
        })
    return contract


def _build_and_run(*, theme: ThemeMode | None, database: Path, auto_close_ms: int | None, candidate: bool) -> int:
    import tkinter as tk

    from Analyzer_next.adapters.observer.interactive_process_runner import InteractivePresentationProcessRunner
    from Analyzer_next.adapters.observer.desktop_path_opener import DesktopPathOpener
    from Analyzer_next.adapters.observer.ui_preferences import JSONUIPreferencesRepository
    from Analyzer_next.adapters.observer.experiment_catalog_compat import SchemaCompatibleSQLiteExperimentCatalog
    from Analyzer_next.adapters.observer.experiment_target_context import ExperimentTargetContextReader
    from Analyzer_next.adapters.observer.director_proposals import JSONResearchDirectorProposalAdapter
    from Analyzer_next.adapters.observer.research_experiment_pipeline_fix6 import AuditedResearchExperimentPipelineFix6
    from Analyzer_next.execution.observer.shell2.mutations1.app import HAS_FUNCTIONS1G
    from Analyzer_next.execution.observer.shell2.scientific_refresh1.app import (
        ObserverLauncher2ScientificRefreshShell,
    )
    # SCIENTIFIC_REFRESH1 wraps VIS1; the earlier UI/runtime owners remain frozen.
    from Analyzer_next.execution.observer.shell2.mutations2.controller import MutationAnalysisController
    from Analyzer_next.adapters.observer.mutation_analysis import JSONMutationAnalysisReader, MutationAnalysisProcessRunner
    if HAS_FUNCTIONS1G:
        from Analyzer_next.adapters.observer.experiment_runtime_handoff_bridge4 import AuditedExperimentRuntimeHandoffBridge4
        from Analyzer_next.adapters.observer.verified_experiment_queue_authorization import VerifiedExperimentQueueAuthorization
        from Analyzer_next.execution.observer.shell2.functions1g.controller import ExperimentRuntimeHandoffController
    from Analyzer_next.adapters.observer.process_runner import SubprocessRunner
    from Analyzer_next.adapters.observer.automatic_scientific_refresh import (
        AutomaticScientificRefreshHandoff,
    )
    from Analyzer_next.adapters.observer.authoritative_cycle_lifecycle import (
        ObserverAuthoritativeCycleLifecycle,
    )
    from Analyzer_next.adapters.observer.queue_journal import JSONQueueJournal
    from Analyzer_next.production.automatic_refresh import AutomaticRefreshPaths
    from Analyzer_next.adapters.telemetry.async_live import AsyncLiveTelemetryController
    from Analyzer_next.execution.observer.shell2.analyze1.controller import AnalysisController
    from Analyzer_next.execution.observer.shell2.catalog1 import Catalog1ControlShellStore, build_catalog1
    from Analyzer_next.execution.observer.shell2.functions1d.controller import ExperimentCatalogController
    from Analyzer_next.execution.observer.shell2.functions1e.controller import ProposalWorkflowController
    from Analyzer_next.execution.observer.shell2.functions1f.controller import ExperimentPipelineController
    from Analyzer_next.execution.observer.shell2.mutations1.controller import MutationWorkspaceController
    from Analyzer_next.execution.observer.shell2.save_policy1.campaign_controller import SavePolicyCampaignController
    from Analyzer_next.execution.observer.shell2.config1.command_service import ObserverCommandService
    from Analyzer_next.adapters.observer.mutation_workspace import SnapshotWorldCatalog
    from Analyzer_next.adapters.observer.cached_mutation_workspace import CachedMutationWorkspace
    from Analyzer_next.execution.observer.shell2.functions1c.controller import LauncherSettingsController
    from Analyzer_next.execution.observer.shell2.functions1b.controller import ObserverStopWorkflowController
    from Analyzer_next.execution.observer.shell2.queue2.controller import ObserverQueue2Controller
    from Analyzer_next.execution.observer.shell2.theme import detect_system_scheme

    telemetry_controller = AsyncLiveTelemetryController(database)
    # PERF1 supersedes the synchronous MUTATIONS1 composition while preserving its contract:
    # RoutedLiveTelemetryAdapter(canonical_telemetry_port)
    # mutation_telemetry_router=telemetry_port

    os_runner = SubprocessRunner()
    presentation_runner = InteractivePresentationProcessRunner(os_runner)
    preferences_repository = JSONUIPreferencesRepository(
        PROJECT_ROOT / "Config/ObserverLauncher/ui_preferences.json"
    )
    settings_controller = LauncherSettingsController(
        preferences_repository, DesktopPathOpener()
    )
    experiment_controller = ExperimentCatalogController(SchemaCompatibleSQLiteExperimentCatalog(database))
    experiment_target_context = ExperimentTargetContextReader(
        database,
        PROJECT_ROOT / "Results/Analysis/Experiments/scientific_target_resolution_registry.json",
    )
    director_report = PROJECT_ROOT / "Results/Analysis/research_director_report.json"
    proposal_controller = ProposalWorkflowController(JSONResearchDirectorProposalAdapter(director_report))
    experiment_pipeline_controller = ExperimentPipelineController(
        AuditedResearchExperimentPipelineFix6(PROJECT_ROOT, database)
    )
    runtime_handoff_adapter = None
    runtime_handoff_controller = None
    if HAS_FUNCTIONS1G:
        runtime_handoff_adapter = AuditedExperimentRuntimeHandoffBridge4(PROJECT_ROOT)
        runtime_handoff_controller = ExperimentRuntimeHandoffController(runtime_handoff_adapter)
    resolved_theme_preference = theme or settings_controller.preferences.theme
    root = tk.Tk()
    world_catalog = build_catalog1(PROJECT_ROOT)
    store = Catalog1ControlShellStore(
        theme_preference=resolved_theme_preference,
        system_scheme=detect_system_scheme(),
        catalog=world_catalog,
    )
    # CONFIG1 already resolved the canonical world catalog while constructing
    # ControlShellStore.  Reuse that in-memory snapshot for Mutations instead
    # of synchronously rescanning Atlas + observation_logs in the Tk route.
    mutation_source_catalog = SnapshotWorldCatalog(lambda: store.config_snapshot.worlds)
    mutation_controller = MutationWorkspaceController(
        CachedMutationWorkspace(source_catalog=mutation_source_catalog),
        initial_worlds=store.config_snapshot.worlds,
    )
    mutation_analysis_controller = MutationAnalysisController(
        JSONMutationAnalysisReader(PROJECT_ROOT / "Results/Analysis/Mutations"),
        MutationAnalysisProcessRunner(PROJECT_ROOT),
    )
    campaign_controller = SavePolicyCampaignController(
        ObserverCommandService(
            default_output_dir=PROJECT_ROOT / "Results/Universe_Search/observation_logs"
        ),
        worlds=store.config_snapshot.worlds,
    )
    analysis_controller = AnalysisController(AnalysisLaunchPlan.create(PROJECT_ROOT), os_runner)
    control_controller = ObserverStopWorkflowController(PROJECT_ROOT, presentation_runner)
    queue_repository = JSONQueueJournal(
        PROJECT_ROOT / "Results/Analysis/ObserverLauncher2/OL2_QUEUE1_STATE.json",
        PROJECT_ROOT / "Results/Universe_Search/mutation_runs/launcher_history.json",
    )
    queue_kwargs = {
        "repository": queue_repository,
        "lifecycle": ObserverAuthoritativeCycleLifecycle(
            PROJECT_ROOT, PROJECT_ROOT / "Results/Analysis"
        ),
    }
    if HAS_FUNCTIONS1G and runtime_handoff_adapter is not None:
        queue_kwargs["authorization"] = VerifiedExperimentQueueAuthorization(runtime_handoff_adapter)
    queue_controller = ObserverQueue2Controller(control_controller, **queue_kwargs)
    automatic_refresh_handoff = AutomaticScientificRefreshHandoff(
        AutomaticRefreshPaths(
            project_root=PROJECT_ROOT,
            results_directory=PROJECT_ROOT / "Results/Universe_Search",
            analysis_root=PROJECT_ROOT / "Results/Analysis",
            analyzer_entrypoint=(
                PROJECT_ROOT / "Analyzer_next/cli/analyze_results.py"
            ),
            telemetry_database=database,
        )
    )
    app_kwargs = {}
    if HAS_FUNCTIONS1G and runtime_handoff_controller is not None:
        app_kwargs["runtime_handoff_controller"] = runtime_handoff_controller
    app = ObserverLauncher2ScientificRefreshShell(
        root,
        store,
        analysis_controller,
        telemetry_controller,
        control_controller,
        queue_controller,
        settings_controller=settings_controller,
        experiment_controller=experiment_controller,
        experiment_target_context=experiment_target_context,
        proposal_controller=proposal_controller,
        director_report_path=director_report,
        experiment_pipeline_controller=experiment_pipeline_controller,
        mutation_controller=mutation_controller,
        mutation_analysis_controller=mutation_analysis_controller,
        mutation_telemetry_router=telemetry_controller,
        campaign_controller=campaign_controller,
        automatic_refresh_handoff=automatic_refresh_handoff,
        animate=False,
        **app_kwargs,
    )
    root.title("ARCHON Observer Launcher 2.0" + (" — CUTOVER CANDIDATE" if candidate else ""))
    try:
        app.footer_hint.set(
            "CUTOVER candidate • manual acceptance required before production activation"
            if candidate
            else "OL2 production profile active • rollback is launcher-profile only"
        )
    except Exception:
        pass
    if auto_close_ms is not None:
        root.after(max(1, auto_close_ms), app.close)
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARCHON Observer Launcher 2.0 production/candidate entrypoint")
    parser.add_argument("--theme", choices=tuple(item.value for item in ThemeMode), default=None)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--candidate", action="store_true", help="manual acceptance candidate; does not require active OL2 profile")
    parser.add_argument("--headless-check", action="store_true")
    parser.add_argument("--auto-close-ms", type=int)
    args = parser.parse_args(argv)

    database = args.database.expanduser().resolve()
    service = CutoverService(PROJECT_ROOT)
    if args.candidate:
        active_profile = service.read_profile(verify_ol2_acceptance=False).profile.value
    else:
        try:
            profile = service.read_profile(
                verify_ol2_acceptance=True,
                allow_modified_sources=True,
            )
            source_changes = service.source_modifications(
                acceptance_bound=bool(profile.acceptance_receipt_hash),
            )
        except CutoverError as exc:
            parser.error(str(exc))
        if source_changes:
            print(
                "WARNING: MODIFIED_SOURCE_TREE: local production sources differ from the "
                "accepted/sealed release; continuing in source mode. Changed: "
                + ", ".join(source_changes),
                file=sys.stderr,
            )
        if profile.profile is not LauncherProfile.OL2:
            parser.error(
                "OL2 is not the active production launcher profile. "
                "Use --candidate for acceptance testing or launch through OBSERVER.sh."
            )
        active_profile = profile.profile.value

    if args.headless_check:
        print(json.dumps(headless_contract(database, candidate=args.candidate, active_profile=active_profile), indent=2, sort_keys=True))
        return 0
    return _build_and_run(
        theme=(ThemeMode(args.theme) if args.theme is not None else None),
        database=database,
        auto_close_ms=args.auto_close_ms,
        candidate=args.candidate,
    )


if __name__ == "__main__":
    raise SystemExit(main())
