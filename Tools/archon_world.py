#!/usr/bin/env python3
"""Headless diagnostics for ARCHON portable Worlds."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from World_Portability import WorldPortabilityError, WorldPortabilityService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect, export and import local .archon-world packages")
    parser.add_argument("--root", type=Path, default=ROOT, help="ARCHON installation root")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_export = commands.add_parser("inspect-export")
    inspect_export.add_argument("rule_id")
    export = commands.add_parser("export")
    export.add_argument("rule_id")
    export.add_argument("output", type=Path)
    export_all = commands.add_parser("export-all")
    export_all.add_argument("output", type=Path)
    inspect_import = commands.add_parser("inspect-import")
    inspect_import.add_argument("package", type=Path)
    import_world = commands.add_parser("import")
    import_world.add_argument("package", type=Path)
    inspect_import_all = commands.add_parser("inspect-import-all")
    inspect_import_all.add_argument("collection", type=Path)
    import_all = commands.add_parser("import-all")
    import_all.add_argument("collection", type=Path)
    args = parser.parse_args()
    service = WorldPortabilityService(args.root)
    try:
        if args.command == "inspect-export":
            result = service.inspect_export(args.rule_id)
        elif args.command == "export":
            result = service.export_world(args.rule_id, args.output)
        elif args.command == "export-all":
            result = service.export_all_worlds(args.output)
        elif args.command == "inspect-import":
            result = service.inspect_import(args.package)
        elif args.command == "inspect-import-all":
            result = service.inspect_world_collection(args.collection)
        elif args.command == "import-all":
            result = service.import_world_collection(args.collection)
        else:
            result = service.import_world(args.package)
    except (WorldPortabilityError, OSError) as exc:
        result = {"status": "INVALID", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") not in {"INVALID", "UNSUPPORTED_VERSION"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
