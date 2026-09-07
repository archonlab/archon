#!/usr/bin/env python3
"""ARCHON Studio STUDIO20.5 desktop launcher.

The desktop launcher owns the Studio runtime lifecycle.  It serves the sealed
production frontend from the in-process Python runtime, opens a dedicated app
window when a Chromium-family browser is available, and shuts down the runtime
(and any Studio-owned engine processes) when that window closes.

A browser fallback is retained for systems without an app-mode browser.  In
that fallback a tiny native Tk control window owns the lifecycle so the local
runtime is never left orphaned merely because a browser tab was closed.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Iterable
from urllib.request import urlopen
import webbrowser

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import archon_studio_bundle as bundle  # noqa: E402
import archon_studio_runtime as runtime  # noqa: E402
from archon_runtime_python import runtime_python_command  # noqa: E402

STUDIO_VERSION = "STUDIO20.5"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
APP_TITLE = "ARCHON Studio"


def _http_health(url: str, timeout: float = 0.35) -> dict | None:
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _prepare_snapshot(root: Path, *, quiet: bool = False) -> None:
    command = [*runtime_python_command(root), str(root / "Tools/archon_studio_snapshot.py"), "--root", str(root)]
    result = subprocess.run(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE if quiet else None,
        stderr=subprocess.STDOUT if quiet else None,
    )
    if result.returncode != 0:
        detail = (result.stdout or "").strip() if quiet else "snapshot builder failed"
        raise RuntimeError(detail or "snapshot builder failed")


def _verify_bundle(root: Path) -> dict:
    try:
        return bundle.inspect_bundle(root)
    except Exception as exc:
        raise RuntimeError(
            "ARCHON Studio production frontend is missing or stale. "
            "Run ./STUDIO_BUILD_PRODUCTION.sh first. " + str(exc)
        ) from exc


class RuntimeSession:
    """Own an in-process Studio runtime server and its scientific child engines."""

    def __init__(self, root: Path, host: str, port: int, static_root: Path) -> None:
        self.root = root.resolve()
        self.host = host
        self.requested_port = int(port)
        self.static_root = static_root.resolve()
        self.bridge: runtime.StudioRuntimeBridge | None = None
        self.server: runtime.StudioRuntimeHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.owns_runtime = False
        self.attached_existing = False
        self.port = int(port)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> None:
        if not _port_available(self.host, self.requested_port):
            payload = _http_health(f"http://{self.host}:{self.requested_port}/api/studio/health")
            bridge = payload.get("bridge") if isinstance(payload, dict) else None
            caps = set((bridge or {}).get("capabilities") or []) if isinstance(bridge, dict) else set()
            if (
                isinstance(payload, dict)
                and payload.get("schema") == "archon_studio_runtime_v1"
                and isinstance(bridge, dict)
                and bridge.get("version") == STUDIO_VERSION
                and "desktop_launcher_v1" in caps
                and bridge.get("root_identity") == hashlib.sha256(os.fsencode(str(self.root))).hexdigest()
            ):
                self.port = self.requested_port
                self.attached_existing = True
                return
            raise RuntimeError(
                f"Port {self.requested_port} is already in use by another process or an older ARCHON Studio runtime. "
                "Close the old Studio session and launch again."
            )

        self.bridge = runtime.StudioRuntimeBridge(self.root)
        self.server = runtime.StudioRuntimeHTTPServer(
            (self.host, self.requested_port),
            runtime.StudioRequestHandler,
            self.bridge,
            static_root=self.static_root,
        )
        self.port = int(self.server.server_address[1])
        self.bridge.start()
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.25},
            name="ARCHONStudioHTTP",
            daemon=True,
        )
        self.thread.start()
        self.owns_runtime = True

        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            payload = _http_health(f"{self.url}api/studio/health")
            if payload:
                bridge_payload = payload.get("bridge") or {}
                caps = set(bridge_payload.get("capabilities") or [])
                if (
                    payload.get("schema") == "archon_studio_runtime_v1"
                    and bridge_payload.get("version") == STUDIO_VERSION
                    and "desktop_launcher_v1" in caps
                    and bridge_payload.get("root_identity") == hashlib.sha256(os.fsencode(str(self.root))).hexdigest()
                ):
                    return
            time.sleep(0.06)
        self.close()
        raise RuntimeError("ARCHON Studio desktop runtime did not become ready")

    def close(self) -> None:
        if not self.owns_runtime:
            return
        server, bridge, thread = self.server, self.bridge, self.thread
        self.owns_runtime = False
        self.server = None
        self.bridge = None
        self.thread = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
        if bridge is not None:
            try:
                bridge.shutdown()
            except Exception:
                pass
        if server is not None:
            try:
                server.server_close()
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)


_CHROMIUM_NAMES = (
    "chromium",
    "chromium-browser",
    "google-chrome-stable",
    "google-chrome",
    "microsoft-edge-stable",
    "microsoft-edge",
    "brave-browser",
    "brave",
)


def chromium_candidates() -> Iterable[Path]:
    seen: set[str] = set()
    for name in _CHROMIUM_NAMES:
        raw = shutil.which(name)
        if raw and raw not in seen:
            seen.add(raw)
            yield Path(raw)

    if os.name == "nt":
        bases = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
        rels = [
            "Microsoft/Edge/Application/msedge.exe",
            "Google/Chrome/Application/chrome.exe",
            "BraveSoftware/Brave-Browser/Application/brave.exe",
        ]
        for base in filter(None, bases):
            for rel in rels:
                path = Path(str(base)) / rel
                key = str(path)
                if path.is_file() and key not in seen:
                    seen.add(key); yield path

    if sys.platform == "darwin":
        apps = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
        for path in apps:
            key = str(path)
            if path.is_file() and key not in seen:
                seen.add(key); yield path


def chromium_app_command(executable: Path, url: str, profile: Path) -> list[str]:
    command = [
        str(executable),
        f"--app={url}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
    ]
    if sys.platform.startswith("linux"):
        command.append("--class=ARCHONStudio")
    return command


def _run_chromium_window(url: str, runtime_dir: Path, *, executable: Path | None = None) -> bool:
    browser = executable or next(iter(chromium_candidates()), None)
    if browser is None:
        return False
    runtime_dir.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix="desktop-profile-", dir=runtime_dir))
    try:
        process = subprocess.Popen(chromium_app_command(browser, url, profile))
        # A dedicated user-data-dir prevents normal Chromium instance handoff,
        # so this process owns the app window and exits when the user closes it.
        return process.wait() == 0
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _open_default_browser(url: str) -> None:
    try:
        if webbrowser.open(url, new=1, autoraise=True):
            return
    except Exception:
        pass
    for command in ("xdg-open", "open"):
        executable = shutil.which(command)
        if executable:
            subprocess.Popen([executable, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    raise RuntimeError("No supported browser opener is available")


def _browser_fallback_control(url: str) -> None:
    _open_default_browser(url)
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        # Headless/minimal systems still retain a usable terminal lifecycle.
        print(f"ARCHON Studio opened at {url}")
        print("Press Ctrl+C to stop the Studio runtime.")
        while True:
            time.sleep(3600)

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("430x180")
    root.minsize(390, 165)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="ARCHON Studio", font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Studio is running in your web browser. This small launcher owns the local runtime lifecycle.",
        wraplength=390,
    ).pack(anchor="w", pady=(8, 14))
    actions = ttk.Frame(frame); actions.pack(anchor="w")
    ttk.Button(actions, text="Open Studio", command=lambda: _open_default_browser(url)).pack(side="left")
    ttk.Button(actions, text="Quit Studio", command=root.destroy).pack(side="left", padx=(8, 0))
    root.mainloop()


def _run_self_test(root: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="archon-studio15-desktop-") as raw:
        static = Path(raw)
        (static / "index.html").write_text('<!doctype html><div id="root">STUDIO15_DESKTOP_PROBE</div>', encoding="utf-8")
        session = RuntimeSession(root, "127.0.0.1", 0, static)
        # Port 0 is intentionally special for the isolated self-test: it can be
        # bound directly without consulting the fixed production port.
        session.bridge = runtime.StudioRuntimeBridge(root)
        session.server = runtime.StudioRuntimeHTTPServer(("127.0.0.1", 0), runtime.StudioRequestHandler, session.bridge, static_root=static)
        session.port = int(session.server.server_address[1])
        # Self-test intentionally does not start the source watcher: it validates
        # HTTP/window lifecycle without triggering a potentially expensive live
        # snapshot rebuild on the developer's current Atlas.
        session.thread = threading.Thread(target=session.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        session.thread.start(); session.owns_runtime = True
        try:
            deadline = time.monotonic() + 5
            health = None
            while time.monotonic() < deadline:
                health = _http_health(f"{session.url}api/studio/health")
                if health: break
                time.sleep(.05)
            assert health and health["bridge"]["version"] == STUDIO_VERSION
            assert "desktop_launcher_v1" in health["bridge"]["capabilities"]
            with urlopen(session.url, timeout=.5) as response:
                assert b"STUDIO15_DESKTOP_PROBE" in response.read()
            sample = chromium_app_command(Path("/opt/chromium"), session.url, Path("/tmp/archon-profile"))
            assert any(item.startswith("--app=http://127.0.0.1:") for item in sample)
            assert any(item.startswith("--user-data-dir=") for item in sample)
        finally:
            session.close()
    print("PASS: STUDIO20.5 desktop launcher owns an in-process production runtime, exposes desktop_launcher_v1, builds an isolated app-window command, and shuts the runtime down cleanly")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ARCHON Studio STUDIO20.5 desktop launcher")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=None, help="Explicit port; by default use 8765 or an available port if occupied")
    parser.add_argument("--browser-mode", choices=("auto", "app", "browser"), default="auto")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--headless-smoke", action="store_true", help="Verify sealed bundle + snapshot + desktop-owned runtime without opening a window")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    if args.self_test:
        return _run_self_test(root)

    _verify_bundle(root)
    _prepare_snapshot(root, quiet=args.quiet)
    static_root = root / "archon-studio/dist"
    session = RuntimeSession(root, args.host, DEFAULT_PORT if args.port is None else args.port, static_root)

    def close_session(*_args: object) -> None:
        session.close()

    old_sigint = signal.signal(signal.SIGINT, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    old_sigterm = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt())) if hasattr(signal, "SIGTERM") else None
    try:
        try:
            session.start()
        except RuntimeError as exc:
            if args.port is not None or not str(exc).startswith(f"Port {DEFAULT_PORT} is already in use"):
                raise
            # A different project/service owns the default port. Never kill it.
            session = RuntimeSession(root, args.host, 0, static_root)
            session.start()
        print("=" * 78)
        print(f"ARCHON Studio {STUDIO_VERSION} Desktop Launcher")
        print(f"Runtime: {'ATTACHED' if session.attached_existing else 'OWNED'}")
        print(f"URL: {session.url}")
        print("=" * 78)

        if args.headless_smoke:
            payload = _http_health(f"{session.url}api/studio/health", timeout=0.8)
            if not payload or payload.get("schema") != "archon_studio_runtime_v1":
                raise RuntimeError("desktop runtime health probe failed")
            with urlopen(session.url, timeout=0.8) as response:
                if response.status != 200:
                    raise RuntimeError(f"desktop frontend probe returned HTTP {response.status}")
            print("PASS: STUDIO20.5 headless desktop launch smoke")
            return 0

        if args.browser_mode in {"auto", "app"}:
            browser = next(iter(chromium_candidates()), None)
            if browser is not None:
                print(f"Desktop window: {browser.name} app mode")
                opened = _run_chromium_window(session.url, root / "Results/Studio/runtime", executable=browser)
                if opened:
                    return 0
                if args.browser_mode == "app":
                    raise RuntimeError(f"{browser.name} could not open the ARCHON Studio app window")
                print("App-window launch failed; falling back to the system browser.")
            elif args.browser_mode == "app":
                raise RuntimeError("No Chromium-family app-mode browser is installed")

        print("Desktop window: browser fallback")
        _browser_fallback_control(session.url)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        close_session()
        signal.signal(signal.SIGINT, old_sigint)
        if old_sigterm is not None:
            signal.signal(signal.SIGTERM, old_sigterm)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ARCHON Studio desktop launcher failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
