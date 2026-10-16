"""The frozen numeric learner must be usable as a bounded portal source file."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from hashlib import sha256
import pytest
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.learning import read_artifact, train, save_artifact
from cartpole_sdk.portal.queue import Store
from cartpole_sdk.sim import MujocoBackend, SimulationConfig

ROOT=Path(__file__).resolve().parents[1]
HISTORICAL_ARTIFACT=ROOT/'evidence/phase5/learned-policy.json'


@pytest.fixture(scope='module')
def trained_artifact(tmp_path_factory):
    # Actual short CEM rollouts capture this runtime's provenance. Never rewrite
    # historical weights or replace their recorded hashes to make them load.
    artifact=train(seed=7,training_seeds=(11,12),generations=1,population=4,
                   config=SimulationConfig(control_steps=10,max_steps=20))
    path=tmp_path_factory.mktemp('current-export-training')/'weights.json'
    save_artifact(artifact,path)
    return path


def api():
    assert importlib.util.find_spec('cartpole_sdk.learning.export'), 'single-file exporter missing'
    from cartpole_sdk.learning.export import export_policy
    return export_policy


def load_source(path):
    spec=importlib.util.spec_from_file_location('exported_policy',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_embeds_exact_artifact_and_runs_without_original_weight_file(tmp_path,trained_artifact):
    export=api()
    copy=tmp_path/'weights.json';copy.write_bytes(trained_artifact.read_bytes())
    target=tmp_path/'policy.py'
    result=export(copy,target,source='simulation')
    copy.unlink()
    assert 0<len(target.read_bytes())<=65536
    assert result['artifact_sha256']==sha256(trained_artifact.read_bytes()).hexdigest()
    module=load_source(target)
    assert module.ARTIFACT_SHA256==result['artifact_sha256']
    assert module.SENSOR_SOURCE=='simulation'
    assert module.RATE_HZ==100
    assert json.loads(module.ARTIFACT_JSON)==read_artifact(trained_artifact)
    p=module.create_policy()
    b=MujocoBackend();obs=b.reset(state=(0.,0.,.04,0.));p.reset(b.session)
    # Only theta is nonzero in this balance observation: u = theta_gain*.04.
    expected=read_artifact(trained_artifact)['parameters']['theta_gain']*.04
    assert p.act(obs).acceleration_m_s2==pytest.approx(expected)
    store=Store(tmp_path/'queue')
    job=store.submit('test-owner','trained',target.read_bytes(),'trained.py','simulation',10.)
    assert job['artifact']==result['source_sha256']


def test_export_is_deterministic_and_wrong_sources_fail_closed(tmp_path,trained_artifact):
    export=api()
    first,second=tmp_path/'one.py',tmp_path/'two.py'
    export(trained_artifact,first,source='magnetic-step')
    export(trained_artifact,second,source='magnetic-step')
    assert first.read_bytes()==second.read_bytes()
    p=load_source(first).create_policy()
    assert [(c.source,c.frame_id) for c in p.channels]==[
        ('step','cart-step-home'),('step','cart-step-home'),
        ('magnetic','encoder-zero'),('magnetic','encoder-zero')]
    b=MujocoBackend();obs=b.reset();p.reset(b.session)
    assert p.act(obs) is None
    assert 'missing channel' in p.fault_reason
    with pytest.raises(ValidationError):export(trained_artifact,tmp_path/'bad.py',source='auto')


def test_export_loads_in_stdlib_only_child_and_missing_runtime_hash_fails(tmp_path,trained_artifact):
    export=api()
    target=tmp_path/'policy.py';export(trained_artifact,target,source='simulation')
    code='''import importlib.util,sys
sys.path.insert(0,sys.argv[1])
spec=importlib.util.spec_from_file_location('policy',sys.argv[2]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=m.create_policy()
assert p.rate_hz==100
assert 'numpy' not in sys.modules and 'mujoco' not in sys.modules
'''
    p=subprocess.run([sys.executable,'-I','-S','-c',code,str(ROOT/'src'),str(target)],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    artifact=read_artifact(trained_artifact)
    artifact['provenance']['code_sha256'].pop('policies/host.py')
    malformed=tmp_path/'bad.json';malformed.write_text(json.dumps(artifact))
    with pytest.raises(ValidationError):export(malformed,tmp_path/'bad.py',source='simulation')


def test_tampered_embedded_artifact_is_rejected_before_policy_creation(tmp_path,trained_artifact):
    export=api()
    target=tmp_path/'policy.py';export(trained_artifact,target,source='simulation')
    module=load_source(target)
    module.ARTIFACT_JSON+=' '  # Still valid JSON, but no longer the exact embedded bytes.
    with pytest.raises(ValidationError):module.create_policy()


def test_historical_trained_provenance_is_preserved_and_rejected_by_changed_runtime(tmp_path):
    original=HISTORICAL_ARTIFACT.read_bytes()
    artifact=read_artifact(HISTORICAL_ARTIFACT)
    current_hash=sha256((ROOT/'src/cartpole_sdk/control/parameters.py').read_bytes()).hexdigest()
    assert artifact['provenance']['code_sha256']['control/parameters.py']!=current_hash
    target=tmp_path/'historical.py'
    result=api()(HISTORICAL_ARTIFACT,target,source='simulation')
    assert result['artifact_sha256']==sha256(original).hexdigest()
    with pytest.raises(ValidationError,match='SDK inference code differs from trained provenance'):
        load_source(target).create_policy()
    assert HISTORICAL_ARTIFACT.read_bytes()==original
