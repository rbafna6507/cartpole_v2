"""Hardware-free checks for the policy console's scoped runtime setup."""
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'cartpole_sdk.rig.policy_console'


def load_launcher():
    assert importlib.util.find_spec(MODULE) is not None, 'policy console launcher is missing'
    return importlib.import_module(MODULE)


@pytest.fixture
def prior_interval():
    original = sys.getswitchinterval()
    # CPython stores whole microseconds; restoring its float can truncate by 1 us.
    sys.setswitchinterval(.007)
    try:
        yield sys.getswitchinterval()
    finally:
        sys.setswitchinterval(original)


@pytest.mark.parametrize('argv', [None, ['--port', 'a port', '--actor', 'an actor.json']])
def test_delegates_same_arguments_and_return_under_scoped_interval(prior_interval, monkeypatch, argv):
    launcher = load_launcher()
    from cartpole_sdk.rig import console
    output = io.StringIO()
    factory = object()
    input_fn = object()
    calls = []

    def delegate(received, **kwargs):
        calls.append(received)
        assert received is argv
        assert kwargs == dict(rig_factory=factory, input_fn=input_fn, output=output)
        assert sys.getswitchinterval() == pytest.approx(.001)
        return 23

    monkeypatch.setattr(console, 'main', delegate)
    assert launcher.main(argv, rig_factory=factory, input_fn=input_fn, output=output) == 23
    assert len(calls) == 1
    assert sys.getswitchinterval() == pytest.approx(prior_interval, abs=1.1e-6, rel=0)


@pytest.mark.parametrize('failure', [RuntimeError('delegate failed'), KeyboardInterrupt(), SystemExit(7)])
def test_restores_interval_and_propagates_original_exception(prior_interval, monkeypatch, failure):
    launcher = load_launcher()
    from cartpole_sdk.rig import console

    def delegate(*args, **kwargs):
        assert sys.getswitchinterval() == pytest.approx(.001)
        raise failure

    monkeypatch.setattr(console, 'main', delegate)
    with pytest.raises(type(failure)) as caught:
        launcher.main([])
    assert caught.value is failure
    assert sys.getswitchinterval() == pytest.approx(prior_interval, abs=1.1e-6, rel=0)


@pytest.mark.parametrize('argv', [['--help'], None])
def test_real_console_help_never_creates_rig_and_restores_interval(prior_interval, monkeypatch, capsys, argv):
    launcher = load_launcher()
    monkeypatch.setattr(sys, 'argv', ['policy-console', '--help'])

    def forbidden_rig(*args, **kwargs):
        pytest.fail('help must not create a Rig')

    with pytest.raises(SystemExit) as caught:
        launcher.main(argv, rig_factory=forbidden_rig)
    assert caught.value.code == 0
    assert '--actor' in capsys.readouterr().out
    assert sys.getswitchinterval() == pytest.approx(prior_interval, abs=1.1e-6, rel=0)


def test_interval_is_set_before_real_console_calls_rig_factory(prior_interval):
    launcher = load_launcher()
    class ReachedFactory(Exception):
        pass

    def factory(port, **kwargs):
        assert port == 'a port with spaces'
        assert kwargs['rate_hz'] == 250
        assert kwargs['log_dir'] == 'a log directory'
        assert sys.getswitchinterval() == pytest.approx(.001)
        raise ReachedFactory

    with pytest.raises(ReachedFactory):
        launcher.main(['--port', 'a port with spaces', '--rate', '250', '--log-dir',
                       'a log directory', '--keep-board-params', '--no-vision-telemetry'],
                      rig_factory=factory)
    assert sys.getswitchinterval() == pytest.approx(prior_interval, abs=1.1e-6, rel=0)


def test_fresh_import_has_no_runtime_or_hardware_side_effects():
    load_launcher()
    code = '''
import sys
from cartpole_sdk.rig import client

def forbidden(*args, **kwargs):
    raise AssertionError('import must not configure runtime or create a Rig')

client.Rig.__init__ = forbidden
sys.setswitchinterval = forbidden
import cartpole_sdk.rig.policy_console
assert 'cartpole_sdk.rig.console' not in sys.modules
print('import safe')
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'import safe'


@pytest.mark.parametrize('args,extras', [
    (['--port', 'a port', '--actor', 'an actor.json'], ['--extra', 'hardware', '--extra', 'inference']),
    (['--help'], []),
    (['--port', 'a port', '-h'], []),
])
def test_shell_launcher_preserves_arguments_and_selects_extras(tmp_path, args, extras):
    script = ROOT / 'scripts/policy-console'
    assert script.exists(), 'policy-console shell launcher is missing'
    assert os.access(script, os.X_OK), 'policy-console must be executable'
    fake_uv = tmp_path / 'uv'
    fake_uv.write_text('#!' + sys.executable + '\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\nraise SystemExit(19)\n')
    fake_uv.chmod(0o755)
    result = subprocess.run([str(script), *args], cwd=tmp_path,
                            env={**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH']},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 19, result.stderr
    assert json.loads(result.stdout) == ['run', '--project', str(ROOT), *extras,
                                        'python', '-m', MODULE, *args]
