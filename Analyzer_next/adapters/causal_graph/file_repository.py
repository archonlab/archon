"""Filesystem boundary for Causal Graph Builder inputs and artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from Analyzer_next.core.causal_graph.contracts import (
    CausalGraphInputs,
    CausalGraphPaths,
    CausalGraphRunResult,
)

def fmt_float(x: Any, digits: int = 3) -> str:
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return "0.000"


def write_causal_graph_md(report: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Causal Graph Stage 3")
    lines.append("")
    lines.append(f"Results folder: `{report.get('results_dir')}`")
    lines.append(f"Rules analyzed: **{report.get('rules_analyzed', 0)}**")
    lines.append("")

    gm = report["global_motifs"]

    lines.append("## Global mechanism summary")
    lines.append("")
    lines.append(f"- Event motifs: **{gm['event_motif_count']}**")
    lines.append(f"- Family motifs: **{gm['family_motif_count']}**")
    lines.append("")

    lines.append("## Strongest family mechanisms")
    lines.append("")
    lines.append("| Mechanism | Family motif | Count | Rules | Variants | Confidence |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for m in gm.get("strongest_family_motifs", [])[:20]:
        lines.append(
            f"| {m['mechanism_label']} | {m['family_motif_text']} | {m['count']} | "
            f"{m['rule_count']} | {m['event_variant_count']} | {fmt_float(m['confidence'])} |"
        )
    lines.append("")

    lines.append("## Causal family tree")
    lines.append("")
    lines.append("| Source family | Branches | Divergence |")
    lines.append("|---|---|---:|")
    for src, data in sorted(report.get("causal_tree", {}).get("family_tree", {}).items()):
        branches = "; ".join(f"{b['target']} {fmt_float(b['probability'])}" for b in data["branches"])
        lines.append(f"| {src} | {branches} | {fmt_float(data['divergence_score'])} |")
    lines.append("")

    lines.append("## Event causal tree")
    lines.append("")
    lines.append("| Source event | Branches | Divergence |")
    lines.append("|---|---|---:|")
    for src, data in sorted(report.get("causal_tree", {}).get("event_tree", {}).items()):
        branches = "; ".join(f"{b['target']} {fmt_float(b['probability'])}" for b in data["branches"])
        lines.append(f"| {src} | {branches} | {fmt_float(data['divergence_score'])} |")
    lines.append("")

    lines.append("## Rule mechanism fingerprints")
    lines.append("")
    lines.append("| Rule | Mechanism archetype | Family signature | Complexity | Collapse | Recovery | Dormancy |")
    lines.append("|---:|---|---|---:|---:|---:|---:|")
    for rid, fp in sorted(report.get("global_family_fingerprints", {}).get("rule_fingerprints", {}).items()):
        lines.append(
            f"| {rid} | {fp['mechanism_archetype']} | {fp['family_signature']} | "
            f"{fmt_float(fp['mechanism_complexity'])} | {fmt_float(fp['collapse_pressure'])} | "
            f"{fmt_float(fp['recovery_pressure'])} | {fmt_float(fp['dormancy_pressure'])} |"
        )
    lines.append("")

    lines.append("## Per-rule family motifs")
    lines.append("")
    for rid, graph in sorted(report.get("rule_graphs", {}).items()):
        fp = graph["family_fingerprint"]
        lines.append(f"### Rule {rid} — {fp['mechanism_archetype']}")
        lines.append("")
        lines.append(f"- Event signature: **{fp['event_signature']}**")
        lines.append(f"- Family signature: **{fp['family_signature']}**")
        lines.append(f"- Mechanism complexity: **{fmt_float(fp['mechanism_complexity'])}**")
        lines.append("")
        lines.append("| Mechanism | Family motif | Count | Variants | Cycle | Recovery |")
        lines.append("|---|---|---:|---:|---|---|")
        motifs = sorted(graph["motif_info"]["family_motifs"].values(), key=lambda m: (m["count"], m["length"]), reverse=True)
        for m in motifs[:18]:
            lines.append(
                f"| {m['mechanism_label']} | {m['family_motif_text']} | {m['count']} | "
                f"{m['event_variant_count']} | {'yes' if m['is_true_cycle'] else 'no'} | "
                f"{'yes' if m['has_recovery'] else 'no'} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_causal_report_md(report: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Causal Report Stage 3")
    lines.append("")
    lines.append("Stage 3 groups concrete motifs into generalized mechanism families.")
    lines.append("It still produces hypotheses, not proof, but the output is now suitable for the Analyzer narrative layer.")
    lines.append("")

    lines.append("## Main mechanism hypotheses")
    lines.append("")
    for h in report.get("mechanism_hypotheses", [])[:12]:
        lines.append(
            f"- **{h['mechanism_label']}**: {h['hypothesis']} "
            f"Confidence **{fmt_float(h['confidence'])}**, rules **{h['rule_count']}**, count **{h['count']}**."
        )
    lines.append("")

    lines.append("## Mechanism archetypes")
    lines.append("")
    lines.append("| Archetype | Rules |")
    lines.append("|---|---:|")
    for arch, count in sorted(report.get("global_family_fingerprints", {}).get("archetype_counts", {}).items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {arch} | {count} |")
    lines.append("")

    lines.append("## Rule summaries")
    lines.append("")
    lines.append("| Rule | Archetype | Family signature |")
    lines.append("|---:|---|---|")
    for rid, fp in sorted(report.get("global_family_fingerprints", {}).get("rule_fingerprints", {}).items()):
        lines.append(f"| {rid} | {fp['mechanism_archetype']} | {fp['family_signature']} |")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_mechanisms_json(report: Dict[str, Any], results_dir: Path) -> None:
    payload = {
        "schema": "universe_search_causal_mechanisms_stage3_v10",
        "results_dir": report.get("results_dir"),
        "rules_analyzed": report.get("rules_analyzed"),
        "global_motifs": report.get("global_motifs"),
        "causal_tree": report.get("causal_tree"),
        "mechanism_hypotheses": report.get("mechanism_hypotheses"),
        "rule_mechanisms": {
            rid: {
                "family_fingerprint": graph["family_fingerprint"],
                "family_motifs": graph["motif_info"]["family_motifs"],
                "compact_family_sequence": graph["compact_family_sequence"],
                "compact_family_sequence_text": graph["compact_family_sequence_text"],
            }
            for rid, graph in report.get("rule_graphs", {}).items()
        }
    }
    (results_dir / "causal_mechanisms.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_mechanisms_md(report: Dict[str, Any], results_dir: Path) -> None:
    lines = []
    lines.append("# Causal Mechanisms Stage 3")
    lines.append("")
    lines.append("## Strongest generalized mechanisms")
    lines.append("")
    lines.append("| Mechanism | Family motif | Count | Rules | Variants | Confidence |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for m in report.get("global_motifs", {}).get("strongest_family_motifs", [])[:30]:
        lines.append(
            f"| {m['mechanism_label']} | {m['family_motif_text']} | {m['count']} | "
            f"{m['rule_count']} | {m['event_variant_count']} | {fmt_float(m['confidence'])} |"
        )
    lines.append("")

    lines.append("## Mechanism hypotheses")
    lines.append("")
    for h in report.get("mechanism_hypotheses", [])[:20]:
        lines.append(f"- **{h['mechanism_label']}**: {h['hypothesis']}")
    lines.append("")

    lines.append("## Rule mechanism fingerprints")
    lines.append("")
    lines.append("| Rule | Archetype | Family signature | Recovery families | Collapse recurrence families | True cycles |")
    lines.append("|---:|---|---|---:|---:|---:|")
    for rid, fp in sorted(report.get("global_family_fingerprints", {}).get("rule_fingerprints", {}).items()):
        lines.append(
            f"| {rid} | {fp['mechanism_archetype']} | {fp['family_signature']} | "
            f"{fp['recovery_family_count']} | {fp['collapse_recurrence_family_count']} | {fp['true_cycle_family_count']} |"
        )
    lines.append("")

    (results_dir / "causal_mechanisms.md").write_text("\n".join(lines), encoding="utf-8")



def write_causal_motifs_json(report: Dict[str, Any], results_dir: Path) -> None:
    payload = {
        "schema": "universe_search_causal_motifs_stage3_v10",
        "results_dir": report.get("results_dir"),
        "rules_analyzed": report.get("rules_analyzed"),
        "global_motifs": {
            "event_motif_count": report.get("global_motifs", {}).get("event_motif_count", 0),
            "family_motif_count": report.get("global_motifs", {}).get("family_motif_count", 0),
            "event_motifs": report.get("global_motifs", {}).get("event_motifs", {}),
            "strongest_event_motifs": report.get("global_motifs", {}).get("strongest_event_motifs", []),
            "recovery_event_motifs": [
                m for m in report.get("global_motifs", {}).get("strongest_event_motifs", [])
                if m.get("has_recovery")
            ],
            "collapse_recurrence_event_motifs": [
                m for m in report.get("global_motifs", {}).get("strongest_event_motifs", [])
                if m.get("has_collapse_recurrence")
            ],
            "true_cycle_event_motifs": [
                m for m in report.get("global_motifs", {}).get("strongest_event_motifs", [])
                if m.get("is_true_cycle")
            ],
            "repetition_event_motifs": [
                m for m in report.get("global_motifs", {}).get("strongest_event_motifs", [])
                if m.get("is_repetition")
            ],
        },
        "rule_motifs": {
            rid: {
                "sequence": graph.get("sequence", []),
                "sequence_text": graph.get("sequence_text", "NONE"),
                "compact_sequence": graph.get("compact_sequence", []),
                "compact_sequence_text": graph.get("compact_sequence_text", "NONE"),
                "motifs": graph.get("motif_info", {}).get("motifs", {}),
                "compact_motifs": graph.get("motif_info", {}).get("compact_motifs", {}),
                "true_cycle_motifs": graph.get("motif_info", {}).get("true_cycle_motifs", {}),
                "repetition_motifs": graph.get("motif_info", {}).get("repetition_motifs", {}),
                "recovery_motifs": graph.get("motif_info", {}).get("recovery_motifs", {}),
                "collapse_recurrence_motifs": graph.get("motif_info", {}).get("collapse_recurrence_motifs", {}),
            }
            for rid, graph in report.get("rule_graphs", {}).items()
        }
    }
    (results_dir / "causal_motifs.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_causal_motifs_md(report: Dict[str, Any], results_dir: Path) -> None:
    lines = []
    lines.append("# Causal Motifs Stage 3")
    lines.append("")
    lines.append("This file preserves the motif layer separately from the generalized mechanism layer.")
    lines.append("Stage 3 fixes false cycles: `A -> A` is now repetition, not a true cycle.")
    lines.append("")

    gm = report.get("global_motifs", {})

    lines.append("## Strongest event motifs")
    lines.append("")
    lines.append("| Motif | Family motif | Length | Count | Rules | Confidence | True cycle | Repetition | Recovery | Collapse recurrence |")
    lines.append("|---|---|---:|---:|---:|---:|---|---|---|---|")
    for m in gm.get("strongest_event_motifs", [])[:30]:
        lines.append(
            f"| {m.get('motif_text')} | {m.get('family_motif_text')} | {m.get('length')} | "
            f"{m.get('count')} | {m.get('rule_count')} | {fmt_float(m.get('confidence'))} | "
            f"{'yes' if m.get('is_true_cycle') else 'no'} | "
            f"{'yes' if m.get('is_repetition') else 'no'} | "
            f"{'yes' if m.get('has_recovery') else 'no'} | "
            f"{'yes' if m.get('has_collapse_recurrence') else 'no'} |"
        )
    lines.append("")

    recovery = [m for m in gm.get("strongest_event_motifs", []) if m.get("has_recovery")]
    collapse = [m for m in gm.get("strongest_event_motifs", []) if m.get("has_collapse_recurrence")]
    cycles = [m for m in gm.get("strongest_event_motifs", []) if m.get("is_true_cycle")]
    repetitions = [m for m in gm.get("strongest_event_motifs", []) if m.get("is_repetition")]

    lines.append("## Recovery event motifs")
    lines.append("")
    lines.append("| Motif | Count | Rules | Confidence |")
    lines.append("|---|---:|---:|---:|")
    for m in recovery[:20]:
        lines.append(f"| {m.get('motif_text')} | {m.get('count')} | {m.get('rule_count')} | {fmt_float(m.get('confidence'))} |")
    lines.append("")

    lines.append("## Collapse recurrence event motifs")
    lines.append("")
    lines.append("| Motif | Count | Rules | Confidence |")
    lines.append("|---|---:|---:|---:|")
    for m in collapse[:20]:
        lines.append(f"| {m.get('motif_text')} | {m.get('count')} | {m.get('rule_count')} | {fmt_float(m.get('confidence'))} |")
    lines.append("")

    lines.append("## True cycle event motifs")
    lines.append("")
    lines.append("| Motif | Count | Rules | Confidence |")
    lines.append("|---|---:|---:|---:|")
    for m in cycles[:20]:
        lines.append(f"| {m.get('motif_text')} | {m.get('count')} | {m.get('rule_count')} | {fmt_float(m.get('confidence'))} |")
    lines.append("")

    lines.append("## Repetition motifs")
    lines.append("")
    lines.append("| Motif | Count | Rules | Confidence |")
    lines.append("|---|---:|---:|---:|")
    for m in repetitions[:20]:
        lines.append(f"| {m.get('motif_text')} | {m.get('count')} | {m.get('rule_count')} | {fmt_float(m.get('confidence'))} |")
    lines.append("")

    lines.append("## Per-rule motif signatures")
    lines.append("")
    lines.append("| Rule | Event signature | Motifs | True cycles | Repetitions | Recovery motifs | Collapse recurrence motifs |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|")
    for rid, graph in sorted(report.get("rule_graphs", {}).items()):
        mi = graph.get("motif_info", {})
        lines.append(
            f"| {rid} | {graph.get('compact_sequence_text', 'NONE')} | "
            f"{len(mi.get('motifs', {}))} | {len(mi.get('true_cycle_motifs', {}))} | "
            f"{len(mi.get('repetition_motifs', {}))} | {len(mi.get('recovery_motifs', {}))} | "
            f"{len(mi.get('collapse_recurrence_motifs', {}))} |"
        )
    lines.append("")

    (results_dir / "causal_motifs.md").write_text("\n".join(lines), encoding="utf-8")

def write_outputs(report: Dict[str, Any], results_dir: Path) -> None:
    (results_dir / "causal_graph.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_causal_graph_md(report, results_dir / "causal_graph.md")

    compact = {
        "schema": "universe_search_causal_report_stage3_v10",
        "results_dir": report.get("results_dir"),
        "rules_analyzed": report.get("rules_analyzed"),
        "mechanism_hypotheses": report.get("mechanism_hypotheses"),
        "global_family_fingerprints": report.get("global_family_fingerprints"),
        "strongest_family_motifs": report.get("global_motifs", {}).get("strongest_family_motifs", [])[:20],
        "causal_tree": report.get("causal_tree"),
    }
    (results_dir / "causal_report.json").write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
    write_causal_report_md(report, results_dir / "causal_report.md")
    write_causal_motifs_json(report, results_dir)
    write_causal_motifs_md(report, results_dir)
    write_mechanisms_json(report, results_dir)
    write_mechanisms_md(report, results_dir)


class FileCausalGraphRepository:
    def load(self, paths: CausalGraphPaths) -> CausalGraphInputs:
        source_path = paths.results_root / "morphological_fused_events.json"
        if not source_path.exists():
            raise FileNotFoundError(f"Missing required file: {source_path}")
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        return CausalGraphInputs(fused_events=payload)

    def save(
        self,
        paths: CausalGraphPaths,
        result: CausalGraphRunResult,
    ) -> None:
        write_outputs(result.report, paths.results_root)
