"""Read-only mode-interval summary of the sealed gentle training source."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from cartpole_sdk.identification import campaign


def summarize(directory):
    directory = Path(directory)
    valid, reason = campaign.verify(directory)
    if not valid:
        raise ValueError(reason)
    raw, = directory.glob('rig-*.jsonl')
    started = False
    stopped = False
    states = []
    for line in raw.open():
        row = json.loads(line)
        if row['type'] == 'driven_coupled_start':
            if started:
                raise ValueError('expected exactly one coupled trial')
            started = True
            requested = row['seconds']
        elif started and row['type'] == 'state':
            state = row['state']
            if states and state['unwrapped_us'] <= states[-1]['unwrapped_us']:
                if state == states[-1]:
                    continue
                raise ValueError('non-increasing state clock')
            states.append(state)
        elif started and row['type'] == 'driven_stop':
            if row['confirmed'] is not True:
                raise ValueError('unconfirmed stop')
            stopped = True
            break
    if not stopped or not states:
        raise ValueError('missing complete coupled trial')
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
    return dict(trial='008-coupled', requested_s=requested, observed_s=t,
        mode_intervals=intervals, balance_intervals=balance_intervals,
        total_observed_balance_s=sum(i['duration_s'] for i in balance_intervals),
        balanced_samples=len(balanced), raw_balance_angle_rms_deg=float(np.sqrt(np.mean(theta**2))),
        raw_balance_angle_p95_abs_deg=float(np.quantile(np.abs(theta), .95)),
        max_abs_counted_x_m=max(abs(s['x']) for s in states),
        faults=sorted(set(s['fault'] for s in states)),
        source_raw_path=str(raw), source_raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        semantics='Raw firmware-reference angle RMS only within mode3 and enabled snapshots; mode intervals quantized at recorded telemetry. Counted cart x is not physical motion measurement.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign')
    args = parser.parse_args()
    print(json.dumps(summarize(args.campaign), indent=2, allow_nan=False))
