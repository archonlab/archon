#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARCHON alias-aware integrity audit v1.1.

Checks that active Atlas, Atlas indexes, Knowledge Base, and key Analyzer JSON
products no longer expose quarantined duplicate rule IDs as active identities.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.production.alias_canonicalization import (
    RULE_KEY_HINTS,
    canonicalize_product,
    normalize_rule_id as norm,
    read_json,
    repair_product,
)


def structured_alias_hits(
    node: Any,
    aliases: dict[str, str],
    path: str = "$",
    parent_key: str = "",
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            hits.extend(
                structured_alias_hits(
                    value,
                    aliases,
                    f"{path}.{key}",
                    str(key).lower(),
                )
            )
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            hits.extend(
                structured_alias_hits(
                    value,
                    aliases,
                    f"{path}[{idx}]",
                    parent_key,
                )
            )
    elif parent_key in RULE_KEY_HINTS:
        old = norm(node)
        if old in aliases:
            hits.append({
                "path": path,
                "duplicate_rule_id": old,
                "canonical_rule_id": aliases[old],
            })
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    ap.add_argument(
        "--world-atlas-root",
        type=Path,
        default=None,
        help="Override the active World Atlas directory.",
    )
    ap.add_argument(
        "--knowledge-root",
        type=Path,
        default=None,
        help="Override the Knowledge Atlas directory.",
    )
    ap.add_argument(
        "--analysis-root",
        type=Path,
        default=None,
        help="Override the Analyzer output directory.",
    )
    ap.add_argument(
        "--no-repair",
        action="store_true",
        help="Audit only; do not canonicalize derived JSON products first.",
    )
    args = ap.parse_args()

    root = args.project_root.resolve()
    atlas = (
        args.world_atlas_root.resolve()
        if args.world_atlas_root
        else root / "Atlas" / "Worlds"
    )
    knowledge = (
        args.knowledge_root.resolve()
        if args.knowledge_root
        else root / "Atlas" / "Knowledge"
    )
    analysis = (
        args.analysis_root.resolve()
        if args.analysis_root
        else root / "Results" / "Analysis"
    )

    alias_payload = read_json(knowledge / "duplicate_rule_aliases.json", {})
    raw_aliases = alias_payload.get("aliases", {}) if isinstance(alias_payload, dict) else {}
    aliases = {
        norm(old): norm(new)
        for old, new in raw_aliases.items()
        if norm(old) and norm(new)
    }

    active_rule_ids: set[str] = set()
    active_hashes: set[str] = set()
    duplicate_active_folders: list[str] = []
    for rule_file in atlas.rglob("rule.json"):
        payload = read_json(rule_file, {})
        rid = norm(payload.get("rule_id")) if isinstance(payload, dict) else None
        if rid:
            if rid in active_rule_ids:
                duplicate_active_folders.append(str(rule_file.parent))
            active_rule_ids.add(rid)

    index = read_json(atlas / "atlas_index.json", [])
    index_rows = index if isinstance(index, list) else []
    index_ids = {norm(row.get("rule_id")) for row in index_rows if isinstance(row, dict)}
    index_ids.discard(None)

    products = [
        knowledge / "knowledge_base.json",
        knowledge / "research_atlas.json",
        knowledge / "consensus_database.json",
        analysis / "general_principles.json",
        analysis / "predictions.json",
        analysis / "validation_report.json",
        analysis / "cohort_report.json",
        analysis / "cohort_targets.json",
        analysis / "experiment_plan.json",
        analysis / "research_director_report.json",
        analysis / "next_research_actions.json",
    ]

    repaired_products: list[dict[str, Any]] = []
    if not args.no_repair:
        for product in products:
            if not product.exists():
                continue
            change_count = repair_product(product, aliases)
            if change_count:
                repaired_products.append({
                    "file": str(product),
                    "change_count": change_count,
                })

    product_hits: list[dict[str, Any]] = []
    for product in products:
        if not product.exists():
            continue
        payload = read_json(product, None)
        if payload is None:
            continue
        hits = structured_alias_hits(payload, aliases)
        if hits:
            product_hits.append({
                "file": str(product),
                "hit_count": len(hits),
                "hits": hits[:200],
            })

    missing_from_index = sorted(active_rule_ids - index_ids)
    extra_in_index = sorted(index_ids - active_rule_ids)
    aliases_still_active = sorted(set(aliases) & active_rule_ids)

    kb = read_json(knowledge / "knowledge_base.json", {})
    kb_rules = set(kb.get("rules", {})) if isinstance(kb, dict) else set()
    kb_rules = {norm(x) for x in kb_rules if norm(x)}
    kb_missing = sorted(active_rule_ids - kb_rules)
    kb_extra = sorted(kb_rules - active_rule_ids)

    # Knowledge Base is evidence-backed and intentionally contains only
    # observed/analyzed rules. Therefore KB ⊆ Atlas is required, not KB == Atlas.
    ok = not any([
        duplicate_active_folders,
        missing_from_index,
        extra_in_index,
        aliases_still_active,
        product_hits,
        kb_extra,
    ])

    report = {
        "schema": "archon_alias_integrity_audit_v1_1",
        "ok": ok,
        "active_rules": len(active_rule_ids),
        "atlas_index_rules": len(index_ids),
        "knowledge_base_rules": len(kb_rules),
        "alias_count": len(aliases),
        "duplicate_active_folders": duplicate_active_folders,
        "missing_from_index": missing_from_index,
        "extra_in_index": extra_in_index,
        "aliases_still_active": aliases_still_active,
        "knowledge_base_coverage_gap_count": len(kb_missing),
        "knowledge_base_unanalyzed_rules": kb_missing,
        "knowledge_base_missing_rules": kb_missing,
        "repaired_products": repaired_products,
        "knowledge_base_extra_rules": kb_extra,
        "products_with_alias_hits": product_hits,
    }

    out = analysis / "Integrity" / "alias_integrity_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out)

    print("=" * 72)
    print("ARCHON Alias Integrity Audit")
    print("=" * 72)
    print(f"Active Atlas rules:     {len(active_rule_ids)}")
    print(f"Atlas index rules:      {len(index_ids)}")
    print(f"Knowledge Base rules:   {len(kb_rules)}")
    print(f"Aliases:                {len(aliases)}")
    print(f"Products repaired:      {len(repaired_products)}")
    print(f"Rewritten references:  {sum(x['change_count'] for x in repaired_products)}")
    print(f"Alias hits in products: {sum(x['hit_count'] for x in product_hits)}")
    print(f"Integrity:              {'OK' if ok else 'FAILED'}")
    print(f"Report:                 {out}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
