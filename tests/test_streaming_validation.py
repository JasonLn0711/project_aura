import unittest
from scripts.check_streaming_system import endpoint_results


class DisplayGateTests(unittest.TestCase):
    def test_missing_endpoint_is_a_failure_not_dropped_from_percentile(self):
        result = endpoint_results([16000, 32000], [dict(monotonic=12, ranges=[[0, 1000]])], 10)
        self.assertEqual(result['missing'], 1)
        self.assertIsNone(result['p95_seconds'])
        self.assertFalse(result['pass_gate'])

    def test_first_display_uses_source_clock_and_requires_endpoint_coverage(self):
        result = endpoint_results([16000, 64000], [
            dict(monotonic=12, ranges=[[0, 1000]]),
            dict(monotonic=20, ranges=[[1000, 3000]]),
            dict(monotonic=22, ranges=[[3000, 4100]])], 10)
        self.assertEqual([r['display_delay_seconds'] for r in result['endpoints']], [1, 8])
        self.assertFalse(result['pass_gate'])

    def test_empty_source_cannot_certify_five_second_target(self):
        self.assertFalse(endpoint_results([], [], 0)['pass_gate'])
