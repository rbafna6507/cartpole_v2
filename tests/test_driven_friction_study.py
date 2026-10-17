"""Constrained exploratory fit mathematics; no hardware or package changes."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from cartpole_sdk.identification.fit import FitConfig,_segments,_windows
from test_identification import trial

SCRIPT=Path(__file__).resolve().parents[1]/'evidence/system-id-20261017/tools/analyze_driven_friction.py'

def tool():
 spec=importlib.util.spec_from_file_location('driven_friction_study',SCRIPT)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_constrained_solver_recovers_interior_physics_and_enforces_nonnegative_friction():
 module=tool();rng=np.random.default_rng(19);x=rng.normal(size=(120,4))
 true=np.array([54.,.8,6.,1.2]);coef,details=module.constrained_solve(x,x@true,FitConfig())
 assert coef==pytest.approx(true,abs=1e-9)
 bad=np.array([54.,-2.,6.,-3.]);coef,details=module.constrained_solve(x,x@bad,FitConfig())
 assert coef[1]>=-1e-9 and coef[3]>=-1e-9
 assert coef[1]==pytest.approx(0.,abs=1e-9) and coef[3]==pytest.approx(0.,abs=1e-9)


def test_constrained_solver_preserves_length_and_coupled_input_gain_priors():
 module=tool();rng=np.random.default_rng(21);x=rng.normal(size=(120,4))
 coef,details=module.constrained_solve(x,x@np.array([1.,10.,100.,30.]),FitConfig())
 length=9.81/coef[0];gain=coef[2]*length
 assert .05-1e-9<=length<=1.5+1e-9 and .05-1e-9<=gain<=3.+1e-9
 assert 0<=coef[1]<=5.+1e-9 and 0<=coef[3]<=20.+1e-9


def test_friction_windows_keep_original_weak_equation_columns_and_boundaries():
 module=tool();cfg=FitConfig();segments=_segments(trial('training',noise=0.,gap=True),'magnetic','commanded',cfg)
 expected_x,expected_y=_windows(segments,.03,cfg)
 x,y=module.friction_windows(segments,.03,cfg)
 assert x[:,:3]==pytest.approx(expected_x,abs=0.) and y==pytest.approx(expected_y,abs=0.)
 assert x.shape[1]==4 and len(segments)==2
 assert np.all(np.isfinite(x))


def test_zero_coulomb_rollout_matches_existing_causal_predictor():
 module=tool();from cartpole_sdk.identification.fit import _predict
 cfg=FitConfig();segments=_segments(trial('development',phase=1.1,noise=0.),'magnetic','commanded',cfg)
 coef=np.array([9.81/.32,.12,.87/.32,0.])
 expected=_predict(segments,coef[:3],.03,cfg);observed=module.predict(segments,coef,.03,cfg)
 assert observed['prediction_windows']==expected['prediction_windows']
 assert observed['prediction_samples']==expected['prediction_samples']
 assert observed['prediction_rmse_rad']==pytest.approx(expected['prediction_rmse_rad'],abs=1e-8)
