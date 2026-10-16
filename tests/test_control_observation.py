"""Explicit governor feedback augments observations without resampling sensors."""
from dataclasses import replace
import math

import pytest

from cartpole_sdk.contracts import (
    ActionRequest, Channel, Observation, Sample, Session, ValidationError,
    validate_observation,
)
from cartpole_sdk.rig import Rig, RigError
from cartpole_sdk.sim import SimulationConfig, SensorConfig
from cartpole_sdk.sim.executor import ExecutorSimulation
from test_rig import FDTransport, Firmware


class FeedbackFirmware(Firmware):
    def state(self, **kwargs):
        fields = super().state(**kwargs).split()
        fields[12] = '1.25'  # Executed acceleration, distinct from raw demand.
        fields[13] = '7.5'
        fields[18] = '-1'
        return ' '.join(fields)


class CountingRig(Rig):
    state_reads = 0

    @property
    def state(self):
        self.state_reads += 1
        return super().state


@pytest.fixture
def rig():
    firmware = FeedbackFirmware()
    try:
        with CountingRig(firmware.port, rate_hz=0, transport_factory=FDTransport,
                         command_timeout=.2) as connected:
            yield connected, firmware
    finally:
        firmware.close()


def control_observation(backend):
    assert hasattr(backend, 'control_observation'), 'explicit controller feedback is missing'
    return backend.control_observation()


def test_cart_governor_quantities_have_explicit_units_and_topology():
    samples = tuple(Sample('cart', quantity, 'step', value, unit, 'cart-step-home',
                           'governor_state', 'valid', None, 'estimated', 0, 0, 0)
                    for quantity, value, unit in (
                        ('acceleration', 1.25, 'm/s^2'), ('brake_direction', -1, '1')))
    session = Session('feedback', 'board')
    observation = Observation('feedback', 'board', 0, 0, 'board snapshot', samples)
    validate_observation(session, observation)
    for sample in samples:
        with pytest.raises(ValidationError):
            replace(sample, unit='rad')
        with pytest.raises(ValidationError):
            validate_observation(session, replace(observation,
                samples=(replace(sample, entity='pole'),)))
    assert Channel('pole', 'angle', 'magnetic_filtered', 'encoder-zero').source == 'magnetic_filtered'


def test_rig_opt_in_feedback_uses_one_snapshot_and_preserves_bare_observation(rig):
    connected, _ = rig
    bare = connected.observation()
    before_reads = connected.state_reads
    feedback = control_observation(connected)
    assert connected.state_reads == before_reads+1
    assert len(bare.samples) == 4
    assert feedback.samples[:4] == bare.samples
    assert connected.observation() == bare
    assert (feedback.sequence, feedback.available_ns) == (bare.sequence, bare.available_ns)
    validate_observation(connected.session, feedback)
    extra = {(sample.quantity, sample.source): sample for sample in feedback.samples[4:]}
    assert len(extra) == 3
    angle = extra['angle', 'magnetic_filtered']
    assert angle.value == .19
    assert angle.value != bare.samples[0].value  # Raw theta is .2.
    assert angle.frame_id == 'encoder-zero'
    assert angle.method == 'filtered_magnetic_angle'
    acceleration = extra['acceleration', 'step']
    assert acceleration.value == 1.25  # Never raw balance demand (7.5).
    assert acceleration.unit == 'm/s^2'
    assert acceleration.method == 'commanded_acceleration'
    brake = extra['brake_direction', 'step']
    assert brake.value == -1
    assert brake.unit == '1'
    assert brake.method == 'governor_brake_direction'
    for sample in (acceleration, brake):
        assert sample.frame_id == 'cart-step-home'
    for sample in extra.values():
        assert sample.kind == 'estimated'
        assert sample.validity == 'valid'
        assert (sample.acquired_ns, sample.effective_ns, sample.received_ns) == (bare.available_ns,)*3


def test_rig_filtered_angle_preserves_encoder_health(rig):
    connected, firmware = rig
    previous = connected.state.tick
    firmware.flags &= ~1
    firmware.send(firmware.state(tick=(previous+1)&0xffffffff))
    connected.wait_state(after_tick=previous)
    feedback = control_observation(connected)
    angle = next(sample for sample in feedback.samples if sample.source == 'magnetic_filtered')
    assert angle.validity == 'invalid'
    assert angle.value is None
    assert angle.reason == 'encoder unhealthy'


def test_rig_feedback_rejects_stale_receipt(rig):
    connected, _ = rig
    with connected._condition:
        connected._state = replace(connected._state, received_ns=0)
    with pytest.raises(ValidationError, match='stale'):
        control_observation(connected)


def test_rig_feedback_requires_connection():
    connected = Rig('not-a-real-device')
    with pytest.raises(RigError, match='not connected'):
        control_observation(connected)


@pytest.fixture
def simulation():
    backend = ExecutorSimulation(config=SimulationConfig(control_steps=10),
        sensors=SensorConfig(sample_every_steps=4, delay_steps=3, frame_id='sim:test-frame'))
    try:
        yield backend
    finally:
        backend.close()


def action(backend, value=25.):
    observation = backend.observation
    return ActionRequest(observation.session_id, observation.clock_id, 0,
        observation.sequence, observation.available_ns, observation.available_ns+20_000_000, value)


def test_simulation_feedback_requires_reset(simulation):
    with pytest.raises(RuntimeError, match='reset'):
        control_observation(simulation)


def test_simulation_feedback_preserves_unknown_sensor_warmup(simulation):
    bare = simulation.reset()
    feedback = control_observation(simulation)
    assert len(bare.samples) == 4
    assert feedback.samples[:4] == bare.samples
    assert simulation.observation is bare
    assert all(sample.validity == 'unknown' for sample in feedback.samples[:4])
    assert all(sample.effective_ns is None for sample in feedback.samples[:4])
    assert [sample.value for sample in feedback.samples[4:]] == [0., 0]
    assert all(sample.effective_ns == 0 for sample in feedback.samples[4:])
    validate_observation(simulation.session, feedback)


def test_simulation_governor_feedback_does_not_refresh_delayed_sensors(simulation):
    simulation.reset(state=(0., 0., math.pi, 0.))
    bare = simulation.step(action(simulation))
    before = simulation.ground_truth, simulation.motion
    feedback = control_observation(simulation)
    assert feedback.samples[:4] == bare.samples
    assert simulation.observation is bare
    assert len(simulation.observation.samples) == 4
    assert {sample.effective_ns for sample in feedback.samples[:4]} == {4_000_000}
    assert {sample.received_ns for sample in feedback.samples[:4]} == {7_000_000}
    assert feedback.available_ns == 10_000_000
    assert feedback.sequence == bare.sequence
    acceleration, brake = feedback.samples[4:]
    assert acceleration.quantity == 'acceleration'
    assert acceleration.value == pytest.approx(1.5, abs=1e-6)
    assert acceleration.method == 'commanded_acceleration'
    assert brake.quantity == 'brake_direction'
    assert brake.value == 0
    assert brake.method == 'governor_brake_direction'
    for sample in (acceleration, brake):
        assert sample.source == 'simulation'
        assert sample.frame_id == 'sim:test-frame'
        assert sample.kind == 'estimated'
        assert sample.validity == 'valid'
        assert (sample.acquired_ns, sample.effective_ns, sample.received_ns) == (10_000_000,)*3
    assert control_observation(simulation) == feedback
    assert (simulation.ground_truth, simulation.motion) == before
    validate_observation(simulation.session, feedback)


@pytest.mark.parametrize('side', [-1, 1])
def test_simulation_exposes_signed_rail_braking_direction(side):
    backend = ExecutorSimulation(config=SimulationConfig(control_steps=10))
    try:
        backend.reset(state=(side*.24, side*.3, math.pi, 0.))
        backend.step(action(backend, 0.))
        feedback = control_observation(backend)
        brake = next(sample for sample in feedback.samples if sample.quantity == 'brake_direction')
        assert brake.value == side
        assert next(sample for sample in feedback.samples if sample.quantity == 'acceleration').value*side < 0
    finally:
        backend.close()
