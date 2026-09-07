"""OL2-FUNCTIONS1A: live Worlds search and safe sequential-run handoff."""
from __future__ import annotations

import tkinter as tk

from Analyzer_next.execution.observer.shell2.interact1.app import (
    ObserverLauncher2InteractShell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute

from .search import is_fresh_review_for_world, parse_world_search


class ObserverLauncher2FunctionsWorldsShell(ObserverLauncher2InteractShell):
    """Make Worlds/search operational without moving execution ownership.

    This layer deliberately owns only selection/search UX and guards the
    immutable CONFIG1 handoff.  CONTROL1 remains the sole process owner.
    """

    SEARCH_DEBOUNCE_MS = 35

    def __init__(self, *args, **kwargs) -> None:
        self._world_search_after: str | None = None
        self._world_query_trace: str | None = None
        super().__init__(*args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — FUNCTIONS1A")
        self.footer_hint.set(
            "FUNCTIONS1A live rule search • fresh validation required for each selected world"
        )

    # ------------------------------------------------------------------
    # Worlds search. CONFIG1 already owns canonical catalog/filter state;
    # this layer makes that filter live and makes numeric rule identity
    # pleasant to use without auto-selecting anything.
    # ------------------------------------------------------------------
    def _build_worlds_route(self) -> None:
        # Entering Worlds is an explicit selection workflow.  Any prior review
        # is no longer launch-authoritative until a world is explicitly chosen
        # and revalidated.  This prevents Run-1 review state leaking into Run-2.
        workflow = self.config_store.workflow
        if workflow.snapshot.review is not None:
            workflow.back_to_worlds()

        super()._build_worlds_route()

        # CONFIG1 bound Return only.  FUNCTIONS1A adds live filtering while
        # keeping Enter as a harmless immediate refresh.
        self._world_query_trace = self.world_query_var.trace_add(
            "write", self._world_query_changed
        )
        self._decorate_world_search_status()

    def _world_query_changed(self, *_args) -> None:
        if self._world_search_after is not None:
            try:
                self.root.after_cancel(self._world_search_after)
            except tk.TclError:
                pass
        self._world_search_after = self.root.after(
            self.SEARCH_DEBOUNCE_MS, self._apply_live_world_search
        )

    def _apply_live_world_search(self) -> None:
        self._world_search_after = None
        if self.snapshot.route is not ShellRoute.WORLDS:
            return
        try:
            if not self.world_tree.winfo_exists():
                return
        except (AttributeError, tk.TclError):
            return
        self._apply_world_filters()

    def _apply_world_filters(self) -> None:
        # CONFIG1 updates the pure workflow but did not repaint the tree on a
        # same-route snapshot.  Repaint explicitly here; no route rebuild and
        # no selection mutation are required.
        self.config_store.set_world_filters(
            query=self.world_query_var.get(),
            world_class=self.world_class_var.get(),
            status=self.world_status_var.get(),
            sort=self.world_sort_var.get(),
        )
        self._populate_world_table()
        self._decorate_world_search_status()

    def _populate_world_table(self) -> None:
        super()._populate_world_table()
        if not hasattr(self, "world_tree"):
            return
        try:
            if not self.world_tree.winfo_exists():
                return
        except tk.TclError:
            return
        intent = parse_world_search(self.world_query_var.get())
        exact = intent.canonical_display_id
        if exact and exact in self._world_rows:
            # Exact normalized numeric identity is ranked first, but is never
            # auto-selected.  The user must still click the canonical row.
            try:
                self.world_tree.move(exact, "", 0)
            except tk.TclError:
                pass

    def _decorate_world_search_status(self) -> None:
        if not hasattr(self, "world_count_label"):
            return
        try:
            if not self.world_count_label.winfo_exists():
                return
        except tk.TclError:
            return
        intent = parse_world_search(self.world_query_var.get())
        if not intent.normalized:
            return
        visible = len(self.config_store.config_snapshot.visible_worlds)
        exact = intent.canonical_display_id
        suffix = f" • live search: {visible} match{'es' if visible != 1 else ''}"
        if exact and exact in self._world_rows:
            suffix += f" • exact {exact}"
        current = str(self.world_count_label.cget("text") or "")
        # Avoid accumulating decorations when an immediate Return refresh and
        # the live callback happen back-to-back.
        current = current.split(" • live search:", 1)[0]
        self.world_count_label.configure(text=current + suffix)

    # ------------------------------------------------------------------
    # Sequential-run safety.  Search/selection never mutates a RunSpec.
    # Selecting a canonical world invalidates old review state and launch/
    # queue handoff fail closed unless all immutable identities agree.
    # ------------------------------------------------------------------
    def _select_world_and_configure(self) -> None:
        world = self._selected_table_world
        if world is None or not world.source_verified:
            self.footer_hint.set("A verified canonical rule source is required")
            return
        if self.control_controller.process_active:
            self.footer_hint.set(
                "World change refused while Observer is active • Stop the current run first"
            )
            return
        rule_id = int(world.rule_id)
        self.config_store.select_world(rule_id)
        cfg = self.config_store.config_snapshot
        if (
            cfg.selected_world_id != rule_id
            or cfg.draft.world is None
            or cfg.draft.world.rule_id != rule_id
            or cfg.review is not None
        ):
            self.footer_hint.set("World selection failed closed: canonical configuration identity mismatch")
            return
        self.footer_hint.set(
            f"Rule {world.display_id} selected • Validate & Review required before launch"
        )

    def _review_is_current(self) -> bool:
        cfg = self.config_store.config_snapshot
        return is_fresh_review_for_world(cfg.review, cfg.draft.world)

    def _launch_observer(self) -> None:
        if not self._review_is_current():
            self.footer_hint.set(
                "Launch refused: selected world requires a fresh Validate & Review"
            )
            if hasattr(self, "config_notebook") and hasattr(self, "review_tab"):
                try:
                    self.config_notebook.select(self.review_tab)
                except tk.TclError:
                    pass
            return
        super()._launch_observer()

    def _enqueue_review(self) -> None:
        if not self._review_is_current():
            self.footer_hint.set(
                "Queue refused: selected world requires a fresh Validate & Review"
            )
            return
        super()._enqueue_review()

    def _refresh_review_panel(self) -> None:
        super()._refresh_review_panel()
        cfg = self.config_store.config_snapshot
        review = cfg.review
        if review is None or not review.valid or review.prepared is None:
            return
        try:
            if not self.review_issues_label.winfo_exists():
                return
        except (AttributeError, tk.TclError):
            return
        if self._review_is_current():
            self.review_issues_label.configure(
                text=(
                    f"RunSpec is frozen for Rule {review.prepared.run_spec.rule_id:05d}. "
                    f"Forced controls applied: {len(review.prepared.forced_controls)}. "
                    "Launch Observer or Add to Queue when ready."
                )
            )
        else:
            self.review_issues_label.configure(
                text="Review identity is stale. Validate & Review the selected world again."
            )

    def _clear_dead_interaction_refs(self) -> None:
        # INTERACT1 widgets belong to the Observation route.  Once that route
        # is destroyed, Python attributes can still reference dead Tcl command
        # names.  A subsequent store refresh must treat those handles as absent
        # instead of configuring them and aborting the route transition.
        for name in (
            "zoom_label",
            "speed_label_widget",
            "grid_button",
            "cell_px_label",
            "speed_minus_button",
            "speed_plus_button",
        ):
            widget = getattr(self, name, None)
            if widget is None:
                continue
            try:
                alive = bool(widget.winfo_exists())
            except (tk.TclError, AttributeError):
                alive = False
            if not alive:
                setattr(self, name, None)

    def _refresh_interaction_controls(self) -> None:
        self._clear_dead_interaction_refs()
        super()._refresh_interaction_controls()

    def _refresh_control_buttons(self) -> None:
        # Route transitions such as Observation -> Worlds destroy the viewport
        # before CONTROL1/INTERACT1 refresh hooks run.  Sanitize route-local
        # handles first so the transition completes atomically.
        self._clear_dead_interaction_refs()
        super()._refresh_control_buttons()
        # CONTROL1 only checked that some review existed. FUNCTIONS1A also
        # requires the review to match the currently selected canonical world.
        current = self._review_is_current()
        active = self.control_controller.process_active
        if hasattr(self, "control_launch_button"):
            try:
                self.control_launch_button.configure(
                    state="normal" if current and not active else "disabled"
                )
            except tk.TclError:
                pass
        if hasattr(self, "queue_add_button"):
            try:
                self.queue_add_button.configure(
                    state="normal" if current and not active else "disabled"
                )
            except tk.TclError:
                pass


__all__ = ["ObserverLauncher2FunctionsWorldsShell"]
