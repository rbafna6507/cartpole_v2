import pytest
from cartpole_sdk.portal import sandbox

def test_launcher_resets_child_scheduling_before_bwrap(tmp_path,monkeypatch):
    policy=tmp_path/'policy.py';policy.write_text('def create_policy(): return None')
    instance=sandbox.Sandbox(policy)
    monkeypatch.setattr(instance,'preflight',lambda:None)
    monkeypatch.setattr(sandbox.shutil,'which',lambda name:'/usr/bin/'+name)
    captured={}
    def spawn(args,**kwargs):captured.update(args=args,kwargs=kwargs);return object()
    monkeypatch.setattr(sandbox.subprocess,'Popen',spawn)
    monkeypatch.setattr(sandbox,'PolicyChannel',lambda process,**kwargs:process)
    instance.launch()
    assert captured['args'][:4]==['/usr/bin/chrt','--other','0','/usr/bin/bwrap']
    assert captured['kwargs']['env']=={}
    assert 'preexec_fn' not in captured['kwargs']

def test_scheduler_reset_missing_fails_before_spawn(tmp_path,monkeypatch):
    policy=tmp_path/'policy.py';policy.write_text('')
    instance=sandbox.Sandbox(policy)
    monkeypatch.setattr(instance,'preflight',lambda:None)
    monkeypatch.setattr(sandbox.shutil,'which',lambda name:None if name=='chrt' else '/usr/bin/'+name)
    def forbidden(*args,**kwargs):pytest.fail('must not launch without scheduler reset')
    monkeypatch.setattr(sandbox.subprocess,'Popen',forbidden)
    with pytest.raises(sandbox.SandboxError,match='scheduler'):instance.launch()

def test_explicit_child_cpu_is_applied_before_scheduler_reset(tmp_path,monkeypatch):
    policy=tmp_path/'policy.py';policy.write_text('')
    instance=sandbox.Sandbox(policy,cpu_affinity=0)
    monkeypatch.setattr(instance,'preflight',lambda:None)
    monkeypatch.setattr(sandbox.shutil,'which',lambda name:'/usr/bin/'+name)
    captured=[]
    monkeypatch.setattr(sandbox.subprocess,'Popen',lambda args,**kwargs:captured.extend(args) or object())
    monkeypatch.setattr(sandbox,'PolicyChannel',lambda process,**kwargs:process)
    instance.launch()
    assert captured[:7]==['/usr/bin/taskset','-c','0','/usr/bin/chrt','--other','0','/usr/bin/bwrap']

def test_missing_taskset_rejects_explicit_affinity_before_spawn(tmp_path,monkeypatch):
    instance=sandbox.Sandbox(tmp_path/'policy.py',cpu_affinity=0)
    monkeypatch.setattr(instance,'preflight',lambda:None)
    monkeypatch.setattr(sandbox.shutil,'which',lambda name:None if name=='taskset' else '/usr/bin/'+name)
    monkeypatch.setattr(sandbox.subprocess,'Popen',lambda *a,**kw:pytest.fail('must not launch without requested isolation'))
    with pytest.raises(sandbox.SandboxError,match='affinity'):instance.launch()

@pytest.mark.parametrize('cpu',[-1,True,'0',100000])
def test_invalid_child_cpu_rejected(tmp_path,cpu):
    with pytest.raises(sandbox.SandboxError,match='CPU'):sandbox.Sandbox(tmp_path/'policy.py',cpu_affinity=cpu)
