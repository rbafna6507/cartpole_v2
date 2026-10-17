"""The cloud launcher sends a bounded, immutable, self-consistent experiment."""
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]


def build(tmp_path, **kw):
    from cartpole_sdk.learning.colab_bundle import prepare_bundle
    return prepare_bundle(ROOT, ROOT/'training/profiles/passive-20261017',
                          tmp_path/'bundle', **kw)


def test_bundle_flat_inputs_verified_recipe_and_only_selected_source(tmp_path):
    result = build(tmp_path, steps=2048)
    root = tmp_path/'bundle'
    with zipfile.ZipFile(root/'inputs.zip') as z:
        assert 'model.json' in z.namelist()
        assert 'observation-config.json' in z.namelist()
        assert all('/' not in name for name in z.namelist())
    with zipfile.ZipFile(root/'source.zip') as z:
        names = z.namelist()
        assert 'src/cartpole_sdk/learning/ppo.py' in names
        assert 'README.md' in names and 'uv.lock' in names
        assert not any(name.startswith(('runs/', 'evidence/', '.')) for name in names)
        assert not any('__pycache__' in name or name.endswith('.pyc') for name in names)
    recipe = json.loads((root/'recipe.json').read_text())
    assert recipe['steps'] == 2048 and recipe['seconds'] == 25
    assert recipe['angle_source'] == 'raw'
    assert recipe['randomize'] and recipe['gamma'] == .999
    assert recipe['reward_scale'] == .01
    assert result['hardware_accepted'] is False
    compile((root/'remote.py').read_text(), 'remote.py', 'exec')
    from cartpole_sdk.learning.colab_bundle import verify_bundle
    verify_bundle(root)
    (root/'inputs.zip').write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash'):
        verify_bundle(root)


def test_bad_steps_leave_no_output_and_existing_output_is_immutable(tmp_path):
    with pytest.raises(ValueError, match='multiple'):
        build(tmp_path, steps=100000)
    assert not (tmp_path/'bundle').exists()
    build(tmp_path, steps=1024)
    with pytest.raises(FileExistsError):
        build(tmp_path, steps=1024)


def test_colab_wrapper_requires_explicit_session_and_never_authenticates_on_help(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT/'examples/colab_training.py'), '--help'],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert 'start' in result.stdout and 'download' in result.stdout


def test_start_uses_pinned_cli_explicit_cpu_session_and_generated_script(tmp_path, monkeypatch):
    import importlib.util
    spec=importlib.util.spec_from_file_location('cloud_cli',ROOT/'examples/colab_training.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    build(tmp_path,steps=1024)
    fake=tmp_path/'colab';fake.write_text('fake executable')
    calls=[]
    def execute(command,check,**kwargs):
        from types import SimpleNamespace
        calls.append(command)
        action=next((arg.split('=',1)[1] for arg in command if arg.startswith('CARTPOLE_ACTION=')),None)
        nonce=next((arg.split('=',1)[1] for arg in command if arg.startswith('CARTPOLE_NONCE=')),None)
        return SimpleNamespace(stdout='CARTPOLE_REMOTE_OK '+json.dumps(dict(action=action,nonce=nonce))+'\n',stderr='')
    monkeypatch.setattr(cli.subprocess,'run',execute)
    assert cli.main(['start',str(tmp_path/'bundle'),'--session','my-test','--colab',str(fake),'--state-file',str(tmp_path/'sessions.json')])==0
    assert len(calls)==6
    assert calls[0]==[str(fake),'--auth','oauth2','--config',str(tmp_path/'sessions.json'),'new','-s','my-test']
    assert '--gpu' not in sum(calls,[])
    assert 'CARTPOLE_ACTION=start' in calls[-1]
    assert 'CARTPOLE_ACTION=setup' in calls[-2]


def test_remote_archive_path_traversal_is_rejected_without_extracting(tmp_path):
    from cartpole_sdk.learning.colab_remote import safe_extract
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside.txt','bad')
    with pytest.raises(ValueError,match='unsafe'):
        safe_extract(archive,tmp_path/'extract')
    assert not (tmp_path/'outside.txt').exists()


def test_remote_python_error_with_cli_exit_zero_does_not_launch_or_report_success(tmp_path,monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('cloud_cli_error',ROOT/'examples/colab_training.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    build(tmp_path,steps=1024)
    fake=tmp_path/'colab';fake.write_text('fake')
    calls=[]
    def execute(command,check,**kwargs):
        calls.append(command)
        return SimpleNamespace(stdout='ValueError: remote setup failed\n',stderr='')
    monkeypatch.setattr(cli.subprocess,'run',execute)
    with pytest.raises(SystemExit) as error:
        cli.main(['start',str(tmp_path/'bundle'),'--session','test','--colab',str(fake),'--state-file',str(tmp_path/'sessions.json')])
    assert error.value.code==2
    assert len(calls)==5
    assert not any('CARTPOLE_ACTION=start' in c for c in calls)


def test_packaged_profile_manifest_remains_complete_and_untampered(tmp_path):
    build(tmp_path,steps=1024)
    from hashlib import sha256
    with zipfile.ZipFile(tmp_path/'bundle/inputs.zip') as z:
        profile=json.loads(z.read('bundle.json'))
        for name,expected in profile['files_sha256'].items():
            assert sha256(z.read(name)).hexdigest()==expected


def test_changed_valid_profile_input_is_rejected_before_packaging(tmp_path):
    import shutil
    from cartpole_sdk.learning.colab_bundle import prepare_bundle
    profile=tmp_path/'profile'
    shutil.copytree(ROOT/'training/profiles/passive-20261017',profile)
    path=profile/'observation-config.json';value=json.loads(path.read_text());value['angle_noise_std']=.001
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='profile.*hash'):
        prepare_bundle(ROOT,profile,tmp_path/'bundle',steps=1024)
    assert not (tmp_path/'bundle').exists()


@pytest.mark.parametrize('existing',['registry','reservation'])
def test_duplicate_cloud_session_does_not_allocate_another_vm(tmp_path,monkeypatch,existing):
    import importlib.util
    from hashlib import sha256
    spec=importlib.util.spec_from_file_location('cloud_cli_collision',ROOT/'examples/colab_training.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    build(tmp_path,steps=1024)
    fake=tmp_path/'colab';fake.write_text('fake')
    registry=tmp_path/'sessions.json'
    if existing=='registry':registry.write_text(json.dumps({'my-test':{'opaque':'do not print'}}))
    else:(tmp_path/('.cartpole-launch-'+sha256(b'my-test').hexdigest()+'.json')).write_text('{}')
    def forbidden(*args,**kwargs):raise AssertionError('duplicate session must fail before CLI invocation')
    monkeypatch.setattr(cli.subprocess,'run',forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main(['start',str(tmp_path/'bundle'),'--session','my-test','--colab',str(fake),'--state-file',str(registry)])
    assert error.value.code==2


def test_remote_commands_reject_session_from_another_bundle(tmp_path,monkeypatch):
    from cartpole_sdk.learning import colab_remote as remote
    monkeypatch.setattr(remote,'PROJECT',tmp_path)
    monkeypatch.setattr(remote,'EXPECTED_ARCHIVES',{'source.zip':'a','inputs.zip':'b'},raising=False)
    (tmp_path/'colab-archives.json').write_text(json.dumps({'source.zip':'wrong','inputs.zip':'b'}))
    with pytest.raises(ValueError,match='different training bundle'):remote.verify_installed_binding()
    (tmp_path/'colab-archives.json').write_text(json.dumps({'source.zip':'a','inputs.zip':'b'}))
    remote.verify_installed_binding()
