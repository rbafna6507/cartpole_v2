"""100 Hz Gym adapter for raw SDK actions, a 1 kHz governor and encoder observer.

This opt-in environment leaves the frozen direct-acceleration model unchanged.
Raw angle plus estimated angular rate matches Rig.observation/HostRatePolicy;
filtered angle is an explicit alternative for ExecutorFeedbackPolicy. All SDK
channels retain source='simulation': names do not certify physical sensors.

The plant is still an ideal acceleration servo with an assumed force ceiling.
Step position is an ideal commanded pulse count, without ISR phase/direction
setup timing, missed steps or backlash. The reused governor checks physical
plant x, which differs from this command-count estimate by quantization while
the servo tracks. Force saturation terminates as unsupported tracking, rather
than allowing that discrepancy to train a policy. Timing settings are declared
integer delays, not measured transport distributions. Faults end the episode;
disabled-motor travel is not modeled.
"""
from collections import deque
from dataclasses import asdict, dataclass, replace
import math

import gymnasium as gym
from gymnasium import spaces
import numpy as np

from cartpole_sdk.contracts import ActionRequest, Observation, Sample, ValidationError
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.control.reference import estimate, wrap
from cartpole_sdk.policies.rig_observation import encode_rig_observation, simulation_channels
from .config import SimulationConfig, integer, number
from .executor import ExecutorSimulation


@dataclass(frozen=True, slots=True)
class RigObservationConfig:
    """Encoder processing at 1 kHz, complete telemetry snapshots at 100 Hz."""
    angle_source: str = 'raw'
    encoder_counts: int = 4096
    angle_noise_std: float = 0.
    telemetry_delay_steps: int = 0
    command_delay_steps: int = 0
    dropout_probability: float = 0.

    def __post_init__(self):
        if self.angle_source not in ('raw', 'filtered'):
            raise ValidationError('angle_source must be raw or filtered')
        integer(self.encoder_counts, 'encoder_counts', positive=True)
        integer(self.telemetry_delay_steps, 'telemetry_delay_steps')
        integer(self.command_delay_steps, 'command_delay_steps')
        if max(self.telemetry_delay_steps, self.command_delay_steps) > 1000:
            raise ValidationError('declared delays must be at most 1000 ticks')
        number(self.angle_noise_std, 'angle_noise_std')
        number(self.dropout_probability, 'dropout_probability')
        if self.dropout_probability > 1:
            raise ValidationError('dropout_probability must be at most one')


class RigCartpoleEnv(gym.Env):
    """Raw acceleration actions; state=[x,v,sin(angle),cos(angle),omega,a,brake].

    x/v/a are commanded estimates, omega is the causal encoder observer output.
    Reset acquires a healthy initial snapshot and advances a zero-demand ARM
    lease until its first delivery (at most 20 ms). Decisions then follow that
    delivery phase. ``step(None)`` and numeric actions on unusable telemetry
    advance the held lease without renewing it. Actions anchor expiry to the
    latest delivered telemetry snapshot. SDK timestamps match Rig's board
    snapshot proxies; true transport age appears only in diagnostic info.
    Ground truth is available only in diagnostics/reward, never state channels.
    """
    metadata = {'render_modes': []}
    step_m = 120 / 3_200_000
    action_semantics = ExecutorSimulation.action_semantics
    frame_id = 'sim:upright+x'

    def __init__(self, config: SimulationConfig, *, parameters: ControllerParameters,
                 observation_config: RigObservationConfig | None = None, ttl_ms=20,
                 render_mode=None):
        if render_mode is not None:
            raise ValidationError('only headless render_mode=None is supported')
        if not isinstance(config, SimulationConfig) or config.physics_dt_ns != 1_000_000 or config.control_steps != 10:
            raise ValidationError('rig Gym requires 1 ms physics and 100 Hz decisions')
        if not isinstance(parameters, ControllerParameters):
            raise ValidationError('an explicit ControllerParameters snapshot is required')
        if type(ttl_ms) is not int or not 1 <= ttl_ms <= 50 or ttl_ms*1_000_000 > config.max_action_ttl_ns:
            raise ValidationError('TTL must be 1..50 ms within the plant action limit')
        self.observation_config = observation_config or RigObservationConfig()
        if not isinstance(self.observation_config, RigObservationConfig):
            raise ValidationError('expected RigObservationConfig')
        self.config, self.parameters, self.ttl_ms = config, parameters, ttl_ms
        self.render_mode = None
        self.backend = ExecutorSimulation(replace(config, control_steps=1,
            max_steps=config.max_steps*config.control_steps+min(self.observation_config.telemetry_delay_steps, 20)), parameters=parameters)
        limit = min(config.max_acceleration_m_s2, max(parameters.amax_s, parameters.amax_b))
        # The physical SDK ceiling is a Python float. Float32 Box endpoints can
        # round outward (e.g. .3 -> .3000000119) and fail SDK action validation.
        self.action_space = spaces.Box(-limit, limit, shape=(1,), dtype=np.float64)
        self.observation_space = spaces.Dict({
            'state': spaces.Box(-np.inf, np.inf, shape=(7,), dtype=np.float64),
            'valid': spaces.MultiBinary(7),
            'age_s': spaces.Box(-1., np.inf, shape=(7,), dtype=np.float64),
        })
        self._initialized = False

    @property
    def ground_truth(self): return self.backend.ground_truth

    @property
    def diagnostics(self): return self.backend.diagnostics

    @property
    def session(self): return self.backend.session

    def _measure_angle(self):
        c = self.observation_config
        angle = self.ground_truth.theta + self.np_random.normal(0., c.angle_noise_std)
        quantum = 2*math.pi/c.encoder_counts
        return wrap(round(angle/quantum)*quantum)

    def _samples(self, timestamp, *, valid=True):
        angle = self._raw_angle if self.observation_config.angle_source == 'raw' else self._angle_hat
        rows = (
            ('cart', 'position', self._step_position*self.step_m, 'm', 'step_count'),
            ('cart', 'velocity', float(self.backend.motion.velocity), 'm/s', 'commanded_velocity'),
            ('pole', 'angle', angle, 'rad', 'magnetic_decoded' if self.observation_config.angle_source == 'raw' else 'filtered_magnetic_angle'),
            ('pole', 'angular_velocity', self._rate_hat, 'rad/s', 'filtered_magnetic_rate'),
            ('cart', 'acceleration', float(self.backend.motion.acceleration), 'm/s^2', 'commanded_acceleration'),
            ('cart', 'brake_direction', self.backend.motion.brake_direction, '1', 'governor_brake_direction'),
        )
        return tuple(Sample(entity, quantity, 'simulation', float(value) if valid else None,
            unit, self.frame_id, method, 'valid' if valid else 'invalid',
            None if valid else 'simulated telemetry dropout',
            'measured' if method == 'magnetic_decoded' else 'estimated', timestamp, timestamp, None)
            for entity, quantity, value, unit, method in rows)

    def _publish(self, *, initial=False):
        now = self.ground_truth.time_ns
        valid = initial or self.np_random.random() >= self.observation_config.dropout_probability
        self._snapshots.append((now+self.observation_config.telemetry_delay_steps*1_000_000,
                                now, self._samples(now, valid=valid)))

    def _deliver(self):
        now = self.ground_truth.time_ns
        while self._snapshots and self._snapshots[0][0] <= now:
            receipt, self._observed_ns, samples = self._snapshots.popleft()
            # Rig._observation reports board snapshot proxies for all three
            # timestamps, not host receipt or physical transport latency.
            self._delivered = tuple(replace(s, received_ns=self._observed_ns) for s in samples)
        snapshot_time = 0 if self._observed_ns is None else self._observed_ns
        self.sdk_observation = Observation(self.session.session_id, self.session.clock_id,
            snapshot_time//1_000_000, snapshot_time, 'board acquisition snapshot proxy', self._delivered)

    def _observation(self):
        encoded = encode_rig_observation(self.sdk_observation, simulation_channels())
        return {key: np.array(value, dtype=np.int8 if key == 'valid' else np.float64)
                for key, value in encoded.items()}

    def _info(self):
        return dict(ground_truth=asdict(self.ground_truth), diagnostics=asdict(self.diagnostics),
                    fault_reason=self.fault_reason, observation_sequence=self.sdk_observation.sequence,
                    available_ns=self.sdk_observation.available_ns,
                    physical_time_ns=self.ground_truth.time_ns,
                    telemetry_transport_age_ns=None if self._observed_ns is None else self.ground_truth.time_ns-self._observed_ns,
                    reset_warmup_ns=self._reset_warmup_ns,
                    action_ignored_reason=self._action_ignored_reason, action_semantics=self.action_semantics)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options is not None and not isinstance(options, dict):
            raise ValidationError('options must be a dictionary')
        state = None if options is None else options.get('state')
        self.backend.reset(seed=int(self.np_random.integers(0, 2**63-1)), state=state)
        self._step_position = round(self.ground_truth.x/self.step_m)
        self._step_fraction = 0.
        self._raw_angle = self._measure_angle()
        self._angle_hat, self._rate_hat = self._raw_angle, 0.
        self._snapshots, self._commands = deque(), deque()
        self._observed_ns = None
        self._delivered = tuple(replace(s, value=None, validity='unknown', reason='telemetry delay warmup',
            acquired_ns=None, effective_ns=None, received_ns=None) for s in self._samples(0))
        self._intervals = self._sequence = 0
        self._arm_lease_installed = False
        self.terminated = self.truncated = False
        self.fault_reason = None
        self._action_ignored_reason = None
        self._reset_warmup_ns = 0
        self._initialized = True
        self._publish(initial=True)
        self._deliver()
        # Run actual causal sensor/plant ticks; never invent a sensor history.
        # At 3 ms delay the first decision is t=3, then t=13, 23, ... as a
        # telemetry-paced host. An impossible >=20 ms startup expires on step.
        for _ in range(min(self.observation_config.telemetry_delay_steps, 20)):
            request = None
            if not self._arm_lease_installed:
                request = self._request(0., min(20_000_000, self.backend.action_limits.max_ttl_ns))
                self._arm_lease_installed = True
            self._tick(request)
            if self.terminated: break
        self._reset_warmup_ns = self.ground_truth.time_ns
        return self._observation(), self._info()

    def _action(self, action):
        if action is None: return None
        array = np.asarray(action)
        if array.shape != (1,) or array.dtype.kind not in 'fiu' or not np.all(np.isfinite(array)):
            raise ValidationError('action must contain one finite real acceleration')
        acceleration = float(array[0])
        if abs(acceleration) > float(self.action_space.high[0]):
            raise ValidationError('action exceeds acceleration limit')
        if self._observed_ns is None or any(s.validity != 'valid' for s in self._delivered):
            self._action_ignored_reason = 'unusable telemetry'
            return None
        return acceleration

    def _request(self, acceleration, expires):
        o = self.backend.observation
        self._sequence += 1
        return ActionRequest(o.session_id, o.clock_id, self._sequence, o.sequence,
                             o.available_ns, expires, acceleration)

    def step(self, action):
        if not self._initialized: raise RuntimeError('reset before stepping')
        if self.terminated or self.truncated: raise RuntimeError('episode ended; reset before stepping')
        self._action_ignored_reason = None
        acceleration = self._action(action)  # Reject malformed actions before state changes.
        now = self.ground_truth.time_ns
        if acceleration is not None:
            self._commands.append((now+self.observation_config.command_delay_steps*1_000_000,
                self._observed_ns, self._observed_ns+self.ttl_ms*1_000_000, acceleration))
        for _ in range(10):
            now = self.ground_truth.time_ns
            request = None
            while self._commands and self._commands[0][0] <= now:
                _, observed, expires, value = self._commands.popleft()
                if now-observed > 20_000_000 or now >= expires:
                    self.terminated, self.fault_reason = True, 'stale action at executor arrival'
                    break
                request = self._request(value, expires)
            if self.terminated: break
            if not self._arm_lease_installed:
                if request is None: request = self._request(0., min(20_000_000, self.backend.action_limits.max_ttl_ns))
                self._arm_lease_installed = True
            self._tick(request)
            if self.terminated: break
        self._intervals += 1
        self.truncated = self._intervals >= self.config.max_steps
        self._deliver()
        truth = self.ground_truth
        demand = self.diagnostics.raw_acceleration_m_s2
        reward = math.cos(truth.theta)-(truth.x/self.config.rail_half_m)**2-.001*demand*demand
        return self._observation(), float(reward), self.terminated, self.truncated, self._info()

    def _tick(self, request):
        self.backend.step(request)
        self.terminated, self.fault_reason = self.backend.terminated, self.backend.fault_reason
        if self.terminated: return
        velocity = float(self.backend.motion.velocity)
        self._step_fraction += abs(velocity)*.001/self.step_m
        pulses = int(self._step_fraction)
        self._step_fraction -= pulses
        self._step_position += pulses*(1 if velocity >= 0 else -1)
        self._raw_angle = self._measure_angle()
        self._angle_hat, self._rate_hat = estimate(self._raw_angle, self._angle_hat,
                                                   self._rate_hat, self.parameters.bw)
        if self.diagnostics.force_saturated:
            self.terminated, self.fault_reason = True, 'force saturation: tracking model unsupported'
        if self.ground_truth.time_ns % 10_000_000 == 0: self._publish()
        self._deliver()

    def close(self): self.backend.close()
