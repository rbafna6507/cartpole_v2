"""Hanging admission through the real SDK runner, without serial or motor access."""
from dataclasses import replace
import json
import math

import pytest

from cartpole_sdk.contracts import ValidationError
from test_balance_hardware import rehearsal, saved_actor, run
from test_console_policy import RateAwareRig, command, select


@pytest.mark.parametrize('mode', ['raw', 'filtered'])
@pytest.mark.parametrize('theta,filtered', [(math.pi, -math.pi), (-math.pi, math.pi), (2.97, -2.98)])
def test_hanging_check_and_execute_preserve_actor_reference_leases_and_restore_rate(tmp_path, mode, theta, filtered):
    path = saved_actor(tmp_path, demand=.5, action_scale=25., mode=mode)
    with rehearsal(rig_type=RateAwareRig, state=dict(theta=theta, angle_hat=filtered, omega=0.)) as rig:
        rig.rate_hz = 250
        original = rig.parameters
        select(rig, path)
        check = json.loads(command(rig, 'policy check swingup'))
        assert check['ready'] and check['task'] == 'swingup-balance'
        assert check['start_mode'] == 'hanging' and check['start_angle_reference'] == 'down'
        assert not rig.commands and rig.rate_hz == 250
        output = command(rig, 'policy swingup .04')
        result = json.loads(output.splitlines()[-1])
        assert result['task'] == 'swingup-balance' and not result['hardware_accepted']
        boundary = next(r for r in rig.records if r['type'] == 'swingup_balance_boundary')
        assert boundary['start_mode'] == 'hanging' and boundary['start_angle_reference'] == 'down'
        assert boundary['start_limits']['angle_rad'] == .35
        requests = [r['request'] for r in rig.records if r['type'] == 'action_request']
        assert requests and all(r['acceleration_m_s2'] == 12.5 for r in requests)
        assert all(r['expires_at_ns']-r['issued_at_ns'] == 20_000_000 for r in requests)
        assert rig.parameters == original and rig._info.encoder_upright_raw == 123
        assert {c[1] for c in rig.commands} == {'RATE', 'ARM', 'A', 'STOP'}
        assert rig.rate_hz == 250 and not rig.state.enabled
        # Explicit swing-up preparation does not turn ordinary run into a hanging start.
        with pytest.raises(ValidationError, match='upright'):
            command(rig, 'policy run .04')


@pytest.mark.parametrize('state', [dict(theta=0.), dict(theta=2.7), dict(angle_hat=0.),
    dict(angle_hat=-2.7), dict(x=.016), dict(velocity=.026), dict(omega=.151), dict(brake_direction=1)])
def test_hanging_checks_both_angles_and_centered_stationary_state_before_arm(tmp_path, state):
    path = saved_actor(tmp_path, mode='filtered')
    with rehearsal(rig_type=RateAwareRig,
                   state=dict(theta=math.pi, angle_hat=-math.pi, omega=0.) | state) as rig:
        select(rig, path)
        with pytest.raises(ValidationError, match='hanging'):
            command(rig, 'policy swingup .04')
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
        assert rig.commands[-1][1] == 'STOP'


def test_hanging_shadow_default_and_swingup_default_are_stopped_and_bounded(tmp_path):
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=RateAwareRig, state=dict(theta=math.pi, omega=0.)) as rig:
        select(rig, path)
        command(rig, 'policy shadow swingup .04')
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
        started = rig.clock.now_ns
        result = json.loads(command(rig, 'policy swingup').splitlines()[-1])
        assert result['duration_s'] == 25.
        assert 24_990_000_000 <= rig.clock.now_ns-started <= 25_000_000_000
        assert not rig.state.enabled


def test_hanging_admission_is_rechecked_at_arm(tmp_path):
    class MovedAtArm(RateAwareRig):
        def _command_state(self, command, *args, **kwargs):
            super()._command_state(command, *args, **kwargs)
            if command == 'ARM':
                self._state = replace(self._state, theta=0., angle_hat=0.)
                self._history[self._state.unwrapped_tick] = self._state
    path = saved_actor(tmp_path, mode='filtered')
    with rehearsal(rig_type=MovedAtArm, state=dict(theta=math.pi, angle_hat=math.pi, omega=0.)) as rig:
        select(rig, path)
        with pytest.raises(ValidationError, match='hanging'):
            command(rig, 'policy swingup .04')
        assert any(c[1] == 'ARM' for c in rig.commands)
        assert not any(c[1] == 'A' for c in rig.commands)
        assert not rig.state.enabled


def test_swingup_can_cross_horizontal_capture_and_native_rail_braking_after_admission(tmp_path):
    class SwingingRig(RateAwareRig):
        def wait_state(self, **kwargs):
            super().wait_state(**kwargs)
            if self.state.enabled:
                theta, omega, brake = next(self.trajectory, (0.01, .02, 0))
                self._state = replace(self._state, theta=theta, angle_hat=theta, omega=omega,
                                      brake_direction=brake)
                self._history[self._state.unwrapped_tick] = self._state
            return self._state
    path = saved_actor(tmp_path, mode='filtered', demand=.1)
    with rehearsal(rig_type=SwingingRig, state=dict(theta=math.pi, angle_hat=math.pi, omega=0.)) as rig:
        rig.trajectory = iter([(1.57, -12., 1), (0., -4., 0), (-1.57, 9., -1), (.01, .02, 0)])
        select(rig, path)
        command(rig, 'policy swingup .08')
        assert len([r for r in rig.records if r['type'] == 'action_request']) >= 5
        assert not rig.state.enabled


@pytest.mark.parametrize('problem', ['home', 'switches', 'parameters', 'reference', 'cadence', 'interrupt'])
def test_swingup_retains_live_admission_fault_stop_and_rate_restoration(tmp_path, problem):
    class InterruptedRig(RateAwareRig):
        def wait_state(self, **kwargs):
            if self.state.enabled and problem == 'interrupt':
                raise KeyboardInterrupt
            return super().wait_state(**kwargs)
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=InterruptedRig, state=dict(theta=math.pi, omega=0.)) as rig:
        select(rig, path)
        rig.rate_hz = 250
        if problem in ('home', 'switches'):
            rig._state = replace(rig._state, flags=rig._state.flags & ~(4 if problem == 'home' else 8))
        elif problem == 'parameters':
            rig.parameters = replace(rig.parameters, bw=6.)
        elif problem == 'reference':
            rig._info.encoder_upright_raw = 124
        elif problem == 'cadence':
            rig.intervals = iter([16])
        with pytest.raises(KeyboardInterrupt if problem == 'interrupt' else (ValidationError, RuntimeError)):
            command(rig, 'policy swingup .04')
        if problem in ('home', 'switches', 'parameters', 'reference'):
            assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
        assert rig.rate_hz == 250 and not rig.state.enabled


@pytest.mark.parametrize('line', ['policy swingup nan', 'policy swingup 60.01', 'policy check sideways',
                                 'policy shadow swingup bad', 'policy swingup 1 unexpected'])
def test_bad_swingup_arguments_do_not_arm_or_change_rate(tmp_path, line):
    path = saved_actor(tmp_path)
    with rehearsal(rig_type=RateAwareRig) as rig:
        select(rig, path)
        rig.rate_hz = 250
        with pytest.raises(ValueError):
            command(rig, line)
        assert not rig.commands and rig.rate_hz == 250


def test_hanging_mode_requires_rig_profile(tmp_path):
    path = saved_actor(tmp_path)
    with rehearsal(state=dict(theta=math.pi, omega=0.)) as rig:
        with pytest.raises(ValidationError, match='rig'):
            run(rig, path, execute=True, start_mode='hanging')
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)


def test_standalone_hanging_cli_uses_same_boundary(tmp_path):
    from cartpole_sdk.learning.balance_hardware import main
    path = saved_actor(tmp_path)
    with rehearsal(state=dict(theta=math.pi, omega=0.)) as rig:
        code = main(['--actor', str(path), '--port', 'scripted', '--expected-upright-raw', '123',
            '--development-only', '--execute', '--guard-profile', 'rig', '--start-mode', 'hanging',
            '--duration', '.04', '--no-vision-telemetry'], rig_factory=lambda *a, **kw: rig)
        assert code == 0 and any(c[1] == 'A' for c in rig.commands)
        assert not rig.state.enabled
