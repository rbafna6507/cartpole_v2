# v12: full-rotation overspeed recovery

User confirmed that the 50 RPM failsafe should trigger after a full pendulum
rotation, not during an ordinary fast partial swing. Defaults remain
vmax=0.8, amax_s=amax_b=16, jmax=70; the 20T pulley and 175 mm pendulum are unchanged.

## Behavior

- A wrap-aware encoder monitor identifies a complete 2π excursion in either
  direction. Oscillation across the ±π display boundary is not counted as a turn.
- On completion of a full turn, trigger if the filtered angular speed OR the
  measured average speed of the completed turn exceeds 50 RPM. The average
  catches rotations that slow at the exact completion angle.
- Automatic swing-up, balance, and automatic rail recovery yield to latched
  SPIN_BRAKE (7), SPIN_CENTER (8), then SPIN_WAIT (9). The normal angle controller
  cannot resume or capture while recovery is active.
- Preserve current commanded velocity/acceleration and the jerk governor while
  braking. Return to the existing startup center at a target up to 0.10 m/s,
  acceleration target up to 0.5 m/s²; lower configured limits still apply.
  Rail prediction, hard boundary, speed ceiling, and encoder-fault shutdown stay active.
- Start the quiet timer only at |x|≤3 mm, |v|≤0.005 m/s, |a|≤0.1 m/s². Require
  three continuous wall-clock seconds with valid encoder data, speed below
  30 RPM, no full turn, and the pendulum in the lower half (over 90° from upright).
  New motion outside those conditions resets the timer. Drift away from center
  returns to centering. Waiting has no timeout that restarts motion.
- Resume SWINGUP after the quiet interval, resetting pump/rotation history and
  startup-response watch. Failure to center within 10 seconds gives a disabled
  fault. `stop`/`off` cancel recovery and disable all motors immediately.
- Repeated auto/bal/manual/jog commands cannot bypass active recovery. The host
  console names the new modes; stat shows the phase and elapsed quiet time.

Center is still inferred from commanded steps. This cannot correct a physical
position error from slipping, and it does not home or measure the endstops.

## Verification

- Native C++ tests cover ordinary ±π-crossing swings, clockwise/counterclockwise
  turns, whole-turn average speed, threshold rejection, centering trajectories
  in both directions, jerk/speed/rail constraints, three-second timing, timer
  rollover, repeated calls at one timestamp, disturbance/dropout timer resets,
  centering timeout, reset, and indefinite waiting under persistent fast rotation.
- Fourteen simulator groups pass, including existing firmware equation parity
  and new end-to-end full-spin recovery in both directions. Each returns to
  center, stays there for the quiet interval, then resumes. The simulator is
  an idealized actuator/pendulum model, not measured hardware behavior.
- Existing compiled stop/disable/pulse-count test and host console/run-review
  tests pass. The log reviewer includes modes 7–9 in automatic-active time.
- ESP32 build passes: 338043 program bytes, 22720 global bytes.
- The full swing-up regression still fails sustained balance on its first
  case. This change adds recovery behavior; it does not demonstrate reliable
  physical swing-up or balancing.

Not flashed or physically run by the assistant. Reflash v12 and restart the
Python console for the new mode labels. Historical v10/v11 assessments retain
their original settings and behavior.
