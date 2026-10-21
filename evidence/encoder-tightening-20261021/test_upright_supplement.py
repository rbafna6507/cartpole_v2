"""Known-angle contrasts and genuinely frozen model checks."""
import importlib.util
from pathlib import Path
import numpy as np


def module():
    path=Path(__file__).with_name('analyze_upright.py')
    spec=importlib.util.spec_from_file_location('upright_analysis',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def test_upright_anchor_contrast_handles_downward_branch_cut():
    m=module()
    result=m.anchor_contrast(.02,-.01,np.pi-.15,np.pi+.02)
    assert abs(result['camera_minus_encoder_separation_rad']-.2)<1e-10
    # A shared constant shift of either sensor cancels from the contrast.
    shifted=m.anchor_contrast(.32,.49,np.pi+.15,np.pi+.52)
    assert abs(shifted['camera_minus_encoder_separation_rad']-.2)<1e-10


def test_model_coefficients_are_fit_only_on_first_trial():
    m=module()
    q=np.linspace(-np.pi,np.pi,200,endpoint=False)
    def rows(offset):
        return [dict(analysis_angle_rad=float(x),encoder_rate_rad_s=float(2*np.cos(3*x)),
                     analysis_residual_rad=float(.03+.08*np.sin(2*x)+offset)) for x in q]
    result=m.fit_models([('training',rows(0)),('heldout',rows(.1))])
    shape=result['angle_shape']
    assert shape['training_trial']=='training'
    assert abs(shape['coefficients'][3]-.08)<1e-10
    assert shape['evaluation'][0]['rms_deg']<1e-8
    assert abs(shape['evaluation'][1]['rms_deg']-np.degrees(.1))<1e-8
