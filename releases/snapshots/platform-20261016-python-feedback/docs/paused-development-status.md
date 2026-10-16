# Paused hardware work — 2026-10-16

Historical record of the earlier local-only increment. Hardware tuning later
resumed; see [current checkpoint](checkpoint-20261016.md) and
[platform status](platform-status.md) for the current state.

Hardware testing remains paused until the user explicitly says the rig is ready.
This increment used only local source, archived recordings, PTY firmware tests,
and MuJoCo. Nothing was flashed or deployed to the Jetson.

## First resumed comparison

The first motion experiment should use `profiles/original-working-20261012.json`,
the archived gains associated with 43.179 s and 42.668 s balance holds (angle RMS
1.90° and 1.31°). That profile was loaded/read back during the last session, but
its proposed comparison AUTO was **never executed**. Keep jerk at **150 m/s³**.
The user will provide the usual upright resting pose for a fresh direct reference.
Do not start motion while the user is holding the pole. Record settled hanging
as a diagnostic; do not replace direct upright with an ideal half-turn estimate.
Use fresh homing geometry, not the archived rail length.

The existing hardware-health preflight still applies. Four encoder I²C errors
occurred in the previous session; the proposed last historical comparison was
rejected by automatic approval review pending investigation. No bypass or repeat
was attempted. The last three errors clustered near 12 cm left of center during
leftward motion; a cable/connector correlation is a hypothesis, not a diagnosis.
A 60 s stationary check had no new errors. A readiness message does not establish
that the sensor issue is resolved.

Start with a short native AUTO trial from the fresh upright pose, using the
historical `pw` feedback that produced those AUTO holds; then test hanging-to-AUTO
swing-up with that same profile. Native BAL uses the distinct `bal_pw`, so do not
treat a BAL trial as an identical comparison. Establish three bounded repeat
trials before changing one parameter family. Compare time to capture, longest continuous balance, angle RMS in early
and late windows, mean/peak x, saturation, recovery exits and all health events.
Extend duration toward the former 40 s holds only if short trials and health
checks support it. Subsequent gains should be compared to this baseline in an
alternating sequence, with the same reference and jerk setting.

## What the recent tuning evidence establishes

- The last direct upright recapture changed 351 to 330 counts (−1.846°). One
  same-gain comparison changed mean cart position from +106 mm to +5 mm. This
  supports angle-reference bias as a contributor to rightward drift; it does
  not distinguish reference-pose repeatability from encoder drift.
- Balance can still become oscillatory with mean cart position near center.
  The current problem is not explained by a constant angle offset alone.
- Recent native AUTO holds were roughly 6–11 s, not repeatably stable. The last
  actual run captured in 1.342 s, held 6.044 s, then left balance for rail recovery
  and later stopped on an encoder fault. Its saved profile is
  `profiles/last-observed-20261015.json`.
- Increasing pz to 1.15 worsened oscillation. Reducing pw to 3.5 improved some
  trials but not their consistency; pw 2.5 weakened capture/centering. Lowering
  observer bandwidth 30→15 reduced some acceleration disagreement but hurt
  capture. Jerk 300 had no repeatable advantage over 150.
- Recorded angular rate and demand contain a substantial 12–18 Hz component,
  while the main pole motion is around 0.7–1 Hz. Possible contributors include
  fixture vibration/play, magnetic measurement error and observer response.
  The logs alone do not isolate these causes. Jerk limiting is frequently active;
  it changes the effective control response but is not proven to be the root cause.
- The normal rail boundary now permits approximately 588 mm of a measured
  619 mm span (95%). Braking still begins earlier when speed/acceleration require
  stopping distance. Widening the envelope did not remove the growing oscillation.

Evidence: `evidence/phase3/retuning-20261015/tunable-motion/postcapture/result.json`
and its preserved recordings and analyses.

## Sensing and calibration

The maintained vision runtime is `src/cartpole_vision/`, separate from archived
vision3. SDK vision clients/providers, source-explicit observations, clock-aware
alignment, encoder mirroring, and a complementary angle-bias fusion observer
are implemented. The viewer can plot encoder, vision, and SDK fusion. Encoder
mirroring comes from the sole serial owner (console/Rig), not a second serial
reader. It is not available from a stopped console unless another authorized
serial owner is publishing it. See `docs/sensing.md`.

Fusion is optional and available for logging/shadow analysis. It has **not been
commissioned as a physical feedback source**. It corrects angle bias slowly;
angular-rate channels remain source-specific. Existing alignments tied to older
upright references must be rebuilt for the current reference. Tracking cadence
in the documented dense-stream test was about 38–39 Hz, with camera acquisition
about 75 Hz; acquisition, tracking, video streaming and control rates differ.
Current service availability was not checked during this paused local increment.

The hanging-to-upright conversion fitter and guarded application commands exist,
but **there is no accepted hanging-only calibration model**. Earlier paired
observations shifted by roughly 2–3° after manual movement. A frozen full-angle
camera-relative fit reduced held-out RMS from 7.45° raw to 3.38°, but needed a
+4.08° correction at the very upright pose that defined zero. It therefore was
not promoted. A single hanging reading cannot by itself distinguish friction
holding the pole off vertical, sensor mapping/history, and reference-pose error.
Use the directly captured working upright for now. The last saved value was 330;
it is not a claim of surveyed physical vertical. See
`evidence/phase3/retuning-20261015/calibration/natural351-camera-map/README.md`.

Vision could help diagnose slow drift and independently check physical cart/pole
motion. It should first run in shadow with the fresh reference and matching clock
alignment. Do not insert the present unvalidated fusion into high-rate feedback
and assume it resolves the oscillation.

## Local development delivered

1. `identification.rig_log_rows` consumes actual Rig JSONL, preserving invalid
   boundaries and reference/home identities. It uses raw magnetic theta and
   governed **commanded** acceleration, not pre-governor demand or assumed
   measured acceleration. It omits filtered omega because its effective delay is
   unknown. Exact duplicate board packets are counted once; conflicting packets,
   clock rollbacks, session changes and missing active reference data fail.
2. `examples/identify_rig.py` reads plain/gzip logs or an explicit tar member
   without extraction, hashes the inputs, fits training only and assesses a
   separate recording. Rejected fits produce no model recommendation.
3. `HostRatePolicy` now has explicit auto and balance-only modes and maps feedback
   gains from supplied controller settings (`pw` for auto, `bal_pw` for bal).
   Balance-only refuses a hanging start and stops on leaving its release envelope.
4. Console `python-auto`/`python-bal` use the actual SDK external-action path at
   100 or 250 Hz, with live v6 parameter readback, 20 ms action leases, explicit
   magnetic/step sources, and stop-on-failure/finally. Native `auto`/`bal` remain
   Teensy 1 kHz control. The Python commands are experimental and not deployed.
5. `ExecutorSimulation` accepts explicit speed/acceleration/jerk/rail limits.
   `examples/host_cartpole.py` exercises the same Python policy against this
   governed MuJoCo backend with a complete saved parameter snapshot. Defaults
   and plant physics remain provisional; no rejected ID estimate was applied.

The host implementation maps energy/feedback terms, but does not reproduce the
native approach-speed limiter, capture ramp or recovery state machines. It uses
the supplied magnetic filtered rate instead of running a hidden 1 kHz observer.
It returns raw demand, so the Teensy/sim executor applies its governor once.
Host runs currently stop and disable on completion; `rehome` is explicit.

Reproducible results and limitations are in `evidence/phase4/paused-20261016/`.
The four 10 s simulator checks use **one seed**, ideal simulated sensing and a
provisional plant. They are an integration check, not robustness acceptance or
validation of physical Python control.

## USB versus Ethernet

Use USB CDC as the first host-control transport. Teensy USB Serial is native USB,
not a 115200-baud UART: PJRC states that the baud setting is ignored. Teensy 4.1's
USB device interface is 480 Mbit/s and its onboard Ethernet is 10/100 Mbit/s.
These are link capabilities, not measured application throughput or latency.
Sources: [USB Serial](https://www.pjrc.com/teensy/td_serial.html),
[Teensy 4.1 specifications](https://www.pjrc.com/store/teensy41.html).

At these small packet sizes neither nominal link bandwidth establishes the
winner. Measure observation age, host execution time, action acceptance age,
p50/p95/p99/max latency, missed deadlines and stale/rejected packets under vision
and inference load. Receipt spacing alone is not end-to-end latency, and clocks
must be mapped with uncertainty or measured by a round-trip instrument.

The current host controller explicitly supports 100/250 Hz; 250 Hz gives a 4 ms
policy interval while the executor remains at 1 kHz. Before adding 500/1000 Hz
host modes, benchmark the complete loop. A compiled transport/scheduling bridge
is an option if Python/runtime or OS scheduling dominates, while retaining the
Python policy API. Changing to Ethernet will not remove those sources of jitter.

If USB timing or topology proves inadequate, compare a direct wired Ethernet
prototype with the same timestamps, sequence checks and expiring leases. UDP
would require loss/reorder handling and stale-packet rejection; TCP would require
bounded buffering and attention to retransmission delays. Neither should carry
internet-facing control directly. USB can stay connected for flashing. No new
Ethernet transport or firmware change was needed in this paused increment.

## Verification

Final local suite:711 passed,7 skipped,381 subtests passed. Independent review
findings were fixed. The new host console integration passed15 consecutive PTY
runs after correcting the emulator to match firmware STATUS publication timing.
`evidence/phase4/paused-20261016/verification.json` records commands, source hashes
and intermediate failures, including one preexisting wall-clock lease failure
that did not recur in its exact rerun or final suite. No hardware timing claim
is inferred from these tests.
