#!/usr/bin/env python3
"""Verify recovered actors against existing console start/run guards offline."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
import math
import sys
from pathlib import Path

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.learning.balance_hardware import _load_policy

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests'))
from test_balance_hardware import rehearsal

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step',type=int,choices=(102400,460800),required=True)
    args=parser.parse_args()
    path=ROOT/f'training/candidates/combined-recovery-20261021-step{args.step:09d}/actor.json'
    baseline=json.loads((ROOT/'training/candidates/balance-recovery-20261021/actor.json').read_text())
    actor=json.loads(path.read_text())
    same_fields=('executor_parameters','observation_contract','action_scale_m_s2','rate_hz','runtime_sha256')
    for name in same_fields:
        assert actor[name]==baseline[name],name
    policy=_load_policy(path,guard_profile='rig',inference_backend='numpy')
    with rehearsal(state=dict(x=0.,velocity=0.,theta=0.,angle_hat=0.,omega=0.)) as rig:
        policy.reset(rig.session)
        policy.validate_start(rig.control_observation())
        assert policy.act(rig.control_observation()) is not None
        rig.wait_state()
        rig._state=replace(rig._state,theta=math.pi,angle_hat=math.pi)
        rig._history[rig._state.unwrapped_tick]=rig._state
        fallen=rig.control_observation()
        # Scripted hardware-schema observation, same admitted session, now fallen.
        assert policy.act(fallen) is not None
        policy.reset(rig.session)
        try:
            policy.validate_start(fallen)
        except ValidationError as exc:
            rejection=str(exc)
            assert 'upright start' in rejection
        else:
            raise AssertionError('hanging start unexpectedly admitted')
        assert not any(c[1] in ('ARM','A') for c in rig.commands)
    report=dict(step=args.step,actor_file_sha256=sha256(path.read_bytes()).hexdigest(),
        same_as_preserved_actor_fields=list(same_fields),numpy_load_pass=True,upright_start_pass=True,
        hanging_start_rejected=True,hanging_start_rejection=rejection,
        fallen_angle_after_upright_admission_emits_action=True,
        run_limits=policy.run_limits,hardware_accepted=False,
        scope='Existing scripted Rig fixture and synthetic telemetry only; no serial or hardware acceptance.')
    with (OUT/f'console-admission-{args.step:09d}.json').open('x') as stream:
        json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=='__main__':
    main()
