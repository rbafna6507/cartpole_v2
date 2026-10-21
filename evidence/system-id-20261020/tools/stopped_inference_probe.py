#!/usr/bin/env python3
"""Time the actual numeric actor on stopped live telemetry; never arm or send actions.

Run with the hardware extra from the project root. This measures inference and
observed scheduling only. Hanging observations are outside a balance actor's
training region and are not a test of balance quality or powered deadlines.
"""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import time

from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.rig_observation import rig_channels
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.neural_runner import run_neural_policy
from cartpole_sdk.rig.runtime import defer_cyclic_gc
from cartpole_sdk.identification.timing_capture import _stats


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--actor',type=Path,required=True)
    p.add_argument('--expected-reference',type=int,required=True)
    p.add_argument('--seconds',type=float,default=25.)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not 0<a.seconds<=60 or not 0<=a.expected_reference<4096:p.error('invalid bounded duration/reference')
    a.output.mkdir(parents=True,exist_ok=False)
    actor=load_neural_policy(a.actor,channels=rig_channels(angle_source='raw'))
    report=dict(actor_sha256=sha256(a.actor.read_bytes()).hexdigest(),script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),execute=False,hardware_accepted=False,completed=False)
    samples=[]
    try:
        with defer_cyclic_gc(), Rig(a.port,rate_hz=100,log_dir=a.output,max_host_age_s=.02) as rig:
            info=rig.get_info()
            if info.encoder_upright_raw!=a.expected_reference:raise ValueError('saved reference changed')
            report['initial_info']=asdict(info)
            act=actor.act
            def timed(observation):
                if rig.state.enabled:raise ValueError('shadow probe requires disabled motor')
                start=time.monotonic_ns()
                result=act(observation)
                end=time.monotonic_ns()
                samples.append(dict(start_ns=start,end_ns=end,sequence=observation.sequence))
                return result
            actor.act=timed
            try:
                report['result']=run_neural_policy(rig,actor,development_only=True,execute=False,duration_s=a.seconds)
                report['completed']=True
            finally:
                rig.stop()
                report['final_state']=asdict(rig.state)
                report['final_info']=asdict(rig.get_info())
    except Exception as exc:
        report['failure']=repr(exc)
    report['inference_ms']=_stats([(s['end_ns']-s['start_ns'])/1e6 for s in samples])
    report['inter_inference_ms']=_stats([(b['start_ns']-a['start_ns'])/1e6 for a,b in zip(samples,samples[1:])])
    (a.output/'inference-samples.json').write_text(json.dumps(samples)+'\n')
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['completed'] else 1


if __name__=='__main__':raise SystemExit(main())
