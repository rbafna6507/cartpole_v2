#!/usr/bin/env python3
"""Read-only, no-device independent checks of the governed simulation interface."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import math
import sys
from types import SimpleNamespace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();repo=args.repo.resolve()
    if args.output.exists():raise FileExistsError('choose a new report path')
    sys.path.insert(0,str(repo/'src'))
    from cartpole_sdk.contracts import Session
    from cartpole_sdk.rig.client import Rig
    from cartpole_sdk.rig.protocol import State
    from cartpole_sdk.policies.rig_observation import encode_rig_observation,rig_channels
    from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv,RigObservationConfig
    from cartpole_sdk.sim.config import SimulationConfig
    from cartpole_sdk.control.parameters import ControllerParameters
    import numpy as np

    # Invoke the actual stateless SDK encoding methods on a preserved STATE.
    # No Rig constructor, transport, or device method is used.
    source=next((repo/'evidence/system-id-20261017').glob('raw-pulse-training/pulse-pos10-short-01/rig-*.jsonl.gz'))
    raw=gzip.decompress(source.read_bytes())
    state=next(State(**r['state']) for r in map(json.loads,raw.splitlines()) if r.get('type')=='state' and r['state']['mode']==12 and abs(r['state']['acceleration'])>.1)
    context=SimpleNamespace(state=state,session=Session(str(state.sid),f'teensy:{state.sid}'),_require=lambda:None,_fresh=lambda state:None)
    context._observation=lambda value:Rig._observation(context,value)
    wire=Rig.control_observation(context)
    for choice,angle in (('raw',state.theta),('filtered',state.angle_hat)):
        encoded=encode_rig_observation(wire,rig_channels(angle_source=choice))
        expected=[state.x,state.velocity,math.sin(angle),math.cos(angle),state.omega,state.acceleration,state.brake_direction]
        np.testing.assert_array_equal(encoded['state'],expected)
        assert encoded['valid']==[1]*7 and encoded['age_s']==[0.]*7
    p=ControllerParameters(rail=.308962494,bw=6.)
    config=SimulationConfig(rail_half_m=p.rail,control_steps=10,max_steps=100)
    timing=[]
    for telemetry,command in ((0,0),(1,1),(3,3),(9,0),(9,3)):
        env=RigCartpoleEnv(config,parameters=p,observation_config=RigObservationConfig(telemetry_delay_steps=telemetry,command_delay_steps=command))
        first,info=env.reset(seed=123)
        assert first['valid'].all() and not first['age_s'].any()
        for count in range(30):
            obs,reward,ended,truncated,info=env.step([0.])
            assert not obs['age_s'].any()
            if ended:break
        expected_fault=telemetry+command>10
        assert ended==expected_fault,(telemetry,command,info)
        timing.append(dict(telemetry_ms=telemetry,command_ms=command,decisions=count+1,ended=ended,reason=info['fault_reason'],physical_time_ns=info['physical_time_ns'],snapshot_ns=info['available_ns']))
        env.close()
    env=RigCartpoleEnv(config,parameters=p,observation_config=RigObservationConfig(dropout_probability=1.))
    env.reset(seed=3)
    for count in range(3):obs,reward,ended,truncated,info=env.step([0.])
    assert ended and info['fault_reason']=='action lease expired'
    env.close()
    files=['src/cartpole_sdk/sim/rig_gym_env.py','src/cartpole_sdk/policies/rig_observation.py','src/cartpole_sdk/sim/executor.py','src/cartpole_sdk/rig/client.py','tests/test_rig_gym_env.py']
    report=dict(scope='Independent offline interface review; not physical model validation',blocking_findings=[],resolved_findings=['Policy age now uses same board-snapshot proxy as the actual SDK; actual transport age is diagnostic-only.','Causal reset warmup aligns100Hz decisions with delayed telemetry delivery and removes the false3ms+3ms lease gap.','Unusable telemetry ignores numeric Gym actions and lets the original lease expire without fresh demand.'],checks=dict(actual_sdk_raw_and_filtered_codec=True,missing_telemetry_returns_terminal_transition=True,timing_matrix=timing),reviewed_behavior=['Raw acceleration enters the binary32 governor once per1ms tick.','Quantized raw angle initializes a zero-rate causal observer; no true omega in policy channels.','Step count and commanded velocity/acceleration are explicit estimates; force saturation terminates unsupported tracking.','Action expiry remains observed_snapshot+TTL; command transport never renews it.','The shared policy codec selects explicit channels and never reads simulation diagnostics or truth.'],limitations=['Plant still assumes ideal cart acceleration tracking below a declared force ceiling; cart step ISR phase/backlash/missed steps and global magnetic calibration are unvalidated.','Initial healthy snapshot is an explicit preflight assumption; delayed reset advances real model time under zero demand.','With100Hz control and20ms TTL, combined transport delays above10ms can legitimately create gaps between leases.','Faulted reset states outside the declared startup assumptions are not a physical safe-start demonstration.'],source_sha256={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in files},sdk_replay_raw_sha256=hashlib.sha256(raw).hexdigest(),review_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['checks'],indent=2))

if __name__=='__main__':main()
