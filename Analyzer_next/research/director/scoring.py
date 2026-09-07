"""Scientific prioritization, dependency, and coverage scoring."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from Analyzer_next.research.director.common import clamp, now_iso, safe_num
from Analyzer_next.research.director.contracts import ResearchAction
from Analyzer_next.research.director.governance.target_integrity import action_accepts_principle

PRINCIPLE_DOMAIN_KEYWORDS: Dict[str, set[str]] = {
    "GP-101": {
        "emergence", "validation", "false positive", "false negative",
        "emg", "criterion",
    },
    "GP-102": {
        "knowledge", "feedback", "coupling", "know", "fb",
    },
    "GP-103": {
        "self-regulation", "regulation", "self direction",
        "feedback risk", "recovery",
    },
    "GP-104": {
        "pattern", "life", "living", "object population",
        "mass", "age", "organization",
    },
    "GP-105": {
        "civilization", "knowledge scaffold", "civ", "technology",
        "culture", "institution",
    },
    "GP-201": {
        "memory", "stability", "repeatability", "noise sensitivity",
        "collapse", "genome signature",
    },
}

SIGNAL_ACTION_MATCH_POLICY: Dict[str, Dict[str, Any]] = {
    "needs_scope_test": {
        "kinds": {"matched_control_study", "cross_family_replication", "benchmark_control", "experiment"},
        "keywords": {"scope", "condition", "boundary", "matched", "control", "seed", "initial state", "calibration"},
    },
    "needs_counterexample_search": {
        "kinds": {"negative_cohort_search", "counterexample_set", "benchmark_control", "explore"},
        "keywords": {"counterexample", "negative cohort", "adversarial", "opposing regime", "low-know", "search"},
    },
    "needs_perturbation_resolution": {
        "kinds": {"perturbation_test", "perturbation_evidence_program", "matched_control_study"},
        "keywords": {"perturbation", "recovery", "mutation", "response", "matched control", "resolve"},
    },
    "needs_perturbation_evidence": {
        "kinds": {"perturbation_test", "perturbation_evidence_program"},
        "keywords": {"perturbation", "mutation", "recovery"},
    },
    "needs_controlled_experiment": {
        "kinds": {"matched_control_study", "benchmark_control", "perturbation_test", "cross_family_replication", "experiment"},
        "keywords": {"controlled", "control", "matched", "experiment", "validation"},
    },
    "needs_replication": {
        "kinds": {"cross_family_replication", "cluster_replication", "long_run_replication", "replication_set"},
        "keywords": {"replication", "multi-seed", "seed", "long run", "cross-family", "repeat"},
    },
    "ready_for_broader_validation": {
        "kinds": {"cross_family_replication", "benchmark_control", "prediction_followup"},
        "keywords": {"broader validation", "cross-family", "benchmark", "prediction followup"},
    },
}

def decision_profile(action_type: str, action_id: str) -> Dict[str, Any]:
    """Heuristic resource profile for Decision Model v1.0."""
    profiles: Dict[str, Dict[str, Any]] = {
        "infrastructure_upgrade": {
            "runtime": "medium",
            "cost": "low",
            "automation": "semi_auto",
            "dependency": "none",
            "prerequisites": [],
            "information_gain": 0.72,
        },
        "perturbation_test": {
            "runtime": "long",
            "cost": "high",
            "automation": "manual",
            "dependency": "required",
            "prerequisites": ["matched rule cohorts", "standardized perturbation protocol"],
            "information_gain": 0.95,
        },
        "matched_control_study": {
            "runtime": "long",
            "cost": "medium",
            "automation": "semi_auto",
            "dependency": "required",
            "prerequisites": ["matched control groups", "mechanism features"],
            "information_gain": 0.92,
        },
        "cross_family_replication": {
            "runtime": "medium",
            "cost": "medium",
            "automation": "semi_auto",
            "dependency": "optional",
            "prerequisites": ["unrelated rule families"],
            "information_gain": 0.88,
        },
        "negative_cohort_search": {
            "runtime": "medium",
            "cost": "medium",
            "automation": "semi_auto",
            "dependency": "optional",
            "prerequisites": ["search filters for negative cohort"],
            "information_gain": 0.80,
        },
        "benchmark_control": {
            "runtime": "medium",
            "cost": "low",
            "automation": "semi_auto",
            "dependency": "none",
            "prerequisites": [],
            "information_gain": 0.82,
        },
        "cluster_replication": {
            "runtime": "medium",
            "cost": "low",
            "automation": "full",
            "dependency": "optional",
            "prerequisites": ["sufficient Atlas sample"],
            "information_gain": 0.70,
        },
        "long_run_replication": {
            "runtime": "long",
            "cost": "medium",
            "automation": "full",
            "dependency": "none",
            "prerequisites": [],
            "information_gain": 0.76,
        },
        "prediction_followup": {
            "runtime": "medium",
            "cost": "medium",
            "automation": "semi_auto",
            "dependency": "optional",
            "prerequisites": [],
            "information_gain": 0.68,
        },
        "explore": {
            "runtime": "medium",
            "cost": "medium",
            "automation": "semi_auto",
            "dependency": "none",
            "prerequisites": [],
            "information_gain": 0.70,
        },
    }

    profile = dict(profiles.get(action_type, {
        "runtime": "medium",
        "cost": "medium",
        "automation": "semi_auto",
        "dependency": "optional",
        "prerequisites": [],
        "information_gain": 0.60,
    }))

    if action_id == "EXP-INFRA-MECH":
        profile.update({
            "runtime": "medium",
            "cost": "low",
            "automation": "semi_auto",
            "dependency": "none",
            "prerequisites": [],
            "information_gain": 0.78,
        })

    return profile

def compute_unlock_score(
    action_type: str,
    action_id: str,
    plan: List[Dict[str, Any]],
    bottleneck_component: Optional[str],
) -> float:
    """Estimate how many downstream tasks or subsystems this action can unlock."""
    direct_unlocks = {
        "infrastructure_upgrade": 4,
        "perturbation_test": 1,
        "matched_control_study": 2,
        "cross_family_replication": 2,
        "negative_cohort_search": 1,
        "benchmark_control": 2,
        "cluster_replication": 1,
        "long_run_replication": 1,
        "prediction_followup": 1,
    }

    count = direct_unlocks.get(action_type, 1)

    # Infrastructure that addresses the primary mechanism bottleneck has
    # broad downstream leverage.
    if action_id == "EXP-INFRA-MECH" or (
        action_type == "infrastructure_upgrade"
        and bottleneck_component == "mechanism_coverage"
    ):
        count = max(count, len(plan))

    return clamp(count / max(1, len(plan)), 0, 1)

def bottleneck_action_relevance(component: str, action_type: str) -> str:
    """
    Return direct, supporting, or none.

    Direct actions primarily close the bottleneck.
    Supporting actions may benefit from or contribute to it, but are not the
    shortest route to removing the bottleneck.
    """
    mapping = {
        "mechanism_coverage": {
            "direct": {
                "infrastructure_upgrade",
                "mechanism",
            },
            "supporting": {
                "matched_control_study",
                "perturbation_test",
            },
        },
        "validation_resolution": {
            "direct": {
                "perturbation_test",
                "matched_control_study",
                "cross_family_replication",
                "negative_cohort_search",
                "prediction_followup",
            },
            "supporting": {
                "benchmark_control",
                "mechanism",
            },
        },
        "research_debt_control": {
            "direct": {
                "infrastructure_upgrade",
                "benchmark_control",
            },
            "supporting": {
                "replication_set",
                "cluster_replication",
            },
        },
        "knowledge_coverage": {
            "direct": {
                "replication_set",
                "long_run_replication",
            },
            "supporting": {
                "explore",
            },
        },
        "discovery_coverage": {
            "direct": {
                "explore",
                "cluster_replication",
            },
            "supporting": {
                "replication_set",
            },
        },
        "scientific_stability": {
            "direct": {
                "counterexample_set",
                "benchmark_control",
            },
            "supporting": {
                "cross_family_replication",
                "negative_cohort_search",
            },
        },
        "integrity": {
            "direct": {
                "integrity_repair",
            },
            "supporting": set(),
        },
    }

    spec = mapping.get(component, {})
    if action_type in spec.get("direct", set()):
        return "direct"
    if action_type in spec.get("supporting", set()):
        return "supporting"
    return "none"

def rank_plan_by_bottlenecks(
    plan: List[Dict[str, Any]],
    meta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    bottlenecks = meta.get("bottlenecks", {}) if isinstance(meta, dict) else {}
    ranked_bottlenecks = (
        bottlenecks.get("ranking", [])
        if isinstance(bottlenecks, dict)
        else []
    )
    if not isinstance(ranked_bottlenecks, list):
        ranked_bottlenecks = []

    output: List[Dict[str, Any]] = []

    for item in plan:
        row = dict(item)
        base_priority = int(safe_num(row.get("priority"), 0))
        action_type = str(row.get("type") or "")

        best_match = None
        best_match_score = -1.0

        for index, bottleneck in enumerate(ranked_bottlenecks, start=1):
            if not isinstance(bottleneck, dict):
                continue

            component = str(bottleneck.get("component") or "")
            directness = bottleneck_action_relevance(component, action_type)
            if directness == "none":
                continue

            severity = clamp(bottleneck.get("severity"), 0, 1)
            gain = clamp(bottleneck.get("max_index_gain"), 0, 1)
            directness_value = 1.0 if directness == "direct" else 0.45

            # Used only to choose the most relevant bottleneck for this action.
            match_score = (
                0.45 * directness_value
                + 0.35 * severity
                + 0.20 * clamp(gain / 0.15, 0, 1)
            )

            if match_score > best_match_score:
                best_match_score = match_score
                best_match = {
                    "component": component,
                    "rank": index,
                    "severity": severity,
                    "gain": gain,
                    "directness": directness,
                    "directness_value": directness_value,
                }

        if best_match:
            severity = best_match["severity"]
            gain_normalized = clamp(best_match["gain"] / 0.15, 0, 1)
            directness_value = best_match["directness_value"]

            # Strategic score on a 0-10 scale.
            strategic_score = 10.0 * (
                0.40 * clamp(base_priority / 5.0, 0, 1)
                + 0.30 * severity
                + 0.20 * gain_normalized
                + 0.10 * directness_value
            )

            row["_bottleneck_component"] = best_match["component"]
            row["_bottleneck_rank"] = best_match["rank"]
            row["_bottleneck_severity"] = severity
            row["_projected_health_gain"] = best_match["gain"]
            row["_bottleneck_directness"] = best_match["directness"]
        else:
            strategic_score = 10.0 * 0.40 * clamp(base_priority / 5.0, 0, 1)
            row["_bottleneck_component"] = None
            row["_bottleneck_rank"] = None
            row["_bottleneck_severity"] = 0.0
            row["_projected_health_gain"] = 0.0
            row["_bottleneck_directness"] = "none"

        row["_base_priority"] = base_priority
        row["_strategic_score"] = round(strategic_score, 4)

        # Keep a familiar integer label for the console, derived from score.
        row["_effective_priority"] = max(
            1,
            min(10, int(round(strategic_score))),
        )
        output.append(row)

    return sorted(
        output,
        key=lambda item: (
            float(item.get("_strategic_score", 0.0)),
            item.get("_bottleneck_directness") == "direct",
            float(item.get("_projected_health_gain", 0.0)),
            float(item.get("_bottleneck_severity", 0.0)),
            str(item.get("id", "")),
        ),
        reverse=True,
    )

def build_dependency_graph(
    actions: List[ResearchAction],
    experiment_plan: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build explicit action dependencies without changing ranking yet.

    `required` means the downstream experiment should not be treated as fully
    executable before the prerequisite is satisfied.
    `supporting` means the action improves quality or efficiency but is not a
    strict blocker.
    """
    by_id = {action.action_id: action for action in actions}
    plan_by_id = {
        str(item.get("id")): item
        for item in experiment_plan
        if isinstance(item, dict) and item.get("id")
    }

    required_edges: List[Dict[str, str]] = []
    supporting_edges: List[Dict[str, str]] = []

    explicit_required = {
        "EXP-GP103": ["EXP-GP102"],
    }
    explicit_supporting = {
        "EXP-GP101": ["EXP-INFRA-MECH"],
        "EXP-GP102": ["EXP-INFRA-MECH"],
        "EXP-GP103": ["EXP-INFRA-MECH"],
    }

    for target_id, source_ids in explicit_required.items():
        if target_id not in by_id:
            continue
        for source_id in source_ids:
            if source_id in by_id:
                required_edges.append({
                    "from": source_id,
                    "to": target_id,
                    "relation": "required",
                    "reason": (
                        "The downstream experiment requires outputs or cohorts "
                        "created by the prerequisite action."
                    ),
                })

    for target_id, source_ids in explicit_supporting.items():
        if target_id not in by_id:
            continue
        for source_id in source_ids:
            if source_id in by_id:
                supporting_edges.append({
                    "from": source_id,
                    "to": target_id,
                    "relation": "supporting",
                    "reason": (
                        "The upstream action improves measurement quality, "
                        "comparison power, or interpretation."
                    ),
                })

    # Link experiments to predictions from the Planner payload.
    for action_id, action in by_id.items():
        plan_item = plan_by_id.get(action_id, {})
        prediction_id = plan_item.get("based_on_prediction")
        if prediction_id:
            action.linked_predictions = [str(prediction_id)]

    # Populate action-level graph fields.
    for edge in required_edges:
        source = by_id[edge["from"]]
        target = by_id[edge["to"]]
        if edge["from"] not in target.depends_on_actions:
            target.depends_on_actions.append(edge["from"])
        if edge["to"] not in source.unlocks_actions:
            source.unlocks_actions.append(edge["to"])

    for edge in supporting_edges:
        source = by_id[edge["from"]]
        target = by_id[edge["to"]]
        if edge["from"] not in target.supporting_actions:
            target.supporting_actions.append(edge["from"])
        if edge["to"] not in source.unlocks_actions:
            source.unlocks_actions.append(edge["to"])

    # Compute required-dependency depth using a tiny DAG-safe relaxation.
    depths = {action_id: 0 for action_id in by_id}
    for _ in range(max(1, len(by_id))):
        changed = False
        for edge in required_edges:
            candidate = depths[edge["from"]] + 1
            if candidate > depths[edge["to"]]:
                depths[edge["to"]] = candidate
                changed = True
        if not changed:
            break

    for action_id, action in by_id.items():
        action.depends_on_actions = sorted(set(action.depends_on_actions))
        action.supporting_actions = sorted(set(action.supporting_actions))
        action.unlocks_actions = sorted(set(action.unlocks_actions))
        action.linked_predictions = sorted(set(action.linked_predictions))
        action.dependency_depth = depths.get(action_id, 0)

    nodes = []
    for action in actions:
        nodes.append({
            "id": action.action_id,
            "title": action.title,
            "type": action.kind,
            "depends_on": action.depends_on_actions,
            "supported_by": action.supporting_actions,
            "unlocks": action.unlocks_actions,
            "linked_predictions": action.linked_predictions,
            "dependency_depth": action.dependency_depth,
            "strategic_score": action.strategic_score,
        })

    return {
        "schema": "archon_research_dependency_graph_v1",
        "version": "Dependency Graph v1.0",
        "generated_at": now_iso(),
        "node_count": len(nodes),
        "required_edge_count": len(required_edges),
        "supporting_edge_count": len(supporting_edges),
        "nodes": nodes,
        "required_edges": required_edges,
        "supporting_edges": supporting_edges,
        "roots": sorted(
            action.action_id
            for action in actions
            if not action.depends_on_actions
        ),
        "terminal_actions": sorted(
            action.action_id
            for action in actions
            if not action.unlocks_actions
        ),
    }

def apply_graph_unlock_scores(
    actions: List[ResearchAction],
    dependency_graph: Dict[str, Any],
) -> None:
    """
    Replace heuristic unlock scores with graph-derived leverage.

    Direct edge weights:
    - required:   1.00
    - supporting: 0.55

    Additional hops decay:
    - required hop multiplier:   0.65
    - supporting hop multiplier: 0.30

    For every source action, only the strongest path to each downstream action
    is counted. Raw leverage is then normalized against the strongest action
    in the current graph.
    """
    by_id = {action.action_id: action for action in actions}
    adjacency: Dict[str, List[Tuple[str, str]]] = {
        action_id: [] for action_id in by_id
    }

    for edge in dependency_graph.get("required_edges", []):
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source in adjacency and target in by_id:
            adjacency[source].append((target, "required"))

    for edge in dependency_graph.get("supporting_edges", []):
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source in adjacency and target in by_id:
            adjacency[source].append((target, "supporting"))

    direct_weight = {
        "required": 1.00,
        "supporting": 0.55,
    }
    hop_decay = {
        "required": 0.65,
        "supporting": 0.30,
    }

    raw_scores: Dict[str, float] = {}

    for source_id in by_id:
        best_to_target: Dict[str, float] = {}
        stack: List[Tuple[str, float, int, Tuple[str, ...]]] = [
            (source_id, 1.0, 0, (source_id,))
        ]

        while stack:
            node, path_weight, depth, visited = stack.pop()

            for target, relation in adjacency.get(node, []):
                if target in visited:
                    continue

                if depth == 0:
                    next_weight = direct_weight[relation]
                else:
                    next_weight = path_weight * hop_decay[relation]

                if next_weight <= 0:
                    continue

                if next_weight > best_to_target.get(target, 0.0):
                    best_to_target[target] = next_weight

                stack.append(
                    (
                        target,
                        next_weight,
                        depth + 1,
                        visited + (target,),
                    )
                )

        raw_scores[source_id] = sum(best_to_target.values())

    maximum_raw = max(raw_scores.values(), default=0.0)

    for action_id, action in by_id.items():
        raw = raw_scores.get(action_id, 0.0)
        action.graph_unlock_raw = round(raw, 4)
        action.unlock_score = (
            round(raw / maximum_raw, 4)
            if maximum_raw > 0
            else 0.0
        )

    # Refresh graph nodes after assigning scores.
    node_map = {
        str(node.get("id")): node
        for node in dependency_graph.get("nodes", [])
        if isinstance(node, dict)
    }
    for action_id, action in by_id.items():
        node = node_map.get(action_id)
        if node is not None:
            node["graph_unlock_raw"] = action.graph_unlock_raw
            node["unlock_score"] = action.unlock_score

    dependency_graph["unlock_model"] = {
        "version": "Graph Unlock Model v1.0",
        "direct_required": 1.00,
        "direct_supporting": 0.55,
        "indirect_required_decay": 0.65,
        "indirect_supporting_decay": 0.30,
        "normalization": "divide by maximum raw leverage in current graph",
    }
    dependency_graph["maximum_raw_unlock"] = round(maximum_raw, 4)

def recompute_strategic_scores(actions: List[ResearchAction]) -> None:
    """
    Final strategic score after the complete action graph is known.

    Components:
    - Planner priority:          30%
    - Bottleneck severity:      20%
    - Scientific Health gain:   15%
    - Bottleneck directness:    10%
    - Information gain:         10%
    - Graph unlock leverage:    15%
    """
    for action in actions:
        base_component = clamp(action.base_priority / 5.0, 0, 1)
        severity_component = clamp(action.bottleneck_severity, 0, 1)
        health_gain_component = clamp(
            action.projected_health_gain / 0.15,
            0,
            1,
        )
        directness_component = (
            1.0
            if action.bottleneck_directness == "direct"
            else 0.45
            if action.bottleneck_directness == "supporting"
            else 0.0
        )
        information_component = clamp(
            action.expected_information_gain_score,
            0,
            1,
        )
        unlock_component = clamp(action.unlock_score, 0, 1)

        action.strategic_score = round(
            10.0 * (
                0.30 * base_component
                + 0.20 * severity_component
                + 0.15 * health_gain_component
                + 0.10 * directness_component
                + 0.10 * information_component
                + 0.15 * unlock_component
            ),
            4,
        )
        action.priority = max(
            1,
            min(10, int(round(action.strategic_score))),
        )
        action.urgency = (
            "Critical"
            if action.priority >= 7
            else "High"
            if action.priority >= 5
            else "Medium"
            if action.priority >= 3
            else "Low"
        )
        action.decision_model_version = "Decision Model v1.1"

def _action_search_text(action: ResearchAction) -> str:
    return " ".join([
        action.action_id,
        action.title,
        action.kind,
        action.rationale,
        action.suggested_target or "",
        action.done_when or "",
        " ".join(action.prerequisites),
    ]).lower()

def score_signal_action_match(
    signal: Dict[str, Any],
    action: ResearchAction,
    principle_id: str,
) -> Tuple[float, List[str], str]:
    """Return score, reasons, and coverage scope.

    Coverage scopes:
    - exact: explicit principle ID or strong domain match
    - family: signal-target compatibility without principle specificity
    - generic: broad action-kind/keyword overlap only
    """
    signal_type = str(signal.get("signal_type") or "")

    # Scientific target integrity: an action whose ID is explicitly bound to
    # GP-XXX must never become the refinement target for another principle.
    # Cross-principle relationships remain representable as dependencies;
    # they are not permitted to rewrite the action's scientific target.
    if not action_accepts_principle(action.action_id, principle_id):
        return 0.0, [
            f"principle_target_boundary:{action.action_id}:{principle_id}"
        ], "none"

    policy = SIGNAL_ACTION_MATCH_POLICY.get(signal_type, {})
    kinds = set(policy.get("kinds", set()))
    keywords = set(policy.get("keywords", set()))
    domain_keywords = PRINCIPLE_DOMAIN_KEYWORDS.get(
        principle_id,
        set(),
    )
    text = _action_search_text(action)

    score = 0.0
    reasons: List[str] = []
    exact_specificity = False
    family_specificity = False

    if action.kind in kinds:
        score += 0.30
        reasons.append(f"kind_match:{action.kind}")

    keyword_hits = sorted(k for k in keywords if k and k in text)
    if keyword_hits:
        score += min(0.22, 0.06 * len(keyword_hits))
        reasons.append("signal_keyword_match:" + ",".join(keyword_hits[:5]))
        family_specificity = True

    principle_token = principle_id.lower()
    compact = principle_token.replace("-", "")
    if principle_token in text or compact in text.replace("-", ""):
        score += 0.32
        reasons.append(f"principle_id_match:{principle_id}")
        exact_specificity = True

    domain_hits = sorted(
        keyword for keyword in domain_keywords
        if keyword and keyword in text
    )
    if domain_hits:
        score += min(0.32, 0.10 * len(domain_hits))
        reasons.append("principle_domain_match:" + ",".join(domain_hits[:5]))
        exact_specificity = True

    suggested_target = str(signal.get("suggested_target") or "").lower()
    target_tokens = {
        token for token in re.split(r"[_\W]+", suggested_target)
        if len(token) >= 5
    }
    overlap = sorted(token for token in target_tokens if token in text)
    if overlap:
        score += min(0.20, 0.06 * len(overlap))
        reasons.append("target_overlap:" + ",".join(overlap[:4]))
        family_specificity = True

    if exact_specificity:
        scope = "exact"
    elif family_specificity:
        scope = "family"
    elif score > 0:
        scope = "generic"
    else:
        scope = "none"

    # Generic overlap must never masquerade as full coverage.
    if scope == "generic":
        score = min(score, 0.44)
    elif scope == "family":
        score = min(score, 0.79)

    return clamp(score, 0.0, 1.0), reasons, scope

def reconcile_consensus_signals_to_actions(
    intake: Dict[str, Any],
    actions: List[ResearchAction],
) -> Dict[str, Any]:
    principle_records = intake.get("principles", []) if isinstance(intake, dict) else []
    if not isinstance(principle_records, list):
        principle_records = []

    rows: List[Dict[str, Any]] = []
    status_counts = {"covered": 0, "partial": 0, "uncovered": 0, "blocked": 0}
    action_coverage: Dict[str, List[str]] = {}

    for principle in principle_records:
        if not isinstance(principle, dict):
            continue
        principle_id = str(principle.get("principle_id") or "UNKNOWN")
        grouped: List[Tuple[str, Any]] = [("primary", principle.get("primary_signal"))]
        grouped.extend(("secondary", x) for x in principle.get("secondary_signals", []) or [])
        grouped.extend(("blocked", x) for x in principle.get("blocked_signals", []) or [])

        for role, signal in grouped:
            if not isinstance(signal, dict):
                continue

            matches: List[Dict[str, Any]] = []
            for action in actions:
                score, reasons, coverage_scope = score_signal_action_match(
                    signal,
                    action,
                    principle_id,
                )
                if score <= 0:
                    continue
                matches.append({
                    "action_id": action.action_id,
                    "action_title": action.title,
                    "action_kind": action.kind,
                    "match_score": round(score, 4),
                    "match_reasons": reasons,
                    "coverage_scope": coverage_scope,
                    "action_priority": action.priority,
                    "strategic_score": action.strategic_score,
                })

            matches.sort(
                key=lambda item: (
                    safe_num(item.get("match_score"), 0.0),
                    safe_num(item.get("strategic_score"), 0.0),
                    safe_num(item.get("action_priority"), 0.0),
                ),
                reverse=True,
            )

            # BRIDGE5.8.4: a blocked Consensus signal is a downstream
            # dependency statement, not a license to block every action for
            # the same principle.  Principle/domain overlap alone can produce
            # a strong-looking match (for example GP-103 needs_replication ->
            # EXP-PERT-GP-103), even though the action cannot perform the
            # blocked signal.  For blocked rows, only signal-capable actions
            # may become dependency targets.  Keep the broad match separately
            # for diagnostics so no information is lost.
            diagnostic_best = matches[0] if matches else None
            if role == "blocked":
                signal_capable_matches = [
                    item
                    for item in matches
                    if any(
                        str(reason).startswith((
                            "kind_match:",
                            "signal_keyword_match:",
                        ))
                        for reason in (item.get("match_reasons") or [])
                    )
                ]
                best = (
                    signal_capable_matches[0]
                    if signal_capable_matches
                    else None
                )
                alternatives = signal_capable_matches[1:4]
            else:
                best = diagnostic_best
                alternatives = matches[1:4]

            if role == "blocked":
                status = "blocked"
            elif (
                best
                and safe_num(best.get("match_score"), 0.0) >= 0.80
                and str(best.get("coverage_scope")) == "exact"
            ):
                status = "covered"
            elif best and safe_num(best.get("match_score"), 0.0) >= 0.45:
                status = "partial"
            else:
                status = "uncovered"

            status_counts[status] += 1
            if best and status in {"covered", "partial"}:
                action_coverage.setdefault(str(best["action_id"]), []).append(
                    f"{principle_id}:{signal.get('signal_type')}"
                )

            rows.append({
                "reconciliation_id": f"{principle_id}::{role}::{signal.get('signal_type')}",
                "principle_id": principle_id,
                "signal_role": role,
                "signal_type": signal.get("signal_type"),
                "signal_priority": signal.get("priority"),
                "signal_priority_score": signal.get("priority_score"),
                "status": status,
                "best_action": best,
                "alternative_matches": alternatives,
                "diagnostic_best_action": (
                    diagnostic_best
                    if role == "blocked"
                    and diagnostic_best is not None
                    and (
                        best is None
                        or str(diagnostic_best.get("action_id"))
                        != str(best.get("action_id"))
                    )
                    else None
                ),
                "blocked_by": list(signal.get("blocked_by", []) or []),
                "rationale": (
                    "Signal is blocked by Consensus dependency policy."
                    if status == "blocked"
                    else "Existing Director action strongly covers this signal."
                    if status == "covered"
                    else "Existing Director action partially covers this signal."
                    if status == "partial"
                    else "No existing Director action sufficiently covers this signal."
                ),
            })

    return {
        "schema": "archon_signal_action_reconciliation_v1",
        "available": bool(rows),
        "signal_count": len(rows),
        "status_counts": status_counts,
        "covered_or_partial_count": status_counts["covered"] + status_counts["partial"],
        "uncovered_count": status_counts["uncovered"],
        "blocked_count": status_counts["blocked"],
        "action_coverage": {
            action_id: sorted(set(values))
            for action_id, values in action_coverage.items()
        },
        "reconciliations": rows,
        "scientific_policy": {
            "advisory_only": True,
            "creates_research_actions": False,
            "changes_director_priority": False,
            "changes_strategic_score": False,
            "automatic_execution": False,
            "deterministic_matching": True,
            "covered_requires_exact_specificity": True,
            "covered_minimum_score": 0.80,
            "partial_minimum_score": 0.45,
            "generic_scope_capped_at": 0.44,
            "family_scope_capped_at": 0.79,
        },
    }

def interpret_director_coverage_gaps(
    intake: Dict[str, Any],
    reconciliation: Dict[str, Any],
) -> Dict[str, Any]:
    """Aggregate signal reconciliation into principle-level coverage states."""
    principle_meta = {
        str(item.get("principle_id")): item
        for item in (intake.get("principles", []) if isinstance(intake, dict) else [])
        if isinstance(item, dict) and item.get("principle_id")
    }

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    rows = (
        reconciliation.get("reconciliations", [])
        if isinstance(reconciliation, dict)
        else []
    )
    if not isinstance(rows, list):
        rows = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("principle_id") or "UNKNOWN")
        grouped.setdefault(pid, []).append(row)

    principle_results: List[Dict[str, Any]] = []
    state_counts = {
        "fully_addressed": 0,
        "partially_addressed": 0,
        "unaddressed": 0,
        "blocked": 0,
    }

    for principle_id, items in grouped.items():
        active = [x for x in items if x.get("status") != "blocked"]
        blocked = [x for x in items if x.get("status") == "blocked"]
        covered = [x for x in active if x.get("status") == "covered"]
        partial = [x for x in active if x.get("status") == "partial"]
        uncovered = [x for x in active if x.get("status") == "uncovered"]

        primary_rows = [
            x for x in active
            if x.get("signal_role") == "primary"
        ]
        primary = primary_rows[0] if primary_rows else None
        primary_status = (
            str(primary.get("status"))
            if isinstance(primary, dict)
            else "missing"
        )

        if active and len(covered) == len(active):
            coverage_state = "fully_addressed"
        elif uncovered and not covered and not partial:
            coverage_state = "unaddressed"
        elif not active and blocked:
            coverage_state = "blocked"
        else:
            coverage_state = "partially_addressed"

        state_counts[coverage_state] += 1

        coverage_ratio = (
            (len(covered) + 0.5 * len(partial)) / len(active)
            if active
            else 0.0
        )

        priority = "HIGH" if primary_status in {"uncovered", "partial"} else "MEDIUM"
        if coverage_state == "fully_addressed":
            priority = "LOW"
        elif coverage_state == "unaddressed":
            priority = "CRITICAL"
        elif coverage_state == "blocked":
            priority = "MEDIUM"

        meta = principle_meta.get(principle_id, {})
        principle_results.append({
            "principle_id": principle_id,
            "principle_title": meta.get("principle_title"),
            "legacy_status": meta.get("legacy_status"),
            "channel_aware_status": meta.get("channel_aware_status"),
            "coverage_state": coverage_state,
            "coverage_ratio": round(coverage_ratio, 4),
            "primary_signal_status": primary_status,
            "active_signal_count": len(active),
            "covered_signal_count": len(covered),
            "partial_signal_count": len(partial),
            "uncovered_signal_count": len(uncovered),
            "blocked_signal_count": len(blocked),
            "covered_signals": [
                x.get("signal_type") for x in covered
            ],
            "partial_signals": [
                x.get("signal_type") for x in partial
            ],
            "uncovered_signals": [
                x.get("signal_type") for x in uncovered
            ],
            "blocked_signals": [
                x.get("signal_type") for x in blocked
            ],
            "interpretation_priority": priority,
            "interpretation": (
                "All active Consensus needs have exact Director coverage."
                if coverage_state == "fully_addressed"
                else "At least one active Consensus need is only partially covered."
                if coverage_state == "partially_addressed"
                else "No active Consensus need has sufficient Director coverage."
                if coverage_state == "unaddressed"
                else "All current needs are blocked by Consensus dependencies."
            ),
        })

    principle_results.sort(
        key=lambda item: (
            {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(
                str(item.get("interpretation_priority")), 0
            ),
            1.0 - safe_num(item.get("coverage_ratio"), 0.0),
            str(item.get("principle_id")),
        ),
        reverse=True,
    )

    fully = [
        item["principle_id"]
        for item in principle_results
        if item["coverage_state"] == "fully_addressed"
    ]
    partial = [
        item["principle_id"]
        for item in principle_results
        if item["coverage_state"] == "partially_addressed"
    ]
    unaddressed = [
        item["principle_id"]
        for item in principle_results
        if item["coverage_state"] == "unaddressed"
    ]
    blocked = [
        item["principle_id"]
        for item in principle_results
        if item["coverage_state"] == "blocked"
    ]

    return {
        "schema": "archon_director_coverage_gap_interpretation_v1",
        "available": bool(principle_results),
        "principle_count": len(principle_results),
        "state_counts": state_counts,
        "fully_addressed_principles": fully,
        "partially_addressed_principles": partial,
        "unaddressed_principles": unaddressed,
        "blocked_research_needs": blocked,
        "principles": principle_results,
        "scientific_policy": {
            "interpretation_only": True,
            "creates_research_actions": False,
            "changes_director_priority": False,
            "changes_strategic_score": False,
            "automatic_execution": False,
        },
    }

def build_coverage_aware_recommendations(
    coverage: Dict[str, Any],
    reconciliation: Dict[str, Any],
) -> Dict[str, Any]:
    """Turn coverage gaps into advisory refinement recommendations."""
    reconciliation_rows = (
        reconciliation.get("reconciliations", [])
        if isinstance(reconciliation, dict)
        else []
    )
    if not isinstance(reconciliation_rows, list):
        reconciliation_rows = []

    by_principle: Dict[str, List[Dict[str, Any]]] = {}
    for row in reconciliation_rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("principle_id") or "UNKNOWN")
        by_principle.setdefault(pid, []).append(row)

    recommendations: List[Dict[str, Any]] = []
    type_counts: Dict[str, int] = {}
    priority_counts: Dict[str, int] = {}

    for principle in (
        coverage.get("principles", [])
        if isinstance(coverage, dict)
        else []
    ):
        if not isinstance(principle, dict):
            continue

        principle_id = str(principle.get("principle_id") or "UNKNOWN")
        coverage_state = str(
            principle.get("coverage_state") or "unaddressed"
        )
        rows = by_principle.get(principle_id, [])

        for row in rows:
            status = str(row.get("status") or "")
            if status == "covered":
                continue

            signal_type = str(row.get("signal_type") or "unknown")
            signal_role = str(row.get("signal_role") or "secondary")
            best = row.get("best_action")
            best_action_id = (
                str(best.get("action_id"))
                if isinstance(best, dict) and best.get("action_id")
                else None
            )
            best_scope = (
                str(best.get("coverage_scope") or "none")
                if isinstance(best, dict)
                else "none"
            )
            match_score = (
                safe_num(best.get("match_score"), 0.0)
                if isinstance(best, dict)
                else 0.0
            )

            if status == "blocked":
                rec_type = "resolve_blocked_dependency"
                priority = "MEDIUM"
                rationale = (
                    "The Consensus signal is blocked by a prerequisite and "
                    "should remain deferred until that dependency is resolved."
                )
                refinement = "Resolve the declared blocking signal first."
            elif status == "partial" and best_action_id:
                if best_scope == "family":
                    rec_type = "add_missing_target"
                    refinement = (
                        f"Add explicit {principle_id} targeting and success "
                        f"criteria to action {best_action_id}."
                    )
                else:
                    rec_type = "extend_action_scope"
                    refinement = (
                        f"Extend action {best_action_id} so it directly tests "
                        f"{signal_type} for {principle_id}."
                    )
                priority = "HIGH" if signal_role == "primary" else "MEDIUM"
                rationale = (
                    "An existing Director action is relevant, but its current "
                    "scope is not specific enough for exact coverage."
                )
            elif status == "uncovered":
                rec_type = "refine_existing_action"
                priority = "CRITICAL" if signal_role == "primary" else "HIGH"
                rationale = (
                    "No existing Director action sufficiently addresses this "
                    "Consensus signal."
                )
                refinement = (
                    f"Identify the closest existing action and add a dedicated "
                    f"{principle_id}:{signal_type} target before creating a new action."
                )
            else:
                continue

            rec_id = (
                f"CAR-{principle_id}-"
                f"{signal_role.upper()}-"
                f"{signal_type.upper().replace('NEEDS_', '')}"
            )
            recommendations.append({
                "recommendation_id": rec_id,
                "principle_id": principle_id,
                "coverage_state": coverage_state,
                "signal_role": signal_role,
                "signal_type": signal_type,
                "reconciliation_status": status,
                "recommendation_type": rec_type,
                "priority": priority,
                "target_action_id": best_action_id,
                "match_scope": best_scope,
                "match_score": round(match_score, 4),
                "rationale": rationale,
                "recommended_refinement": refinement,
                "creates_new_action": False,
                "changes_existing_action": False,
                "automatic_execution": False,
            })
            type_counts[rec_type] = type_counts.get(rec_type, 0) + 1
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

    priority_order = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }
    recommendations.sort(
        key=lambda item: (
            priority_order.get(str(item.get("priority")), 0),
            str(item.get("signal_role")) == "primary",
            1.0 - safe_num(item.get("match_score"), 0.0),
            str(item.get("principle_id")),
        ),
        reverse=True,
    )

    principles_with_recommendations = sorted({
        str(item.get("principle_id"))
        for item in recommendations
    })

    return {
        "schema": "archon_coverage_aware_director_recommendations_v1",
        "available": bool(recommendations),
        "recommendation_count": len(recommendations),
        "principles_with_recommendations": principles_with_recommendations,
        "recommendation_type_counts": type_counts,
        "priority_counts": priority_counts,
        "recommendations": recommendations,
        "scientific_policy": {
            "advisory_only": True,
            "creates_research_actions": False,
            "modifies_existing_actions": False,
            "changes_director_priority": False,
            "changes_strategic_score": False,
            "automatic_execution": False,
        },
    }

def consolidate_coverage_recommendations(
    recommendation_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    """Group advisory recommendations by action and principle."""
    items = (
        recommendation_bundle.get("recommendations", [])
        if isinstance(recommendation_bundle, dict)
        else []
    )
    if not isinstance(items, list):
        items = []

    priority_order = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }

    def rank_key(item: Dict[str, Any]) -> Tuple[int, bool, float, str]:
        return (
            priority_order.get(str(item.get("priority")), 0),
            str(item.get("signal_role")) == "primary",
            1.0 - safe_num(item.get("match_score"), 0.0),
            str(item.get("recommendation_id")),
        )

    grouped_by_action: Dict[str, List[Dict[str, Any]]] = {}
    grouped_by_principle: Dict[str, List[Dict[str, Any]]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("target_action_id") or "UNASSIGNED")
        principle_id = str(item.get("principle_id") or "UNKNOWN")
        grouped_by_action.setdefault(action_id, []).append(item)
        grouped_by_principle.setdefault(principle_id, []).append(item)

    action_groups: List[Dict[str, Any]] = []
    principle_groups: List[Dict[str, Any]] = []

    for action_id, group in grouped_by_action.items():
        ordered = sorted(group, key=rank_key, reverse=True)
        primary = ordered[0] if ordered else None
        secondary = ordered[1:]

        refinements: List[str] = []
        signals: List[str] = []
        principles: List[str] = []
        types: List[str] = []

        for item in ordered:
            refinement = str(item.get("recommended_refinement") or "").strip()
            if refinement and refinement not in refinements:
                refinements.append(refinement)
            signal = str(item.get("signal_type") or "")
            if signal and signal not in signals:
                signals.append(signal)
            principle = str(item.get("principle_id") or "")
            if principle and principle not in principles:
                principles.append(principle)
            rec_type = str(item.get("recommendation_type") or "")
            if rec_type and rec_type not in types:
                types.append(rec_type)

        action_groups.append({
            "target_action_id": (
                None if action_id == "UNASSIGNED" else action_id
            ),
            "recommendation_count": len(ordered),
            "primary_recommendation": primary,
            "secondary_recommendations": secondary,
            "combined_refinements": refinements,
            "signals": signals,
            "principles": principles,
            "recommendation_types": types,
            "highest_priority": (
                str(primary.get("priority"))
                if isinstance(primary, dict)
                else "NONE"
            ),
            "consolidated_summary": (
                f"Refine {action_id}: " + " ".join(refinements)
                if action_id != "UNASSIGNED"
                else "Unassigned recommendation set: " + " ".join(refinements)
            ),
        })

    for principle_id, group in grouped_by_principle.items():
        ordered = sorted(group, key=rank_key, reverse=True)
        primary = ordered[0] if ordered else None
        principle_groups.append({
            "principle_id": principle_id,
            "recommendation_count": len(ordered),
            "primary_recommendation": primary,
            "secondary_recommendations": ordered[1:],
            "target_actions": sorted({
                str(item.get("target_action_id"))
                for item in ordered
                if item.get("target_action_id")
            }),
            "signals": sorted({
                str(item.get("signal_type"))
                for item in ordered
                if item.get("signal_type")
            }),
            "highest_priority": (
                str(primary.get("priority"))
                if isinstance(primary, dict)
                else "NONE"
            ),
        })

    action_groups.sort(
        key=lambda item: (
            priority_order.get(str(item.get("highest_priority")), 0),
            int(safe_num(item.get("recommendation_count"), 0)),
            str(item.get("target_action_id") or ""),
        ),
        reverse=True,
    )
    principle_groups.sort(
        key=lambda item: (
            priority_order.get(str(item.get("highest_priority")), 0),
            int(safe_num(item.get("recommendation_count"), 0)),
            str(item.get("principle_id")),
        ),
        reverse=True,
    )

    primary_recommendation = (
        sorted(
            [item for item in items if isinstance(item, dict)],
            key=rank_key,
            reverse=True,
        )[0]
        if items
        else None
    )

    return {
        "schema": "archon_consolidated_coverage_recommendations_v1",
        "available": bool(items),
        "raw_recommendation_count": len(items),
        "action_group_count": len(action_groups),
        "principle_group_count": len(principle_groups),
        "primary_recommendation": primary_recommendation,
        "recommendations_by_action": action_groups,
        "recommendations_by_principle": principle_groups,
        "scientific_policy": {
            "advisory_only": True,
            "creates_research_actions": False,
            "modifies_existing_actions": False,
            "changes_director_priority": False,
            "changes_strategic_score": False,
            "automatic_execution": False,
            "deduplicates_refinement_text": True,
        },
    }
