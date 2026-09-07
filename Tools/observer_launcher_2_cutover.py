#!/usr/bin/env python3
"""Human-facing OL2-CUTOVER1 acceptance, activation, status and rollback tool."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.execution.observer.shell2.cutover1 import CutoverError, CutoverService, LauncherProfile


def status(service: CutoverService) -> int:
    record = service.read_profile(verify_ol2_acceptance=True)
    payload: dict[str, object] = {
        "profile": record.profile.value,
        "profile_path": str(service.profile_path),
        "target": str(service.target_path(record.profile)),
        "acceptance_path": str(service.acceptance_path),
        "ol2_accepted": False,
    }
    try:
        receipt = service.read_acceptance(verify_current_sources=True)
    except CutoverError as exc:
        payload["acceptance_status"] = str(exc)
    else:
        payload["ol2_accepted"] = True
        payload["acceptance_receipt_hash"] = receipt.receipt_hash
        payload["accepted_at"] = receipt.accepted_at
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARCHON Observer Launcher 2.0 guarded cutover")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")

    accept = sub.add_parser("accept", help="record explicit visual + operational acceptance and activate OL2")
    accept.add_argument("--visual", action="store_true", help="confirm the OL2 candidate was visually inspected")
    accept.add_argument("--operational", action="store_true", help="confirm a real short run completed correctly in the OL2 candidate")

    activate = sub.add_parser("set", help="set a launcher profile")
    activate.add_argument("profile", choices=tuple(item.value for item in LauncherProfile))

    rollback = sub.add_parser("rollback", help="rollback without editing protected launcher files")
    rollback.add_argument("--to", choices=(LauncherProfile.MODULAR_V1.value, LauncherProfile.LEGACY.value), default=LauncherProfile.MODULAR_V1.value)

    args = parser.parse_args(argv)
    service = CutoverService(PROJECT_ROOT)
    try:
        if args.command == "status":
            return status(service)
        if args.command == "accept":
            if not args.visual or not args.operational:
                parser.error("accept requires both --visual and --operational")
            receipt = service.create_acceptance(visual_acceptance=True, operational_acceptance=True)
            record = service.set_profile(LauncherProfile.OL2)
            print("PASS: OL2 manual acceptance receipt written and production profile activated")
            print(f"Receipt: {service.acceptance_path}")
            print(f"Receipt SHA-256: {receipt.receipt_hash}")
            print(f"Profile: {record.profile.value}")
            print("Stable launch: ./OBSERVER.sh")
            print("Rollback: python3 Tools/observer_launcher_2_cutover.py rollback --to modular-v1")
            return 0
        if args.command == "set":
            record = service.set_profile(LauncherProfile(args.profile))
            print(f"PASS: launcher profile set to {record.profile.value}")
            return 0
        if args.command == "rollback":
            record = service.rollback(to=LauncherProfile(args.to))
            print(f"PASS: launcher rolled back to {record.profile.value}; protected launchers were not edited")
            return 0
    except CutoverError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
