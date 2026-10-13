"""Starter Gymnasium adapter, not a trained or validated balance benchmark."""
import math

import gymnasium as gym
import numpy as np

from .config import RigConfig
from .simulation import SimRig


class CartPoleEnv(gym.Env):
    """Actions are cart acceleration in m/s²; observations are [x,v,theta,omega].

    Reset starts near upright and explicitly homes/arms the simulator. Each
    step submits a fresh action then advances one policy interval. A fault,
    departure beyond 12 degrees or the rail threshold terminates the episode.
    Reward cos(theta) is illustrative scaffolding for a future training task.
    """

    metadata = {"render_modes": []}

    def __init__(self, config: RigConfig | None = None, max_episode_steps=1000):
        super().__init__()
        self.config = config or RigConfig()
        if not isinstance(max_episode_steps, int) or max_episode_steps <= 0:
            raise ValueError("max_episode_steps must be a positive integer")
        if self.config.policy_dt_s >= 0.1:
            raise ValueError("policy interval must be below the 100 ms command lease")
        self.rig = SimRig(self.config)
        self.max_episode_steps = max_episode_steps
        self.action_space = gym.spaces.Box(-self.config.max_acceleration_m_s2, self.config.max_acceleration_m_s2, (1,), dtype=np.float32)
        self.observation_space = gym.spaces.Box(
            np.array([-np.inf, -np.inf, -math.pi, -np.inf], dtype=np.float64),
            np.array([np.inf, np.inf, math.pi, np.inf], dtype=np.float64), dtype=np.float64)
        self._steps, self._done = 0, True

    def _observation(self):
        obs = self.rig.read()
        return np.array([obs.x_m, obs.v_m_s, obs.theta_rad, obs.omega_rad_s], dtype=np.float64), {
            "observation": obs.to_dict(), "true_state": self.rig.true_state(),
            "position_source": obs.position_source, "model_status": "provisional"}

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        options = dict(options or {})
        unknown = set(options) - {"theta_rad", "omega_rad_s", "x_m", "v_m_s"}
        if unknown:
            raise ValueError(f"unknown reset options: {sorted(unknown)}")
        if seed is not None:
            self.rig._rng = np.random.default_rng(seed)
        options.setdefault("theta_rad", float(self.np_random.uniform(-0.02, 0.02)))
        self.rig.reset(**options)
        self.rig.home(self.config.rail_half_m)
        # Full simulation reset starts a new epoch; constant session metadata
        # makes seeded episodes deterministic, including Gym's info mapping.
        self.rig.arm(session=1)
        self._steps, self._done = 0, False
        return self._observation()

    def step(self, action):
        if self._done:
            raise RuntimeError("reset is required before stepping a finished episode")
        try:
            action = np.asarray(action, dtype=np.float64)
        except (TypeError, ValueError, OverflowError) as error:
            self.rig.stop()
            self._done = True
            raise ValueError("action must be one finite acceleration within configured limits") from error
        if action.shape != (1,) or not np.isfinite(action).all() or abs(action[0]) > self.config.max_acceleration_m_s2:
            self.rig.stop()
            self._done = True
            raise ValueError("action must be one finite acceleration within configured limits")
        ttl_ms = min(100, max(10, math.ceil(self.config.policy_dt_s * 1000) + 1))
        self.rig.command("acceleration", float(action[0]), ttl_ms=ttl_ms)
        self.rig.advance(self.config.policy_dt_s)
        self._steps += 1
        observation, info = self._observation()
        raw = info["observation"]
        terminated = (raw["mode"] == "FAULT" or abs(raw["theta_rad"]) > math.radians(12)
                      or abs(raw["x_m"]) >= self.config.rail_half_m - 0.010)
        truncated = self._steps >= self.max_episode_steps and not terminated
        reward = float(math.cos(raw["theta_rad"]))
        self._done = bool(terminated or truncated)
        if self._done:
            self.rig.stop()
        return observation, reward, bool(terminated), bool(truncated), info

    def close(self):
        self.rig.close()
