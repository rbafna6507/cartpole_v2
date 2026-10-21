"""Rehearse the balance-only boundary without a serial device or motor."""
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from hashlib import sha256
import gc
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.policies import neural
from test_neural_runner import DeadlineAwareShadowRig, prepared_rig
from test_policy_sensor_contract import numeric_actor
from test_rig_console import ScriptedClock


def saved_actor(tmp_path, *, demand=0., mode='raw', legacy=False, bad_runtime=False):
    actor = numeric_actor(mode, legacy=legacy)
    actor['layers'][-1]['bias'] = [demand]
    root = Path(neural.__file__).resolve().parents[1]
    actor['runtime_sha256'] = {name: sha256((root/name).read_bytes()).hexdigest()
                               for name in neural.RUNTIME_FILES}
    if bad_runtime:
        actor['runtime_sha256']['rig/client.py'] = '0'*64
    actor.pop('content_sha256')
    actor['content_sha256'] = neural._digest(actor)
    path = tmp_path/'actor.json'
    path.write_text(json.dumps(actor))
    return path


@contextmanager
def rehearsal(*, rig_type=DeadlineAwareShadowRig, state=None):
    clock = ScriptedClock()
    with ExitStack() as stack:
        for name in ('cartpole_sdk.rig.neural_runner.time', 'cartpole_sdk.rig.policy.time',
                     'cartpole_sdk.rig.client.time'):
            stack.enter_context(patch(name, clock))
        rig = prepared_rig(clock, rig_type=rig_type)
        rig._state = replace(rig._state, **({'x': .005, 'theta': .02,
                                            'angle_hat': .02, 'omega': .1} | (state or {})))
        rig._history[rig._state.unwrapped_tick] = rig._state
        stack.enter_context(rig)
        yield rig


def run(rig, actor, **kwargs):
    from cartpole_sdk.learning.balance_hardware import run_balance_policy
    return run_balance_policy(rig, actor, development_only=True,
                              expected_upright_raw=123, duration_s=.04, **kwargs)


def test_default_shadow_never_arms_and_keeps_hardware_acceptance_false(tmp_path):
    actor = saved_actor(tmp_path)
    with rehearsal() as rig:
        result = run(rig, actor)
        assert result['mode'] == 'shadow' and result['task'] == 'balance-only'
        assert result['hardware_accepted'] is False
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
        assert rig.commands[-1][1] == 'STOP' and not rig.state.enabled


def test_explicit_execute_keeps_leases_and_stops_without_changing_parameters(tmp_path):
    actor = saved_actor(tmp_path, demand=.1)
    with rehearsal() as rig:
        before = rig.parameters
        result = run(rig, actor, execute=True)
        assert result['mode'] == 'execute'
        requests = [r['request'] for r in rig.records if r['type'] == 'action_request']
        assert requests and all(r['expires_at_ns']-r['issued_at_ns'] == 20_000_000 for r in requests)
        assert all(r['acceleration_m_s2'] == .1 for r in requests)
        assert rig.parameters == before
        assert {c[1] for c in rig.commands} == {'ARM', 'A', 'STOP'}
        assert rig.commands[-1][1] == 'STOP' and not rig.state.enabled


@pytest.mark.parametrize('state', [dict(theta=3.14), dict(theta=.071), dict(theta=-.071), dict(x=.016),
                                    dict(velocity=.026), dict(omega=.151), dict(brake_direction=1)])
def test_unsuitable_start_is_rejected_before_arm(tmp_path, state):
    actor = saved_actor(tmp_path)
    with rehearsal(state=state) as rig:
        with pytest.raises(ValidationError, match='balance-only'):
            run(rig, actor, execute=True)
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
        assert rig.commands[-1][1] == 'STOP'


@pytest.mark.parametrize('state', [dict(theta=.15), dict(theta=-.151), dict(omega=1.01), dict(x=.12), dict(x=-.121),
                                    dict(velocity=.25), dict(velocity=-.251), dict(velocity=1.5),
                                    dict(brake_direction=-1)])
def test_leaving_balance_envelope_stops_before_next_action(tmp_path, state):
    class DepartingRig(DeadlineAwareShadowRig):
        def wait_state(self, **kwargs):
            super().wait_state(**kwargs)
            self._state = replace(self._state, **state)
            self._history[self._state.unwrapped_tick] = self._state
            return self._state
    actor = saved_actor(tmp_path, demand=.1)
    with rehearsal(rig_type=DepartingRig) as rig:
        with pytest.raises(ValidationError, match='balance-only'):
            run(rig, actor, execute=True)
        assert len([r for r in rig.records if r['type'] == 'action_request']) == 1
        assert rig.commands[-1][1] == 'STOP' and not rig.state.enabled


def test_start_is_rechecked_after_arm_before_first_action(tmp_path):
    class MovingAtArmRig(DeadlineAwareShadowRig):
        def _command_state(self, command, *args, **kwargs):
            super()._command_state(command, *args, **kwargs)
            if command == 'ARM':
                self._state = replace(self._state, theta=.08)
                self._history[self._state.unwrapped_tick] = self._state
    actor = saved_actor(tmp_path)
    with rehearsal(rig_type=MovingAtArmRig) as rig:
        with pytest.raises(ValidationError, match='balance-only'):
            run(rig, actor, execute=True)
        assert any(c[1] == 'ARM' for c in rig.commands)
        assert not any(c[1] == 'A' for c in rig.commands)
        assert rig.commands[-1][1] == 'STOP' and not rig.state.enabled


def test_existing_neural_cadence_rejection_remains_active(tmp_path):
    actor = saved_actor(tmp_path)
    with rehearsal() as rig:
        rig.intervals = iter([16])
        with pytest.raises(ValidationError, match='cadence'):
            run(rig, actor, execute=True)
        assert len([r for r in rig.records if r['type'] == 'action_request']) == 1
        assert rig.commands[-1][1] == 'STOP' and not rig.state.enabled


def test_reference_changed_by_shared_preflight_is_rejected_before_arm(tmp_path):
    class ChangedReferenceRig(DeadlineAwareShadowRig):
        info_reads = 0
        def get_info(self):
            self.info_reads += 1
            if self.info_reads == 2:
                self._info.encoder_upright_raw = 124
            return super().get_info()
    actor = saved_actor(tmp_path)
    with rehearsal(rig_type=ChangedReferenceRig) as rig:
        with pytest.raises(ValidationError, match='reference'):
            run(rig, actor, execute=True)
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
        assert rig.commands[-1][1] == 'STOP'


def test_cached_reference_change_stops_without_active_info_command(tmp_path):
    class ChangedReferenceRig(DeadlineAwareShadowRig):
        def get_info(self):
            assert not self.state.enabled, 'INFO must never block the armed action path'
            return super().get_info()
        def wait_state(self, **kwargs):
            super().wait_state(**kwargs)
            self._info.encoder_upright_raw = 124
            return self._state
    actor = saved_actor(tmp_path)
    with rehearsal(rig_type=ChangedReferenceRig) as rig:
        with pytest.raises(ValidationError, match='reference'):
            run(rig, actor, execute=True)
        assert len([r for r in rig.records if r['type'] == 'action_request']) == 1
        assert rig.commands[-1][1] == 'STOP' and not rig.state.enabled


@pytest.mark.parametrize('problem', ['reference', 'parameters', 'home', 'magnet'])
def test_existing_live_admission_and_expected_reference_cannot_be_bypassed(tmp_path, problem):
    actor = saved_actor(tmp_path)
    with rehearsal() as rig:
        if problem == 'reference': rig._info.encoder_upright_raw = 124
        if problem == 'parameters': rig.parameters = replace(rig.parameters, bw=6.)
        if problem == 'home': rig._state = replace(rig._state, flags=rig._state.flags & ~4)
        if problem == 'magnet': rig._info.mag_status = 0
        with pytest.raises(ValidationError):
            run(rig, actor, execute=True)
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
        assert rig.commands[-1][1] == 'STOP'


def test_acceleration_ceiling_faults_instead_of_clipping(tmp_path):
    actor = saved_actor(tmp_path, demand=.5)
    with rehearsal() as rig:
        with pytest.raises(ValidationError, match='commissioning bound'):
            run(rig, actor, execute=True)
        assert not any(c[1] == 'A' for c in rig.commands)
        assert rig.commands[-1][1] == 'STOP'


@pytest.mark.parametrize('options', [dict(bad_runtime=True), dict(mode='vision'), dict(legacy=True)])
def test_cli_rejects_actor_contract_before_opening_device(tmp_path, options):
    from cartpole_sdk.learning.balance_hardware import main
    actor = saved_actor(tmp_path, **options)
    def forbidden(*args, **kwargs):
        pytest.fail('invalid actor must not open a serial device')
    with pytest.raises(SystemExit) as error:
        main(['--actor', str(actor), '--port', 'unopened', '--development-only',
              '--expected-upright-raw', '123'], rig_factory=forbidden)
    assert error.value.code == 2


def test_cli_defaults_to_shadow_with_scripted_device(tmp_path, capsys):
    from cartpole_sdk.learning.balance_hardware import main
    actor = saved_actor(tmp_path)
    with rehearsal() as rig:
        code = main(['--actor', str(actor), '--port', 'scripted', '--development-only',
                     '--expected-upright-raw', '123', '--duration', '.04'],
                    rig_factory=lambda *args, **kwargs: rig)
        assert code == 0
        assert json.loads(capsys.readouterr().out)['mode'] == 'shadow'
        assert not any(c[1] in ('ARM', 'A') for c in rig.commands)


@pytest.mark.parametrize('initially_enabled', [True, False])
def test_cli_defers_cyclic_gc_until_rig_close_then_restores_state(tmp_path, initially_enabled):
    from cartpole_sdk.learning.balance_hardware import main
    actor = saved_actor(tmp_path)
    original_gc_state = gc.isenabled()
    try:
        (gc.enable if initially_enabled else gc.disable)()
        with rehearsal() as rig:
            closes = []
            original_close = rig.close
            def record_close():
                closes.append(gc.isenabled())
                original_close()
            rig.close = record_close
            def factory(*args, **kwargs):
                assert not gc.isenabled(), 'cyclic GC must be deferred before opening the rig'
                return rig
            assert main(['--actor', str(actor), '--port', 'scripted', '--development-only',
                         '--expected-upright-raw', '123', '--duration', '.04'], rig_factory=factory) == 0
            assert closes == [False]
            assert gc.isenabled() == initially_enabled
            boundary = next(r for r in rig.records if r['type'] == 'balance_only_boundary')
            assert boundary['gc_policy']['cyclic_gc_enabled'] is False
            assert len(boundary['runtime_helper_sha256']) == 64
    finally:
        (gc.enable if original_gc_state else gc.disable)()


def test_cli_failure_stops_and_closes_before_restoring_cyclic_gc(tmp_path):
    from cartpole_sdk.learning.balance_hardware import main
    actor = saved_actor(tmp_path)
    original_gc_state = gc.isenabled()
    try:
        gc.enable()
        with rehearsal(state={'theta': 3.14}) as rig:
            closes = []
            original_close = rig.close
            def record_close():
                closes.append(gc.isenabled())
                original_close()
            rig.close = record_close
            with pytest.raises(SystemExit) as error:
                main(['--actor', str(actor), '--port', 'scripted', '--development-only', '--execute',
                      '--expected-upright-raw', '123', '--duration', '.04'],
                     rig_factory=lambda *args, **kwargs: rig)
            assert error.value.code == 2
            assert closes == [False] and gc.isenabled()
            assert not any(c[1] in ('ARM', 'A') for c in rig.commands)
            assert rig.commands[-1][1] == 'STOP'
    finally:
        (gc.enable if original_gc_state else gc.disable)()


@pytest.mark.parametrize('extra', [[], ['--development-only', '--duration', '11'],
                                  ['--development-only', '--max-acceleration', '26']])
def test_cli_rejects_missing_admission_or_out_of_bound_options_before_serial(tmp_path, extra):
    from cartpole_sdk.learning.balance_hardware import main
    def forbidden(*args, **kwargs):
        pytest.fail('invalid options must not open a serial device')
    with pytest.raises(SystemExit) as error:
        main(['--actor', str(tmp_path/'missing.json'), '--port', 'unopened',
              '--expected-upright-raw', '123', *extra], rig_factory=forbidden)
    assert error.value.code == 2
