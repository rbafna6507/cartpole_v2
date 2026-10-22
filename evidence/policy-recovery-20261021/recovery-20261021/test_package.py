import importlib.util
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent

def module():
    path=HERE/'package_recovery.py'
    assert path.exists(), 'recovery packaging must exist'
    spec=importlib.util.spec_from_file_location('recovery_package_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_dispatch_resumes_only_first_run_and_preserves_rest():
    m=module();commands=m.trial_commands('/python')
    assert len(commands)==6
    assert len(set(x['run'] for x in commands))==6
    assert 'resume.py' in commands[0]['command'][2]
    assert '--manifest' in commands[0]['command']
    assert all('run.py' in x['command'][2] and 'train' in x['command'] for x in commands[1:])
    assert [(x['arm'],x['seed']) for x in commands]==[(arm,seed) for seed in (11,23,47) for arm in ('ppo','retained')]

def test_foreground_job_waits_for_real_child_and_refuses_duplicate(tmp_path):
    m=module();calls=[]
    class Child:
        pid=123
        def wait(self):calls.append('wait');return 0
    class Subprocess:
        STDOUT=-1
        @staticmethod
        def Popen(*a,**k):calls.append('launch');return Child()
    scope=dict(PROJECT=tmp_path,subprocess=Subprocess,sys=type('Sys',(),dict(executable='/python')),json=__import__('json'))
    exec(m.FOREGROUND,scope)
    scope['run']()
    assert calls==['launch','wait']
    with pytest.raises(FileExistsError):scope['run']()
    assert calls==['launch','wait']
