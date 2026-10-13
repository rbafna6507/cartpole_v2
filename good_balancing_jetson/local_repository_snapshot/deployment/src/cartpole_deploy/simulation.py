"""MuJoCo rig with explicit time, finite drive tracking and latched leases."""
from dataclasses import dataclass
import math
import secrets

import mujoco
import numpy as np

from .config import RigConfig
from .model import build_model
from .types import Observation


def _clamp(value, lo, hi):
    return min(hi, max(lo, value))


def _slew(current, target, delta):
    return current + _clamp(target - current, -delta, delta)


def velocity_accel(velocity, target, amax, jerk, dt):
    error = target - velocity
    jd = jerk * dt
    acceleration = min(amax, math.sqrt(jd * jd + 2 * jerk * abs(error)) - jd)
    return acceleration if error >= 0 else -acceleration


def settled_velocity_accel(velocity, acceleration, target, amax, jerk, dt):
    error = target - velocity
    remaining = acceleration * acceleration / (2 * jerk) + abs(acceleration) * dt
    if acceleration * error > 0 and abs(error) <= remaining:
        return 0.0
    return velocity_accel(velocity, target, amax, jerk, dt)


def stopping_distance(velocity, acceleration, amax, jerk):
    """Source-derived jerk stop, ending with both velocity and acceleration zero."""
    v = max(0.0, velocity)
    a = _clamp(acceleration, -amax, amax)
    if a < 0 and v < a * a / (2 * jerk):
        t = 2 * v / (-a + math.sqrt(max(0.0, a * a - 2 * jerk * v)))
        return max(0.0, v * t + 0.5 * a * t * t + jerk * t**3 / 6)
    peak = min(amax, math.sqrt(jerk * v + 0.5 * a * a))
    t1 = max(0.0, (a + peak) / jerk)
    v1 = v + a * t1 - 0.5 * jerk * t1 * t1
    hold = max(0.0, (v1 - peak * peak / (2 * jerk)) / peak) if peak > 0 else 0.0
    d1 = v * t1 + 0.5 * a * t1 * t1 - jerk * t1**3 / 6
    d2 = v1 * hold - 0.5 * peak * hold * hold
    v2, t3 = v1 - peak * hold, peak / jerk
    return max(0.0, d1 + d2 + v2 * t3 - 0.5 * peak * t3**2 + jerk * t3**3 / 6)


@dataclass(frozen=True)
class MotionState:
    velocity: float = 0.0
    acceleration: float = 0.0
    brake_direction: int = 0


def advance_governor(state, x, requested_accel, vmax, drive_amax, brake_amax, jerk, rail_half, dt):
    """Float64 port of the working cart_motion.h governor, in SI units."""
    velocity, acceleration, brake = state.velocity, state.acceleration, state.brake_direction
    boundary, jd = rail_half - 0.015, jerk * dt
    target = _clamp(requested_accel, -drive_amax, drive_amax)
    positive = settled_velocity_accel(velocity, acceleration, vmax, brake_amax, jerk, dt)
    negative = settled_velocity_accel(velocity, acceleration, -vmax, brake_amax, jerk, dt)
    target = _clamp(target, negative, positive)
    next_a = _slew(acceleration, target, jd)
    next_v = velocity + next_a * dt
    if brake and abs(velocity) <= 0.005 and abs(acceleration) <= 0.1:
        brake = 0
    if not brake:
        for direction in (-1, 1):
            outward_v, outward_a = next_v * direction, next_a * direction
            room = boundary - direction * x
            if room <= 0 and outward_v <= 0.005 and outward_a < 0:
                continue
            travel = max(0.0, outward_v) * dt
            if (outward_v > 0 or outward_a > 0) and travel + stopping_distance(outward_v, outward_a, brake_amax, jerk) >= room:
                brake = direction
                break
    if brake:
        target = settled_velocity_accel(velocity, acceleration, 0, brake_amax, jerk, dt)
    candidate_a = _slew(acceleration, target, jd)
    candidate_v = velocity + candidate_a * dt
    if candidate_a > 0 and candidate_v + candidate_a**2 / (2 * jerk) >= vmax:
        target = min(target, 0.0)
    if candidate_a < 0 and candidate_v - candidate_a**2 / (2 * jerk) <= -vmax:
        target = max(target, 0.0)
    acceleration = _slew(acceleration, target, jd)
    return MotionState(velocity + acceleration * dt, acceleration, brake)


class SimRig:
    """SDK-compatible rig. Only advance() integrates physics or lease time.

    Commands drive the source governor's desired velocity through a bounded
    force servo. Its time constant, force limit and cart mass are assumptions,
    not measurements of motor tracking. Disabled means zero drive force.
    """

    def __init__(self, config: RigConfig | None = None):
        self.config = config or RigConfig()
        # Copy validation also protects against callers mutating a config after init.
        self.config = RigConfig(**self.config.to_dict())
        self.model = build_model(self.config)
        self.data = mujoco.MjData(self.model)
        self._rng = np.random.default_rng(self.config.seed)
        self._closed = False
        self._clamped = False
        self._last_session = 0
        self.reset()

    def reset(self, theta_rad=math.pi, omega_rad_s=0, x_m=0, v_m_s=0) -> Observation:
        self._ensure_open()
        values = (theta_rad, omega_rad_s, x_m, v_m_s)
        if any(isinstance(v, bool) or not isinstance(v, (int, float, np.number)) or not math.isfinite(v) for v in values):
            raise ValueError("reset state must be finite")
        if abs(x_m) > self.config.rail_half_m:
            raise ValueError("reset cart lies outside physical rail")
        if self._clamped and v_m_s != 0:
            raise ValueError("clamped cart reset requires zero velocity")
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:] = (x_m, theta_rad)
        self.data.qvel[:] = (v_m_s, omega_rad_s)
        self._ticks = 0
        # Reset creates a new simulated time epoch. stop()/clear_fault() retain
        # the previous-session guard inside an epoch, just as hardware does.
        self._last_session = 0
        self._mode, self._fault = "DISARMED", "none"
        self._homed, self._session, self._sequence = False, 0, 0
        self._deadline_s = None
        self._half = self.config.rail_half_m
        self._kind, self._value = "acceleration", 0.0
        self._governor = MotionState()
        self.model.jnt_range[0] = (-self._half, self._half)
        self.model.eq_data[0, 0] = x_m
        self.data.eq_active[0] = self._clamped
        mujoco.mj_forward(self.model, self.data)
        self._sample_sensor(initial=True)
        return self.read()

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("rig is closed")

    def _state_is_finite(self):
        return (np.isfinite(self.data.qpos).all() and np.isfinite(self.data.qvel).all()
                and np.isfinite(self.data.qacc).all())

    @property
    def _time_s(self):
        return self._ticks * self.config.control_dt_s

    def _sample_sensor(self, initial=False):
        noisy_angle = float(self.data.qpos[1]) + self._rng.normal(0, self.config.sensor_noise_rad)
        count = int(math.floor(noisy_angle * self.config.encoder_counts / (2 * math.pi) + 0.5))
        self._raw = (self.config.encoder_upright_raw + count) % self.config.encoder_counts
        relative = (self._raw - self.config.encoder_upright_raw) % self.config.encoder_counts
        self._theta = ((relative * 2 * math.pi / self.config.encoder_counts + math.pi) % (2 * math.pi)) - math.pi
        if initial:
            self._omega = 0.0
        else:
            delta = (self._theta - self._previous_theta + math.pi) % (2 * math.pi) - math.pi
            measured = delta / self.config.control_dt_s
            # Same 30 Hz first-order estimator used by the trusted executor;
            # true angular velocity remains available only in true_state().
            gain = self.config.control_dt_s / (0.005305165 + self.config.control_dt_s)
            self._omega += gain * (measured - self._omega)
        self._previous_theta = self._theta

    def read(self) -> Observation:
        valid = self._state_is_finite()
        enabled = self._mode in ("ARMED", "RUNNING")
        flags = int(valid) | (2 if self._homed else 0) | (4 if enabled else 0)
        return Observation(
            time_us=round(self._time_s * 1e6) & 0xFFFFFFFF, mode=self._mode,
            theta_rad=self._theta, omega_rad_s=self._omega,
            x_m=float(self.data.qpos[0]), v_m_s=float(self.data.qvel[0]), a_m_s2=float(self.data.qacc[0]),
            encoder_raw=self._raw, flags=flags, sequence=self._sequence, session=self._session,
            fault=self._fault, position_source="simulated_true")

    def true_state(self) -> dict:
        """Ground truth and drive intent; these do not replace encoder samples."""
        return {"time_s": self._time_s, "theta_rad": float(self.data.qpos[1]),
                "omega_rad_s": float(self.data.qvel[1]), "x_m": float(self.data.qpos[0]),
                "v_m_s": float(self.data.qvel[0]), "a_m_s2": float(self.data.qacc[0]),
                "commanded_v_m_s": self._governor.velocity,
                "commanded_a_m_s2": self._governor.acceleration,
                "brake_direction": self._governor.brake_direction,
                "actuator_force_n": float(self.data.ctrl[0]), "cart_clamped": self._clamped}

    def capabilities(self) -> dict:
        return {"backend": "mujoco", "cart": True, "encoder": True, "imu": False,
                "z": False, "ground_truth": True, "cart_clamp_fixture": True,
                "position_source": "simulated_true"}

    def home(self, rail_half_m=0.15):
        self._ensure_open()
        if self._mode != "DISARMED":
            raise RuntimeError("home assertion requires disarmed rig")
        if isinstance(rail_half_m, bool) or not isinstance(rail_half_m, (int, float, np.number)) or not math.isfinite(rail_half_m) or not 0.03 <= rail_half_m <= self.config.rail_half_m:
            raise ValueError("half-span must be 0.03 m through configured owner limit")
        self._half, self._homed = float(rail_half_m), True
        self.model.jnt_range[0] = (-self._half, self._half)

    def arm(self, session=None):
        self._ensure_open()
        if self._mode != "DISARMED" or not self._homed or not self.read().encoder_valid:
            raise RuntimeError("arm requires disarmed, homed rig and valid encoder")
        if self._clamped:
            raise RuntimeError("release cart clamp fixture before arming")
        if session is None:
            session = secrets.randbelow(0xFFFFFFFF) + 1
            while session == self._last_session:
                session = secrets.randbelow(0xFFFFFFFF) + 1
        if isinstance(session, bool) or not isinstance(session, int) or not 0 < session <= 0xFFFFFFFF or session == self._last_session:
            raise ValueError("session must be fresh nonzero uint32")
        self._session, self._last_session, self._sequence = session, session, 0
        self._mode, self._deadline_s = "ARMED", self._time_s + 0.1
        self._governor = MotionState()

    def command(self, kind, value, ttl_ms=50):
        self._ensure_open()
        if self._mode not in ("ARMED", "RUNNING"):
            raise RuntimeError("command requires an explicitly armed rig")
        if not self._state_is_finite():
            self._latch_fault("nonfinite_state")
            raise RuntimeError("command requires valid simulator state")
        limits = {"acceleration": self.config.max_acceleration_m_s2,
                  "velocity": self.config.max_velocity_m_s,
                  "position": self._half - 0.015}
        invalid = not isinstance(kind, str) or kind not in limits
        invalid |= isinstance(value, bool) or not isinstance(value, (int, float, np.number)) or not math.isfinite(value)
        invalid |= isinstance(ttl_ms, bool) or not isinstance(ttl_ms, int) or not 10 <= ttl_ms <= 100
        if not invalid:
            invalid = abs(value) > limits[kind]
        if invalid:
            self._latch_fault("invalid_action")
            raise ValueError("invalid kind, nonfinite/out-of-bounds target or TTL")
        if self._sequence == 0xFFFFFFFF:
            self._latch_fault("sequence")
            raise RuntimeError("session sequence exhausted")
        # read() samples no new time: this current sensor timestamp anchors TTL.
        self.read()
        self._sequence += 1
        self._kind, self._value = kind, float(value)
        self._deadline_s = self._time_s + ttl_ms / 1000
        self._mode = "RUNNING"

    def _latch_fault(self, reason):
        self._mode, self._fault = "FAULT", reason
        self._homed, self._session, self._deadline_s = False, 0, None
        self._governor = MotionState()
        self.data.ctrl[0] = 0

    def _check_deadline(self):
        if self._deadline_s is not None and self._time_s >= self._deadline_s - 1e-12:
            self._latch_fault("deadline")

    def _requested_acceleration(self):
        c, s = self.config, self._governor
        if self._kind == "acceleration":
            return self._value
        if self._kind == "velocity":
            target_v = self._value
        else:
            # Same proportional position approach as the trusted executor;
            # final jerk/rail handling remains in the source motion governor.
            error = self._value - float(self.data.qpos[0])
            target_v = _clamp(4 * error, -c.max_velocity_m_s, c.max_velocity_m_s)
        return settled_velocity_accel(s.velocity, s.acceleration, target_v,
                                      c.max_acceleration_m_s2, c.max_jerk_m_s3, c.control_dt_s)

    def advance(self, seconds) -> Observation:
        self._ensure_open()
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float, np.number)) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("advance duration must be finite and nonnegative")
        steps = seconds / self.config.control_dt_s
        if not math.isclose(steps, round(steps), abs_tol=1e-8, rel_tol=0):
            raise ValueError("advance duration must be an integer number of control ticks")
        c = self.config
        for _ in range(round(steps)):
            if not self._state_is_finite():
                self._latch_fault("nonfinite_state")
                raise RuntimeError("MuJoCo state is nonfinite")
            self._check_deadline()
            if self._mode in ("ARMED", "RUNNING"):
                requested = self._requested_acceleration() if self._mode == "RUNNING" else 0.0
                self._governor = advance_governor(self._governor, float(self.data.qpos[0]), requested,
                    c.max_velocity_m_s, c.max_acceleration_m_s2, c.max_acceleration_m_s2,
                    c.max_jerk_m_s3, self._half, c.control_dt_s)
                # A first-order velocity tracking time constant converts error
                # to force; MuJoCo handles the coupled cart/pole acceleration.
                force = (c.cart_mass_kg + c.total_pendulum_mass_kg) * (self._governor.velocity - self.data.qvel[0]) / c.actuator_time_constant_s
                self.data.ctrl[0] = _clamp(force, -c.actuator_force_limit_n, c.actuator_force_limit_n)
            else:
                self.data.ctrl[0] = 0
            unstable_warnings = (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL,
                                 mujoco.mjtWarning.mjWARN_BADQACC, mujoco.mjtWarning.mjWARN_BADCTRL)
            warning_counts = [self.data.warning[int(w)].number for w in unstable_warnings]
            mujoco.mj_step(self.model, self.data)
            self._ticks += 1
            if any(self.data.warning[int(w)].number > previous for w, previous in zip(unstable_warnings, warning_counts)):
                self._latch_fault("simulation_unstable")
                raise RuntimeError("MuJoCo reported unstable state; fault is latched")
            if not self._state_is_finite():
                self._latch_fault("nonfinite_state")
                raise RuntimeError("MuJoCo produced nonfinite state")
            if self._mode in ("ARMED", "RUNNING") and abs(self.data.qpos[0]) >= self._half - 0.010:
                self._latch_fault("rail")
            self._check_deadline()
            self._sample_sensor()
        return self.read()

    def stop(self):
        self.data.ctrl[0] = 0
        self._homed, self._session, self._deadline_s = False, 0, None
        self._governor = MotionState()
        if self._mode != "FAULT":
            self._mode, self._fault = "DISARMED", "none"

    def clear_fault(self):
        self._ensure_open()
        if self._mode in ("ARMED", "RUNNING"):
            raise RuntimeError("cannot clear an active rig")
        self.stop()
        self._mode, self._fault = "DISARMED", "none"

    def set_cart_clamped(self, clamped: bool):
        """Enable a mechanical fixture constraint, distinct from disabling drive."""
        self._ensure_open()
        if self._mode in ("ARMED", "RUNNING"):
            raise RuntimeError("fixture changes require disabled rig")
        if not isinstance(clamped, bool):
            raise ValueError("clamped must be bool")
        self._clamped = clamped
        self.model.eq_data[0, 0] = float(self.data.qpos[0])
        self.data.eq_active[0] = clamped
        mujoco.mj_forward(self.model, self.data)

    def close(self):
        self.stop()
        self._closed = True

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, *_):
        self.close()
