"""Immutable Telemetry read models and the storage-independent query port."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Protocol, Sequence


class TelemetryQueryError(RuntimeError):
    """Raised when a Telemetry query cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: str
    rule_id: int | None
    world_id: str | None
    observer_version: str | None
    status: str
    started_at_utc: str | None
    finished_at_utc: str | None
    final_tick: int | None
    samples_count: int
    events_count: int
    chronicle_count: int
    pressure_count: int
    source_path: str | None
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ChannelSummary:
    run_id: str
    channel: str
    row_count: int
    first_tick: int | None
    last_tick: int | None


@dataclass(frozen=True, slots=True)
class ScientificRunContext:
    """Scientific provenance used to route one run into an evidence channel."""

    run_id: str
    status: str
    experiment_id: str | None
    condition_id: str | None
    role: str | None
    is_experimental: bool
    is_mutation: bool
    observational_eligible: bool
    exclusion_reason: str | None


class TelemetryReadRepository(Protocol):
    """Read-only port consumed by Analyzer core and production services."""

    def list_runs(
        self,
        *,
        rule_id: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> list[RunSummary]: ...

    def get_run(self, run_id: str) -> RunSummary: ...

    def get_scientific_run_context(
        self,
        run_id: str,
    ) -> ScientificRunContext: ...

    def latest_run(
        self,
        *,
        rule_id: int | None = None,
        status: str | None = None,
    ) -> RunSummary | None: ...

    def channel_summary(
        self,
        run_id: str,
        channel: str,
    ) -> ChannelSummary: ...

    def all_channel_summaries(
        self,
        run_id: str,
    ) -> dict[str, ChannelSummary]: ...

    def read_channel(
        self,
        run_id: str,
        channel: str,
        *,
        tick_from: int | None = None,
        tick_to: int | None = None,
        limit: int | None = None,
        newest_first: bool = False,
        payload_only: bool = True,
    ) -> list[dict[str, Any]]: ...

    def iter_channel(
        self,
        run_id: str,
        channel: str,
        *,
        tick_from: int | None = None,
        tick_to: int | None = None,
        limit: int | None = None,
        newest_first: bool = False,
        payload_only: bool = True,
        fetch_size: int = 1000,
    ) -> Iterator[dict[str, Any]]: ...

    def nearest_sample(
        self,
        run_id: str,
        tick: int,
    ) -> dict[str, Any] | None: ...

    def ticks(
        self,
        run_id: str,
        channel: str = "sample",
    ) -> list[int]: ...

    def count(
        self,
        run_id: str,
        channel: str,
        *,
        tick_from: int | None = None,
        tick_to: int | None = None,
    ) -> int: ...
