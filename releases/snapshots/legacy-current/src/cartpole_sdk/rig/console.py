"""Operator console for board reference modes and explicit external policies."""
import argparse
from dataclasses import asdict
import math
import shlex
import sys
import time
from cartpole_sdk.contracts import Channel, ValidationError
from cartpole_sdk.recording import canonical_json
from .client import Rig, RigError
from .policy import ZeroAccelerationPolicy, run_policy

HELP = ('auto [seconds], bal [seconds], manual [seconds], velocity m/s [ttl_ms], '
        'stop, center, home, switches on|off, status, info, clear, rate hz, quit')

def _status(rig, output):
    state=rig.state
    data=asdict(state)
    data['host_receipt_age_ms']=(time.monotonic_ns()-state.received_ns)/1e6
    data['cart_position_basis']='estimated step count'
    data['cart_velocity_basis']='commanded velocity'
    data['mode_basis']='external host policy' if state.mode==12 else 'board reference/operator'
    data['error']=None if rig.error is None else str(rig.error)
    print(canonical_json(data),file=output)

def execute_command(rig, line, *, output=None):
    """One interactive trusted operator command; return False to quit."""
    output=sys.stdout if output is None else output
    words=shlex.split(line)
    if not words:return True
    command,*args=words
    if command in ('quit','exit'):
        rig.stop(); return False
    if command in ('help','?'):
        print(HELP,file=output);return True
    if command in ('auto','bal','balance','manual'):
        if len(args)>1:raise ValidationError('mode accepts at most one duration')
        mode='bal' if command=='balance' else command
        duration=10. if not args else float(args[0])
        rig.start(mode,duration)
        print(f'board reference {mode} active for at most {duration:g}s',file=output)
    elif command=='velocity':
        if not 1<=len(args)<=2:raise ValidationError('velocity requires m/s and optional TTL milliseconds')
        seq=rig.set_velocity(float(args[0]),50 if len(args)==1 else int(args[1]))
        print(f'one manual velocity lease, sequence {seq}; expires unless explicitly renewed',file=output)
    elif command=='switches':
        if args not in (['on'],['off']):raise ValidationError('switches requires on or off')
        rig.configure_switches(args[0]=='on')
        print(f'physical switch profile {args[0]}',file=output)
    elif command=='rate':
        if len(args)!=1:raise ValidationError('rate requires one Hz value')
        rig.set_rate(int(args[0]))
    elif command in ('stop','center','home','status','info','clear'):
        if args:raise ValidationError(f'{command} accepts no arguments')
        if command=='status':_status(rig,output)
        elif command=='info':print(canonical_json(asdict(rig.get_info())),file=output)
        elif command=='center':
            rig.center()
            print('operator confirmed cart physically centered; step origin established',file=output)
        elif command=='clear':rig.clear_fault()
        else:getattr(rig,command)()
    else:
        raise ValidationError(f'unknown command: {command}; {HELP}')
    return True

def _wait_run(rig, duration_s, output):
    deadline=time.monotonic()+duration_s
    if rig._deadline_ns is not None:
        deadline=min(deadline,rig._deadline_ns/1e9)-min(.01,duration_s*.25)
    try:
        while time.monotonic()<deadline:
            if rig.error is not None:raise RigError(str(rig.error))
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            try:
                rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=min(remaining,.1))
            except TimeoutError:
                if time.monotonic()>=deadline:break
                raise
        _status(rig,output)
    finally:
        rig.stop()

def _wait_home(rig, timeout, output):
    deadline=time.monotonic()+timeout
    try:
        while True:
            state=rig.state
            if state.homed and state.healthy and not state.enabled and state.mode==0:
                _status(rig,output)
                return
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise TimeoutError('physical homing completion timeout')
            rig.wait_state(after_tick=state.unwrapped_tick,timeout=min(remaining,.1))
    finally:
        rig.stop()

def main(argv=None, *, rig_factory=None, input_fn=None, output=None):
    output=sys.stdout if output is None else output
    input_fn=input if input_fn is None else input_fn
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--rate',type=int,default=100,choices=(0,100,250,500,1000))
    parser.add_argument('--log-dir',default='runs/rig')
    parser.add_argument('--command',choices=('auto','bal','manual','velocity','stop','center','home','status','info','clear','policy-zero'))
    parser.add_argument('--duration',type=float,default=None,help='motion duration (default 10s) or homing timeout (default 60s)')
    parser.add_argument('--switches',choices=('on','off'),help='explicit stopped physical switch profile selection')
    parser.add_argument('--center-confirmed',action='store_true',help='operator asserts cart is physically centered now')
    parser.add_argument('--velocity',type=float,default=0.)
    parser.add_argument('--ttl-ms',type=int,default=50)
    parser.add_argument('--source',choices=('magnetic-step',),help='explicit source/frame selection for external policy-zero')
    args=parser.parse_args(argv)
    if args.duration is None:
        args.duration=60. if args.command=='home' else 10.
    if not math.isfinite(args.duration) or not .001<=args.duration<=60:
        parser.error('duration must be finite and within 1ms..60s')
    if args.command=='policy-zero' and args.source is None:
        parser.error('external policy requires --source magnetic-step')
    factory=Rig if rig_factory is None else rig_factory
    try:
        with factory(args.port,rate_hz=args.rate,log_dir=args.log_dir) as rig:
            print(f'connected stopped, session {rig.session.session_id}; log {rig.log_path}',file=output)
            if args.switches is not None:rig.configure_switches(args.switches=='on')
            if args.center_confirmed:rig.center()
            if args.command in ('auto','bal','manual'):
                execute_command(rig,f'{args.command} {args.duration}',output=output)
                _wait_run(rig,args.duration,output)
            elif args.command=='policy-zero':
                print('external host zero-acceleration policy; no swing-up/balance controller',file=output)
                channels=(Channel('pole','angle','magnetic','encoder-zero'),Channel('cart','position','step','cart-step-home'))
                run_policy(rig,ZeroAccelerationPolicy,channels=channels,duration_s=args.duration)
            elif args.command=='velocity':
                rig.start('manual',args.duration)
                rig.set_velocity(args.velocity,args.ttl_ms)
                _wait_run(rig,min(args.duration,args.ttl_ms/1000*.8),output)
            elif args.command=='home':
                rig.home()
                _wait_home(rig,args.duration,output)
            elif args.command is not None:
                execute_command(rig,args.command,output=output)
            else:
                print(HELP,file=output)
                while True:
                    try:
                        line=input_fn('cartpole> ')
                    except EOFError:break
                    try:
                        if not execute_command(rig,line,output=output):break
                    except (RigError,ValidationError,ValueError) as exc:
                        print(f'error: {exc}',file=output)
        return 0
    except KeyboardInterrupt:
        print('interrupted; stop requested',file=output)
        return 130
    except (RigError,ValidationError,TimeoutError,OSError,RuntimeError) as exc:
        print(f'error: {exc}',file=output)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
