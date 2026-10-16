#!/usr/bin/env python3
"""Bounded 100 Hz cart pulse and feedback hold; hardware requires --execute.

The reference is A*sin^4(pi*t/.65), followed by 12 s of active cart feedback.
The hold is feedback-forced, not proof that the physical cart is fixed. Import
and --check-waveform are offline. No home, clear, calibration or SET is issued.
"""
import argparse
from dataclasses import asdict, fields, is_dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
import traceback
from cartpole_sdk.contracts import (Acceleration,Channel,ValidationError,
                                    select_channels,validate_observation)
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.rig.policy import run_policy

PULSE_S=.65
HOLD_S=12.
COMPLETION_PAD_S=.04
AMPLITUDES_MM=(-30,-20,-10,-5,5,10,20,30)
GAP_NS=20_000_000
CHANNELS=(Channel('cart','position','step','cart-step-home'),
          Channel('cart','velocity','step','cart-step-home'),
          Channel('pole','angle','magnetic','encoder-zero'),
          Channel('pole','angular_velocity','magnetic','encoder-zero'))

def amplitude(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value not in tuple(mm/1000 for mm in AMPLITUDES_MM):
        raise ValidationError('amplitude must be exactly signed 5, 10, 20 or 30 mm')
    return value

def wrap(value):return math.atan2(math.sin(value),math.cos(value))

def waveform(t,amplitude_m):
    """Analytic position, velocity, acceleration and jerk; exactly zero endpoints."""
    A=amplitude(amplitude_m)
    if not math.isfinite(t):raise ValueError('finite waveform time required')
    if t<=0 or t>=PULSE_S:return (0.,)*4
    w=math.pi/PULSE_S;u=w*t;s=math.sin(u)
    return (A*s**4,A*w*(math.sin(2*u)-.5*math.sin(4*u)),
            2*A*w*w*(math.cos(2*u)-math.cos(4*u)),
            A*w**3*(-4*math.sin(2*u)+8*math.sin(4*u)))

def waveform_bounds(amplitude_m):
    """Exact continuous reference extrema, independently checked on a 10 us grid.

    For jerk, extrema satisfy cos(2u)=(1 +/- sqrt(129))/16. These
    certify only the analytic reference; measured trajectories retain guards.
    """
    A=abs(amplitude(amplitude_m));w=math.pi/PULSE_S
    c=((1+math.sqrt(129))/16,(1-math.sqrt(129))/16)
    jerk_factor=max(abs(4*math.sqrt(1-z*z)*(4*z-1)) for z in c)
    analytic=(A,3*math.sqrt(3)/4*A*w,4*A*w*w,jerk_factor*A*w**3)
    grid=[0.]*4
    for i in range(65_001):
        for k,value in enumerate(waveform(i/100_000,amplitude_m)):grid[k]=max(grid[k],abs(value))
    return dict(amplitude_m=amplitude_m,pulse_s=PULSE_S,hold_s=HOLD_S,
        grid_interval_s=.00001,analytic_abs_max=analytic,grid_abs_max=grid,
        quantities=('position_m','velocity_m_s','acceleration_m_s2','jerk_m_s3'),
        endpoint_start=waveform(0,amplitude_m),endpoint_end=waveform(PULSE_S,amplitude_m),
        reference_only=True,physical_trajectory_guaranteed=False)

def validate_board(state):
    if not(state.healthy and state.homed and state.switch_profile) or state.flags&48:
        raise ValidationError('requires healthy homed board with both installed switches released')
    if state.mode not in (0,12):raise ValidationError('requires idle or external action mode')

def validate_preflight(state,info):
    validate_board(state)
    if (info.firmware!='executor-v6-measuredrail' or info.encoder_upright_raw!=330 or
            not info.reference_saved or not info.encoder_conf_valid or info.home_epoch!=14):
        raise ValidationError('requires v6, saved reference 330, valid encoder configuration and home epoch 14')
    if state.enabled or state.mode!=0 or state.brake_direction:
        raise ValidationError('requires stopped executor with settled governor')
    if (abs(state.x)>=.003 or abs(state.velocity)>=.005 or abs(state.acceleration)>=.1 or
            abs(state.omega)>=.15 or abs(wrap(state.theta-math.pi))>=.35):
        raise ValidationError('requires centered quiet cart and quietly hanging pole')

def stationary_preflight(rig,info):
    state=rig.state;rig._fresh(state);validate_preflight(state,info)
    first=state.unwrapped_us;initial=state.theta;deadline=time.monotonic()+1.5
    while state.unwrapped_us-first<500_000:
        if time.monotonic()>=deadline:raise ValidationError('quiet preflight deadline exceeded')
        state=rig.wait_state(after_tick=state.unwrapped_tick,timeout=.1)
        rig._fresh(state);validate_preflight(state,info)
        if abs(wrap(state.theta-initial))>.03:raise ValidationError('pole changed during quiet preflight')
    return state.theta

class RingdownPolicy:
    def __init__(self,channels,*,amplitude_m,initial_hanging,record=None,clock_ns=None):
        if tuple(channels)!=CHANNELS:raise ValidationError('exact magnetic/step channels required')
        if not math.isfinite(initial_hanging):raise ValidationError('finite hanging reference required')
        self.channels=tuple(channels);self.amplitude_m=amplitude(amplitude_m)
        self.initial_hanging=initial_hanging;self.record=record
        self.clock_ns=clock_ns if clock_ns is not None else lambda:time.monotonic_ns()
    def reset(self,session):
        self.session=session;self.origin_ns=None;self.previous=None;self.mode='pulse'
        self.clamped_commands=0;self.hold_max_abs_x=0.;self.hold_max_abs_v=0.
        self.last_elapsed_s=0.
    def _read(self,observation):
        validate_observation(self.session,observation)
        selected=select_channels(observation,self.channels,now_ns=observation.available_ns,max_age_ns=GAP_NS-1)
        if len({s.effective_ns for s in selected})!=1:raise ValidationError('requires coherent same-snapshot channels')
        return tuple(s.value for s in selected)
    def validate_start(self,observation):
        x,v,theta,omega=self._read(observation)
        if (abs(x)>=.003 or abs(v)>=.005 or abs(omega)>=.15 or
            abs(wrap(theta-self.initial_hanging))>.03 or abs(wrap(theta-math.pi))>=.35):
            raise ValidationError('start no longer centered, quiet and hanging')
    def act(self,observation):
        host_ns=self.clock_ns();x,v,theta,omega=self._read(observation);now=observation.available_ns
        if self.previous is None:self.validate_start(observation);self.origin_ns=now
        else:
            sequence,board_ns,previous_host=self.previous;board_gap=now-board_ns;host_gap=host_ns-previous_host
            if observation.sequence<=sequence or not 0<board_gap<GAP_NS or not 0<=host_gap<GAP_NS:
                raise ValidationError(f'ringdown cadence fault: seq={observation.sequence} previous={sequence} board_gap_ns={board_gap} host_gap_ns={host_gap}')
        if abs(x)>=.05 or abs(v)>=.3 or abs(wrap(theta-self.initial_hanging))>=1. or abs(omega)>=10.:
            raise ValidationError('measured/estimated trajectory exceeded ringdown guard')
        t=(now-self.origin_ns)/1e9;reference=waveform(t,self.amplitude_m)
        self.mode='pulse' if t<PULSE_S else 'feedback_cart_hold'
        unbounded=reference[2]+80*(reference[0]-x)+14*(reference[1]-v)
        command=max(-3.,min(3.,unbounded));clamped=command!=unbounded
        self.clamped_commands+=int(clamped);self.last_elapsed_s=t
        if t>=PULSE_S:
            self.hold_max_abs_x=max(self.hold_max_abs_x,abs(x));self.hold_max_abs_v=max(self.hold_max_abs_v,abs(v))
        if self.record:self.record(phase=self.mode,t_s=t,observation_sequence=observation.sequence,board_ns=now,
            host_policy_ns=host_ns,x_reference=reference[0],v_reference=reference[1],a_reference=reference[2],
            jerk_reference=reference[3],x=x,v=v,theta=theta,omega=omega,command=command,
            unclamped_command=unbounded,clamped=clamped,tail_is_independent_physical_proof=False)
        self.previous=observation.sequence,now,host_ns
        return Acceleration(command)
    def summary(self):
        return dict(clamped_commands=self.clamped_commands,fit_protocol_deviation_clamped=bool(self.clamped_commands),
            hold_max_abs_x_m=self.hold_max_abs_x,hold_max_abs_v_m_s=self.hold_max_abs_v,
            elapsed_board_s=self.last_elapsed_s,hold_type='feedback_cart_hold',physical_cart_fixed=False)

def plain(value):return asdict(value) if is_dataclass(value) else vars(value)

def run_ringdown(rig,*,amplitude_m,provenance=None):
    """Trusted bounded runner. STOP on preflight, policy, transport or wait failure."""
    failure=None;policy=None;result=None
    try:
        amplitude(amplitude_m)
        if rig.rate_hz!=100:raise ValidationError('ringdown requires 100 Hz telemetry')
        rig._stopped_healthy();parameters=rig.get_parameters()
        names={f.name for f in fields(ControllerParameters)}
        if len(names)!=41 or set(parameters)!=names:raise ValidationError('complete live 41-parameter catalog required')
        ControllerParameters(**parameters)
        info=rig.get_info();initial_hanging=stationary_preflight(rig,info)
        rig._record('ringdown_start',amplitude_m=amplitude_m,parameters=parameters,info=plain(info),
            state=plain(rig.state),initial_hanging=initial_hanging,provenance=provenance or {},rate_hz=100,
            pulse_s=PULSE_S,feedback_hold_s=HOLD_S,completion_pad_s=COMPLETION_PAD_S,ttl_ms=20,
            feedback_kp=80.,feedback_kd=14.,command_limit_m_s2=3.,hardware_validated=False)
        def observe():
            state=rig.state;rig._fresh(state);validate_board(state)
            return rig._observation(state)
        def factory(channels):
            nonlocal policy
            policy=RingdownPolicy(channels,amplitude_m=amplitude_m,initial_hanging=initial_hanging,
                record=lambda **record:rig._record('ringdown_reference',**record))
            return policy
        # 40 ms of additional feedback hold compensates the runner's bounded
        # wall-deadline margin; it never extends the excitation waveform.
        run_policy(rig,factory,channels=CHANNELS,duration_s=PULSE_S+HOLD_S+COMPLETION_PAD_S,
            ttl_ms=20,max_acceleration=3.,observation_provider=observe)
        if policy is None or policy.last_elapsed_s<PULSE_S+HOLD_S:
            raise ValidationError('incomplete board-clock pulse/hold duration')
        result=dict(parameters=parameters,info=plain(info),initial_hanging=initial_hanging,
            amplitude_m=amplitude_m,policy=policy.summary(),hardware_validated=False)
    except BaseException as exc:
        failure=exc;rig._record('ringdown_failure',reason=repr(exc));raise
    finally:
        if policy is not None:rig._record('ringdown_summary',**policy.summary())
        try:
            rig.stop();state=rig.state
            if state.enabled:raise ValidationError('STOP did not confirm disabled executor')
            rig._record('ringdown_stop',confirmed=True,state=plain(state))
        except BaseException as exc:
            rig._record('ringdown_stop',confirmed=False,reason=repr(exc))
            if failure is None:raise
    return result

def provenance():
    import cartpole_sdk.contracts
    root=Path(cartpole_sdk.contracts.__file__).resolve().parent
    paths=[Path(__file__).resolve(),*sorted(root.rglob('*.py'))]
    return dict(python=sys.version,platform=platform.platform(),sdk_root=str(root),
        sources=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths])

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-waveform',action='store_true')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--amplitude-mm',type=int,choices=AMPLITUDES_MM)
    parser.add_argument('--port')
    parser.add_argument('--log-dir',type=Path)
    args=parser.parse_args(argv)
    if args.check_waveform:
        if args.execute:parser.error('offline bounds cannot be combined with execution')
        print(json.dumps({mm:waveform_bounds(mm/1000) for mm in AMPLITUDES_MM},indent=2));return 0
    if not args.execute or args.amplitude_mm is None or not args.port or args.log_dir is None:
        parser.error('hardware requires --execute --amplitude-mm --port --log-dir')
    from cartpole_sdk.rig import Rig
    args.log_dir.mkdir(parents=True,exist_ok=False)
    report=dict(amplitude_mm=args.amplitude_mm,provenance=provenance(),hardware_validated=False)
    rig=Rig(args.port,rate_hz=100,log_dir=args.log_dir,record_capacity=8192,max_host_age_s=.02)
    try:
        with rig:report['result']=run_ringdown(rig,amplitude_m=args.amplitude_mm/1000,provenance=report['provenance'])
        if rig.records_dropped:raise ValidationError('log records lost; ringdown evidence is incomplete')
    except BaseException as exc:
        report['failure']=repr(exc);report['traceback']=traceback.format_exc();raise
    finally:
        report['log']=str(rig.log_path) if rig.log_path is not None else None
        report['records_dropped']=rig.records_dropped
        report['stop_records']=[r for r in rig.records if r['type'] in ('ringdown_stop','stop_failure')]
        if rig.log_path is not None and rig.log_path.exists():
            report['raw_log_sha256']=hashlib.sha256(rig.log_path.read_bytes()).hexdigest()
        (args.log_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
