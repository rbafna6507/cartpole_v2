"""Read-only analysis regression checks; no Rig/transport construction."""
import importlib.util
import math
from pathlib import Path
import unittest

PATH=Path(__file__).with_name('analyze_characterization.py')
SPEC=importlib.util.spec_from_file_location('analyze_characterization',PATH)
module=importlib.util.module_from_spec(SPEC)
if PATH.exists():SPEC.loader.exec_module(module)

class AnalysisTests(unittest.TestCase):
    def setUp(self):self.assertTrue(PATH.exists(),'analysis implementation missing')
    def test_offset_uses_only_stopped_training_preflight(self):
        def state(theta,t,flags=205):return dict(type='state',state=dict(theta=theta,unwrapped_us=t,flags=flags,mode=0,fault=0,x=0.,velocity=0.,acceleration=0.,omega=0.))
        records=[state(3.04,0),state(3.04,100_000),state(3.04,200_000),state(3.04,300_000),state(3.04,400_000),state(3.04,500_000),dict(type='characterization_start',state={'unwrapped_us':500_000}),state(2.5,600_000)]
        offset=module.training_hanging_offset({'records':records})
        self.assertAlmostEqual(offset['angle_offset_rad'],3.04-math.pi)
        self.assertEqual(offset['samples'],6)
        self.assertEqual(offset['source'],'training preflight only')
    def test_offset_wraps_across_pi_without_changing_equilibrium(self):
        records=[dict(type='state',state=dict(theta=q,unwrapped_us=i*100_000,flags=205,mode=0,fault=0,x=0.,velocity=0.,acceleration=0.,omega=0.)) for i,q in enumerate((math.pi-.01,-math.pi+.01)*3)]
        records.append(dict(type='characterization_start',state={'unwrapped_us':500_000}))
        self.assertAlmostEqual(module.training_hanging_offset({'records':records})['angle_offset_rad'],0.,places=12)
    def test_missing_stationary_training_window_refuses_offset(self):
        with self.assertRaises(ValueError):module.training_hanging_offset({'records':[dict(type='characterization_start',state={'unwrapped_us':0})]})
    def test_same_raw_input_cannot_be_training_and_heldout(self):
        run={'manifest':{'raw_sha256':'same'},'rows':[]}
        with self.assertRaisesRegex(ValueError,'independent'):module.fit_pair(run,run)
    def test_angle_validity_blocks_promotion_even_if_software_gates_pass(self):
        decision=module.promotion_decision([{'accepted':True,'recommended_model':{'effective_length_m':.16}}])
        self.assertFalse(decision['promoted'])
        self.assertIsNone(decision['recommended_model'])
        self.assertIn('angle',decision['reason'])
    def test_frozen_fit_configuration_is_unchanged(self):
        cfg=module.FitConfig()
        self.assertEqual((cfg.min_angle_span_rad,cfg.max_integral_nrmse,cfg.max_prediction_rmse_rad,cfg.max_prediction_p95_rad),(.15,.15,.08,.15))
        self.assertEqual(cfg.min_windows,20)
        module.verify_modules()

if __name__=='__main__':unittest.main()
