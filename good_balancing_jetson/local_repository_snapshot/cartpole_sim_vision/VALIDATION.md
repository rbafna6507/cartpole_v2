# Validation

- Three automated tests passed: locked-cart MuJoCo period vs analytical physical-pendulum period; deterministic reset and target-velocity bounds; synthetic color-marker homing, angle sign, ambiguity and reacquisition.
- Stable-Baselines3 environment checker and 512-step PPO smoke training completed. Saved-policy evaluation and HTML replay generation ran successfully.
- The smoke policy failed evaluation episodes: this is expected for a software check and is not evidence of learned balance.
- Python files compile. Camera, Jetson performance, physical tracking accuracy and Tailscale streaming have NOT been tested on your hardware. No hardware commands are implemented.
- Full requirements are ranges for portability; exact software versions tested below.

- mujoco: 3.14.0
- gymnasium: 1.3.0
- stable-baselines3: 2.9.0
- numpy: 2.3.5
- opencv-python-headless: 5.0.0.93
- flask: 3.1.3
- torch: 2.14.0