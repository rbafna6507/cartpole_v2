"""Informational policy act timing; no timing assertions or device access."""
from pathlib import Path
import json
import statistics
import sys
import time
from cartpole_sdk.contracts import Sample,Observation,Session,UNITS
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.policies.executor_feedback import ExecutorFeedbackPolicy

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
profile=json.loads((ROOT/'evidence/python-control-id-20261016/capture-audit/source/cartpole_sdk/control/tuned-20261016-bw10.json').read_text())['parameters']
profile['rail']=.309037507
parameters=ControllerParameters(**profile)
quantities=('position','velocity','angle','angular_velocity','acceleration','brake_direction')
observations=[]
for i in range(1000):
    t=i*4_000_000
    samples=tuple(Sample('pole' if q in ('angle','angular_velocity') else 'cart',q,
        'simulation',value,UNITS[q],'sim','benchmark','valid',None,'estimated',t,t,t)
        for q,value in zip(quantities,(0.,0.,.02,0.,0.,0.)))
    observations.append(Observation('benchmark','clock',i*4,t,'benchmark',samples))
results=[]
for option in (None,2,3):
    batches=[]
    for repeat in range(5):
        policy=ExecutorFeedbackPolicy(tuple(s.channel for s in observations[0].samples),
            parameters=parameters,max_gap_periods=option)
        policy.reset(Session('benchmark','clock'))
        start=time.perf_counter_ns()
        for observation in observations:
            assert policy.act(observation) is not None
        batches.append((time.perf_counter_ns()-start)/1e9)
    results.append(dict(max_gap_periods=option,calls_per_batch=1000,batch_seconds=batches,
        median_ms_per_call=statistics.median(batches),max_batch_ms_per_call=max(batches)))
(OUT/'benchmark.json').write_text(json.dumps(dict(python=sys.version,
    method='5 x 1000 policy act calls, prebuilt current observations, 250 Hz balanced feedback; timing informational only',
    results=results),indent=2)+'\n')
print(json.dumps(results,indent=2))
