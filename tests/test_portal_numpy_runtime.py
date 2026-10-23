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
