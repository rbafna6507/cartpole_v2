"""Offline driven ID checks use the real Rig policy/lease/stop implementation."""
from contextlib import ExitStack
from dataclasses import asdict, replace
import importlib
import json
import math
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cartpole_sdk.contracts import Session, ValidationError
from cartpole_sdk.control.parameters import ControllerParameters
from test_rig_console import ScriptedClock, ScriptedConsoleRig
from test_system_id_experiments import observation


def module():
    return importlib.import_module('cartpole_sdk.identification.driven_capture')


class Camera:
    def __init__(self, clock):
        self.clock = clock
        self.stale = False
        self.missing_geometry = False
        self.failure = None

    def check(self):
        if self.failure is not None:
            raise self.failure

    def latest(self):
        t = self.clock.monotonic()
        vision = dict(seq=self.clock.now_ns // 10_000_000, t=t, stale=self.stale,
                      age_since_host_read_s=0., worker_error=None,
                      image_angle_rad=0., pivot_px=[100., 100.], bob_px=[100., 200.],
                      detected=True, confidence=1., length_px=100.,
                      frame_width=960, frame_height=600)
        if self.missing_geometry:
            vision['bob_px'] = None
        return dict(collector_received_ns=self.clock.now_ns, host_t=t, vision=vision)


class DrivenRig(ScriptedConsoleRig):
    """Device scheduling only: native AUTO and counted return finish asynchronously."""
    def _command_state(self, command, *args, predicate, allow_error=False):
        if command == 'REHOME':
            self._require(allow_error=allow_error)
            self.commands.append(['V2', command, str(self._sid)])
            self._state = replace(self._state, mode=14, flags=self._state.flags | 2)
            self._history[self._state.unwrapped_tick] = self._state
            self.native_finish = self.clock.now_ns + 100_000_000
            self._lease_until_ns = None
            assert predicate(self._state)
        else:
            super()._command_state(command, *args, predicate=predicate, allow_error=allow_error)
            if command == 'MODE':
                self._lease_until_ns = None
                self.native_finish = self.clock.now_ns + int(args[-1]) * 1_000_000

    def wait_state(self, *args, **kwargs):
        state = super().wait_state(*args, **kwargs)
        if state.mode in (3, 14) and self.clock.now_ns >= self.native_finish:
            self._state = replace(state, mode=0, flags=state.flags & ~2, x=0.,
                                  velocity=0., acceleration=0., brake_direction=0)
            self._active = False
        return self._state


def setup_rig():
    clock = ScriptedClock()
    clock.now_ns = 0
    rig = DrivenRig('offline-driven', clock=clock, rate_hz=100, record_capacity=20000)
    rig.connect()
    rig._state = replace(rig._state, theta=math.pi, angle_hat=math.pi, omega=0., x=0.)
    rig._info = SimpleNamespace(firmware='executor-v6-measuredrail', encoder_upright_raw=330,
                               reference_saved=True, encoder_conf_valid=True, home_epoch=14,
                               measured_span_steps=16000, rail_half_m=.26)
    return rig, clock, Camera(clock)


def clocks(clock):
    stack = ExitStack()
    for name in ('cartpole_sdk.rig.client.time', 'cartpole_sdk.rig.policy.time',
                 'cartpole_sdk.identification.experiments.time',
                 'cartpole_sdk.identification.driven_capture.time'):
        stack.enter_context(patch(name, clock))
    return stack


def assert_stopped(rig):
    assert rig.commands[-1][1] == 'STOP'
    assert not rig.state.enabled
    assert not any(c[1] in ('HOME', 'CLEAR', 'CALIBRATE', 'SET') for c in rig.commands)


def test_presets_are_json_choices_with_progressive_signed_excitation_and_no_shared_mutation():
    driven = module()
    gentle, standard = driven.actuator_plan(), driven.actuator_plan('standard')
    assert json.loads(json.dumps(gentle)) == gentle
    assert len(standard) > len(gentle) >= 4
    assert max(abs(t['amplitude_m']) for t in gentle) >= .02
    assert max(abs(t['amplitude_m']) for t in standard) >= .05
    assert {'pulse', 'reversal'} <= {t['kind'] for t in standard}
    for trial in standard:
        assert any(t['kind'] == trial['kind'] and t['amplitude_m'] == -trial['amplitude_m']
                   and t['segment_s'] == trial['segment_s'] for t in standard)
    gentle[0]['amplitude_m'] = 100.
    assert driven.actuator_plan()[0]['amplitude_m'] != 100.
    with pytest.raises(ValidationError):
        driven.actuator_plan('aggressive')


def test_references_have_finite_analytic_derivatives_zero_endpoints_and_bounded_excitation():
    driven = module()
    for trial in driven.actuator_plan('standard'):
        duration = trial['segment_s'] * (2 if trial['kind'] == 'pulse' else 3)
        assert driven.trajectory(0., trial) == (0.,) * 4
        assert driven.trajectory(duration, trial) == (0.,) * 4
        maxima = [0.] * 4
        for k in range(1, 1000):
            t = duration * k / 1000
            point = driven.trajectory(t, trial)
            h = 1e-7
            left, right = driven.trajectory(t-h, trial), driven.trajectory(t+h, trial)
            for j in range(3):
                assert (right[j]-left[j])/(2*h) == pytest.approx(point[j+1], abs=2e-5)
            maxima = [max(a, abs(b)) for a, b in zip(maxima, point)]
        assert maxima[0] < .08 and maxima[1] < .6 and maxima[2] < 8 and maxima[3] < 150


def test_real_actuator_runner_pins_live_readback_and_short_leases_and_stops():
    driven = module()
    rig, clock, camera = setup_rig()
    trial = driven.actuator_plan('standard')[-1]
    wrappers = []
    def wrap(policy):
        wrappers.append(policy)
        return policy
    with clocks(clock):
        result = driven.run_actuator(rig, trial=trial, camera=camera, expected_reference=330,
                                     expected_home=14, policy_wrapper=wrap)
    assert_stopped(rig)
    assert result['parameters'] == asdict(ControllerParameters())
    assert result['reference'] == 330 and result['home_epoch'] == 14
    assert result['completed'] is True and result['hardware_validated'] is False
    assert wrappers
    actions = [r['request'] for r in rig.records if r['type'] == 'action_request']
    assert len(actions) > 300
    assert all(a['expires_at_ns']-a['issued_at_ns'] == 20_000_000 for a in actions)
    assert max(abs(a['acceleration_m_s2']) for a in actions) > 1.
    assert all(abs(a['acceleration_m_s2']) <= 8. for a in actions)
    for a, b in zip(actions, actions[1:]):
        assert abs(a['acceleration_m_s2']-b['acceleration_m_s2']) <= 150*(b['issued_at_ns']-a['issued_at_ns'])/1e9+1e-9
    assert not any(c[1] in ('MODE', 'REHOME') for c in rig.commands)


@pytest.mark.parametrize('fault', ('camera_stale', 'camera_failure', 'x', 'v', 'theta', 'wait', 'home', 'reference', 'catalog', 'preset', 'jerk'))
def test_driven_failures_stop_and_propagate_without_recovery(fault):
    driven = module()
    rig, clock, camera = setup_rig()
    trial = driven.actuator_plan()[0]
    original = rig.wait_state
    def wait(*args, **kwargs):
        state = original(*args, **kwargs)
        if state.enabled:
            if fault == 'wait':
                raise RuntimeError('injected wait failure')
            if fault == 'camera_stale': camera.stale = True
            if fault == 'camera_failure': camera.failure = RuntimeError('camera failed')
            if fault in ('x', 'v', 'theta'):
                values = {'x': {'x': .1}, 'v': {'velocity': .6}, 'theta': {'theta': math.pi+1.5}}[fault]
                rig._state = replace(state, **values)
        return rig.state
    rig.wait_state = wait
    if fault == 'home': rig._info.home_epoch = 15
    if fault == 'reference': rig._info.encoder_upright_raw = 331
    if fault == 'catalog': rig.get_parameters = lambda: {'jmax': 150.}
    if fault == 'preset': trial['amplitude_m'] = .5
    if fault == 'jerk': rig.parameters = replace(rig.parameters, jmax=1.)
    with clocks(clock), pytest.raises((ValidationError, RuntimeError)):
        driven.run_actuator(rig, trial=trial, camera=camera, expected_reference=330, expected_home=14)
    assert_stopped(rig)
    assert not any(c[1] == 'REHOME' for c in rig.commands)
    if fault in ('home', 'reference', 'catalog', 'preset', 'jerk'):
        assert not any(c[1] == 'ARM' for c in rig.commands)


def test_live_small_rail_rejects_large_trial_before_arm():
    driven = module()
    rig, clock, camera = setup_rig()
    rig.parameters = replace(rig.parameters, rail=.04)
    rig._info.rail_half_m = .04
    with clocks(clock), pytest.raises(ValidationError, match='rail|position'):
        driven.run_actuator(rig, trial=driven.actuator_plan('standard')[-1], camera=camera)
    assert_stopped(rig)
    assert not any(c[1] == 'ARM' for c in rig.commands)


def test_missing_camera_geometry_remains_explicit_quality_loss_not_motion_evidence():
    driven = module()
    rig, clock, camera = setup_rig()
    camera.missing_geometry = True
    with clocks(clock):
        result = driven.run_timing_hold(rig, seconds=1., camera=camera)
    assert_stopped(rig)
    assert result['camera_quality']['missing_geometry_frames'] > 0
    assert result['camera_quality']['valid_geometry_frames'] == 0
    assert all(r['request']['acceleration_m_s2'] == 0. for r in rig.records if r['type'] == 'action_request')


def test_timing_hold_preserves_identity_pins_and_does_not_inject_delays():
    driven = module()
    rig, clock, camera = setup_rig()
    with clocks(clock):
        result = driven.run_timing_hold(rig, seconds=1., camera=camera, expected_home=14)
    assert_stopped(rig)
    assert result['policy']['elapsed_board_s'] >= 1.
    rows = [r['request'] for r in rig.records if r['type'] == 'action_request']
    assert len(rows) >= 100
    assert {b['issued_at_ns']-a['issued_at_ns'] for a, b in zip(rows, rows[1:])} == {10_000_000}


def test_coupled_runs_preserved_auto_to_completion_with_unrestricted_pole_phase():
    driven = module()
    rig, clock, camera = setup_rig()
    original = rig.wait_state
    def wait(*args, **kwargs):
        state = original(*args, **kwargs)
        if state.enabled:
            rig._state = replace(state, theta=0., omega=8., x=.12)
        return rig.state
    rig.wait_state = wait
    with clocks(clock):
        result = driven.run_coupled(rig, seconds=1., camera=camera, expected_home=14)
    assert_stopped(rig)
    assert result['completed'] is True
    assert any(c[1] == 'MODE' and c[3] == 'auto' for c in rig.commands)
    assert not any(c[1] in ('ARM', 'A', 'REHOME') for c in rig.commands)
    assert clock.monotonic() >= 2.


@pytest.mark.parametrize('fault', ('fault', 'rail', 'stale', 'deadline', 'early_stop', 'changed_home'))
def test_coupled_failure_abandons_without_rehome_clear_or_parameter_change(fault):
    driven = module()
    rig, clock, camera = setup_rig()
    original = rig.wait_state
    def wait(*args, **kwargs):
        state = original(*args, **kwargs)
        if state.enabled or fault == 'changed_home':
            if fault == 'fault': rig._state = replace(state, mode=4, fault=1, flags=state.flags & ~2)
            if fault == 'rail': rig._state = replace(state, x=.251)
            if fault == 'stale': camera.stale = True
            if fault == 'deadline': rig.native_finish = clock.now_ns+100_000_000_000
            if fault == 'early_stop': rig._state = replace(state, mode=0, flags=state.flags & ~2)
            if fault == 'changed_home' and clock.monotonic() > 1.5: rig._info.home_epoch = 15
        return rig.state
    rig.wait_state = wait
    with clocks(clock), pytest.raises((ValidationError, RuntimeError)):
        driven.run_coupled(rig, seconds=1., camera=camera, expected_home=14)
    assert_stopped(rig)
    assert not any(c[1] == 'REHOME' for c in rig.commands)


def test_explicit_saved_home_return_waits_for_disabled_same_epoch_without_full_home():
    driven = module()
    rig, clock, camera = setup_rig()
    rig._state = replace(rig._state, x=.03, theta=0., omega=1.)
    with clocks(clock):
        result = driven.return_saved_home(rig, camera=camera, expected_reference=330, expected_home=14)
    assert_stopped(rig)
    assert result['home_epoch'] == 14 and rig.state.x == 0.
    assert clock.monotonic() >= .1
    assert sum(c[1] == 'REHOME' for c in rig.commands) == 1


def test_failed_stop_is_not_reported_as_success_and_primary_failure_is_preserved():
    driven = module()
    for primary in (False, True):
        rig, clock, camera = setup_rig()
        original = rig.stop
        def stop():
            original()
            raise RuntimeError('STOP transport failure')
        rig.stop = stop
        if primary: camera.failure = ValueError('primary camera failure')
        with clocks(clock), pytest.raises((RuntimeError, ValueError), match='primary camera failure' if primary else 'STOP transport failure'):
            driven.run_timing_hold(rig, seconds=1., camera=camera)
        assert any(r['type'] == 'driven_stop' and r['confirmed'] is False for r in rig.records)


def test_wrapper_failure_before_reset_preserves_primary_error_and_always_stops():
    driven = module()
    rig, clock, camera = setup_rig()
    def broken_wrapper(policy):
        raise RuntimeError('timing wrapper could not initialize')
    with clocks(clock), pytest.raises(RuntimeError, match='timing wrapper could not initialize'):
        driven.run_timing_hold(rig, seconds=1., camera=camera, policy_wrapper=broken_wrapper)
    assert_stopped(rig)
    assert any(r['type'] == 'driven_stop' and r['confirmed'] for r in rig.records)


def test_readiness_callback_cannot_change_identity_before_arm():
    driven = module()
    rig, clock, camera = setup_rig()
    def ready(status):
        rig._info.home_epoch = 15
    with clocks(clock), pytest.raises(ValidationError, match='home'):
        driven.run_timing_hold(rig, seconds=1., camera=camera, ready=ready)
    assert_stopped(rig)
    assert not any(c[1] == 'ARM' for c in rig.commands)


@pytest.mark.parametrize('fault', ('board_gap', 'host_gap', 'replay'))
def test_driven_policy_rejects_cadence_and_replays_before_new_command(fault):
    driven = module()
    rig, clock, camera = setup_rig()
    limits = dict(position_m=.1, velocity_m_s=.6, acceleration_m_s2=8., jerk_m_s3=150.)
    policy = driven.DrivenPolicy(driven.CHANNELS, trial=driven.actuator_plan()[0],
                                 initial_hanging=math.pi, limits=limits, clock_ns=clock.monotonic_ns)
    policy.reset(Session('7', 'teensy:7'))
    policy.act(observation())
    clock.now_ns = 20_000_000 if fault == 'host_gap' else 10_000_000
    sample = observation(20 if fault == 'board_gap' else 10, sequence=0 if fault == 'replay' else None)
    with pytest.raises(ValidationError, match='cadence'):
        policy.act(sample)


def test_fresh_geometry_is_counted_as_raw_valid_frames():
    driven = module()
    rig, clock, camera = setup_rig()
    with clocks(clock):
        result = driven.run_timing_hold(rig, seconds=1., camera=camera)
    assert result['camera_quality']['valid_geometry_frames'] > 100
    assert result['camera_quality']['missing_geometry_frames'] == 0


@pytest.mark.parametrize('fault', ('fault', 'deadline', 'stale', 'epoch'))
def test_saved_home_return_failures_stop_without_retry_or_clear(fault):
    driven = module()
    rig, clock, camera = setup_rig()
    rig._state = replace(rig.state, x=.03)
    original = rig.wait_state
    def wait(*args, **kwargs):
        state = original(*args, **kwargs)
        if state.enabled:
            if fault == 'fault': rig._state = replace(state, mode=4, fault=1, flags=state.flags & ~2)
            if fault == 'deadline': rig.native_finish = clock.now_ns+100_000_000_000
            if fault == 'stale': camera.stale = True
            if fault == 'epoch': rig._info.home_epoch = 15
        return rig.state
    rig.wait_state = wait
    with clocks(clock), pytest.raises((ValidationError, RuntimeError)):
        driven.return_saved_home(rig, camera=camera, expected_home=14)
    assert_stopped(rig)
    assert sum(c[1] == 'REHOME' for c in rig.commands) == 1
