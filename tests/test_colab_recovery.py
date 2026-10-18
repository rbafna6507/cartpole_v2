"""Runtime loss must remain visible and completed checkpoints must reach local disk."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from test_colab_bundle import build, ROOT


def cli_module():
    spec = importlib.util.spec_from_file_location('recovery_cli', ROOT/'examples/colab_training.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nonzero_cli_error_preserves_provider_diagnostic(tmp_path, monkeypatch, capsys):
    cli = cli_module(); build(tmp_path, steps=1024)
    fake = tmp_path/'colab'; fake.touch()
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], output="[colab] Session 'gone' not found.\n", stderr='provider details\n')
    monkeypatch.setattr(cli.subprocess, 'run', fail)
    with pytest.raises(SystemExit):
        cli.main(['status',str(tmp_path/'bundle'),'--session','gone','--colab',str(fake)])
    captured = capsys.readouterr()
    assert "Session 'gone' not found" in captured.out
    assert 'provider details' in captured.err


def test_remote_status_distinguishes_dead_job_and_incomplete_checkpoint(tmp_path, monkeypatch, capsys):
    from cartpole_sdk.learning import colab_remote as remote
    monkeypatch.setattr(remote, 'PROJECT', tmp_path)
    (tmp_path/'job-status.json').write_text(json.dumps({'status':'training','pid':999999999,'run':'runs/ppo-001'}))
    run = tmp_path/'runs/ppo-001'; (run/'logs').mkdir(parents=True)
    (run/'logs/progress.csv').write_text('time/total_timesteps,time/fps\n1024,100\n2048,99\n')
    partial = run/'checkpoints/step-000002048'; partial.mkdir(parents=True)
    (partial/'checkpoint.zip').write_bytes(b'unfinished')
    remote.status()
    rows = [line for line in capsys.readouterr().out.splitlines() if line.startswith('CARTPOLE_STATUS ')]
    assert len(rows)==1
    status = json.loads(rows[0].split(' ',1)[1])
    assert status['status']=='interrupted'
    assert status['recorded_status']=='training'
    assert status['latest_progress']['time/total_timesteps']=='2048'
    assert status['checkpoints']==[]


def test_watch_saves_new_checkpoint_and_terminal_state_without_duplicate_snapshots(tmp_path, monkeypatch):
    from cartpole_sdk.learning import colab_watch as watch
    monkeypatch.setattr(watch.time, 'sleep', lambda _:None)
    states = iter([
        {'status':'training','checkpoints':[]},
        {'status':'training','checkpoints':['step-000002048']},
        {'status':'training','checkpoints':['step-000002048']},
        {'status':'completed','checkpoints':['step-000002048']},
    ])
    def save(path):path.write_bytes(b'snapshot');return {'sha256':'verified-at-download'}
    result = watch.watch_job(lambda:next(states), save, tmp_path/'watch', poll_seconds=1, max_seconds=60)
    assert result['status']=='completed'
    assert len(list((tmp_path/'watch').glob('*.zip')))==2
    assert len((tmp_path/'watch/events.jsonl').read_text().splitlines())==6
    with pytest.raises(FileExistsError):
        watch.watch_job(lambda:None,save,tmp_path/'watch',poll_seconds=1,max_seconds=60)


def test_watch_preserves_saved_checkpoint_when_runtime_disappears(tmp_path, monkeypatch):
    from cartpole_sdk.learning import colab_watch as watch
    monkeypatch.setattr(watch.time, 'sleep', lambda _:None)
    states = iter([{'status':'training','checkpoints':['step-000002048']},ValueError('session not found')])
    def status():
        item = next(states)
        if isinstance(item,Exception):raise item
        return item
    def save(path):path.write_bytes(b'recoverable');return {'sha256':'verified-at-download'}
    with pytest.raises(ValueError,match='session not found'):
        watch.watch_job(status,save,tmp_path/'watch',poll_seconds=1,max_seconds=60)
    assert len(list((tmp_path/'watch').glob('*.zip')))==1
    final = json.loads((tmp_path/'watch/watch-status.json').read_text())
    assert final['status']=='connection_error' and final['last_snapshot']


def test_bundle_can_bound_checkpoint_and_evaluation_intervals(tmp_path):
    build(tmp_path,steps=2048,checkpoint_every=1024,evaluation_seeds=(21000,21001))
    recipe=json.loads((tmp_path/'bundle/recipe.json').read_text())
    assert recipe['checkpoint_every']==1024 and recipe['evaluation_seeds']==[21000,21001]


@pytest.mark.parametrize('kwargs', [{'checkpoint_every':0},{'checkpoint_every':1025},{'evaluation_seeds':(10000,)},{'evaluation_seeds':()}])
def test_bundle_rejects_invalid_recovery_recipe_before_writes(tmp_path,kwargs):
    with pytest.raises(ValueError):build(tmp_path,steps=2048,**kwargs)
    assert not (tmp_path/'bundle').exists()


@pytest.mark.parametrize('corrupt',[False, True])
def test_download_promotes_only_hash_verified_archive(tmp_path, monkeypatch, corrupt):
    from hashlib import sha256
    import io,zipfile
    cli=cli_module();build(tmp_path,steps=1024)
    fake=tmp_path/'colab';fake.touch()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('training.log','recorded progress')
    payload=buffer.getvalue()
    def execute(command, **kwargs):
        if 'exec' in command:
            nonce=next(x.split('=',1)[1] for x in command if x.startswith('CARTPOLE_NONCE='))
            metadata=dict(path='/content/cartpole-results.zip',bytes=len(payload),sha256=sha256(payload).hexdigest())
            return SimpleNamespace(stdout='CARTPOLE_PACKAGE '+json.dumps(metadata)+'\nCARTPOLE_REMOTE_OK '+json.dumps(dict(action='package',nonce=nonce))+'\n',stderr='')
        assert 'download' in command
        assert 0 < kwargs.get('timeout',float('inf')) <= 600
        Path(command[-1]).write_bytes(payload+b'corrupt' if corrupt else payload)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(cli.subprocess,'run',execute)
    output=tmp_path/'result.zip'
    args=['download',str(tmp_path/'bundle'),'--session','test','--colab',str(fake),'--output',str(output)]
    if corrupt:
        with pytest.raises(SystemExit):cli.main(args)
        assert not output.exists()
        assert output.with_suffix('.zip.part').exists()
    else:
        assert cli.main(args)==0
        assert output.read_bytes()==payload
        assert not output.with_suffix('.zip.part').exists()


def test_watch_timeout_never_claims_job_completed(tmp_path, monkeypatch):
    from cartpole_sdk.learning import colab_watch as watch
    now=[0.]
    monkeypatch.setattr(watch.time,'monotonic',lambda:now[0])
    def status():now[0]=2.;return {'status':'training','checkpoints':[]}
    result=watch.watch_job(status,lambda _:None,tmp_path/'watch',poll_seconds=1,max_seconds=1)
    assert result['status']=='timeout' and result['last_snapshot'] is None


def test_cli_timeout_preserves_partial_provider_output(tmp_path,monkeypatch,capsys):
    cli=cli_module();build(tmp_path,steps=1024)
    fake=tmp_path/'colab';fake.touch()
    def timeout(*args,**kwargs):
        raise subprocess.TimeoutExpired(args[0],150,output=b'partial remote traceback\n',stderr=b'provider timeout detail\n')
    monkeypatch.setattr(cli.subprocess,'run',timeout)
    with pytest.raises(SystemExit):
        cli.main(['status',str(tmp_path/'bundle'),'--session','test','--colab',str(fake)])
    captured=capsys.readouterr()
    assert 'partial remote traceback' in captured.out
    assert 'provider timeout detail' in captured.err
