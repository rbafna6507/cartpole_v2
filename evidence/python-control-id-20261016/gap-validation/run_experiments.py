"""Offline 1 ms MuJoCo + executor rollouts; no rig/network imports or devices.

Scheduled missing host decisions leave the prior 20 ms anchored action active.
Physics, sensing, governor and lease checks continue at every 1 ms tick. These
provisional plant experiments do not establish hardware stability or sensor
observer fidelity. Compare paired initial states with unchanged live gains.
"""
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import math
import platform
import sys
import time
import mujoco
from cartpole_sdk.contracts import ActionRequest
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.policies.executor_feedback import ExecutorFeedbackPolicy
from cartpole_sdk.sim import SimulationConfig
from cartpole_sdk.sim.executor import ExecutorSimulation

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
PROFILE=ROOT/'evidence/python-control-id-20261016/capture-audit/source/cartpole_sdk/control/tuned-20261016-bw10.json'
parameters=json.loads(PROFILE.read_text())['parameters']
parameters['rail']=.309037507
P=ControllerParameters(**parameters)


def run(name,state,duration_ms,option,skip,decision_stop_ms=None):
    config=SimulationConfig(control_steps=1,max_steps=duration_ms+1,rail_half_m=P.rail,effective_length_m=P.leff)
    sim=ExecutorSimulation(config,parameters=P)
    sim.reset(state=state,seed=29)
    observation=sim.control_observation()
    policy=ExecutorFeedbackPolicy(tuple(s.channel for s in observation.samples),parameters=P,
        rate_hz=250,max_gap_periods=option)
    policy.reset(sim.session)
    actions=0;max_x=abs(state[0]);max_v=abs(state[1]);max_a=max_jerk=0.;last_a=0.
    mode_ticks={};transitions=[];last_mode=None;captures=[];max_abs_balance_angle=0.;decisions=[]
    began=time.perf_counter_ns()
    try:
        for tick in range(duration_ms):
            request=None
            if tick%4==0 and tick not in skip and (decision_stop_ms is None or tick<decision_stop_ms):
                observation=sim.control_observation()
                action=policy.act(observation)
                decisions.append(dict(board_ns=observation.available_ns,observation_sequence=observation.sequence,
                    action=None if action is None else action.acceleration_m_s2,
                    mode=policy.mode,x=sim.ground_truth.x,theta=sim.ground_truth.theta,
                    cadence=policy.timing_diagnostics()))
                if policy.mode!=last_mode:
                    transitions.append(dict(time_ms=tick,mode=policy.mode))
                    if policy.mode=='balance':captures.append(tick)
                    last_mode=policy.mode
                if action is None:break  # production runner STOPs immediately on a policy fault
                actions+=1
                request=ActionRequest(observation.session_id,observation.clock_id,actions,
                    observation.sequence,observation.available_ns,observation.available_ns+20_000_000,
                    action.acceleration_m_s2)
            sim.step(request)
            mode_ticks[policy.mode]=mode_ticks.get(policy.mode,0)+1
            a=float(sim.motion.acceleration)
            max_x=max(max_x,abs(sim.ground_truth.x));max_v=max(max_v,abs(sim.ground_truth.v))
            max_a=max(max_a,abs(a));max_jerk=max(max_jerk,abs(a-last_a)/.001);last_a=a
            if policy.mode=='balance':max_abs_balance_angle=max(max_abs_balance_angle,abs(sim.ground_truth.theta))
            if sim.terminated or sim.truncated:break
        result=dict(name=name,initial_state=state,target_duration_ms=duration_ms,
            simulated_ns=sim.ground_truth.time_ns,max_gap_periods=option,
            skipped_decision_ms=sorted(skip),actions=actions,policy_fault=policy.fault_reason,
            executor_fault=sim.fault_reason,cadence=policy.timing_diagnostics(),
            max_abs_x=max_x,max_abs_v=max_v,max_abs_acceleration=max_a,max_abs_jerk=max_jerk,
            max_abs_balance_angle=max_abs_balance_angle,first_capture_ms=captures[0] if captures else None,
            mode_ticks=mode_ticks,transitions=transitions,final_state=asdict(sim.ground_truth),
            runtime_s=(time.perf_counter_ns()-began)/1e9)
        (OUT/f'{name}-decisions.json').write_text(json.dumps(decisions,indent=2)+'\n')
        return result
    finally:sim.close()


def gaps(duration_ms,maximum,phases=(200,700)):
    skipped=set()
    # Two long gaps per 1100 ms cycle. The 100 ms slack avoids coupling
    # endpoint placement to the exact window boundary. Early phases exercise
    # braking, return, and capture approach before those transients finish.
    for cycle in range(0,duration_ms,1100):
        for phase in phases:
            skipped.add(cycle+phase)
            if maximum==3:skipped.add(cycle+phase+4)
    return {t for t in skipped if t<duration_ms}


if __name__=='__main__':
    cases=[('hanging',(0.,0.,math.pi,0.),8000),
           ('balance',(0.,0.,.02,0.),5000),
           ('capture',(.02,.15,.15,-.4),5000),
           ('approach',(.02,.35,.2,-.5),5000),
           ('rail-right',(.295,.1,2.,0.),4000),
           ('rail-left',(-.295,-.1,-2.,0.),4000)]
    results=[]
    for label,state,duration in cases:
        for option in (None,2,3):
            name=f'{label}-'+('strict' if option is None else f'gap{option}')
            early=label.startswith('rail') or label=='approach'
            skipped=set() if option is None else gaps(duration,option,phases=(20,80) if early else (200,700))
            result=run(name,state,duration,option,skipped)
            results.append(result)
            print(json.dumps({k:result[k] for k in ('name','simulated_ns','policy_fault','executor_fault','first_capture_ms','max_abs_x','cadence')}),flush=True)
    checks=[('strict-rejects-8ms',None,{4},None,12,'cadence',None),
            ('gap3-rejects-16ms',3,{4,8,12},None,20,'cadence',None),
            ('gap3-rejects-third',3,{4,12,16,24},None,32,'gap budget',None),
            ('gap3-no-renewal-20ms',3,set(),4,25,None,'action lease expired')]
    for name,option,skip,stop,duration,policy_fault,executor_fault in checks:
        result=run(name,(0.,0.,.02,0.),duration,option,skip,stop)
        assert (policy_fault in result['policy_fault']) if policy_fault else result['policy_fault'] is None
        assert result['executor_fault']==executor_fault
        if executor_fault:assert result['simulated_ns']==20_000_000
        results.append(result)
    sources=['src/cartpole_sdk/policies/executor_feedback.py','src/cartpole_sdk/rig/policy.py',
             'src/cartpole_sdk/sim/executor.py','src/cartpole_sdk/control/motion.py',
             'tests/test_executor_feedback_policy.py',str(Path(__file__).resolve().relative_to(ROOT)),str(PROFILE.relative_to(ROOT))]
    report=dict(status='offline provisional simulation; no hardware stability claim',
        python=sys.version,platform=platform.platform(),mujoco=mujoco.__version__,
        parameters=asdict(P),physics_tick_ns=1_000_000,nominal_decision_period_ns=4_000_000,
        action_ttl_ns=20_000_000,source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
        cases=results)
    (OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Saved',OUT/'results.json',flush=True)
