#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
python3 "$ROOT/Analyzer_next/cli/analyze_results.py" "$@"
EXIT_CODE=$?
echo
echo "========================================================================"
echo "Analyzer finished with exit code: $EXIT_CODE"
if [[ -t 0 ]]; then
  read -r -p "Press Enter to close..."
fi
exit "$EXIT_CODE"
