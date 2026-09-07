"""Filesystem boundary and legacy-compatible template rendering."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from Analyzer_next.core.composition_templates.contracts import (
    CompositionTemplateInputs,
    CompositionTemplatePaths,
    CompositionTemplateRunResult,
)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_sources(results_dir: Path) -> CompositionTemplateInputs:
    mech_path = results_dir / "mechanism_registry.json"
    comp_path = results_dir / "composition_registry.json"
    rule_path = results_dir / "rule_mechanism_map.json"
    missing = [str(p) for p in (mech_path, comp_path, rule_path) if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))
    return CompositionTemplateInputs(
        mechanism_registry=load_json(mech_path),
        composition_registry=load_json(comp_path),
        rule_map=load_json(rule_path),
    )


def fmt_float(x: Any, digits: int = 3) -> str:
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return "0.000"


def write_templates_md(template_registry: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Composition Templates v1.0")
    lines.append("")
    lines.append(f"Templates: **{template_registry.get('template_count', 0)}**")
    lines.append("")
    lines.append("| ID | Template | Category | Rules | Count | Instances | Variants | Confidence |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")
    templates = sorted(
        template_registry.get("templates", {}).values(),
        key=lambda t: (
            t["scores"]["template_confidence"],
            t["support"]["rule_count"],
            t["support"]["count"],
        ),
        reverse=True,
    )
    for t in templates:
        lines.append(
            f"| {t['template_id']} | {t['template_label']} | {t['category']} | "
            f"{t['support']['rule_count']} | {t['support']['count']} | {t['support']['composition_count']} | "
            f"{t['support']['family_variant_count']} | {fmt_float(t['scores']['template_confidence'])} |"
        )
    lines.append("")
    lines.append("## Template details")
    lines.append("")
    for t in templates:
        lines.append(f"### {t['template_id']} — {t['template_label']}")
        lines.append("")
        lines.append(f"- Category: **{t['category']}**")
        lines.append(
            f"- Rules: **{', '.join(t['support']['rules']) if t['support']['rules'] else 'none'}**"
        )
        lines.append(
            f"- Atomic mechanisms: **{', '.join(t['support']['atomic_mechanism_ids'])}**"
        )
        lines.append("")
        lines.append("| Family variant | Count |")
        lines.append("|---|---:|")
        for variant in t["support"]["family_variants"][:12]:
            lines.append(
                f"| {variant['family_motif_text']} | {variant['count']} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_instances_md(instance_registry: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Composition Instances v1.0")
    lines.append("")
    lines.append(f"Instances: **{instance_registry.get('instance_count', 0)}**")
    lines.append("")
    lines.append("| Instance | Template | Composition | Family motif | Atomic labels | Rules | Count |")
    lines.append("|---|---|---|---|---|---:|---:|")
    instances = sorted(
        instance_registry.get("instances", {}).values(),
        key=lambda i: (
            i["template_label"],
            i.get("support", {}).get("rule_count", 0),
            i.get("support", {}).get("count", 0),
        ),
        reverse=True,
    )
    for instance in instances:
        lines.append(
            f"| {instance['instance_id']} | {instance['template_label']} | {instance['composition_id']} | "
            f"{instance['family_motif_text']} | {' + '.join(instance['atomic_labels'])} | "
            f"{instance.get('support', {}).get('rule_count', 0)} | {instance.get('support', {}).get('count', 0)} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_template_rule_map_md(
    template_rule_map: Dict[str, Any], path: Path
) -> None:
    lines = []
    lines.append("# Template Rule Map v1.0")
    lines.append("")
    lines.append(f"Rules: **{template_rule_map.get('rule_count', 0)}**")
    lines.append("")
    lines.append("| Rule | Dominant template category | Template diversity | Instance diversity | Atomic diversity | Family signature | Top templates |")
    lines.append("|---:|---|---:|---:|---:|---|---|")
    for rid, rule in sorted(template_rule_map.get("rules", {}).items()):
        top = ", ".join(
            f"{t['template_label']}×{t['count']}"
            for t in rule["template_counts"][:4]
        )
        lines.append(
            f"| {rid} | {rule['dominant_template_category']} | {rule['template_diversity']} | "
            f"{rule['instance_diversity']} | {rule['atomic_diversity']} | {rule['family_signature']} | {top} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report_md(report: Dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Template Report v1.0")
    lines.append("")
    lines.append(f"Templates: **{report.get('template_count', 0)}**")
    lines.append(f"Instances: **{report.get('instance_count', 0)}**")
    lines.append(f"Rules: **{report.get('rule_count', 0)}**")
    lines.append("")
    lines.append("## Template categories")
    lines.append("")
    lines.append("| Category | Templates |")
    lines.append("|---|---:|")
    for category, count in sorted(
        report.get("template_category_counts", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {category} | {count} |")
    lines.append("")
    lines.append("## Top templates")
    lines.append("")
    lines.append("| ID | Template | Category | Rules | Count | Instances | Confidence |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    for template in report.get("top_templates", [])[:12]:
        lines.append(
            f"| {template['template_id']} | {template['template_label']} | {template['category']} | "
            f"{template['rule_count']} | {template['count']} | {template['composition_count']} | {fmt_float(template['template_confidence'])} |"
        )
    lines.append("")
    lines.append("## Rule summaries")
    lines.append("")
    lines.append("| Rule | Dominant category | Template diversity | Instance diversity | Atomic diversity | Signature |")
    lines.append("|---:|---|---:|---:|---:|---|")
    for rid, rule in sorted(report.get("rule_summaries", {}).items()):
        lines.append(
            f"| {rid} | {rule['dominant_template_category']} | {rule['template_diversity']} | "
            f"{rule['instance_diversity']} | {rule['atomic_diversity']} | {rule['family_signature']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    result: CompositionTemplateRunResult,
    results_dir: Path,
) -> None:
    (results_dir / "composition_templates.json").write_text(
        json.dumps(result.template_registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_templates_md(
        result.template_registry, results_dir / "composition_templates.md"
    )
    (results_dir / "composition_instances.json").write_text(
        json.dumps(result.instance_registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_instances_md(
        result.instance_registry, results_dir / "composition_instances.md"
    )
    (results_dir / "template_rule_map.json").write_text(
        json.dumps(result.template_rule_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_template_rule_map_md(
        result.template_rule_map, results_dir / "template_rule_map.md"
    )
    (results_dir / "template_report.json").write_text(
        json.dumps(result.report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report_md(result.report, results_dir / "template_report.md")


class FileCompositionTemplateRepository:
    def load(
        self,
        paths: CompositionTemplatePaths,
    ) -> CompositionTemplateInputs:
        return load_sources(paths.results_root)

    def save(
        self,
        paths: CompositionTemplatePaths,
        result: CompositionTemplateRunResult,
    ) -> None:
        write_outputs(result, paths.results_root)
