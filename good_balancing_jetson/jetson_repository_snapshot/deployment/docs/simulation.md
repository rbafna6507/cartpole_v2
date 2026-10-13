# MuJoCo simulation starter

`SimRig` runs the coupled cart and pendulum equations in MuJoCo. It has the
same `read/home/arm/command/stop/clear_fault/close` interface as `HardwareRig`,
and starts disarmed. The simulator never opens a device or network connection.
The initial profile is a historical prior for a 125 mm arm, **not a confirmation
of the current physical assembly**. Cart mass, COM, motor tracking and force
limits remain assumptions until independently measured.

Install the package's simulation extra, then run the headless example:

```sh
python -m pip install -e '.[sim]'
python - <<'PY'
from cartpole_deploy.simulation import SimRig

with SimRig() as rig:
    rig.reset(theta_rad=0.02)
    rig.home(rig.config.rail_half_m)   # manual center assertion, no movement
    rig.arm(session=1)
    for _ in range(20):
        rig.command('acceleration', 0.1, ttl_ms=50)
        sample = rig.advance(0.01)
        print(sample.to_dict())
PY
```

## Geometry and dynamics

Angles use radians: zero is upright, positive moves the top towards +x, and
the hanging equilibrium is pi. The pendulum rotates about the +y hinge axis.
A positive cart acceleration initially pushes an upright pendulum towards
negative theta. Gravity is 9.81 m/s² downwards. All lengths, forces and masses
are SI quantities.

The visible arm remains 0.125 m long, with a tip weight drawn at that endpoint.
The single rigid pendulum carries the combined 0.01105 + 0.0117 kg mass. Its
explicit COM is 0.09464285714285714 m, a provisional assumption associated with
the arm and tip weights. Its transverse pivot inertia is
`I = total_mass * COM * effective_length`, using the historical fitted
`effective_length = 0.124454888 m`. The parallel-axis theorem supplies the
transverse inertia about the COM. Equal positive x/y moments and a small
positive z moment satisfy the rotational inertia triangle inequalities while
retaining the fitted hinge inertia. No hidden effective-length substitution
or automatic geometry-derived mass is used. [MuJoCo's inertial reference](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-inertial)
describes these explicit properties.

Viscous hinge damping is `I * 0.913383` N m s/rad. Thus the clamped small-angle
model is `theta_ddot = (g/L_eff) sin(theta) - b*theta_dot`, with `b` in 1/s.
Optional Coulomb friction uses hinge `frictionloss = I * coulomb_rad_s2`.
The small-angle, undamped hanging period is about 0.708 s. The fit alone does
not identify COM, cart mass, motor friction or tracking.

## Motion and observation contracts

Acceleration intent first enters the source-derived jerk/speed/rail governor
from `teensy_swingup_ethernet/teensy_swingup/cart_motion.h`. Velocity intent uses
its settled-velocity approach, and position intent uses the trusted executor's
bounded `4 * position_error` velocity approach. Normal rail braking reserves
15 mm from each end; reaching the separate 10 mm fault boundary disables
drive and latches `rail`. Defaults are 0.25 m/s, 2 m/s² and 20 m/s³. The governor
bounds **commanded** velocity/acceleration/jerk. Pendulum forces and tracking
error can change actual cart acceleration and speed.

The actuator is a bounded force servo: desired velocity minus actual velocity,
multiplied by assumed moving mass and divided by the tracking time constant.
MuJoCo determines the resulting coupled acceleration. Defaults are a 10 ms
time constant and a 5 N force limit. This produces finite tracking lag rather
than assigning cart acceleration directly. The parameters are provisional,
and no missed steps or measured belt/motor friction are modeled.

`reset(theta_rad=pi, omega_rad_s=0, x_m=0, v_m_s=0)` sets true physical state,
disarms, invalidates home, and starts a new simulated time epoch. It retains
the selected clamp fixture. `home()` asserts that the cart is manually centered;
it does not reposition it. Use `reset(x_m=0)` to place the simulated cart at the
asserted center. A configured smaller rail requires `home(config.rail_half_m)`.
Within an epoch, stop/fault invalidation retains the last-session guard; a
new arm session must differ from the immediately previous one.

`advance(seconds)` is the only source of elapsed simulation time and requires
an integer number of control ticks. `read()` returns the same sensor sample
without drawing new noise or advancing physics. Gaussian angle noise is
applied before quantizing to the 4096-count encoder. The angle wraps to
[-pi, pi), raw count includes the configured upright reference, and angular
velocity is derived from count differences with the executor's 30 Hz
first-order filter. The first sample's velocity estimate is zero. Encoder
sampling can alias rotations exceeding half a revolution per control tick.

Observation cart position, velocity and acceleration are actual simulated
values marked `position_source="simulated_true"`. Hardware observations remain
`commanded_steps`; these are materially different sources. `true_state()`
returns unquantized angle and velocity, cart state, commanded velocity and
acceleration, braking direction, force and clamp status. It does not advance
time. `model` and `data` expose the MuJoCo objects for inspection/viewing.

Commands have 10..100 ms leases anchored to the current sensor time. Each
fresh client command increments its sequence. Advancing past a deadline without
calling the controller disables force, invalidates home/session and latches
`deadline`; reads and streams cannot extend a lease. Arming expires after
100 ms without a first action. Invalid active actions, invalid physical state
and MuJoCo instability warnings also latch faults. `clear_fault()` leaves the
rig disarmed and unhomed. A subsequent home and explicit fresh arm are required.
`stop()` and `close()` invalidate home and remove drive force, preserving an
already latched fault. They do not mechanically clamp the cart.

## Passive decay fixture

Use an explicit MuJoCo equality constraint for stationary-cart captures:

```python
import math
from cartpole_deploy.simulation import SimRig

with SimRig() as rig:
    rig.set_cart_clamped(True)
    rig.reset(theta_rad=math.pi + 0.3)
    samples = [rig.advance(0.001) for _ in range(3000)]
```

The constraint holds the cart at its reset position with a small numerical
residual. A clamped reset requires zero cart velocity, and arming requires
releasing the fixture. A disabled unclamped cart is free to move under pendulum
forces. Real disabled hardware needs its own physical fixture for stationary
cart characterization; driver disable does not establish that condition.

## Gymnasium adapter

```python
import numpy as np
from cartpole_deploy.gym_env import CartPoleEnv

env = CartPoleEnv(max_episode_steps=1000)
try:
    observation, info = env.reset(seed=1)
    observation, reward, terminated, truncated, info = env.step(
        np.array([0.1], dtype=np.float32))
finally:
    env.close()
```

The continuous action is a one-element acceleration in m/s² within the owner
limit. The observation is `[x, v, theta, omega]`, using the encoder angle and
derived angular velocity. Reset starts within +/-0.02 rad of upright and
explicitly homes/arms a new simulation epoch. Options accept the four true
initial state values. Each policy step submits a fresh lease and advances one
policy interval, which must be below 100 ms. Fault, rail departure or angle
beyond 12 degrees terminates the episode; `max_episode_steps` truncates it.
Completion or an invalid action stops drive. Reward is the illustrative
`cos(theta)`. Info includes observation, ground truth and provisional model
status. This is scaffolding for future training, **not a trained controller or
a validated balance benchmark**. Gym's checker advises normalized actions and
finite observation bounds; SI actions and unbounded velocity spaces are
intentional in this starter.

## Optional viewer

Headless tests do not need a display. For a local viewer, save this as
`viewer_demo.py` and run `python viewer_demo.py`, or `mjpython viewer_demo.py`
on macOS. The special macOS launcher and viewer synchronization are documented
in the [official MuJoCo Python guide](https://mujoco.readthedocs.io/en/stable/python.html#passive-viewer).

```python
import math
import time
import mujoco.viewer
from cartpole_deploy.simulation import SimRig

with SimRig() as rig:
    rig.set_cart_clamped(True)
    rig.reset(theta_rad=math.pi + 0.3)
    with mujoco.viewer.launch_passive(rig.model, rig.data) as viewer:
        while viewer.is_running():
            with viewer.lock():
                rig.advance(0.01)
            viewer.sync()
            time.sleep(0.01)
```

The viewer snippet is optional and was not exercised by headless validation.
Do not use a viewer's independent physics loop to advance this rig: lease time
and governor updates belong to `SimRig.advance()`.

## Checks

`python -m pytest -q tests/test_simulation.py` checks model sign and physical
inertia, free period/damping, explicit clamp behavior, reset validity, seeded
noise and Gym behavior, lease expiry/fault latch, action/force/governor bounds,
velocity/position tracking and engine instability handling. With a C++ compiler
and the shipped firmware header present, it also compares 800 governor cases
against the actual C++ source. Float64 Python and float32 firmware results are
compared with numerical tolerances. These checks validate this implementation;
supervised hardware characterization is still required to validate the model.
