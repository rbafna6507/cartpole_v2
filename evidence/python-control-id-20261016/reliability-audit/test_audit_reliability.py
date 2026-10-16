"""Offline evidence-accounting checks; never import a rig or open serial."""
import gzip
import hashlib
import json
import unittest
from pathlib import Path

from audit_reliability import mode_intervals, stats

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]


class AuditVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(gzip.decompress((BASE / 'analysis.json.gz').read_bytes()))

    def test_balance_ends_at_return_to_swing(self):
        intervals = mode_intervals([
            dict(mode='swing', board_ns=0),
            dict(mode='balance', board_ns=3_000_000_000),
            dict(mode='swing', board_ns=4_000_000_000),
        ], 25_000_000_000)
        self.assertEqual(sum(i['duration_s'] for i in intervals if i['mode']=='balance'), 1)

    def test_missing_observations_are_not_zero_measurements(self):
        self.assertEqual(stats([]), {'n': 0})
        self.assertEqual(stats([None]), {'n': 0})
        self.assertIsNone(self.data['runs'][1]['balance_raw_theta_rms_deg'])

    def test_recorded_capture_interval(self):
        r = self.data['runs'][0]
        self.assertEqual(r['balance_seconds'], .976)
        self.assertEqual(r['longest_balance_seconds'], .976)
        self.assertEqual(r['balance_actions'], 244)
        self.assertEqual(r['action_board_interval_counts'], {'4': 6247})
        self.assertAlmostEqual(r['balance_raw_theta_rms_deg'], 19.188648122733788)
        self.assertTrue(all(3.280 <= x['t_s'] < 4.256 for x in r['selected_rows'] if x['mode']=='balance'))

    def test_native_mode_mapping(self):
        n = self.data['native']
        self.assertEqual(n['mode_mapping'], {'swing': 2, 'balance': 3})
        self.assertEqual([s['mode'] for s in n['transitions']], [2, 3])
        self.assertEqual(n['balance_count'], 5631)
        self.assertEqual(n['balance_stats']['theta']['n'], 5631)

    def test_cadence_frames_and_stop_deadline(self):
        f = self.data['runs'][1]['failure']
        self.assertEqual(f['failed_board_gap_ms'], 16)
        self.assertEqual([s['unwrapped_tick'] for s in f['intervening_received_states']],
                         [80954876, 80954880, 80954884, 80954888])
        self.assertEqual(f['first_stopped_state']['unwrapped_tick'], 80954891)
        self.assertLess(f['first_stopped_state']['unwrapped_us']*1000,
                        f['last_action']['request']['expires_at_ns'])
        self.assertEqual(f['gc_overlapping_last_action_to_failure'], [])

    def test_oracles_and_shadow_match(self):
        for r in self.data['runs']:
            self.assertEqual(r['capture_oracle_disagreements'], [])
            self.assertEqual(r['shadow_faults'], 0)
            self.assertLess(r['shadow_max_abs_request_error'], 1e-12)
            self.assertTrue(r['recorded_and_replayed_transitions_identical'])

    def test_input_and_equation_hashes(self):
        for r in self.data['runs']:
            for item in r['source_manifest']:
                path = Path(item['path'])
                if not path.is_absolute(): path = REPO / path
                content = path.read_bytes()
                if 'sha256_gzip' in item:
                    self.assertEqual(hashlib.sha256(content).hexdigest(), item['sha256_gzip'])
                    self.assertEqual(hashlib.sha256(gzip.decompress(content)).hexdigest(), item['sha256_uncompressed'])
                else:
                    self.assertEqual(hashlib.sha256(content).hexdigest(), item['sha256'])
        frozen = BASE.parent / 'capture-audit'
        for relative, expected in self.data['source_hashes'].items():
            self.assertEqual(hashlib.sha256((frozen / relative).read_bytes()).hexdigest(), expected)
        self.assertEqual(hashlib.sha256((BASE/'audit_reliability.py').read_bytes()).hexdigest(), self.data['analysis_sha256'])
        self.assertEqual(hashlib.sha256((BASE/'native-1792178943322637321-compact.json').read_bytes()).hexdigest(), self.data['native_compact_sha256'])

    def test_stale_input_shadow_is_reproducible(self):
        from timing_shadow import analyze
        actual = analyze(BASE/'native-1792178943322637321-compact.json')
        saved = json.loads((BASE/'timing-shadow.json').read_text())
        self.assertEqual(actual['results'], saved['results'])
        self.assertFalse(saved['hardware_activity'])
        self.assertEqual([r['snapshot_lag_ms'] for r in saved['results']], [0, 4, 8, 12])


if __name__ == '__main__':
    unittest.main()
