"""Research-state evaluation, trends, and action finalization."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List

from Analyzer_next.adapters.scientific_view_adapter import SCIENTIFIC_VIEW_SCHEMA, evidence_rule_set, scope_signature
from Analyzer_next.research.director.common import clamp, count_unique_rules, load_json, now_iso, safe_num, write_json
from Analyzer_next.research.director.contracts import ResearchAction, ResearchDirectorState
from Analyzer_next.research.director.execution_readiness import classify_action_execution_readiness
from Analyzer_next.research.director.governance.patch_application import load_latest_patch_application_receipt, load_patch_application_request
from Analyzer_next.research.director.governance.patch_preview import load_research_action_patch_state
from Analyzer_next.research.director.governance.patch_rollback import load_latest_patch_rollback_receipt, load_patch_rollback_request
from Analyzer_next.research.director.governance.review import load_human_review_audit_trail, load_human_review_decisions, load_review_import_candidate
from Analyzer_next.research.director.governance.review_transactions import load_latest_review_commit_receipt, load_review_commit_request
from Analyzer_next.research.director.inputs import load_consensus, load_consensus_action_intake, load_evidence, load_experiment_plan, load_general_principles, load_knowledge_base, load_meta, load_meta_history, load_prediction_database, load_profiles, load_questions, load_reference_controls, load_search_execution_outcomes, status_of_principle
from Analyzer_next.research.director.scoring import apply_graph_unlock_scores, build_dependency_graph, compute_unlock_score, decision_profile, rank_plan_by_bottlenecks, recompute_strategic_scores

def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def finalize_action_strategy(state: ResearchDirectorState) -> ResearchDirectorState:
    """
    Finalize the Director after Trend Memory may have added actions.

    Order:
    final actions
    -> rebuild dependency graph
    -> graph-derived unlock
    -> strategic-score recomputation
    -> final sort
    -> refresh graph nodes with final scores
    """
    graph = build_dependency_graph(state.actions, [])
    apply_graph_unlock_scores(state.actions, graph)
    recompute_strategic_scores(state.actions)
    state.actions = sort_actions_by_decision(state.actions)

    # Rebuild once more so graph node ordering and node strategic scores
    # reflect the final sorted, rescored actions.
    graph = build_dependency_graph(state.actions, [])
    apply_graph_unlock_scores(state.actions, graph)

    node_map = {
        str(node.get("id")): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
    }
    for action in state.actions:
        node = node_map.get(action.action_id)
        if node is not None:
            node["strategic_score"] = action.strategic_score
            node["priority"] = action.priority
            node["information_gain_score"] = (
                action.expected_information_gain_score
            )
            node["graph_unlock_raw"] = action.graph_unlock_raw
            node["unlock_score"] = action.unlock_score

    graph["decision_model"] = {
        "version": "Decision Model v1.1",
        "formula": {
            "planner_priority": 0.30,
            "bottleneck_severity": 0.20,
            "scientific_health_gain": 0.15,
            "bottleneck_directness": 0.10,
            "information_gain": 0.10,
            "graph_unlock": 0.15,
        },
        "execution_order": [
            "final_actions",
            "dependency_graph",
            "graph_unlock",
            "strategic_score",
            "final_sort",
        ],
    }
    state.dependency_graph = graph
    return state

def evaluate_state(results_dir: Path, root: Path, knowledge_root: Path | None = None) -> ResearchDirectorState:
    knowledge_root = knowledge_root or root
    profiles = load_profiles(results_dir)
    reference_controls = load_reference_controls(knowledge_root)
    consensus = load_consensus(root)
    consensus_action_intake = load_consensus_action_intake(root)
    evidence = load_evidence(root)
    principles = load_general_principles(root)
    meta = load_meta(root)
    kb = load_knowledge_base(knowledge_root)
    experiment_plan = load_experiment_plan(root)
    search_execution_outcomes = load_search_execution_outcomes(root)
    prediction_db = load_prediction_database(knowledge_root)
    history = load_meta_history(knowledge_root)
    human_review_decisions = load_human_review_decisions(root)
    human_review_audit_trail = load_human_review_audit_trail(root)
    human_review_import_candidate = load_review_import_candidate(root)
    human_review_commit_request = load_review_commit_request(root)
    human_review_receipt_lookup = load_latest_review_commit_receipt(root)
    research_action_patch_state = load_research_action_patch_state(root)
    patch_application_request = load_patch_application_request(root)
    patch_application_receipt_lookup = load_latest_patch_application_receipt(root)
    patch_rollback_request = load_patch_rollback_request(root)
    patch_rollback_receipt_lookup = load_latest_patch_rollback_receipt(root)
    q_count, q_text = load_questions(root)
    if q_count == 0:
        q_count, q_text = load_questions(results_dir)

    kb_summary = kb.get("summary", {}) if isinstance(kb.get("summary"), dict) else {}
    current_evidence_rules = evidence_rule_set({
        "claims": evidence,
    })
    rules = len(current_evidence_rules)
    if rules == 0:
        rules = count_unique_rules(profiles) or len(profiles)
    if rules == 0 and profiles:
        rules = len(profiles)

    statuses = [status_of_principle(p) for p in consensus]
    supported = sum(s in {"SUPPORTED", "STRONG", "CONSENSUS", "FOUNDATIONAL"} for s in statuses)
    consensus_count = sum(s in {"CONSENSUS", "FOUNDATIONAL"} for s in statuses)
    foundational = sum(s == "FOUNDATIONAL" for s in statuses)
    disputed = sum(s == "DISPUTED" for s in statuses)

    # Pull useful scores from available files, including the v33 nested schema.
    meta_metrics = meta.get("research_metrics", {}) if isinstance(meta.get("research_metrics"), dict) else {}
    meta_maturity = clamp(
        meta_metrics.get("knowledge_maturity_score",
            meta.get("knowledge_maturity", meta.get("maturity", meta.get("score", 0.0)))),
        0, 1,
    )
    meta_velocity = clamp(
        meta_metrics.get("research_velocity_score",
            meta.get("research_velocity", meta.get("velocity", meta.get("knowledge_velocity", 0.0)))),
        0, 1,
    )
    meta_efficiency = clamp(
        meta_metrics.get("knowledge_efficiency_score",
            meta.get("knowledge_efficiency", meta.get("efficiency", 0.0))),
        0, 1,
    )


    lab_health = meta.get("laboratory_health", {}) if isinstance(meta.get("laboratory_health"), dict) else {}
    coverage = meta.get("coverage", {}) if isinstance(meta.get("coverage"), dict) else {}
    prediction_pipeline = meta.get("prediction_pipeline", {}) if isinstance(meta.get("prediction_pipeline"), dict) else {}
    research_debt = meta.get("research_debt", {}) if isinstance(meta.get("research_debt"), dict) else {}
    integrity = meta.get("knowledge_integrity", {}) if isinstance(meta.get("knowledge_integrity"), dict) else {}

    predictions_total = int(safe_num(prediction_pipeline.get("generated"), kb_summary.get("predictions", 0)))
    confirmed_predictions = int(safe_num(prediction_pipeline.get("confirmed"), 0))
    testing_predictions = int(safe_num(prediction_pipeline.get("testing"), 0))
    mechanism_coverage = clamp(safe_num(coverage.get("mechanism_percent"), 0) / 100.0)
    discovery_coverage = clamp(safe_num(coverage.get("discovery_percent"), 0) / 100.0)
    integrity_ok = bool(integrity.get("ok", lab_health.get("integrity_ok", False)))

    evidence_conf = []
    for e in evidence:
        evidence_conf.append(clamp(_first_present(e.get("confidence_score"), e.get("confidence"), e.get("quality"), e.get("score")), 0, 1))
    evidence_strength = sum(evidence_conf) / len(evidence_conf) if evidence_conf else 0.0

    consensus_scores = []
    for p in consensus:
        raw = _first_present(p.get("consensus"), p.get("consensus_score"), p.get("score"))
        val = safe_num(raw, 0)
        if val > 1.0:
            val /= 100.0
        consensus_scores.append(clamp(val, 0, 1))
    consensus_strength = sum(consensus_scores) / len(consensus_scores) if consensus_scores else 0.0

    # Diversity: right now rules are the main independent unit.
    # The score is deliberately conservative until many rules exist.
    diversity = clamp(math.log10(max(rules, 1)) / 3.0, 0, 1)  # 1 at about 1000 rules
    replication = clamp((rules - 1) / 24.0, 0, 1)             # decent at 25 rules
    principle_count = int(safe_num(kb_summary.get("principles"), len(consensus) or len(principles)))
    principle_volume = clamp(principle_count / 20.0, 0, 1)

    maturity = clamp(
        0.22 * meta_maturity
        + 0.18 * evidence_strength
        + 0.22 * consensus_strength
        + 0.18 * diversity
        + 0.10 * replication
        + 0.10 * principle_volume,
        0,
        1,
    )

    # If meta report is young, use derived proxies.
    if maturity < 0.03 and (profiles or consensus or evidence):
        maturity = clamp(0.08 + 0.10 * bool(profiles) + 0.10 * bool(evidence) + 0.12 * bool(consensus), 0, 1)

    # Research stage.
    if rules < 3:
        stage = "Exploration"
    elif maturity < 0.25:
        stage = "Structured Exploration"
    elif maturity < 0.45:
        stage = "Evidence Building"
    elif maturity < 0.65:
        stage = "Consensus Formation"
    elif maturity < 0.82:
        stage = "Pre-Foundational Research"
    else:
        stage = "Foundational Research"

    # Risks and bottlenecks.
    risks: List[str] = []
    bottlenecks: List[str] = []
    strengths: List[str] = []
    priorities: List[str] = []
    actions: List[ResearchAction] = []

    latest_search_outcome = search_execution_outcomes.get("latest") if isinstance(search_execution_outcomes, dict) else None
    if isinstance(latest_search_outcome, dict):
        search_status = str(latest_search_outcome.get("scientific_status") or "")
        search_job = str(latest_search_outcome.get("search_job_id") or "unknown Search job")
        target_regime = str(latest_search_outcome.get("target_regime") or "unknown target")
        if search_status == "TARGET_INCONCLUSIVE":
            bottlenecks.append(
                f"Search outcome is inconclusive for {target_regime} ({search_job})"
            )
            risks.append(
                "A completed Search must not be interpreted as target-not-found while target metric coverage is incomplete"
            )
            priorities.append(
                f"Resolve target-metric coverage before repeating {search_job}"
            )
        elif search_status == "TARGET_FOUND":
            strengths.append(
                f"Search produced a target candidate for {target_regime}"
            )
            priorities.append(
                f"Validate Search target candidate for {target_regime} in Observer before cohort promotion"
            )
        elif search_status == "TARGET_NOT_FOUND":
            strengths.append(
                f"Search exhausted a fully measured budget without finding {target_regime}"
            )

    if profiles:
        strengths.append("Normalized observer profile bridge is active")
    else:
        risks.append("Observer profiles are missing")
        bottlenecks.append("Analyzer has no normalized profile layer to reason from")

    if rules < 10:
        bottlenecks.append("Too few independent rules for strong scientific claims")
        risks.append("High single-case overfitting risk")
    elif rules < 50:
        bottlenecks.append("Replication base is still small")
    else:
        strengths.append("Independent-rule base is becoming useful")

    if len(consensus) == 0:
        bottlenecks.append("No consensus principles available yet")
    else:
        strengths.append("Consensus layer is producing ranked principles")

    if consensus_action_intake.get("available"):
        strengths.append(
            "Consensus action-signal intake is available as an advisory channel"
        )

    if disputed:
        risks.append(f"{disputed} principle(s) are disputed and need inspection")

    if evidence_strength < 0.35:
        bottlenecks.append("Evidence strength is low or based on very young claims")
    elif evidence_strength > 0.65:
        strengths.append("Evidence layer shows promising support quality")

    total_support = sum(safe_num(e.get("support"), 0) for e in evidence)
    total_counterexamples = sum(safe_num(e.get("counterexamples"), 0) for e in evidence)
    if total_support >= 10 and total_counterexamples == 0:
        risks.append("No counterexamples have been recorded despite broad support")
        bottlenecks.append("Counterexample search or classification may be under-tested")

    rc_summary = reference_controls.get("summary", {}) if isinstance(reference_controls, dict) else {}
    rc_observed = int(safe_num(rc_summary.get("observed_classes"), 0))
    rc_qualified = int(safe_num(rc_summary.get("qualified_classes"), 0))
    rc_total = int(safe_num(rc_summary.get("class_count"), 8))
    if rc_observed < rc_total:
        bottlenecks.append(
            f"Reference-control coverage is incomplete ({rc_observed}/{rc_total} regimes observed)"
        )
    elif rc_qualified < rc_total:
        bottlenecks.append(
            f"Reference controls exist, but only {rc_qualified}/{rc_total} regimes are qualified"
        )
    else:
        strengths.append("Reference-control registry covers all target regimes")

    if diversity < 0.35:
        bottlenecks.append("Rule diversity is too low for broad principles")

    if consensus_count == 0:
        priorities.append("Do not promote principles yet; collect more independent confirmations")
    else:
        priorities.append("Audit consensus-level principles for counterexamples")

    if rc_observed < rc_total:
        priorities.append("Fill missing reference-control regimes using normalized Observer evidence")
    elif rc_qualified < rc_total:
        priorities.append("Replicate observed reference regimes until each has at least three qualified rules")
    priorities.append("Compare high-EMG worlds against structurally similar qualified reference controls")

    # Research Director v34.1 combines Planner priority with Meta Science bottlenecks.
    actions = []
    execution_readiness = classify_action_execution_readiness(experiment_plan)
    ranked_plan = rank_plan_by_bottlenecks(experiment_plan, meta)
    for item in ranked_plan:
        priority = int(safe_num(item.get("_effective_priority"), len(actions) + 1))
        base_priority = int(safe_num(item.get("_base_priority"), priority))
        tests = item.get("tests") if isinstance(item.get("tests"), list) else []
        suggested_target = "; ".join(str(x) for x in tests[:3]) if tests else None
        rationale = str(
            item.get("reason") or "Generated from current validation state."
        )
        bottleneck_component = item.get("_bottleneck_component")
        if bottleneck_component:
            rationale += (
                f" Meta Science ranks {bottleneck_component} as bottleneck "
                f"#{item.get('_bottleneck_rank')} "
                f"(severity={safe_num(item.get('_bottleneck_severity')):.3f}, "
                f"potential health gain=+{safe_num(item.get('_projected_health_gain')):.3f}, "
                f"directness={item.get('_bottleneck_directness')})."
            )

        decision = decision_profile(
            str(item.get("type") or "experiment"),
            str(item.get("id") or ""),
        )
        unlock_score = compute_unlock_score(
            str(item.get("type") or "experiment"),
            str(item.get("id") or ""),
            ranked_plan,
            str(bottleneck_component) if bottleneck_component else None,
        )

        action_id = str(item.get("id") or f"PLAN-{len(actions)+1:03d}")
        readiness = execution_readiness.get(action_id, {})
        actions.append(ResearchAction(
            priority=priority,
            base_priority=base_priority,
            action_id=action_id,
            title=str(item.get("title") or "Unnamed experiment"),
            kind=str(item.get("type") or "experiment"),
            rationale=rationale,
            expected_gain=str(item.get("expected_information_gain") or "Unknown"),
            urgency="Critical" if priority >= 7 else "High" if priority >= 5 else "Medium" if priority >= 3 else "Low",
            suggested_target=suggested_target,
            done_when=str(item.get("success_criteria") or "") or None,
            bottleneck_component=str(bottleneck_component) if bottleneck_component else None,
            bottleneck_rank=int(item.get("_bottleneck_rank")) if item.get("_bottleneck_rank") else None,
            bottleneck_severity=safe_num(item.get("_bottleneck_severity"), 0.0),
            projected_health_gain=safe_num(item.get("_projected_health_gain"), 0.0),
            strategic_score=safe_num(item.get("_strategic_score"), 0.0),
            bottleneck_directness=str(
                item.get("_bottleneck_directness") or "none"
            ),
            estimated_runtime=str(decision["runtime"]),
            estimated_cost=str(decision["cost"]),
            automation_level=str(decision["automation"]),
            dependency_level=str(decision["dependency"]),
            prerequisites=list(decision["prerequisites"]),
            expected_information_gain_score=safe_num(
                decision["information_gain"], 0.0
            ),
            unlock_score=unlock_score,
            target_rules=list(readiness.get("target_rules") or []),
            execution_readiness=str(readiness.get("status") or "UNKNOWN"),
            execution_readiness_reason=(
                str(readiness.get("reason"))
                if readiness.get("reason")
                else None
            ),
            superseded_by_action_id=(
                str(readiness.get("superseded_by_action_id"))
                if readiness.get("superseded_by_action_id")
                else None
            ),
        ))

    if not actions:
        priorities.append("No unresolved experiments are currently queued")
    else:
        priorities.append("Execute the highest-priority validation-driven experiment first")

    meta_bottlenecks = meta.get("bottlenecks", {}) if isinstance(meta, dict) else {}
    primary_bottleneck = meta_bottlenecks.get("primary") if isinstance(meta_bottlenecks, dict) else None
    if isinstance(primary_bottleneck, dict) and primary_bottleneck.get("title"):
        priorities.insert(
            0,
            (
                f"Primary system bottleneck: {primary_bottleneck.get('title')} "
                f"(severity={safe_num(primary_bottleneck.get('severity')):.3f}, "
                f"potential health gain=+{safe_num(primary_bottleneck.get('max_index_gain')):.3f})"
            ),
        )

    if not integrity_ok:
        risks.append("Knowledge Base integrity is not confirmed")
        bottlenecks.append("Repair broken or duplicate knowledge links before new promotion")

    missing_mechanisms = int(safe_num(research_debt.get("rules_without_mechanisms"), 0))
    if missing_mechanisms > 0:
        bottlenecks.append(f"{missing_mechanisms} rule(s) still lack mechanism coverage")

    if testing_predictions > 0:
        strengths.append("Prediction-validation-planning loop is active")

    dependency_graph = build_dependency_graph(actions, experiment_plan)
    apply_graph_unlock_scores(actions, dependency_graph)
    if dependency_graph.get("required_edge_count", 0):
        strengths.append("Research dependency graph contains explicit prerequisite links")

    # Risk score: high when small sample, low diversity, weak evidence, disputes.
    risk = clamp(
        0.35 * (1 - replication)
        + 0.25 * (1 - diversity)
        + 0.20 * (1 - evidence_strength)
        + 0.10 * bool(disputed)
        + 0.10 * (1 - consensus_strength),
        0,
        1,
    )

    summary = (
        f"Stage: {stage}. Maturity={maturity:.2f}, rules={rules}, "
        f"principles={principle_count}, predictions={predictions_total}, "
        f"planned_experiments={len(experiment_plan)}, risk={risk:.2f}."
    )

    return ResearchDirectorState(
        generated_at=now_iso(),
        profiles=len(profiles),
        scientific_rule_ids=sorted(
            current_evidence_rules
            or {
                str(profile.get("rule") or "unknown").zfill(5)
                for profile in profiles
                if profile.get("rule") is not None
            }
        ),
        rules=rules,
        principles=principle_count,
        consensus_principles=consensus_count,
        supported_principles=supported,
        disputed_principles=disputed,
        foundational_principles=foundational,
        evidence_claims=len(evidence),
        questions=q_count,
        maturity=maturity,
        evidence_strength=evidence_strength,
        consensus_strength=consensus_strength,
        diversity=diversity,
        velocity=meta_velocity,
        efficiency=meta_efficiency,
        risk=risk,
        stage=stage,
        summary=summary,
        strengths=strengths,
        bottlenecks=bottlenecks,
        risks=risks,
        priorities=priorities,
        actions=actions,
        predictions=predictions_total,
        confirmed_predictions=confirmed_predictions,
        testing_predictions=testing_predictions,
        planned_experiments=len(experiment_plan),
        mechanism_coverage=mechanism_coverage,
        discovery_coverage=discovery_coverage,
        integrity_ok=integrity_ok,
        dependency_graph=dependency_graph,
        reference_controls=reference_controls,
        consensus_action_intake=consensus_action_intake,
        human_review_decisions=human_review_decisions,
        human_review_audit_trail=human_review_audit_trail,
        human_review_import_preview={
            "import_candidate": human_review_import_candidate,
        },
        human_review_commit_request=human_review_commit_request,
        human_review_receipt_verification={
            "receipt_lookup": human_review_receipt_lookup,
        },
        research_action_patch_state=research_action_patch_state,
        patch_application_request=patch_application_request,
        patch_application_receipt_verification={
            "receipt_lookup": patch_application_receipt_lookup,
        },
        patch_rollback_request=patch_rollback_request,
        patch_rollback_receipt_verification={
            "receipt_lookup": patch_rollback_receipt_lookup,
        },
    )

def load_director_history(root: Path) -> List[Dict[str, Any]]:
    data = load_json(root / "research_director_history.json", [])
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict) and isinstance(data.get("history"), list):
        return [x for x in data["history"] if isinstance(x, dict)]
    return []

def current_research_signature(state: ResearchDirectorState) -> Dict[str, Any]:
    """Fields that indicate actual scientific-state change, not a code rerun."""
    return {
        "rules": state.rules,
        "profiles": state.profiles,
        "principles": state.principles,
        "consensus_principles": state.consensus_principles,
        "supported_principles": state.supported_principles,
        "foundational_principles": state.foundational_principles,
        "predictions": state.predictions,
        "confirmed_predictions": state.confirmed_predictions,
        "testing_predictions": state.testing_predictions,
        "planned_experiments": state.planned_experiments,
        "mechanism_coverage": round(state.mechanism_coverage, 6),
        "discovery_coverage": round(state.discovery_coverage, 6),
        "integrity_ok": state.integrity_ok,
    }

def historical_research_signature(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rules": int(safe_num(snapshot.get("rules"), 0)),
        "profiles": int(safe_num(snapshot.get("profiles"), 0)),
        "principles": int(safe_num(snapshot.get("principles"), 0)),
        "consensus_principles": int(safe_num(snapshot.get("consensus_principles"), 0)),
        "supported_principles": int(safe_num(snapshot.get("supported_principles"), 0)),
        "foundational_principles": int(safe_num(snapshot.get("foundational_principles"), 0)),
        "predictions": int(safe_num(snapshot.get("predictions"), 0)),
        "confirmed_predictions": int(safe_num(snapshot.get("confirmed_predictions"), 0)),
        "testing_predictions": int(safe_num(snapshot.get("testing_predictions"), 0)),
        "planned_experiments": int(safe_num(snapshot.get("planned_experiments"), 0)),
        "mechanism_coverage": round(safe_num(snapshot.get("mechanism_coverage"), 0.0), 6),
        "discovery_coverage": round(safe_num(snapshot.get("discovery_coverage"), 0.0), 6),
        "integrity_ok": bool(snapshot.get("integrity_ok", False)),
    }

def apply_decision_model_to_action(
    action: ResearchAction,
    all_actions: List[ResearchAction],
) -> ResearchAction:
    decision = decision_profile(action.kind, action.action_id)
    action.estimated_runtime = str(decision["runtime"])
    action.estimated_cost = str(decision["cost"])
    action.automation_level = str(decision["automation"])
    action.dependency_level = str(decision["dependency"])
    action.prerequisites = list(decision["prerequisites"])
    action.expected_information_gain_score = safe_num(
        decision["information_gain"], 0.0
    )

    plan_stub = [{"id": item.action_id} for item in all_actions] or [{"id": action.action_id}]
    action.unlock_score = compute_unlock_score(
        action.kind,
        action.action_id,
        plan_stub,
        action.bottleneck_component,
    )

    # Trend-generated actions do not have Planner or bottleneck evidence.
    # Score them conservatively rather than assigning a fake maximum priority.
    action.strategic_score = round(
        10.0 * (
            0.40 * clamp(action.base_priority / 5.0, 0, 1)
            + 0.25 * action.expected_information_gain_score
            + 0.20 * action.unlock_score
            + 0.15 * (1.0 if action.automation_level == "full" else 0.65)
        ),
        4,
    )
    action.priority = max(1, min(10, int(round(action.strategic_score))))
    action.urgency = (
        "Critical" if action.priority >= 7
        else "High" if action.priority >= 5
        else "Medium" if action.priority >= 3
        else "Low"
    )
    return action

def sort_actions_by_decision(actions: List[ResearchAction]) -> List[ResearchAction]:
    return sorted(
        actions,
        key=lambda action: (
            action.strategic_score,
            action.bottleneck_directness == "direct",
            action.projected_health_gain,
            action.expected_information_gain_score,
            action.unlock_score,
            action.action_id,
        ),
        reverse=True,
    )

def apply_director_trends(root: Path, state: ResearchDirectorState) -> ResearchDirectorState:
    """Compare current state with previous Research Director snapshots."""
    history = load_director_history(root)
    compatible_history = [
        snapshot
        for snapshot in history
        if snapshot.get("scientific_view_schema") == SCIENTIFIC_VIEW_SCHEMA
    ]
    if not compatible_history:
        state.trend = "NEW_SCIENTIFIC_BASELINE"
        state.maturity_delta = 0.0
        state.risk_delta = 0.0
        state.rules_delta = 0
        state.consensus_delta = 0
        state.director_note = (
            "Scientific-view routing changed. This snapshot is a new "
            "comparable baseline; legacy and test snapshots were not used "
            "for trend deltas."
        )
        return state

    prev = compatible_history[-1]
    prev_maturity = safe_num(prev.get("maturity"), state.maturity)
    prev_risk = safe_num(prev.get("risk"), state.risk)
    prev_rules = int(safe_num(prev.get("rules"), state.rules))
    prev_consensus = int(safe_num(prev.get("consensus_principles"), state.consensus_principles))

    state.maturity_delta = state.maturity - prev_maturity
    state.risk_delta = state.risk - prev_risk
    state.rules_delta = state.rules - prev_rules
    state.consensus_delta = state.consensus_principles - prev_consensus

    recent = compatible_history[-5:]
    recent_maturity = [safe_num(x.get("maturity"), 0.0) for x in recent]
    maturity_gain_recent = state.maturity - (
        recent_maturity[0] if recent_maturity else state.maturity
    )

    current_signature = current_research_signature(state)
    previous_signatures = [
        historical_research_signature(snapshot)
        for snapshot in recent
        if isinstance(snapshot, dict)
    ]
    identical_state_runs = sum(
        signature == current_signature
        for signature in previous_signatures
    )

    # Technical reruns with identical scientific inputs are neutral.
    # Stagnation requires repeated snapshots AND a genuine sequence of
    # non-identical research states without meaningful gain.
    has_real_state_changes = any(
        signature != current_signature
        for signature in previous_signatures
    )
    state.stagnation = (
        len(recent) >= 4
        and has_real_state_changes
        and state.rules_delta <= 0
        and maturity_gain_recent < 0.01
    )

    if identical_state_runs >= 2 and not has_real_state_changes:
        state.trend = "TECHNICAL_RERUN"
        state.director_note = (
            "Scientific inputs are unchanged. This run is treated as a technical "
            "rerun, not research stagnation."
        )
    elif state.maturity_delta > 0.03 and state.risk_delta <= 0.02:
        state.trend = "IMPROVING"
        state.director_note = "Research maturity is increasing without a meaningful risk increase."
    elif state.maturity_delta > 0.01:
        state.trend = "SLOW_IMPROVEMENT"
        state.director_note = "Research maturity is improving, but the gain is still modest."
    elif state.risk_delta > 0.05:
        state.trend = "RISK_INCREASING"
        state.director_note = "Research risk increased. Add controls or independent replication before promotion."
    elif state.stagnation:
        state.trend = "STAGNATING"
        state.director_note = (
            "Distinct research states have accumulated without meaningful "
            "knowledge gain. Increase search diversity."
        )
    elif state.trend != "TECHNICAL_RERUN":
        state.trend = "STABLE"
        state.director_note = (
            "Research state is stable; continue collecting independent evidence."
        )

    # If history reveals stagnation, add a concrete action and risk.
    if state.stagnation:
        state.risks.append("Research progress appears stagnant across recent director snapshots")
        state.bottlenecks.append("Recent runs are not increasing maturity or independent coverage")
        diversify = ResearchAction(
            priority=0,
            base_priority=3,
            action_id="DIVERSIFY_SEARCH_SPACE",
            title="Diversify the search space",
            kind="explore",
            rationale=(
                "Research Director history shows distinct scientific states "
                "without meaningful knowledge gain."
            ),
            expected_gain="High",
            urgency="Medium",
            suggested_target=(
                "Sample distant rule families, not only local neighbours "
                "of current winners."
            ),
            done_when="maturity_delta over last 5 genuine research states >= 0.03",
        )
        diversify = apply_decision_model_to_action(
            diversify,
            state.actions + [diversify],
        )
        state.actions.append(diversify)

    return state

def append_director_history(root: Path, state: ResearchDirectorState) -> None:
    path = root / "research_director_history.json"
    history = load_director_history(root)
    snapshot = {
        "generated_at": state.generated_at,
        "stage": state.stage,
        "trend": state.trend,
        "maturity": state.maturity,
        "risk": state.risk,
        "rules": state.rules,
        "profiles": state.profiles,
        "principles": state.principles,
        "consensus_principles": state.consensus_principles,
        "supported_principles": state.supported_principles,
        "foundational_principles": state.foundational_principles,
        "evidence_strength": state.evidence_strength,
        "consensus_strength": state.consensus_strength,
        "diversity": state.diversity,
        "velocity": state.velocity,
        "efficiency": state.efficiency,
        "predictions": state.predictions,
        "confirmed_predictions": state.confirmed_predictions,
        "testing_predictions": state.testing_predictions,
        "planned_experiments": state.planned_experiments,
        "mechanism_coverage": state.mechanism_coverage,
        "discovery_coverage": state.discovery_coverage,
        "integrity_ok": state.integrity_ok,
        "maturity_delta": state.maturity_delta,
        "risk_delta": state.risk_delta,
        "rules_delta": state.rules_delta,
        "consensus_delta": state.consensus_delta,
        "stagnation": state.stagnation,
        "scientific_view_schema": SCIENTIFIC_VIEW_SCHEMA,
        "scientific_scope_signature": scope_signature(
            state.scientific_rule_ids
        ),
    }
    # Avoid duplicate snapshot if a user reruns instantly without new inputs: still keep it,
    # but cap history size to keep files tidy.
    history.append(snapshot)
    history = history[-500:]
    write_json(path, history)
