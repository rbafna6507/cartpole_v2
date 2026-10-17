#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib>=3.8,<4"]
# ///
"""Summarize/plot local teacher runs. Run after extracting teacher-runs.tar.xz at repo root."""
import argparse
import gzip
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--repo', type=Path, default=Path.cwd())
p.add_argument('--output', type=Path, required=True, help='Existing directory for teacher-summary.json and teacher-comparison.png')
a = p.parse_args()
ev = a.repo / 'evidence/rl-diagnostics-20261017'
exact = json.loads(gzip.decompress((ev / 'feasibility/cartpole_teacher25.json.gz').read_bytes()).decode())
result = {'role': 'Exploratory nominal simulation; inspected cases are development, not final qualification.', 'hold_definition': 'Final 5 seconds continuously: abs(wrapped theta)<.15rad, abs(omega)<1rad/s, abs(x)<.12m.', 'exact_teacher': [e['summary'] for e in exact['episodes']], 'imitation': []}
reports = []
for path in sorted((a.repo / 'runs').glob('local-teacher-probe-20261017-seed*/report.json')):
    report = json.loads(path.read_text())
    evaluation = report.get('longer_evaluation', report.get('confirmation'))
    episodes = []
    for e in evaluation['episodes']:
        if e['start'] != 'upright':
            continue
        trace = e['trajectory']
        counts = {}
        for key, limit in (('x', .12), ('theta', .15), ('omega', 1.)):
            counts[key + '_violations'] = sum(abs(math.atan2(math.sin(t[key]), math.cos(t[key])) if key == 'theta' else t[key]) >= limit for t in trace)
        episodes.append({'seed': e['seed'], 'hold_success': e['hold_success'], 'balanced_fraction': e['balanced_fraction'], 'final_balance_dwell_s': e['final_balance_dwell_s'], 'max_abs_x_m': e['max_abs_x_m'], **counts})
    row = {'path': str(path.relative_to(a.repo)), 'seed': report['seed'], 'updates': report['updates'], 'validation_raw_rmse': report['fit_trace'][-1]['validation_raw_rmse'], 'role': 'adaptive regression follow-up' if report['updates'] != 1500 else 'initial longer evaluation, now inspected development', 'by_start': evaluation['by_start'], 'upright_episodes': episodes}
    result['imitation'].append(row)
    reports.append((row, evaluation))
a.output.mkdir(parents=True, exist_ok=True)
(a.output / 'teacher-summary.json').write_text(json.dumps(result, indent=2) + '\n')
fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, layout='constrained')
teacher = next(e for e in exact['episodes'] if e['summary']['seed'] == 41000)['trajectory']
axes[0].plot([t['t_s'] for t in teacher], [1000*t['x'] for t in teacher], color='#172b4d', label='Exact controller: passes final hold', linewidth=2)
axes[1].plot([t['t_s'] for t in teacher], [math.degrees(t['theta']) for t in teacher], color='#172b4d', linewidth=2)
for row, evaluation in reports:
    if row['seed'] != 3:
        continue
    e = next(e for e in evaluation['episodes'] if e['seed'] == 41000 and e['start'] == 'upright')
    trace = e['trajectory']
    label = f"Network, {row['updates']:,} updates: fails final hold"
    axes[0].plot([t['t'] for t in trace], [1000*t['x'] for t in trace], label=label, alpha=.85)
    axes[1].plot([t['t'] for t in trace], [math.degrees(t['theta']) for t in trace], alpha=.85)
for ax, bound in zip(axes, (120, math.degrees(.15))):
    for sign in (-1, 1):
        ax.axhline(sign*bound, color='#c43a3a', linestyle='--', alpha=.7)
    ax.axvspan(20, 25, color='#e8edf3', alpha=.7, zorder=-1)
    ax.grid(alpha=.2)
axes[0].set_ylabel('Cart position (mm)')
axes[1].set_ylabel('Angle from upright (degrees)')
axes[1].set_xlabel('Time (s); shaded = final 5-second hold window')
axes[0].legend(loc='upper right', fontsize=9)
fig.suptitle('Useful balance feedback still needs position margin\nOne shared development pose (41000); all seeds are retained in teacher-summary.json')
fig.savefig(a.output / 'teacher-comparison.png', dpi=160)
print(json.dumps([{k:r[k] for k in ('seed','updates','validation_raw_rmse','upright_episodes')} for r in result['imitation']], indent=2))
