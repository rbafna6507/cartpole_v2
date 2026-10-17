"""Numerical checks for the diagnostic's derivative-free input integral."""
import importlib.util
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location('diagnosis', Path(__file__).with_name('diagnose_input.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_constant_acceleration_has_analytic_weak_integral():
    assert hasattr(m, 'velocity_input_integral'), 'velocity input integral is not implemented'
    t = np.array([0., .017, .055, .111, .19, .35])
    q = np.full(t.shape, np.pi)
    v = .4 + 2.7*t
    assert abs(m.velocity_input_integral(t, q, v)-2.7*.35/30) < 1e-13


def test_velocity_offset_does_not_change_acceleration_input():
    assert hasattr(m, 'velocity_input_integral'), 'velocity input integral is not implemented'
    t = np.linspace(0, .35, 71)
    q = np.pi+.5*np.sin(8*t)
    v = np.sin(5*t)
    assert abs(m.velocity_input_integral(t,q,v+9)-m.velocity_input_integral(t,q,v)) < 1e-13


def test_irregular_linear_velocity_matches_dense_quadrature():
    assert hasattr(m, 'velocity_input_integral'), 'velocity input integral is not implemented'
    t = np.array([0., .017, .055, .111, .19, .35])
    q = 2.6 + 2*t
    v = .4 + 2.7*t
    fine = np.linspace(0,.35,100001);s=fine/.35
    expected=np.trapezoid(-2.7*np.cos(2.6+2*fine)*s*s*(1-s)**2,fine)
    assert abs(m.velocity_input_integral(t,q,v)-expected) < 1e-11
