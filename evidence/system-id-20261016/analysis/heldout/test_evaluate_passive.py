"""Synthetic and frozen-source checks only; never reads physical heldout data."""
import copy
import importlib.util
import math
from pathlib import Path
import unittest
import numpy as np


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class HeldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=Path(__file__).parent
        cls.evaluator=load(cls.path/'evaluate_passive.py','heldout_evaluator')
        cls.fitter,cls.summary,cls.manifest=cls.evaluator.verify_freeze(cls.path.parent)
        synthetic=load(cls.path.parent/'test_passive_fit.py','frozen_test_generator').synthetic
        cls.train=synthetic('synthetic-train',(.35,-.4,.5,-.6,.7,-.75))
        cls.valid=synthetic('synthetic-heldout',(.42,-.55,.65,-.7))

    def test_exact_frozen_sources_verified(self):
        self.assertEqual(self.manifest['candidate_parameters'],self.summary['candidate_parameters'])

    def test_fixed_score_matches_original_validation_without_refitting(self):
        training=self.fitter.fit_passive(self.train,None)
        original=self.fitter.fit_passive(self.train,self.valid)
        unchanged=copy.deepcopy(training)
        fit=self.fitter.fit_passive
        self.fitter.fit_passive=lambda *a,**kw: (_ for _ in ()).throw(AssertionError('must not refit'))
        try:result=self.evaluator.score_frozen(self.valid,training,self.fitter)
        finally:self.fitter.fit_passive=fit
        self.assertEqual(result['validation'],original['validation'])
        self.assertEqual(result['parameters'],original['parameters'])
        self.assertEqual(training,unchanged)
        self.assertTrue(result['statistical_checks_pass'])
        self.assertIsNone(result['recommended_model'])

    def test_static_heldout_rejects_with_parameters_unchanged(self):
        training=self.fitter.fit_passive(self.train,None,model='viscous')
        t=np.arange(0,12,.004)
        quiet=[dict(run_id='quiet',episode_id='a',t_s=t.tolist(),
                    theta_rad=[math.pi+training['parameters']['angle_offset_rad']]*len(t))]
        result=self.evaluator.score_frozen(quiet,training,self.fitter)
        self.assertFalse(result['statistical_checks_pass'])
        self.assertEqual(result['parameters'],training['parameters'])
        self.assertIn('insufficient heldout angle excitation',result['reasons'])

    def test_training_identity_cannot_be_heldout(self):
        training=self.fitter.fit_passive(self.train,None)
        with self.assertRaisesRegex(ValueError,'independent'):
            self.evaluator.score_frozen(self.train,training,self.fitter)

    def test_annotations_must_be_frozen_before_scoring(self):
        with self.assertRaisesRegex(ValueError,'before scoring'):
            self.evaluator.validate_annotations({'selected_before_scoring':False})

    def test_reversed_board_clock_is_not_silently_dropped(self):
        states=np.zeros((4,13));states[:,0]=[0,4,3,8];states[:,9]=205
        with self.assertRaisesRegex(ValueError,'reversed'):
            self.evaluator.canonical_states(states)


if __name__=='__main__':unittest.main()
