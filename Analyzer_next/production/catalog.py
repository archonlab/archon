"""Declarative production Analyzer step catalog.

This is the modular source of truth for process order, invocations, products,
inputs, optionality, cache revisions, and stage membership.  The catalog keeps
filesystem path construction at the production boundary and imports no legacy
Analyzer runtime module.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from archon_paths import (
    ANALYSIS_RESULTS_DIR,
    KNOWLEDGE_ATLAS_DIR,
    PROJECT_ROOT,
    WORLD_ATLAS_DIR,
)
from Analyzer_next.production.alias_canonicalization import (
    ALIAS_CANONICAL_PRODUCT_NAMES,
)
from Analyzer_next.production.contracts import Step, validate_step_catalog


def _p(path: Path) -> str:
    return str(path.resolve())


def build_steps(results: Path, skip_lab: bool = False) -> list[Step]:
    a=ANALYSIS_RESULTS_DIR
    telemetry_db = results / "observation_logs" / "telemetry.sqlite"
    telemetry_inputs = (
      telemetry_db,
      telemetry_db.with_name(telemetry_db.name + "-wal"),
    )
    k=KNOWLEDGE_ATLAS_DIR
    w=WORLD_ATLAS_DIR
    atlas=k/'research_atlas.json'
    profiles=results/'observer_profiles_v30.json'
    profiles_v31=results/'observer_profiles_v31.json'
    passport=a/'passport_analysis.md'
    research_questions=a/'research_questions.md'
    discovery_database=results/'discovery_database.json'
    discovery_report=results/'discovery_report.md'
    principles=a/'general_principles.json'
    evidence=a/'evidence_report.json'
    counterexamples=a/'counterexample_report.json'
    cohort_targets=a/'cohort_targets.json'
    claims=PROJECT_ROOT/'Analyzer_next/core/scientific_claims.py'
    scientific_view_module=PROJECT_ROOT/'Analyzer_next/compatibility/legacy_analyzer/scientific_view.py'
    rule_aliases=k/'duplicate_rule_aliases.json'
    passport_inputs=tuple(results.rglob('*passport*.md'))
    obs_inputs=tuple(results.rglob('*passport*.json'))
    mutation_root = results/'mutation_runs'
    mutation_out = a/'Mutations'
    mutation_analysis = mutation_out/'mutation_analysis.json'
    mutation_manifests = tuple(mutation_root.rglob('mutation_manifest.json')) if mutation_root.exists() else ()
    mutation_samples = tuple(mutation_root.rglob('*_samples.csv')) if mutation_root.exists() else ()
    mutation_metadata = tuple(
      p for p in mutation_root.rglob('*.json')
      if p.name != 'mutation_manifest.json'
    ) if mutation_root.exists() else ()
    canonical_samples = tuple(
      p for p in results.rglob('*_samples.csv')
      if mutation_root not in p.parents
    )
    lifecycle_passports = tuple(results.rglob('*passport*.json'))
    experiment_runtime_root = a/'Experiments'/'RuntimePackages'
    experiment_passports = tuple(
      experiment_runtime_root.rglob('*passport*.json')
    ) if experiment_runtime_root.exists() else ()
    morphology_samples = (*canonical_samples, *mutation_samples)
    steps=[
      Step(
       'Observer Profile v31',
       'observer_profile_v31.py',
       (_p(results), '--telemetry-db', _p(telemetry_db)),
       (
        profiles_v31,
        results/'observer_profiles_v31.md',
        profiles,
        results/'observer_profiles_v30.md',
       ),
       (*obs_inputs, *experiment_passports, *telemetry_inputs),
       stage='profiles',
       revision='scientific-provenance-v1',
      ),
      Step(
       'Experiment Analyzer v1',
       'experiment_analyzer.py',
       (
        _p(results),
        '--telemetry-db', _p(telemetry_db),
        '--profiles', _p(profiles_v31),
        '--out-dir', _p(a/'Experiments'),
       ),
       (
        a/'Experiments'/'experiment_analysis.json',
        a/'Experiments'/'experiment_analysis.md',
        a/'Experiments'/'experiment_knowledge.json',
        a/'Experiments'/'experiment_knowledge.md',
        a/'Experiments'/'experiment_knowledge_integrity.json',
       ),
       (
        *telemetry_inputs,
        profiles_v31,
       ),
       optional=True,
       stage='profiles',
       revision='experiment-analysis-v2-knowledge-contract'
      ),
      Step(
       'Passport Analyzer',
       'passport_analyzer.py',
       (
        _p(results),
        '--out',_p(passport),
        '--profiles',_p(profiles_v31),
       ),
       (passport,),
       (*passport_inputs, profiles_v31, scientific_view_module),
       stage='profiles',
       revision='scientific-view-v1',
      ),
      Step('Question Tracker','question_tracker.py',(_p(passport),'--out',_p(research_questions)),(research_questions,),(passport,),stage='profiles'),
      Step(
       'Discovery Engine',
       'discovery_engine.py',
       (_p(results),),
       (discovery_database, discovery_report),
       (passport, research_questions),
       optional=True,
       stage='discovery',
      ),
      Step(
       'Mutation Analyzer',
       'mutation_analyzer.py',
       (
        _p(results),
        '--mutation-root', _p(mutation_root),
        '--out-dir', _p(mutation_out),
        '--allow-missing-root',
       ),
       (
        mutation_out/'mutation_analysis.json',
        mutation_out/'mutation_analysis.md',
        mutation_out/'required_controls.json',
        mutation_out/'required_controls.md',
       ),
       (
        *mutation_manifests,
        *mutation_metadata,
        *mutation_samples,
        *canonical_samples,
        *lifecycle_passports,
       ),
       optional=True,
       heavy=True,
       stage='mutation'
      ),
    ]
    if not skip_lab:
      steps += [
       Step(
        'Morphology Analyzer',
        'morphology_analyzer.py',
        (_p(results),),
        (
         results/'morphology_report.json',
         results/'morphology_static_distance_matrix.json',
         results/'morphology_dynamic_distance_matrix.json',
        results/'morphology_behaviour_distance_matrix.json',
        results/'morphology_distance_matrix.json',
        results/'morphology_distance_matrix.csv',
        results/'similar_worlds.json',
        results/'morphology_report.md',
        results/'morphology_comparison.md',
        results/'morphology_trajectory_report.json',
        results/'morphology_trajectory_report.md',
        results/'morphology_behaviour_report.json',
        results/'morphology_behaviour_report.md',
        ),
        morphology_samples,
        True,True,'morphology'
       ),
       Step(
        'Morphological Epoch Detector',
        'morphological_epoch_detector.py',
        (_p(results),),
        (
         results/'morphological_epoch_report.json',
         results/'morphological_epoch_report.md',
         results/'morphological_epochs.json',
         results/'morphological_epochs.md',
        ),
        (*morphology_samples, results/'morphology_report.json'),
        True,True,'morphology'
       ),
       Step(
        'Morphological Event Detector',
        'morphological_event_detector.py',
        (_p(results),),
        (
         results/'morphological_event_report.json',
         results/'morphological_event_report.md',
         results/'morphological_events.json',
         results/'morphological_events.md',
        ),
        (*morphology_samples, results/'morphological_epochs.json'),
        True,True,'morphology'
       ),
       Step(
        'Morphological Event Fusion',
        'morphological_event_fusion_engine.py',
        (_p(results),),
        (
         results/'morphological_event_fusion_report.json',
         results/'morphological_event_fusion_report.md',
         results/'morphological_fused_events.json',
         results/'morphological_fused_events.md',
        ),
        (results/'morphological_events.json',),
        True,True,'morphology'
       ),
       Step(
        'Morphological Evolution Engine',
        'morphological_evolution_engine.py',
        (_p(results),),
        (
         results/'morphological_evolution_report.json',
         results/'morphological_evolution_report.md',
         results/'morphological_life_cycles.json',
         results/'morphological_life_cycles.md',
        ),
        (*morphology_samples, results/'morphological_fused_events.json'),
        True,True,'morphology'
       ),
      Step(
       'Mechanism Engine',
       'mechanism_engine.py',
       (_p(results),),
       (
        *tuple(ANALYSIS_RESULTS_DIR.glob('mechanism_report_rule_*.md')),
        results/'mechanism_report.json',
       ),
       (passport, profiles, rule_aliases, w),
       True,
       True,
       'mechanism'
       ),
       Step(
        'Causal Graph Builder',
        'causal_graph_builder.py',
        (_p(results),),
        (
         results/'causal_graph.json',
         results/'causal_graph.md',
         results/'causal_report.json',
         results/'causal_report.md',
         results/'causal_motifs.json',
         results/'causal_motifs.md',
         results/'causal_mechanisms.json',
         results/'causal_mechanisms.md',
        ),
        (results/'morphological_fused_events.json',),
        True,
        True,
        'mechanism'
       ),
       Step(
        'Atomic Mechanism Registry',
        'causal_mechanism_registry.py',
        (_p(results),),
        (
         results/'mechanism_registry.json',
         results/'mechanism_registry.md',
         results/'composition_registry.json',
         results/'composition_registry.md',
         results/'rule_mechanism_map.json',
         results/'rule_mechanism_map.md',
         results/'causal_mechanism_report.json',
         results/'causal_mechanism_report.md',
        ),
        (
         results/'causal_mechanisms.json',
         results/'causal_motifs.json',
         results/'causal_graph.json',
        ),
        True,
        True,
        'mechanism'
       ),
       Step(
        'Composition Template Builder',
        'composition_template_builder.py',
        (_p(results),),
        (
         results/'composition_templates.json',
         results/'composition_templates.md',
         results/'composition_instances.json',
         results/'composition_instances.md',
         results/'template_rule_map.json',
         results/'template_rule_map.md',
         results/'template_report.json',
         results/'template_report.md',
        ),
        (
         results/'mechanism_registry.json',
         results/'composition_registry.json',
         results/'rule_mechanism_map.json',
        ),
        True,
        True,
        'mechanism'
       ),
       Step(
        'Mechanism Evolution Graph',
        'mechanism_evolution_graph.py',
        (_p(results),),
        (
         results/'mechanism_evolution_graph.json',
         results/'mechanism_evolution_graph.md',
         results/'mechanism_evolution_report.json',
         results/'mechanism_evolution_report.md',
         results/'rule_evolution_paths.json',
         results/'rule_evolution_paths.md',
        ),
        (
         results/'mechanism_registry.json',
         results/'composition_templates.json',
         results/'composition_instances.json',
         results/'template_rule_map.json',
        ),
        True,
        True,
        'mechanism'
       ),
       Step(
        'Mechanism Timeline Builder',
        'mechanism_timeline_builder.py',
        (_p(results),),
        (
         results/'mechanism_timeline.json',
         results/'mechanism_timeline.md',
         results/'mechanism_events.csv',
         results/'mechanism_transitions.json',
         results/'mechanism_transitions.md',
         results/'mechanism_timeline_report.json',
         results/'mechanism_timeline_report.md',
        ),
        (
         results/'morphological_fused_events.json',
         results/'mechanism_registry.json',
         results/'composition_templates.json',
         results/'composition_instances.json',
         results/'composition_registry.json',
         results/'causal_motifs.json',
         results/'causal_mechanisms.json',
        ),
        True,
        True,
        'mechanism'
       ),
       Step(
        'Timeline Compression Engine',
        'timeline_compression_engine.py',
        (_p(results),),
        (
         results/'compressed_timeline.json',
         results/'compressed_timeline.md',
         results/'compressed_transitions.json',
         results/'compressed_transitions.md',
         results/'timeline_segments.json',
         results/'timeline_segments.md',
         results/'timeline_compression_report.json',
         results/'timeline_compression_report.md',
        ),
        (results/'mechanism_timeline.json',),
        True,
        True,
        'mechanism'
       ),
      ]
    steps += [
      Step(
       'Reference Control Registry',
       'reference_control_registry.py',
       (
        _p(results),
        '--out', _p(k/'reference_control_registry.json'),
        '--md-out', _p(k/'reference_control_registry.md'),
       ),
       (
        k/'reference_control_registry.json',
        k/'reference_control_registry.md',
       ),
       (
        profiles,
        results/'morphology_report.json',
       ),
       stage='science'
      ),
      Step(
       'Atlas Engine',
       'atlas_engine.py',
       (_p(results),'--atlas',_p(atlas)),
       (atlas,k/'research_atlas.md'),
       (
        profiles,
        profiles_v31,
        results/'discovery_report.md',
        a/'research_questions.md',
        scientific_view_module,
       ),
       stage='science'
      ),
      Step(
       'Metric Independence Audit',
       'metric_independence_audit.py',
       (
        _p(profiles_v31),
        '--out',_p(a/'Integrity'/'metric_independence_audit.json'),
        '--md-out',_p(a/'Integrity'/'metric_independence_audit.md'),
       ),
       (
        a/'Integrity'/'metric_independence_audit.json',
        a/'Integrity'/'metric_independence_audit.md',
       ),
       (
        profiles_v31,
        PROJECT_ROOT/'Analyzer_next/cli/metric_independence_audit.py',
       ),
       stage='science',
       revision='know-feedback-independence-v1',
      ),
      Step(
       'Evidence Engine',
       'evidence_engine.py',
       (
        _p(results),
        '--root',_p(a),
        '--json-out',_p(evidence),
        '--md-out',_p(a/'evidence_report.md'),
        '--mutations',_p(mutation_analysis),
       ),
       (evidence,a/'evidence_report.md'),
       (
        profiles,
        claims,
        mutation_analysis,
        a/'Experiments'/'experiment_knowledge.json',
        a/'Experiments'/'experiment_knowledge_integrity.json',
        a/'Integrity'/'metric_independence_audit.json',
       ),
       stage='science'
      ),
      Step(
       'Counterexample Engine',
       'counterexample_engine.py',
       (_p(results),'--root',_p(a)),
       (
        counterexamples,
        a/'counterexample_report.md',
        a/'counterexample_targets.json',
       ),
       (profiles,claims),
       stage='science'
      ),
      Step(
       'Cohort Builder',
       'cohort_builder.py',
       (
        _p(results),
        '--root',_p(a),
        '--atlas',_p(atlas),
        '--similar',_p(results/'similar_worlds.json'),
        '--behaviour-matrix',_p(results/'morphology_behaviour_distance_matrix.json'),
        '--dynamic-matrix',_p(results/'morphology_dynamic_distance_matrix.json'),
        '--template-map',_p(results/'template_rule_map.json'),
       ),
       (
        a/'cohort_report.json',
        a/'cohort_report.md',
        a/'cohort_targets.json',
       ),
       (
        profiles,
        claims,
        counterexamples,
        atlas,
        results/'similar_worlds.json',
        results/'morphology_behaviour_distance_matrix.json',
        results/'morphology_dynamic_distance_matrix.json',
        results/'template_rule_map.json',
       ),
       stage='science'
      ),
      Step(
       'General Principle Engine',
       'general_principle_engine.py',
       (
        _p(atlas),
        '--results',_p(results),
        '--results',_p(a),
        '--out',_p(a/'general_principles.md'),
        '--evidence',_p(evidence),
        '--counterexamples',_p(counterexamples),
       ),
       (a/'general_principles.md',principles),
       (
        atlas,
        evidence,
        counterexamples,
        claims,
        scientific_view_module,
        *tuple(a.glob('mechanism_report_rule_*.md')),
       ),
       stage='science'
      ),
      Step(
       'Theory Engine',
       'theory_engine.py',
       (
        _p(atlas),
        '--out',_p(a/'theory_report.md'),
        '--principles',_p(principles),
       ),
       (a/'theory_report.md',),
       (
        atlas,
        principles,
        claims,
       ),
       stage='science'
      ),
      Step(
       'Consensus Engine',
       'consensus_engine.py',
       (
        _p(results),
        '--root',_p(a),
        '--evidence',_p(evidence),
        '--counterexamples',_p(counterexamples),
        '--db',_p(k/'consensus_database.json'),
        '--md',_p(k/'consensus_database.md'),
        '--report-json',_p(a/'consensus_report.json'),
        '--report-md',_p(a/'consensus_report.md'),
       ),
       (
        a/'consensus_report.json',
        a/'consensus_report.md',
        k/'consensus_database.json',
        k/'consensus_database.md',
       ),
       (
        evidence,
        counterexamples,
        profiles,
        profiles_v31,
        claims,
        scientific_view_module,
       ),
       stage='science'
      ),
      Step(
       'Prediction Engine',
       'prediction_engine.py',
       (_p(atlas),'--principles',_p(principles),'--out',_p(a/'predictions.md')),
       (
        a/'predictions.json',
        a/'predictions.md',
        k/'prediction_database.json',
        k/'prediction_database.md',
       ),
       (atlas,principles),
       True,
       stage='prediction'
      ),
      Step('Prediction Validation Engine','validation_engine.py',(_p(atlas),'--predictions',_p(a/'predictions.json'),'--out',_p(a/'validation_report.md')),(a/'validation_report.md',a/'validation_report.json'),(atlas,a/'predictions.json'),True,stage='prediction'),
      Step(
       'Notebook Engine',
       'notebook_engine.py',
       (_p(results),'--analysis-root',_p(a)),
       (results/'ResearchNotebook/notebook_manifest.json',),
       (
        passport,
        a/'research_questions.md',
        results/'discovery_report.md',
        a/'general_principles.md',
        a/'predictions.md',
        *tuple(a.glob('mechanism_report_rule_*.md')),
       ),
       optional=True,
       stage='notebook'
      ),
      Step(
       'Knowledge Base Sync',
       'knowledge_base_engine.py',
       (
        _p(results),
        '--atlas', _p(atlas),
        '--analysis-root', _p(a),
        '--knowledge-root', _p(k),
        '--out', _p(k/'knowledge_base.json'),
       ),
       (
        k/'knowledge_base.json',
        k/'knowledge_base.md',
        k/'knowledge_base_integrity.json',
       ),
       (
        atlas,
        principles,
        passport,
        results/'discovery_report.md',
        *tuple(a.glob('mechanism_report_rule_*.md')),
        *tuple((results/'ResearchNotebook').glob('experiment_*.md')),
        results/'ResearchNotebook/notebook_manifest.json',
        a/'predictions.json',
        a/'validation_report.json',
        k/'prediction_database.json',
        rule_aliases,
       ),
       optional=True,
       stage='prediction'
      ),
      Step(
       'Experiment Planner',
       'experiment_planner_engine.py',
       (
        _p(k/'knowledge_base.json'),
        '--out',_p(a/'experiment_plan.md'),
        '--validation',_p(a/'validation_report.json'),
        '--predictions',_p(a/'predictions.json'),
        '--cohort-targets',_p(cohort_targets),
        '--consensus',_p(a/'consensus_report.json'),
        '--evidence',_p(evidence),
        '--metric-audit',_p(a/'Integrity'/'metric_independence_audit.json'),
       ),
       (
        a/'experiment_plan.md',
        a/'experiment_plan.json',
       ),
       (
        k/'knowledge_base.json',
        a/'validation_report.json',
        a/'predictions.json',
        cohort_targets,
        a/'consensus_report.json',
        evidence,
        a/'Integrity'/'metric_independence_audit.json',
       ),
       True,
       stage='prediction'
      ),
      Step(
       'Research Notebook Index',
       'research_notebook_index.py',
       (_p(results),),
       (results/'ResearchNotebook/index.md',),
       (results/'ResearchNotebook',),
       optional=True,
       stage='notebook'
      ),
      Step(
       'Meta Science Engine',
       'meta_science_engine.py',
       (
        _p(results),
        '--root',_p(a),
        '--knowledge-root',_p(k),
        '--report-json',_p(a/'meta_science_report.json'),
        '--report-md',_p(a/'meta_science_report.md'),
        '--history',_p(k/'meta_science_history.json'),
       ),
       (
        a/'meta_science_report.json',
        a/'meta_science_report.md',
        k/'meta_science_history.json',
       ),
       (
        profiles,
        profiles_v31,
        a/'consensus_report.json',
        k/'consensus_database.json',
        evidence,
        principles,
        atlas,
        a/'theory_report.md',
        k/'knowledge_base.json',
        k/'knowledge_base_integrity.json',
        k/'prediction_database.json',
        a/'validation_report.json',
        a/'experiment_plan.json',
        k/'reference_control_registry.json',
        scientific_view_module,
       ),
       stage='meta',
       revision='complete-scientific-inputs-v1',
      ),
      Step(
       'Research Director',
       'research_director.py',
       (
        _p(results),
        '--root',_p(a),
        '--knowledge-root',_p(k),
       ),
       (
        a/'research_director_report.md',
        a/'research_director_report.json',
        a/'next_research_actions.json',
        a/'research_dependency_graph.json',
       ),
       (
        profiles,
        profiles_v31,
        a/'research_questions.md',
        a/'meta_science_report.json',
        k/'meta_science_history.json',
        a/'consensus_report.json',
        evidence,
        principles,
        k/'knowledge_base.json',
        a/'experiment_plan.json',
        k/'prediction_database.json',
        k/'reference_control_registry.json',
        scientific_view_module,
       ),
       stage='meta',
       revision='complete-scientific-inputs-v1',
      ),
      Step(
       'Scientific View Integrity',
       'scientific_view_integrity.py',
       (
        _p(results),
        '--analysis-root',_p(a),
        '--knowledge-root',_p(k),
        '--out',_p(a/'Integrity'/'scientific_view_integrity.json'),
       ),
       (a/'Integrity'/'scientific_view_integrity.json',),
       (
        profiles_v31,
        evidence,
        atlas,
        principles,
        a/'consensus_report.json',
        a/'meta_science_report.json',
        a/'research_director_report.json',
        scientific_view_module,
       ),
       stage='meta',
       revision='scientific-view-invariant-v1',
      ),
      Step(
       'Alias Integrity Audit',
       'alias_integrity_audit.py',
       (
        '--project-root', _p(PROJECT_ROOT),
        '--world-atlas-root', _p(w),
        '--knowledge-root', _p(k),
        '--analysis-root', _p(a),
        '--no-repair',
       ),
       (a/'Integrity'/'alias_integrity_report.json',),
       (
        w,
        k/'duplicate_rule_aliases.json',
        k/'knowledge_base.json',
        atlas,
        a/'experiment_plan.json',
        a/'research_director_report.json',
       ),
       optional=False,
       stage='meta',
       revision='audit-only-v2'
      ),
    ]
    alias_product_paths = {
        output.resolve()
        for step in steps
        for output in step.outputs
        if output.name in ALIAS_CANONICAL_PRODUCT_NAMES
    }
    catalog = [
        replace(step, inputs=(*step.inputs, rule_aliases))
        if any(output.resolve() in alias_product_paths for output in step.outputs)
        and rule_aliases not in step.inputs
        else step
        for step in steps
    ]
    validate_step_catalog(catalog)
    return catalog

# ARCHON RELEASE2.4 source-proven relocated compatibility dependencies.
_ARCHON_RELEASE2_RELOCATED_COMPATIBILITY_FILES = (
    'Analyzer_next/compatibility/legacy_analyzer/passport_analyzer.py',
    'Analyzer_next/compatibility/legacy_analyzer/question_tracker.py',
    'Analyzer_next/compatibility/legacy_analyzer/scientific_view.py',
)
