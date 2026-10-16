"""Offline only: exact waveform bounds and 1 ms governor/MuJoCo pulse trials."""
from dataclasses import asdict,replace
import importlib.util
import json
import math
from pathlib import Path
from cartpole_sdk.contracts import ActionRequest,ValidationError
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.sim.config import SimulationConfig,SensorConfig
from cartpole_sdk.sim.executor import ExecutorSimulation

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ringdown_probe',HERE/'ringdown_probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

def rollout(amplitude_mm):
    parameters=ControllerParameters(rail=.3091125,bw=10.)
    config=SimulationConfig(control_steps=1,max_steps=13000,rail_half_m=parameters.rail,
        effective_length_m=.124,max_acceleration_m_s2=3.,max_action_ttl_ns=20_000_000)
    executor=ExecutorSimulation(config,SensorConfig(),parameters=parameters)
    clock=[0];rows=[]
    policy=probe.RingdownPolicy(probe.CHANNELS,amplitude_m=amplitude_mm/1000,
        initial_hanging=math.pi,clock_ns=lambda:clock[0],record=lambda **row:rows.append(row))
    failure=None;maximum={'x':0.,'v':0.,'theta_departure':0.,'omega':0.,'executed_acceleration':0.,'executed_jerk':0.}
    last_acceleration=0.;post_peak=0.;guard_fault=None
    try:
        observation=executor.reset(state=(0.,0.,math.pi,0.));policy.reset(executor.session)
        for i in range(1269):
            clock[0]=observation.available_ns
            # Simulation-only source adapter; provenance remains explicitly
            # simulation and does not assert physical step tracking or sensing.
            samples=tuple(replace(s,source=c.source,frame_id=c.frame_id) for s,c in zip(observation.samples,probe.CHANNELS))
            sensed=replace(observation,samples=samples)
            try:intent=policy.act(sensed)
            except ValidationError as exc:guard_fault=str(exc);break
            request=ActionRequest(sensed.session_id,sensed.clock_id,i+1,sensed.sequence,
                sensed.available_ns,sensed.available_ns+20_000_000,intent.acceleration_m_s2)
            for tick in range(10):
                observation=executor.step(request if tick==0 else None);truth=executor.ground_truth
                if executor.terminated:failure=executor.fault_reason;break
                a=executor.diagnostics.executed_acceleration_m_s2
                maximum={k:max(maximum[k],abs(v)) for k,v in dict(x=truth.x,v=truth.v,
                    theta_departure=probe.wrap(truth.theta-math.pi),omega=truth.omega,
                    executed_acceleration=a,executed_jerk=(a-last_acceleration)/.001).items()}
                last_acceleration=a
                if truth.time_ns>=650_000_000:post_peak=max(post_peak,abs(probe.wrap(truth.theta-math.pi)))
            if failure:break
        final=asdict(executor.ground_truth)
    finally:executor.close()
    return dict(amplitude_mm=amplitude_mm,policy_guard_fault=guard_fault,executor_fault=failure,
        completed=guard_fault is None and failure is None,maxima=maximum,residual_peak_rad=post_peak,
        final=final,policy=policy.summary(),config=asdict(config),parameters=asdict(parameters),
        note='1 ms governor/physics, 100 Hz decisions, 20 ms anchored lease; maxima measured on every 1 ms physics/governor tick',references=rows)

def lease_expiry():
    executor=ExecutorSimulation(SimulationConfig(control_steps=10,max_steps=10,max_action_ttl_ns=20_000_000))
    try:
        o=executor.reset(state=(0.,0.,math.pi,0.))
        request=ActionRequest(o.session_id,o.clock_id,1,o.sequence,0,20_000_000,0.)
        executor.step(request);executor.step(None);executor.step(None)
        return dict(fault=executor.fault_reason,board_ns=executor.ground_truth.time_ns)
    finally:executor.close()

if __name__=='__main__':
    bounds={str(mm):probe.waveform_bounds(mm/1000) for mm in probe.AMPLITUDES_MM}
    trials=[rollout(mm) for mm in probe.AMPLITUDES_MM]
    report=dict(scope='offline provisional MuJoCo; not validated hardware tracking, pole or cart model',
        provenance=probe.provenance(),bounds=bounds,trials=trials,lease_expiry=lease_expiry())
    (HERE/'ringdown-offline-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    for trial in trials:print(json.dumps({k:trial[k] for k in ('amplitude_mm','completed','policy_guard_fault','executor_fault','maxima','residual_peak_rad','policy')}),flush=True)
    print(json.dumps(report['lease_expiry']))
