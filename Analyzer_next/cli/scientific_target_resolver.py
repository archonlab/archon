#!/usr/bin/env python3
"""Stable resolver entrypoint with native atomic registration by default."""
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.telemetry.scientific_target_registration_routing import (  # noqa: E402
    register_identities,
)


from Analyzer_next.compatibility.legacy_analyzer import (  # noqa: E402
    scientific_target_resolver as resolver,
)
resolver.register_identities = register_identities
main = resolver.main


if __name__ == "__main__":
    raise SystemExit(main())
