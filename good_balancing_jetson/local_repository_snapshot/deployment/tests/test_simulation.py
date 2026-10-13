"""Headless, physical and lifecycle checks for the deployment simulator."""
import importlib
import math
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest


def make_rig(**overrides):
    config = importlib.import_module("cartpole_deploy.config").RigConfig(**overrides)
    cls = importlib.import_module("cartpole_deploy.simulation").SimRig
    return cls(config)


def activate(rig, session=1):
    rig.home()
    rig.arm(session=session)


def test_model_gravity_matches_upright_angle_sign():
    import mujoco

    rig = make_rig()
    rig.set_cart_clamped(True)
    rig.reset(theta_rad=0.05)
    mujoco.mj_forward(rig.model, rig.data)
    assert rig.data.qacc[1] > 0  # positive top displacement falls towards +x
    rig.reset(theta_rad=math.pi + 0.05)
    mujoco.mj_forward(rig.model, rig.data)
    assert rig.data.qacc[1] < 0  # hanging equilibrium restores the perturbation
    assert rig.model.body_mass[2] == pytest.approx(0.02275)
    assert rig.model.body_ipos[2, 2] == pytest.approx(0.09464285714285714)


def test_clamped_small_angle_free_period_uses_historical_effective_length():
    rig = make_rig(damping_per_s=0)
    rig.set_cart_clamped(True)
    rig.reset(theta_rad=math.pi + 0.02)
    times, angles, carts = [], [], []
    for _ in range(2000):
        rig.advance(0.001)
        state = rig.true_state()
        times.append(state["time_s"])
        angles.append(state["theta_rad"] - math.pi)
        carts.append(state["x_m"])
    crossing_indices = np.flatnonzero((np.asarray(angles[:-1]) < 0) & (np.asarray(angles[1:]) >= 0))
    periods = np.diff(np.asarray(times)[crossing_indices])
    assert periods.size >= 1
    assert np.mean(periods) == pytest.approx(0.707686, abs=0.004)
    assert max(abs(x) for x in carts) < 2e-6


def test_clamped_free_decay_has_historical_damping_envelope():
    rig = make_rig()
    rig.set_cart_clamped(True)
    rig.reset(theta_rad=math.pi + 0.03)
    peaks = []
    previous_velocity = 0.0
    for _ in range(2500):
        rig.advance(0.001)
        state = rig.true_state()
        if previous_velocity > 0 and state["omega_rad_s"] <= 0:
            peaks.append((state["time_s"], abs(state["theta_rad"] - math.pi)))
        previous_velocity = state["omega_rad_s"]
    assert len(peaks) >= 3
    first, last = peaks[0], peaks[-1]
    damping = -2 * math.log(last[1] / first[1]) / (last[0] - first[0])
    assert damping == pytest.approx(0.913383, abs=0.01)


def test_disable_is_free_cart_while_fixture_clamp_is_explicit():
    rig = make_rig()
    rig.reset(theta_rad=math.pi + 0.3)
    rig.advance(0.1)
    assert abs(rig.true_state()["x_m"]) > 1e-4
    rig.set_cart_clamped(True)
    rig.reset(theta_rad=math.pi + 0.3)
    rig.advance(0.1)
    assert abs(rig.true_state()["x_m"]) < 2e-6


def test_reset_true_state_and_encoder_observation_are_separate():
    rig = make_rig()
    obs = rig.reset(theta_rad=0.123, omega_rad_s=0.4, x_m=0.02, v_m_s=-0.1)
    state = rig.true_state()
    assert state["theta_rad"] == pytest.approx(0.123)
    assert state["omega_rad_s"] == pytest.approx(0.4)
    assert state["x_m"] == pytest.approx(0.02)
    assert obs.encoder_raw == 80
    assert obs.theta_rad == pytest.approx(80 * 2 * math.pi / 4096)
    assert obs.position_source == "simulated_true"
    assert obs.mode == "DISARMED"
    assert obs.encoder_valid and not obs.homed and not obs.enabled


def test_read_is_same_sample_without_advancing_time_or_noise():
    rig = make_rig(sensor_noise_rad=0.05, seed=42)
    first = rig.read()
    for _ in range(5):
        assert rig.read().to_dict() == first.to_dict()
    assert rig.true_state()["time_s"] == 0
    rig.advance(0.005)
    assert rig.read().time_us == 5000


def test_sensor_noise_is_reproducible_and_does_not_change_true_physics():
    clean, noisy_a, noisy_b = make_rig(), make_rig(sensor_noise_rad=0.05, seed=8), make_rig(sensor_noise_rad=0.05, seed=8)
    assert noisy_a.read().encoder_raw == noisy_b.read().encoder_raw
    assert noisy_a.read().encoder_raw != clean.read().encoder_raw
    for rig in (clean, noisy_a, noisy_b):
        rig.reset(theta_rad=math.pi + 0.2)
        rig.advance(0.03)
    assert clean.true_state()["theta_rad"] == pytest.approx(noisy_a.true_state()["theta_rad"])
    assert noisy_a.read().to_dict() == noisy_b.read().to_dict()


def test_home_and_arm_require_explicit_disarmed_lifecycle():
    rig = make_rig()
    with pytest.raises(RuntimeError):
        rig.arm(session=1)
    rig.home()
    assert rig.read().homed and not rig.read().enabled
    rig.arm(session=1)
    assert rig.read().mode == "ARMED" and rig.read().enabled
    with pytest.raises(RuntimeError):
        rig.home()
    rig.stop()
    assert rig.read().mode == "DISARMED" and not rig.read().homed
    rig.home()
    with pytest.raises((ValueError, RuntimeError)):
        rig.arm(session=1)
    rig.arm(session=2)
    rig.close()
    assert not rig.read().enabled


@pytest.mark.parametrize("half", [0, 0.02, 0.151, math.nan])
def test_home_rejects_invalid_or_widened_rail(half):
    rig = make_rig()
    with pytest.raises(ValueError):
        rig.home(half)
    assert not rig.read().homed


def test_action_expiry_without_client_calls_latches_fault():
    rig = make_rig()
    activate(rig)
    rig.command("acceleration", 1.0, ttl_ms=10)
    assert rig.read().mode == "RUNNING"
    rig.advance(0.011)
    obs = rig.read()
    assert obs.mode == "FAULT" and not obs.enabled and not obs.homed
    assert obs.fault == "deadline"
    assert rig.true_state()["actuator_force_n"] == 0
    with pytest.raises(RuntimeError):
        rig.command("acceleration", 0)
    rig.advance(0.02)
    assert rig.read().mode == "FAULT"
    rig.clear_fault()
    assert rig.read().mode == "DISARMED" and not rig.read().homed
    with pytest.raises(RuntimeError):
        rig.arm(session=2)
    activate(rig, session=2)
    assert rig.read().mode == "ARMED"


def test_first_action_arm_lease_expires_even_when_reading():
    rig = make_rig()
    activate(rig)
    for _ in range(11):
        rig.read()
        rig.advance(0.01)
    assert rig.read().mode == "FAULT"
    assert rig.read().fault == "deadline"


@pytest.mark.parametrize("kind,value,ttl", [("acceleration", 2.01, 50), ("velocity", -0.251, 50), ("position", 0.136, 50), ("acceleration", math.nan, 50), ("unsupported", 0, 50), ("velocity", 0, 9), ("velocity", 0, 101)])
def test_invalid_active_action_disables_and_latches(kind, value, ttl):
    rig = make_rig()
    activate(rig)
    with pytest.raises(ValueError):
        rig.command(kind, value, ttl_ms=ttl)
    assert rig.read().mode == "FAULT" and not rig.read().enabled


def test_jerk_speed_and_rail_governor_and_finite_actuator():
    rig = make_rig()
    activate(rig)
    velocities, accelerations, positions, forces = [], [], [], []
    for _ in range(3000):
        rig.command("acceleration", 2, ttl_ms=50)
        rig.advance(0.001)
        state = rig.true_state()
        velocities.append(state["commanded_v_m_s"])
        accelerations.append(state["commanded_a_m_s2"])
        positions.append(state["x_m"])
        forces.append(state["actuator_force_n"])
        if rig.read().mode == "FAULT":
            break
    assert max(abs(a) for a in accelerations) <= 2 + 1e-9
    assert max(abs(v) for v in velocities) <= 0.2501
    assert max(abs(a) for a in np.diff([0] + accelerations)) <= 0.020001
    assert max(positions) < 0.145
    assert max(abs(f) for f in forces) <= 5
    assert rig.read().mode != "FAULT"
    assert rig.true_state()["v_m_s"] < 0.01


def test_positive_cart_acceleration_drives_upright_angle_negative():
    rig = make_rig()
    rig.reset(theta_rad=0)
    activate(rig)
    rig.command("acceleration", 1, ttl_ms=100)
    rig.advance(0.04)
    assert rig.true_state()["x_m"] > 0
    assert rig.true_state()["theta_rad"] < 0
    assert rig.true_state()["v_m_s"] < rig.true_state()["commanded_v_m_s"]


def test_force_saturation_and_velocity_position_targets_use_physical_cart():
    saturated = make_rig(actuator_force_limit_n=0.01)
    activate(saturated)
    saturated.command("acceleration", 2, ttl_ms=100)
    forces = []
    for _ in range(90):
        saturated.advance(0.001)
        forces.append(saturated.true_state()["actuator_force_n"])
    assert max(forces) == pytest.approx(0.01)
    assert max(abs(f) for f in forces) <= 0.01
    velocity = make_rig()
    activate(velocity)
    for _ in range(50):
        velocity.command("velocity", 0.1)
        velocity.advance(0.01)
    assert velocity.true_state()["v_m_s"] == pytest.approx(0.1, abs=0.01)
    position = make_rig()
    activate(position)
    for _ in range(300):
        position.command("position", 0.04)
        position.advance(0.01)
    assert position.true_state()["x_m"] == pytest.approx(0.04, abs=0.001)


def test_omega_is_encoder_derived_with_source_firmware_filter():
    rig = make_rig()
    rig.set_cart_clamped(True)
    rig.reset(theta_rad=0, omega_rad_s=1)
    assert rig.read().omega_rad_s == 0
    rig.advance(0.001)
    assert rig.read().encoder_raw == 1
    assert rig.read().omega_rad_s == pytest.approx(0.243289555132283, abs=1e-8)


@pytest.mark.parametrize("seconds", [-0.01, math.nan, math.inf, 0.0005])
def test_advance_rejects_invalid_or_fractional_control_ticks(seconds):
    rig = make_rig()
    with pytest.raises(ValueError):
        rig.advance(seconds)
    assert rig.read().time_us == 0


@pytest.mark.parametrize("kwargs", [{"theta_rad": math.nan}, {"omega_rad_s": math.inf}, {"x_m": 0.2}, {"v_m_s": math.nan}])
def test_reset_rejects_nonfinite_and_outside_physical_rail(kwargs):
    rig = make_rig()
    with pytest.raises(ValueError):
        rig.reset(**kwargs)


def test_gym_reset_step_and_time_limit():
    env_cls = importlib.import_module("cartpole_deploy.gym_env").CartPoleEnv
    env = env_cls(max_episode_steps=2)
    obs, info = env.reset(seed=1, options={"theta_rad": 0.02})
    assert env.observation_space.contains(obs)
    assert info["position_source"] == "simulated_true"
    obs, reward, terminated, truncated, info = env.step(np.array([0.2], dtype=np.float32))
    assert env.observation_space.contains(obs)
    assert isinstance(reward, float) and not terminated and not truncated
    assert info["observation"]["time_us"] == 10000
    _, _, terminated, truncated, _ = env.step(np.array([0], dtype=np.float32))
    assert not terminated and truncated
    env.close()
    assert not env.rig.read().enabled


def test_gym_seeded_resets_are_deterministic_including_step_info():
    from gymnasium.utils.env_checker import check_env

    env_cls = importlib.import_module("cartpole_deploy.gym_env").CartPoleEnv
    with pytest.warns(UserWarning):  # checker advises normalized actions and finite Box bounds
        check_env(env_cls(), skip_render_check=True)


def test_gym_rejects_policy_tick_that_consumes_entire_maximum_lease():
    config_cls = importlib.import_module("cartpole_deploy.config").RigConfig
    env_cls = importlib.import_module("cartpole_deploy.gym_env").CartPoleEnv
    with pytest.raises(ValueError):
        env_cls(config_cls(policy_dt_s=0.1))


def test_nonfinite_engine_state_is_faulted_before_mujoco_can_reset_it():
    rig = make_rig()
    activate(rig)
    rig.command("acceleration", 1)
    rig.data.qvel[1] = math.nan
    with pytest.raises(RuntimeError):
        rig.advance(0.001)
    assert rig.read().mode == "FAULT" and not rig.read().enabled
    assert rig.read().fault == "nonfinite_state"
    assert rig.true_state()["actuator_force_n"] == 0


def test_nonfinite_state_rejects_new_action_and_invalid_kind_latches():
    rig = make_rig()
    activate(rig)
    rig.data.qpos[1] = math.nan
    with pytest.raises(RuntimeError):
        rig.command("acceleration", 1)
    assert rig.read().mode == "FAULT" and not rig.read().enabled
    rig.reset()
    activate(rig, session=2)
    with pytest.raises(ValueError):
        rig.command([], 1)
    assert rig.read().mode == "FAULT" and not rig.read().enabled


def test_engine_instability_warning_cannot_silently_restart():
    rig = make_rig()
    activate(rig)
    rig.data.qvel[1] = 1e12  # finite, but MuJoCo reports/reset an unstable state
    with pytest.raises(RuntimeError):
        rig.advance(0.001)
    assert rig.read().mode == "FAULT" and not rig.read().enabled
    assert rig.read().fault == "simulation_unstable"


def test_source_cart_governor_parity_for_braking_reversal_and_stopping(tmp_path):
    """Compile shipped source math; no device, pulse generation or Arduino used."""
    compiler = shutil.which("c++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("native compiler is unavailable for governor parity")
    header = Path(__file__).parents[1] / "firmware" / "deployment_executor" / "cart_motion.h"
    if not header.exists():
        pytest.skip("firmware source is unavailable for governor parity")
    source = tmp_path / "governor.cpp"
    source.write_text('''#include <iostream>
#include <iomanip>
#include "cart_motion.h"
int main() {
  std::cout << std::setprecision(9);
  for (int i=0; i<800; ++i) {
    cart_motion::State s;
    s.velocity = (i % 17 - 8) * 0.04f;
    s.acceleration = (i % 9 - 4) * 0.5f;
    s.brake_direction = i % 13 == 0 ? (i%2 ? 1 : -1) : 0;
    float x = (i%23 - 11)*0.012f, request = (i%7 - 3)*0.8f;
    auto n=cart_motion::advance(s,x,request,.25f,2.f,2.f,20.f,.15f,.001f);
    std::cout << n.velocity << " " << n.acceleration << " " << n.brake_direction
              << " " << cart_motion::stoppingDistance(s.velocity,s.acceleration,2.f,20.f) << "\\n";
  }
}''')
    executable = tmp_path / "governor"
    subprocess.run([compiler, "-std=c++11", "-I", str(header.parent), str(source), "-o", str(executable)], check=True, capture_output=True, text=True)
    rows = subprocess.run([str(executable)], check=True, capture_output=True, text=True).stdout.splitlines()
    sim = importlib.import_module("cartpole_deploy.simulation")
    for i, row in enumerate(rows):
        velocity, acceleration, brake, distance = map(float, row.split())
        state = sim.MotionState((i % 17 - 8) * 0.04, (i % 9 - 4) * 0.5, (1 if i%2 else -1) if i%13 == 0 else 0)
        actual = sim.advance_governor(state, (i%23 - 11)*0.012, (i%7 - 3)*0.8, .25, 2, 2, 20, .15, .001)
        assert actual.velocity == pytest.approx(velocity, abs=2e-7)
        assert actual.acceleration == pytest.approx(acceleration, abs=2e-6)
        assert actual.brake_direction == brake
        assert sim.stopping_distance(state.velocity, state.acceleration, 2, 20) == pytest.approx(distance, abs=2e-7)


@pytest.mark.parametrize("bad_action", [np.array([math.nan], dtype=np.float32), ["invalid"], object(), [0, 0]])
def test_gym_failure_terminates_and_invalid_action_cannot_leave_motor_enabled(bad_action):
    env_cls = importlib.import_module("cartpole_deploy.gym_env").CartPoleEnv
    env = env_cls()
    env.reset(options={"theta_rad": 0.4})
    _, _, terminated, truncated, _ = env.step(np.array([0], dtype=np.float32))
    assert terminated and not truncated and not env.rig.read().enabled
    env.reset()
    with pytest.raises(ValueError):
        env.step(bad_action)
    assert not env.rig.read().enabled
