"""Offline mode-duration audit; no model fitting or hardware imports."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from cartpole_sdk.identification import campaign
from cartpole_sdk.identification.driven_validation import _states


def summarize(directory):
    directory = Path(directory)
    valid, reason = campaign.verify(directory)
    if not valid:
        raise ValueError(reason)
    report = json.loads((directory/'report.json').read_text())
    trial_ids = iter(t['id'] for t in report['trials'] if t['kind'] == 'coupled')
    raw, = directory.glob('rig-*.jsonl')
    segments = []
    active = None
    for line in raw.open():
        row = json.loads(line)
        if row['type'] == 'driven_coupled_start':
            if active is not None:
                raise ValueError('overlapping native trials')
            active = dict(id=next(trial_ids), requested_s=row['seconds'], records=[])
        elif active is not None:
            active['records'].append(row)
            if row['type'] == 'driven_stop':
                if row['confirmed'] is not True:
                    raise ValueError('unconfirmed stop')
                segments.append(active)
                active = None
    if active is not None:
        raise ValueError('unfinished native trial')
    result = []
    for segment in segments:
        states = _states(segment['records'])
        origin = states[0]['unwrapped_us']
        intervals = []
        for state in states:
            t = (state['unwrapped_us']-origin)/1e6
            if not intervals or state['mode'] != intervals[-1]['mode']:
                if intervals:
                    intervals[-1]['end_s'] = t
                    intervals[-1]['duration_s'] = t-intervals[-1]['start_s']
                intervals.append(dict(mode=state['mode'], start_s=t, last_s=t, samples=1))
            else:
                intervals[-1]['last_s'] = t
                intervals[-1]['samples'] += 1
        intervals[-1]['end_s'] = t
        intervals[-1]['duration_s'] = t-intervals[-1]['start_s']
        balanced = [s for s in states if s['mode'] == 3 and s['flags'] & 2]
        theta = np.array([math.atan2(math.sin(s['theta']), math.cos(s['theta']))
                          for s in balanced])*180/math.pi
        balance_intervals = [i for i in intervals if i['mode'] == 3]
        result.append(dict(id=segment['id'], requested_s=segment['requested_s'],
            observed_through_stop_s=t, mode_intervals=intervals,
            balance_intervals=balance_intervals,
            total_observed_balance_s=sum(i['duration_s'] for i in balance_intervals),
            balanced_samples=len(balanced),
            raw_balance_angle_rms_deg=float(np.sqrt(np.mean(theta**2))) if len(theta) else None,
            raw_balance_angle_p95_abs_deg=float(np.quantile(np.abs(theta), .95)) if len(theta) else None,
            max_abs_counted_x_m=max(abs(s['x']) for s in states),
            faults=sorted(set(s['fault'] for s in states))))
    return dict(campaign=directory.name, declared_role=report['dataset_role'],
        source_raw_path=str(raw), source_raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        trials=result,
        semantics='Mode intervals end at first next-mode sample and are telemetry-quantized. Angle metrics use only enabled mode3; counted cart x is not independently measured physical displacement. Return-home motion is included only in mode timeline, not forecast scores.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaigns', nargs='+')
    args = parser.parse_args()
    print(json.dumps([summarize(p) for p in args.campaigns], indent=2, allow_nan=False))
