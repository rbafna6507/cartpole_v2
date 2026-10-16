# Python control and identification — 2026-10-16

The native Teensy controller remains the established operator baseline. The new
`ExecutorFeedbackPolicy` runs the high-level AUTO/BAL decisions in Python at
100 or 250 Hz. The Teensy retains its 1 kHz encoder observer, pulse generation,
jerk/speed/rail governor, switch interlocks and expiring command leases. No
firmware change is needed. Hardware commissioning results are recorded in
`evidence/python-control-id-20261016/`; simulation success alone is not physical
validation.

## What the major tuning settings do

These are energy-shaping and full-state feedback settings, rather than one
conventional PID with independent P, I and D knobs. The pole and cart settings
jointly determine the four feedback coefficients for angle, angular velocity,
cart position and cart velocity.

| Setting | Change / retained value | Effect and evidence |
| --- | --- | --- |
| `bw` | Earlier 30 → 10 and 8 Hz; operator later selected 4, then 6 Hz | Bandwidth of the MCU angle/rate observer. Lower values reduce high-frequency rate noise and jittery acceleration, at the cost of tracking delay. Repeated 25 s bw8 trials versus bw10 lowered requested 9–30 Hz acceleration RMS about 42%, applied RMS about 21%, and angle RMS about 19%. These are finite trial results; they do not establish that ever-lower bandwidth is better. Commissioning records each live readback; subsequent operator-console startup restored the saved bw10 default. |
| `pw` | 4.5 → 3 for AUTO | Sets the pole feedback frequency. Lowering it softened an aggressive correction loop. It changes several feedback coefficients together, so it is not equivalent to changing only angle P gain. |
| `bal_pw` | 4.5 retained | Separate feedback frequency for a run started with BAL. AUTO's captured balance uses `pw=3`, so identical initial angles can produce different AUTO and BAL demands. |
| `pz` | 0.85 retained; 1.15 trial was worse | Pole damping target. Increasing it emphasizes rate-dependent damping but also exposes rate noise and interacts with actuator delay/jerk. More damping did not automatically reduce the observed oscillation. |
| `pc1`, `pc2` | −3/−4 → −5/−6 | Cart-centering pole locations. Larger negative magnitudes target faster centering and change the coupled pole feedback as well. They help keep balance near home but cannot repair an incorrect angle zero or physical step loss. |
| `ke` | 4 retained after an unsuccessful 5 trial | Swing-up energy gain. More gain pumps/removes energy more strongly; too much can produce fast, poorly timed upright approaches. |
| `kpx`, `kdx` | 40 and 2 retained | Position and velocity penalties during swing-up. They limit cart wandering and damp translation while the energy term pumps the pendulum. |
| `phase_soft` | 2 retained | Smooths the energy-pump direction change near zero angular velocity. Smaller values make that change sharper. |
| `approach_v` | 0.3 → 0.2 m/s | Progressively lowers the cart speed target near an inbound upright approach, leaving room to catch without carrying excessive sideways motion. |
| `catch_a` | 0.6 → 0.25 rad | Requires the pole closer to upright before switching to balance. Capture also checks angular rate, cart speed/position, acceleration matching and a governed feasibility forecast. |
| `catch_r`, `catch_v`, `catch_da` | 3 rad/s, 0.3 m/s, 4 m/s² | Gate upright capture on manageable rate/speed and the difference between current acceleration and required balance acceleration. These are capture conditions, not extra feedback gains. |
| `jmax` | 150 m/s³ retained | Bounds acceleration change. Raising it makes corrections arrive faster but can increase command roughness. Higher-jerk trials did not establish a repeatable benefit. |
| `vmax*`, `amax*` | 1.5 m/s and 25 m/s² ceilings | Available motion authority; increasing a ceiling does not command that speed continuously. The physical motor's tracking capability is separate from these commanded limits. |
| `rail_fraction` and margins | 95% travel policy; measured half-range ≈0.309 m | Relates the controller's usable envelope to measured switch travel. Recovery begins inside the fault boundary and includes braking distance; it does not use every last millimeter at full speed. |
| `leff` | 0.124 m retained | Effective pendulum length used by energy and feedback calculations. It depends on inertia, not just physical length. Offline candidate values near 0.16 m have not passed validation and have not replaced the working controller value. |

The saved upright reference is separate from these gains. A biased angle zero
can appear as persistent lateral drift: the controller accelerates to correct a
lean that does not match gravity. The current direct-upright reference is 330.
A robust hanging-to-upright calibration model remains unvalidated; commissioning
does not overwrite this reference with ideal hanging calibration.

## SDK interface

`Rig.observation()` keeps its existing four channels. The opt-in
`Rig.control_observation()` adds `magnetic_filtered` angle and two `step`
quantities: commanded acceleration and governor braking direction. The raw
magnetic angle remains available separately. All seven values come from one
board snapshot. Step position/velocity/acceleration describe counted or commanded
motion, not independently measured physical motor tracking.

The console's `python-auto` and `python-bal` use a stopped, complete live parameter
readback. They select filtered-angle feedback plus an independent raw-angle
safety check. Python handles swing energy, approach speed, capture forecasting,
balance and rail return. It does not duplicate the actuator governor. Invalid
sources, timing, starting pose or runtime faults stop the run. BAL refuses a
hanging start before ARM. A normal Python run stops at duration expiry; use
`rehome` explicitly afterward. The commissioning harness performs that return
only following a successful, healthy trial.

Native `auto` and `bal` still run on Teensy. The older four-channel
`HostRatePolicy` remains available for reproducibility; existing learned-policy
exports and portal runners still use their explicit four-channel interface.
Neither vision nor fusion is silently selected for motion.

Simulation uses the same new policy through:

```sh
uv run --locked --extra sim python examples/host_cartpole.py \
  --controller executor-feedback --mode auto --rate 250 --seconds 25 \
  --profile profiles/last-observed-20261015-full-snapshot.json \
  --output /tmp/cartpole-python-auto.json
```

Use a new output filename for each run. `--controller legacy` selects the older
policy. The example's plant/sensor model is provisional and does not simulate the
real observer or transport jitter. BAL starts with zero cart speed, matching its
pre-arm condition.

## Identification and vision

The existing native-run cohort was refitted with frozen training/validation
splits. All 11 full-model assessments failed the unchanged acceptance gates;
there is no new accepted RL plant model. Passive tails suggest useful period and
damping information, but are too short and lack verified physical cart
stationarity. See the complete report in
`../evidence/python-control-id-20261016/native-identification/report.md`.

Next physical identification measurements are fixed-cart passive decay and
bounded independent forcing with separate training and held-out runs. Report
commanded-input gain/delay as composite quantities until camera scale and timing
are independently validated. Preserve raw encoder, filtered angle, command,
executed governor state and sensor validity separately.

The camera audit found a moved/rotated camera and obsolete length calibration,
not a universal detector failure: 801/801 stationary frames detected the pole,
but all were rejected by the old length gate. A separate Engine bug discarding
valid cart-template measurements after a rejected arm was fixed and regression
tested. Existing vision3 and historical releases remain unchanged. Camera
recalibration, motion framing and full-angle accuracy are still required before
vision-based identification or fused control can be considered validated.

## Physical Python commissioning and fresh identification

The recorded best Python AUTO trial used the saved bw10 gains at 250 Hz:
3.172 s to capture, then continuous balance for the remaining 21.816 s of a
25 s run (3.61 degree raw-angle RMS while balancing). A later repeat captured
but hit the right switch at counted x=0.27544 m, inside the prior measured geometric half-span
0.30941 m (governor rail reference 0.30893 m). Driver disable and loss of home were correct. Following manual switch
release, full two-switch home measured 619.2375 mm total travel and established
home epoch 14. That repeated span does not prove why the earlier contact
occurred: independent physical cart tracking is still missing, and the cart was
manually moved between the fault and rehome.

An earlier bw6 Python run captured, then stopped on strict host cadence after
about 7.44 s. Board frames remained 4 ms apart but reached the host in a batch
after a 12.90 ms receipt gap. Computation was below 1.52 ms; the trace does not
isolate USB, OS scheduling, GIL or garbage collection as the cause. No timing or
switch gates were loosened. A 100 Hz bw10 attempt completed 25 s but did not
capture. The successful 250 Hz result is evidence of functioning Python
feedback, not repeatability. Standalone physical Python BAL remains pending.

After full homing, three bounded 100 Hz identification recordings completed:
20 s pilot, 20 s training plus 20 s commanded-hold tail, and a separate 20 s
held-out waveform plus 20 s tail. They use the same live working parameters,
raw magnetic angle and counted cart motion. Maximum counted excursions were
3.413, 6.825 and 5.475 mm respectively; no faults, clipping or dropped log
records occurred. Counted tracking RMS was 0.082 mm in the pilot and 0.160 mm
in training. These comparisons do not independently measure physical step loss.

Both new frozen train/held-out fits reject under the unchanged gates. A
conditional fit using only the training preflight hanging offset predicts the
held-out short-horizon angles closely, but training/validation integral residuals
and an angle-zero diagnostic still fail. No fitted plant or encoder calibration
was promoted, and leff=0.124, jerk=150 and reference330 remain unchanged. The
zero-command tails are not proof of a physically stationary cart. See
`../evidence/python-control-id-20261016/characterization/` for the harness,
source-hashed raw data references, analysis and numerical results.

## Repeatability investigation

Later matched trials separate a working native controller from an uncommissioned
host loop. With the same 41 parameters, reference 330 and home epoch 14, native
AUTO captured in 2.476 s and held approximately 22.52 s of a 25 s run. A Python
trial completed its duration but balanced for only 0.976 s; completion alone is
not a balance success. Its capture decisions agree with the actual native C++
forecast, and the recorded Python requests replay correctly.

Other Python trials stopped on 12–16 ms gaps between consumed observations. The
16 ms case contains every intermediate 4 ms board frame, some received before
the runner resumed. This identifies host scheduling/processing delay, but does
not isolate an OS, GIL, logging or USB cause. Recorded garbage collection does
not overlap that failure. Reducing the Python thread switch interval to 1 ms
and pinning the process to CPU 2 did not establish repeatability.

An explicit experimental `max_gap_periods=2|3` runner argument permits occasional
8/12 ms gaps at 250 Hz, at most two long gaps in a rolling second. The default
remains strict. It does not extend the 20 ms anchored command expiry, alter
sensor freshness, or bypass switch/rail protections. Offline tests advance the
executor and physics every 1 ms while skipping host decisions. The first
hardware max-3 trial stopped after a third 8 ms gap within one second, as
designed; the cart was subsequently returned home. This option is not a fix for
unbounded host scheduling jitter and is not the console default.

See `../evidence/python-control-id-20261016/reliability-audit/` for the numerical
comparison and `gap-validation/` for the bounded-gap safety experiments.

## Stopped timing diagnosis and next powered test

The timing problem also occurs without swing-up arithmetic. A zero-demand run
expired the unchanged 20 ms firmware action lease. The decisive interval was
22.314 ms wall time versus 1.997 ms caller-thread CPU, including delay before or
during sending. The board disabled the driver at counted home. A late action
error could obscure STOP acknowledgement; the SDK now waits for STOP's own OK
and disabled state while retaining the fault latch.

Disabled logger/mirror comparisons still show gaps. Keeping the rig process on
CPU 2 and temporarily excluding video workers from that CPU reduced long gaps
from 67 to 9 over 20 s; a second repeat had zero. The first still had a cluster
that would violate the bounded-gap budget. Camera affinities were restored after
each experiment; no persistent scheduling changes were made. Subsequent isolated
zero-demand and AUTO tests passed, but an immediate AUTO repeat expired its
20 ms lease after 2.748 s. The trace shows a delayed action-send path while
telemetry continued; OS/GIL versus serial-write delay is not isolated.

The final check uses a wire-equivalent CRC implementation in the Python standard
library. Exhaustive short-input, seeded full-length and exact framed-byte tests
preserve the original protocol. A 20 s zero-demand trial and 25 s AUTO trial
passed: capture 3.172 s, then continuous balance 21.816 s, followed by counted
return home. One 8 ms observation gap was accepted by the opt-in test allowance.
This reduces overhead but does not establish a causal fix or repeatability.

The user requested moving on to system identification. Further SDK scheduling
work is parked, while native AUTO/BAL remain the established operator baseline.
New bidirectional decay and forced-motion datasets, with raw camera geometry,
are planned in `../evidence/system-id-20261016/plan.md`. No new physical model is
accepted merely because a Python control trial succeeds.
