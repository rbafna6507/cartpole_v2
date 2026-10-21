#!/usr/bin/env python3
"""Record a bounded native two-switch HOME; no gain or reference writes.

Run from a cartpole_v2 checkout with its hardware-enabled Python environment.
Switch-contact coordinates are counted estimates, not dynamic motion truth.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time
from cartpole_sdk.rig import Rig


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', required=True)
    p.add_argument('--expected-reference', required=True, type=int)
    p.add_argument('--expected-home', required=True, type=int)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--execute', action='store_true', required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    report = {'completed': False, 'interpretation': 'Limit contacts can reveal net endpoint/count discrepancy. They do not independently measure cart acceleration, dynamic lag, metric scale or canceling missed steps.'}
    try:
        with Rig(a.port, rate_hz=100, log_dir=a.output/'raw', record_capacity=20000) as rig:
            try:
                info = rig.get_info()
                before = rig.get_parameters()
                state = rig.wait_state()
                report['before'] = {'info': asdict(info), 'parameters': before, 'state': asdict(state)}
                if info.encoder_upright_raw != a.expected_reference or info.home_epoch != a.expected_home:
                    raise RuntimeError('Unexpected reference/home identity')
                if (state.enabled or state.mode != 0 or state.fault or not state.healthy or
                    not state.homed or not state.switch_profile or state.flags & 48 or abs(state.x) > .01):
                    raise RuntimeError('HOME audit needs a healthy disabled centered rig and released switches')
                deadline = time.monotonic()+2
                while time.monotonic() < deadline:
                    state = rig.wait_state(after_tick=state.tick, timeout=.2)
                    if abs(state.theta) < 2.5 or abs(state.omega) > .15 or state.enabled:
                        raise RuntimeError('Pole must be quietly hanging before HOME audit')
                rig.home()
                deadline = time.monotonic()+80
                seen_home = False
                while time.monotonic() < deadline:
                    state = rig.wait_state(after_tick=state.tick, timeout=.2)
                    seen_home |= state.mode == 13
                    if state.fault or not state.healthy:
                        raise RuntimeError('Homing health/fault failure')
                    if seen_home and state.mode == 0 and not state.enabled and state.homed:
                        break
                else:
                    raise RuntimeError('Homing audit exceeded 80 s deadline')
                rig.stop()
                after_info = rig.get_info()
                after_parameters = rig.get_parameters()
                report['after'] = {'info': asdict(after_info), 'parameters': after_parameters, 'state': asdict(rig.state)}
                if after_info.encoder_upright_raw != a.expected_reference or after_info.home_epoch != a.expected_home+1:
                    raise RuntimeError('Homing completion identity did not match')
                report['parameter_changes'] = {k: [v, after_parameters[k]] for k,v in before.items() if after_parameters[k] != v}
                report['completed'] = True
            finally:
                try:
                    rig.stop()
                    report['final_state'] = asdict(rig.state)
                    report['stop_confirmed'] = not rig.state.enabled and rig.state.mode == 0
                except BaseException as exc:
                    report['stop_error'] = str(exc)
    except BaseException as exc:
        report['error'] = str(exc)
        raise
    finally:
        (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2), flush=True)

if __name__ == '__main__':
    main()
