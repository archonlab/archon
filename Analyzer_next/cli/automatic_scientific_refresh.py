#!/usr/bin/env python3
"""Execute one durable BRIDGE5.7 automatic scientific refresh request."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Tools.archon_platform import pid_alive

from Analyzer_next.production.automatic_refresh import (
    AutomaticRefreshPaths,
    run_automatic_scientific_refresh,
    validate_automatic_refresh_request,
)
from Analyzer_next.production.receipt_renderer import canonical_hash


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--results-directory", type=Path, required=True)
    parser.add_argument("--analysis-root", type=Path, required=True)
    parser.add_argument("--analyzer-entrypoint", type=Path, required=True)
    parser.add_argument("--telemetry-database", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    return parser


def _pid_is_alive(pid: int) -> bool:
    return pid_alive(pid)


def _acquire_refresh_lock(
    analysis_root: Path,
    request: dict,
) -> tuple[Path, bool]:
    lock_id = f"AUTOLOCK-{canonical_hash(request)[:32].upper()}"
    lock_root = analysis_root / "Experiments/AutomaticScientificRefreshLocks"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / f"{lock_id}.lock"
    payload = json.dumps(
        {
            "refresh_id": request.get("refresh_id"),
            "request_hash": request.get("request_hash"),
            "pid": os.getpid(),
        },
        sort_keys=True,
    ).encode("utf-8")
    for _attempt in range(2):
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            try:
                owner = json.loads(lock_path.read_text(encoding="utf-8"))
                owner_pid = int(owner.get("pid") or 0)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return lock_path, False
            if _pid_is_alive(owner_pid):
                return lock_path, False
            try:
                lock_path.unlink()
            except OSError:
                return lock_path, False
            continue
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return lock_path, True
    return lock_path, False


def _wait_for_existing_refresh(
    analysis_root: Path,
    request: dict,
    *,
    timeout_seconds: int,
) -> int:
    valid, _issues = validate_automatic_refresh_request(request)
    refresh_id = (
        str(request.get("refresh_id") or "")
        if valid
        else f"AUTO-SCI-INVALID-{canonical_hash(request)[:20].upper()}"
    )
    receipt_path = (
        analysis_root
        / "Experiments/AutomaticScientificRefreshReceipts"
        / f"{refresh_id}.json"
    )
    deadline = time.monotonic() + max(1, int(timeout_seconds))
    while time.monotonic() < deadline:
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            time.sleep(0.25)
            continue
        if (
            receipt.get("refresh_id") == refresh_id
            and receipt.get("request_hash") == request.get("request_hash")
        ):
            print(
                "[automatic scientific refresh] reused active request "
                f"status={receipt.get('status')} receipt={receipt_path}"
            )
            return 0 if receipt.get("status") == "COMPLETED" else 1
        time.sleep(0.25)
    print(
        "[automatic scientific refresh] active request did not produce a "
        "receipt before timeout",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[automatic scientific refresh] invalid request: {exc}", file=sys.stderr)
        return 2
    paths = AutomaticRefreshPaths(
        project_root=PROJECT_ROOT,
        results_directory=args.results_directory.expanduser().resolve(),
        analysis_root=args.analysis_root.expanduser().resolve(),
        analyzer_entrypoint=args.analyzer_entrypoint.expanduser().resolve(),
        telemetry_database=args.telemetry_database.expanduser().resolve(),
        python_executable=str(args.python),
    )
    lock_path, owns_lock = _acquire_refresh_lock(paths.analysis_root, request)
    if not owns_lock:
        return _wait_for_existing_refresh(
            paths.analysis_root,
            request,
            timeout_seconds=max(1, int(args.timeout_seconds)),
        )
    try:
        result = run_automatic_scientific_refresh(
            request,
            paths,
            timeout_seconds=max(1, int(args.timeout_seconds)),
        )
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
    print(
        "[automatic scientific refresh] "
        f"status={result['status']} refresh_id={result['refresh_id']} "
        f"receipt={result['receipt_path']}"
    )
    return 0 if result["status"] in {"COMPLETED", "REUSED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
