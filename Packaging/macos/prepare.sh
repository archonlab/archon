#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT="${1:-$ROOT/dist-stage/macos}"
RUNTIME_ROOT="${2:-}"
ARGS=("$ROOT/Tools/archon_distribution_stage.py" --root "$ROOT" --platform macos --output "$OUTPUT" --replace)
if [[ -n "$RUNTIME_ROOT" ]]; then ARGS+=(--runtime-root "$RUNTIME_ROOT"); fi
exec python3 "${ARGS[@]}"
