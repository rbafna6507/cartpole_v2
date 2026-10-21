"""Finite post-hoc input-convention/horizon checks, never a model promotion."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from cartpole_sdk.identification import campaign
from cartpole_sdk.identification.driven_validation import FrozenDrivenModel, _states, advance, causal_encoder_rate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trajectories(source):
    directory = ROOT/'runs/id-live-20261020'/source['name']
    valid, reason = campaign.verify(directory)
    if not valid:
        raise ValueError(reason)
    report = json.loads((directory/'report.json').read_text())
    raw = directory/report['raw_log']
    if digest(raw) != source['source_raw_sha256']:
        raise ValueError('source hash differs from primary assessment')
    records = [json.loads(line) for line in raw.open()]
    admitted = {t['id']: t for t in source['trials'] if t['status'] == 'scored'}
    for trial in report['trials']:
        if trial['id'] not in admitted:
            continue
        rows = [r for r in records if trial['started_ns'] <= r.get('host_monotonic_ns', -1) <= trial['finished_ns']]
        start, = [r for r in rows if r['type'] in ('driven_start', 'driven_coupled_start')]
        stop = next(r for r in rows if r['type'] == 'driven_stop' and r['host_monotonic_ns'] > start['host_monotonic_ns'])
        states = _states([r for r in rows if r['host_monotonic_ns'] < stop['host_monotonic_ns']])
        allowed = {12} if trial['kind'] in ('actuator', 'timing') else {2,3,5,6,7,8,9,10,11}
        first = next(i for i,s in enumerate(states) if s['received_ns'] >= start['host_monotonic_ns'] and s['flags'] & 2 and s['mode'] in allowed)
        end = first
        while end < len(states) and states[end]['flags'] & 2 and states[end]['mode'] in allowed:
            end += 1
        left = max(0, first-10)
        states = states[left:end]
        first -= left
        t = np.array([s['unwrapped_us'] for s in states], float)/1e6
        t -= t[first]
        if first < 6 or np.any(np.diff(t) <= 0) or np.any(np.diff(t) >= .02-1e-10):
            raise ValueError('continuity/history guard')
        yield dict(id=trial['id'], kind=trial['kind'], t=t, first=first,
            angle=np.unwrap([s['theta'] for s in states]),
            acceleration=np.array([s['acceleration'] for s in states]),
            modes=[s['mode'] for s in states], primary=admitted[trial['id']])


def score(trial, phase, sign=1, delay=0., horizon=.5):
    model = FrozenDrivenModel()
    t, raw, a = trial['t'], trial['angle'], trial['acceleration']
    offset = trial['primary']['phase_baselines'][phase]['phase_offset_rad']
    errors = []
    bymode = {}
    i = trial['first']
    windows = 0
    while i+8 < len(t):
        end = int(np.searchsorted(t, t[i]+horizon+1e-10, side='right'))
        if t[end-1]-t[i] < horizon-.01-1e-10:
            break
        q, w = float(raw[i]-offset), causal_encoder_rate(t, raw, i)
        for j in range(i+1, end):
            ai = int(np.searchsorted(t, t[j-1]-delay+1e-10, side='right'))-1
            if ai < 0:
                raise ValueError('missing causal delay history')
            duration = t[j]-t[j-1]
            n = max(1, math.ceil(duration/.001))
            for _ in range(n):
                q, w = advance(q, w, duration/n, float(sign*a[ai]), model)
            e = math.atan2(math.sin(q+offset-raw[j]), math.cos(q+offset-raw[j]))
            errors.append(e)
            bymode.setdefault(str(trial['modes'][j]), []).append(e)
        windows += 1
        i = end
    def metric(e):
        return dict(samples=len(e), rms_rad=float(np.sqrt(np.mean(np.square(e)))),
                    p95_rad=float(np.quantile(np.abs(e), .95)))
    return dict(windows=windows, **metric(errors), by_mode={m:metric(e) for m,e in bymode.items()})


def main():
    plan = json.loads((HERE/'posthoc-plan.json').read_text())
    primary = json.loads((HERE/'analysis.json').read_text())
    phases = plan['phase_baselines']
    hypotheses = [dict(sign=s, delay_s=d) for s in plan['input_hypotheses']['sign'] for d in plan['input_hypotheses']['causal_delay_s']]
    training = []
    short = []
    for source in primary['training']:
        for trial in trajectories(source):
            short.append(dict(role='training', campaign=source['name'], id=trial['id'],
                scores={p:score(trial,p,horizon=.1) for p in phases}))
            if trial['kind'] == 'timing':
                continue
            row = dict(campaign=source['name'], id=trial['id'], scores={})
            for p in phases:
                row['scores'][p] = [dict(**h, score=score(trial,p,h['sign'],h['delay_s'])) for h in hypotheses]
                expected = trial['primary']['phase_baselines'][p]['scores']['causal_encoder']['prediction_rmse_rad']
                if abs(row['scores'][p][0]['score']['rms_rad']-expected) > 1e-12:
                    raise ValueError('default hypothesis does not reproduce primary')
            training.append(row)
    choice = {}
    for p in phases:
        means = [float(np.mean([tr['scores'][p][i]['score']['rms_rad']**2 for tr in training])) for i in range(len(hypotheses))]
        i = int(np.argmin(means))
        choice[p] = dict(**hypotheses[i], training_equal_trial_mse=means[i], all_training_mse=means)
    frozen = dict(plan_sha256=digest(HERE/'posthoc-plan.json'), primary_sha256=digest(HERE/'analysis.json'),
        diagnostic_source_sha256=digest(Path(__file__)), selection=choice, training_results=training,
        source_hashes={s['name']:s['source_raw_sha256'] for s in primary['training']},
        posthoc=True, new_unseen_validation=False)
    (HERE/'training-choice.json').write_text(json.dumps(frozen,indent=2,allow_nan=False)+'\n')
    validation = []
    for source in primary['validation']:
        for trial in trajectories(source):
            short.append(dict(role='validation_reused_posthoc', campaign=source['name'], id=trial['id'],
                scores={p:score(trial,p,horizon=.1) for p in phases}))
            validation.append(dict(campaign=source['name'], id=trial['id'], scores={
                p:score(trial,p,choice[p]['sign'],choice[p]['delay_s']) for p in phases}))
    result = dict(training_choice_sha256=digest(HERE/'training-choice.json'), selected_input_validation_diagnostic=validation,
        fixed_100ms_diagnostic=short, primary_analysis_unchanged=True, hardware_accepted=False,
        new_unseen_validation=False)
    (HERE/'input-horizon-diagnostic.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(selection=choice, validation=validation),indent=2))


if __name__ == '__main__':
    main()
