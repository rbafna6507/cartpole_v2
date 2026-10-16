"""Offline physical-parameter and heldout-isolation tests; no rig imports."""
import importlib.util
import math
from pathlib import Path
import unittest
import numpy as np


def synthetic(run_id, amplitudes, *, length=.18, damping=.65, coulomb=.4, bias=-.09):
    result=[]
    for i,amplitude in enumerate(amplitudes):
        t=np.arange(0,3.004,.004)
        # Independent 0.25 ms midpoint integration, different from the fitter's
        # 1 ms RK4 forecasts. These short releases do not reach static friction.
        def acceleration(q,w):
            return -9.81/length*math.sin(q)-damping*w-coulomb*(1 if w>0 else -1 if w<0 else 0)
        q,w=amplitude,0.; values=[q]; h=.00025
        for unused in range(len(t)-1):
            for step in range(16):
                qm=q+.5*h*w;wm=w+.5*h*acceleration(q,w)
                q+=h*wm;w+=h*acceleration(qm,wm)
            values.append(q)
        result.append(dict(run_id=run_id,episode_id=str(i),t_s=t.tolist(),
                           theta_rad=(np.asarray(values)+math.pi+bias).tolist()))
    return result


class PassiveFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).with_name('passive_fit.py')
        cls.module=None
        if path.exists():
            spec=importlib.util.spec_from_file_location('passive_fit',path)
            cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
        cls.train=synthetic('training-file',(.35,-.4,.5,-.6,.7,-.75))
        cls.valid=synthetic('heldout-file',(.42,-.55,.65,-.7))

    def fitter(self):
        self.assertIsNotNone(self.module,'passive fitter has not been implemented')
        return self.module.fit_passive

    def test_independent_damped_pendulum_recovers_length_friction_and_bias(self):
        report=self.fitter()(self.train,self.valid,model='viscous_coulomb')
        p=report['parameters']
        self.assertAlmostEqual(p['effective_length_m'],.18,delta=.002)
        self.assertAlmostEqual(p['angular_damping_per_s'],.65,delta=.08)
        self.assertAlmostEqual(p['coulomb_rad_per_s2'],.4,delta=.08)
        self.assertAlmostEqual(p['angle_offset_rad'],-.09,delta=.003)
        self.assertTrue(report['statistical_checks_pass'],report['reasons'])
        self.assertIsNone(report['recommended_model'])

    def test_validation_cannot_change_training_parameters_and_bad_holdout_rejects(self):
        fit=self.fitter(); good=fit(self.train,self.valid)
        bad=synthetic('heldout-other',(.42,-.55,.65,-.7),length=.32)
        failed=fit(self.train,bad)
        self.assertEqual(good['parameters'],failed['parameters'])
        self.assertFalse(failed['statistical_checks_pass'])
        self.assertTrue(any('heldout' in x for x in failed['reasons']))

    def test_reused_recording_and_identical_measurements_are_rejected(self):
        fit=self.fitter()
        with self.assertRaisesRegex(ValueError,'independent'):
            fit(self.train,self.train)
        renamed=[dict(x,run_id='renamed') for x in self.train]
        with self.assertRaisesRegex(ValueError,'identical'):
            fit(self.train,renamed)

    def test_static_or_short_data_cannot_pass_by_small_prediction_error(self):
        fit=self.fitter()
        t=np.arange(0,12,.004).tolist()
        a=[dict(run_id='a',episode_id='0',t_s=t,theta_rad=[3.04]*len(t))]
        b=[dict(run_id='b',episode_id='0',t_s=t,theta_rad=[3.041]*len(t))]
        report=fit(a,b)
        self.assertFalse(report['statistical_checks_pass'])
        self.assertIsNone(report['recommended_model'])

    def test_time_gaps_never_create_cross_gap_weak_windows(self):
        fit=self.fitter()
        # Only 0.2 s valid fragments, each shorter than a weak window.
        t=np.concatenate([np.arange(i,i+.2,.004) for i in range(15)])
        a=[dict(run_id='gapped',episode_id='a',t_s=t.tolist(),theta_rad=(3+.3*np.sin(t*8)).tolist())]
        report=fit(a,self.valid)
        self.assertEqual(report['training']['window_count'],0)
        self.assertFalse(report['statistical_checks_pass'])

    def test_raw_camera_pixels_detect_translation_without_claiming_metric_calibration(self):
        self.fitter()
        self.assertTrue(hasattr(self.module,'camera_stationarity'),'raw camera audit has not been implemented')
        rows=[{'vision':{'t':i/80,'confidence':.9,'pivot_px':[100.+.05*(i%2),200.],
                         'bob_px':[100.+20*math.sin(i/12),250.]}} for i in range(160)]
        quiet=self.module.camera_stationarity(rows)
        self.assertTrue(quiet['pixel_stationarity_check_pass'])
        self.assertFalse(quiet['metric_stationarity_established'])
        for i,row in enumerate(rows):row['vision']['pivot_px'][0]+=i/20
        moved=self.module.camera_stationarity(rows)
        self.assertFalse(moved['pixel_stationarity_check_pass'])

    def test_passive_forecast_sticks_below_coulomb_threshold(self):
        self.fitter()
        # A=50, B=0, q=pi+.001 => |gravity acceleration|~.05 < friction .4.
        q,w=self.module.advance(math.pi+.001,0.,.001,[50.,.65,0.,.4])
        self.assertEqual(q,math.pi+.001)
        self.assertEqual(w,0.)

    def test_constant_speed_hand_motion_cannot_produce_an_infinite_length_model(self):
        fit=self.fitter();t=np.arange(0,12,1/128)
        train=[dict(run_id='hand-a',episode_id='a',t_s=t.tolist(),theta_rad=(3+t/8).tolist())]
        valid=[dict(run_id='hand-b',episode_id='b',t_s=t.tolist(),theta_rad=(3.125+t/8).tolist())]
        result=fit(train,valid,model='viscous')
        self.assertFalse(result['statistical_checks_pass'])
        self.assertIsNone(result['recommended_model'])

    def test_training_only_never_invents_heldout_scores_or_acceptance(self):
        fit=self.fitter();training_only=fit(self.train,None);full=fit(self.train,self.valid)
        self.assertEqual(training_only['parameters'],full['parameters'])
        self.assertTrue(training_only['training_checks_pass'])
        self.assertFalse(training_only['statistical_checks_pass'])
        self.assertEqual(training_only['validation'],{'status':'not provided'})
        self.assertIsNone(training_only['recommended_model'])

    def test_sparse_camera_samples_do_not_invent_coulomb_velocity(self):
        fit=self.fitter();t=np.arange(0,12,.04)
        data=[dict(run_id='camera',episode_id='a',t_s=t.tolist(),theta_rad=(3+.3*np.sin(8*t)).tolist())]
        result=fit(data,None,model='viscous_coulomb')
        self.assertFalse(result['training_checks_pass'])
        self.assertEqual(result['training']['window_count'],0)
        # The viscous weak form does not need a local derivative at all.
        viscous=fit(data,None,model='viscous')
        self.assertGreater(viscous['training']['window_count'],20)

    def test_static_heldout_cannot_validate_a_dynamic_training_model(self):
        fit=self.fitter();trained=fit(self.train,None,model='viscous')
        t=np.arange(0,12,.004)
        quiet=[dict(run_id='quiet-heldout',episode_id='a',t_s=t.tolist(),
                    theta_rad=[math.pi+trained['parameters']['angle_offset_rad']]*len(t))]
        report=fit(self.train,quiet,model='viscous')
        self.assertEqual(report['parameters'],trained['parameters'])
        self.assertFalse(report['statistical_checks_pass'])
        self.assertIn('insufficient heldout angle excitation',report['reasons'])


if __name__=='__main__':unittest.main()
