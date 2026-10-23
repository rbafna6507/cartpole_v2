"""Exercise the service's real CLI invocation without acquiring a rig or queue."""
import configparser
import importlib.util
from pathlib import Path
import shlex
import sys

import pytest

from cartpole_sdk.portal import worker


@pytest.fixture
def installer():
    path = Path(__file__).parents[1] / 'deploy/portal/install-worker-service.py'
    spec = importlib.util.spec_from_file_location('cartpole_worker_installer_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def service(text):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    return parser['Service']


@pytest.mark.parametrize('backend,port,source', [
    ('simulation', None, 'simulation'),
    ('hardware', '/dev/serial/by-id/usb-cartpole-controller', 'magnetic-step'),
])
def test_generated_entrypoint_invokes_worker_cli_with_private_token_file(
        installer, tmp_path, monkeypatch, backend, port, source):
    home = tmp_path / 'operator home'
    token = home / '.config/cartpole-portal/worker-token'
    token.parent.mkdir(parents=True)
    token.write_text('private-test-worker-token\n')
    token.chmod(0o600)
    text = installer.unit_text(sys.executable, home, backend, port)
    unit = service(text)
    argv = shlex.split(unit['ExecStart'])
    assert argv[0] == sys.executable
    assert argv[1] == '-c'
    assert str(token) in argv
    assert token.read_text().strip() not in text
    assert Path(unit['WorkingDirectory']) == home / '.local/state/cartpole-portal'
    assert unit['Restart'] == 'no'
    assert unit['KillMode'] == 'control-group'

    received = {}
    queue = object()
    def remote(origin, credential):
        received.update(origin=origin, credential=credential)
        return queue
    def run_once(actual_queue, identity, rig_id, **kwargs):
        assert actual_queue is queue
        received.update(identity=identity, rig_id=rig_id, options=kwargs)
        return None
    monkeypatch.setattr(worker, 'RemoteQueue', remote)
    monkeypatch.setattr(worker, 'run_once', run_once)
    monkeypatch.setattr(sys, 'argv', ['-c', *argv[3:], '--once'])
    # Execute the actual configured Python entrypoint, not a duplicated parser.
    with pytest.raises(SystemExit) as exited:
        exec(compile(argv[2], '<service-entrypoint>', 'exec'), {})
    assert exited.value.code == 0
    assert received['origin'] == 'http://127.0.0.1:8780'
    assert received['credential'] == 'private-test-worker-token'
    assert received['options']['sensor_source'] == source
    assert received['rig_id'] == ('cartpole' if backend == 'hardware' else 'cartpole-simulation')
    if backend == 'hardware':
        assert received['options']['max_acceleration'] == .25
        # Construct only the inert bridge; it must not connect until a job starts.
        bridge = received['options']['bridge_factory']()
        assert bridge.port == port
        assert bridge.rig is None


@pytest.mark.parametrize('port', [None, '', 'ttyUSB0', 'auto'])
def test_hardware_unit_requires_explicit_device(installer, tmp_path, port):
    with pytest.raises(ValueError, match='explicit device'):
        installer.unit_text(sys.executable, tmp_path, 'hardware', port)


@pytest.mark.parametrize('start', [False, True])
@pytest.mark.parametrize('enable', [False, True])
def test_install_only_reloads_and_start_requires_explicit_option(
        installer, tmp_path, monkeypatch, capsys, start, enable):
    token = tmp_path / '.config/cartpole-portal/worker-token'
    token.parent.mkdir(parents=True)
    token.write_text('must-never-be-printed')
    commands = []
    monkeypatch.setattr(installer.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(installer.subprocess, 'run', lambda command, **kw: commands.append(command))
    argv = ['install-worker-service.py', '--python', sys.executable, '--backend', 'hardware', '--port', '/dev/ttyUSB0']
    monkeypatch.setattr(sys, 'argv', argv + (['--start'] if start else []) + (['--enable'] if enable else []))
    installer.main()
    unit = tmp_path / '.config/systemd/user/cartpole-worker-hardware.service'
    assert unit.is_file()
    assert commands[0] == ['systemctl', '--user', 'daemon-reload']
    assert len(commands) == 1 + int(start) + int(enable)
    assert (['systemctl', '--user', 'enable', unit.name] in commands) == enable
    assert (['systemctl', '--user', 'start', unit.name] in commands) == start
    assert all('--now' not in command for command in commands)
    assert 'must-never-be-printed' not in capsys.readouterr().out
    assert (tmp_path / '.local/state/cartpole-portal/hardware-spool').is_dir()
    assert (tmp_path / '.local/state/cartpole-portal/hardware-recordings').is_dir()


def test_missing_credential_prevents_install_and_start(installer, tmp_path, monkeypatch):
    monkeypatch.setattr(installer.Path, 'home', lambda: tmp_path)
    commands = []
    monkeypatch.setattr(installer.subprocess, 'run', lambda *args, **kwargs: commands.append(args))
    monkeypatch.setattr(sys, 'argv', ['install-worker-service.py', '--python', sys.executable,
                                   '--backend', 'hardware', '--port', '/dev/ttyUSB0', '--start'])
    with pytest.raises(SystemExit):
        installer.main()
    assert not commands
    assert not (tmp_path / '.config/systemd/user').exists()


@pytest.mark.parametrize('unsafe', ['bad\nRestart=always', 'bad%u', 'bad$HOME', 'bad"value', 'bad\\value'])
def test_unit_arguments_reject_injection_and_systemd_specifiers(installer, tmp_path, unsafe):
    with pytest.raises(ValueError):
        installer.unit_text('/usr/bin/' + unsafe, tmp_path, 'simulation')

def test_trusted_acceleration_ceiling_is_explicit_and_bounded(installer):
    module = installer
    for value in (0, 26, float('nan'), True):
        with pytest.raises(ValueError):
            module.unit_text('/usr/bin/python3', '/home/test', 'hardware', '/dev/ttyACM0', max_acceleration=value)
    text = module.unit_text('/usr/bin/python3', '/home/test', 'hardware', '/dev/ttyACM0', max_acceleration=25)
    assert '"--max-acceleration" "25.0"' in text
