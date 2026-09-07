"""PERF1 launcher-local acceleration for the MUTATIONS1 workspace.

The scientific mutation engine remains authoritative.  This adapter only caches
read-side discovery and the exact baseline provenance result while the files
that define that result are unchanged.
"""
from __future__ import annotations

from pathlib import Path
import csv
import json
import os
from typing import Any

from Observer.observer_mutation_engine import (
    PRESETS,
    create_mutation_run,
    diff_payload,
    stable_payload_hash,
)

from Analyzer_next.adapters.observer.mutation_workspace import NativeMutationWorkspace
from Analyzer_next.execution.observer.shell2.mutations1.model import (
    MutationDraft,
    MutationPreview,
    MutationRecord,
    MutationStrategy,
)


class CachedMutationWorkspace(NativeMutationWorkspace):
    """Avoid repeated manifest/baseline scans during one Launcher session."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._records_cache: tuple[MutationRecord, ...] | None = None
        self._records_signature: tuple[Any, ...] | None = None
        self._baseline_cache: dict[int, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        # During an explicit launch of a record already selected from the in-memory
        # execution snapshot, discovery must not rescan the entire mutation tree.
        # Base prepare_launch() still re-reads and validates that record's manifest,
        # mutated rule, parent identity and hashes before returning a command.
        self._launch_record_cache_bypass = False

    @staticmethod
    def _fingerprint(path: Path) -> tuple[str, int, int]:
        try:
            stat = path.stat()
        except OSError:
            return (str(path), -1, -1)
        return (str(path), int(stat.st_mtime_ns), int(stat.st_size))

    @staticmethod
    def _dir_children(path: Path, *, prefix: str | None = None) -> tuple[tuple[str, int], ...]:
        rows: list[tuple[str, int]] = []
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        if prefix is not None and not entry.name.startswith(prefix):
                            continue
                        rows.append((entry.name, int(entry.stat(follow_symlinks=False).st_mtime_ns)))
                    except OSError:
                        continue
        except OSError:
            return ()
        rows.sort()
        return tuple(rows)

    def _mutation_signature(self) -> tuple[Any, ...]:
        rules: list[tuple[str, int, tuple[tuple[str, int], ...]]] = []
        try:
            with os.scandir(self.mutation_root) as entries:
                for entry in entries:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    rules.append(
                        (
                            entry.name,
                            int(stat.st_mtime_ns),
                            self._dir_children(Path(entry.path), prefix="MUT-"),
                        )
                    )
        except OSError:
            pass
        rules.sort(key=lambda row: row[0])
        try:
            analysis_stat = self.analysis_root.stat()
            analysis_marker = (int(analysis_stat.st_mtime_ns), int(analysis_stat.st_size))
        except OSError:
            analysis_marker = (-1, -1)
        return (tuple(rules), analysis_marker)

    def invalidate_records(self) -> None:
        self._records_cache = None
        self._records_signature = None

    def load_records(self) -> tuple[MutationRecord, ...]:
        if self._launch_record_cache_bypass and self._records_cache is not None:
            return self._records_cache
        signature = self._mutation_signature()
        if self._records_cache is not None and signature == self._records_signature:
            return self._records_cache
        records = super().load_records()
        self._records_cache = records
        self._records_signature = self._mutation_signature()
        return records

    def prepare_launch(self, mutation_id: str):
        """Prepare one selected mutation without a global mutation-tree scan.

        Selection itself came from the session's execution snapshot.  Re-scanning
        every mutation directory here adds no safety for the selected artifact and
        can take many seconds on a mature ARCHON tree.  The inherited implementation
        still re-opens the selected manifest/rule and performs all per-record identity
        and hash checks.  If the requested id is not in the current cache, fall back
        to the normal discovery path.
        """
        mutation_id = str(mutation_id)
        cache = self._records_cache
        if cache is None or mutation_id not in {item.mutation_id for item in cache}:
            return super().prepare_launch(mutation_id)
        self._launch_record_cache_bypass = True
        try:
            return super().prepare_launch(mutation_id)
        finally:
            self._launch_record_cache_bypass = False

    def _baseline_files(self, rule_id: int) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
        """Return only canonical evidence files that can belong to one rule.

        The legacy Observer writes both samples and passports with the canonical
        ``rule_XXXXX_`` prefix.  Scanning every passport for every mutation
        preview is therefore unnecessary launcher-side work.
        """
        logs = self.results_root / "observation_logs"
        if not logs.is_dir():
            return (), ()
        token = f"{int(rule_id):05d}"
        samples = tuple(sorted(logs.glob(f"rule_{token}_*_samples.csv")))
        passports = tuple(sorted(logs.glob(f"rule_{token}_*_passport.json")))
        return samples, passports

    def _baseline_signature(self, rule_id: int) -> tuple[Any, ...]:
        samples, passports = self._baseline_files(rule_id)
        return (
            tuple(self._fingerprint(path) for path in samples),
            tuple(self._fingerprint(path) for path in passports),
        )

    @staticmethod
    def _read_json_dict(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _samples_run_id(path: Path) -> str:
        suffix = "_samples.csv"
        return path.name[:-len(suffix)] if path.name.endswith(suffix) else path.stem

    def _capture_rule_baseline(self, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Launcher-local fast equivalent of legacy baseline provenance lookup.

        It preserves the legacy selection semantics while narrowing passport
        discovery to the target rule's canonical filename namespace.
        """
        token = f"{int(rule_id):05d}"
        expected_seed = payload.get("seed")
        samples_candidates, passports = self._baseline_files(rule_id)

        identities: list[dict[str, Any]] = []
        for path in passports:
            passport = self._read_json_dict(path)
            state = passport.get("observer_state") if isinstance(passport.get("observer_state"), dict) else {}
            life = passport.get("life") if isinstance(passport.get("life"), dict) else {}
            tick = state.get("tick", life.get("final_tick_observed"))
            try:
                tick = int(float(tick)) if tick is not None else None
            except (TypeError, ValueError):
                tick = None
            identities.append({
                "path": path.resolve(),
                "run_id": str(state.get("run_id") or passport.get("run_id") or "").strip(),
                "seed": passport.get("seed", state.get("seed")),
                "tick": tick,
            })

        by_run: dict[str, list[dict[str, Any]]] = {}
        for item in identities:
            by_run.setdefault(str(item["run_id"]), []).append(item)

        matches: list[dict[str, Any]] = []
        for samples in samples_candidates:
            run_id = self._samples_run_id(samples)
            matched = by_run.get(run_id, ())
            if not matched:
                continue
            try:
                sample_tick = -1
                with samples.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
                    for row in csv.DictReader(fh):
                        try:
                            sample_tick = int(float(row.get("tick", "")))
                        except (TypeError, ValueError):
                            continue
            except Exception:
                sample_tick = -1
            eligible = [
                item for item in matched
                if item["tick"] is None or sample_tick < 0 or item["tick"] <= sample_tick
            ] or list(matched)
            passport = max(
                eligible,
                key=lambda item: (
                    item["tick"] if item["tick"] is not None else -1,
                    item["path"].stat().st_mtime,
                ),
            )
            same_seed = (
                expected_seed is not None
                and passport["seed"] is not None
                and str(expected_seed) == str(passport["seed"])
            )
            matches.append({
                "samples_path": str(samples.resolve()),
                "passport_path": str(passport["path"]),
                "run_id": run_id,
                "samples_final_tick": sample_tick,
                "passport_tick": passport["tick"],
                "same_seed": same_seed,
                "modified": max(samples.stat().st_mtime, passport["path"].stat().st_mtime),
            })

        exact = [item for item in matches if item["same_seed"]]
        pool = exact or matches
        if not pool:
            return {
                "status": "unavailable",
                "reason": "no_canonical_baseline_with_resolved_passport",
                "rule_id": token,
                "expected_seed": expected_seed,
            }
        chosen = max(
            pool,
            key=lambda item: (
                int(item["same_seed"]),
                item["modified"],
                item["samples_final_tick"],
            ),
        )
        return {
            "status": "resolved",
            "method": "frozen_at_mutation_preparation",
            "rule_id": token,
            "expected_seed": expected_seed,
            **{key: value for key, value in chosen.items() if key != "modified"},
        }

    def _baseline(self, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        signature = self._baseline_signature(rule_id)
        cached = self._baseline_cache.get(int(rule_id))
        if cached is not None and cached[0] == signature:
            return dict(cached[1])
        baseline = self._capture_rule_baseline(rule_id, payload)
        # Recompute after the read so a concurrent append cannot make a stale
        # result look valid for the next operation.
        final_signature = self._baseline_signature(rule_id)
        self._baseline_cache[int(rule_id)] = (final_signature, dict(baseline))
        return baseline

    def preview(self, draft: MutationDraft) -> MutationPreview:
        if draft.source_rule_id is None:
            raise ValueError("select a canonical source rule first")
        _world, _source, payload = self._world(draft.source_rule_id)
        seed = int(draft.seed) if int(draft.seed) > 0 else 1_234_567
        mutated = self._mutated_payload(payload, draft, seed)
        changes = tuple(diff_payload(payload, mutated))
        baseline = self._baseline(draft.source_rule_id, payload)
        if baseline.get("status") == "resolved":
            detail = f"Run {baseline.get('run_id')} • final tick {baseline.get('samples_final_tick')}"
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
        baseline = self._baseline(draft.source_rule_id, payload)
        if baseline.get("status") != "resolved":
            raise ValueError(
                "No resolved canonical baseline exists for this rule. "
                "Observe and save the canonical rule before creating mutations."
            )
        import time
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
        self.invalidate_records()
        return tuple(created)


__all__ = ["CachedMutationWorkspace"]
