import io
import stat
import zipfile
import pytest
from cartpole_sdk.portal.artifacts import inspect_artifact, prepare_artifact, ArtifactError

SOURCE=b'from helper import value\ndef create_policy(): return value\n'
def archive(entries):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for path,data in entries:z.writestr(path,data)
    return out.getvalue()

def test_zip_inspection_and_private_preparation(tmp_path):
    data=archive([('policy.py',SOURCE),('helper.py',b'value=1')])
    info=inspect_artifact(data,'project.zip')
    assert info['kind']=='python-zip' and info['entrypoint']=='policy.py'
    prepare_artifact(data,'project.zip',tmp_path)
    assert (tmp_path/'policy.py').read_bytes()==SOURCE
    assert (tmp_path/'helper.py').stat().st_mode&0o222==0

@pytest.mark.parametrize('path',['../escape','/absolute','a/../../escape','a\\escape','./policy.py','a//b'])
def test_reject_unsafe_zip_paths(path):
    with pytest.raises(ArtifactError):inspect_artifact(archive([('policy.py',SOURCE),(path,b'x')]),'project.zip')

def test_duplicates_links_missing_entrypoint_and_limits():
    for entries in ([('policy.py',SOURCE),('policy.py',SOURCE)],[('elsewhere/policy.py',SOURCE)],[(f'{i}.py',b'x') for i in range(257)]):
        with pytest.raises(ArtifactError):inspect_artifact(archive(entries),'project.zip')
    link=zipfile.ZipInfo('policy.py');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16
    with pytest.raises(ArtifactError):inspect_artifact(archive([(link,b'/etc/passwd')]),'project.zip')
    with pytest.raises(ArtifactError):inspect_artifact(archive([('policy.py',SOURCE),('large',b'0'*(32*1024*1024))]),'project.zip')

def test_invalid_actor_is_data_only():
    for data in (b'{}',b'null',b'{"schema":"pickle"}',b'notjson'):
        with pytest.raises(ArtifactError):inspect_artifact(data,'actor.json')

def test_actor_supported_contract():
    from pathlib import Path
    data=Path('training/candidates/combined-recovery-20261021-step000102400-rail1mm/actor.json').read_bytes()
    info=inspect_artifact(data,'actor.json')
    assert info['kind']=='actor-json' and info['rate_hz']==100

def test_worker_prepares_project_before_sandbox(tmp_path):
    from cartpole_sdk.portal.queue import Store
    from cartpole_sdk.portal.worker import run_once
    from test_portal_worker import TrustedPipeFixture
    store=Store(tmp_path/'queue')
    data=archive([('policy.py',SOURCE),('helper.py',b'value=1')])
    store.submit('alice','zip',data,'project.zip','simulation',.1)
    class Inspect(TrustedPipeFixture):
        def __init__(self,path,**kw):
            assert path.is_dir() and (path/'helper.py').read_bytes()==b'value=1'
            assert kw['artifact_kind']=='python-zip' and kw['sensor_source']=='simulation'
            super().__init__(path,**kw)
    assert run_once(store,'w','sim',sandbox_factory=Inspect)['status']=='succeeded'

def test_slow_setup_retains_short_renewable_lease(tmp_path):
    import time
    from cartpole_sdk.portal.queue import Store
    from cartpole_sdk.portal.worker import run_once, SimulationBridge
    from test_portal_worker import TrustedPipeFixture
    store=Store(tmp_path/'queue')
    store.submit('alice','slow',b'x=1','policy.py','simulation',.1)
    class Slow(SimulationBridge):
        def prepare(self,*args):
            time.sleep(2.1)
            return super().prepare(*args)
    assert run_once(store,'w','sim',bridge_factory=Slow,sandbox_factory=TrustedPipeFixture)['status']=='succeeded'

import shutil
import sys
@pytest.mark.skipif(sys.platform!='linux' or not shutil.which('bwrap'),reason='actual Linux isolation required')
@pytest.mark.parametrize('kind',['project','actor','actor-numpy'])
def test_actual_sandbox_project_and_numeric_policy(tmp_path,kind):
    from pathlib import Path
    from hashlib import sha256
    from cartpole_sdk.portal.queue import Store
    from cartpole_sdk.portal.worker import run_once
    from cartpole_sdk.portal.sandbox import Sandbox
    from functools import partial
    import os
    runtime=os.environ.get('CARTPOLE_TEST_SANDBOX_NUMPY_ROOT')
    if kind=='actor-numpy' and not runtime:pytest.skip('explicit sandbox-compatible NumPy runtime required')
    from cartpole_sdk.policies.neural import RUNTIME_FILES, _digest
    from cartpole_sdk.recording import canonical_json, strict_json_loads
    if kind=='project':
        data=archive([('policy.py',b'from helper import Policy\ndef create_policy(): return Policy()\n'),('helper.py',b'from cartpole_sdk.contracts import Acceleration\nclass Policy:\n def reset(self,session): pass\n def act(self,observation): return Acceleration(0)\n')])
        filename='project.zip'
    else:
        root=Path(__file__).resolve().parents[1]
        actor=strict_json_loads((root/'training/candidates/combined-recovery-20261021-step000102400-rail1mm/actor.json').read_text())
        for layer in actor['layers']:
            layer['weights']=[[0. for _ in row] for row in layer['weights']]
            layer['bias']=[0. for _ in layer['bias']]
        actor.pop('content_sha256')
        actor['runtime_sha256']={name:sha256((root/'src/cartpole_sdk'/name).read_bytes()).hexdigest() for name in RUNTIME_FILES}
        actor['content_sha256']=_digest(actor)
        data=canonical_json(actor).encode();filename='actor.json'
    store=Store(tmp_path/'queue');store.submit('alice',kind,data,filename,'simulation',.1)
    factory=partial(Sandbox,numpy_root=runtime) if kind=='actor-numpy' else Sandbox
    result=run_once(store,'w','sim',sandbox_factory=factory)
    assert result['status']=='succeeded',result['result']
    if kind=='actor-numpy':assert result['result']['numeric_inference_backend']=='numpy-einsum'
    assert result['result']['actions']>0


def test_numeric_actor_wrong_profile_source_rejected_before_policy_launch(tmp_path):
    from pathlib import Path
    from cartpole_sdk.recording import canonical_json, strict_json_loads
    from cartpole_sdk.policies.neural import _digest
    from cartpole_sdk.portal.queue import Store
    from cartpole_sdk.portal.worker import run_once
    from test_portal_worker import TrustedPipeFixture
    actor=strict_json_loads(Path('training/candidates/combined-recovery-20261021-step000102400-rail1mm/actor.json').read_text())
    actor['angle_source']='raw'
    actor['observation_contract']['angle_source']='raw'
    actor.pop('content_sha256');actor['content_sha256']=_digest(actor)
    data=canonical_json(actor).encode()
    store=Store(tmp_path/'queue');store.submit('alice','wrong-source',data,'actor.json','simulation',.1)
    launches=[]
    class Tracked(TrustedPipeFixture):
        def launch(self):launches.append(True);return super().launch()
    result=run_once(store,'w','sim',sandbox_factory=Tracked)
    assert result['status']=='failed'
    assert not launches
    assert result['result']['error']=='simulation_profile_mismatch'
