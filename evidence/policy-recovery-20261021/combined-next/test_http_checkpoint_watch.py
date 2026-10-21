"""Behavioral tests for bounded, read-only checkpoint backup; no network calls."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import zipfile

import pytest


@pytest.fixture
def mod():
    path = Path(__file__).with_name('http_checkpoint_watch.py')
    assert path.exists(), 'HTTP checkpoint watcher is not implemented'
    spec = importlib.util.spec_from_file_location('http_checkpoint_watch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        z.writestr('policy.pth', b'checkpoint tensor bytes')
    return buffer.getvalue()


@pytest.fixture
def remote(mod):
    protocol = b'{"frozen":true}'
    cp = archive()
    run = 'runs/combined-long/ppo-seed11'
    report = {'protocol_sha256': digest(protocol), 'arm': 'ppo', 'optimizer_seed': 11,
              'budget': 'long', 'completed': False,
              'checkpoints': [{'step': 0, 'path': 'checkpoints/step-000000000.zip', 'sha256': digest(cp)}]}
    state = {'status': 'training', 'run': run, 'completed_trials': []}
    files = {mod.PROTOCOL_PATH: protocol, 'job-status.json': json.dumps(state).encode(),
             run + '/report.json': json.dumps(report).encode(), run + '/checkpoints/step-000000000.zip': cp}
    calls = []
    def download(path, destination, timeout):
        assert path.startswith('/content/cartpole-training/')
        assert 0 < timeout <= 45
        key = path.removeprefix('/content/cartpole-training/')
        calls.append(key)
        destination.write_bytes(files[key])
    return files, calls, download, digest(protocol), run


def test_verifies_checkpoint_before_success_and_does_not_redownload(mod, remote, tmp_path):
    files, calls, download, expected, run = remote
    first = mod.poll(download, tmp_path, expected)
    assert first['status'] == 'backup_complete'
    dest = tmp_path / run / 'checkpoints/step-000000000.zip'
    assert dest.read_bytes() == archive()
    assert (tmp_path / run / 'checkpoints/step-000000000.receipt.json').exists()
    calls.clear()
    mod.poll(download, tmp_path, expected)
    assert not any(x.endswith('.zip') for x in calls)


@pytest.mark.parametrize('failure', ['protocol', 'digest', 'crc', 'path', 'identity'])
def test_invalid_remote_data_never_marks_backup_complete(mod, remote, tmp_path, failure):
    files, calls, download, expected, run = remote
    report = json.loads(files[run + '/report.json'])
    if failure == 'protocol': report['protocol_sha256'] = '0' * 64
    if failure == 'digest': report['checkpoints'][0]['sha256'] = '0' * 64
    if failure == 'crc':
        broken = bytearray(archive()); index = broken.index(b'checkpoint tensor bytes'); broken[index] ^= 1
        files[run + '/checkpoints/step-000000000.zip'] = bytes(broken)
        report['checkpoints'][0]['sha256'] = digest(broken)
    if failure == 'path': report['checkpoints'][0]['path'] = '../../outside.zip'
    if failure == 'identity': report['optimizer_seed'] = 23
    files[run + '/report.json'] = json.dumps(report).encode()
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        mod.poll(download, tmp_path, expected)
    assert not (tmp_path / 'last-complete.json').exists()
    assert not list(tmp_path.rglob('*.receipt.json'))


def test_existing_checkpoint_is_never_overwritten_on_conflict(mod, remote, tmp_path):
    files, calls, download, expected, run = remote
    mod.poll(download, tmp_path, expected)
    dest = tmp_path / run / 'checkpoints/step-000000000.zip'
    dest.write_bytes(b'local corruption')
    calls.clear()
    with pytest.raises(ValueError): mod.poll(download, tmp_path, expected)
    assert dest.read_bytes() == b'local corruption'
    assert not any(x.endswith('.zip') for x in calls)


def test_rollover_backs_up_completed_and_current_trials(mod, remote, tmp_path):
    files, calls, download, expected, run = remote
    old = json.loads(files[run + '/report.json']);old['completed'] = True
    files[run + '/report.json'] = json.dumps(old).encode()
    next_run = 'runs/combined-long/retained-seed11'
    new = dict(old, arm='retained', completed=False)
    files[next_run + '/report.json'] = json.dumps(new).encode()
    files[next_run + '/checkpoints/step-000000000.zip'] = archive()
    files['job-status.json'] = json.dumps({'status': 'training', 'run': next_run,
        'completed_trials': [{'run': run, 'arm': 'ppo', 'seed': 11, 'report_sha256': digest(files[run + '/report.json'])}]}).encode()
    result = mod.poll(download, tmp_path, expected)
    assert len(result['checkpoints']) == 2
    assert (tmp_path / run / 'checkpoints/step-000000000.zip').exists()
    assert (tmp_path / next_run / 'checkpoints/step-000000000.zip').exists()


def test_unlisted_run_rejected_before_report_download(mod, remote, tmp_path):
    files, calls, download, expected, run = remote
    files['job-status.json'] = b'{"status":"training","run":"../../secret","completed_trials":[]}'
    with pytest.raises(ValueError): mod.poll(download, tmp_path, expected)
    assert not any('secret' in x for x in calls)


def test_cli_download_only_has_deadline_and_suppresses_credentials(mod, monkeypatch, tmp_path):
    recorded = []
    def run(args, **kw):
        recorded.append((args, kw))
        raise subprocess.TimeoutExpired(args, kw['timeout'], output=b'credential-secret')
    monkeypatch.setattr(mod.subprocess, 'run', run)
    with pytest.raises(mod.DownloadError) as error:
        mod.download_cli(Path('/pinned/colab'), Path('/private/session.json'), 'known-session',
                          '/content/cartpole-training/job-status.json', tmp_path / 'data', 45)
    assert 'credential-secret' not in str(error.value)
    args, kw = recorded[0]
    assert args == ['/pinned/colab', '--auth', 'oauth2', '--config', '/private/session.json',
                    'download', '-s', 'known-session', '/content/cartpole-training/job-status.json', str(tmp_path / 'data')]
    assert kw['timeout'] == 45
    assert kw['stdout'] == subprocess.DEVNULL and kw['stderr'] == subprocess.DEVNULL


def test_three_consecutive_failures_stop_and_do_not_leak_exception(mod, tmp_path):
    now = [0.]
    def fail(*args): raise mod.DownloadError('credential-secret')
    result = mod.watch(fail, tmp_path, '0'*64, max_seconds=1000,
                       clock=lambda:now[0], sleep=lambda value:now.__setitem__(0,now[0]+value))
    assert result['status'] == 'failed' and result['consecutive_failures'] == 3
    assert now[0] == 45
    assert 'credential-secret' not in ''.join(p.read_text() for p in tmp_path.glob('*.json*'))


def test_complete_poll_resets_failure_count_and_max_duration_stops(mod, remote, tmp_path):
    files, calls, download, expected, run = remote
    now = [0.];attempt = [0]
    def sometimes(path, dest, timeout):
        if path.endswith('job-status.json'):
            attempt[0] += 1
            if attempt[0] in [1, 3]: raise mod.DownloadError('temporary')
        download(path,dest,timeout)
    result = mod.watch(sometimes, tmp_path, expected, max_seconds=100,
                       clock=lambda:now[0], sleep=lambda value:now.__setitem__(0,now[0]+value))
    assert result['status'] == 'timeout'
    events = [json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]
    failures = [e['consecutive_failures'] for e in events if e['status'] == 'retrying']
    assert failures == [1,1]
    assert now[0] == 100


def test_completed_job_requires_all_trials_and_preserves_their_checkpoints(mod, remote, tmp_path):
    files, calls, download, expected, initial = remote
    completed = []
    template = json.loads(files[initial + '/report.json'])
    for run, (arm, seed) in mod.RUNS.items():
        report = dict(template, arm=arm, optimizer_seed=seed, completed=True)
        files[run + '/report.json'] = json.dumps(report).encode()
        files[run + '/checkpoints/step-000000000.zip'] = archive()
        completed.append({'run':run, 'arm':arm, 'seed':seed,
                          'report_sha256':digest(files[run + '/report.json'])})
    files['job-status.json'] = json.dumps({'status':'completed', 'run':completed[-1]['run'],
                                          'completed_trials':completed}).encode()
    result = mod.watch(download, tmp_path, expected)
    assert result['status'] == 'remote_completed'
    assert len(list(tmp_path.rglob('*.receipt.json'))) == 6


def test_completed_report_binding_mismatch_rejected(mod, remote, tmp_path):
    files, calls, download, expected, run = remote
    files['job-status.json'] = json.dumps({'status':'training', 'run':run,
        'completed_trials':[{'run':run,'arm':'ppo','seed':11,'report_sha256':'0'*64}]}).encode()
    with pytest.raises(ValueError): mod.poll(download,tmp_path,expected)
    assert not list(tmp_path.rglob('*.receipt.json'))


def test_actual_subprocess_deadline_kills_hung_downloader(mod, tmp_path):
    import sys
    import time
    exe = tmp_path/'fake-colab'
    exe.write_text('#!'+sys.executable+'\nimport time\nprint("credential-secret",flush=True)\ntime.sleep(10)\n')
    exe.chmod(0o755)
    began=time.monotonic()
    with pytest.raises(mod.DownloadError):
        mod.download_cli(exe, tmp_path/'state', 'known-session',
                         '/content/cartpole-training/job-status.json', tmp_path/'dest', .1)
    assert time.monotonic()-began < 2


def test_failed_remote_job_backs_up_before_stopping(mod, remote, tmp_path):
    files, calls, download, expected, run = remote
    files['job-status.json'] = json.dumps({'status':'failed','run':run,'completed_trials':[]}).encode()
    result=mod.watch(download,tmp_path,expected,max_seconds=86400)
    assert result['status']=='remote_failed'
    assert len(list(tmp_path.rglob('*.receipt.json')))==1
