"""Filesystem boundary and legacy-compatible evolution rendering."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from Analyzer_next.core.mechanism_evolution.contracts import (
    MechanismEvolutionInputs,
    MechanismEvolutionPaths,
    MechanismEvolutionRunResult,
)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_sources(results_dir: Path) -> MechanismEvolutionInputs:
    required = {
        "mechanism_registry": results_dir / "mechanism_registry.json",
        "composition_templates": results_dir / "composition_templates.json",
        "composition_instances": results_dir / "composition_instances.json",
        "template_rule_map": results_dir / "template_rule_map.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))
    return MechanismEvolutionInputs(
        mechanism_registry=load_json(required["mechanism_registry"]),
        template_registry=load_json(required["composition_templates"]),
        instance_registry=load_json(required["composition_instances"]),
        template_rule_map=load_json(required["template_rule_map"]),
    )


def fmt_float(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.000"


def write_evolution_graph_md(evolution_graph: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Mechanism Evolution Graph v1.0")
    lines.append("")
    lines.append(f"Rules: **{evolution_graph['rule_count']}**")
    lines.append("")
    lines.append("## Template evolution layer")
    lines.append("")
    lines.append(
        f"- Nodes: **{evolution_graph['template_layer']['node_count']}**"
    )
    lines.append(
        f"- Edges: **{evolution_graph['template_layer']['edge_count']}**"
    )
    lines.append("")
    lines.append("### Top template transitions")
    lines.append("")
    lines.append("| Source | Target | Count | Rules | P | Strength |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for edge in evolution_graph["template_layer"]["top_edges"][:20]:
        lines.append(
            f"| {edge['source']} | {edge['target']} | {edge['count']} | {edge['rule_count']} | "
            f"{fmt_float(edge['probability_from_source'])} | {fmt_float(edge['transition_strength'])} |"
        )
    lines.append("")
    lines.append("### Top template nodes")
    lines.append("")
    lines.append(
        "| Node | Count | In | Out | In degree | Out degree | Centrality |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for node in evolution_graph["template_layer"]["top_nodes"][:20]:
        lines.append(
            f"| {node['node']} | {node['count']} | {node['incoming_count']} | {node['outgoing_count']} | "
            f"{node['in_degree']} | {node['out_degree']} | {fmt_float(node['centrality_score'])} |"
        )
    lines.append("")
    lines.append("## Atomic evolution layer")
    lines.append("")
    lines.append(
        f"- Nodes: **{evolution_graph['atomic_layer']['node_count']}**"
    )
    lines.append(
        f"- Edges: **{evolution_graph['atomic_layer']['edge_count']}**"
    )
    lines.append("")
    lines.append("### Top atomic transitions")
    lines.append("")
    lines.append("| Source | Target | Count | Rules | P | Strength |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for edge in evolution_graph["atomic_layer"]["top_edges"][:20]:
        lines.append(
            f"| {edge['source']} | {edge['target']} | {edge['count']} | {edge['rule_count']} | "
            f"{fmt_float(edge['probability_from_source'])} | {fmt_float(edge['transition_strength'])} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_evolution_report_md(report: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Mechanism Evolution Report v1.0")
    lines.append("")
    lines.append(f"Rules: **{report['rule_count']}**")
    lines.append("")
    lines.append("## Evolution archetypes")
    lines.append("")
    lines.append("| Archetype | Rules |")
    lines.append("|---|---:|")
    for archetype, count in sorted(
        report["global"]["template_evolution_archetype_counts"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {archetype} | {count} |")
    lines.append("")
    lines.append("## Strongest template motifs")
    lines.append("")
    lines.append("| Motif | Count | Rules | Confidence | Cycle |")
    lines.append("|---|---:|---:|---:|---|")
    for motif in report["template_layer_summary"]["strongest_motifs"][:12]:
        lines.append(
            f"| {motif['motif_text']} | {motif['count']} | {motif['rule_count']} | "
            f"{fmt_float(motif['confidence'])} | {'yes' if motif['is_cycle'] else 'no'} |"
        )
    lines.append("")
    lines.append("## Strongest atomic motifs")
    lines.append("")
    lines.append("| Motif | Count | Rules | Confidence | Cycle |")
    lines.append("|---|---:|---:|---:|---|")
    for motif in report["atomic_layer_summary"]["strongest_motifs"][:12]:
        lines.append(
            f"| {motif['motif_text']} | {motif['count']} | {motif['rule_count']} | "
            f"{fmt_float(motif['confidence'])} | {'yes' if motif['is_cycle'] else 'no'} |"
        )
    lines.append("")
    lines.append("## Rule evolution paths")
    lines.append("")
    lines.append("| Rule | Template archetype | Template path | Atomic path |")
    lines.append("|---:|---|---|---|")
    for rule_id, record in sorted(report["rule_summaries"].items()):
        lines.append(
            f"| {rule_id} | {record['template_evolution_archetype']} | {record['template_path_text']} | {record['atomic_path_text']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_rule_paths_md(evolution_graph: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Rule Evolution Paths v1.0")
    lines.append("")
    lines.append(
        "| Rule | Template path length | Atomic path length | Template cycle | Atomic cycle | Template path |"
    )
    lines.append("|---:|---:|---:|---|---|---|")
    for rule_id, record in sorted(evolution_graph["rule_paths"].items()):
        lines.append(
            f"| {rule_id} | {record['template_path_length']} | {record['atomic_path_length']} | "
            f"{'yes' if record['template_cycle_detected'] else 'no'} | "
            f"{'yes' if record['atomic_cycle_detected'] else 'no'} | {record['template_path_text']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    result: MechanismEvolutionRunResult,
    results_dir: Path,
) -> None:
    evolution_graph = result.evolution_graph
    (results_dir / "mechanism_evolution_graph.json").write_text(
        json.dumps(evolution_graph, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_evolution_graph_md(
        evolution_graph, results_dir / "mechanism_evolution_graph.md"
    )
    (results_dir / "mechanism_evolution_report.json").write_text(
        json.dumps(result.report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_evolution_report_md(
        result.report, results_dir / "mechanism_evolution_report.md"
    )
    rule_paths = {
        "schema": "universe_search_rule_evolution_paths_v10",
        "results_dir": str(results_dir),
        "rule_count": evolution_graph["rule_count"],
        "rule_paths": evolution_graph["rule_paths"],
    }
    (results_dir / "rule_evolution_paths.json").write_text(
        json.dumps(rule_paths, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_rule_paths_md(evolution_graph, results_dir / "rule_evolution_paths.md")


class FileMechanismEvolutionRepository:
    def load(
        self,
        paths: MechanismEvolutionPaths,
    ) -> MechanismEvolutionInputs:
        return load_sources(paths.results_root)

    def save(
        self,
        paths: MechanismEvolutionPaths,
        result: MechanismEvolutionRunResult,
    ) -> None:
        write_outputs(result, paths.results_root)
