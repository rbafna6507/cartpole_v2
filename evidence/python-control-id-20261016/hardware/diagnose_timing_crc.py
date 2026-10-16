"""Scratch-only timing diagnosis. Import is inert; main explicitly opens the rig.

Use an exact staged SDK --sdk-src. Default is a 20 s, 250 Hz zero-demand run or
stopped observation counterpart. --shadow-feedback is observe-only: computes
feedback without constructing/sending any ActionRequest; strict faults stop it.
All instrumentation uses preallocated integer arrays. Serialize only after STOP.
The existing SDK logger/mirror remain enabled to preserve their workload.
"""
import argparse
from array import array
from dataclasses import asdict
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import traceback

EXPECTED_SOURCE_SHA256 = {'cartpole_sdk/rig/client.py': 'ec577c1cf47f95572cb5b7d03b6828af136e85e82d88f9393e36db336ffd4b6b', 'cartpole_sdk/rig/policy.py': 'f1a29f0acdaab0522a6765e23048d1d058dd41c0c80f90f8f97cfda723020de8', 'cartpole_sdk/rig/protocol.py': 'bea00edbd75eeb5325709e1befcca5f1e4dbfcc3947ea9a167ca62c24c060b80', 'cartpole_sdk/rig/transport.py': '35db54a2da12b97bb05032513c55e64ce4091e3e7b3d989bbb372f155f649e76', 'cartpole_sdk/contracts.py': 'dbbbfafad2622d14e6d0a377786619ed156d87a6694503c26d4db36f8be261a6', 'cartpole_sdk/policies/executor_feedback.py': 'a8168cb11d053c086ecb3e589d0fcb19a768a829b71a98c45db658a09bc773b4', 'cartpole_sdk/control/parameters.py': 'e5377f098cfa8303f84f51bd4009c49163d98fb854562bea678af5922e25d288', 'cartpole_sdk/control/motion.py': '041ee5d0db35f383430812b8d559a111b7ec8b6e7d8b8aa14028cad335eb2690', 'cartpole_sdk/control/reference.py': '098f1f41065e811b0ce892f9b2ccae1796c524cf715c0d08458ac8697a14ea25', 'cartpole_sdk/control/forecast.py': 'ddbb88bafda97b8fc24e7e1a52bb62a015dc0c7248ed9ea109633e1793717a77', 'cartpole_sdk/sensing/telemetry.py': '7ed4f9890787f19090c18e315942220699597e76b1d7e8138e6b5e22bbd4a84b'}
STAGES=('observe','act','step','wait')
FIELDS=('stage','host_start_ns','cpu_start_ns','host_finish_ns','cpu_finish_ns',
        'input_sequence','input_board_ns','output_sequence','output_board_ns','error')


class MemoryTrace:
    def __init__(self, capacity=30_000):
        self.capacity=capacity;self.count=0;self.dropped=0
        self.columns=[array('q',[-1])*capacity for _ in FIELDS]
        self.native_id=threading.get_native_id()

    @staticmethod
    def identity(value):
        if value is None:return -1,-1
        sequence=getattr(value,'observation_sequence',getattr(value,'sequence',getattr(value,'unwrapped_tick',-1)))
        board=getattr(value,'issued_at_ns',getattr(value,'available_ns',-1))
        if board==-1 and hasattr(value,'unwrapped_us'):board=value.unwrapped_us*1000
        return sequence,board

    def call(self,stage,function,*args,**kwargs):
        row=self.count
        if row>=self.capacity:
            self.dropped+=1
            return function(*args,**kwargs)
        self.count+=1
        c=self.columns;c[0][row]=stage
        incoming=args[0] if args else None
        sequence,board=self.identity(incoming)
        if stage==3:sequence=kwargs.get('after_tick',sequence)
        c[5][row]=sequence;c[6][row]=board
        c[1][row]=time.monotonic_ns();c[2][row]=time.thread_time_ns()
        try:
            value=function(*args,**kwargs)
        except BaseException:
            c[9][row]=1
            raise
        else:
            c[9][row]=0
            c[7][row],c[8][row]=self.identity(value)
            return value
        finally:
            c[3][row]=time.monotonic_ns();c[4][row]=time.thread_time_ns()

    def summary(self,rate_hz):
        # Aggregate only after STOP. Observe-only keeps running across cadence
        # gaps, so this reports the full interval without an act cadence latch.
        c=self.columns
        board=[c[8][i] for i in range(self.count) if c[0][i]==0 and c[9][i]==0]
        gaps=[right-left for left,right in zip(board,board[1:])]
        period=1_000_000_000//rate_hz
        return dict(observations=len(board),max_observation_gap_ns=max(gaps,default=0),
            gaps_above_1_5_periods=sum(gap>period*3//2 for gap in gaps),
            gaps_above_2_periods=sum(gap>period*2 for gap in gaps),
            gaps_above_3_periods=sum(gap>period*3 for gap in gaps),
            gaps_below_half_period=sum(gap<period//2 for gap in gaps),
            stage_max_wall_ns={name:max((c[3][i]-c[1][i] for i in range(self.count) if c[0][i]==stage),default=0)
                for stage,name in enumerate(STAGES)},
            stage_max_cpu_ns={name:max((c[4][i]-c[2][i] for i in range(self.count) if c[0][i]==stage),default=0)
                for stage,name in enumerate(STAGES)})

    def dump(self,path):
        # Called only after STOP/close. No dict/JSON/file work in timed paths.
        Path(path).write_text(json.dumps(dict(fields=FIELDS,stages=STAGES,
            native_id=self.native_id,count=self.count,dropped=self.dropped,
            columns=[list(column[:self.count]) for column in self.columns]),separators=(',',':'))+'\n')


class TimedRig:
    def __init__(self,rig,trace):self._rig=rig;self._trace=trace
    def __getattr__(self,name):return getattr(self._rig,name)
    def step(self,*args,**kwargs):return self._trace.call(2,self._rig.step,*args,**kwargs)
    def wait_state(self,*args,**kwargs):return self._trace.call(3,self._rig.wait_state,*args,**kwargs)


class TimedPolicy:
    def __init__(self,policy,trace):self._policy=policy;self._trace=trace
    def __getattr__(self,name):return getattr(self._policy,name)
    def reset(self,session):return self._policy.reset(session)
    def act(self,observation):return self._trace.call(1,self._policy.act,observation)


def guarded(rig,operation,report):
    """Always STOP; a STOP failure must not mask an original operation error."""
    failure=None
    try:return operation()
    except BaseException as exc:
        failure=exc
        raise
    finally:
        try:
            rig.stop()
            report['stop_state']=asdict(rig.state)
            report['stop_confirmed']=not rig.state.enabled
        except BaseException as exc:
            report['stop_failure']=repr(exc);report['stop_confirmed']=False
            if failure is None:raise


def thread_snapshot():
    result=[]
    for thread in threading.enumerate():
        native=thread.native_id
        try:affinity=sorted(os.sched_getaffinity(native)) if native is not None and hasattr(os,'sched_getaffinity') else None
        except OSError:affinity=None
        result.append(dict(name=thread.name,ident=thread.ident,native_id=native,affinity=affinity))
    return result


def load_sdk(source):
    source=Path(source).resolve()
    for relative,expected in EXPECTED_SOURCE_SHA256.items():
        path=source/relative
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=expected:raise RuntimeError(f'exact staged source mismatch: {path}')
    sys.path.insert(0,str(source))
    modules={name:importlib.import_module(name) for name in (
        'cartpole_sdk.rig','cartpole_sdk.rig.policy','cartpole_sdk.contracts',
        'cartpole_sdk.policies.executor_feedback','cartpole_sdk.control.parameters',
        'cartpole_sdk.sensing.telemetry')}
    for name,module in modules.items():
        if not Path(module.__file__).resolve().is_relative_to(source):
            raise RuntimeError(f'{name} imported outside requested exact source root')
    return modules


def execute(rig,trace,args,modules,report):
    runner=modules['cartpole_sdk.rig.policy'];contracts=modules['cartpole_sdk.contracts']
    channels=tuple(contracts.Channel(*item) for item in (
        ('cart','position','step','cart-step-home'),('cart','velocity','step','cart-step-home'),
        ('pole','angle','magnetic_filtered','encoder-zero'),('pole','angular_velocity','magnetic','encoder-zero'),
        ('cart','acceleration','step','cart-step-home'),('cart','brake_direction','step','cart-step-home')))
    info=rig.get_info();state=rig._stopped_healthy()
    report['before_info']=asdict(info);report['before_state']=asdict(state)
    if info.firmware!='executor-v6-measuredrail' or info.encoder_upright_raw!=330:
        raise RuntimeError('requires exact v6 firmware and unchanged reference 330')
    if not(state.homed and state.healthy and state.switch_profile and not state.enabled) or abs(state.x)>=.003:
        raise RuntimeError('requires disabled healthy switch-protected home within 3 mm')
    if abs(state.velocity)>.005 or abs(state.acceleration)>.1 or state.brake_direction:
        raise RuntimeError('requires still cart and settled governor')
    if abs(state.omega)>.3 or abs(abs(state.theta)-math.pi)>.35:
        raise RuntimeError('requires quietly hanging pole')
    report['parameters']=rig.get_parameters();report['threads_before']=thread_snapshot()
    proxy=TimedRig(rig,trace)
    def observe():return trace.call(0,rig.control_observation)
    if args.case=='zero':
        runner.run_policy(proxy,lambda chosen:TimedPolicy(runner.ZeroAccelerationPolicy(chosen),trace),
            channels=channels,duration_s=args.seconds,ttl_ms=20,max_acceleration=.25,observation_provider=observe)
    else:
        if args.shadow_feedback:
            parameters=modules['cartpole_sdk.control.parameters'].ControllerParameters(**report['parameters'])
            inner=modules['cartpole_sdk.policies.executor_feedback'].ExecutorFeedbackPolicy(channels,
                parameters=parameters,rate_hz=args.rate,raw_angle_channel=contracts.Channel('pole','angle','magnetic','encoder-zero'))
        else:inner=runner.ZeroAccelerationPolicy(channels)
        policy=TimedPolicy(inner,trace);policy.reset(rig.session)
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline:
            if rig.state.enabled or rig.state.mode!=0:raise RuntimeError('observe-only requires disabled idle state throughout')
            observation=observe()
            intent=policy.act(observation)  # shadow calculation only; NEVER step/ARM
            if intent is None and getattr(policy,'fault_reason',None):
                raise contracts.ValidationError(f'shadow policy fault: {policy.fault_reason}')
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            try:proxy.wait_state(after_tick=observation.sequence,timeout=min(remaining,.1))
            except TimeoutError:
                if time.monotonic()>=deadline:break
                raise
        if hasattr(inner,'timing_diagnostics'):report['shadow_timing']=inner.timing_diagnostics()
    report['threads_after']=thread_snapshot()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case',choices=('observe','zero'))
    parser.add_argument('--sdk-src',required=True,type=Path)
    parser.add_argument('--seconds',type=float,default=20.)
    parser.add_argument('--rate',type=int,choices=(100,250),default=250)
    parser.add_argument('--shadow-feedback',action='store_true')
    parser.add_argument('--no-log',action='store_true',help='disable SDK JSONL logger; retain in-memory timings')
    parser.add_argument('--no-mirror',action='store_true',help='disable encoder mirror worker independently')
    parser.add_argument('--switch-interval',type=float,default=None)
    parser.add_argument('--port',default='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00')
    parser.add_argument('--output-root',type=Path,default=Path('/home/rbafna/cartpole-v2-runs/python-id-20261016'))
    args=parser.parse_args(argv)
    if not math.isfinite(args.seconds) or not 0<args.seconds<=20:parser.error('duration must be >0 and <=20 seconds')
    if args.shadow_feedback and args.case!='observe':parser.error('shadow feedback is disabled observation only')
    switch=args.switch_interval
    if switch is None and os.environ.get('CARTPOLE_TEST_SWITCH_INTERVAL_S'):
        switch=float(os.environ['CARTPOLE_TEST_SWITCH_INTERVAL_S'])
    if switch is not None:
        if not math.isfinite(switch) or not .0005<=switch<=.005:parser.error('switch interval must be .0005..005 seconds')
        sys.setswitchinterval(switch)
    modules=load_sdk(args.sdk_src)  # source verification precedes any connection
    directory=args.output_root/(f'timing-{args.case}-'+str(time.time_ns()));directory.mkdir(parents=True)
    trace=MemoryTrace();report=dict(case=args.case,seconds=args.seconds,rate_hz=args.rate,
        shadow_feedback=args.shadow_feedback,log_enabled=not args.no_log,mirror_enabled=not args.no_mirror,
        ttl_ms=20,sdk_src=str(args.sdk_src.resolve()),
        source_sha256=EXPECTED_SOURCE_SHA256,python=sys.version,switch_interval_s=sys.getswitchinterval(),
        threads_initial=thread_snapshot(),instrumentation='preallocated integer arrays; dump after STOP')
    failure=None
    try:
        publisher=None if args.no_mirror else modules['cartpole_sdk.sensing.telemetry'].EncoderPublisher()
        with modules['cartpole_sdk.rig'].Rig(args.port,rate_hz=args.rate,log_dir=None if args.no_log else directory,
                record_capacity=2048,vision_publisher=publisher) as rig:
            try:guarded(rig,lambda:execute(rig,trace,args,modules,report),report)
            finally:report['log']=str(rig.log_path) if rig.log_path is not None else None
    except BaseException as exc:
        failure=exc;report['failure']=repr(exc);report['traceback']=traceback.format_exc()
    finally:
        report['threads_final']=thread_snapshot()
        report['timing_summary']=trace.summary(args.rate)
        trace.dump(directory/'timing.json')
        (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(report=str(directory/'report.json'),failure=report.get('failure'),
            stop_confirmed=report.get('stop_confirmed'),samples=trace.count,dropped=trace.dropped)),flush=True)
    if failure is not None:raise failure
    return 0


if __name__=='__main__':raise SystemExit(main())
