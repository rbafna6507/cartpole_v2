import time
from cartpole_sdk.portal.queue import Store
from cartpole_sdk.portal.worker import run_once, SimulationBridge
from test_portal_worker import TrustedPipeFixture

def test_slow_heartbeat_does_not_block_control_actions(tmp_path):
    class Slow(Store):
        count=0
        def heartbeat(self,*args,**kwargs):
            self.count+=1
            if self.count>1:time.sleep(.2)
            return super().heartbeat(*args,**kwargs)
    queue=Slow(tmp_path)
    queue.submit('alice','one',b'x','policy.py','simulation',.8)
    ticks=[]
    class Paced(SimulationBridge):
        def advance(self,*args):
            ticks.append(time.monotonic());time.sleep(.01)
            return super().advance(*args)
    result=run_once(queue,'w','sim',bridge_factory=Paced,sandbox_factory=TrustedPipeFixture)
    assert result['status']=='succeeded'
    assert queue.count>=2
    assert max(b-a for a,b in zip(ticks,ticks[1:]))<.1

def test_runtime_cancel_stops_and_preserves_bundle(tmp_path):
    class Cancel(Store):
        count=0
        def heartbeat(self,identifier,*args,**kwargs):
            self.count+=1
            if self.count==2:self.cancel(identifier,'alice')
            return super().heartbeat(identifier,*args,**kwargs)
    queue=Cancel(tmp_path)
    job=queue.submit('alice','one',b'x','policy.py','simulation',1)
    class Paced(SimulationBridge):
        def advance(self,*args):time.sleep(.01);return super().advance(*args)
    result=run_once(queue,'w','sim',bridge_factory=Paced,sandbox_factory=TrustedPipeFixture)
    assert result['status']=='cancelled' and result['result']['stopped']
    assert result['result']['actions']<90
    assert queue.recording(job['id'],'alice')

def test_stale_runtime_lease_fails_closed_without_waiting_for_network():
    import threading
    import pytest
    from cartpole_sdk.portal.worker import _RunLease, RunAuthorityError
    entered=threading.Event();release=threading.Event()
    class Blocked:
        def heartbeat(self,*args):
            entered.set();release.wait(1)
            return dict(id='job',worker='w',lease='lease',rig='rig',status='running',cancel_requested=False)
    lease=_RunLease(Blocked(),'job','w','lease','rig',confirmed_at=time.monotonic(),interval=.005,max_age=.03)
    try:
        assert entered.wait(.2)
        time.sleep(.04)
        began=time.monotonic()
        with pytest.raises(RunAuthorityError,match='stale'):lease.check()
        assert time.monotonic()-began<.02
    finally:release.set();lease.close()

def test_failed_runtime_heartbeat_stops_run_and_records(tmp_path):
    class Failing(Store):
        count=0
        def heartbeat(self,*args,**kwargs):
            self.count+=1
            if self.count>1:raise OSError('simulated transport failure')
            return super().heartbeat(*args,**kwargs)
    queue=Failing(tmp_path)
    job=queue.submit('alice','one',b'x','policy.py','simulation',1)
    class Paced(SimulationBridge):
        def advance(self,*args):time.sleep(.01);return super().advance(*args)
    result=run_once(queue,'w','sim',bridge_factory=Paced,sandbox_factory=TrustedPipeFixture)
    assert result['status']=='failed' and result['result']['stopped']
    assert result['result']['error']=='runtime_authority_failure'
    assert result['result']['actions']<90
    assert queue.recording(job['id'],'alice')

import pytest
@pytest.mark.parametrize('failure',[False,True])
def test_stop_precedes_child_cleanup_and_armed_diagnostics(tmp_path,failure):
    from cartpole_sdk.portal.sandbox import SandboxError
    queue=Store(tmp_path)
    queue.submit('alice','one',b'x','policy.py','simulation',.1)
    events=[]
    class Tracked(SimulationBridge):
        armed=False
        def arm(self,duration):self.armed=True;events.append('arm')
        def stop(self):self.armed=False;events.append('stop');return super().stop()
        def diagnostics(self):
            assert not self.armed,'diagnostics must follow STOP'
            return super().diagnostics()
    class Child(TrustedPipeFixture):
        def launch(self):
            channel=super().launch()
            if failure:
                def act(*args):raise SandboxError('synthetic policy failure')
                channel.act=act
            class Context:
                def __enter__(self):return channel
                def __exit__(self,*args):events.append('child_exit');channel.close()
            return Context()
    result=run_once(queue,'w','sim',bridge_factory=Tracked,sandbox_factory=Child)
    assert events.index('stop')<events.index('child_exit')
    assert result['status']==('failed' if failure else 'succeeded')
    assert result['result']['stopped']

def test_fault_reported_after_stop_cannot_be_success(tmp_path):
    queue=Store(tmp_path)
    queue.submit('alice','one',b'x','policy.py','simulation',.1)
    class LateFault(SimulationBridge):
        fault=0
        def stop(self):self.fault=3;return super().stop()
        def diagnostics(self):return super().diagnostics()|{'board_state':{'fault':self.fault}}
    result=run_once(queue,'w','sim',bridge_factory=LateFault,sandbox_factory=TrustedPipeFixture)
    assert result['status']=='failed'
    assert result['result']['error']=='hardware_executor_fault'
    assert result['result']['board_state']['fault']==3

def test_failed_policy_attempt_timing_is_preserved_in_bundle(tmp_path):
    import io,json,zipfile
    from cartpole_sdk.portal.sandbox import SandboxError
    queue=Store(tmp_path)
    job=queue.submit('alice','timed-failure',b'x','policy.py','simulation',.1)
    class Failing(TrustedPipeFixture):
        def launch(self):
            channel=super().launch()
            def act(observation):
                time.sleep(.015)
                raise SandboxError('private untrusted detail')
            channel.act=act
            return channel
    result=run_once(queue,'w','sim',sandbox_factory=Failing)
    assert result['status']=='failed' and result['result']['stopped']
    assert result['result']['actions']==0
    assert result['result']['max_inference_s']>=.015
    with zipfile.ZipFile(io.BytesIO(queue.recording(job['id'],'alice'))) as archive:
        records=[json.loads(line) for line in archive.read('telemetry.jsonl').splitlines()]
    failures=[row for row in records if row['type']=='policy_failure']
    assert len(failures)==1 and failures[0]['inference_s']>=.015
    assert 'private untrusted detail' not in json.dumps(failures)
