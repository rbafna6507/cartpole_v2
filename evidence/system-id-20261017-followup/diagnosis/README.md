# Offline input and equilibrium diagnosis — October 17, 2026

This is development analysis of already viewed recordings. It does not change old reports, acceptance gates, live settings, or any model. Raw input hashes are checked against the preserved batch and completion reports. No hardware or network access is used.

The main finding is that sampling the 1 kHz governor at 100 Hz does not explain the driven-fit rejection. Replacing the weak-form acceleration term with an integral of logged velocity increments leaves the original training NRMSE essentially unchanged. A separate equilibrium nuisance term for each training run has much greater effect, but its large impact on the physical coefficients prevents interpreting it as an established correction.

| Development comparison | Training integral NRMSE | Previously viewed 30 mm integral NRMSE | Effective length | Damping | Input gain | Delay |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original sampled acceleration | 0.2528033 | 0.1354488 | 0.174957 m | 1.4362/s | 1.4090 | 0 ms |
| Velocity increments | 0.2528020 | 0.1307265 | 0.173704 m | 1.5960/s | 1.4415 | 5 ms |
| Original input + four run-specific gravity offset terms | 0.1380030 | Not evaluated | 0.141876 m | 2.9825/s | 1.1459 | 0 ms |

The velocity formulation evaluates `-∫ v'(t) cos(q(t)) φ(t) dt` using piecewise-linear velocity and angle and five-point Gaussian quadrature on each original sample interval. Each interval's velocity change is preserved; neither angle nor velocity is numerically differentiated into a noisy pointwise acceleration. It uses the same 40 training windows, gravity/damping features, targets, phase, and delay candidate grid as the preserved fit. These velocity values are governor state, not independent physical cart velocity. Differences between a piecewise-linear trajectory and unobserved sub-sample motion remain possible.

Across the six admitted pulse runs, the sampled-acceleration trapezoidal integral differs from governor velocity increments by 3.44–4.76% RMS per interval and accumulates 3.03–6.95 mm/s maximum velocity error. Correcting this discrepancy fails to remove the training residual. This narrows the explanation; it does not certify exact actuator dynamics or metrology.

The four additional fitted local phase terms are +0.02108, +0.01200, −0.00277 and −0.00609 rad in chronological +10, −10, +20 and −20 mm runs. The raw initial angles move in the same chronological direction: 3.05416, 3.04955, 3.04188 and 3.02961 rad. At small swing amplitudes, such offsets can strongly bias a pendulum fit. However, the nuisance terms can absorb static friction, sensor offset, varying equilibrium, or omitted dynamics. They are not independent calibration and must not be copied into the plant or used to automatically recenter each run. Length and damping changing substantially with this choice demonstrate confounding.

The fixed pre-pulse window `[−0.25, −0.05] s` gives raw camera `−image_angle` medians of approximately 0.00615, 0.01270, 0.01795 and 0.01473 rad for those runs. Its slow trend does not corroborate the encoder trend. The report retains camera IQR, sample counts, encoder spans, and a fixed last-half-second tail comparison. Receipt times provide only a same-host proxy; camera pose and detector bias are not independently calibrated. The tail window is not claimed to be physically stationary. These small static differences cannot establish which sensor is correct.

## Recommended next experiment

Prefer duration variation over many repetitions at the old 0.65 s duration. One interleaved ±10 mm / 0.65 s repeat pair provides a baseline. Then use signed ±10 mm at 0.45 and 0.80 s, and signed ±20 mm at 0.80 and 1.00 s, subject to the existing preflight and measured-motion guards. Interleave directions and durations to avoid confounding chronological drift with amplitude. Retain at least one second of raw static pre-pulse observations and at least three seconds of tail, together with raw camera angle and geometry. No guard or lease increase is justified by this analysis.

For the existing `A sin^4(πt/T)` reference, peak acceleration is `4π²|A|/T²`. Thus 20 mm / 0.45 s requests 3.90 m/s² before feedback and is inappropriate under the 3 m/s² experiment limit; 10 mm / 0.45 s requests 1.95 m/s². Actual feedback/governor motion remains authoritative. Changing duration changes the excitation spectrum and separates timing/input effects from angle-dependent residuals more effectively than scaling the same waveform alone.

Analyze matched raw-angle bins across the different durations and signs, retain every run's initial/final raw angle, and compare camera/encoder disagreement against angular velocity. Residuals that track angle across frequencies suggest a map/geometry or angle-dependent force issue; residuals that scale with speed or acceleration suggest timing/dynamic effects. These are discriminating hypotheses, not exclusive diagnoses. Once a candidate and analysis are frozen, reserve fresh recordings for acceptance; all recordings used to choose the candidate are development.

## Reproduce

```sh
/path/to/cartpole_v2/.venv/bin/python \
  /path/to/cartpole_v2/evidence/system-id-20261017-followup/diagnosis/diagnose_input.py \
  --repo /path/to/cartpole_v2 --output /tmp/new-input-diagnosis.json

/path/to/cartpole_v2/.venv/bin/python -m pytest -q \
  /path/to/cartpole_v2/evidence/system-id-20261017-followup/diagnosis/test_diagnose_input.py
```

The script also declares uv dependencies. Output must be a new path. `input-diagnosis-development-v1.json` contains exact figures, source hashes, per-run residuals, sampling diagnostics, and camera comparisons. The baseline reproduces the preserved parameters and both integral NRMSE values exactly. Three numerical tests cover the analytic constant-acceleration integral, velocity-offset invariance, and an irregular-grid comparison against dense quadrature; all passed after first failing before the new integral implementation existed.

## Independent simulation interface review

The new governed Gym adapter and shared SDK observation codec were reviewed separately from physical identification. Three issues found in review were corrected by the implementation agent: policy-visible age semantics now match the hardware's board-snapshot proxy; actual causal startup ticks align decisions with delayed telemetry; and a numeric Gym action on unusable telemetry sends no demand and allows lease expiry instead of crashing the training loop.

`simulation-interface-independent-review.json` pins the reviewed source hashes. Fifteen adapter/codec tests plus the three diagnosis tests passed. An additional check invokes the actual `Rig.control_observation()` encoding methods on a preserved raw `STATE`, with no transport or device access. Raw and filtered channel encodings match exactly. Delay pairs 0+0, 1+1, 3+3 and 9+0 ms survive thirty 100 Hz decisions; 9+3 ms correctly exhausts the 20 ms anchored lease. Complete telemetry loss returns a terminal lease fault without a Gym action exception.

```sh
/path/to/cartpole_v2/.venv/bin/python \
  /path/to/cartpole_v2/evidence/system-id-20261017-followup/diagnosis/review_sim_interface.py \
  --repo /path/to/cartpole_v2 --output /tmp/new-simulation-interface-review.json
```

This review does not establish physical servo tracking, a global encoder map, the force ceiling, or hardware policy transfer. The full-suite run and its sandbox/concurrent-development limitations are recorded in `verification.json`; later focused checks supersede the transient missing-implementation failures, without concealing the original run.

## Final review follow-up

`simulation-interface-independent-review-v2.json` supersedes the earlier interface hash snapshot after the exact acceleration Box endpoint regression was fixed. The current adapter and diagnosis suites passed 19 tests. The replay script records only checks actually executed by that invocation; historical pytest results remain in the separate verification reports.

`operator-workflow-independent-review.json` records the final offline review and source hashes. Five new regression cases reproduced two protocol-binding gaps: modern protocol records could fall through the historical path, and the protocol procedure was not compared with the completion report or raw start event. The fixed collection/protocol and workflow suites passed 46 tests.

`synthetic-fit-review/recorded-vs-frozen-ode.png` and `.pdf` show the new saved-fit review workflow. These are prominently labelled **synthetic numerical verification, not rig measurements** and were visually checked. The source fit and validation files remain unchanged in the earlier synthetic CLI verification directory. The 0.5 s forecast RMS is exactly the saved 0.00165539964850215 rad. `report.json` preserves the saved admission and model coefficients, raw source and annotation identities, fixed gates, causal initial conditions, short forecasts and continuous trajectories. Ten plotting tests passed using cached matplotlib dependencies. The CLI is `scripts/system-id review-fit --fit FIT --validation RAW --validation-annotations ANNOTATIONS --output NEW_DIRECTORY`; this is frozen passive ODE replay, not a MuJoCo validation or new acceptance test.
