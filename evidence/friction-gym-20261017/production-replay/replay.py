#!/usr/bin/env python3
"""Replay a frozen passive candidate through the production MujocoBackend.

Uses one causal 0.5 s initialization per annotated release, fixed 1 ms physics,
zero cart-acceleration demand and no subsequent trajectory corrections.
"""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import mujoco
import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / 'evidence/system-id-model-review-20261017'
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(REFERENCE / 'tools'))
from cartpole_sdk.identification import passive, workflow
from cartpole_sdk.sim import MujocoBackend, SimulationConfig
from dynamics import initial_state, metrics, ode_solution

DT_NS = 1_000_000
WARMUP_S = .5


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def make_config(coefficients, *, max_steps):
    if len(coefficients) != 4 or not all(math.isfinite(x) for x in coefficients):
        raise ValueError('expected the four frozen viscous + smooth friction coefficients')
    a, gamma, b, friction = coefficients
    magnitude = math.hypot(a, b)
    if magnitude <= 0. or min(gamma, friction) < 0.:
        raise ValueError('nonphysical passive coefficients')
    length = 9.81 / magnitude
    inertia = .75 * .02275 * length**2
    return SimulationConfig(
        physics_dt_ns=DT_NS, control_steps=1, max_steps=max_steps,
        rail_half_m=.308962494, effective_length_m=length,
        cart_mass_kg=.35, pole_mass_kg=.02275, cart_damping=.05,
        hinge_damping=inertia * gamma, hinge_coulomb_friction_nm=inertia * friction,
        hinge_friction_velocity_scale_rad_s=.05, max_force_n=20.,
    ), math.atan2(b, a), inertia


def replay_on_sample_times(config, phase, state, times):
    """Integrate unchanged 1 ms backend ticks, interpolate only output samples."""
    times = np.asarray(times, dtype=float)
    if (times.ndim != 1 or len(times) < 2 or not np.all(np.isfinite(times))
            or np.any(np.diff(times) <= 0.)):
        raise ValueError('finite strictly increasing sample timestamps required')
    exact_ns = (times - times[0]) * 1e9
    sample_ns = np.rint(exact_ns).astype(np.int64)
    if np.any(np.diff(sample_ns) <= 0.):
        raise ValueError('sample timestamps must differ by at least one nanosecond')
    if config.physics_dt_ns != DT_NS or config.control_steps != 1:
        raise ValueError('production replay requires one fixed 1 ms physics tick per step')
    backend = MujocoBackend(config)
    hinge = int(backend.model.joint('pole_hinge').qposadr[0])
    backend.reset(state=(0., 0., float(state[0] + phase), float(state[1])))
    current = previous = float(state[0])
    predicted = [current]
    steps = saturated = 0
    max_x = max_v = max_a = max_force = 0.
    for target in sample_ns[1:]:
        target_tick = (int(target) + DT_NS - 1) // DT_NS
        while steps < target_tick:
            previous = current
            # None means zero acceleration demand in MujocoBackend. Its inverse
            # cart force compensates coupling; no state or hinge force is edited.
            backend.step(None)
            current = float(backend.data.qpos[hinge]) - phase
            steps += 1
            truth, diagnostics = backend.ground_truth, backend.diagnostics
            max_x = max(max_x, abs(truth.x))
            max_v = max(max_v, abs(truth.v))
            max_a = max(max_a, abs(diagnostics.achieved_acceleration_m_s2))
            max_force = max(max_force, abs(diagnostics.applied_force_n))
            saturated += int(diagnostics.force_saturated)
        remainder = int(target) % DT_NS
        predicted.append(current if remainder == 0 else previous +
                         (current - previous) * remainder / DT_NS)
    backend.close()
    return dict(predicted_raw_rad=predicted, physics_steps=steps,
                force_saturation_count=saturated, max_abs_cart_position_m=max_x,
                max_abs_cart_velocity_m_s=max_v, max_abs_cart_acceleration_m_s2=max_a,
                max_abs_cart_force_n=max_force,
                timing=dict(physics_dt_ns=DT_NS, sample_count=len(times),
                            fractional_sample_count=int(np.count_nonzero(sample_ns % DT_NS)),
                            maximum_timestamp_roundoff_ns=float(np.max(abs(exact_ns-sample_ns))),
                            fractional_sample_method='Linear interpolation of adjacent 1 ms backend states; physics timestep is never changed',
                            timestamps='Exact recorded board time relative to initialization, rounded only to the nearest nanosecond'))


def quality_summary(quality):
    return dict(passed=quality['passed'], all_release_poses_verified=quality['all_release_poses_verified'],
                reasons=quality['reasons'], absolute_angle_calibration=quality['absolute_angle_calibration'],
                physical_cart_stationarity_certified=quality['physical_cart_stationarity_certified'],
                failed_free_intervals=[x['episode_id'] for x in quality['episodes'] if not x['passed']],
                failed_poses=[dict(episode_id=x['episode_id'], reasons=x['release_pose']['reasons'])
                              for x in quality['episodes'] if not x['pose_verified']],
                original_qualifications_waived=False)


def plot_report(report, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = report['episodes']
    fig, axes = plt.subplots(math.ceil(len(rows) / 2), 2, figsize=(13, 3 * math.ceil(len(rows)/2)),
                             layout='constrained', squeeze=False)
    baseline = report['source_identity']['passive_baseline']['encoder']['raw_angle_rad']
    for ax, row in zip(axes.flat, rows):
        times = np.array(row['t_s'])
        observed = np.array(row['observed_raw_rad'])
        branch = baseline + 2 * np.pi * round((np.median(observed)-baseline) / (2*np.pi))
        for key, label, style in (('observed_raw_rad', 'Recorded encoder', '-'),
                                  ('predicted_raw_rad', 'Production backend', '-'),
                                  ('ode_raw_rad', 'Frozen ODE', '--')):
            ax.plot(times-times[0], np.rad2deg(np.array(row[key])-branch), style, lw=1, label=label)
        ax.set_title(f"{row['episode_id']}: encoder RMS {row['measured_error']['rms_deg']:.2f}°")
        ax.set_xlabel('Seconds after causal initialization')
        ax.set_ylabel('Angle from recorded hanging (degrees)')
        ax.grid(alpha=.2)
    for ax in list(axes.flat)[len(rows):]:
        ax.set_visible(False)
    axes.flat[0].legend(fontsize=8)
    fig.suptitle(f"Production MuJoCo backend • batch-6 frozen parameters, batch-7 replay\n"
                 f"0.5 s initialization excluded; encoder RMS {report['measured_error']['rms_deg']:.3f}°; "
                 f"ODE parity RMS {report['ode_parity']['rms_deg']:.3f}°\n"
                 "Development evidence: camera and pose qualifications remain unresolved")
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('freeze', 'source', 'annotations', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--qualification-report', type=Path,
                        default=REFERENCE / 'analysis/batch7-latest6-check/report.json.gz',
                        help='Original frozen evaluation containing source-bound camera/pose qualifications')
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    freeze = workflow.read_json(args.freeze)
    for name, digest in freeze['method_hashes'].items():
        if sha(REFERENCE / 'tools' / name) != digest:
            raise ValueError('frozen method changed: ' + name)
    coefficients = next(x['coefficients'] for x in freeze['models'] if x['model'] == 'weak_coulomb')
    episodes, identity = workflow.passive_episodes(str(args.source), args.annotations)
    if not identity['collection_report']['completed']:
        raise ValueError('completed collection required')
    if identity['sha256'] in freeze['development_source_sha256']:
        raise ValueError('a development source cannot be claimed as an independent replay')
    qualification = json.loads(gzip.decompress(args.qualification_report.read_bytes()))
    quality = qualification['camera_quality']
    if (qualification['source_identity']['sha256'] != identity['sha256']
            or quality['annotations_sha256'] != sha(args.annotations)
            or qualification['freeze_sha256'] != sha(args.freeze)):
        raise ValueError('original qualification report does not bind to source, annotations and freeze')
    parts = passive.segments(episodes, dict(passive.DEFAULT_GATES, window_s=.35))
    if len(parts) != len(episodes):
        raise ValueError('segmentation changed annotated episode coverage')
    source_files = ('sim/backend.py', 'sim/config.py', 'sim/model.py', 'contracts.py',
                    'identification/workflow.py', 'identification/passive.py')
    source_hashes = {name: sha(ROOT / 'src/cartpole_sdk' / name) for name in source_files}
    rows, measured_errors, ode_errors, ode_measured_errors = [], [], [], []
    config, phase, inertia = make_config(coefficients, max_steps=100_000)
    for times, observed, episode_id in parts:
        start = int(np.searchsorted(times, times[0] + WARMUP_S))
        if start + 1 >= len(times):
            raise ValueError('insufficient samples after causal initialization')
        state = initial_state(times, observed, start, coefficients, 'history_rawq:0.5')
        replay = replay_on_sample_times(config, phase, state, times[start:])
        predicted = np.array(replay['predicted_raw_rad'])
        ode = ode_solution(times[start:], state, coefficients)[0]
        wrap = lambda error: np.arctan2(np.sin(error), np.cos(error))
        measured_error = wrap(predicted[1:] - observed[start+1:])
        ode_error = wrap(predicted[1:] - ode[1:])
        ode_measured_error = wrap(ode[1:] - observed[start+1:])
        measured_errors.extend(measured_error)
        ode_errors.extend(ode_error)
        ode_measured_errors.extend(ode_measured_error)
        rows.append(dict(episode_id=episode_id[1], initial_state_raw=state.tolist(),
                         initialization_index=start, initialization_history_s=WARMUP_S,
                         actual_initialization_history_span_s=float(times[start]-times[0]),
                         t_s=times[start:].tolist(), observed_raw_rad=observed[start:].tolist(),
                         ode_raw_rad=ode.tolist(), measured_error=metrics(measured_error),
                         ode_parity=metrics(ode_error), **replay))
    parity = metrics(ode_errors)
    max_difference = float(np.max(np.abs(np.rad2deg(ode_errors))))
    physics = {key: max(row[key] for row in rows) for key in
               ('max_abs_cart_position_m', 'max_abs_cart_velocity_m_s',
                'max_abs_cart_acceleration_m_s2', 'max_abs_cart_force_n')}
    physics.update(total_physics_steps=sum(row['physics_steps'] for row in rows),
                   force_saturation_count=sum(row['force_saturation_count'] for row in rows),
                   fractional_sample_count=sum(row['timing']['fractional_sample_count'] for row in rows))
    checks = dict(ode_rms_below_half_degree=parity['rms_deg'] < .5,
                  ode_max_below_one_degree=max_difference < 1.,
                  cart_position_below_one_nm=physics['max_abs_cart_position_m'] < 1e-9,
                  cart_velocity_below_one_nm_per_s=physics['max_abs_cart_velocity_m_s'] < 1e-9,
                  cart_acceleration_below_one_um_per_s2=physics['max_abs_cart_acceleration_m_s2'] < 1e-6,
                  no_force_saturation=physics['force_saturation_count'] == 0)
    if source_hashes != {name: sha(ROOT/'src/cartpole_sdk'/name) for name in source_files}:
        raise ValueError('production/preprocessing sources changed during replay')
    report = dict(schema='cartpole-production-passive-replay-v1',
                  scope='Production backend passive numerical verification; no hardware or full-rig model approval',
                  accepted=False, hardware_rl_approved=False, coefficients_refitted=False,
                  source_identity=identity, freeze_sha256=sha(args.freeze), annotations_sha256=sha(args.annotations),
                  qualification_report_sha256=sha(args.qualification_report),
                  qualification_report_path=str(args.qualification_report.resolve()),
                  coefficients=coefficients, simulation_config=asdict(config),
                  inertia_kg_m2=inertia, raw_to_physical_phase_rad=phase,
                  phase_mapping_is_absolute_calibration=False,
                  initialization_method='Frozen dynamics.initial_state(history_rawq:0.5); once per release; no later corrections',
                  measured_error=metrics(measured_errors), ode_measured_error=metrics(ode_measured_errors),
                  ode_parity=parity, ode_max_difference_deg=max_difference, physics=physics,
                  numerical_checks=checks, numerical_checks_passed=all(checks.values()),
                  camera_quality_summary=quality_summary(quality), original_camera_quality=quality,
                  production_source_hashes=source_hashes, frozen_method_hashes=freeze['method_hashes'],
                  replay_script_sha256=sha(__file__), command=[sys.executable, *sys.argv],
                  versions=dict(python=sys.version, numpy=np.__version__, scipy=scipy.__version__, mujoco=mujoco.__version__),
                  limitations=['Assumed mass, rod inertia, force limit and cart damping are not identified by passive decays.',
                               'Zero acceleration uses an ideal inverse-force cart servo; it does not validate physical actuator tracking.',
                               'Camera/pose failures and unverified physical cart restraint remain unwaived.',
                               'Smooth tanh friction does not model exact static sticking.',
                               'Recorded hanging zero is a display convention, not an absolute calibration.'],
                  episodes=rows)
    args.output.mkdir(parents=True)
    (args.output/'report.json.gz').write_bytes(gzip.compress(json.dumps(report, indent=2, allow_nan=False).encode(), mtime=0))
    summary = {key: value for key, value in report.items() if key not in ('episodes', 'original_camera_quality')}
    summary['episodes'] = [{key: value for key, value in row.items() if key not in
                            ('t_s', 'observed_raw_rad', 'predicted_raw_rad', 'ode_raw_rad')} for row in rows]
    workflow.write_json(args.output/'summary.json', summary)
    plot_report(report, args.output/'recorded-vs-production.png')
    print(json.dumps({key: report[key] for key in ('measured_error', 'ode_parity', 'ode_max_difference_deg',
                                                  'physics', 'numerical_checks', 'camera_quality_summary')}, indent=2))
    if not report['numerical_checks_passed']:
        raise RuntimeError('production replay failed numerical verification; see saved report')


if __name__ == '__main__':
    main()
