#!/usr/bin/env python3
"""Plot every audited fresh hanging trajectory from the frozen stateful teacher.

From the repository root:
  .venv/bin/python evidence/rl-swing-20261018/tools/teacher_trajectories.py

For restored raw evidence, pass --runs PATH/TO/fresh60 and --audit PATH/TO/audit.json.
This script only reads evidence and writes the requested PNG; it runs no controller.
"""
import argparse
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SEEDS = tuple(range(55000, 55008))
COLORS = ('#0b7285', '#e67700', '#5f3dc4', '#2b8a3e',
          '#c2255c', '#1864ab', '#9c6500', '#495057')


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read_verified(runs, audit_path):
    audit = json.loads(audit_path.read_text())
    if audit.get('passed') is not True:
        raise ValueError('Evidence audit did not pass')
    audit_binding = json.loads((audit_path.parent / 'teacher-summary.json').read_text())
    if audit_binding['audit_sha256'] != digest(audit_path):
        raise ValueError('Audit hash differs from teacher-summary binding')
    pin = next(row for row in audit['runs'] if row['directory'] == 'fresh60')
    for filename, key in (('report.json', 'report_sha256'), ('recipe.json', 'recipe_sha256'),
                          ('source.zip', 'source_zip_sha256')):
        if digest(runs / filename) != pin[key]:
            raise ValueError(f'Audited {filename} hash mismatch')
    report = json.loads((runs / 'report.json').read_text())
    recipe = json.loads((runs / 'recipe.json').read_text())
    if (not report['completed'] or len(report['candidates']) != 1
            or recipe['purpose'] != 'frozen_evaluation' or recipe['seconds'] != 60.
            or recipe['seeds'] != list(SEEDS)):
        raise ValueError('Expected the complete frozen 60 s evaluation on all eight fresh seeds')
    candidate = report['candidates'][0]
    if candidate['name'] != 'mirror_pos20' or candidate['actor'] != 'host_latch':
        raise ValueError('Expected the frozen stateful mirror_pos20 controller')
    episodes = sorted((e for e in candidate['episodes'] if e['start'] == 'hanging'),
                      key=lambda e: e['seed'])
    if tuple(e['seed'] for e in episodes) != SEEDS:
        raise ValueError('All eight hanging starts must be shown exactly once')
    result = []
    for episode in episodes:
        trace_path = runs / episode['trajectory_path']
        if digest(trace_path) != episode['trajectory_sha256']:
            raise ValueError(f'Trace hash mismatch for seed {episode["seed"]}')
        with gzip.open(trace_path, 'rt') as stream:
            rows = [json.loads(line) for line in stream]
        if len(rows) != 6000 or episode['steps'] != 6000:
            raise ValueError('Every plotted episode must include the full 60 s horizon')
        t = np.asarray([r['t_s'] for r in rows])
        theta = np.asarray([r['theta'] for r in rows])
        x = np.asarray([r['x'] for r in rows])
        omega = np.asarray([r['omega'] for r in rows])
        if not np.allclose(t, np.arange(1, 6001) / 100., atol=1e-12, rtol=0):
            raise ValueError('Expected every 100 Hz trace sample in chronological order')
        balanced = (np.abs(theta) < .15) & (np.abs(omega) < 1.) & (np.abs(x) < .12)
        if not np.array_equal(balanced, [r['strict_balanced'] for r in rows]):
            raise ValueError('Strict-balance flags disagree with trace values')
        dwell = 0
        first5 = None
        for index, ok in enumerate(balanced):
            dwell = dwell + 1 if ok else 0
            if first5 is None and dwell >= 500:
                first5 = t[index]
        if (first5 != episode['first_five_second_hold_s']
                or not math.isclose(dwell / 100., episode['final_balance_dwell_s'], abs_tol=1e-8)):
            raise ValueError('Recomputed capture/final-hold metrics disagree with report')
        result.append(dict(episode=episode, t=t, theta=theta, x=x, first5=first5))
    return recipe, result, pin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=ROOT / 'runs/local-swing-teacher-20261018/fresh60')
    parser.add_argument('--audit', type=Path, default=ROOT / 'runs/local-swing-teacher-20261018/audit.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/rl-swing-20261018/teacher-fresh60.png')
    args = parser.parse_args()
    recipe, traces, pin = read_verified(args.runs, args.audit)
    rail_mm = recipe['experiment']['simulation_config']['rail_half_m'] * 1000
    hold_times = np.asarray([r['first5'] for r in traces], dtype=float)
    if not np.all(np.isfinite(hold_times)):
        raise ValueError('This frozen report should contain a completed hold for every seed')
    peak_mm = max(float(np.max(np.abs(r['x']))) * 1000 for r in traces)
    rms_mm = float(np.mean([np.sqrt(np.mean(r['x'][-500:]**2)) * 1000 for r in traces]))
    faults = sum(r['episode']['fault_reason'] is not None for r in traces)
    saturations = sum(r['episode']['force_saturated_control_steps'] for r in traces)
    holds = sum(r['episode']['hold_success'] for r in traces)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.titleweight': 'bold', 'axes.labelcolor': '#29343d',
                         'text.color': '#182630', 'xtick.color': '#46535d',
                         'ytick.color': '#46535d'})
    fig = plt.figure(figsize=(16.5, 9), facecolor='white')
    grid = fig.add_gridspec(2, 2, width_ratios=(3., 1.35), height_ratios=(1., 1.),
                           left=.07, right=.975, top=.84, bottom=.15, hspace=.29, wspace=.24)
    angle_ax = fig.add_subplot(grid[0, 0])
    cart_ax = fig.add_subplot(grid[1, 0], sharex=angle_ax)
    right = grid[:, 1].subgridspec(2, 1, height_ratios=(2.05, 1.), hspace=.32)
    capture_ax = fig.add_subplot(right[0, 0])
    note_ax = fig.add_subplot(right[1, 0]); note_ax.axis('off')

    angle_ax.axhspan(-.15, .15, color='#dbece3', alpha=.8, zorder=0)
    cart_ax.axhspan(-120, 120, color='#edf4ef', alpha=.9, zorder=0)
    for color, row in zip(COLORS, traces):
        # Break the drawing at angular wrapping discontinuities; retain every trace value.
        wrapped = row['theta'].copy()
        wrapped[np.r_[False, np.abs(np.diff(wrapped)) > math.pi]] = np.nan
        angle_ax.plot(row['t'], wrapped, color=color, linewidth=.85, alpha=.85,
                      label=str(row['episode']['seed']))
        cart_ax.plot(row['t'], row['x'] * 1000, color=color, linewidth=.9, alpha=.85)
    for sign in (-1, 1):
        angle_ax.axhline(sign * .15, color='#64786a', linestyle='--', linewidth=.85, alpha=.9)
        cart_ax.axhline(sign * 120, color='#946200', linestyle='--', linewidth=1.05)
        cart_ax.axhline(sign * rail_mm, color='#a23f41', linestyle='-.', linewidth=1.15)
    angle_ax.set(title='Wrapped pole angle · every fresh hanging start', ylabel='Pole angle (rad; upright = 0)',
                 xlim=(0, 60), ylim=(-3.45, 3.45), yticks=(-math.pi, -math.pi / 2, 0, math.pi / 2, math.pi),
                 yticklabels=('−π', '−π/2', '0', 'π/2', 'π'))
    angle_ax.tick_params(labelbottom=False)
    angle_ax.legend(title='Pose seed', ncol=4, loc='upper right', fontsize=9, title_fontsize=9,
                    frameon=True, facecolor='white', edgecolor='#e3e7e9', framealpha=.95)
    angle_ax.text(59.2, .27, 'Hold angle: ±0.15 rad', ha='right', fontsize=9, color='#536a5b')
    cart_ax.set(title='Cart position · peak |x| = %.2f mm' % peak_mm,
                xlabel='Elapsed time after reset (s)', ylabel='Cart position (mm)',
                ylim=(-340, 340), xticks=range(0, 61, 10), yticks=(-300, -120, 0, 120, 300))
    cart_ax.legend(handles=[Line2D([], [], color='#946200', linestyle='--', label='Hold centering: ±120 mm'),
                           Line2D([], [], color='#a23f41', linestyle='-.', label=f'Rail bounds: ±{rail_mm:.2f} mm')],
                   loc='lower right', fontsize=9, frameon=True, facecolor='white',
                   edgecolor='#e3e7e9', framealpha=.95)
    for ax in (angle_ax, cart_ax):
        ax.grid(axis='x', alpha=.18, linewidth=.6)
        ax.grid(axis='y', alpha=.12, linewidth=.6)
        ax.set_axisbelow(True)

    y = np.arange(len(traces))
    capture_ax.barh(y, hold_times, color=COLORS, height=.62, alpha=.9)
    capture_ax.set(yticks=y, yticklabels=[str(s) for s in SEEDS], ylim=(7.7, -.7),
                   xlim=(0, 18), xticks=(0, 5, 10, 15), xlabel='Seconds to complete a 5 s hold',
                   title='Capture time · all eight seeds')
    capture_ax.axvline(float(np.mean(hold_times)), color='#263b47', linestyle=':', linewidth=1.4)
    for index, value in enumerate(hold_times):
        capture_ax.text(value + .22, index, f'{value:.2f}', va='center', fontsize=10)
    capture_ax.grid(axis='x', alpha=.17); capture_ax.set_axisbelow(True)
    capture_ax.text(.98, -.18, f'Dotted line: mean {np.mean(hold_times):.2f} s',
                    transform=capture_ax.transAxes, ha='right', fontsize=9, color='#46535d')
    note_ax.text(0, .97, f'{holds}/8 retained final holds', fontsize=17, weight='bold', va='top')
    note_ax.text(0, .73,
                 f'{faults} faults · {saturations} force-saturated samples\n'
                 f'Capture range: {min(hold_times):.2f}–{max(hold_times):.2f} s\n'
                 f'Mean final 5 s cart RMS: {rms_mm:.2f} mm\n'
                 f'Minimum geometric rail margin: {rail_mm - peak_mm:.2f} mm',
                 fontsize=11, linespacing=1.7, va='top')
    fig.suptitle('Stateful controller baseline (not RL)', x=.07, y=.963, ha='left', fontsize=21, weight='bold')
    fig.text(.07, .914,
             'Frozen mirror_pos20 · all 8 fresh hanging starts (55000–55007) · 60 s per trial · nominal encoder simulation',
             fontsize=12, color='#52616c')
    fig.text(.07, .075,
             'A hold requires |θ| < 0.15 rad, |ω| < 1 rad/s and |x| < 120 mm continuously for 5 s; capture time includes those 5 s.',
             fontsize=10, color='#46535d')
    fig.text(.07, .043,
             'Truth is used for scoring/plots only; controller inputs are observations. 100 Hz control · jerk 150 m/s³. '
             'Angles break at ±π. Simulation only; no hardware qualification.',
             fontsize=9.5, color='#606d76')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, facecolor='white')
    plt.close(fig)
    print(json.dumps(dict(output=str(args.output.resolve()), png_sha256=digest(args.output),
                          report_sha256=pin['report_sha256'], seeds=list(SEEDS),
                          samples_per_episode=6000, first5_s=hold_times.tolist(),
                          mean_first5_s=float(np.mean(hold_times)), holds=holds,
                          peak_abs_x_mm=peak_mm, final5_x_rms_mean_mm=rms_mm), indent=2))


if __name__ == '__main__':
    main()
