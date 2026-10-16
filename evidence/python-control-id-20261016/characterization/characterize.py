#!/usr/bin/env python3
"""Trusted, bounded characterization proposal; hardware runs require --execute.

Import and --check-waveform are offline. Only main's explicit execution branch
opens Rig. No calibration, parameter write, switch change, clear, or home occurs.
"""
import argparse
from dataclasses import asdict, fields, is_dataclass
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time

from cartpole_sdk.contracts import (Acceleration, Channel, ValidationError,
                                    select_channels, validate_observation)
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.rig.policy import run_policy

DURATION=20.
RAMP=2.
KINDS={'pilot':(.00125,(.8,1.3,2.1)),
       'train':(.0025,(.8,1.3,2.1)),
       'heldout':(.002,(.7,1.6,2.3))}
CHANNELS=(Channel('cart','position','step','cart-step-home'),
          Channel('cart','velocity','step','cart-step-home'),
          Channel('pole','angle','magnetic','encoder-zero'),
          Channel('pole','angular_velocity','magnetic','encoder-zero'))
GAP_NS=20_000_000

def wrap(angle):
    return math.atan2(math.sin(angle),math.cos(angle))

def waveform(t,kind):
    """x, v, a, jerk of the previously checked quintic-ramped multisine."""
    amplitude,frequencies=KINDS[kind]
    if not math.isfinite(t):raise ValueError('waveform time must be finite')
    if t<0 or t>DURATION:return (0.,)*4
    s=min(t,DURATION-t)/RAMP
    if s>=1:e,ed,edd,eddd=1.,0.,0.,0.
    else:
        sign=1 if t<=DURATION/2 else -1
        e=10*s**3-15*s**4+6*s**5
        ed=sign*(30*s*s-60*s**3+30*s**4)/RAMP
        edd=(60*s-180*s*s+120*s**3)/RAMP**2
        eddd=sign*(60-360*s+360*s*s)/RAMP**3
    g=[sum(amplitude*(2*math.pi*f)**n*math.sin(2*math.pi*f*t+n*math.pi/2) for f in frequencies) for n in range(4)]
    return (e*g[0],ed*g[0]+e*g[1],edd*g[0]+2*ed*g[1]+e*g[2],
            eddd*g[0]+3*edd*g[1]+3*ed*g[2]+e*g[3])

def waveform_bounds():
    """Continuous x/v/a bounds from a 0.1 ms grid plus derivative bounds.

    This certifies the reference only. It does not bound the physical trajectory.
    """
    result={}
    for kind,(amplitude,frequencies) in KINDS.items():
        peaks=[0.]*4
        for i in range(200001):
            values=waveform(i/10000,kind)
            peaks=[max(a,abs(b)) for a,b in zip(peaks,values)]
        gs=[sum(amplitude*(2*math.pi*f)**n for f in frequencies) for n in range(4)]
        max_ed=1.875/RAMP;max_edd=10*math.sqrt(3)/(3*RAMP**2);max_eddd=60/RAMP**3
        derivative_bounds=[gs[0],max_ed*gs[0]+gs[1],max_edd*gs[0]+2*max_ed*gs[1]+gs[2],
                           max_eddd*gs[0]+3*max_edd*gs[1]+3*max_ed*gs[2]+gs[3]]
        result[kind]=dict(amplitude_per_tone_m=amplitude,frequencies_hz=list(frequencies),
                          duration_s=DURATION,ramp_s=RAMP,grid_interval_s=.0001,
                          grid_peaks=peaks,analytic_derivative_bounds=derivative_bounds,
                          continuous_bounds=[peaks[k]+derivative_bounds[k+1]*.00005 for k in range(3)],
                          endpoint_start=waveform(0,kind),endpoint_end=waveform(DURATION,kind))
    return result

def validate_board(state):
    if not state.healthy or not state.homed or not state.switch_profile:
        raise ValidationError('characterization requires healthy homed board with switches on')

def validate_preflight(state,info):
    validate_board(state)
    if info.encoder_upright_raw!=330 or not info.reference_saved or not info.encoder_conf_valid:
        raise ValidationError('reference 330 saved and valid encoder configuration required')
    if state.enabled or state.mode!=0 or state.brake_direction:
        raise ValidationError('preflight requires stopped executor with no governor brake')
    if (abs(state.x)>=.003 or abs(state.velocity)>=.005 or abs(state.acceleration)>=.1 or
            abs(state.omega)>=.15 or abs(wrap(state.theta-math.pi))>=.35):
        raise ValidationError('preflight requires centered quiet cart and quiet hanging pole')

def stationary_preflight(rig,info):
    """Require 0.5 s of quiet stopped observations, no waiting for motion to settle."""
    state=rig.state;rig._fresh(state);validate_preflight(state,info)
    first=state.unwrapped_us;initial=state.theta
    deadline=time.monotonic()+1.5
    while state.unwrapped_us-first<500_000:
        if time.monotonic()>=deadline:raise ValidationError('quiet preflight did not complete')
        state=rig.wait_state(after_tick=state.unwrapped_tick,timeout=.1)
        rig._fresh(state);validate_preflight(state,info)
        if abs(wrap(state.theta-initial))>.03:
            raise ValidationError('pole was not stationary throughout preflight')
    return state.theta

class CharacterizationPolicy:
    def __init__(self,channels,*,kind,initial_hanging,tail=False,record=None,clock_ns=time.monotonic_ns):
        if tuple(channels)!=CHANNELS or kind not in KINDS:
            raise ValidationError('explicit four magnetic/step channels and known waveform required')
        if not math.isfinite(initial_hanging):raise ValidationError('finite hanging reference required')
        self.channels=tuple(channels);self.kind=kind;self.initial_hanging=initial_hanging
        self.tail=bool(tail);self.record=record;self.clock_ns=clock_ns
        self.mode='excitation'
    def reset(self,session):
        self.session=session;self.origin_ns=None;self.previous=None;self.tail_entered=False
        self.mode='excitation'
    def _read(self,observation):
        validate_observation(self.session,observation)
        samples=select_channels(observation,self.channels,now_ns=observation.available_ns,max_age_ns=GAP_NS-1)
        if len({s.effective_ns for s in samples})!=1:
            raise ValidationError('channels must come from one coherent board snapshot')
        return tuple(s.value for s in samples)
    def validate_start(self,observation):
        x,v,theta,omega=self._read(observation)
        if (abs(x)>=.003 or abs(v)>=.005 or abs(omega)>=.15 or
                abs(wrap(theta-self.initial_hanging))>.03 or abs(wrap(theta-math.pi))>=.35):
            raise ValidationError('policy start no longer centered, quiet, and hanging')
    def act(self,observation):
        host_ns=self.clock_ns()
        x,v,theta,omega=self._read(observation)
        now=observation.available_ns
        if self.previous is None:
            self.validate_start(observation);self.origin_ns=now
        else:
            sequence,board_ns,previous_host=self.previous
            board_gap=now-board_ns;host_gap=host_ns-previous_host
            if (observation.sequence<=sequence or board_gap<=0 or board_gap>=GAP_NS or
                    host_gap<0 or host_gap>=GAP_NS):
                raise ValidationError(f'characterization cadence fault: sequence={observation.sequence} previous={sequence} board_gap_ns={board_gap} host_gap_ns={host_gap}')
        if abs(x)>.03 or abs(v)>.12 or abs(wrap(theta-self.initial_hanging))>.65 or abs(omega)>6:
            raise ValidationError('measured/estimated trajectory exceeded characterization guard')
        t=(now-self.origin_ns)/1e9
        reference=waveform(t,self.kind)
        if t>=DURATION:
            if self.tail and not self.tail_entered:
                if abs(x)>=.003 or abs(v)>=.005:
                    raise ValidationError('tail refused: cart not still and centered at taper end')
                self.tail_entered=True
            self.mode='commanded_hold' if self.tail and t<2*DURATION else 'complete'
            unbounded=command=0.
        else:
            self.mode='excitation'
            unbounded=reference[2]+80*(reference[0]-x)+14*(reference[1]-v)
            command=max(-1.,min(1.,unbounded))
        if self.record:
            self.record(phase=self.mode,t_s=t,observation_sequence=observation.sequence,board_ns=now,
                        host_policy_ns=host_ns,x_reference=reference[0],v_reference=reference[1],
                        a_reference=reference[2],jerk_reference=reference[3],x=x,v=v,theta=theta,omega=omega,
                        command=command,unclamped_command=unbounded,clamped=command!=unbounded,
                        tail_is_independent_physical_proof=False)
        self.previous=observation.sequence,now,host_ns
        return Acceleration(command)

def _plain(value):
    return asdict(value) if is_dataclass(value) else vars(value)

def run_characterization(rig,*,kind,tail=False,provenance=None):
    """Only trusted caller may invoke. Always STOP; never recover implicitly."""
    try:
        if rig.rate_hz!=100:raise ValidationError('characterization requires explicit 100 Hz SDK rate')
        if kind not in KINDS:raise ValidationError('choose pilot, train, or heldout explicitly')
        rig._stopped_healthy()
        parameters=rig.get_parameters()
        if set(parameters)!={f.name for f in fields(ControllerParameters)}:
            raise ValidationError('complete live parameter catalog required')
        ControllerParameters(**parameters)
        info=rig.get_info()
        initial_hanging=stationary_preflight(rig,info)
        rig._record('characterization_start',waveform_kind=kind,tail=tail,parameters=parameters,info=_plain(info),
                    state=_plain(rig.state),initial_hanging=initial_hanging,provenance=provenance or {},
                    rate_hz=100,duration_s=20,tail_nominal_s=20 if tail else 0,
                    completion_padding_s=.03,hardware_validated=False)
        def observe():
            # Health and all four values refer to the same stored state object.
            state=rig.state;rig._fresh(state);validate_board(state)
            return rig._observation(state)
        def factory(channels):
            return CharacterizationPolicy(channels,kind=kind,initial_hanging=initial_hanging,tail=tail,
                       record=lambda **values:rig._record('characterization_reference',**values))
        # SDK stops 10 ms before its wall deadline. A bounded 30 ms zero-command
        # pad allows the final taper/hold endpoint to be sampled despite this.
        # The waveform itself remains exactly 20 s; no excitation after it.
        run_policy(rig,factory,channels=CHANNELS,duration_s=20.03+(20 if tail else 0),
                   ttl_ms=20,max_acceleration=1.,observation_provider=observe)
        return dict(parameters=parameters,info=_plain(info),initial_hanging=initial_hanging,
                    kind=kind,tail=tail,hardware_validated=False)
    finally:
        rig.stop()

def provenance():
    import cartpole_sdk.contracts
    import cartpole_sdk.rig.client
    import cartpole_sdk.rig.policy
    paths=[Path(__file__).resolve(),Path(cartpole_sdk.contracts.__file__),
           Path(cartpole_sdk.rig.client.__file__),Path(cartpole_sdk.rig.policy.__file__)]
    return dict(python=sys.version,platform=platform.platform(),
                sources=[dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths])

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-waveform',action='store_true',help='offline JSON bounds; never connect')
    parser.add_argument('--execute',action='store_true',help='explicitly authorize this invocation to open the selected rig and run motion')
    parser.add_argument('--kind',choices=tuple(KINDS))
    parser.add_argument('--port')
    parser.add_argument('--log-dir',type=Path)
    parser.add_argument('--tail',action='store_true',help='nominal 20 s zero-command hold if still at taper end')
    parser.add_argument('--record-gc',action='store_true',help='record GC start/stop events without changing GC settings')
    args=parser.parse_args(argv)
    if args.check_waveform:
        if args.execute:parser.error('--check-waveform cannot be combined with --execute')
        print(json.dumps(waveform_bounds(),indent=2));return 0
    if not args.execute or not args.kind or not args.port or args.log_dir is None:
        parser.error('hardware invocation requires --execute --kind --port --log-dir')
    from cartpole_sdk.rig import Rig
    args.log_dir.mkdir(parents=True,exist_ok=False)
    report=dict(kind=args.kind,tail=args.tail,provenance=provenance(),hardware_validated=False)
    rig=Rig(port=args.port,rate_hz=100,log_dir=args.log_dir,max_host_age_s=.02)
    callback=None
    try:
        with rig:
            if args.record_gc:
                def callback(phase,info):rig._record('gc',phase=phase,info=dict(info))
                gc.callbacks.append(callback)
            report['result']=run_characterization(rig,kind=args.kind,tail=args.tail,provenance=report['provenance'])
    except BaseException as exc:
        report['failure']=repr(exc)
        raise
    finally:
        if callback is not None:gc.callbacks.remove(callback)
        report['log']=str(rig.log_path) if rig.log_path is not None else None
        report['records_dropped']=rig.records_dropped
        if rig.log_path and rig.log_path.exists():
            report['raw_log_sha256']=hashlib.sha256(rig.log_path.read_bytes()).hexdigest()
        (args.log_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
