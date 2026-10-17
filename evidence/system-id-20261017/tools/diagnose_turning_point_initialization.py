#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3"]
# ///
"""DEVELOPMENT diagnostic: compare frozen-ODE initializers on identical samples.

A first raw-angle extremum supplies an alternative initial condition, never a
new coefficient fit. Its surrounding samples are excluded from both scores.
No primary metrics/gates, model promotion, hardware, or camera-clock inference.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np

FREEZE_SHA = '04befe14b16a54e5288d4326a7ca5d826e8c5a169dc20206dd1108ea160aa744'
RULES = dict(search_seconds=1.2, half_window_seconds=.06,
             minimum_side_seconds=.055, minimum_samples=21,
             minimum_curvature_rad_s2=2., minimum_side_excursion_rad=.01,
             maximum_polynomial_rmse_rad=.01, maximum_gap_s=.05,
             maximum_rk4_step_s=.001)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_method(repo):
    analysis = Path(repo) / 'evidence/system-id-20261016/analysis'
    if sha(analysis / 'manual-ringdown-train-02-freeze.json') != FREEZE_SHA:
        raise ValueError('training freeze changed')
    path = analysis / 'heldout/evaluate_passive.py'
    spec = importlib.util.spec_from_file_location('turning_point_frozen_evaluator', path)
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    fitter, training, freeze = evaluator.verify_freeze(analysis)
    if training['magnetic_reports']['viscous']['parameters'] != freeze['candidate_parameters']:
        raise ValueError('frozen coefficients disagree')
    return fitter, training, freeze, evaluator


def vectors(t, q):
    t, q = np.asarray(t, float), np.asarray(q, float)
    if (t.ndim != 1 or q.shape != t.shape or len(t) < 40 or
            not np.isfinite(t).all() or not np.isfinite(q).all() or
            np.any(np.diff(t) <= 0) or np.max(np.diff(t)) > RULES['maximum_gap_s']):
        raise ValueError('finite ordered contiguous samples required')
    return t, np.unwrap(q)


def first_turning_point(t, q):
    """First qualifying raw extremum; no model, fit residual or scored future."""
    t, q = vectors(t, q)
    for i in range(1, len(t) - 1):
        if t[i] - t[0] > RULES['search_seconds']:
            break
        lo = int(np.searchsorted(t, t[i] - RULES['half_window_seconds'] - 1e-10))
        hi = int(np.searchsorted(t, t[i] + RULES['half_window_seconds'] + 1e-10, side='right'))
        if (hi - lo < RULES['minimum_samples'] or
                t[i] - t[lo] < RULES['minimum_side_seconds'] or
                t[hi - 1] - t[i] < RULES['minimum_side_seconds']):
            continue
        dt = t[lo:hi] - t[i]
        a, b, c = np.polyfit(dt, q[lo:hi], 2)
        if abs(2 * a) < RULES['minimum_curvature_rad_s2']:
            continue
        vertex = -b / (2 * a)
        # The vertex must belong to this candidate's central sample cell. This
        # chooses the first qualifying turn without optimizing model error.
        if not -(t[i] - t[i - 1]) / 2 <= vertex <= (t[i + 1] - t[i]) / 2:
            continue
        peak_t = float(t[i] + vertex)
        if peak_t - t[0] > RULES['search_seconds']:
            continue
        peak_q = float(c - b * b / (4 * a))
        excursion = float(min(abs(np.polyval([a, b, c], dt[0]) - peak_q),
                              abs(np.polyval([a, b, c], dt[-1]) - peak_q)))
        residual = float(np.sqrt(np.mean((q[lo:hi] - np.polyval([a, b, c], dt)) ** 2)))
        if (excursion < RULES['minimum_side_excursion_rad'] or
                residual > RULES['maximum_polynomial_rmse_rad']):
            continue
        return dict(vertex_t_s=peak_t, initial_raw_angle_rad=peak_q,
                    initial_omega_rad_s=0., curvature_rad_s2=float(2 * a),
                    polynomial_rmse_rad=residual, minimum_side_excursion_rad=excursion,
                    support_start_s=float(t[lo]), support_end_s=float(t[hi - 1]),
                    support_samples=hi - lo, support_indices=[lo, hi - 1],
                    candidate_center_s=float(t[i]), kind='minimum' if a > 0 else 'maximum')
    raise ValueError('no clear turning point within fixed first1.2s search')


def trajectory(t, initial_t, initial_q, initial_w, coefficients, fitter):
    """One initial state, no subsequent access to measured angles."""
    q, w, previous = float(initial_q), float(initial_w), float(initial_t)
    rows = []
    for target in t:
        delta = float(target - previous)
        if delta <= 0:
            raise ValueError('prediction timestamps must follow initialization')
        n = max(1, math.ceil(delta / RULES['maximum_rk4_step_s']))
        for _ in range(n):
            q, w = fitter.advance(q, w, delta / n, coefficients)
        rows.append(q)
        previous = float(target)
    return np.asarray(rows)


def statistics(errors):
    return dict(samples=len(errors), rmse_rad=float(np.sqrt(np.mean(errors ** 2))),
                p95_rad=float(np.quantile(abs(errors), .95)))


def compare_episode(episode, coefficients, fitter):
    t, q = vectors(episode['t_s'], episode['theta_rad'])
    turn = first_turning_point(t, q)
    i = max(10, int(np.searchsorted(t, t[0] + .1)))
    baseline_w = float(np.polyfit(t[i - 10:i + 1] - t[i], q[i - 10:i + 1], 2)[-2])
    selected = np.flatnonzero(t > max(turn['support_end_s'], t[i]) + 1e-10)
    if len(selected) < 20:
        raise ValueError('insufficient disjoint scored samples after turning-point support')
    # Integrate both models on every intervening observed timestamp; score only
    # the common suffix after all initializer samples, including the peak's
    # right-hand polynomial support, have ended.
    baseline_t = t[i + 1:]
    baseline = trajectory(baseline_t, t[i], q[i], baseline_w, coefficients, fitter)
    turn_ix = np.flatnonzero(t > turn['vertex_t_s'] + 1e-10)
    turned = trajectory(t[turn_ix], turn['vertex_t_s'], turn['initial_raw_angle_rad'],
                        0., coefficients, fitter)
    predicted_base = baseline[selected - (i + 1)]
    predicted_turn = turned[np.searchsorted(turn_ix, selected)]
    base_error = np.arctan2(np.sin(predicted_base - q[selected]), np.cos(predicted_base - q[selected]))
    turn_error = np.arctan2(np.sin(predicted_turn - q[selected]), np.cos(predicted_turn - q[selected]))
    return dict(episode_id=episode['episode_id'], parameters_refitted=False,
                turning_point=turn, first_scored_t_s=float(t[selected[0]]),
                last_scored_t_s=float(t[selected[-1]]),
                baseline_initialization=dict(t_s=float(t[i]), raw_angle_rad=float(q[i]),
                                             omega_rad_s=baseline_w, support_start_s=float(t[i - 10]), support_end_s=float(t[i])),
                baseline=statistics(base_error), turn_initialized=statistics(turn_error),
                reading_columns=['board_relative_s', 'measured_raw_angle_rad',
                                 'baseline_predicted_raw_angle_rad', 'turn_predicted_raw_angle_rad',
                                 'baseline_wrapped_error_rad', 'turn_wrapped_error_rad'],
                readings=np.column_stack([t[selected], q[selected], predicted_base,
                                          predicted_turn, base_error, turn_error]).tolist())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    p.add_argument('--input', required=True)
    p.add_argument('--annotations', type=Path, required=True)
    p.add_argument('--annotations-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    if a.output.exists():
        p.error('output exists; preserve previous results')
    if sha(a.annotations) != a.annotations_sha256:
        raise ValueError('annotation hash mismatch')
    sys.path.insert(0, str(a.repo / 'src'))
    from cartpole_sdk.identification import workflow
    episodes, identity = workflow.passive_episodes(a.input, a.annotations)
    if identity.get('collection_report', {}).get('completed') is not True:
        raise ValueError('bound successful modern raw recording required')
    if identity['reference'][0] != 330:
        raise ValueError('frozen local phase requires unchanged raw reference330')
    fitter, training, freeze, evaluator = frozen_method(a.repo)
    if identity['sha256'] in freeze['source_export']['source_hashes'].values():
        raise ValueError('training source cannot be repeated as new diagnostic input')
    parameters = freeze['candidate_parameters']
    results = []
    for episode in episodes:
        try:
            result = compare_episode(episode, parameters['linear_coefficients'], fitter)
            result['status'] = 'scored'
        except ValueError as exc:
            result = dict(episode_id=episode['episode_id'], status='unavailable', reason=str(exc))
        results.append(result)
    report = dict(schema='cartpole-turning-point-initialization-development-v1',
                  scope='DEVELOPMENT initialization sensitivity only; primary scores/gates unchanged, no independent acceptance',
                  parameters_refitted=False, recommended_for_hardware_rl=False,
                  parameters=parameters, input=identity, annotations_sha256=a.annotations_sha256,
                  rules=RULES, episodes=results,
                  provenance=dict(script_sha256=sha(__file__), frozen_training_manifest_sha256=FREEZE_SHA,
                                  frozen_fitter_sha256=sha(fitter.__file__), frozen_evaluator_sha256=sha(evaluator.__file__),
                                  workflow_sha256=sha(workflow.__file__), numpy_version=np.__version__),
                  caveats=['New initialization diagnostic chosen after primary errors were inspected; not independent validation.',
                           'Both scores use exactly the same samples strictly after all initial-state estimation support.',
                           'The peak uses a bounded local quadratic on raw angles; zero angular velocity is the fitted extremum condition.',
                           'Raw angle scale, frozen local phase, and physically fixed cart remain assumptions.',
                           'Frozen RK4 ODE only; no new MuJoCo verification or parameter fitting.'])
    payload = json.dumps(report, indent=2, allow_nan=False) + '\n'
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as stream:
        stream.write(payload)
    print(json.dumps(dict(output=str(a.output), episodes=[{k: v for k, v in x.items() if k != 'readings'} for x in results]), indent=2))


if __name__ == '__main__':
    main()
