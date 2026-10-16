import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('jerk_analyze',Path(__file__).with_name('analyze.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
BASE=Path('/tmp/cartpole-retune-20261015/natural351-bandwidth-trials/natural351-bw20a-1792092993959609231')

class AnalysisTests(unittest.TestCase):
 def test_episode_duration_uses_irregular_board_time(self):
  e=a.episodes(np.array([0,.007,.026,.050]),np.array([2,3,3,2]),3,0,.050)
  self.assertEqual(len(e),1);self.assertAlmostEqual(e[0]['lower_duration_s'],.019);self.assertAlmostEqual(e[0]['upper_duration_s'],.050)
 def test_gap_splits_contiguous_episode(self):
  e=a.episodes(np.array([0,.004,.008,.100,.104,.108]),np.array([2,3,3,3,3,2]),3,0,.108)
  self.assertEqual(len(e),2);self.assertAlmostEqual(sum(x['lower_duration_s'] for x in e),.008)
 def test_cap_normalization_and_missing_camera(self):
  original=a.analyze(BASE)
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);r=json.loads((BASE/'report.json').read_text());r['parameters']['jmax']=300
   (p/'report.json').write_text(json.dumps(r));(p/'camera.json').write_text('[]')
   for f in BASE.glob('rig-*.jsonl'):(p/f.name).symlink_to(f)
   synthetic=a.analyze(p)
   self.assertEqual(synthetic['balance'],original['balance'])
   self.assertGreater(original['actuation']['balance']['observed_avg_jerk_near_cap_fraction'],.8)
   self.assertEqual(synthetic['actuation']['balance']['observed_avg_jerk_near_cap_fraction'],0)
   self.assertIsNone(synthetic['camera']['valid_fraction']);self.assertEqual(synthetic['camera']['balance_aligned']['n'],0)
   self.assertIsNone(synthetic['firmware_provenance']['hex_sha256'])
   self.assertTrue(synthetic['settled_hanging']['all_disabled_healthy'])
   self.assertAlmostEqual(synthetic['home_return']['recomputed_delta_xy_px'][0],synthetic['home_return']['reported_horizontal_delta_px'])
 def test_manifest_mismatch_is_not_silently_attributed(self):
  report=json.loads((BASE/'report.json').read_text())
  with tempfile.TemporaryDirectory() as td:
   manifest=Path(td)/'manifest.json';manifest.write_text(json.dumps({'firmware':'not-the-recorded-firmware','hashes':{'test.hex':'a'*64}}))
   with self.assertRaisesRegex(ValueError,'does not match'):a.firmware_provenance(BASE,report,manifest)
 def test_unchanged_original_native_metrics(self):
  r=a.analyze(BASE);old=json.loads(Path('/tmp/cartpole-retune-20261015/bandwidth-analysis/results.json').read_text())['trials'][0]
  for key in ['balance','rail_brake','rail_return','limits','time']:self.assertEqual(r[key],old[key])
  self.assertEqual(r['actuation']['balance']['observed_avg_jerk_near_cap_fraction'],old['actuation']['balance']['observed_avg_jerk_near150_fraction'])

if __name__=='__main__':unittest.main()
