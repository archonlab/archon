#!/usr/bin/env python3
"""CSV persistence backend for ARCHON Telemetry v1.

The writer preserves the four CSV schemas currently produced by LifeObserver:
``sample``, ``event``, ``chronicle``, and ``pressure``.  It owns file handles,
headers, flushing, and shutdown while Telemetry only routes channel payloads.

No scientific values are calculated or transformed here.  Payload keys and
column order are kept compatible with the existing Observer output.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
from typing import Any, Mapping, Sequence, TextIO


class CsvWriterError(RuntimeError):
    """Raised when a telemetry CSV channel cannot be opened or written."""


SAMPLE_FIELDS = ['tick',
 'alive',
 'life_state',
 'life_score',
 'life_confidence',
 'life_uncertainty',
 'structural_state',
 'ecology_state',
 'identity_state',
 'knowledge_state',
 'objects',
 'largest',
 'total_living_mass',
 'top10_mass',
 'mean_object_size',
 'ecosystem_health',
 'mass_delta',
 'defect_delta',
 'object_delta',
 'fragmentation_index',
 'split_rate_1000',
 'merge_rate_1000',
 'birth_rate_1000',
 'death_rate_1000',
 'growth_phase',
 'large_colonies',
 'medium_colonies',
 'small_colonies',
 'top3_mass',
 'top5_mass',
 'dominance_ratio',
 'top_sizes',
 'history_delta_objects',
 'history_delta_mass',
 'history_delta_largest',
 'mass_growth_per_tick',
 'objects_growth_per_tick',
 'largest_growth_per_tick',
 'stability_index',
 'history_window',
 'ecosystem_phase',
 'story_era',
 'story_era_age',
 'story_era_line',
 'story_era_count',
 'active_families',
 'active_colonies_tracked',
 'new_colonies_this_tick',
 'extinct_colonies_total',
 'extinct_families_total',
 'largest_family_size',
 'deepest_generation',
 'oldest_lineage_age',
 'lineage_summary',
 'dynasty_leader_id',
 'dynasty_line',
 'dynasty_age',
 'dynasty_born',
 'dynasty_living',
 'dynasty_dead',
 'dynasty_peak_living',
 'dynasty_dominance',
 'dynasty_survival',
 'dynasty_turnover',
 'dynasty_birth_rate',
 'dynasty_death_rate',
 'dynasty_max_generation',
 'dynasty_largest_colony',
 'dynasty_mass',
 'demo_born_total',
 'demo_dead_total',
 'demo_alive_tracked',
 'demo_mean_life',
 'demo_max_life',
 'demo_birth_rate_1000',
 'demo_death_rate_1000',
 'demo_turnover_1000',
 'demo_replacement',
 'demo_survival_ratio',
 'demography_line',
 'evo_stress',
 'evo_adapt',
 'evo_pressure',
 'evo_recovery',
 'evo_extinction_risk',
 'evo_phase',
 'evolution_line',
 'evo_src_frag_pct',
 'evo_src_death_pct',
 'evo_src_loss_pct',
 'evo_src_inst_pct',
 'evo_src_dom_pct',
 'evo_cause',
 'evo_source_line',
 'evo_timeline_line',
 'evo_stress_trend',
 'evo_adapt_trend',
 'evo_pressure_trend',
 'evo_risk_trend',
 'evo_timeline_len',
 'civ_stage',
 'civ_score',
 'civ_age',
 'civ_cities',
 'civ_capital_size',
 'civ_urban_mass',
 'civ_urbanization',
 'civ_trade_index',
 'civ_conflict_index',
 'civ_cohesion',
 'civ_specialization',
 'civ_tech_index',
 'civ_culture_index',
 'civ_collapse_risk',
 'civ_line',
 'civ_peak_score',
 'civ_peak_tick',
 'civ_count',
 'knowledge_score',
 'knowledge_peak_score',
 'knowledge_age',
 'knowledge_families',
 'knowledge_dominant_family',
 'knowledge_dominant_axis',
 'knowledge_exploration',
 'knowledge_cooperation',
 'knowledge_aggression',
 'knowledge_efficiency',
 'knowledge_adaptation',
 'knowledge_memory',
 'knowledge_memory_peak',
 'knowledge_memory_peak_tick',
 'knowledge_transfer',
 'knowledge_loss',
 'knowledge_discoveries',
 'knowledge_line',
 'feedback_score',
 'feedback_peak_score',
 'feedback_regime',
 'feedback_survival_bonus',
 'feedback_pressure_buffer',
 'feedback_effective_pressure',
 'feedback_effective_risk',
 'feedback_self_direction',
 'feedback_environment_impact',
 'feedback_knowledge_impact',
 'feedback_response_capacity',
 'feedback_response_opportunity',
 'feedback_observed_response',
 'feedback_legacy_score',
 'feedback_metric_version',
 'feedback_metric_independence_status',
 'feedback_line',
 'emergence_score',
 'emergence_peak_score',
 'emergence_confidence',
 'emergence_evidence_count',
 'emergence_positive_evidence',
 'emergence_negative_evidence',
 'emergence_complexity_index',
 'emergence_stability_signal',
 'emergence_line',
 'validation_quality',
 'validation_grade',
 'validation_repeatability',
 'validation_stability_confidence',
 'validation_false_positive_risk',
 'validation_false_negative_risk',
 'validation_noise_sensitivity',
 'validation_warning',
 'validation_explain',
 'validation_line',
 'morphology_compactness',
 'morphology_aspect',
 'morphology_edge_complexity',
 'morphology_bbox_fill',
 'morphology_symmetry',
 'morphology_branching',
 'morphology_filament_score',
 'morphology_lattice_score',
 'morphology_change_rate',
 'morphology_stability_ticks',
 'morphology_peak_complexity',
 'morphology_class',
 'morphology_line',
 'bbox_min_x',
 'bbox_max_x',
 'bbox_min_y',
 'bbox_max_y',
 'bbox_width',
 'bbox_height',
 'top_edge_fill',
 'right_edge_fill',
 'bottom_edge_fill',
 'left_edge_fill',
 'top_edge_run',
 'right_edge_run',
 'bottom_edge_run',
 'left_edge_run',
 'defect_cells',
 'changed',
 'age',
 'health',
 'cx',
 'cy',
 'step_drift',
 'total_drift',
 'identity_persistence',
 'legacy_score',
 'information_survival',
 'post_collapse_structure',
 'expansion_front_speed']
EVENT_FIELDS = ['tick', 'type', 'detail']
PRESSURE_FIELDS = ['tick',
 'phase',
 'stress',
 'adapt',
 'pressure',
 'recovery',
 'risk',
 'src_frag_pct',
 'src_death_pct',
 'src_loss_pct',
 'src_inst_pct',
 'src_dom_pct',
 'cause',
 'stress_trend',
 'adapt_trend',
 'pressure_trend',
 'risk_trend',
 'ecosystem_phase',
 'objects',
 'mass',
 'largest',
 'families',
 'dynasty_id',
 'dynasty_dominance',
 'demo_birth_rate_1000',
 'demo_death_rate_1000',
 'demo_replacement',
 'demo_survival_ratio']
CHRONICLE_FIELDS = ['tick', 'severity', 'event', 'family', 'colony', 'phase', 'pressure', 'risk', 'cause', 'details']


@dataclass(slots=True)
class _ChannelState:
    name: str
    path: Path | None
    fieldnames: tuple[str, ...]
    file: TextIO | None = None
    writer: csv.DictWriter | None = None
    rows_since_flush: int = 0
    rows_written: int = 0


class CsvWriter:
    """Write Telemetry channel payloads to Observer-compatible CSV files.

    Any path may be ``None`` to disable that channel.  Files are opened lazily
    on the first write, so constructing the writer does not create empty files.

    Parameters mirror the current Observer outputs.  ``flush_every`` is the
    default flush interval, while per-channel values may override it.
    """

    def __init__(
        self,
        *,
        samples_path: str | Path | None = None,
        events_path: str | Path | None = None,
        chronicle_path: str | Path | None = None,
        pressure_path: str | Path | None = None,
        flush_every: int = 100,
        sample_flush_every: int | None = None,
        event_flush_every: int | None = 1,
        chronicle_flush_every: int | None = 1,
        pressure_flush_every: int | None = 1,
        append: bool = False,
        strict: bool = True,
        encoding: str = "utf-8",
    ) -> None:
        self.flush_every = self._positive_int(flush_every, "flush_every")
        self.append = bool(append)
        self.strict = bool(strict)
        self.encoding = str(encoding)
        self._closed = False

        self._flush_intervals = {
            "sample": self._interval(sample_flush_every),
            "event": self._interval(event_flush_every),
            "chronicle": self._interval(chronicle_flush_every),
            "pressure": self._interval(pressure_flush_every),
        }
        self._channels = {
            "sample": _ChannelState(
                "sample", self._path(samples_path), tuple(SAMPLE_FIELDS)
            ),
            "event": _ChannelState(
                "event", self._path(events_path), tuple(EVENT_FIELDS)
            ),
            "chronicle": _ChannelState(
                "chronicle", self._path(chronicle_path), tuple(CHRONICLE_FIELDS)
            ),
            "pressure": _ChannelState(
                "pressure", self._path(pressure_path), tuple(PRESSURE_FIELDS)
            ),
        }

    def write_sample(self, **kwargs: Any) -> bool:
        return self._write("sample", kwargs)

    def write_event(self, **kwargs: Any) -> bool:
        return self._write("event", kwargs)

    def write_chronicle(self, **kwargs: Any) -> bool:
        return self._write("chronicle", kwargs)

    def write_pressure(self, **kwargs: Any) -> bool:
        return self._write("pressure", kwargs)

    def flush(self, channel: str | None = None) -> None:
        """Flush one channel or every open channel."""
        for state in self._selected(channel):
            if state.file is not None:
                state.file.flush()
                state.rows_since_flush = 0

    def close(self) -> None:
        """Flush and close all open files. Safe to call more than once."""
        if self._closed:
            return
        errors: list[str] = []
        for state in self._channels.values():
            if state.file is None:
                continue
            try:
                state.file.flush()
                state.file.close()
            except Exception as exc:
                errors.append(f"{state.name}: {exc!r}")
            finally:
                state.file = None
                state.writer = None
                state.rows_since_flush = 0
        self._closed = True
        if errors:
            raise CsvWriterError("Could not close CSV channels: " + "; ".join(errors))

    def stats(self) -> dict[str, dict[str, Any]]:
        """Return lightweight channel state for diagnostics."""
        return {
            name: {
                "enabled": state.path is not None,
                "path": str(state.path) if state.path is not None else None,
                "open": state.file is not None,
                "rows_written": state.rows_written,
                "rows_since_flush": state.rows_since_flush,
            }
            for name, state in self._channels.items()
        }

    def __enter__(self) -> "CsvWriter":
        if self._closed:
            raise CsvWriterError("CsvWriter is already closed")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _write(self, channel: str, payload: Mapping[str, Any]) -> bool:
        if self._closed:
            raise CsvWriterError("Cannot write after CsvWriter.close()")

        state = self._channels[channel]
        if state.path is None:
            return False

        self._ensure_open(state)
        assert state.writer is not None

        row = dict(payload)
        if self.strict:
            extra = sorted(set(row).difference(state.fieldnames))
            missing = sorted(set(state.fieldnames).difference(row))
            if extra or missing:
                parts = []
                if extra:
                    parts.append("unexpected=" + ",".join(extra))
                if missing:
                    parts.append("missing=" + ",".join(missing))
                raise CsvWriterError(
                    f"Invalid {channel} payload: " + " ".join(parts)
                )
        else:
            row = {name: row.get(name, "") for name in state.fieldnames}

        try:
            state.writer.writerow(row)
        except Exception as exc:
            raise CsvWriterError(
                f"Could not write {channel} row to {state.path}: {exc}"
            ) from exc

        state.rows_written += 1
        state.rows_since_flush += 1
        if state.rows_since_flush >= self._flush_intervals[channel]:
            assert state.file is not None
            state.file.flush()
            state.rows_since_flush = 0
        return True

    def _ensure_open(self, state: _ChannelState) -> None:
        if state.writer is not None:
            return
        assert state.path is not None
        state.path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if self.append else "w"
        existed_with_data = state.path.exists() and state.path.stat().st_size > 0
        try:
            state.file = state.path.open(
                mode,
                encoding=self.encoding,
                newline="",
            )
            state.writer = csv.DictWriter(
                state.file,
                fieldnames=state.fieldnames,
                extrasaction="raise",
            )
            if not (self.append and existed_with_data):
                state.writer.writeheader()
                state.file.flush()
        except Exception as exc:
            if state.file is not None:
                state.file.close()
            state.file = None
            state.writer = None
            raise CsvWriterError(
                f"Could not open {state.name} CSV at {state.path}: {exc}"
            ) from exc

    def _selected(self, channel: str | None) -> tuple[_ChannelState, ...]:
        if channel is None:
            return tuple(self._channels.values())
        if channel not in self._channels:
            raise CsvWriterError(f"Unknown CSV channel: {channel!r}")
        return (self._channels[channel],)

    def _interval(self, value: int | None) -> int:
        return self.flush_every if value is None else self._positive_int(
            value, "channel flush interval"
        )

    @staticmethod
    def _positive_int(value: int, name: str) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise CsvWriterError(f"{name} must be a positive integer") from exc
        if result < 1:
            raise CsvWriterError(f"{name} must be >= 1")
        return result

    @staticmethod
    def _path(value: str | Path | None) -> Path | None:
        return None if value is None else Path(value).expanduser()


__all__ = [
    "CsvWriterError",
    "CsvWriter",
    "SAMPLE_FIELDS",
    "EVENT_FIELDS",
    "CHRONICLE_FIELDS",
    "PRESSURE_FIELDS",
]
