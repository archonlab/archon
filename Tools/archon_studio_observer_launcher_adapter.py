#!/usr/bin/env python3
"""Studio-owned context adapter for the active ARCHON Observer Launcher profile.

The adapter never imports the retired ``Observer/observer_launcher.py`` surface.
It patches only the construction seam of the active OL2 shell long enough to
seed a selected canonical Rule and preview settings, then delegates startup to
``Analyzer_next/cli/observer_launcher_profile.py``.  All scientific runtime,
review, queue, save policy, and process ownership remain in Observer Launcher 2.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def normalize_rule_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("rule id is required")
    return f"{int(text):05d}"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rule-id", required=True)
    p.add_argument("--max-ticks", type=int, required=True)
    p.add_argument("--speed", type=int, required=True)
    p.add_argument("--sample-every", type=int, required=True)
    p.add_argument("--autosave-every", type=int, required=True)
    p.add_argument("--field-width", type=int, default=96)
    p.add_argument("--field-height", type=int, default=64)
    p.add_argument(
        "--verify-context-and-exit",
        action="store_true",
        help="Apply the context to OL2, print it, and close without entering the Tk loop.",
    )
    return p


def _apply_context(app: Any, args: argparse.Namespace) -> dict[str, object]:
    from Analyzer_next.execution.observer.shell2.store import ShellRoute

    rule_id = normalize_rule_id(args.rule_id)
    numeric_rule = int(rule_id)
    worlds = tuple(app.config_store.config_snapshot.worlds)
    if not any(int(world.rule_id) == numeric_rule for world in worlds):
        raise ValueError(f"Rule {rule_id} is not present in the active Observer Launcher catalog")

    # Use the same CONFIG1 workflow the native Launcher itself uses.  We do not
    # create a review or start a process.  The native UI remains authoritative.
    app.config_store.workflow.select_world(numeric_rule)
    app.config_store.update_configuration(
        max_ticks=int(args.max_ticks),
        speed=int(args.speed),
        sample_every=int(args.sample_every),
        autosave_every=int(args.autosave_every),
        field_width=int(args.field_width),
        field_height=int(args.field_height),
    )
    app.store.select_route(ShellRoute.RUNS)
    try:
        app.footer_hint.set(
            f"ARCHON Studio preview context loaded • Rule {rule_id} • Validate & Review before native launch"
        )
    except Exception:
        pass

    cfg = app.config_store.config_snapshot
    draft = cfg.draft
    return {
        "rule_id": rule_id,
        "selected_rule": None if draft.world is None else f"{int(draft.world.rule_id):05d}",
        "max_ticks": int(draft.max_ticks),
        "speed": int(draft.speed),
        "sample_every": int(draft.sample_every),
        "autosave_every": int(draft.autosave_every),
        "field_width": int(draft.field_width),
        "field_height": int(draft.field_height),
        "route": str(getattr(app.snapshot.route, "value", app.snapshot.route)),
        "review_created": cfg.review is not None,
        "semantics": "ol2-config-prefill-fresh-native-review",
    }


def main() -> int:
    args = parser().parse_args()
    if args.max_ticks < 1 or args.speed < 1 or args.sample_every < 1 or args.autosave_every < 0:
        raise SystemExit("invalid Observer handoff settings")

    # Patch the final OL2 composition class before observer_launcher_2 imports
    # it inside _build_and_run().  The patch is process-local and restored even
    # if launcher startup fails.
    from Analyzer_next.execution.observer.shell2.scientific_refresh1 import app as shell_module
    from Analyzer_next.cli import observer_launcher_profile

    shell_cls = shell_module.ObserverLauncher2ScientificRefreshShell
    original_init = shell_cls.__init__
    applied: dict[str, object] = {}

    def studio_init(self, *init_args, **init_kwargs):
        original_init(self, *init_args, **init_kwargs)
        try:
            applied.update(_apply_context(self, args))
        except Exception as exc:
            try:
                self.footer_hint.set(f"ARCHON Studio context handoff failed closed: {exc}")
            except Exception:
                pass
            raise
        if args.verify_context_and_exit:
            try:
                self.root.after(1, self.close)
            except Exception:
                try:
                    self.root.after(1, self.root.destroy)
                except Exception:
                    pass

    shell_cls.__init__ = studio_init
    try:
        result = observer_launcher_profile.main([])
    finally:
        shell_cls.__init__ = original_init

    if args.verify_context_and_exit:
        print("ARCHON_STUDIO_OBSERVER_LAUNCHER_CONTEXT=" + json.dumps(applied, sort_keys=True))
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())
