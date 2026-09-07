"""Filesystem boundary and legacy-compatible rendering for the registry."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from Analyzer_next.core.causal_registry.contracts import (
    CausalRegistryInputs,
    CausalRegistryPaths,
    CausalRegistryRunResult,
)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_sources(results_dir: Path) -> Dict[str, Any]:
    sources: Dict[str, Any] = {}
    for key, filename in (
        ("mechanisms", "causal_mechanisms.json"),
        ("motifs", "causal_motifs.json"),
        ("graph", "causal_graph.json"),
    ):
        path = results_dir / filename
        if path.exists():
            sources[key] = load_json(path)
    if not sources:
        raise FileNotFoundError(
            "Cannot find causal_mechanisms.json, causal_motifs.json, or "
            f"causal_graph.json in {results_dir}"
        )
    return sources


def fmt_float(x: Any, digits: int = 3) -> str:
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return "0.000"


def write_atomic_registry_md(registry: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Atomic Mechanism Registry v1.1")
    lines.append("")
    lines.append(f"Atomic mechanisms: **{registry['mechanism_count']}**")
    lines.append("")
    lines.append("| ID | Label | Family transition | Category | Rules | Count | Variants | Confidence |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|")
    mechanisms = sorted(
        registry["mechanisms"].values(),
        key=lambda m: (m["scores"]["registry_confidence"], m["support"]["rule_count"], m["support"]["count"]),
        reverse=True,
    )
    for m in mechanisms:
        lines.append(
            f"| {m['mechanism_id']} | {m['label']} | {m['family_motif_text']} | {m['category']} | "
            f"{m['support']['rule_count']} | {m['support']['count']} | {m['support']['event_variant_count']} | "
            f"{fmt_float(m['scores']['registry_confidence'])} |"
        )
    lines.append("")
    lines.append("## Source family motifs explained by each atomic mechanism")
    lines.append("")
    for m in mechanisms:
        lines.append(f"### {m['mechanism_id']} — {m['label']}")
        lines.append("")
        lines.append(f"- Family transition: **{m['family_motif_text']}**")
        lines.append(f"- Category: **{m['category']}**")
        lines.append(f"- Rules: **{', '.join(m['support']['rules']) if m['support']['rules'] else 'none'}**")
        lines.append("")
        lines.append("| Source family motif | Count |")
        lines.append("|---|---:|")
        for sf in m["support"]["source_family_motifs"][:12]:
            lines.append(f"| {sf['family_motif_text']} | {sf['count']} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_composition_registry_md(registry: Dict[str, Any], atomic_registry: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Mechanism Composition Registry v1.1")
    lines.append("")
    lines.append(f"Compositions: **{registry['composition_count']}**")
    lines.append("")
    lines.append("| ID | Label | Family motif | Atomic decomposition | Rules | Count | Confidence |")
    lines.append("|---|---|---|---|---:|---:|---:|")
    comps = sorted(
        registry["compositions"].values(),
        key=lambda c: (c["scores"]["composition_confidence"], c["support"]["rule_count"], c["support"]["count"]),
        reverse=True,
    )
    for c in comps:
        atoms = " + ".join(atomic_registry["mechanisms"][mid]["label"] for mid in c["atomic_mechanism_ids"])
        lines.append(
            f"| {c['composition_id']} | {c['label']} | {c['family_motif_text']} | {atoms} | "
            f"{c['support']['rule_count']} | {c['support']['count']} | {fmt_float(c['scores']['composition_confidence'])} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_rule_map_md(rule_map: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Rule Mechanism Map v1.1 Atomic")
    lines.append("")
    lines.append(f"Rules: **{rule_map['rule_count']}**")
    lines.append("")
    lines.append("| Rule | Dominant atomic category | Atomic diversity | Composition diversity | Family signature | Top atomic mechanisms |")
    lines.append("|---:|---|---:|---:|---|---|")
    for rid, r in sorted(rule_map["rules"].items()):
        top = ", ".join(f"{m['label']}×{m['count']}" for m in r["atomic_mechanism_counts"][:4])
        lines.append(
            f"| {rid} | {r['dominant_atomic_category']} | {r['atomic_mechanism_diversity']} | "
            f"{r['composition_diversity']} | {r['family_signature']} | {top} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report_md(report: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Mechanism Report v1.1 Atomic")
    lines.append("")
    lines.append(f"Atomic mechanisms: **{report['atomic_mechanism_count']}**")
    lines.append(f"Compositions: **{report['composition_count']}**")
    lines.append(f"Rules: **{report['rule_count']}**")
    lines.append("")
    lines.append("## Atomic mechanism categories")
    lines.append("")
    lines.append("| Category | Atomic mechanisms |")
    lines.append("|---|---:|")
    for cat, count in sorted(report["atomic_category_counts"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {cat} | {count} |")
    lines.append("")
    lines.append("## Top atomic mechanisms")
    lines.append("")
    lines.append("| ID | Label | Family | Category | Rules | Count | Confidence |")
    lines.append("|---|---|---|---|---:|---:|---:|")
    for m in report["top_atomic_mechanisms"][:12]:
        lines.append(
            f"| {m['mechanism_id']} | {m['label']} | {m['family_motif_text']} | {m['category']} | "
            f"{m['rule_count']} | {m['count']} | {fmt_float(m['registry_confidence'])} |"
        )
    lines.append("")
    lines.append("## Top compositions")
    lines.append("")
    lines.append("| ID | Label | Family motif | Category | Rules | Count | Confidence |")
    lines.append("|---|---|---|---|---:|---:|---:|")
    for c in report["top_compositions"][:12]:
        lines.append(
            f"| {c['composition_id']} | {c['label']} | {c['family_motif_text']} | {c['category']} | "
            f"{c['rule_count']} | {c['count']} | {fmt_float(c['composition_confidence'])} |"
        )
    lines.append("")
    lines.append("## Rule summaries")
    lines.append("")
    lines.append("| Rule | Dominant atomic category | Atomic diversity | Composition diversity | Family signature |")
    lines.append("|---:|---|---:|---:|---|")
    for rid, r in sorted(report["rule_summaries"].items()):
        lines.append(
            f"| {rid} | {r['dominant_atomic_category']} | {r['atomic_mechanism_diversity']} | "
            f"{r['composition_diversity']} | {r['family_signature']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(atomic_registry, composition_registry, rule_map, report, results_dir: Path) -> None:
    # Use same primary filenames, but now they contain atomic registry.
    (results_dir / "mechanism_registry.json").write_text(json.dumps(atomic_registry, ensure_ascii=False, indent=2), encoding="utf-8")
    write_atomic_registry_md(atomic_registry, results_dir / "mechanism_registry.md")

    (results_dir / "composition_registry.json").write_text(json.dumps(composition_registry, ensure_ascii=False, indent=2), encoding="utf-8")
    write_composition_registry_md(composition_registry, atomic_registry, results_dir / "composition_registry.md")

    (results_dir / "rule_mechanism_map.json").write_text(json.dumps(rule_map, ensure_ascii=False, indent=2), encoding="utf-8")
    write_rule_map_md(rule_map, results_dir / "rule_mechanism_map.md")

    (results_dir / "causal_mechanism_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report_md(report, results_dir / "causal_mechanism_report.md")




class FileCausalRegistryRepository:
    def load(self, paths: CausalRegistryPaths) -> CausalRegistryInputs:
        return CausalRegistryInputs(sources=load_sources(paths.results_root))

    def save(
        self,
        paths: CausalRegistryPaths,
        result: CausalRegistryRunResult,
    ) -> None:
        write_outputs(
            result.atomic_registry,
            result.composition_registry,
            result.rule_map,
            result.report,
            paths.results_root,
        )

