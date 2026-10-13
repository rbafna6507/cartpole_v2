"""Passive pendulum identification; never equates emitted steps to actual motion."""
from dataclasses import replace
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares
from scipy.signal import find_peaks

from .config import RigConfig


def _load(path):
    path = Path(path)
    with path.open(newline='') as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 3:
        raise ValueError('capture needs at least three samples')
    required = ('device_elapsed_s', 'theta_rad', 'flags', 'x_m', 'v_m_s')
    try:
        arrays = {k: np.array([float(row[k]) for row in rows]) for k in required}
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('capture is missing numeric time/angle/flags/cart fields') from exc
    if not all(np.all(np.isfinite(v)) for v in arrays.values()):
        raise ValueError('capture contains nonfinite samples')
    t = arrays['device_elapsed_s']
    if np.any(np.diff(t) <= 0):
        raise ValueError('device time must be strictly increasing; remove no samples silently')
    if np.any(arrays['flags'] != arrays['flags'].astype(np.int64)):
        raise ValueError('flags must be integers')
    return arrays


def inspect_capture(path):
    d = _load(path)
    gaps = np.diff(d['device_elapsed_s'])
    theta = np.unwrap(d['theta_rad'])
    return {
        'sample_count': len(theta),
        'duration_s': float(d['device_elapsed_s'][-1] - d['device_elapsed_s'][0]),
        'median_sample_interval_s': float(np.median(gaps)),
        'max_sample_interval_s': float(np.max(gaps)),
        'gaps_over_twice_median': int(np.sum(gaps > 2.01*np.median(gaps))),
        'invalid_sensor_samples': int(np.sum((d['flags'].astype(np.int64) & 1) == 0)),
        'angle_std_rad': float(np.std(theta)),
        'angle_peak_to_peak_rad': float(np.ptp(theta)),
        'commanded_position_range_m': float(np.ptp(d['x_m'])),
        'note': 'Angle spread is a noise metric only for a stationary fixture. Hardware x is commanded_steps, not measured cart travel.'}


def _decay_window(path, release_s, cart_clamped):
    if release_s is None or not math.isfinite(release_s) or release_s < 0:
        raise ValueError('provide explicit release_s after hands leave the pendulum')
    if not cart_clamped:
        raise ValueError('passive fitting requires a physically clamped cart assertion')
    d = _load(path)
    keep = d['device_elapsed_s'] >= release_s
    if np.count_nonzero(keep) < 100:
        raise ValueError('at least 100 released samples are required')
    d = {k: v[keep] for k, v in d.items()}
    t = d['device_elapsed_s'] - d['device_elapsed_s'][0]
    if t[-1] < 3:
        raise ValueError('record at least three seconds after release')
    if np.any((d['flags'].astype(np.int64) & 1) == 0):
        raise ValueError('invalid encoder samples in fit window')
    if np.any((d['flags'].astype(np.int64) & 4) != 0):
        raise ValueError('passive fit requires disabled drivers')
    if np.ptp(d['x_m']) > .0005 or np.max(np.abs(d['v_m_s'])) > .001:
        raise ValueError('cart command changed during passive release')
    dt = np.diff(t)
    if np.median(dt) > .03 or np.max(dt) > max(.1, 5*np.median(dt)):
        raise ValueError('capture timing too sparse or gapped for identification')
    # Convert upright-zero wrapped observations to a continuous down-zero angle.
    y = np.unwrap((d['theta_rad'] - math.pi + math.pi) % (2*math.pi) - math.pi)
    if np.max(np.abs(y)) > math.radians(85):
        raise ValueError('use a passive release within 85 degrees of hanging down')
    if np.ptp(y) < math.radians(5):
        raise ValueError('insufficient pendulum excitation for identification')
    # Limit work on short/high-rate captures without sacrificing oscillation
    # resolution on long ones. Keep every initial-state sample for validation.
    stride = min(max(1, int(np.ceil(len(t)/600))),
                 max(1, int(.02/np.median(dt))))
    indices = np.unique(np.concatenate((np.flatnonzero(t <= .1),
                                        np.arange(0, len(t), stride), [len(t)-1])))
    return t[indices], y[indices]


def _predict(t, length, damping, angle0, omega0, offset=0):
    def dynamics(_, y):
        return (y[1], -9.81/length*math.sin(y[0])-damping*y[1])
    solution = solve_ivp(dynamics, (0, float(t[-1])), [angle0, omega0], t_eval=t,
                         rtol=2e-6, atol=1e-8, max_step=.03)
    if not solution.success or solution.y.shape[1] != len(t):
        raise ValueError('model integration failed')
    return solution.y[0]+offset


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fit_decay(path, *, release_s, cart_clamped=False):
    t, y = _decay_window(path, release_s, cart_clamped)
    centered = y-np.mean(y[-max(10, len(y)//10):])
    peaks, _ = find_peaks(centered, prominence=max(.003, np.ptp(y)*.03),
                         distance=max(1, int(.2/np.median(np.diff(t)))))
    if len(peaks) < 3:
        raise ValueError('need at least three resolved same-side oscillation peaks')
    period = float(np.median(np.diff(t[peaks])))
    length0 = float(np.clip(9.81*(period/(2*math.pi))**2, .03, .5))
    initial = [length0, .5, y[0], 0, 0]
    lower = [.025, 0, y[0]-.15, -5, -.15]
    upper = [.6, 5, y[0]+.15, 5, .15]
    result = least_squares(lambda p: _predict(t, *p)-y, initial,
                           bounds=(lower, upper), x_scale='jac', max_nfev=150,
                           loss='soft_l1', f_scale=.003)
    if not result.success:
        raise ValueError('fit did not converge; inspect release and sensor quality')
    prediction = _predict(t, *result.x)
    length, damping, angle0, omega0, offset = result.x
    near_bound = [i for i, (v, lo, hi) in enumerate(zip(result.x, lower, upper))
                  if min(v-lo, hi-v) < (hi-lo)*1e-4]
    # Zero damping can be a valid result. Other fitted bounds indicate a poor model/window.
    if any(i != 1 for i in near_bound):
        raise ValueError('fit reached parameter bounds; inspect window/geometry before export')
    return {
        'schema_version': 1, 'kind': 'passive_decay',
        'effective_length_m': float(length), 'damping_per_s': float(damping),
        'initial_angle_down_rad': float(angle0), 'initial_omega_rad_s': float(omega0),
        'angle_offset_rad': float(offset), 'rmse_rad': float(np.sqrt(np.mean((prediction-y)**2))),
        'duration_s': float(t[-1]), 'fit_samples': len(t), 'release_s': release_s,
        'source_path': str(Path(path).resolve()), 'source_sha256': _hash(path),
        'quality': inspect_capture(path), 'cart_clamped_asserted': True,
        'status': 'provisional_requires_separate_validation',
        'model': 'alpha_ddot = -g/L_eff*sin(alpha) - damping*alpha_dot',
        'not_identified': ['mass', 'COM', 'motor torque', 'cart friction', 'backlash',
                           'missed steps', 'actuator lag', 'dry friction'],
        'note': 'Fits effective-length ratio and equivalent viscous damping. Offset is diagnostic, not an encoder calibration. No confidence or physical safety guarantee.'}


def validate_decay(path, fit, *, release_s, cart_clamped=False):
    if _hash(path) == fit.get('source_sha256'):
        raise ValueError('validation must use a different capture, not the fitting data')
    t, y = _decay_window(path, release_s, cart_clamped)
    offset = float(fit['angle_offset_rad'])
    length, damping = float(fit['effective_length_m']), float(fit['damping_per_s'])
    # Fit ONLY release state, using the first 100 ms; physical parameters stay frozen.
    early = t <= .1
    if np.count_nonzero(early) < 3:
        raise ValueError('need three validation samples in the first 100 ms')
    initial = least_squares(lambda p: _predict(t[early], length, damping, *p, offset)-y[early],
                            [y[0]-offset, 0], bounds=([y[0]-offset-.05, -5], [y[0]-offset+.05, 5]))
    predicted = _predict(t, length, damping, *initial.x, offset)
    heldout = t > .1
    residual = predicted[heldout]-y[heldout]
    return {'schema_version': 1, 'source_path': str(Path(path).resolve()),
            'source_sha256': _hash(path), 'fit_source_sha256': fit['source_sha256'],
            'rmse_rad': float(np.sqrt(np.mean(residual**2))),
            'max_error_rad': float(np.max(np.abs(residual))),
            'evaluation_samples': int(np.sum(heldout)), 'release_s': release_s,
            'note': 'Physical parameters frozen. Initial state uses first 100 ms; metrics exclude it. Choose acceptance thresholds before physical training.'}


def export_fit(config: RigConfig, fit: dict, output, validation=None):
    path = Path(output)
    if path.exists():
        raise FileExistsError('refusing to overwrite an existing rig configuration')
    if validation is not None and validation.get('fit_source_sha256') != fit.get('source_sha256'):
        raise ValueError('validation does not belong to this fit')
    provenance = dict(config.provenance)
    provenance.update({'status': 'provisional_with_validation_metrics' if validation else 'provisional',
                       'fit': fit, 'validation': validation,
                       'note': 'Only effective length and angular damping updated; remeasure mass/COM and actuator behavior separately.'})
    updated = replace(config, effective_length_m=fit['effective_length_m'],
                      damping_per_s=fit['damping_per_s'], provenance=provenance)
    # Exclusive creation protects previous measurements and configurations.
    with path.open('x') as f:
        json.dump(updated.to_dict(), f, indent=2, allow_nan=False)
        f.write('\n')
    return updated
