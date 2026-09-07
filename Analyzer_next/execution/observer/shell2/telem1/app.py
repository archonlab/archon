"""OL2-TELEM1 UI extension: contextual rail plus read-only live Telemetry cards."""
from __future__ import annotations

import tkinter as tk

from Analyzer_next.execution.observer.shell2.analyze1.app import (
    ObserverLauncher2AnalyzeShell,
)
from Analyzer_next.execution.observer.shell2.metrics import (
    MetricSample,
    load_default_metric_definitions,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute
from Analyzer_next.execution.observer.shell2.view_model import MetricCardViewModel
from Analyzer_next.execution.observer.state import TelemetryState

from .controller import LiveTelemetryController, LiveTelemetryPoll
from .policy import MetricRailMode, metric_rail_mode
from .projection import (
    TelemetryProjectionError,
    metric_cards_from_frame,
    state_strip_from_frame,
)


class ObserverLauncher2TelemetryShell(ObserverLauncher2AnalyzeShell):
    """Attach read-only Telemetry without changing frozen prior milestones."""

    def __init__(
        self,
        root: tk.Tk,
        store,
        analysis_controller,
        telemetry_controller: LiveTelemetryController,
        *,
        animate: bool = False,
    ) -> None:
        self.telemetry_controller = telemetry_controller
        self.live_poll: LiveTelemetryPoll | None = None
        super().__init__(
            root,
            store,
            analysis_controller,
            animate=animate,
        )
        root.title("ARCHON Observer Launcher 2.0 — TELEM1")
        self.footer_hint.set(
            "Live telemetry is read-only and shown only in Observation"
        )
        root.after(500, self._poll_live_telemetry)

    def _metric_rail_mode(self) -> MetricRailMode:
        return metric_rail_mode(
            self.snapshot.route,
            analysis_active=self.analysis_route_active,
            compact=self._metrics_compact,
        )

    def _sync_metric_rail(self) -> None:
        if not hasattr(self, "metrics_rail"):
            return
        mode = self._metric_rail_mode()
        if mode is MetricRailMode.HIDDEN:
            self.metrics_rail.grid_remove()
            self.metrics_toggle.pack_forget()
            self.metrics_drawer.place_forget()
            self._drawer_open = False
            return
        if mode is MetricRailMode.DRAWER:
            self.metrics_rail.grid_remove()
            self.metrics_toggle.pack(side="right", padx=6, pady=8)
            return
        self.metrics_toggle.pack_forget()
        self.metrics_drawer.place_forget()
        self._drawer_open = False
        self.metrics_rail.grid(row=0, column=2, sticky="nsew")

    def _toggle_metrics_drawer(self) -> None:
        if self._metric_rail_mode() is not MetricRailMode.DRAWER:
            self._drawer_open = False
            if hasattr(self, "metrics_drawer"):
                self.metrics_drawer.place_forget()
            return
        super()._toggle_metrics_drawer()

    def _on_resize(self, event: tk.Event) -> None:
        super()._on_resize(event)
        if event.widget is self.root:
            self._sync_metric_rail()

    def _refresh_content(self) -> None:
        super()._refresh_content()
        self._sync_metric_rail()
        self._render_live_telemetry()

    def _poll_live_telemetry(self) -> None:
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        if self._metric_rail_mode() is not MetricRailMode.HIDDEN:
            self.live_poll = self.telemetry_controller.poll(self.snapshot.run.run_id)
            self._render_live_telemetry()
        self.root.after(500, self._poll_live_telemetry)

    def _blank_metric_cards(self) -> tuple[MetricCardViewModel, ...]:
        return tuple(
            MetricCardViewModel(
                metric_id=definition.metric_id,
                label=definition.label,
                value_text="—",
                delta_text="waiting for canonical sample",
                source_text=f"{definition.source} · {definition.kind}",
                secondary_text=None,
                history=(),
                chart_token=f"chart.{index % 5 + 1}",
            )
            for index, definition in enumerate(load_default_metric_definitions())
        )

    def _render_cards(self, cards: tuple[MetricCardViewModel, ...]) -> None:
        for card_set in self._metric_sets:
            for widgets, card in zip(card_set, cards):
                widgets["label"].configure(text=card.label.upper())
                widgets["value"].configure(text=card.value_text)
                widgets["delta"].configure(text=card.delta_text)
                widgets["secondary"].configure(text=card.secondary_text or "")
                widgets["source"].configure(text=card.source_text)
                self._draw_sparkline(widgets["spark"], card)

    def _render_live_telemetry(self) -> None:
        if self._metric_rail_mode() is MetricRailMode.HIDDEN:
            return
        poll = self.live_poll
        if poll is None or poll.frame is None:
            self._render_cards(self._blank_metric_cards())
            if hasattr(self, "footer_right"):
                state = poll.state.value.upper() if poll else "OFFLINE"
                self.footer_right.configure(
                    text=(f"Telemetry {state}  •  read-only SQLite"
                          + (f"  •  {poll.error}" if poll and poll.error else ""))
                )
            return
        try:
            cards = metric_cards_from_frame(poll.frame)
            strip = state_strip_from_frame(poll.frame)
        except TelemetryProjectionError as exc:
            self._render_cards(self._blank_metric_cards())
            self.footer_right.configure(
                text=f"Telemetry ERROR  •  {exc}"
            )
            return

        self._render_cards(cards)
        if hasattr(self, "state_badges"):
            for label, (key, value) in zip(self.state_badges, strip):
                label.configure(text=f"{key}: {value}")
        if hasattr(self, "tick_label") and poll.frame.latest is not None:
            self.tick_label.configure(
                text=(
                    f"Tick {poll.frame.latest.tick:,} / "
                    f"{self.snapshot.run.spec.max_ticks:,}"
                )
            )
        age = "—" if poll.age_seconds is None else f"{poll.age_seconds:.1f}s"
        state_text = poll.state.value.upper()
        suffix = f"  •  age {age}"
        if poll.error:
            suffix += f"  •  {poll.error}"
        self.footer_right.configure(
            text=f"Telemetry {state_text}  •  read-only SQLite{suffix}"
        )

    def close(self) -> None:
        self.telemetry_controller.close()
        super().close()


__all__ = ["ObserverLauncher2TelemetryShell"]
