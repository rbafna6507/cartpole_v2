"""Undeployed research diagnostic for notification-to-control wake latency.

Only public wait_state scopes cap individual Condition.wait calls at1ms.
Rig's original predicate, overall deadline, fault checks and action leases are
unchanged. This cannot recover missing/late serial telemetry and is not a fix.
"""
from contextlib import contextmanager
import threading
from timing_instrumentation import InstrumentedRig,TimingCondition
POLL_INTERVAL_S=.001


class PollingCondition(TimingCondition):
    def __init__(self,timings,rig):
        super().__init__(timings,rig);self._poll_scope=threading.local()
        self._counts=dict(calls=0,notified_returns=0,timeout_returns=0,errors=0)
    def polling_active(self):return getattr(self._poll_scope,'depth',0)>0
    @contextmanager
    def control_wait_scope(self):
        previous=getattr(self._poll_scope,'depth',0);self._poll_scope.depth=previous+1
        try:yield
        finally:self._poll_scope.depth=previous
    def wait(self,timeout=None):
        if not self.polling_active():return super().wait(timeout)
        bounded=POLL_INTERVAL_S if timeout is None else min(timeout,POLL_INTERVAL_S)
        self._counts['calls']+=1
        try:result=super().wait(bounded)
        except BaseException:
            self._counts['errors']+=1;raise
        self._counts['notified_returns' if result else 'timeout_returns']+=1
        return result
    def polling_summary(self):
        return dict(self._counts,interval_s=POLL_INTERVAL_S,
            scope='Only Condition.wait inside public Rig.wait_state on the calling thread',
            semantics='False/spurious wakes return to the original predicate/deadline loop. No new observation/action is synthesized; no lease is renewed by polling.')


class PollingRig(InstrumentedRig):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        # Constructor has not connected or started threads; retain the same
        # RLock-backed Condition interface used by the production client.
        self._condition=PollingCondition(self.timings,self)
    def wait_state(self,after_tick=None,timeout=1):
        with self._condition.control_wait_scope():
            return super().wait_state(after_tick=after_tick,timeout=timeout)
