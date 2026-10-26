"""Freeze console Python AUTO into a portal artifact; replay its recorded decisions.

No hardware access, parameter writes, policy defaults, or controller retuning.
The generated artifact imports the same ExecutorFeedbackPolicy as the console.
"""
from dataclasses import fields
import argparse
import hashlib
import json
from pathlib import Path

from cartpole_sdk.contracts import Channel
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.policies.executor_feedback import ExecutorFeedbackPolicy
from cartpole_sdk.recording import _observation, _session, canonical_json, strict_json_loads

CHANNELS = (
    Channel('cart','position','step','cart-step-home'),
    Channel('cart','velocity','step','cart-step-home'),
    Channel('pole','angle','magnetic_filtered','encoder-zero'),
    Channel('pole','angular_velocity','magnetic','encoder-zero'),
    Channel('cart','acceleration','step','cart-step-home'),
    Channel('cart','brake_direction','step','cart-step-home'))
RAW = Channel('pole','angle','magnetic','encoder-zero')


def make_policy(values, *, rate_hz, max_gap_periods=None):
    if type(values) is not dict or set(values)!={f.name for f in fields(ControllerParameters)}:
        raise ValueError('complete live parameter snapshot required, including measured rail')
    return ExecutorFeedbackPolicy(CHANNELS,parameters=ControllerParameters(**values),
        rate_hz=rate_hz,start_mode='auto',raw_angle_channel=RAW,max_gap_periods=max_gap_periods)


def build_source(values, *, rate_hz, max_gap_periods=None):
    make_policy(values,rate_hz=rate_hz,max_gap_periods=max_gap_periods)
    # All interpolated objects were validated above; no user strings enter code.
    return '''"""Frozen Python AUTO baseline. Explicit native snapshot, no hardware writes."""
from cartpole_sdk.contracts import Channel, ValidationError
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.policies.executor_feedback import ExecutorFeedbackPolicy
PARAMETERS = %r
RATE_HZ = %r
MAX_GAP_PERIODS = %r

class PortalPythonAuto(ExecutorFeedbackPolicy):
    def act(self, observation):
        action = super().act(observation)
        if action is None and self.fault_reason:
            raise ValidationError('host policy fault: ' + self.fault_reason)
        return action

def create_policy():
    channels = %s
    return PortalPythonAuto(channels, parameters=ControllerParameters(**PARAMETERS),
        rate_hz=RATE_HZ, start_mode='auto', max_gap_periods=MAX_GAP_PERIODS,
        raw_angle_channel=Channel('pole','angle','magnetic','encoder-zero'))
''' % (values,rate_hz,max_gap_periods,repr(CHANNELS))


def replay_decisions(records, values, *, rate_hz, max_gap_periods=None):
    """Reconstruct phases from policy_call records; never step on uncalled samples.

    Missing observations fail explicitly. Action matching makes SDK drift or
    missing data visible; this is diagnostic replay, not physical validation.
    """
    policy=make_policy(values,rate_hz=rate_hz,max_gap_periods=max_gap_periods)
    current=None;rows=[];pending=None;ready=False
    for record in records:
        kind=record.get('type')
        if kind=='session':
            if ready:raise ValueError('multiple sessions; replay one attempt at a time')
            policy.reset(_session(record['session']));ready=True
        elif kind=='observation':current=_observation(record['observation'])
        elif kind=='policy_call':
            if not ready:raise ValueError('missing session')
            if current is None or current.sequence!=record['observation_sequence']:
                raise ValueError('missing observation for policy call; replay cannot interpolate')
            action=policy.act(current)
            samples={s.channel:s.value for s in current.samples}
            pending=dict(observation_sequence=current.sequence,board_ns=current.available_ns,
                phase=policy.mode,theta=samples.get(CHANNELS[2]),raw_theta=samples.get(RAW),
                omega=samples.get(CHANNELS[3]),x=samples.get(CHANNELS[0]),
                velocity=samples.get(CHANNELS[1]),applied_acceleration=samples.get(CHANNELS[4]),
                requested_acceleration=None if action is None else action.acceleration_m_s2,
                fault_reason=policy.fault_reason,matches_recorded_action=None)
            rows.append(pending)
        elif kind=='action_request':
            if pending is None or pending['observation_sequence']!=record['observation_sequence']:
                raise ValueError('action without matching policy call')
            expected=pending['requested_acceleration'];actual=record['acceleration_m_s2']
            pending['recorded_acceleration']=actual
            pending['matches_recorded_action']=(expected==actual if expected is None or actual is None
                                                else abs(expected-actual)<=1e-6)
            pending=None
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path,help='Complete parameter object or object with parameters key')
    parser.add_argument('--rate',type=int,choices=(100,250),required=True)
    parser.add_argument('--max-gap-periods',type=int,choices=(2,3))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--replay',type=Path,help='Unzipped portal telemetry.jsonl; output diagnostic JSON')
    args=parser.parse_args()
    snapshot=strict_json_loads(args.snapshot.read_text())
    values=snapshot.get('parameters',snapshot)
    source=build_source(values,rate_hz=args.rate,max_gap_periods=args.max_gap_periods)
    if args.replay:
        records=[strict_json_loads(line) for line in args.replay.read_text().splitlines() if line]
        rows=replay_decisions(records,values,rate_hz=args.rate,max_gap_periods=args.max_gap_periods)
        args.output.write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
    else:
        args.output.write_text(source)
        import cartpole_sdk.policies.executor_feedback as implementation
        manifest=dict(controller='ExecutorFeedbackPolicy',mode='auto',rate_hz=args.rate,
            max_gap_periods=args.max_gap_periods,parameters=values,
            parameter_sha256=hashlib.sha256(canonical_json(values).encode()).hexdigest(),
            policy_sha256=hashlib.sha256(source.encode()).hexdigest(),
            local_controller_source_sha256=hashlib.sha256(Path(implementation.__file__).read_bytes()).hexdigest(),
            hardware_validated=False,requires_matching_worker_rate=True,
            requires_worker_acceleration_ceiling=max(values['amax_s'],values['amax_b']))
        args.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
