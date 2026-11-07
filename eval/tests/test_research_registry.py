"""Prevent missing time from appearing as zero-cost inference in the registry."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from sync_audio_registry import measured_rtf


class RegistryTime(unittest.TestCase):
    def test_cli_processing_time_is_duration_weighted(self):
        self.assertAlmostEqual(measured_rtf({'cases': [
            {'audio_seconds': 100, 'processing_seconds': 5},
            {'audio_seconds': 200, 'processing_seconds': 25}]}), .1)

    def test_missing_case_time_uses_measured_aggregate(self):
        self.assertEqual(measured_rtf({'cases': [{'audio_seconds': 100}], 'inference_rtf': .4}), .4)
        self.assertEqual(measured_rtf({'cases': [{'audio_seconds': 100}]}), '')

    def test_legacy_units_and_audit_median(self):
        self.assertEqual(measured_rtf({'cases': [{'audio_seconds': 10, 'wall_ms': 2000}]}), .2)
        self.assertEqual(measured_rtf({'cases': [{'audio_seconds': 10, 'wall_seconds': 3}]}), .3)
        self.assertEqual(measured_rtf({'median_inference_rtf': .05}), .05)


if __name__ == '__main__':
    unittest.main()
