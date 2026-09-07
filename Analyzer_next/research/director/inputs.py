"""Read-only adapters for Analyzer and Knowledge products."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from Analyzer_next.adapters.scientific_view_adapter import eligible_profiles
from Analyzer_next.research.director.common import clamp, iter_dicts, load_json, read_text, safe_num

def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def load_profiles(results_dir: Path) -> List[Dict[str, Any]]:
    return eligible_profiles(results_dir)

def load_consensus(root: Path) -> List[Dict[str, Any]]:
    data = load_json(root / "consensus_report.json", {})
    return list(iter_dicts(data))

def load_consensus_action_intake(root: Path) -> Dict[str, Any]:
    """Read prioritized consensus signals as an advisory Director channel."""
    payload = load_json(root / "consensus_report.json", {})
    if not isinstance(payload, dict):
        payload = {}

    principles = payload.get("principles", [])
    if not isinstance(principles, list):
        principles = []

    records: List[Dict[str, Any]] = []
    priority_counts: Dict[str, int] = {}
    primary_type_counts: Dict[str, int] = {}
    blocked_total = 0
    active_total = 0
    raw_total = 0

    for principle in principles:
        if not isinstance(principle, dict):
            continue
        prioritized = principle.get("prioritized_actions", {})
        if not isinstance(prioritized, dict):
            continue

        primary = prioritized.get("primary_signal")
        secondary = prioritized.get("secondary_signals", [])
        blocked = prioritized.get("blocked_signals", [])
        if not isinstance(secondary, list):
            secondary = []
        if not isinstance(blocked, list):
            blocked = []

        primary_type = (
            str(primary.get("signal_type"))
            if isinstance(primary, dict) and primary.get("signal_type")
            else None
        )
        highest_priority = str(
            prioritized.get("highest_priority") or "NONE"
        )
        priority_counts[highest_priority] = (
            priority_counts.get(highest_priority, 0) + 1
        )
        if primary_type:
            primary_type_counts[primary_type] = (
                primary_type_counts.get(primary_type, 0) + 1
            )

        active_count = int(safe_num(
            prioritized.get("active_signal_count"),
            (1 if primary_type else 0) + len(secondary),
        ))
        blocked_count = int(safe_num(
            prioritized.get("blocked_signal_count"),
            len(blocked),
        ))
        raw_count = int(safe_num(
            prioritized.get("raw_signal_count"),
            active_count + blocked_count,
        ))
        active_total += active_count
        blocked_total += blocked_count
        raw_total += raw_count

        records.append({
            "principle_id": str(principle.get("id") or "UNKNOWN"),
            "principle_title": str(
                principle.get("title") or principle.get("id") or "Unknown"
            ),
            "legacy_status": str(principle.get("status") or "UNKNOWN"),
            "channel_aware_status": str(
                principle.get("channel_aware_status") or "UNKNOWN"
            ),
            "confidence_posture": str(
                principle.get("confidence_posture") or "UNKNOWN"
            ),
            "highest_priority": highest_priority,
            "priority_score": int(safe_num(
                prioritized.get("priority_score"), 0
            )),
            "primary_signal": primary if isinstance(primary, dict) else None,
            "secondary_signals": [
                item for item in secondary if isinstance(item, dict)
            ],
            "blocked_signals": [
                item for item in blocked if isinstance(item, dict)
            ],
            "active_signal_count": active_count,
            "blocked_signal_count": blocked_count,
            "raw_signal_count": raw_count,
        })

    records.sort(
        key=lambda item: (
            int(safe_num(item.get("priority_score"), 0)),
            str(item.get("principle_id")),
        ),
        reverse=True,
    )

    return {
        "schema": "archon_research_director_consensus_intake_v1",
        "source": str(root / "consensus_report.json"),
        "source_schema": payload.get("schema"),
        "available": bool(records),
        "principle_count": len(records),
        "active_signal_count": active_total,
        "blocked_signal_count": blocked_total,
        "raw_signal_count": raw_total,
        "priority_counts": priority_counts,
        "primary_signal_type_counts": primary_type_counts,
        "principles": records,
        "scientific_policy": {
            "advisory_only": True,
            "creates_research_actions": False,
            "changes_director_priority": False,
            "changes_strategic_score": False,
            "automatic_execution": False,
        },
    }

def load_evidence(root: Path) -> List[Dict[str, Any]]:
    data = load_json(root / "evidence_report.json", {})
    return list(iter_dicts(data))

def load_general_principles(root: Path) -> List[Dict[str, Any]]:
    data = load_json(root / "general_principles.json", {})
    return list(iter_dicts(data))

def load_meta(root: Path) -> Dict[str, Any]:
    data = load_json(root / "meta_science_report.json", {})
    return data if isinstance(data, dict) else {}

def load_reference_controls(knowledge_root: Path) -> Dict[str, Any]:
    data = load_json(knowledge_root / "reference_control_registry.json", {})
    return data if isinstance(data, dict) else {}

def load_knowledge_base(knowledge_root: Path) -> Dict[str, Any]:
    data = load_json(knowledge_root / "knowledge_base.json", {})
    return data if isinstance(data, dict) else {}

def load_experiment_plan(root: Path) -> List[Dict[str, Any]]:
    data = load_json(root / "experiment_plan.json", {})
    plan = data.get("plan", []) if isinstance(data, dict) else []
    return [x for x in plan if isinstance(x, dict)] if isinstance(plan, list) else []

def load_search_execution_outcomes(root: Path) -> Dict[str, Any]:
    """Load POSTSEARCH1 outcome receipts as a read-only Director intake."""
    path = root / "Experiments" / "search_execution_outcome_registry.json"
    data = load_json(path, {})
    if not isinstance(data, dict):
        return {
            "schema": "archon_research_director_search_outcome_intake_v1",
            "available": False,
            "outcomes": [],
        }
    rows = [
        dict(row) for row in data.get("outcomes", [])
        if isinstance(row, dict)
    ]
    rows.sort(key=lambda row: str(row.get("generated_at") or ""))
    return {
        "schema": "archon_research_director_search_outcome_intake_v1",
        "source": str(path),
        "available": bool(rows),
        "summary": data.get("summary") if isinstance(data.get("summary"), dict) else {},
        "latest": rows[-1] if rows else None,
        "outcomes": rows,
        "scientific_policy": {
            "advisory_only": True,
            "target_found_requires_observer_validation_when_flagged": True,
            "target_inconclusive_must_not_close_research_gap": True,
        },
    }

def load_prediction_database(knowledge_root: Path) -> Dict[str, Any]:
    data = load_json(knowledge_root / "prediction_database.json", {})
    return data if isinstance(data, dict) else {}

def load_meta_history(root: Path) -> List[Dict[str, Any]]:
    data = load_json(root / "meta_science_history.json", [])
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict) and isinstance(data.get("history"), list):
        return [x for x in data["history"] if isinstance(x, dict)]
    return []

def load_questions(results_dir: Path) -> Tuple[int, str]:
    txt = read_text(results_dir / "research_questions.md")
    if not txt:
        return 0, ""
    # Count markdown bullets/headings/questions conservatively.
    count = 0
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("-") or s.startswith("*") or s.startswith("#") or "?" in s:
            count += 1
    return max(count, 1), txt

def status_of_principle(p: Dict[str, Any]) -> str:
    for k in ("status", "stage", "maturity", "classification", "level"):
        v = p.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper().replace(" ", "_")
    # Some old reports might only have consensus/support values.
    c = clamp(_first_present(p.get("consensus"), p.get("consensus_score"), p.get("score")), 0, 1)
    support = int(safe_num(_first_present(p.get("support"), p.get("support_count")), 0))
    counter = int(safe_num(_first_present(p.get("counter"), p.get("counterexamples"), p.get("counterexample_count")), 0))
    if counter > support and support > 0:
        return "DISPUTED"
    if support <= 1:
        return "OBSERVATION"
    if c >= 0.95 and support >= 50:
        return "FOUNDATIONAL"
    if c >= 0.90 and support >= 20:
        return "CONSENSUS"
    if c >= 0.80 and support >= 10:
        return "STRONG"
    if c >= 0.65 and support >= 3:
        return "SUPPORTED"
    return "PROMISING" if support >= 2 else "OBSERVATION"
