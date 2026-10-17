#!/usr/bin/env python3
"""Reproduce the batch-1 raw-data review; never fit, select intervals or use serial."""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from cartpole_sdk.identification.review import review_recording
from cartpole_sdk.identification.workflow import load_records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = Path(__file__).resolve().parent
    result = {'schema': 'operator-batch1-quality-review-v1', 'model_fitted': False,
              'intervals_selected': False, 'physical_cart_stationarity_certified': False,
              'recordings': []}
    traces = {}
    for name in ('passive-train-01', 'passive-validate-01'):
        source = next((evidence / 'raw' / name).glob('*.jsonl.gz'))
        records, identity = load_records(source)
        completion = json.loads(source.with_name('report.json').read_text())
        states = [r['state'] for r in records if r.get('type') == 'state']
        infos = [r['info'] for r in records if r.get('type') == 'info']
        t = np.array([s['unwrapped_us'] for s in states], dtype=np.int64)
        t = (t - t[0]) / 1e6
        q = np.unwrap(np.array([s['theta'] for s in states]))
        branch = math.pi + 2 * math.pi * round((float(np.median(q)) - math.pi) / (2 * math.pi))
        angle = np.degrees(q - branch)
        dt = np.diff(t)
        unhealthy = sum(s['mode'] != 0 or s['fault'] != 0 or (s['flags'] & 15) != 13
                        or bool(s['flags'] & 304) for s in states)
        metric = dict(name=name, source_sha256=identity['sha256'],
            completed=completion['completed'], stop_confirmed=completion['stop_confirmed'],
            logger_records_dropped=completion['records_dropped'], state_count=len(states),
            duration_s=float(t[-1]), median_snapshot_hz=float(1 / np.median(dt)),
            max_snapshot_gap_ms=float(max(dt) * 1000),
            gaps_over_5ms=int(sum(dt > .005)), duplicate_timestamps=int(sum(dt == 0)),
            reversed_timestamps=int(sum(dt < 0)), unhealthy_passive_states=unhealthy,
            modes=sorted({s['mode'] for s in states}), faults=sorted({s['fault'] for s in states}),
            reference_counts=sorted({i['encoder_upright_raw'] for i in infos}),
            home_epochs=sorted({i['home_epoch'] for i in infos}),
            session_ids=sorted({s['sid'] for s in states}),
            board_drop_counter_delta=states[-1]['dropped'] - states[0]['dropped'],
            raw_branch_angle_range_deg=[float(min(angle)), float(max(angle))],
            initial_rest_median_deg=float(np.median(angle[t <= 1])),
            final_rest_median_deg=float(np.median(angle[t >= t[-1] - 3])),
            counted_cart_range_m=[min(s['x'] for s in states), max(s['x'] for s in states)],
            angle_range_includes_manual_handling=True)
        result['recordings'].append(metric)
        traces[name] = (t, angle)
        review_recording(str(source), args.output / name)
    result['annotation_snapshot'] = json.loads((evidence / 'raw' / 'train-annotations-as-read.json').read_text())
    (args.output / 'quality-report.json').write_text(json.dumps(result, indent=2) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    t, angle = traces['passive-train-01']
    fig, ax = plt.subplots(figsize=(11, 4.5), layout='constrained')
    selected = (t >= 24) & (t <= 39)
    ax.plot(t[selected], angle[selected], color='#255ba3', lw=1.3, label='Recorded raw encoder angle')
    ax.axvspan(32, 36, color='#22a884', alpha=.17,
               label='Illustrative interval [32.0, 36.0]; operator must confirm')
    for x in (32, 36):
        ax.axvline(x, color='#13815d', ls='--', lw=1)
    ax.axhline(float(np.median(angle[t <= 1])), color='#777777', ls=':', label='Initial resting baseline')
    ax.set(xlabel='Seconds from first recorded STATE (same clock as the JSON)',
           ylabel='Raw angle − hanging branch (degrees)',
           title='Batch 1, first training release: reading interval times\nExample only — no annotations selected or model fitted',
           xlim=(24, 39))
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(alpha=.2)
    fig.savefig(args.output / 'annotation-example.png', dpi=160)
    fig.savefig(args.output / 'annotation-example.pdf')
    plt.close(fig)
    print(json.dumps({'output': str(args.output), 'recordings': result['recordings']}, indent=2))


if __name__ == '__main__':
    main()
