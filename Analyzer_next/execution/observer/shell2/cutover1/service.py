"""Guarded profile state, acceptance receipt, and rollback for OL2-CUTOVER1."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

from .model import AcceptanceReceipt, CutoverError, LauncherProfile, ProfileRecord, ReleaseAuthorization

PROFILE_SCHEMA = "archon.observer-launcher-profile.v1"
ACCEPTANCE_SCHEMA = "archon.ol2-cutover-acceptance.v1"
MILESTONE = "OL2-CUTOVER1"
RELEASE_SCHEMA = "archon.ol2-release-production-authorization.v1"
RELEASE_MILESTONE = "RELEASE1-PRODUCTION-BOOTSTRAP"
RELEASE_AUTHORIZATION_RELATIVE = "Release/ARCHON_RELEASE1_PRODUCTION.json"
FINAL_RELEASE_SCHEMA = "archon.release6-production-authorization.v1"
FINAL_RELEASE_MILESTONE = "RELEASE6-FINAL-PRODUCTION-SEAL"
FINAL_RELEASE_VERSION = "1.0.0"
FINAL_FINGERPRINT_POLICY = "release3-runtime-assets-and-control-manifests-v1"
FINAL_CONTROL_MANIFESTS = (
    "Release/RELEASE3/runtime_whitelist.txt",
    "Release/RELEASE3/asset_whitelist.txt",
    "Release/RELEASE3/bootstrap_whitelist.txt",
    "Release/RELEASE3/packaging_whitelist.txt",
)

# These are source/runtime inputs whose exact revisions the human accepts when
# activating OL2.  The list intentionally excludes mutable evidence/state.
ACCEPTANCE_FINGERPRINTS = (
    # Stable launcher routing and the final cutover gate itself are part of the
    # accepted production surface.  Mutable profile/receipt state remains
    # intentionally excluded.
    "OBSERVER.sh",
    "Analyzer_next/cli/observer_launcher_profile.py",
    "Analyzer_next/execution/observer/shell2/cutover1/model.py",
    "Analyzer_next/execution/observer/shell2/cutover1/service.py",
    # Cross-shell contracts and view identity are runtime truthfulness inputs.
    "Analyzer_next/execution/observer/contracts.py",
    "Analyzer_next/execution/observer/shell2/view_model.py",
    # Analyze Results is a production command surface and must be bound to the
    # same accepted source revision as automatic BRIDGE5.7 refresh.
    "Analyzer_next/execution/observer/shell2/analyze1/__init__.py",
    "Analyzer_next/execution/observer/shell2/analyze1/app.py",
    "Analyzer_next/execution/observer/shell2/analyze1/controller.py",
    "Analyzer_next/execution/observer/shell2/analyze1/model.py",
    # CONTROL1 / QUEUE1 / QUEUE2 source revisions own process, queue and
    # recovery truthfulness.
    "Analyzer_next/execution/observer/shell2/control1/app.py",
    "Analyzer_next/execution/observer/shell2/control1/model.py",
    "Analyzer_next/execution/observer/shell2/control1/store.py",
    "Analyzer_next/execution/observer/shell2/queue1/app.py",
    "Analyzer_next/execution/observer/shell2/queue1/model.py",
    "Analyzer_next/execution/observer/shell2/queue2/__init__.py",
    "Analyzer_next/execution/observer/shell2/queue2/app.py",
    "Analyzer_next/execution/observer/shell2/queue2/controller.py",
    "Analyzer_next/adapters/observer/queue_journal.py",
    # Authoritative cycle ownership is part of the final scientific E2E.
    "Analyzer_next/adapters/observer/authoritative_cycle_lifecycle.py",
    "Analyzer_next/research/cycle/authoritative_lifecycle.py",
    "Analyzer_next/cli/observer_launcher_2.py",
    "Analyzer_next/execution/observer/shell2/observe1/app.py",
    "Analyzer_next/execution/observer/shell2/layout1/app.py",
    "Analyzer_next/execution/observer/shell2/interact1/app.py",
    "Analyzer_next/execution/observer/shell2/interact1/controller.py",
    "Analyzer_next/execution/observer/shell2/functions1a/app.py",
    "Analyzer_next/execution/observer/shell2/functions1a/search.py",
    "Analyzer_next/execution/observer/shell2/functions1b/app.py",
    "Analyzer_next/execution/observer/shell2/functions1b/controller.py",
    "Analyzer_next/execution/observer/shell2/functions1c/app.py",
    "Analyzer_next/execution/observer/shell2/functions1c/controller.py",
    "Analyzer_next/execution/observer/shell2/functions1c/model.py",
    "Analyzer_next/execution/observer/shell2/functions1d/app.py",
    "Analyzer_next/execution/observer/shell2/functions1d/controller.py",
    "Analyzer_next/execution/observer/shell2/functions1d/model.py",
    "Analyzer_next/adapters/observer/experiment_catalog.py",
    "Analyzer_next/adapters/observer/experiment_catalog_compat.py",
    "Analyzer_next/adapters/observer/experiment_target_context.py",
    "Analyzer_next/execution/observer/shell2/functions1e/app.py",
    "Analyzer_next/execution/observer/shell2/functions1e/controller.py",
    "Analyzer_next/execution/observer/shell2/functions1e/model.py",
    "Analyzer_next/adapters/observer/director_proposals.py",
    "Analyzer_next/research/director/governance/proposals.py",
    "Analyzer_next/execution/observer/shell2/functions1f/app.py",
    "Analyzer_next/execution/observer/shell2/functions1f/controller.py",
    "Analyzer_next/execution/observer/shell2/functions1f/model.py",
    "Analyzer_next/adapters/observer/research_experiment_pipeline.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix1/__init__.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix1/app.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix2/__init__.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix2/app.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix3/__init__.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix3/app.py",
    "Analyzer_next/adapters/observer/experiment_runtime_policy_compat.py",
    "Analyzer_next/cli/approved_action_planner_intake_compat.py",
    "Analyzer_next/adapters/observer/research_experiment_pipeline_fix3.py",
    "Analyzer_next/adapters/observer/experiment_runtime_handoff_fix3.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix4/__init__.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix4/app.py",
    "Analyzer_next/adapters/observer/experiment_runtime_policy_compat_fix4.py",
    "Analyzer_next/adapters/observer/research_experiment_pipeline_fix4.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix5/__init__.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix5/app.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix6/__init__.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix6/app.py",
    "Analyzer_next/adapters/observer/experiment_authorization_state.py",
    "Analyzer_next/adapters/observer/experiment_runtime_handoff_fix6.py",
    "Analyzer_next/adapters/observer/research_experiment_pipeline_fix6.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix7/__init__.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix7/app.py",
    "Analyzer_next/adapters/observer/experiment_runtime_command_fix7.py",
    "Analyzer_next/adapters/observer/experiment_runtime_handoff_fix7.py",
    "Analyzer_next/adapters/observer/cohort_search_runtime.py",
    "Analyzer_next/adapters/observer/cohort_search_execution_handoff.py",
    "Analyzer_next/adapters/observer/experiment_runtime_handoff_bridge4.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix8/__init__.py",
    "Analyzer_next/execution/observer/shell2/experiments_fix8/app.py",
    "Analyzer_next/execution/observer/shell2/vis1/__init__.py",
    "Analyzer_next/execution/observer/shell2/vis1/app.py",
    "Analyzer_next/execution/observer/shell2/vis1/overflow.py",
    "Analyzer_next/execution/observer/shell2/scientific_refresh1/__init__.py",
    "Analyzer_next/execution/observer/shell2/scientific_refresh1/app.py",
    "Analyzer_next/adapters/observer/automatic_scientific_refresh.py",
    "Analyzer_next/production/automatic_refresh.py",
    "Analyzer_next/cli/automatic_scientific_refresh.py",
    # FUNCTIONS1G remains optional while Experiments is developed as a separate track.
    # If those files are installed they are fingerprinted; a clean FUNCTIONS1F baseline
    # does not fail acceptance merely because FUNCTIONS1G is absent.
    "Analyzer_next/execution/observer/shell2/functions1g/app.py",
    "Analyzer_next/execution/observer/shell2/functions1g/controller.py",
    "Analyzer_next/execution/observer/shell2/functions1g/model.py",
    "Analyzer_next/adapters/observer/experiment_runtime_handoff.py",
    "Analyzer_next/adapters/observer/verified_experiment_queue_authorization.py",
    "Analyzer_next/execution/observer/shell2/catalog1/__init__.py",
    "Analyzer_next/execution/observer/shell2/catalog1/cache.py",
    "Analyzer_next/execution/observer/shell2/catalog1/catalog.py",
    "Analyzer_next/execution/observer/shell2/catalog1/store.py",
    "Analyzer_next/execution/observer/shell2/mutations1/app.py",
    "Analyzer_next/execution/observer/shell2/mutations1/controller.py",
    "Analyzer_next/execution/observer/shell2/mutations1/model.py",
    "Analyzer_next/execution/observer/shell2/mutations2/app.py",
    "Analyzer_next/execution/observer/shell2/mutations2/controller.py",
    "Analyzer_next/execution/observer/shell2/mutations2/model.py",
    "Analyzer_next/adapters/observer/mutation_analysis.py",
    "Analyzer_next/cli/mutation_report_one.py",
    "Analyzer_next/execution/observer/shell2/campaigns1/app.py",
    "Analyzer_next/execution/observer/shell2/campaigns1/controller.py",
    "Analyzer_next/execution/observer/shell2/campaigns1/model.py",
    "Analyzer_next/execution/observer/shell2/save_policy1/app.py",
    "Analyzer_next/execution/observer/shell2/save_policy1/model.py",
    "Analyzer_next/execution/observer/shell2/save_policy1/service.py",
    "Analyzer_next/execution/observer/shell2/save_policy1/campaign_controller.py",
    "Analyzer_next/execution/observer/shell2/dialogs1/app.py",
    "Analyzer_next/execution/observer/shell2/dialogs1/modal.py",
    "Analyzer_next/execution/observer/shell2/dialogs1/model.py",
    "Analyzer_next/adapters/observer/mutation_workspace.py",
    "Analyzer_next/adapters/telemetry/routed_live.py",
    "Analyzer_next/adapters/observer/ui_preferences.py",
    "Analyzer_next/adapters/observer/desktop_path_opener.py",
    "Analyzer_next/execution/observer/shell2/observe1/controller.py",
    "Analyzer_next/execution/observer/shell2/queue1/controller.py",
    "Analyzer_next/execution/observer/shell2/control1/controller.py",
    "Analyzer_next/execution/observer/shell2/telem1/controller.py",
    "Analyzer_next/adapters/observer/presentation_process_runner.py",
    "Analyzer_next/adapters/observer/interactive_process_runner.py",
    "Analyzer_next/adapters/observer/legacy_interactive_bridge.py",
    "Analyzer_next/adapters/observer/process_runner.py",
    "Observer/universe_search_observer_v441_validation_calibration.py",
    "Observer/observer_launcher.py",
)

OPTIONAL_ACCEPTANCE_FINGERPRINTS = frozenset({
    "Analyzer_next/execution/observer/shell2/functions1g/app.py",
    "Analyzer_next/execution/observer/shell2/functions1g/controller.py",
    "Analyzer_next/execution/observer/shell2/functions1g/model.py",
    "Analyzer_next/adapters/observer/experiment_runtime_handoff.py",
    "Analyzer_next/adapters/observer/verified_experiment_queue_authorization.py",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


class CutoverService:
    """Own launcher profile selection without owning any scientific runtime."""

    def __init__(
        self,
        project_root: Path,
        *,
        profile_path: Path | None = None,
        acceptance_path: Path | None = None,
        release_authorization_path: Path | None = None,
        fingerprint_paths: Iterable[str] = ACCEPTANCE_FINGERPRINTS,
    ) -> None:
        self.project_root = project_root.resolve()
        self.profile_path = (profile_path or (self.project_root / "Config/ObserverLauncher/launcher_profile.json")).resolve()
        self.acceptance_path = (acceptance_path or (self.project_root / "Results/Analysis/ObserverLauncher2/OL2_CUTOVER1_ACCEPTANCE.json")).resolve()
        self.release_authorization_path = (
            release_authorization_path or (self.project_root / RELEASE_AUTHORIZATION_RELATIVE)
        ).resolve()
        self.fingerprint_paths = tuple(fingerprint_paths)

    @property
    def default_profile(self) -> LauncherProfile:
        # This preserves the current OBSERVER.sh target before explicit OL2
        # acceptance: Observer/observer_launcher.py.
        return LauncherProfile.MODULAR_V1

    def target_path(self, profile: LauncherProfile) -> Path | None:
        if profile is LauncherProfile.LEGACY:
            raise CutoverError(
                "The pre-modular legacy launcher profile is retired; "
                "use modular-v1 for rollback"
            )
        if profile is LauncherProfile.MODULAR_V1:
            return self.project_root / "Observer/observer_launcher.py"
        if profile is LauncherProfile.OL2:
            return self.project_root / "Analyzer_next/cli/observer_launcher_2.py"
        raise CutoverError(f"Unsupported launcher profile: {profile}")

    def fingerprints(self) -> dict[str, str]:
        rows: dict[str, str] = {}
        for relative in self.fingerprint_paths:
            path = self.project_root / relative
            if not path.is_file():
                if relative in OPTIONAL_ACCEPTANCE_FINGERPRINTS:
                    continue
                raise CutoverError(f"Acceptance input missing: {relative}")
            rows[relative] = _sha256_file(path)
        return rows

    def final_fingerprint_paths(self) -> tuple[str, ...]:
        """Return the complete non-circular v1.0 production trust surface."""
        paths: set[str] = set(FINAL_CONTROL_MANIFESTS)
        for manifest in (
            "Release/RELEASE3/runtime_whitelist.txt",
            "Release/RELEASE3/asset_whitelist.txt",
        ):
            source = self.project_root / manifest
            try:
                rows = [
                    line.strip()
                    for line in source.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except OSError as exc:
                raise CutoverError(f"Final seal manifest is unavailable: {manifest}: {exc}") from exc
            if rows != sorted(set(rows)):
                raise CutoverError(f"Final seal manifest is not sorted and unique: {manifest}")
            paths.update(rows)
        paths.discard(RELEASE_AUTHORIZATION_RELATIVE)
        for relative in sorted(paths):
            pure = PurePosixPath(relative)
            if pure.is_absolute() or not pure.parts or ".." in pure.parts:
                raise CutoverError(f"Unsafe final seal path: {relative}")
            if relative.startswith(("Atlas/Knowledge/", "Atlas/Worlds/", "Config/", "Results/")):
                raise CutoverError(f"Mutable state entered final seal: {relative}")
            if not (self.project_root / relative).is_file():
                raise CutoverError(f"Final seal input missing: {relative}")
        return tuple(sorted(paths))

    def final_fingerprints(self) -> dict[str, str]:
        return {
            relative: _sha256_file(self.project_root / relative)
            for relative in self.final_fingerprint_paths()
        }

    def _acceptance_payload_without_hash(
        self,
        *,
        visual_acceptance: bool,
        operational_acceptance: bool,
        accepted_at: str,
        fingerprints: dict[str, str],
    ) -> dict[str, object]:
        return {
            "schema": ACCEPTANCE_SCHEMA,
            "milestone": MILESTONE,
            "candidate_profile": LauncherProfile.OL2.value,
            "visual_acceptance": bool(visual_acceptance),
            "operational_acceptance": bool(operational_acceptance),
            "accepted_at": accepted_at,
            "fingerprints": dict(sorted(fingerprints.items())),
        }

    def create_acceptance(
        self,
        *,
        visual_acceptance: bool,
        operational_acceptance: bool,
    ) -> AcceptanceReceipt:
        if not visual_acceptance or not operational_acceptance:
            raise CutoverError("OL2 activation requires both visual and operational human acceptance")
        accepted_at = _utc_now()
        fingerprints = self.fingerprints()
        payload = self._acceptance_payload_without_hash(
            visual_acceptance=True,
            operational_acceptance=True,
            accepted_at=accepted_at,
            fingerprints=fingerprints,
        )
        receipt_hash = _sha256_bytes(_canonical_bytes(payload))
        document = {**payload, "receipt_hash": receipt_hash}
        _atomic_write_json(self.acceptance_path, document)
        return AcceptanceReceipt(
            schema=ACCEPTANCE_SCHEMA,
            milestone=MILESTONE,
            candidate_profile=LauncherProfile.OL2,
            visual_acceptance=True,
            operational_acceptance=True,
            accepted_at=accepted_at,
            fingerprints=fingerprints,
            receipt_hash=receipt_hash,
        )

    def read_acceptance(self, *, verify_current_sources: bool = True) -> AcceptanceReceipt:
        try:
            payload = json.loads(self.acceptance_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CutoverError("OL2 acceptance receipt does not exist") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise CutoverError(f"Cannot read OL2 acceptance receipt: {exc}") from exc
        if payload.get("schema") != ACCEPTANCE_SCHEMA or payload.get("milestone") != MILESTONE:
            raise CutoverError("Invalid OL2 acceptance receipt schema/milestone")
        if payload.get("candidate_profile") != LauncherProfile.OL2.value:
            raise CutoverError("Acceptance receipt does not authorize OL2")
        if payload.get("visual_acceptance") is not True or payload.get("operational_acceptance") is not True:
            raise CutoverError("Acceptance receipt is missing required human acceptance")
        supplied_hash = str(payload.get("receipt_hash") or "")
        canonical = {key: value for key, value in payload.items() if key != "receipt_hash"}
        actual_hash = _sha256_bytes(_canonical_bytes(canonical))
        if not supplied_hash or supplied_hash != actual_hash:
            raise CutoverError("Acceptance receipt hash mismatch")
        fingerprints = payload.get("fingerprints")
        if not isinstance(fingerprints, dict) or not fingerprints:
            raise CutoverError("Acceptance receipt has no source fingerprints")
        normalized = {str(k): str(v) for k, v in fingerprints.items()}
        if verify_current_sources:
            current = self.fingerprints()
            if normalized != current:
                changed = sorted(set(normalized) | set(current))
                delta = [name for name in changed if normalized.get(name) != current.get(name)]
                raise CutoverError("Accepted OL2 sources changed after acceptance: " + ", ".join(delta))
        try:
            accepted_at = str(payload["accepted_at"])
        except KeyError as exc:
            raise CutoverError("Acceptance receipt has no accepted_at") from exc
        return AcceptanceReceipt(
            schema=ACCEPTANCE_SCHEMA,
            milestone=MILESTONE,
            candidate_profile=LauncherProfile.OL2,
            visual_acceptance=True,
            operational_acceptance=True,
            accepted_at=accepted_at,
            fingerprints=normalized,
            receipt_hash=supplied_hash,
        )

    def _release_payload_without_hash(
        self,
        *,
        parent_acceptance_receipt_hash: str,
        sealed_at: str,
        fingerprints: dict[str, str],
    ) -> dict[str, object]:
        return {
            "schema": RELEASE_SCHEMA,
            "milestone": RELEASE_MILESTONE,
            "launcher_profile": LauncherProfile.OL2.value,
            "cutover_milestone": MILESTONE,
            "parent_acceptance_receipt_hash": parent_acceptance_receipt_hash,
            "sealed_at": sealed_at,
            "fingerprints": dict(sorted(fingerprints.items())),
            "bootstrap_policy": "clean-install-default-ol2",
        }

    def create_release_authorization(self) -> ReleaseAuthorization:
        """Seal a portable OL2 production authorization from current human acceptance.

        This is intentionally a release/build operation.  It cannot bootstrap trust
        from itself: the current source tree must first be covered by a valid local
        OL2 human-acceptance receipt and active OL2 profile.
        """

        profile = self.read_profile(verify_ol2_acceptance=True)
        if profile.profile is not LauncherProfile.OL2:
            raise CutoverError("RELEASE1 sealing requires the locally accepted OL2 production profile")
        receipt = self.read_acceptance(verify_current_sources=True)
        if profile.acceptance_receipt_hash != receipt.receipt_hash:
            raise CutoverError("RELEASE1 sealing requires the active profile to be bound to the current OL2 acceptance receipt")
        fingerprints = self.fingerprints()
        sealed_at = _utc_now()
        payload = self._release_payload_without_hash(
            parent_acceptance_receipt_hash=receipt.receipt_hash,
            sealed_at=sealed_at,
            fingerprints=fingerprints,
        )
        authorization_hash = _sha256_bytes(_canonical_bytes(payload))
        document = {**payload, "authorization_hash": authorization_hash}
        _atomic_write_json(self.release_authorization_path, document)
        return ReleaseAuthorization(
            schema=RELEASE_SCHEMA,
            milestone=RELEASE_MILESTONE,
            launcher_profile=LauncherProfile.OL2,
            cutover_milestone=MILESTONE,
            parent_acceptance_receipt_hash=receipt.receipt_hash,
            sealed_at=sealed_at,
            fingerprints=fingerprints,
            authorization_hash=authorization_hash,
        )

    def create_final_release_authorization(
        self,
        *,
        preflight_hash: str,
    ) -> ReleaseAuthorization:
        """Replace the legacy seal with a source-complete RELEASE6 authorization."""
        if not preflight_hash:
            raise CutoverError("RELEASE6 sealing requires a verified preflight hash")
        profile = self.read_profile(verify_ol2_acceptance=True)
        if profile.profile is not LauncherProfile.OL2:
            raise CutoverError("RELEASE6 sealing requires the locally accepted OL2 profile")
        receipt = self.read_acceptance(verify_current_sources=True)
        if profile.acceptance_receipt_hash != receipt.receipt_hash:
            raise CutoverError("RELEASE6 sealing requires the active profile to match current human acceptance")
        fingerprints = self.final_fingerprints()
        sealed_at = _utc_now()
        source_tree_hash = _sha256_bytes(_canonical_bytes(fingerprints))
        payload: dict[str, object] = {
            "schema": FINAL_RELEASE_SCHEMA,
            "milestone": FINAL_RELEASE_MILESTONE,
            "release_version": FINAL_RELEASE_VERSION,
            "launcher_profile": LauncherProfile.OL2.value,
            "cutover_milestone": MILESTONE,
            "parent_acceptance_receipt_hash": receipt.receipt_hash,
            "preflight_hash": preflight_hash,
            "sealed_at": sealed_at,
            "fingerprint_policy": FINAL_FINGERPRINT_POLICY,
            "source_tree_hash": source_tree_hash,
            "fingerprints": dict(sorted(fingerprints.items())),
            "bootstrap_policy": "clean-install-default-ol2",
        }
        authorization_hash = _sha256_bytes(_canonical_bytes(payload))
        document = {**payload, "authorization_hash": authorization_hash}
        _atomic_write_json(self.release_authorization_path, document)
        return ReleaseAuthorization(
            schema=FINAL_RELEASE_SCHEMA,
            milestone=FINAL_RELEASE_MILESTONE,
            launcher_profile=LauncherProfile.OL2,
            cutover_milestone=MILESTONE,
            parent_acceptance_receipt_hash=receipt.receipt_hash,
            sealed_at=sealed_at,
            fingerprints=fingerprints,
            authorization_hash=authorization_hash,
        )

    def read_release_authorization(self, *, verify_current_sources: bool = True) -> ReleaseAuthorization:
        try:
            payload = json.loads(self.release_authorization_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CutoverError("RELEASE1 production authorization does not exist") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise CutoverError(f"Cannot read RELEASE1 production authorization: {exc}") from exc
        schema = payload.get("schema")
        milestone = payload.get("milestone")
        legacy = schema == RELEASE_SCHEMA and milestone == RELEASE_MILESTONE
        final = schema == FINAL_RELEASE_SCHEMA and milestone == FINAL_RELEASE_MILESTONE
        if not legacy and not final:
            raise CutoverError("Invalid production authorization schema/milestone")
        if payload.get("launcher_profile") != LauncherProfile.OL2.value:
            raise CutoverError("RELEASE1 production authorization does not authorize OL2")
        if payload.get("cutover_milestone") != MILESTONE:
            raise CutoverError("RELEASE1 production authorization is not rooted in OL2-CUTOVER1")
        parent_hash = str(payload.get("parent_acceptance_receipt_hash") or "")
        if not parent_hash:
            raise CutoverError("RELEASE1 production authorization has no parent acceptance hash")
        supplied_hash = str(payload.get("authorization_hash") or "")
        canonical = {key: value for key, value in payload.items() if key != "authorization_hash"}
        actual_hash = _sha256_bytes(_canonical_bytes(canonical))
        if not supplied_hash or supplied_hash != actual_hash:
            raise CutoverError("RELEASE1 production authorization hash mismatch")
        if payload.get("bootstrap_policy") != "clean-install-default-ol2":
            raise CutoverError("RELEASE1 production authorization has an invalid bootstrap policy")
        fingerprints = payload.get("fingerprints")
        if not isinstance(fingerprints, dict) or not fingerprints:
            raise CutoverError("RELEASE1 production authorization has no source fingerprints")
        normalized = {str(k): str(v) for k, v in fingerprints.items()}
        if final:
            if payload.get("release_version") != FINAL_RELEASE_VERSION:
                raise CutoverError("RELEASE6 production authorization has an invalid release version")
            if payload.get("fingerprint_policy") != FINAL_FINGERPRINT_POLICY:
                raise CutoverError("RELEASE6 production authorization has an invalid fingerprint policy")
            if not payload.get("preflight_hash"):
                raise CutoverError("RELEASE6 production authorization has no preflight hash")
            expected_paths = set(self.final_fingerprint_paths())
            if set(normalized) != expected_paths:
                raise CutoverError("RELEASE6 production authorization fingerprint coverage mismatch")
            expected_tree_hash = _sha256_bytes(_canonical_bytes(normalized))
            if payload.get("source_tree_hash") != expected_tree_hash:
                raise CutoverError("RELEASE6 production authorization source tree hash mismatch")
        if verify_current_sources:
            current = self.final_fingerprints() if final else self.fingerprints()
            if normalized != current:
                changed = sorted(set(normalized) | set(current))
                delta = [name for name in changed if normalized.get(name) != current.get(name)]
                prefix = "RELEASE6-authorized production sources" if final else "RELEASE1-authorized OL2 sources"
                raise CutoverError(prefix + " changed after sealing: " + ", ".join(delta))
        sealed_at = str(payload.get("sealed_at") or "")
        if not sealed_at:
            raise CutoverError("RELEASE1 production authorization has no sealed_at")
        return ReleaseAuthorization(
            schema=str(schema),
            milestone=str(milestone),
            launcher_profile=LauncherProfile.OL2,
            cutover_milestone=MILESTONE,
            parent_acceptance_receipt_hash=parent_hash,
            sealed_at=sealed_at,
            fingerprints=normalized,
            authorization_hash=supplied_hash,
        )

    def source_modifications(self, *, acceptance_bound: bool = False) -> tuple[str, ...]:
        """Return source files that differ from the trusted receipt/seal.

        Structural integrity of the receipt/authorization is still verified
        fail-closed.  A non-empty result means the local source tree has been
        modified after acceptance/sealing; this is provenance information, not
        a runtime authorization failure for an open source checkout.
        """
        if acceptance_bound:
            receipt = self.read_acceptance(verify_current_sources=False)
            trusted = dict(receipt.fingerprints)
            current = self.fingerprints()
        else:
            authorization = self.read_release_authorization(verify_current_sources=False)
            trusted = dict(authorization.fingerprints)
            current = (
                self.final_fingerprints()
                if authorization.schema == FINAL_RELEASE_SCHEMA
                else self.fingerprints()
            )
        changed = sorted(set(trusted) | set(current))
        return tuple(name for name in changed if trusted.get(name) != current.get(name))

    def _implicit_profile(
        self,
        *,
        verify_ol2_acceptance: bool,
        allow_modified_sources: bool = False,
    ) -> ProfileRecord:
        # Unsealed source trees preserve the historical fail-closed default.
        if not self.release_authorization_path.exists():
            return ProfileRecord(PROFILE_SCHEMA, self.default_profile, "implicit-default", None)
        if verify_ol2_acceptance:
            self.read_release_authorization(verify_current_sources=not allow_modified_sources)
        return ProfileRecord(PROFILE_SCHEMA, LauncherProfile.OL2, "release-default", None)

    def read_profile(
        self,
        *,
        verify_ol2_acceptance: bool = True,
        allow_modified_sources: bool = False,
    ) -> ProfileRecord:
        if not self.profile_path.exists():
            return self._implicit_profile(
                verify_ol2_acceptance=verify_ol2_acceptance,
                allow_modified_sources=allow_modified_sources,
            )
        try:
            payload = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CutoverError(f"Cannot read launcher profile: {exc}") from exc
        if payload.get("schema") != PROFILE_SCHEMA:
            raise CutoverError("Invalid launcher profile schema")
        try:
            profile = LauncherProfile(str(payload.get("profile")))
        except ValueError as exc:
            raise CutoverError(f"Unknown launcher profile: {payload.get('profile')!r}") from exc
        acceptance_hash = payload.get("acceptance_receipt_hash")
        if profile is LauncherProfile.OL2 and verify_ol2_acceptance:
            if acceptance_hash:
                receipt = self.read_acceptance(verify_current_sources=not allow_modified_sources)
                if str(acceptance_hash) != receipt.receipt_hash:
                    raise CutoverError("OL2 profile is not bound to the current acceptance receipt")
            else:
                # A clean sealed release has no machine-local human acceptance
                # receipt.  Its explicit OL2 profile is authorized only by the
                # portable, source-bound RELEASE1 production authorization.
                if self.acceptance_path.exists():
                    raise CutoverError("OL2 profile has local acceptance state but is not bound to it")
                self.read_release_authorization(verify_current_sources=not allow_modified_sources)
        return ProfileRecord(
            PROFILE_SCHEMA,
            profile,
            str(payload.get("updated_at") or ""),
            str(acceptance_hash) if acceptance_hash else None,
        )

    def set_profile(self, profile: LauncherProfile) -> ProfileRecord:
        if profile is LauncherProfile.LEGACY:
            raise CutoverError(
                "The pre-modular legacy launcher profile is retired; "
                "use modular-v1 for rollback"
            )
        acceptance_hash: str | None = None
        if profile is LauncherProfile.OL2:
            if self.acceptance_path.exists():
                receipt = self.read_acceptance(verify_current_sources=True)
                acceptance_hash = receipt.receipt_hash
            else:
                # Re-activation after a release rollback is allowed only when
                # the sealed release authorization still matches current source.
                self.read_release_authorization(verify_current_sources=True)
        record = {
            "schema": PROFILE_SCHEMA,
            "profile": profile.value,
            "updated_at": _utc_now(),
            "acceptance_receipt_hash": acceptance_hash,
        }
        _atomic_write_json(self.profile_path, record)
        return ProfileRecord(
            PROFILE_SCHEMA,
            profile,
            str(record["updated_at"]),
            acceptance_hash,
        )

    def accept_and_activate(self) -> tuple[AcceptanceReceipt, ProfileRecord]:
        receipt = self.create_acceptance(visual_acceptance=True, operational_acceptance=True)
        profile = self.set_profile(LauncherProfile.OL2)
        return receipt, profile

    def rollback(self, *, to: LauncherProfile = LauncherProfile.MODULAR_V1) -> ProfileRecord:
        if to is not LauncherProfile.MODULAR_V1:
            raise CutoverError("Release rollback target is modular-v1")
        return self.set_profile(to)
