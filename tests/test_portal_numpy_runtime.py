from cartpole_sdk.portal import worker

def test_worker_numpy_runtime_is_trusted_cli_configuration(tmp_path,monkeypatch):
    runtime=tmp_path/'packages';(runtime/'numpy').mkdir(parents=True);(runtime/'numpy.libs').mkdir()
    captured={}
    def run(*args,**kwargs):captured.update(kwargs);return None
    monkeypatch.setattr(worker,'run_once',run)
    assert worker.main(['--local-root',str(tmp_path/'queue'),'--rig-id','test','--backend','hardware','--port','/dev/never-opened','--numpy-root',str(runtime),'--sandbox-cpu','0','--once'])==0
    factory=captured['sandbox_factory']
    assert factory.func is worker.Sandbox
    assert factory.keywords['numpy_root']==str(runtime.resolve())
    assert factory.keywords['cpu_affinity']==0


def test_worker_realtime_is_trusted_cli_option(tmp_path,monkeypatch):
    captured={}
    monkeypatch.setattr(worker,'run_once',lambda *args,**kwargs:captured.update(kwargs))
    assert worker.main(['--local-root',str(tmp_path/'queue'),'--rig-id','test','--backend','hardware','--port','/dev/never-opened','--sandbox-cpu','1','--sandbox-realtime','--once'])==0
    assert captured['sandbox_factory'].keywords['realtime'] is True


def test_worker_realtime_requires_explicit_child_cpu(tmp_path):
    import pytest
    with pytest.raises(SystemExit):worker.main(['--local-root',str(tmp_path),'--rig-id','test','--sandbox-realtime','--once'])


import pytest
@pytest.mark.parametrize('result',[
    {'status':'failed','result':{'error':'hardware_executor_fault','stopped':True}},
    {'status':'failed','result':{'error':'stop_unconfirmed','stopped':False}},
])
def test_hardware_worker_stops_claiming_after_rig_fault(tmp_path,monkeypatch,result):
    calls=[]
    def run(*a,**kw):
        calls.append(1)
        if len(calls)>1:pytest.fail('faulted rig must not consume another job')
        return result
    monkeypatch.setattr(worker,'run_once',run)
    assert worker.main(['--local-root',str(tmp_path),'--rig-id','test','--backend','hardware','--port','/dev/never-opened'])==1
    assert len(calls)==1


def test_hardware_worker_continues_after_stopped_submission_failure(tmp_path,monkeypatch):
    calls=[]
    def run(*a,**kw):
        calls.append(1)
        if len(calls)==2:raise KeyboardInterrupt()
        return {'status':'failed','result':{'error':'isolated_policy_failure','stopped':True,'board_state':{'fault':0}}}
    monkeypatch.setattr(worker,'run_once',run)
    assert worker.main(['--local-root',str(tmp_path),'--rig-id','test','--backend','hardware','--port','/dev/never-opened'])==130
    assert len(calls)==2
