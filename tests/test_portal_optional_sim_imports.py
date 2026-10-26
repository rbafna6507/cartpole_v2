"""Hardware and API imports must not require the optional simulation extra."""
import os
from pathlib import Path
import subprocess
import sys


def test_hardware_and_client_work_without_optional_simulator():
    script = '''
import importlib.abc
import sys
class MissingSimulator(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        dependency = fullname.split('.')[0]
        if dependency in ('gymnasium', 'mujoco'):
            raise ModuleNotFoundError('deliberately unavailable: ' + dependency, name=dependency)
sys.meta_path.insert(0, MissingSimulator())
from cartpole_sdk.portal.worker import HardwareBridge, SimulationBridge
from cartpole_sdk.portal.client import PortalClient
from cartpole_sdk.sim import SimulationConfig, SensorConfig
assert SimulationConfig() is not None
assert SensorConfig() is not None
assert HardwareBridge().rig is None
client = PortalClient('http://127.0.0.1:8765', 'unused-test-token')
client._request = lambda path: {'recording_modes': ['standard', 'detailed']}
assert client.config()['recording_modes'] == ['standard', 'detailed']
assert 'mujoco' not in sys.modules
assert 'gymnasium' not in sys.modules
assert 'cartpole_sdk.sim.backend' not in sys.modules
try:
    SimulationBridge().prepare(.1, 'offline-test')
except ModuleNotFoundError as exc:
    assert exc.name in ('gymnasium', 'mujoco'), repr(exc)
    assert 'deliberately unavailable:' in str(exc), repr(exc)
else:
    raise AssertionError('simulation must require its optional dependency')
'''
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', script], env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
