import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('review', ROOT/'analysis/review_runs.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class RunReviewTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/'run.csv'
        self.path.write_text('t_ms,mode,theta,x,v,accel,energy\n'
                             '0,2,3.14,0,0,0,-1\n10,2,1.2,.01,1,6,0\n20,0,2,.01,0,0,0\n')

    def test_ack_uses_new_reply_after_transmit(self):
        events = [('rx', '= vmax 1.5'), ('tx', 'auto'), ('rx', '= vmax 2.34375'),
                  ('rx', '= amax_s 6'), ('rx', '= amax_b 6'), ('rx', '= jmax 120'),
                  ('rx', '# SWINGUP')]
        sidecar = self.path.with_name('run_events.jsonl')
        sidecar.write_text(''.join(json.dumps(dict(direction=d,text=t))+'\n' for d,t in events))
        report = review.summarize(self.path, settle_s=0)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['start_snapshots'][0]['parameters']['vmax'], 2.34375)
        self.assertEqual(report['fraction_at_speed_cap'], 0)
        first_hash = report['source_sha256'][sidecar.name]
        sidecar.write_text(sidecar.read_text()+json.dumps(dict(direction='rx',text='! fault'))+'\n')
        self.assertNotEqual(first_hash, review.summarize(self.path,settle_s=0)['source_sha256'][sidecar.name])

    def test_active_partial_reset_and_recent_logs_defer(self):
        good = self.path.read_text()
        for invalid in [good.replace('20,0,','20,2,'), good.rstrip(), good.replace('20,0,','1,0,')]:
            self.path.write_text(invalid)
            self.assertEqual(review.summarize(self.path,settle_s=0)['status'], 'deferred')
        self.path.write_text(good)
        self.assertEqual(review.summarize(self.path,now=time.time())['status'], 'deferred')

    def test_missing_parameters_do_not_invent_saturation(self):
        report = review.summarize(self.path, settle_s=0)
        self.assertNotIn('fraction_at_speed_cap', report)
        self.assertTrue(report['data_quality_notes'])


if __name__ == '__main__':
    unittest.main()
