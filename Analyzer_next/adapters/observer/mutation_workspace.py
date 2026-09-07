"""Native mutation workspace adapter for OL2-MUTATIONS1.

Canonical Atlas rules are read-only inputs. Mutation materialization delegates to
Observer.observer_mutation_engine and writes only beneath mutation_runs.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from Observer.observer_mutation_engine import (
    PRESETS,
    capture_baseline_provenance,
    create_mutation_run,
    diff_payload,
    mutate_local_random,
    mutate_single_parameter,
    parameter_choices,
    stable_payload_hash,
)

from Analyzer_next.execution.observer.runs.command_builder import CommandBuilderMixin
from Analyzer_next.execution.observer.settings import ANALYSIS_RESULTS_DIR, SEARCH_RESULTS_DIR
from Analyzer_next.execution.observer.shell2.config1.catalog_adapter import NativeWorldCatalog
from Analyzer_next.execution.observer.shell2.config1.model import (
    ConfigurationDraft,
    PreparedConfiguration,
    ProvenanceKind,
    canonical_hash,
)
from Analyzer_next.execution.observer.shell2.mutations1.model import (
    MutationDraft,
    MutationPreview,
    MutationRecord,
    MutationStrategy,
)
from Analyzer_next.execution.observer.state import RunSpec


class _Value:
    def __init__(self, value: Any) -> None:
        self.value = value
    def get(self) -> Any:
        return self.value


class _MutationCommandHarness(CommandBuilderMixin):
    """Tk-free variables around the existing Observer command builder."""

    def __init__(self, draft: ConfigurationDraft) -> None:
        assert draft.world is not None
        self.rule_var = _Value(f"{draft.world.rule_id:05d}")
        self.cell_var = _Value(draft.cell_size)
        self.speed_var = _Value(draft.speed)
        self.delay_var = _Value(draft.frame_delay_ms)
        self.autosave_var = _Value(draft.autosave_every)
        self.sample_every_var = _Value(draft.sample_every)
        self.pressure_every_var = _Value(draft.pressure_every)
        self.max_ticks_var = _Value(draft.max_ticks)
        self.auto_stop_var = _Value(False)
        self.samples_var = _Value("samples" in draft.outputs)
        self.events_var = _Value("events" in draft.outputs)
        self.pressure_var = _Value("pressure" in draft.outputs)
        self.chronicle_var = _Value("chronicle" in draft.outputs)
        self.passport_var = _Value("passport" in draft.outputs)
        self.log_var = _Value("log" in draft.outputs)
        self.sqlite_var = _Value("sqlite" in draft.outputs)
        self.evidence_var = _Value("evidence" in draft.outputs)

    def _selected_experimental_context(self) -> None:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()




class SnapshotWorldCatalog:
    """Cheap view over the CONFIG1 world snapshot already loaded by the Launcher.

    MUTATIONS1 must not rescan Atlas/observation_logs on every route mount or
    parameter lookup.  The provider stays dynamic so an explicit CONFIG1
    catalog refresh is visible to Mutations without a second filesystem walk.
    """

    def __init__(self, provider: Callable[[], Iterable[Any]]) -> None:
        self._provider = provider

    def load_worlds(self):
        return tuple(self._provider())


class NativeMutationWorkspace:
    """Read canonical sources, materialize isolated mutations, and prepare launches."""

    def __init__(
        self,
        *,
        source_catalog: NativeWorldCatalog | None = None,
        results_root: Path | None = None,
        mutation_root: Path | None = None,
        analysis_root: Path | None = None,
    ) -> None:
        self.source_catalog = source_catalog or NativeWorldCatalog()
        self.results_root = Path(results_root or SEARCH_RESULTS_DIR).resolve()
        self.mutation_root = Path(mutation_root or (self.results_root / "mutation_runs")).resolve()
        self.analysis_root = Path(
            analysis_root or (ANALYSIS_RESULTS_DIR / "Mutations")
        ).resolve()

    def load_worlds(self):
        return self.source_catalog.load_worlds()

    def _world(self, rule_id: int):
        world = next((item for item in self.load_worlds() if item.rule_id == int(rule_id)), None)
        if world is None:
            raise ValueError(f"canonical source rule not found: {rule_id}")
        if not world.source_verified or not world.source_path:
            raise ValueError(f"canonical source is not verified: {world.display_id}")
        source = Path(world.source_path).expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"canonical source file is missing: {source}")
        payload = _read_json(source)
        if int(payload.get("rule_id", -1)) != world.rule_id:
            raise ValueError("canonical source identity mismatch")
        return world, source, payload

    def parameter_choices(self, rule_id: int) -> tuple[str, ...]:
        _world, _source, payload = self._world(rule_id)
        return tuple(parameter_choices(payload))

    @staticmethod
    def _mutated_payload(payload: dict[str, Any], draft: MutationDraft, seed: int) -> dict[str, Any]:
        rng = random.Random(seed)
        if draft.strategy is MutationStrategy.SINGLE_PARAMETER:
            if not draft.parameter:
                raise ValueError("Single parameter strategy requires a parameter")
            return mutate_single_parameter(payload, draft.parameter, draft.intensity, rng)
        if draft.strategy is MutationStrategy.LOCAL_RANDOM:
            return mutate_local_random(payload, draft.intensity, rng)
        if draft.strategy is MutationStrategy.PRESET:
            config = PRESETS.get(draft.preset)
            if config is None:
                raise ValueError(f"Unknown mutation preset: {draft.preset}")
            return mutate_local_random(
                payload,
                draft.intensity * config["scale_multiplier"],
                rng,
                field_probability=config["field_probability"],
                term_probability=config["term_probability"],
            )
        raise ValueError(f"Unsupported mutation strategy: {draft.strategy}")

    def preview(self, draft: MutationDraft) -> MutationPreview:
        if draft.source_rule_id is None:
            raise ValueError("select a canonical source rule first")
        _world, _source, payload = self._world(draft.source_rule_id)
        seed = int(draft.seed) if int(draft.seed) > 0 else 1_234_567
        mutated = self._mutated_payload(payload, draft, seed)
        changes = tuple(diff_payload(payload, mutated))
        baseline = capture_baseline_provenance(
            original_rule=payload,
            results_root=self.results_root,
        )
        if baseline.get("status") == "resolved":
            detail = (
                f"Run {baseline.get('run_id')} • final tick {baseline.get('samples_final_tick')}"
            )
        else:
            detail = str(baseline.get("reason") or "No resolved canonical baseline")
        return MutationPreview(
            source_rule_id=draft.source_rule_id,
            strategy=draft.strategy.value,
            seed=seed,
            mutated_hash=stable_payload_hash(mutated),
            change_count=len(changes),
            changes=changes,
            baseline_status=str(baseline.get("status") or "unavailable"),
            baseline_detail=detail,
        )

    def materialize(self, draft: MutationDraft) -> tuple[MutationRecord, ...]:
        if draft.source_rule_id is None:
            raise ValueError("select a canonical source rule first")
        _world, _source, payload = self._world(draft.source_rule_id)
        baseline = capture_baseline_provenance(
            original_rule=payload,
            results_root=self.results_root,
        )
        if baseline.get("status") != "resolved":
            raise ValueError(
                "No resolved canonical baseline exists for this rule. "
                "Observe and save the canonical rule before creating mutations."
            )
        base_seed = int(draft.seed)
        if base_seed == 0:
            base_seed = int(time.time() * 1000) & 0x7FFFFFFF
        created: list[MutationRecord] = []
        self.mutation_root.mkdir(parents=True, exist_ok=True)
        for index in range(1, int(draft.count) + 1):
            run = create_mutation_run(
                original_rule=payload,
                mutation_root=self.mutation_root,
                mode=draft.strategy.value,
                intensity=float(draft.intensity),
                seed=base_seed + index - 1,
                parameter=(draft.parameter if draft.strategy is MutationStrategy.SINGLE_PARAMETER else None),
                preset=draft.preset,
                sequence=index,
                baseline_provenance=baseline,
            )
            created.append(self._record_from_manifest(Path(run["manifest_file"])))
        return tuple(created)

    def _record_from_manifest(self, manifest_path: Path) -> MutationRecord:
        manifest_path = manifest_path.resolve()
        payload = _read_json(manifest_path)
        if payload.get("schema") != "archon_observer_mutation_run_v2":
            raise ValueError(f"Unsupported mutation manifest: {manifest_path}")
        mutation_id = str(payload.get("mutation_id") or manifest_path.parent.name)
        parent = int(payload.get("canonical_parent_rule_id"))
        paths = payload.get("paths") if isinstance(payload.get("paths"), dict) else {}
        rule_file = Path(str(paths.get("mutated_rule") or (manifest_path.parent / "mutated_rule.json"))).resolve()
        report = self.analysis_root / f"rule_{parent:05d}" / mutation_id / "mutation_report.json"
        run_dir = manifest_path.parent.resolve()
        if report.is_file():
            status = "ANALYZED"
        elif any(run_dir.glob("*_samples.csv")) or any(run_dir.glob("*passport*.json")):
            status = "OBSERVED"
        else:
            status = str(payload.get("status") or "prepared").upper()
        return MutationRecord(
            mutation_id=mutation_id,
            parent_rule_id=parent,
            mode=str(payload.get("mutation_mode") or "unknown"),
            parameter=(str(payload.get("mutation_parameter")) if payload.get("mutation_parameter") else None),
            preset=(str(payload.get("mutation_preset")) if payload.get("mutation_preset") else None),
            intensity=float(payload.get("mutation_intensity") or 0.0),
            seed=int(payload.get("mutation_seed") or 0),
            change_count=int(payload.get("change_count") or 0),
            created_at=str(payload.get("created_at") or "—"),
            status=status,
            run_dir=run_dir,
            rule_file=rule_file,
            manifest_file=manifest_path,
            analysis_report=(report if report.is_file() else None),
        )

    def load_records(self) -> tuple[MutationRecord, ...]:
        if not self.mutation_root.exists():
            return ()
        records: list[MutationRecord] = []
        for path in sorted(self.mutation_root.rglob("mutation_manifest.json"), reverse=True):
            if "_preview" in path.parts:
                continue
            try:
                records.append(self._record_from_manifest(path))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        records.sort(key=lambda r: (r.created_at, r.mutation_id), reverse=True)
        return tuple(records)

    def prepare_launch(self, mutation_id: str) -> PreparedConfiguration:
        records = {item.mutation_id: item for item in self.load_records()}
        record = records.get(str(mutation_id))
        if record is None:
            raise ValueError(f"Mutation manifest not found: {mutation_id}")
        manifest = _read_json(record.manifest_file)
        if manifest.get("canonical_promotion") is not False:
            raise ValueError("mutation launch refused: canonical_promotion must be false")
        if not record.rule_file.is_file():
            raise ValueError(f"mutated rule file is missing: {record.rule_file}")
        mutated = _read_json(record.rule_file)
        if int(mutated.get("rule_id", -1)) != record.parent_rule_id:
            raise ValueError("mutated rule parent identity mismatch")
        world, _source, _payload = self._world(record.parent_rule_id)
        draft = ConfigurationDraft(
            world=world,
            provenance=ProvenanceKind.CANONICAL,
            max_ticks=0,
            auto_stop=False,
            output_dir=str(record.run_dir),
        )
        run_spec = RunSpec.create(
            rule_id=record.parent_rule_id,
            mode="mutation",
            max_ticks=0,
            sample_every=draft.sample_every,
            pressure_every=draft.pressure_every,
            output_dir=str(record.run_dir),
            outputs=draft.outputs,
            field_width=draft.field_width,
            field_height=draft.field_height,
            topology=draft.topology,
            boundary_mode=draft.boundary_mode,
            seed=record.seed,
        )
        harness = _MutationCommandHarness(draft)
        run = {
            "rule_id": record.parent_rule_id,
            "mode": "mutation",
            "rule_file": record.rule_file,
            "manifest_file": record.manifest_file,
            "run_dir": record.run_dir,
            "experimental_context": None,
        }
        command = tuple(harness._base_command(run))
        payload = {
            "mutation_id": record.mutation_id,
            "manifest_sha256": _sha256(record.manifest_file),
            "mutated_rule_sha256": _sha256(record.rule_file),
            "run_spec_hash": run_spec.content_hash,
            "command": list(command),
        }
        return PreparedConfiguration(
            effective_draft=draft,
            run_spec=run_spec,
            command=command,
            command_text=" ".join(command),
            forced_controls=(),
            review_hash=canonical_hash(payload),
        )


__all__ = ["NativeMutationWorkspace"]
