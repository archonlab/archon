"""Scientific Ontology adapter for mutation lifecycle reconciliation."""
from __future__ import annotations

from typing import Any, Mapping

from Scientific_Ontology.lifecycle_reconciliation import reconcile_lifecycle_contract
from Scientific_Ontology.perturbation_lifecycle_reconciliation import reconcile_perturbation_lifecycle


class ScientificOntologyLifecycleAdapter:
    def reconcile_contract(
        self,
        lifecycle_summary: Mapping[str, Any] | None,
        observer_state: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return reconcile_lifecycle_contract(lifecycle_summary, observer_state)

    def reconcile_perturbation(
        self,
        baseline_lifecycle: Mapping[str, Any],
        mutant_lifecycle: Mapping[str, Any],
        structural_extinction: Mapping[str, Any],
        interpretation: Mapping[str, Any],
    ) -> dict[str, Any]:
        return reconcile_perturbation_lifecycle(
            baseline_lifecycle,
            mutant_lifecycle,
            structural_extinction,
            interpretation,
        )

