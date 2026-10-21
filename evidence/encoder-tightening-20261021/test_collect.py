"""Local safety regressions for the collector; never connect to hardware."""
from dataclasses import dataclass, replace
import importlib.util
import json
import math
from pathlib import Path

import pytest

from cartpole_sdk.rig.protocol import State


class Clock:
    now_ns = 0
    def monotonic(self):
        return self.now_ns / 1e9
    def monotonic_ns(self):
        return self.now_ns


@dataclass
class Info:
    encoder_upright_raw: int = 123
    reference_saved: bool = True
    encoder_conf_valid: bool = True
    firmware: str = 'executor-v6-measuredrail'
    mag_status: int = 0x20


class ScriptedRig:
    """Mirror the SDK: _require checks connection/error, not encoder health."""
    def __init__(self, clock, problem, output):
        self.clock, self.problem = clock, problem
        self.error = None
        self.records_dropped = 0
        self.records = []
        self.commands = []
        self.parameters = {'bw': 10.}
        self.log_path = output / 'rig-scripted.jsonl'
        self.state = State(sid=1, tick=0, us=0, mode=0, flags=13,
            theta=math.pi, angle_hat=math.pi, omega=0., x=0., velocity=0.,
            acceleration=0., demand=0., last_seq=0, fault=0, misses=0,
            dropped=0, brake_direction=0, received_ns=0)

    def __enter__(self):
        self.log_path.write_text('')
        return self

    def __exit__(self, *args):
        self.stop()
        if self.problem == 'late_logger_error':
            self.error = RuntimeError('scripted recording failure during close')

    def _require(self):
        if self.error is not None:
            raise RuntimeError(str(self.error))

    def _stopped_healthy(self):
        self._require()
        if self.state.enabled or self.state.mode or not self.state.healthy:
            raise RuntimeError('operation requires stopped healthy executor')
        return self.state

    def _fresh(self, state):
        if self.clock.monotonic_ns() - state.received_ns > 100_000_000:
            raise RuntimeError('stale host telemetry')

    def _record(self, kind, **details):
        row = dict(type=kind, host_monotonic_ns=self.clock.monotonic_ns(), **details)
        self.records.append(row)
        with self.log_path.open('a') as stream:
            stream.write(json.dumps(row)+'\n')
        if details.get('event') == 'initial_rest_start':
            if self.problem == 'unhealthy':
                self.state = replace(self.state, flags=self.state.flags & ~1)
            elif self.problem == 'moving_rest':
                self.state = replace(self.state, theta=1., omega=2.)
            elif self.problem == 'dropped_log':
                self.records_dropped = 1

    def wait_state(self, after_tick=None, timeout=.1):
        self._require()
        self.clock.now_ns += 100_000_000
        tick = self.clock.now_ns // 1_000_000
        self.state = replace(self.state, tick=tick, us=tick*1000,
            unwrapped_tick=tick, unwrapped_us=tick*1000, received_ns=self.clock.now_ns)
        # The sample that reaches the rest deadline must be validated too.
        if self.clock.now_ns >= 7_100_000_000:
            if self.problem == 'unhealthy_last_sample':
                self.state = replace(self.state, flags=self.state.flags & ~1)
            elif self.problem == 'moving_last_sample':
                self.state = replace(self.state, theta=1., omega=2.)
        return self.state

    def get_info(self):
        return Info()

    def get_parameters(self):
        self._require()
        if self.state.enabled or self.state.mode:
            raise RuntimeError('parameter operation requires stopped state')
        return dict(self.parameters)

    def stop(self):
        self.commands.append('STOP')
        self.state = replace(self.state, flags=self.state.flags & ~2, mode=0)


class ScriptedCamera:
    def __init__(self, problem):
        self.problem = problem
    def start(self):
        pass
    def check(self):
        pass
    def close(self):
        if self.problem == 'camera_close':
            raise OSError('scripted camera close failure')
        return {'frames': 100, 'stream_records': 200}


def collect(monkeypatch, tmp_path, problem):
    path = Path(__file__).with_name('collect.py')
    spec = importlib.util.spec_from_file_location('encoder_fixture_collector', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = Clock()
    output = tmp_path / 'collection'
    rig = ScriptedRig(clock, problem, output)
    monkeypatch.setattr(module, 'time', clock)
    monkeypatch.setattr('cartpole_sdk.rig.Rig', lambda *args, **kwargs: rig)
    monkeypatch.setattr('cartpole_sdk.identification.experiments.CameraRecorder', lambda *args, **kwargs: ScriptedCamera(problem))
    monkeypatch.setattr('cartpole_sdk.sensing.telemetry.EncoderPublisher', lambda *args, **kwargs: None)
    escaped = None
    try:
        code = module.main(['--output', str(output), '--expected-reference', '123'])
    except BaseException as error:
        code = None
        escaped = error
    report_path = output / 'report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else None
    return code, report, rig, escaped


def assert_reported_failure(result, detail):
    code, report, rig, escaped = result
    assert escaped is None, f'collection failure escaped without a final report: {escaped!r}'
    assert code == 1 and report is not None and report['success'] is False
    assert detail in json.dumps(report).lower(), 'failure must be preserved in report.json'
    assert rig.commands and set(rig.commands) == {'STOP'}


def test_stopped_healthy_reference_records_and_stops(monkeypatch, tmp_path):
    code, report, rig, escaped = collect(monkeypatch, tmp_path, None)
    assert escaped is None and code == 0 and report['success'] is True
    assert set(rig.commands) == {'STOP'}


@pytest.mark.parametrize('problem', ['unhealthy', 'unhealthy_last_sample'])
def test_unhealthy_encoder_without_fault_cannot_be_accepted_as_rest(monkeypatch, tmp_path, problem):
    assert_reported_failure(collect(monkeypatch, tmp_path, problem), 'healthy')


@pytest.mark.parametrize('problem', ['moving_rest', 'moving_last_sample'])
def test_pole_motion_during_five_second_rest_cannot_be_accepted(monkeypatch, tmp_path, problem):
    assert_reported_failure(collect(monkeypatch, tmp_path, problem), 'rest')


@pytest.mark.parametrize('problem,detail', [('dropped_log', 'drop'), ('late_logger_error', 'recording failure')])
def test_log_loss_or_error_during_close_cannot_report_success(monkeypatch, tmp_path, problem, detail):
    assert_reported_failure(collect(monkeypatch, tmp_path, problem), detail)


def test_camera_close_failure_preserves_failed_report(monkeypatch, tmp_path):
    assert_reported_failure(collect(monkeypatch, tmp_path, 'camera_close'), 'camera close failure')
