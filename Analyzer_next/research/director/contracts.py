"""Research Director value objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class ResearchAction:
    priority: int
    action_id: str
    title: str
    kind: str
    rationale: str
    expected_gain: str
    urgency: str
    suggested_target: Optional[str] = None
    done_when: Optional[str] = None
    bottleneck_component: Optional[str] = None
    bottleneck_rank: Optional[int] = None
    bottleneck_severity: float = 0.0
    projected_health_gain: float = 0.0
    base_priority: int = 0
    strategic_score: float = 0.0
    bottleneck_directness: str = "none"
    estimated_runtime: str = "unknown"
    estimated_cost: str = "unknown"
    automation_level: str = "unknown"
    dependency_level: str = "none"
    prerequisites: List[str] = field(default_factory=list)
    expected_information_gain_score: float = 0.0
    unlock_score: float = 0.0
    decision_model_version: str = "Decision Model v1.1"
    depends_on_actions: List[str] = field(default_factory=list)
    supporting_actions: List[str] = field(default_factory=list)
    unlocks_actions: List[str] = field(default_factory=list)
    linked_predictions: List[str] = field(default_factory=list)
    target_rules: List[str] = field(default_factory=list)
    execution_readiness: str = "UNKNOWN"
    execution_readiness_reason: Optional[str] = None
    superseded_by_action_id: Optional[str] = None
    dependency_depth: int = 0
    graph_unlock_raw: float = 0.0

@dataclass
class ResearchDirectorState:
    generated_at: str
    profiles: int = 0
    scientific_rule_ids: List[str] = field(default_factory=list)
    trend: str = "NEW"
    maturity_delta: float = 0.0
    risk_delta: float = 0.0
    rules_delta: int = 0
    consensus_delta: int = 0
    stagnation: bool = False
    director_note: str = ""
    rules: int = 0
    principles: int = 0
    consensus_principles: int = 0
    supported_principles: int = 0
    disputed_principles: int = 0
    foundational_principles: int = 0
    evidence_claims: int = 0
    questions: int = 0
    maturity: float = 0.0
    evidence_strength: float = 0.0
    consensus_strength: float = 0.0
    diversity: float = 0.0
    velocity: float = 0.0
    efficiency: float = 0.0
    risk: float = 0.0
    stage: str = "Unknown"
    summary: str = ""
    strengths: List[str] = field(default_factory=list)
    bottlenecks: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    priorities: List[str] = field(default_factory=list)
    actions: List[ResearchAction] = field(default_factory=list)
    predictions: int = 0
    confirmed_predictions: int = 0
    testing_predictions: int = 0
    planned_experiments: int = 0
    mechanism_coverage: float = 0.0
    discovery_coverage: float = 0.0
    integrity_ok: bool = False
    dependency_graph: Dict[str, Any] = field(default_factory=dict)
    reference_controls: Dict[str, Any] = field(default_factory=dict)
    consensus_action_intake: Dict[str, Any] = field(default_factory=dict)
    consensus_action_reconciliation: Dict[str, Any] = field(default_factory=dict)
    consensus_coverage_interpretation: Dict[str, Any] = field(default_factory=dict)
    coverage_aware_recommendations: Dict[str, Any] = field(default_factory=dict)
    consolidated_recommendations: Dict[str, Any] = field(default_factory=dict)
    recommendation_patch_proposals: Dict[str, Any] = field(default_factory=dict)
    patch_proposal_validation: Dict[str, Any] = field(default_factory=dict)
    patch_conflict_resolution_plan: Dict[str, Any] = field(default_factory=dict)
    human_review_queue: Dict[str, Any] = field(default_factory=dict)
    human_review_decisions: Dict[str, Any] = field(default_factory=dict)
    human_review_validation: Dict[str, Any] = field(default_factory=dict)
    human_review_audit_trail: Dict[str, Any] = field(default_factory=dict)
    human_review_decision_template: Dict[str, Any] = field(default_factory=dict)
    human_review_editing_interface: Dict[str, Any] = field(default_factory=dict)
    human_review_import_preview: Dict[str, Any] = field(default_factory=dict)
    human_review_commit_manifest: Dict[str, Any] = field(default_factory=dict)
    human_review_commit_request: Dict[str, Any] = field(default_factory=dict)
    human_review_commit_result: Dict[str, Any] = field(default_factory=dict)
    human_review_receipt_verification: Dict[str, Any] = field(default_factory=dict)
    human_review_recovery_check: Dict[str, Any] = field(default_factory=dict)
    approved_patch_application_preview: Dict[str, Any] = field(default_factory=dict)
    patch_application_manifest: Dict[str, Any] = field(default_factory=dict)
    research_action_patch_state: Dict[str, Any] = field(default_factory=dict)
    patch_application_request: Dict[str, Any] = field(default_factory=dict)
    patch_application_result: Dict[str, Any] = field(default_factory=dict)
    patch_application_receipt_verification: Dict[str, Any] = field(default_factory=dict)
    patch_rollback_readiness: Dict[str, Any] = field(default_factory=dict)
    patch_rollback_request: Dict[str, Any] = field(default_factory=dict)
    patch_rollback_result: Dict[str, Any] = field(default_factory=dict)
    patch_rollback_receipt_verification: Dict[str, Any] = field(default_factory=dict)
    patch_lifecycle_closure: Dict[str, Any] = field(default_factory=dict)
