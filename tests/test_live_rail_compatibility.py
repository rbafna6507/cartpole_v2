"""Measured-home repeatability must never expand the active safety envelope."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.learning.balance_hardware import BalanceOnlyPolicy
from cartpole_sdk.policies.neural import NeuralPolicy, _digest
from cartpole_sdk.policies.rig_observation import rig_channels
from cartpole_sdk.rig.neural_runner import validate_live_executor
from test_balance_hardware import rehearsal, run, saved_actor
from test_neural_runner import DeadlineAwareShadowRig
from test_policy_sensor_contract import numeric_actor


def actor_with_rail(rail):
    actor = numeric_actor('raw')
    actor['executor_parameters']['rail'] = rail
    actor.pop('content_sha256')
    actor['content_sha256'] = _digest(actor)
    return actor


def live_rail(rig, rail, *, span=17000):
    rig.parameters = replace(rig.parameters, rail=rail)
    rig._info.rail_half_m = float(format(rail, '.7g'))
    rig._info.measured_span_steps = span


@pytest.mark.parametrize(('rail', 'span'), [
    (.308925003, 16502), (.308962494, 16504), (.309000015, 16506),
    (.309037507, 16508), (.309074998, 16510),
])
def test_counted_home_repeatability_preserves_actual_readback_and_frozen_actor(rail, span):
    # Up to two 37.5 µm steps in either direction, plus binary32 rounding.
    actor = actor_with_rail(.309)
    frozen_actor = deepcopy(actor)
    policy = NeuralPolicy(actor, channels=rig_channels())
    with rehearsal() as rig:
        live_rail(rig, rail, span=span)
        before = asdict(rig.parameters)
        actual = validate_live_executor(rig, policy)
        assert actual == before and actual['rail'] == rail
        assert asdict(rig.parameters) == before
        assert policy.executor_parameters['rail'] == .309
        assert policy.actor == frozen_actor
        diagnostics = next(r for r in rig.records if r['type'] == 'neural_preflight')['rail_compatibility']
        assert diagnostics['trained_rail_m'] == .309
        assert diagnostics['live_rail_m'] == rail
        assert diagnostics['max_delta_m'] == pytest.approx(.000075, abs=6e-8)
        assert diagnostics['measured_span_steps'] == span
        assert diagnostics['live_rail_cap_m'] == pytest.approx(rail, abs=1e-9)
        assert not rig.commands


def test_repeatability_allowance_cannot_expand_the_current_measured_cap():
    with rehearsal() as rig:
        live_rail(rig, .309037507, span=16506)  # Only one step beyond the actual .309000015 cap.
        with pytest.raises(ValidationError, match='measured homing cap'):
            validate_live_executor(rig, NeuralPolicy(actor_with_rail(.309), channels=rig_channels()))
        assert not rig.commands


@pytest.mark.parametrize('rail', [.3088875, .3091125, .308, .310])
def test_material_rail_change_is_refused(rail):
    with rehearsal() as rig:
        live_rail(rig, rail)
        with pytest.raises(ValidationError, match='rail'):
            validate_live_executor(rig, NeuralPolicy(actor_with_rail(.309), channels=rig_channels()))
        assert not rig.commands


@pytest.mark.parametrize('problem', ['unhomed', 'span-low', 'span-high', 'epoch', 'info-rail', 'cap', 'margin', 'speed'])
@pytest.mark.parametrize('rail', [.309000015, .309037507])
def test_small_rail_delta_does_not_bypass_live_geometry_or_other_snapshot_checks(problem, rail):
    with rehearsal() as rig:
        live_rail(rig, rail)
        if problem == 'unhomed': rig._state = replace(rig._state, flags=rig._state.flags & ~4)
        if problem == 'span-low': rig._info.measured_span_steps = 10666
        if problem == 'span-high': rig._info.measured_span_steps = 20001
        if problem == 'epoch': rig._info.home_epoch = 0
        if problem == 'info-rail': rig._info.rail_half_m = .31
        if problem == 'cap': rig._info.measured_span_steps = 16000  # cap .300, below live rail
        if problem == 'margin': rig.parameters = replace(rig.parameters, rail_margin=.014)
        if problem == 'speed': rig.parameters = replace(rig.parameters, vmax=1.)
        with pytest.raises(ValidationError):
            validate_live_executor(rig, NeuralPolicy(actor_with_rail(.309), channels=rig_channels()))
        assert not rig.commands


def test_stopped_diagnostics_can_report_rate_mismatch_without_waiving_live_admission():
    policy = NeuralPolicy(numeric_actor('raw'), channels=rig_channels())
    with rehearsal() as rig:
        rig.rate_hz = 250
        with pytest.raises(ValidationError, match='100 Hz'):
            validate_live_executor(rig, policy)
        assert validate_live_executor(rig, policy, require_rate=False) == asdict(rig.parameters)
        diagnostics = next(r for r in rig.records if r['type'] == 'neural_preflight')
        assert diagnostics['telemetry_rate_hz'] == 250
        assert diagnostics['required_telemetry_rate_hz'] == 100
        rig.parameters = replace(rig.parameters, bw=6.)
        with pytest.raises(ValidationError, match='bw'):
            validate_live_executor(rig, policy, require_rate=False)
        assert not rig.commands


@pytest.mark.parametrize(('trained', 'current', 'expected'), [
    (.309, .308962494, .2989625036716461),
    (.309, .309037507, .29899999499320984),
])
def test_live_binding_intersects_trained_and_current_hard_rail(trained, current, expected):
    policy = BalanceOnlyPolicy(actor_with_rail(trained), channels=rig_channels(), guard_profile='rig')
    with rehearsal() as rig:
        live_rail(rig, current)
        validate_live_executor(rig, policy)
        assert policy.position_limit == expected
        assert policy.run_limits['position_m'] == expected
        assert policy.executor_parameters['rail'] == trained


@pytest.mark.parametrize('guard_profile', ['commissioning', 'rig'])
@pytest.mark.parametrize('side', [-1, 1])
def test_smaller_live_boundary_stops_before_next_action(tmp_path, guard_profile, side):
    # Use a narrow explicit rail so commissioning's .12 m ceiling cannot mask
    # the need to apply the smaller current rail before the run starts.
    boundary = .09998 if guard_profile == 'commissioning' else .10498
    class DepartingRig(DeadlineAwareShadowRig):
        def wait_state(self, **kwargs):
            super().wait_state(**kwargs)
            self._state = replace(self._state, x=side*boundary)
            self._history[self._state.unwrapped_tick] = self._state
            return self._state
    actor = saved_actor(tmp_path, demand=.1, executor_parameters={'rail': .115})
    with rehearsal(rig_type=DepartingRig) as rig:
        live_rail(rig, .1149625)
        with pytest.raises(ValidationError, match='balance-only envelope'):
            run(rig, actor, execute=True, guard_profile=guard_profile)
        assert len([r for r in rig.records if r['type'] == 'action_request']) == 1
        assert rig.commands[-1][1] == 'STOP' and not rig.state.enabled


def test_larger_live_rail_never_expands_trained_boundary(tmp_path):
    class DepartingRig(DeadlineAwareShadowRig):
        def wait_state(self, **kwargs):
            super().wait_state(**kwargs)
            self._state = replace(self._state, x=.10502)
            self._history[self._state.unwrapped_tick] = self._state
            return self._state
    actor = saved_actor(tmp_path, demand=.1, executor_parameters={'rail': .115})
    with rehearsal(rig_type=DepartingRig) as rig:
        live_rail(rig, .1150375)
        with pytest.raises(ValidationError, match='balance-only envelope'):
            run(rig, actor, execute=True, guard_profile='rig')
        assert len([r for r in rig.records if r['type'] == 'action_request']) == 1
