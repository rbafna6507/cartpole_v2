# v9: ENABLE initialization fix and rail recovery

## Fix for v8 no-motion behavior

The installed ESP32 Arduino core checks its pin registry before `digitalWrite()` writes a GPIO. v8 preloaded GPIO27 HIGH and configured it through `gpio_set_direction()` directly, bypassing that registry. Later `energize(true)` set the software flag but Arduino could reject the write, leaving the drivers disabled. Logs 124920 and 125001 identify v8, show no-response faults, and the latter reports energized=1 after `on` with no pendulum response. This is consistent with the confirmed software initialization defect.

v9 preloads GPIO27 HIGH, then calls `pinMode(PIN_EN_ALL, OUTPUT)` before serial/I2C initialization. All later Arduino writes are registered. The GPIO test now models this registry requirement and tests that `on` drives ENABLE LOW and `stop` drives it HIGH. `stat` reports the GPIO output-register level separately from the software energized flag. This verifies the commanded output latch, not the voltage at a disconnected driver terminal. Startup remains disabled; `auto` enables all three drivers before swing-up; `stop` disables them. Firmware cannot control the reset/bootloader interval.

## Rail behavior

Physical travel remains 300 mm, from −150 to +150 mm relative to the existing startup/home reference.

| Region or condition | Action |
|---|---|
| Central 260 mm, −130 to +130 mm | Normal pendulum control, subject to stopping-distance prediction |
| Within 20 mm of either physical end | Latch RAIL_BRAKE; pause swing-up/balance and decelerate toward rest |
| Predicted stop would cross ±135 mm | Start recovery earlier, even if still inside the central 260 mm |
| Nearly stopped: speed ≤0.01 m/s and acceleration magnitude ≤0.1 m/s² | Enter RECENTER |
| Returning to center | Velocity target capped at 0.15 m/s; requested acceleration at 1.5 m/s² or lower configured limit; retain jerk limiting |
| Within ±3 mm, nearly stopped for 100 ms | Automatic run resumes SWINGUP; manual run ends IDLE with drivers disabled |
| Position exceeds ±140 mm | Fault and disable all drivers |
| Recovery exceeds 8 s | Fault and disable all drivers |

At 0.75 m/s, zero acceleration, amax=15 and jmax=50, stopping distance is approximately **86.6 mm**. Starting braking only 20 mm from the end would be too late. Thus the central 260 mm is positionally available; it cannot all be traversed at unrestricted maximum speed. Low-speed motion at x=129 mm is explicitly tested without premature recovery.

The reference is never reset during recovery. Position still comes from commanded steps, not an endstop or cart encoder. Hand movement while disabled or missed steps invalidate it. Recovery is not homing. The startup pendulum-response monitor remains armed through recovery so repeated recovery cannot conceal a nonmoving motor.

User `stop` cancels recovery immediately and disables all axes. Recovery itself keeps drivers enabled; height axes retain their existing command behavior. Held manual `v` commands are ignored during recovery. Explicit new mode commands still replace the current task.

Console modes 5 and 6 are RAIL_BRAKE and RECENTER. The simulator mirrors automatic recovery and records its duration/count; the run reviewer counts recovery telemetry as part of active automatic runs.

## Verification and limitations

- Ten mirrored host recovery scenarios pass: full-speed approaches, near-edge low-speed approaches, starting stopped in the margin, moving inward, and manual acceleration/jerk limits.
- Tests verify stop-before-return, successful center settling, speed/jerk constraints, no ±140 mm crossing from the tested feasible states, timeout and reset.
- Disabled-driver test passes with Arduino GPIO registration modeled, including stale-rate pulse suppression.
- Eleven simulator test groups pass, including rail recovery and the unchanged no-pendulum-response fault test.
- Console-event and log-review tests pass.
- ESP32 compile passes: 336,027 bytes program, 22,648 bytes globals.
- Full swing-up capture regression still does not balance in its first case. Recorded-state recovery remains imperfect; no improved physical balance claim is made.
- Not flashed and not physically run. The GPIO27 output-level diagnostic is available after reflashing.
