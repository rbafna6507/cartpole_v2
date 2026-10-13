# Swing-up → balance aggression review, September 16

## Finding

The mode switch does not reset velocity, acceleration, estimator, or pulse phase. The common governor continues to slew applied acceleration at jmax. However, the capture gate permits handoffs with large opposing acceleration demands and insufficient time or track to execute them. This can produce sustained maximum-jerk reversals followed by rail braking. These are credible contributors to mechanical skipping, not proof of skipping: cart position is inferred from pulses, and velocity/acceleration are commands.

## Evidence from current v19 log

Source: `logs/run_20260916_153109.csv` and its event log; snapshot hash and sampled episodes in `metrics.json`.

- 22 automatic balance episodes visible in telemetry: 14 exit into rail braking; eight return to swing-up. Median sampled duration 0.1615 seconds. Logs contain 24 capture messages; telemetry can miss episodes shorter than its roughly 40 ms period.
- At 154.496–154.658 board seconds, commanded acceleration changes from −3.810 to +7.530 m/s²: an 11.34 m/s² reversal over 162 ms, consistent with the configured 70 m/s³ jerk. The intervening samples follow the ramp; this is not an instantaneous acceleration jump. The capture then exits into rail braking at 154.699 s.
- At 275.800 s, balance starts with commanded acceleration +4.960 m/s² and velocity +0.479 m/s. Over the following 120 ms acceleration declines only to +0.160, while velocity increases to +0.7838 m/s and the arm passes through upright in the opposite direction. Returning to swing-up follows at 275.961 s.
- These automatic experiments used acceleration caps 16/16 then 20/16 m/s², and jerk settings 70, 100, 50, then 40 m/s³. The successful earlier manual balance used 12/12 and 60. Rail braking uses max(amax_s, amax_b), so the later balance runs can command braking toward 20 m/s² despite amax_b=16. These are caps, not evidence that every cap was reached.
- Auto uses pw=7; upright-only uses bal_pw=8. Changing bal_pw does not change automatic capture gains.

## Capture-gate weakness

`swingup/swing_controller.h:72–85` checks angle, rate, cart position, speed, and instantaneous balance demand. Its acceleration-slew forecast is capped at 100 ms. It does not propagate cart travel and stopping room throughout that handoff. Its angle prediction holds the existing acceleration constant, rather than simulating the governor's changing acceleration.

`reproduce.cpp` exercises the production gate and governor with a representative state near the 275.8 s sample. The gate accepts +4.960 m/s² initial acceleration with −4.7248 m/s² balance demand at jmax=40: a 242.1 ms full slew, versus its 100 ms forecast. An idealized nonlinear continuation crosses the giveup angle at 179 ms with maximum commanded jerk 40.0000 m/s³. This is a counterexample to the gate's feasibility check, not an exact replay: the logged angle is raw, whereas capture uses an unlogged estimated angle; motor tracking is assumed perfect.

Rail recovery also hands back to swing-up while moving inward near the edge, without first settling. Capture can follow soon afterward. That explains why a successful manual start near rest does not establish that the automatic handoff is gentle or feasible.

## Separate electrical timing issue

`swingup/swingup.ino:240–251` updates logical direction, writes the physical DIR pin, then updates pulse rate. The timer ISR can run between these operations, and there is no explicit DIR setup/hold guard. A pulse can theoretically be counted with the new logical direction while the physical pin still has the old direction. This is a genuine race to remove, but we have not measured its occurrence or established that it causes belt tooth skipping. Reversals occur near zero commanded speed, reducing the opportunities for this race.

The [Allegro A4988 datasheet, page 6](https://www.allegromicro.com/~/media/Files/Datasheets/A4988-Datasheet.ashx) requires 200 ns input setup and hold around STEP and 1 µs minimum high/low STEP widths. A guarded direction transition owned by the pulse ISR would make those constraints explicit. An oscilloscope/logic analyzer is needed to verify actual timing.

## Recommended changes, in order

1. Make capture feasibility account for the full jerk-limited transient, estimated angle/rate, speed headroom, and stopping distance to both rail ends. Reject or shape an infeasible approach before switching. Preserve the current velocity/acceleration continuity and rail protection.
2. Shape swing-up near upright so its acceleration already approaches balance demand. Simply blending after capture adds delay, and simply reducing jerk makes an already late reversal slower. Evaluate the approach and capture together in the simulator before a hardware trial.
3. Add a pulse-safe DIR transition with coherent direction/count updates and explicit setup/hold time.
4. Record estimated angle, requested acceleration, acceleration mismatch, and capture/rejection reasons at transitions. The existing 25 Hz telemetry cannot reveal individual 1 kHz switch decisions or electrical pulses.

Do not increase acceleration further to force capture. Establish a conservative matched-limit baseline after the feasibility change and compare against the recorded 12/12/60 manual run. No inertia addition is indicated by these findings; it would change the plant and the required swing-up tuning.

## Verification and scope

Compiled and ran `reproduce.cpp` against the current production headers; its assertions confirm acceptance of the problematic state and preservation of the configured acceleration slew bound. `summarize.py` records the source hash and reproduces sampled episode counts. No production firmware, live settings, serial commands, or uploads changed in this review.
