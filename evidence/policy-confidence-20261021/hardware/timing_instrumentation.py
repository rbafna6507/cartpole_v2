"""Research-driver timing wrappers. Importing this module opens no hardware.

Production methods and their validation/lease behavior are delegated unchanged.
Event buffers are bounded; serialization is deferred until after Rig closes.
"""
from contextlib import contextmanager
import gc
import os
import platform
import sys
import threading
import time
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.transport import SerialTransport
from cartpole_sdk.learning.balance_hardware import BalanceOnlyPolicy


def _optional(fn):
    try:return fn()
    except (AttributeError,OSError,ValueError):return None


def thread_metadata():
    return dict(name=threading.current_thread().name,native_id=threading.get_native_id(),
        affinity=_optional(lambda:sorted(os.sched_getaffinity(0))),
        scheduler_policy=_optional(lambda:os.sched_getscheduler(0)),
        scheduler_priority=_optional(lambda:os.sched_getparam(0).sched_priority))


def runtime_metadata():
    return dict(python=sys.version,implementation=platform.python_implementation(),platform=platform.platform(),
        pid=os.getpid(),gil_enabled=_optional(lambda:sys._is_gil_enabled()),
        gil_switch_interval_ms=sys.getswitchinterval()*1000,cyclic_gc_enabled=gc.isenabled(),
        current_thread=thread_metadata(),threads=[dict(name=t.name,native_id=t.native_id,
            affinity=_optional(lambda t=t:sorted(os.sched_getaffinity(t.native_id))) if t.native_id else None,
            scheduler_policy=_optional(lambda t=t:os.sched_getscheduler(t.native_id)) if t.native_id else None)
            for t in threading.enumerate()],
        thread_environment={key:os.environ.get(key) for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
        semantics='Diagnostic settings only; no scheduler, affinity, priority, lease or safety parameter is changed by instrumentation.')


class TimingRecorder:
    columns=('stage','start_host_ns','finish_host_ns','thread_cpu_ns','input_tick','output_tick','action_sequence','success')
    def __init__(self,capacity=131072):
        if type(capacity) is not int or capacity<1:raise ValueError('positive event capacity required')
        self.capacity=capacity;self._local=threading.local();self._threads=[];self._registration_lock=threading.Lock()
        self.writes=[];self.writes_dropped=0
    def _buffer(self):
        result=getattr(self._local,'buffer',None)
        if result is None:
            result=dict(metadata=thread_metadata(),events=[],dropped=0)
            with self._registration_lock:self._threads.append(result)
            self._local.buffer=result
        return result
    def measure(self,stage,fn,*args,tick=None,action_sequence=None,**kwargs):
        buf=self._buffer();start=time.monotonic_ns();cpu=time.thread_time_ns();success=False;result=None
        try:
            result=fn(*args,**kwargs);success=True;return result
        finally:
            end=time.monotonic_ns();cpu_elapsed=time.thread_time_ns()-cpu
            output_tick=getattr(result,'sequence',getattr(result,'unwrapped_tick',None))
            event=(stage,start,end,cpu_elapsed,tick,output_tick,action_sequence,success)
            if len(buf['events'])<self.capacity:buf['events'].append(event)
            else:buf['dropped']+=1
    def snapshot(self):
        return dict(schema='cartpole-research-timing-v2',columns=self.columns,threads=self._threads,
                    dropped_events=sum(t['dropped'] for t in self._threads),writes=self.writes,
                    writes_dropped=self.writes_dropped,
                    semantics='Wall/CPU spans use separate clock reads; tiny negative wall-minus-CPU differences are measurement overhead. Buffers include preflight and cleanup. Operation results and exceptions are preserved.')


class TimingCondition(threading.Condition):
    def __init__(self,timings,rig):
        super().__init__(threading.RLock());self.timings=timings;self.rig=rig
    def _tick(self):return getattr(self.rig._state,'tick',None)
    def wait(self,timeout=None):
        return self.timings.measure('condition.wait',super().wait,timeout,tick=self._tick())
    def notify_all(self):
        return self.timings.measure('condition.notify_all',super().notify_all,tick=self._tick())


class TimingLock:
    def __init__(self,timings):self.timings=timings;self.lock=threading.Lock()
    def acquire(self,*args,**kwargs):return self.timings.measure('write_lock.acquire',self.lock.acquire,*args,**kwargs)
    def release(self):return self.lock.release()
    def __enter__(self):self.acquire();return self
    def __exit__(self,*args):self.release();return False


class InstrumentedTransport(SerialTransport):
    def __init__(self,port,*,timings):self.timings=timings;super().__init__(port)
    def read(self,size):return self.timings.measure('transport.read',super().read,size)
    def write(self,data):
        began=time.monotonic_ns();cpu=time.thread_time_ns()
        try:return self.timings.measure('transport.write',super().write,data)
        finally:
            end=time.monotonic_ns();elapsed_cpu=time.thread_time_ns()-cpu
            if len(self.timings.writes)<self.timings.capacity:
                self.timings.writes.append((began,end,elapsed_cpu,threading.current_thread().name,data.decode().strip()))
            else:self.timings.writes_dropped+=1


class InstrumentedRig(Rig):
    def __init__(self,*args,timings,**kwargs):
        self.timings=timings;super().__init__(*args,**kwargs)
        self._condition=TimingCondition(timings,self);self._write_lock=TimingLock(timings)
    def wait_state(self,after_tick=None,timeout=1):
        return self.timings.measure('wait_state',super().wait_state,after_tick=after_tick,timeout=timeout,tick=after_tick)
    def control_observation(self):
        return self.timings.measure('fetch.control_observation',super().control_observation)
    def step(self,request):
        return self.timings.measure('step',super().step,request,tick=getattr(request,'observation_sequence',None),action_sequence=getattr(request,'sequence',None))
    def _send(self,payload):
        return self.timings.measure('send',super()._send,payload)


@contextmanager
def instrument_actor(timings):
    """Temporary process-local method wrapper, restored on every exit."""
    original=BalanceOnlyPolicy.act
    def timed(self,observation):
        return timings.measure('act',original,self,observation,tick=observation.sequence)
    BalanceOnlyPolicy.act=timed
    try:yield
    finally:BalanceOnlyPolicy.act=original
