"""Learned console operation on the existing Rig with scripted telemetry."""
from dataclasses import replace
import gc
import io
import json
import math
import shlex

import pytest

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.rig import RigError
from cartpole_sdk.rig.console import execute_command, main
from test_balance_hardware import rehearsal, saved_actor
from test_neural_runner import DeadlineAwareShadowRig


class RateAwareRig(DeadlineAwareShadowRig):
    def _command(self, command, *args, **kwargs):
        if command == 'RATE':
            assert not self.state.enabled
            self.commands.append(['V2', 'RATE', str(self._sid), str(args[0])])
            return None
        raise AssertionError(f'unexpected command {command}')


def command(rig, line):
    output = io.StringIO()
    assert execute_command(rig, line, output=output)
    return output.getvalue()


def select(rig, path):
    return command(rig, 'policy load '+shlex.quote(str(path)))


def test_selection_check_and_unload_never_enable_or_change_rig(tmp_path):
    path = saved_actor(tmp_path, action_scale=25.)
    with rehearsal(rig_type=RateAwareRig) as rig:
        select(rig, path)
        status = json.loads(command(rig, 'policy status'))
        assert status['actor_path'] == str(path.resolve())
        assert status['expected_upright_raw'] == 123
        assert status['max_acceleration_m_s2'] == 25.
        assert status['task'] == 'balance-only'
        assert status['hardware_accepted'] is False
        result = json.loads(command(rig, 'policy check'))
        assert result['ready'] is True and result['reference_matches'] is True
        command(rig, 'policy unload')
        assert json.loads(command(rig, 'policy status'))['selected'] is False
        with pytest.raises(ValidationError, match='load'):
            command(rig, 'policy run')
        assert not any(c[1] != 'STOP' for c in rig.commands)


@pytest.mark.parametrize('options', [dict(bad_runtime=True), dict(mode='vision'), dict(legacy=True)])
def test_invalid_actor_is_rejected_without_selection_or_motion(tmp_path, options):
    path = saved_actor(tmp_path, **options)
    with rehearsal(rig_type=RateAwareRig) as rig:
        with pytest.raises(ValidationError):
            select(rig, path)
        assert json.loads(command(rig, 'policy status'))['selected'] is False
        assert not rig.commands


@pytest.mark.parametrize('operation', ['check', 'shadow .04', 'run .04'])
def test_reference_change_requires_reload_before_any_inference(tmp_path, operation):
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=RateAwareRig) as rig:
        select(rig, path)
        rig._info.encoder_upright_raw = 124
        assert json.loads(command(rig, 'policy status'))['reference_matches'] is False
        with pytest.raises(ValidationError, match='reload'):
            command(rig, 'policy '+operation)
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
        select(rig, path)
        assert json.loads(command(rig, 'policy check'))['expected_upright_raw'] == 124


def test_changed_actor_file_requires_reload(tmp_path):
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=RateAwareRig) as rig:
        select(rig, path)
        saved_actor(tmp_path, demand=.5)
        with pytest.raises(ValidationError, match='reload'):
            command(rig, 'policy run .04')
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)


def test_actor_replaced_during_rate_preparation_is_refused_before_arm(tmp_path):
    path = saved_actor(tmp_path, demand=.1)
    class ReplacedActorRig(RateAwareRig):
        def set_rate(self, hz):
            super().set_rate(hz)
            if hz == 100:
                saved_actor(tmp_path, demand=.8)
    with rehearsal(rig_type=ReplacedActorRig) as rig:
        rig.rate_hz = 250
        select(rig, path)
        with pytest.raises(ValidationError, match='actor'):
            command(rig, 'policy run .04')
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
        assert rig.rate_hz == 250 and not rig.state.enabled


def test_observed_reference_change_remains_invalid_until_reload(tmp_path):
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=RateAwareRig) as rig:
        select(rig, path)
        rig._info.encoder_upright_raw = 124
        command(rig, 'policy status')
        rig._info.encoder_upright_raw = 123
        with pytest.raises(ValidationError, match='reload'):
            command(rig, 'policy run .04')
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)


@pytest.mark.parametrize('duration', ['0', '-1', '60.001', 'nan', 'inf', 'invalid'])
def test_invalid_duration_never_arms_or_changes_rate(tmp_path, duration):
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=RateAwareRig) as rig:
        rig.rate_hz = 250
        select(rig, path)
        with pytest.raises((ValidationError, ValueError)):
            command(rig, 'policy run '+duration)
        assert rig.rate_hz == 250 and not rig.commands


@pytest.mark.parametrize('field,value', [('reference_saved', False), ('encoder_conf_valid', False),
                                        ('encoder_upright_raw', -1)])
def test_load_requires_valid_saved_reference_without_calibrating(tmp_path, field, value):
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=RateAwareRig) as rig:
        setattr(rig._info, field, value)
        with pytest.raises(ValidationError, match='saved encoder reference'):
            select(rig, path)
        assert not rig.commands


def test_check_at_250_reports_preparation_without_changing_rate(tmp_path):
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=RateAwareRig) as rig:
        rig.rate_hz = 250
        select(rig, path)
        result = json.loads(command(rig, 'policy check'))
        assert result['ready'] is True
        assert result['telemetry_rate_hz'] == 250
        assert result['required_rate_hz'] == 100
        assert result['temporary_rate_change'] is True
        assert rig.rate_hz == 250 and not rig.commands
        rig.parameters = replace(rig.parameters, bw=6.)
        with pytest.raises(ValidationError, match='snapshot'):
            command(rig, 'policy check')
        assert rig.rate_hz == 250 and not rig.commands


def test_check_cannot_report_ready_if_reference_changes_during_state_acquisition(tmp_path):
    class ChangedDuringObservationRig(RateAwareRig):
        def control_observation(self):
            observation = super().control_observation()
            self._info.encoder_upright_raw = 124
            return observation
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=ChangedDuringObservationRig) as rig:
        select(rig, path)
        with pytest.raises(ValidationError, match='reload'):
            command(rig, 'policy check')
        assert not rig.commands


def test_shadow_restores_rate_after_stopped_inference_without_actions(tmp_path):
    path = saved_actor(tmp_path, demand=.5, action_scale=25.)
    with rehearsal(rig_type=RateAwareRig) as rig:
        rig.rate_hz = 250
        select(rig, path)
        output = command(rig, 'policy shadow .04')
        assert '12.5' in output and 'shadow' in output
        assert '100' in output and '250' in output
        assert rig.rate_hz == 250 and not rig.state.enabled
        assert [c[-1] for c in rig.commands if c[1] == 'RATE'] == ['100', '250']
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)


def test_explicit_run_uses_full_actor_scale_five_seconds_and_same_rig(tmp_path):
    path = saved_actor(tmp_path, demand=.5, action_scale=25.)
    with rehearsal(rig_type=RateAwareRig) as rig:
        select(rig, path)
        command(rig, 'policy run')
        boundary = next(r for r in rig.records if r['type'] == 'balance_only_boundary')
        assert boundary['guard_profile'] == 'rig'
        assert boundary['requested_duration_s'] == 5.
        assert boundary['max_acceleration_m_s2'] == 25.
        requests = [r['request'] for r in rig.records if r['type'] == 'action_request']
        assert requests and all(r['acceleration_m_s2'] == 12.5 for r in requests)
        assert all(r['expires_at_ns'] - r['issued_at_ns'] == 20_000_000 for r in requests)
        assert not any(c[1] in ('MODE', 'HOME', 'CLEAR', 'CAL', 'PARAM') for c in rig.commands)
        assert rig.commands[-1][1] == 'STOP' and not rig.state.enabled


@pytest.mark.parametrize('failure', ['arm', 'cadence', 'lease'])
def test_failed_run_stops_and_restores_rate(tmp_path, failure):
    class FailedArmRig(RateAwareRig):
        def _command_state(self, name, *args, **kwargs):
            if name == 'ARM':
                raise RigError('failed arm')
            return super()._command_state(name, *args, **kwargs)
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=FailedArmRig if failure == 'arm' else RateAwareRig) as rig:
        rig.rate_hz = 250
        if failure == 'cadence':
            rig.intervals = iter([16])
        elif failure == 'lease':
            rig.intervals = iter([20])
        select(rig, path)
        with pytest.raises((RigError, ValidationError)):
            command(rig, 'policy run .04')
        assert rig.rate_hz == 250 and not rig.state.enabled
        assert rig.commands[-1][1:] == ['RATE', str(rig._sid), '250']
        assert rig.commands[-2][1] == 'STOP'


@pytest.mark.parametrize('operation', ['run', 'swingup'])
def test_interactive_interrupt_stops_and_returns_to_same_prompt(tmp_path, operation):
    class InterruptedRig(RateAwareRig):
        def wait_state(self, **kwargs):
            if self.state.enabled:
                assert not gc.isenabled()
                raise KeyboardInterrupt
            return super().wait_state(**kwargs)
    path = saved_actor(tmp_path)
    state = dict(theta=math.pi, angle_hat=math.pi, omega=0.) if operation == 'swingup' else None
    with rehearsal(rig_type=InterruptedRig, state=state) as rig:
        rig.rate_hz = 250
        lines = iter(['policy load '+shlex.quote(str(path)), 'policy '+operation, 'policy status', 'quit'])
        calls, prompted = [], []
        def factory(*args, **kwargs):
            calls.append(args)
            return rig
        def input_fn(prompt):
            prompted.append((rig.state.enabled, rig.rate_hz))
            return next(lines)
        output = io.StringIO()
        before_gc = gc.isenabled()
        code = main(['--port', 'scripted', '--keep-board-params', '--no-vision-telemetry'],
                    rig_factory=factory, input_fn=input_fn, output=output)
        assert code == 0 and len(calls) == 1
        assert len(prompted) == 4 and all(item == (False, 250) for item in prompted)
        assert 'interrupted' in output.getvalue()
        assert ('swingup-balance' if operation == 'swingup' else 'balance-only') in output.getvalue()
        assert not rig.state.enabled and gc.isenabled() == before_gc


def test_one_shot_cli_uses_actor_without_startup_parameter_writes(tmp_path):
    path = saved_actor(tmp_path, demand=.5, action_scale=25.)
    with rehearsal(rig_type=RateAwareRig) as rig:
        code = main(['--port', 'scripted', '--command', 'policy-run', '--actor', str(path),
                     '--development-only', '--duration', '.04', '--no-vision-telemetry'],
                    rig_factory=lambda *args, **kwargs: rig, output=io.StringIO())
        assert code == 0
        assert any(c[1] == 'A' for c in rig.commands)
        assert not any(c[1] in ('PARAM', 'HOME', 'CAL', 'MODE') for c in rig.commands)


@pytest.mark.parametrize('extra', [[], ['--actor', 'missing.json'], ['--development-only']])
def test_one_shot_requires_actor_and_explicit_development_acknowledgement(extra):
    def forbidden(*args, **kwargs):
        pytest.fail('invalid policy command must not open a serial device')
    with pytest.raises(SystemExit) as error:
        main(['--port', 'unopened', '--command', 'policy-run', *extra], rig_factory=forbidden)
    assert error.value.code == 2


def test_one_shot_rejects_runtime_mismatch_before_opening_serial(tmp_path):
    path = saved_actor(tmp_path, bad_runtime=True)
    def forbidden(*args, **kwargs):
        pytest.fail('invalid actor must not open a serial device')
    output = io.StringIO()
    assert main(['--port', 'unopened', '--command', 'policy-run', '--actor', str(path),
                 '--development-only'], rig_factory=forbidden, output=output) == 1
    assert 'provenance' in output.getvalue()


def test_reported_homing_variation_passes_console_check_and_run_without_rewriting_params(tmp_path):
    from test_live_rail_compatibility import live_rail
    path = saved_actor(tmp_path, demand=.1, action_scale=25., executor_parameters={'rail': .309074998})
    with rehearsal(rig_type=RateAwareRig) as rig:
        live_rail(rig, .308962494, span=16504)
        rig.rate_hz = 250
        select(rig, path)
        assert json.loads(command(rig, 'policy check'))['ready']
        command(rig, 'policy run .04')
        record = [r for r in rig.records if r['type'] == 'neural_preflight'][-1]
        assert record['host_run_limits']['position_m'] == pytest.approx(.2989625036716461, abs=1e-9)
        assert rig.parameters.rail == .308962494
        assert not any(c[1] in ('PARAM', 'HOME', 'CAL', 'CLEAR') for c in rig.commands)
        assert any(c[1] == 'ARM' for c in rig.commands)
        assert rig.commands[-1][1] == 'RATE' and rig.rate_hz == 250
        assert not rig.state.enabled
