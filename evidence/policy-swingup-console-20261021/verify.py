#!/usr/bin/env python3
"""Offline numeric actor/boundary verification. Never opens a device.

Optional saved simulation traces check wrapper admission and numerical parity;
this is replay of observations, not a new closed-loop simulation or hardware test.
The raw guard angle is synthetically set equal to the trace's filtered angle.
"""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
import math
from pathlib import Path

from cartpole_sdk.contracts import Channel, Observation, Sample, Session, UNITS, ValidationError
from cartpole_sdk.learning import balance_hardware
from cartpole_sdk.learning.balance_hardware import _load_policy


def observation(policy, session, values, sequence):
    now = sequence*10_000_000
    channels = (*policy.channels, Channel('pole', 'angle', 'magnetic', 'encoder-zero'))
    samples = tuple(Sample(c.entity, c.quantity, c.source, float(v), UNITS[c.quantity], c.frame_id,
        'offline-synthetic', 'valid', None, 'estimated', now, now, now)
        for c, v in zip(channels, (*values, values[2])))
    return Observation(session.session_id, session.clock_id, sequence, now, 'offline', samples)


def verify(root, traces_root=None):
    assert Path(balance_hardware.__file__).resolve() == root/'src/cartpole_sdk/learning/balance_hardware.py'
    results = []
    session = Session('offline-swingup-verification', 'offline-monotonic')
    for step in (102400, 460800):
        path = root/f'training/candidates/combined-recovery-20261021-step{step:09d}-rail1mm/actor.json'
        policy = _load_policy(path, guard_profile='rig', start_mode='hanging', inference_backend='numpy',
                              max_acceleration=25.)
        upright = _load_policy(path, guard_profile='rig', inference_backend='numpy')
        policy.reset(session); upright.reset(session)
        first = observation(policy, session, (0., 0., math.pi, 0., 0., 0.), 0)
        # Opposite wrap representations must both be accepted as down.
        first = replace(first, samples=tuple(replace(s, value=-math.pi)
            if s.source=='magnetic' and s.quantity=='angle' else s for s in first.samples))
        policy.validate_start(first)
        try:
            upright.validate_start(first)
        except ValidationError as exc:
            assert 'upright' in str(exc)
        else:
            raise AssertionError('ordinary run admitted a hanging start')
        actions = [policy.act(first)]
        for i, theta in enumerate((2., .5, 0., -.5, -math.pi), 1):
            actions.append(policy.act(observation(policy, session, (.02, .1, theta, 5., 1., 1.), i)))
        assert all(a is not None and abs(a.acceleration_m_s2)<=25 for a in actions), policy.fault_reason
        replay = []
        if traces_root:
            for trace in sorted((traces_root/f'step-{step:09d}-nominal-numpy/traces').glob('nominal-hanging-*.jsonl')):
                policy.reset(session)
                count, error = 0, 0.
                for row in map(json.loads, trace.read_text().splitlines()):
                    x, v, sin_theta, cos_theta, omega, acceleration, brake = row['actor_observation']['state']
                    obs = observation(policy, session,
                        (x, v, math.atan2(sin_theta, cos_theta), omega, acceleration, brake), count)
                    action = policy.act(obs)
                    assert action is not None, (trace.name, count, policy.fault_reason)
                    error = max(error, abs(action.acceleration_m_s2-row['requested_raw_action_m_s2']))
                    count += 1
                assert count == 2500 and error < 1e-5, (trace.name, count, error)
                replay.append(dict(trace=trace.name, sha256=sha256(trace.read_bytes()).hexdigest(),
                                   actions=count, max_difference_m_s2=error))
            assert len(replay)==4
        results.append(dict(actor=str(path.relative_to(root)), actor_file_sha256=sha256(path.read_bytes()).hexdigest(),
            actor_content_sha256=policy.actor['content_sha256'], task=policy.task,
            hanging_admission_pass=True, upright_mode_rejects_hanging=True,
            continuation_through_horizontal_upright_and_braking_pass=True,
            start_limits=policy.start_limits, run_limits=policy.run_limits, replay=replay))
    return dict(scope='Offline synthetic boundary verification and optional saved simulation observation replay; '
        'raw guard angle synthesized from filtered angle; no hardware or closed-loop qualification.',
        source_file_sha256=sha256(Path(balance_hardware.__file__).read_bytes()).hexdigest(),
        root=str(root), checks_passed=True, actors=results, hardware_accepted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--traces-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.root.resolve(), args.traces_root)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(checks_passed=True, actors=len(report['actors']),
                         replay_actions=sum(t['actions'] for a in report['actors'] for t in a['replay']),
                         report=str(args.output))))


if __name__ == '__main__':
    main()
