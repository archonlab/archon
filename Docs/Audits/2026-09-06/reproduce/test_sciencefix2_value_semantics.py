"""SCIENCEFIX2 regressions for zero-valued measurements and runtime portability."""
from __future__ import annotations

import csv
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from Analyzer_next.core.prediction_registry.candidates import rule_lifetime
from Analyzer_next.core.prediction_registry.database import apply_validation
from Analyzer_next.core.discovery.analysis import build_discoveries
from Analyzer_next.core.mutation.baseline import final_tick
from Analyzer_next.core.metric_independence.audit import _record_rank
from Analyzer_next.research.director.inputs import status_of_principle
from Analyzer_next.core.experiment_planner.planning import _first_present as planner_first_present
from Universe_Search.discovery_engine import _infer_topic


class ScienceFix2ValueSemantics(unittest.TestCase):
    def test_prediction_lifetime_zero_beats_atlas_fallback(self):
        kb = {"rules": {"00000": {
            "passport": {"lifetime": 0},
            "atlas": {"lifetime": 250000},
        }}}
        self.assertEqual(rule_lifetime(kb, "00000"), 0)

    def test_prediction_confidence_zero_is_not_replaced_by_label(self):
        item = {
            "id": "P-ZERO",
            "status": "Testing",
            "confidence_score": 0.0,
            "confidence": "VERY_HIGH",
            "history": [],
        }
        apply_validation(item, {"status_after": "Testing"})
        self.assertEqual(item["confidence_score"], 0.0)

    def test_discovery_passport_zero_beats_nonzero_atlas_aliases(self):
        discoveries = build_discoveries(
            "00000",
            {
                "lifetime": 0,
                "dynamic_score": 0.0,
                "breathing_score": 0.0,
                "collapse": "Yes, tick 0",
            },
            {
                "lifetime": 500000,
                "dynamic_score": 1.0,
                "breathing_score": 1.0,
                "collapse": "No",
                "emergence_score": 0.0,
                "validation_quality": 0.0,
                "research_value": 0.0,
            },
            {},
        )
        ids = {row["local_id"] for row in discoveries}
        self.assertNotIn("D1", ids)
        self.assertNotIn("D3", ids)

    def test_mutation_final_tick_preserves_zero(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "samples.csv"
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=["tick"])
                writer.writeheader()
                writer.writerow({"tick": 0})
            self.assertEqual(final_tick(path), 0)

    def test_metric_rank_zero_is_newer_than_missing_tick(self):
        zero = {"observer_state_tick": 0, "created": "", "source_file": "zero"}
        missing = {"observer_state_tick": None, "created": "", "source_file": "missing"}
        self.assertGreater(_record_rank(zero)[0], _record_rank(missing)[0])
        self.assertEqual(_record_rank(zero)[0], 0)

    def test_universe_discovery_primary_zero_is_authoritative(self):
        topic = _infer_topic({
            "civilization_score": 0.0,
            "emergence_score": 1.0,
            "knowledge_score": 0.2,
            "information_score": 0.9,
        })
        self.assertEqual(topic, "knowledge")

    def test_experiment_planner_zero_count_is_authoritative(self):
        self.assertEqual(planner_first_present(0, 17, 99), 0)
        self.assertEqual(planner_first_present({}, {"support": 3}), {})

    def test_research_director_zero_consensus_is_not_replaced_by_score(self):
        status = status_of_principle({
            "consensus": 0.0,
            "score": 0.99,
            "support": 3,
            "support_count": 50,
            "counter": 0,
            "counterexample_count": 10,
        })
        self.assertEqual(status, "PROMISING")


if __name__ == "__main__":
    unittest.main()
