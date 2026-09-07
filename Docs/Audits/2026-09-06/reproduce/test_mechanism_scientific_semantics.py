"""Regression for zero-valued measurements and missing Atlas context."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from Analyzer_next.adapters.mechanism.file_repository import (
    FileMechanismRepository,
    load_representative_behaviours,
)
from Analyzer_next.core.mechanism.contracts import MechanismPaths
from Analyzer_next.engines.mechanism_engine import MechanismEngine
from Analyzer_next.compatibility.legacy_analyzer.passport_analyzer import analyze_passport


class MechanismScientificSemantics(unittest.TestCase):
    def _profile(self, collapse_tick, longest_age, *, include_longest=True):
        profile = {
            "rule": "00000",
            "collapse_tick": collapse_tick,
            "final_tick": 256,
            "analyzer_category": "collapsed_world",
        }
        if include_longest:
            profile["longest_age"] = longest_age
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "profiles.json"
            path.write_text(json.dumps({"profiles": [profile]}), encoding="utf-8")
            return load_representative_behaviours(path)[0]

    def test_zero_is_measured_data(self):
        value = self._profile(0, 0)
        self.assertEqual(value["collapse"], "Yes, tick 0")
        self.assertEqual(value["lifetime"], 0)

    def test_none_and_missing_lifetime_fall_back(self):
        self.assertEqual(self._profile(None, None)["lifetime"], 256)
        self.assertEqual(self._profile(None, None, include_longest=False)["lifetime"], 256)
        self.assertEqual(self._profile(None, None)["collapse"], "No")

    def test_upstream_passport_analyzer_preserves_zero_lifetime(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "rule_00000_passport.md"
            path.write_text(
                "# Life Passport Rule 00000\n"
                "- Last alive tick: **256**\n"
                "- Longest observed age: **0**\n"
                "- Collapse tick: **0**\n",
                encoding="utf-8",
            )
            value = analyze_passport(path)
            self.assertEqual(value.longest_observed_age, 0)
            self.assertEqual(value.collapse_tick, 0)
            self.assertEqual(value.long_life_score, 0.0)
            self.assertEqual(value.classification, "Collapsed world")

    def test_missing_atlas_is_deferred_not_failed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            results = root / "Results" / "Universe_Search"
            analysis = root / "Results" / "Analysis"
            knowledge = root / "Atlas" / "Knowledge"
            results.mkdir(parents=True)
            knowledge.mkdir(parents=True)
            (results / "observer_profiles_v30.json").write_text(
                json.dumps({"profiles": [{
                    "rule": "00000",
                    "collapse_tick": 0,
                    "longest_age": 0,
                    "final_tick": 256,
                }]}),
                encoding="utf-8",
            )
            paths = MechanismPaths(
                results_root=results,
                analysis_root=analysis,
                knowledge_root=knowledge,
                world_atlas_root=root / "Atlas" / "Worlds",
                output_directory=analysis,
                aggregate_json=results / "mechanism_report.json",
            )
            result = MechanismEngine().run(paths)
            self.assertEqual(result.aggregate["rules_failed"], 0)
            self.assertEqual(result.aggregate["rules_deferred"], 1)
            self.assertEqual(
                result.aggregate["deferred"][0]["status"],
                "ATLAS_CONTEXT_UNAVAILABLE",
            )
            self.assertTrue((results / "mechanism_report.json").is_file())

    def test_corrupt_atlas_rule_remains_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            results = root / "Results" / "Universe_Search"
            analysis = root / "Results" / "Analysis"
            knowledge = root / "Atlas" / "Knowledge"
            worlds = root / "Atlas" / "Worlds" / "rule_00000_bad"
            results.mkdir(parents=True)
            knowledge.mkdir(parents=True)
            worlds.mkdir(parents=True)
            (results / "observer_profiles_v30.json").write_text(
                json.dumps({"profiles": [{"rule": "00000", "final_tick": 1}]}),
                encoding="utf-8",
            )
            (worlds / "rule.json").write_text("{not-json", encoding="utf-8")
            paths = MechanismPaths(
                results_root=results,
                analysis_root=analysis,
                knowledge_root=knowledge,
                world_atlas_root=root / "Atlas" / "Worlds",
                output_directory=analysis,
                aggregate_json=results / "mechanism_report.json",
            )
            result = MechanismEngine().run(paths)
            self.assertEqual(result.aggregate["rules_failed"], 1)
            self.assertEqual(result.aggregate["rules_deferred"], 0)


if __name__ == "__main__":
    unittest.main()
