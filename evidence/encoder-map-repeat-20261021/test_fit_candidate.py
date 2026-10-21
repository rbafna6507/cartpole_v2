"""Independent-direction fits must not disguise a failed stationary check."""
import importlib.util
from pathlib import Path
import math
import numpy as np
import pytest


def module():
    path=Path(__file__).with_name('fit_candidate.py')
    assert path.exists(), 'offline encoder candidate fitter is not implemented'
    spec=importlib.util.spec_from_file_location('encoder_candidate_fit',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def samples(offset=0.):
    q=np.linspace(-math.pi,math.pi,720,endpoint=False)
    return [dict(encoder_rad=float(x),residual_rad=float(.02+.10*np.sin(x)+offset)) for x in q]


def test_opposite_direction_cannot_change_coefficients_or_order():
    # Mixing validation rows into the fit would erase the injected 0.05rad error.
    m=module();a=m.fit_candidate(samples(),samples());b=m.fit_candidate(samples(),samples(.05))
    assert a['order']==b['order']==1
    assert b['coefficients']==pytest.approx(a['coefficients'])
    assert b['coefficients']==pytest.approx([.02,.1,0.],abs=1e-10)
    assert b['opposite_direction']['rms_deg']==pytest.approx(2.864788975654116,abs=1e-7)


def test_insufficient_angle_coverage_cannot_produce_full_circle_candidate():
    m=module();rows=samples()[:80]
    with pytest.raises(ValueError,match='coverage'):m.fit_candidate(rows,rows)


def test_wrap_boundary_and_derivative_consistency():
    m=module();beta=[.02,.10,0.]
    assert m.predict_camera_angle(math.pi,beta)==pytest.approx(-math.pi+.02)
    assert m.predict_camera_angle(-math.pi,beta)==pytest.approx(-math.pi+.02)
    assert m.slope(0.,beta)==pytest.approx(1.1)
    assert m.slope(math.pi,beta)==pytest.approx(.9)


def test_stationary_failure_is_preserved_despite_perfect_moving_fit():
    m=module();candidate=m.fit_candidate(samples(),samples())
    holds=[dict(encoder_rad=0.,camera_rad=.10,qualified=True),dict(encoder_rad=0.,camera_rad=.02,qualified=False)]
    result=m.validate_stationary(candidate,holds)
    assert candidate['opposite_direction']['rms_deg']<1e-8
    assert result['passed'] is False
    assert result['qualified_holds']==1
    assert result['max_abs_error_deg']==pytest.approx(4.583662361046586)
