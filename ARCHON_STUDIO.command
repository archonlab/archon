#!/usr/bin/env bash
set -euo pipefail

# ARCHON Studio macOS launcher.
# Platform discovery stays here; the canonical desktop lifecycle remains in
# Tools/archon_studio_desktop.py and is shared with Linux and Windows.

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

find_python3() {
  local candidate
  if [[ -n "${ARCHON_PYTHON:-}" ]]; then
    if "${ARCHON_PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)' >/dev/null 2>&1; then
      printf '%s\n' "${ARCHON_PYTHON}"
      return 0
    fi
    printf 'ARCHON_PYTHON does not point to a working Python 3 interpreter: %s\n' "${ARCHON_PYTHON}" >&2
    return 1
  fi

  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
       "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)' >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

if ! PYTHON_BIN="$(find_python3)"; then
  printf '\nARCHON Studio could not find Python 3.\n' >&2
  printf 'Install Python 3, then launch ARCHON_STUDIO.command again.\n' >&2
  printf '\nPress Return to close...\n' >&2
  read -r _ || true
  exit 127
fi

exec "$PYTHON_BIN" "$ROOT/Tools/archon_studio_desktop.py" --root "$ROOT" "$@"
