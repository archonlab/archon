"""Audit regression: zero is measured data, not a missing observation.

Run from the release root:
python3 -B Docs/Audits/2026-09-06/reproduce/test_mechanism_zero_values.py
The current audited release intentionally fails two assertions.
"""
from pathlib import Path
import sys
import tempfile
import json
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from Analyzer_next.adapters.mechanism.file_repository import load_representative_behaviours


class ZeroMeasurements(unittest.TestCase):
    def convert(self, collapse_tick, longest_age):
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw) / 'profiles.json'
            p.write_text(json.dumps({'profiles': [{'rule': '00000', 'collapse_tick': collapse_tick,
                'longest_age': longest_age, 'final_tick': 256, 'analyzer_category': 'collapsed_world'}]}))
            return load_representative_behaviours(p)[0]

    def test_collapse_at_zero_is_preserved(self):
        self.assertEqual(self.convert(0, 0)['collapse'], 'Yes, tick 0')

    def test_zero_lifetime_is_preserved(self):
        self.assertEqual(self.convert(0, 0)['lifetime'], 0)

    def test_positive_measurements_control(self):
        value = self.convert(25, 20)
        self.assertEqual(value['collapse'], 'Yes, tick 25')
        self.assertEqual(value['lifetime'], 20)


if __name__ == '__main__':
    unittest.main()
