#!/usr/bin/env python3
"""Reproduce the October 21 repeat-rotation encoder model and its failed checks.

This is offline analysis. It never opens a device, modifies a calibration, or
qualifies a model for control. The camera measures image geometry, not certified
physical vertical. Raw observations and held-out checks remain separate.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAMES = {
    'rotation03': 'manual-map-after-tightening-03',
    'upright04': 'manual-map-upright-verification-04',
    'contact05': 'manual-map-upright-contact-05',
    'freefall06': 'manual-map-freefall-06',
}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def predict(q, model):
    return fit.wrap(np.asarray(q) + fit.basis(q, model['order']) @ model['coefficients'])


def compact_hold(h, model, origin):
    native = h['native_encoder_angle_rad']
    camera = h['camera_image_angle_rad']
    error = None if native is None or camera is None else float(np.degrees(
        fit.wrap(camera['median'] - fit.predict_camera_angle(native, model['coefficients']))))
    return dict(start_s=h['start_s'] - origin, duration_s=h['duration_s'],
                qualified=h['stationary_comparison_qualified'],
                native_count_median=None if h['native_info_counts'] is None else h['native_info_counts']['median'],
                encoder_deg=None if native is None else math.degrees(native),
                image_deg=None if camera is None else math.degrees(camera['median']),
                frozen_map_error_deg=error)


def plot_results(trials, pairs, holds, candidate, output):
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'cartpole-map-mpl'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout='constrained')
    moving = pairs['rotation03']
    for direction, color, label in [(1, '#2477b3', 'First direction: fit'), (-1, '#c77331', 'Opposite direction: held out')]:
        rows = [r for r in moving if r['slow_motion_fit_eligible'] and r['direction'] == direction]
        axes[0, 0].scatter(np.degrees([r['encoder_rad'] for r in rows]),
                           np.degrees([r['residual_rad'] for r in rows]), s=5, alpha=.4, color=color, label=label)
    grid = np.linspace(-math.pi, math.pi, 721)
    axes[0, 0].plot(np.degrees(grid), np.degrees(fit.basis(grid, candidate['order']) @ candidate['coefficients']), color='black', lw=1.5, label='Frozen order-4 curve')
    axes[0, 0].set(xlabel='Raw encoder angle relative to saved reference (deg)', ylabel='Image angle − raw encoder (deg)', title='Full-circle moving observations')
    axes[0, 0].legend(fontsize=8)

    for key, color in [('upright04', '#a92b36'), ('contact05', '#7445aa'), ('freefall06', '#247e62')]:
        qualified = [h for h in holds[key] if h['qualified'] and abs(h['encoder_deg']) < 10]
        axes[0, 1].scatter([h['encoder_deg'] for h in qualified], [h['image_deg'] for h in qualified], color=color, label=key, s=35)
    grid = np.radians(np.linspace(-3, 3, 201))
    axes[0, 1].plot(np.degrees(grid), np.degrees(predict(grid, candidate)), color='black', label='Frozen moving-model prediction')
    axes[0, 1].set(xlabel='Raw encoder angle (deg)', ylabel='Image angle (deg)', title='Independent upright holds reject the curve')
    axes[0, 1].legend(fontsize=8)

    rows = pairs['contact05']
    origin = trials['contact05']['host'][0]
    times = np.array([r['host_s'] - origin for r in rows])
    q = np.array([r['encoder_rad'] for r in rows]); camera = np.array([r['camera_rad'] for r in rows])
    initial = times < 40
    dq = fit.wrap(q - np.median(q[initial])); dc = fit.wrap(camera - np.median(camera[initial]))
    axes[1, 0].scatter(times, np.degrees(dq), s=2, label='Encoder change')
    axes[1, 0].scatter(times, np.degrees(dc), s=2, label='Image-angle change')
    axes[1, 0].set(xlabel='Contact05 elapsed time (s)', ylabel='Change from initial upright pose (deg)', title='Most contact-associated change is visible pole motion')
    axes[1, 0].legend(fontsize=8)

    rows = pairs['freefall06']; origin = trials['freefall06']['host'][0]
    times = np.array([r['host_s'] - origin for r in rows]); q = np.array([r['encoder_rad'] for r in rows]); camera = np.array([r['camera_rad'] for r in rows])
    axes[1, 1].scatter(times, np.degrees(fit.wrap(camera - q)), s=2, label='Raw disagreement')
    axes[1, 1].scatter(times, np.degrees(fit.wrap(camera - predict(q, candidate))), s=2, label='Frozen-map disagreement')
    axes[1, 1].set(xlabel='Freefall06 elapsed time (s)', ylabel='Image angle − estimate (deg)', title='Free motion: timing and state dependence unresolved', ylim=(-30, 30))
    axes[1, 1].legend(fontsize=8)
    for axis in axes.flat:
        axis.grid(alpha=.2)
    fig.suptitle('Encoder calibration candidate: good sweep fit, failed independent validation', fontsize=14)
    fig.savefig(output / 'calibration-validation.png', dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True, layout='constrained')
    for values, label in [(q, 'Raw encoder'), (camera, 'Independent image geometry'), (predict(q, candidate), 'Frozen rotation model')]:
        axes[0].scatter(times, np.degrees(values), s=2, label=label)
    axes[0].set_ylabel('Wrapped angle (deg)'); axes[0].legend(fontsize=8)
    axes[1].scatter(times, [r['encoder_rate_rad_s'] for r in rows], s=2)
    axes[1].set_ylabel('Firmware angular rate (rad/s)')
    axes[2].scatter(times, np.degrees(fit.wrap(camera - q)), s=2, label='Raw disagreement')
    axes[2].scatter(times, np.degrees(fit.wrap(camera - predict(q, candidate))), s=2, label='Mapped disagreement')
    axes[2].set(ylabel='Image angle − estimate (deg)', xlabel='Seconds from first telemetry', ylim=(-30, 30))
    axes[2].legend(fontsize=8)
    for axis in axes:
        axis.grid(alpha=.2)
        axis.axvspan(44, 48.5, color='#c86e30', alpha=.12)
    fig.suptitle('Passive freefall06: accidental first drop shaded; no model refit', fontsize=14)
    fig.savefig(output / 'freefall-observations.png', dpi=160)
    plt.close(fig)


def main(argv=None):
    global fit
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, required=True, help='Directory containing the four named run directories')
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing directories are rejected')
    parser.add_argument('--lag-from', type=Path, default=ROOT / 'evidence/encoder-tightening-20261021/analysis-reference520/report.json')
    args = parser.parse_args(argv)
    manual = module('repeat_manual', ROOT / 'evidence/encoder-tightening-20261021/analyze_manual_map.py')
    fit = module('repeat_fit', HERE / 'fit_candidate.py')
    base = manual.base
    lag = json.loads(args.lag_from.read_text())['frozen_lag']['lag_s']
    trials = {key: base.load_trial(args.raw_root / name) for key, name in NAMES.items()}
    refs = {tr['reference'] for tr in trials.values()}
    if len(refs) != 1 or None in refs:
        raise ValueError('all passive recordings must have the same fixed reference')
    for key, tr in trials.items():
        if not tr['states'] or not all(s['mode'] == 0 and s['flags'] & 3 == 1 and s['fault'] == 0 for s in tr['states']):
            raise ValueError(f'{key}: require entirely healthy disabled telemetry')
    pairs = {key: manual.moving_pairs(tr, lag) for key, tr in trials.items()}
    direction = manual.first_rotation_direction(trials['rotation03'])
    if direction != 1:
        raise ValueError('recording identity mismatch: this campaign first rotated in positive direction')
    moving = pairs['rotation03']
    candidate = fit.fit_candidate([r for r in moving if r['slow_motion_fit_eligible'] and r['direction'] == direction],
                                  [r for r in moving if r['slow_motion_fit_eligible'] and r['direction'] == -direction])
    holds = {}; checks = []; summaries = {}
    for key, tr in trials.items():
        hh = manual.hold_reports(tr, {}, direction)
        holds[key] = [compact_hold(h, candidate, tr['host'][0]) for h in hh]
        qualified = [dict(encoder_rad=h['native_encoder_angle_rad'], camera_rad=h['camera_image_angle_rad']['median'], qualified=True)
                     for h in hh if h['stationary_comparison_qualified']]
        if key != 'rotation03':
            checks.append(dict(recording=key, **fit.validate_stationary(candidate, qualified)))
        summaries[key] = dict(name=tr['name'], entirely_disabled_healthy=True, reference_counts=tr['reference'],
                              duration_s=float(tr['host'][-1]-tr['host'][0]), state_samples=len(tr['states']), info_samples=len(tr['infos']),
                              camera_filters=tr['filter_report'], holds=holds[key], collector_error=tr['report'].get('error'),
                              collector_source_sha256=tr['report'].get('collector_sha256'), before=tr['report'].get('info_before'), after=tr['report'].get('info_after'))
    sources = [Path(__file__), HERE / 'fit_candidate.py', Path(manual.__file__), Path(base.__file__), args.lag_from]
    for tr in trials.values():
        sources.extend(tr['sources'])
    result = dict(schema='cartpole-encoder-repeat-validation-v1', reference_counts=refs.pop(), candidate=candidate,
                  stationary_checks=checks, calibration_accepted=False, hardware_accepted=False,
                  disposition='rejected_stationary_validation' if any(not c['passed'] for c in checks) else 'requires_independent_validation',
                  frozen_lag_s=lag, recordings=summaries,
                  limitations=['Camera raw atan2 geometry is an image-vertical proxy, not certified physical vertical.',
                               'Multiple quiet windows in one pose are correlated, not independent replications.',
                               'No hand-contact event timestamps were recorded; associations cannot establish a mechanism.',
                               'The first freefall was accidental according to the user. Raising/holding and releases are retained and not mixed into training.',
                               'The frozen -17 ms timing proxy is not a measured exposure delay; fast freefall residuals do not isolate angle error.',
                               'No calibration, firmware, gains, simulator, or learned policy were changed.'],
                  source_hashes=[dict(path=str(p.resolve()), sha256=sha(p)) for p in sources])
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    plot_results(trials, pairs, holds, candidate, args.output)
    print(json.dumps(dict(output=str(args.output), opposite_direction=candidate['opposite_direction'],
                          stationary_checks=checks, disposition=result['disposition']), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
