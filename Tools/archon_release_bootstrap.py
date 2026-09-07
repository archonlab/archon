#!/usr/bin/env python3
"""RELEASE1 portable OL2 production bootstrap sealing and verification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.execution.observer.shell2.cutover1 import CutoverError, CutoverService, LauncherProfile
from Analyzer_next.execution.observer.shell2.cutover1.service import RELEASE_AUTHORIZATION_RELATIVE
from Analyzer_next.release.atlas_bootstrap import ensure_atlas_layout
from Analyzer_next.release.config_bootstrap import (
    ConfigBootstrapError,
    ensure_config_layout,
)


def _status(service: CutoverService) -> int:
    payload: dict[str, object] = {
        "milestone": "RELEASE1-PRODUCTION-BOOTSTRAP",
        "authorization_path": str(service.release_authorization_path),
        "sealed": False,
    }
    try:
        authorization = service.read_release_authorization(verify_current_sources=True)
    except CutoverError as exc:
        payload["status"] = str(exc)
    else:
        payload.update(
            {
                "sealed": True,
                "launcher_profile": authorization.launcher_profile.value,
                "authorization_hash": authorization.authorization_hash,
                "parent_acceptance_receipt_hash": authorization.parent_acceptance_receipt_hash,
                "sealed_at": authorization.sealed_at,
                "fingerprint_count": len(authorization.fingerprints),
                "bootstrap_policy": "clean-install-default-ol2",
            }
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _clean_check(service: CutoverService) -> int:
    # Simulate a freshly extracted release: no Results acceptance receipt and no
    # machine-local launcher profile.  The real project tree is never modified.
    with tempfile.TemporaryDirectory(prefix="archon_release1_clean_bootstrap_") as temp:
        state = Path(temp)
        simulated = CutoverService(
            PROJECT_ROOT,
            profile_path=state / "Config/ObserverLauncher/launcher_profile.json",
            acceptance_path=state / "Results/Analysis/ObserverLauncher2/OL2_CUTOVER1_ACCEPTANCE.json",
            release_authorization_path=service.release_authorization_path,
        )
        record = simulated.read_profile(verify_ol2_acceptance=True)
        if record.profile is not LauncherProfile.OL2 or record.updated_at != "release-default":
            raise CutoverError(
                f"Clean-install bootstrap resolved {record.profile.value}/{record.updated_at}, expected ol2/release-default"
            )
        target = simulated.target_path(record.profile)
        if target != PROJECT_ROOT / "Analyzer_next/cli/observer_launcher_2.py" or not target.is_file():
            raise CutoverError(f"Clean-install OL2 target is missing or unexpected: {target}")
        # An explicit OL2 profile may also be restored after rollback without a
        # local human receipt, but only while the release authorization is valid.
        restored = simulated.set_profile(LauncherProfile.OL2)
        if restored.profile is not LauncherProfile.OL2 or restored.acceptance_receipt_hash is not None:
            raise CutoverError("Release-authorized OL2 reactivation did not preserve release-only authorization semantics")
        simulated.read_profile(verify_ol2_acceptance=True)

    print("PASS: RELEASE1 clean-install bootstrap resolves OL2 without Results, local acceptance receipt, or developer profile")
    print(f"Authorization: {RELEASE_AUTHORIZATION_RELATIVE}")
    print("Stable launch: ./OBSERVER.sh")
    return 0


def _atlas_clean_check() -> int:
    with tempfile.TemporaryDirectory(
        prefix="archon_release3_1_atlas_bootstrap_"
    ) as temp:
        simulated_root = Path(temp) / "ARCHON"
        result = ensure_atlas_layout(simulated_root)
        knowledge = simulated_root / "Atlas" / "Knowledge"
        worlds = simulated_root / "Atlas" / "Worlds"
        if not knowledge.is_dir() or not worlds.is_dir():
            raise CutoverError("Atlas bootstrap directories were not created")
        files = [
            path.relative_to(simulated_root).as_posix()
            for path in simulated_root.rglob("*")
            if path.is_file()
        ]
        if files or result.get("files_created"):
            raise CutoverError(
                "Clean Atlas bootstrap seeded scientific state: "
                + ", ".join(files)
            )

    print(
        "PASS: RELEASE3.1 Atlas clean bootstrap creates directories only; "
        "no passports, principles, predictions, consensus, histories, or "
        "machine paths are seeded"
    )
    print("Bootstrap: Atlas/Knowledge/ + Atlas/Worlds/")
    print("Schema ownership: packaged Python runtime modules")
    return 0


def _config_clean_check() -> int:
    with tempfile.TemporaryDirectory(
        prefix="archon_release3_2_config_bootstrap_"
    ) as temp:
        simulated_root = Path(temp) / "ARCHON"
        result = ensure_config_layout(simulated_root, active_profile="ol2")
        config = simulated_root / "Config" / "ObserverLauncher"
        profile = json.loads(
            (config / "launcher_profile.json").read_text(encoding="utf-8")
        )
        preferences = json.loads(
            (config / "ui_preferences.json").read_text(encoding="utf-8")
        )
        if profile.get("profile") != "ol2" or profile.get(
            "acceptance_receipt_hash"
        ) is not None:
            raise ConfigBootstrapError("Portable launcher profile is invalid")
        if preferences.get("schema") != "archon.ol2-ui-preferences.v1":
            raise ConfigBootstrapError("Portable UI preferences are invalid")
        cache = config / "cache" / "world_catalog_v1.json"
        if cache.exists() or result.get("cache_files_created"):
            raise ConfigBootstrapError(
                "World catalog cache was seeded before source validation"
            )

    print(
        "PASS: RELEASE3.2 Config first-run bootstrap creates portable launcher "
        "defaults and leaves the world catalog cache lazy"
    )
    print("Local state: launcher_profile.json + ui_preferences.json")
    print("Lazy state: cache/world_catalog_v1.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARCHON RELEASE1 portable production bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show portable release authorization status")
    sub.add_parser("seal", help="seal current human-accepted OL2 sources for clean distribution")
    sub.add_parser("clean-check", help="simulate a fresh install with no local profile or Results acceptance")
    sub.add_parser(
        "atlas-clean-check",
        help="simulate an empty first-run Atlas without scientific memory",
    )
    sub.add_parser(
        "config-clean-check",
        help="simulate portable first-run launcher configuration",
    )
    args = parser.parse_args(argv)

    if args.command == "atlas-clean-check":
        try:
            return _atlas_clean_check()
        except CutoverError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    if args.command == "config-clean-check":
        try:
            return _config_clean_check()
        except (CutoverError, ConfigBootstrapError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    service = CutoverService(PROJECT_ROOT)
    try:
        if args.command == "status":
            return _status(service)
        if args.command == "seal":
            authorization = service.create_release_authorization()
            print("PASS: RELEASE1 portable OL2 production authorization sealed")
            print(f"Authorization: {service.release_authorization_path}")
            print(f"Authorization SHA-256: {authorization.authorization_hash}")
            print(f"Parent OL2 acceptance: {authorization.parent_acceptance_receipt_hash}")
            print(f"Fingerprints: {len(authorization.fingerprints)}")
            print("Clean package policy: omit Results/ and Config/ObserverLauncher/launcher_profile.json; include Release/ARCHON_RELEASE1_PRODUCTION.json")
            return 0
        if args.command == "clean-check":
            return _clean_check(service)
    except CutoverError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
