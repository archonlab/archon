#!/usr/bin/env python3
"""Targeted OL2 pre-release UX regressions for Campaigns and Queue."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Analyzer_next.adapters.observer.queue_journal import JSONQueueJournal  # noqa: E402
from Analyzer_next.execution.observer.shell2.campaigns1.controller import CampaignController  # noqa: E402
from Analyzer_next.execution.observer.shell2.config1.command_service import ObserverCommandService  # noqa: E402
from Analyzer_next.execution.observer.shell2.config1.model import (  # noqa: E402
    ConfigurationDraft,
    WorldIntegrity,
    WorldRecord,
)
from Analyzer_next.execution.observer.shell2.queue1.model import (  # noqa: E402
    QueueItem,
    QueueItemStatus,
    QueueSnapshot,
)
from Analyzer_next.execution.observer.shell2.queue1.app import ObserverLauncher2QueueShell  # noqa: E402
from Analyzer_next.execution.observer.shell2.queue1.contracts import MemoryQueueRepository  # noqa: E402
from Analyzer_next.execution.observer.shell2.queue1.controller import ObserverQueueController  # noqa: E402
from Analyzer_next.execution.observer.shell2.queue2.controller import ObserverQueue2Controller  # noqa: E402
from Analyzer_next.execution.observer.shell2.control1.model import ControlSnapshot  # noqa: E402
from Analyzer_next.execution.observer.shell2.control1.app import ObserverLauncher2ControlShell  # noqa: E402
from Analyzer_next.execution.observer.state import RunRecord, RunState  # noqa: E402


def world(rule_id: int, *, observed: bool, verified: bool = True) -> WorldRecord:
    return WorldRecord(
        rule_id=rule_id,
        world_class="Fixture",
        score=1.0,
        genome_hash=f"fixture-{rule_id}",
        observed=observed,
        mutation_runs=0,
        last_run="2026-09-07 12:00" if observed else "-",
        source_path=f"/fixture/rule_{rule_id:05d}/rule.json",
        integrity=WorldIntegrity.VERIFIED if verified else WorldIntegrity.SOURCE_MISSING,
    )


class CountingReviewPort:
    def __init__(self) -> None:
        self.calls = 0

    def review(self, draft):
        self.calls += 1
        return ObserverCommandService().review(draft)


class InactiveControl:
    process_active = False


class FiniteControl:
    """Deterministic CONTROL1 stand-in for terminal-to-next queue dispatch."""

    def __init__(self) -> None:
        self.snapshot = ControlSnapshot()
        self.starts = 0

    @property
    def process_active(self) -> bool:
        return self.snapshot.active

    def start(self, prepared, *, retry_of=None):
        self.starts += 1
        run = RunRecord(
            run_id=f"OL2-CTRL-fixture-{self.starts}",
            spec=prepared.run_spec,
            state=RunState.RUNNING,
            parent_run_id=retry_of,
            process_identity=f"pid:fixture-{self.starts}",
        )
        self.snapshot = ControlSnapshot(run=run, revision=self.starts)
        return self.snapshot

    def complete(self) -> None:
        assert self.snapshot.run is not None
        self.snapshot = replace(
            self.snapshot,
            run=replace(
                self.snapshot.run,
                state=RunState.COMPLETED,
                exit_code=0,
                revision=self.snapshot.run.revision + 1,
            ),
            revision=self.snapshot.revision + 1,
        )


class DestroyedWidget:
    def winfo_exists(self) -> int:
        return 0

    def configure(self, **_options) -> None:
        raise AssertionError("destroyed route-local widget must not be configured")


class OL2UXFixTests(unittest.TestCase):
    def test_completed_finite_run_dispatches_next_waiting_row(self) -> None:
        prepared = ObserverCommandService().review(
            ConfigurationDraft(world=world(8, observed=False), max_ticks=10)
        ).prepared
        self.assertIsNotNone(prepared)
        assert prepared is not None
        control = FiniteControl()
        repository = MemoryQueueRepository()
        controller = ObserverQueueController(control, repository=repository)
        controller.enqueue(prepared)
        controller.enqueue(prepared)

        started = controller.start()
        first_id, second_id = (item.queue_id for item in started.items)
        self.assertEqual(started.active_queue_id, first_id)
        self.assertEqual(control.starts, 1)

        control.complete()
        advanced = controller.poll()

        self.assertEqual(advanced.items[0].status, QueueItemStatus.COMPLETED)
        self.assertEqual(advanced.items[0].exit_code, 0)
        self.assertEqual(advanced.items[1].status, QueueItemStatus.RUNNING)
        self.assertEqual(advanced.active_queue_id, second_id)
        self.assertTrue(advanced.dispatching)
        self.assertEqual(control.starts, 2)
        self.assertIn(first_id, repository.terminal_records)

    def test_destroyed_queue_route_controls_are_ignored(self) -> None:
        shell = object.__new__(ObserverLauncher2QueueShell)
        shell.queue_start_button = DestroyedWidget()
        self.assertFalse(
            shell._configure_live_queue_widget("queue_start_button", state="normal")
        )
        self.assertFalse(
            shell._configure_live_queue_widget("missing_button", state="disabled")
        )

        shell.control_controller = SimpleNamespace(
            snapshot=ControlSnapshot(), process_active=False
        )
        shell.config_store = SimpleNamespace(
            config_snapshot=SimpleNamespace(review=None)
        )
        shell.control_launch_button = DestroyedWidget()
        shell.control_stop_config_button = DestroyedWidget()
        shell.pause_button = DestroyedWidget()
        shell.stop_button = DestroyedWidget()
        shell.new_run_button = DestroyedWidget()
        ObserverLauncher2ControlShell._refresh_control_buttons(shell)

    def test_select_not_observed_uses_visible_canonical_observed_flag_only(self) -> None:
        reviews = CountingReviewPort()
        controller = CampaignController(
            reviews,
            worlds=(
                world(1, observed=True),
                world(2, observed=False),
                world(3, observed=True),
                world(4, observed=False, verified=False),
            ),
        )
        controller.set_scope((1, 2, 3))
        snapshot = controller.select_not_observed_visible()
        self.assertEqual(snapshot.draft.selected_rule_ids, (2,))
        self.assertIsNone(snapshot.plan)
        self.assertEqual(reviews.calls, 0, "selection must not review, queue, or start a campaign")

    def test_select_not_observed_preserves_hidden_filtered_selection(self) -> None:
        controller = CampaignController(
            CountingReviewPort(),
            worlds=(world(1, observed=False), world(2, observed=True), world(12, observed=False)),
        )
        controller.set_scope((1, 2))
        controller.set_query("00012")
        snapshot = controller.select_not_observed_visible()
        self.assertEqual(snapshot.draft.selected_rule_ids, (1, 2, 12))

    def test_clear_completed_preserves_every_other_status_and_durable_history(self) -> None:
        prepared = ObserverCommandService().review(
            ConfigurationDraft(world=world(7, observed=False))
        ).prepared
        self.assertIsNotNone(prepared)
        assert prepared is not None
        statuses = (
            QueueItemStatus.COMPLETED,
            QueueItemStatus.RUNNING,
            QueueItemStatus.WAITING,
            QueueItemStatus.FAILED,
            QueueItemStatus.CANCELLED,
            QueueItemStatus.RECOVERY_REQUIRED,
        )
        items = tuple(
            QueueItem(queue_id=f"OL2-Q-{index:04d}", prepared=prepared, status=status)
            for index, status in enumerate(statuses, 1)
        )
        initial = QueueSnapshot(items=items, active_queue_id=items[1].queue_id, sequence=len(items))
        with tempfile.TemporaryDirectory(prefix="archon-ol2-ux-fix-") as raw:
            base = Path(raw)
            repository = JSONQueueJournal(base / "queue.json", base / "history.json")
            repository.save(initial)
            repository.record_terminal(items[0])
            repository.record_terminal(items[3])

            controller = ObserverQueue2Controller(InactiveControl(), repository=repository)
            # Startup recovery deliberately converts persisted RUNNING to
            # RECOVERY_REQUIRED. Restore an in-process mixed snapshot to test
            # this view-only action without simulating process reattachment.
            controller._snapshot = replace(initial, revision=controller.snapshot.revision)
            history_before = json.loads((base / "history.json").read_text(encoding="utf-8"))
            result = controller.clear_completed()

            self.assertEqual(
                tuple(item.status for item in result.items),
                statuses[1:],
            )
            self.assertEqual(result.active_queue_id, items[1].queue_id)
            persisted = repository.load()
            self.assertIsNotNone(persisted)
            assert persisted is not None
            self.assertEqual(tuple(item.status for item in persisted.items), statuses[1:])
            self.assertEqual(
                json.loads((base / "history.json").read_text(encoding="utf-8")),
                history_before,
                "Clear Completed must not delete or rewrite durable history",
            )


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OL2UXFixTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 2
    print("PASS: OL2 Campaigns/Queue UX and finite-run queue continuation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
