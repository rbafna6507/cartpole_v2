Balance-command jitter comparison — 2026-10-16

USER REQUEST
Preserve the successful bandwidth-10 tuning, make it the console default, and
investigate smoother balance commands using that baseline.

PRESERVED DEFAULT
profiles/candidate-20261016-bw10.json remains byte-identical, SHA256:
82b896439486c1c6f2e8c2e8209fffb6a7169c04b5dbae56ee7977f22e181d39
The package resource control/tuned-20261016-bw10.json is identical. Both local
source and the active Jetson console now load/read back these 40 settings while
stopped before the interactive prompt; default noninteractive AUTO/BAL also
load them. --keep-board-params opts out; --startup-profile PATH selects another
profile. Diagnostic CLI commands do not implicitly load tuning. A faulted
interactive session remains available for diagnosis and defers loading until
explicit CLEAR. Failed profile loading cannot start queued motion. Operator
set/load commands persist in the session. No reference/geometry calibration,
arming, homing, or EEPROM tuning write occurs on startup. The profile includes
rail fraction/margins and motion limits but excludes measured rail half-length.
Bare SDK Rig sessions keep existing behavior.

Deployment touched only the existing native console, the startup helper, and
the packaged profile. Local experimental Python-control console features were
not deployed. A real stopped uv-run smoke test changed bw8 back to bw10 and
verified all settings. No ARM/MODE/HOME/CENTER/CAL commands were issued. Package
wheel and source distribution built successfully; wheel contains the exact
profile and startup helper. Local full suite earlier passed 721 tests, 7 skips,
384 subtests. The recorded final focused regression passed 47 tests/12 subtests.
An independent code review found no important issues.

EXPERIMENT DESIGN
Native 1 kHz control, 250 Hz recorded telemetry, encoder only. Jerk150 m/s^3,
pw3, pz.85, leff.124 and all swing/capture/motion settings fixed. Only bw changed.
Reference330 was retained; no hanging-zero recalibration. Each run required a
full second of stable hanging at counted home. Both switch interlocks, all
firmware deadlines, host age/position guards, full AUTO return and final STOP
remained active. Home epoch9, span16509 steps (619.0875 mm); normal boundary
+/-294.0375 mm, host guard +/-296.5375 mm. No firmware upload or reset.

Order: A1 bw10 25s, B1 bw9 25s, C1 bw8 25s, A2 bw10 25s, C2 bw8 25s,
C3 bw8 60s. Every run captured and stayed in balance through its AUTO deadline,
then returned home normally. No new faults, missed control deadlines or I2C
errors. All results, including the less favorable bw9, are retained.

MATCHED WINDOW RESULTS
Each row uses 15 seconds starting 2 seconds into its balance bout. These windows
were complete, with no gap above20 ms. Units: demand and applied acceleration
RMS m/s^2, angle RMS degrees. Jerk fraction uses 4ms interval-average derivatives
and is not an exact instantaneous 1 kHz duty cycle.

run    capture  hold     angle RMS  demand9-30  applied9-30  jerk-limit fraction
A1     2.543    22.456   3.515      2.224       1.229        55.9%
B1     2.579    22.420   4.182      1.880       1.087        58.3%
C1     2.507    22.492   2.617      1.207       1.015        33.1%
A2     2.551    22.448   2.926      1.522       1.192        31.3%
C2     3.246    21.752   2.577      0.978       0.904        17.6%
C3     3.284    56.716   2.645      1.056       0.974        22.2%

Across the two matched 25s repeats per setting, bw8 versus bw10 reduced mean
9-30 Hz requested acceleration RMS by42%, applied acceleration RMS by21%, and
angle RMS from3.22 to2.60 degrees. Sampled jerk-limit fraction fell from43.6% to
25.4%. Capture times show a tradeoff: one bw8 caught in2.507s, subsequent runs
in3.246/3.284s, versus2.543/2.551s for bw10. The 60s bw8 confirmation held56.716s
continuously after capture, then returned normally. Its whole-hold angle RMS
was3.053 degrees; the observed return transition was about-12.7 degrees, so this
is not proof of unlimited stability or completely smooth balance. Baseline
run-to-run variation is substantial. This is a promising separate candidate,
not sufficient evidence to replace the user's chosen default automatically.

INTERPRETATION
AUTO uses pole-placement state feedback. Earlier long bandwidth-10 holds show
roughly77% of the 4-30 Hz demand variance associated with the angular-rate
feedback term. The requested acceleration changes faster than the jerk-limited
actuator can follow. No rail-recovery events occurred in these comparison
holds. Lowering observer bandwidth attenuates this feedback but adds delay and
also affects swing estimation. That is why only bw was changed first, leaving
jerk150 and the gains fixed. Bandwidth9's angle error worsened despite some
high-frequency reduction and was not promoted. Lower jerk is not automatically
better: it can add lag to a loop already limited by its acceleration governor.

Encoder-only logs cannot distinguish real pole vibration, flexible mechanics,
or magnetic/encoder disturbance. Direct count quantization alone is much too
small to explain the observed demand amplitude in the prior offline analysis,
but it could seed an oscillation. Cart velocity and acceleration are commanded
states, not independent physical measurements. The reference330 trim and the
hanging-to-upright model remain unvalidated; none of that was changed here.

HOW TO USE
Default console: existing uv run --locked --extra hardware cartpole-console
invocation, with --port ... and --rate 250.
No load command needed for the preserved bw10 profile.
Optional smoothing test, while stopped:
  load profiles/candidate-20261016-smoother-bw8.json
  auto 25
Reopening the default console restores bw10, or load the original candidate.
Both profile files exist in the active Jetson release. Future tests should
repeat bw8 for catch reliability and longer hold stability before promotion.

FINAL STATE
Original40-setting bw10 profile restored and read back, reference330 unchanged,
healthy and motor-disabled at counted home, fault0, misses0, cumulative I2C5,
switch checks enabled, epoch9. Motor supply was not switched off by software.

EVIDENCE
compact-evidence.json includes report headers, comparison scores, console
verification and SHA256/size/path manifests for every original report, parameter
snapshot, image, and raw command/telemetry JSONL on the Jetson. Full raw data is
retained in /home/rbafna/cartpole-v2-runs/jitter-20261016/<run>/.
The slow bulk download was canceled; this repository's compact evidence does
not claim to contain the complete raw runs. score_jitter.py reproduces scores
from those full reports. native_jitter_trial.py is the exact one-off guarded
harness, with deployment paths/reference hardcoded; it is evidence, not a
portable general-purpose operator entry point. Prior offline analysis scripts
and notes explain decomposition, observer replay and spectral limitations.
