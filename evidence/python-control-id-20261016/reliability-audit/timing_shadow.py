"""Numerical stale-observation sensitivity on a fixed recorded trajectory.

This is not a closed-loop prediction, a physical counterfactual, or a measured
transport delay. It uses only the first 1.1 seconds of the saved native balance
window, whose telemetry is sampled every 4 ms.
"""
import argparse
import json
from pathlib import Path

from audit_reliability import ControllerParameters, gains, balance, sha, stats


def analyze(path):
    data = json.loads(path.read_text())
    p = ControllerParameters(**data['report']['parameters'])
    k = gains(p)
    states = {s['unwrapped_tick']: s for s in data['selected_states'] if s['mode']==3}
    result = []
    for lag_ms in (0, 4, 8, 12):
        differences = []
        for tick, current in states.items():
            past = states.get(tick-lag_ms)
            if past is not None:
                request = balance(k, *[past[z] for z in ('angle_hat','omega','x','velocity')])
                differences.append(request-current['demand'])
        result.append(dict(snapshot_lag_ms=lag_ms, request_difference_m_s2=stats(differences),
                           maximum_absolute_difference_m_s2=max(abs(v) for v in differences)))
    return dict(source_path=str(path), source_sha256=sha(path), script_sha256=sha(__file__),
                native_run=data['report']['path'], mode=3, duration_s=1.1,
                hardware_activity=False, results=result,
                interpretation='Fixed recorded trajectory only. Differences quantify stale-input sensitivity; they do not predict actual stability or measure transport delay. Same-snapshot discrepancy includes telemetry rounding and observation of motion after a control tick.')


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--native',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():raise SystemExit('refusing to overwrite evidence')
    result=analyze(args.native)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['results'],indent=2))
