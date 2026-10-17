# Existing cart evidence and frozen driven replay

The ideal acceleration-servo cart model can remain an **explicit development assumption**. Existing optical pulses support its local motion shape, velocity-endpoint reconstruction reproduces emitted cart counts within 0.292 mm, and the production backend implements the assumed coupled equations accurately. These data do not identify physical acceleration gain/delay, cart mass/drag or motor force limits. The driven model remains unaccepted: the frozen law's original-training weak-form NRMSE is **0.26796**, above the unchanged **0.15** bound.

[Recorded pulses and optical comparison](results-v1/driven-replay-and-optical-shape.png) · [Actual production backend versus recorded angle](backend-profile-v1/production-backend-driven.png) · [Complete audit](results-v1/report.json) · [Verification](results-v1/verification.json) · [Production replay](backend-profile-v1/report.json) · [Velocity reconstruction comparison](velocity-reconstruction-v1/input-reconstruction.png) · [Bundle checks](verification.json)

## Sources and observation meaning

The strongest local cart evidence is the completed October 17 signed 10/20 mm training pulses and signed 30 mm development pair: six distinct raw hashes/sessions, a 0.65 s reference plus 3 s feedback hold per run, around 100 Hz direct telemetry, simultaneous raw optical pivot measurements, confirmed STOP, no collection faults and zero logger drops. The 30 mm pair has already been inspected and reclassified development by the historic friction study. Each clipped exactly two requested samples at the test's 3 m/s² limit; that protocol deviation is preserved. No unexamined validation data enter this audit, and no coefficients are fitted.

The existing canonical validity rows and segment boundaries are retained. The earlier 5 mm pilot is not added; failed longer negative 5 mm attempts remain excluded. October 16's six native AUTO recordings have empty camera series and all eleven full-model assessments rejected. The earlier Python multisine characterization also rejected and showed amplitude-dependent response. Those reports cannot supply missing physical cart observations or be upgraded by these results.

Firmware increments `ax_pos` when emitting step pulses (`firmware/teensy_executor/teensy_executor.ino:179`) and converts that count to `xc` at line 632. Telemetry publishes `xc`, governor velocity `vc` and governor acceleration `acc_cmd` at line 912. These are distinct from independent physical translation. Raw magnetic `theta` measures the pole; its local fitted phase is not a global angle calibration. Raw camera `pivot_px` measures visible image motion, but the runtime metric calibration is false and there is no fixed-background landmark check here. Fused cart/angle, mirrored encoder packets and filtered omega are not used.

## Frozen prediction results

The exact batch-6 passive candidate is retained: L=0.16030387335574306 m, gamma=0.006891975341585199 /s, c=1.6268943123178277 rad/s², local phase=−0.11297194821931156 rad, friction `−c*tanh(omega/0.05)`. Driven coupling assumes unit acceleration gain and zero input delay. Recorded future governor inputs are supplied for conditional replay, rather than predicted before commands exist.

All rows below are RMS / P95 absolute angle error in degrees:

| Prediction | Original four 10/20 mm runs | Previously inspected 30 mm pair |
|---|---:|---:|
| 0.5 s forecasts, historic causal 7-point rate | 1.183 / 2.594 | 1.314 / 2.700 |
| 0.5 s forecasts, causal frozen-ODE history | 0.880 / 2.052 | 1.132 / 2.297 |
| Continuous, first 0.1 s initialization | 1.258 / 2.496 | 1.736 / 3.874 |
| Continuous, first 0.5 s initialization | 1.134 / 2.312 | 1.329 / 2.925 |

Each short comparison uses seven windows and 350 future samples per run. The history initializer uses at most 0.20 s of past angle/input; the current raw angle is retained. Continuous fits estimate only the initial angle/velocity from the declared history, retain its endpoint raw angle, then score every later point without measurement correction. The model/input coefficients stay fixed. The 0.5 s initialization uses most of the pulse and is shown as sensitivity, not the sole result. All initial-state optimizations converged. `verify.py` confirms future angle/input changes cannot alter initialization.

Plots show faster predicted decay than the recorded later oscillations, plus quiet local offsets in the smaller pulses. Favorable short errors do not erase those mismatches. Fixed-coefficient weak-form NRMSE is 0.26796 across 40 original-training windows and 0.10462 across 20 development windows; the training bound still fails. Original rejected fits and acceptance gates are unchanged.

## What the camera supports

A single map is frozen from the archived four-training-run optical analysis: mean best-lag scale **1001.577 pixels per counted meter**, median proxy lag **15 ms**. Only each recording's pre-pulse median pixel origin is used subsequently. Applying that map without fitting either 30 mm pulse gives **0.216 px RMS** (+30 mm) and **0.187 px RMS** (−30 mm), with 100% valid delivered geometry in both fixed pulse windows. Their apparent return offsets are −0.005 and −0.046 px. The four original pulses give 0.165–0.222 px RMS under the same map.

This supports consistent visible signed pulse shape over approximately ±32 mm counted excursion and up to 0.206 m/s commanded velocity. Scale was derived from counts, not an independent ruler measurement. The lag combines camera delivery, board receipt proxy, detector and physical/count effects; it is not measured actuator latency. Negative 20 mm pulse geometry coverage is 95.1%, and its final hold is only 83.6% with an 88 ms valid-frame gap. Those original gaps and all other per-run coverage remain in the report. There are no repeated trials within each sign/amplitude condition and no claim of statistical repeatability or no slip.

## Production backend and input reconstruction

`backend_replay.py` uses the actual `MujocoBackend` with 1 ms physics, equivalent-rod pole mass 0.02275 kg, assumed cart mass 0.35 kg, cart damping 0.05, force bound 20 N and rail half-length 0.308962494 m. Damping and dry torque are gamma and c times pivot inertia `0.75*m*L²`. Source hashes and full configuration are saved. It copies the audit's causal 0.1 s initial state and interpolates recorded 100 Hz governor acceleration at the start of each 1 ms action, holding that value for the tick. It does not replay the original firmware or claim that intervening 1 kHz input is known.

Across all six runs and 2,137 scored points, production MuJoCo versus recorded encoder is **1.43076° RMS / 3.00937° P95**. Production MuJoCo versus the high-accuracy continuous-input ODE is **0.007741° RMS**, maximum **0.021765°**. Simulated acceleration tracking differs by at most **8.88e−16 m/s²**, and simulated position agrees with an independent discrete ideal-servo integrator to floating-point precision. Peak simulated cart force is **1.06242 N**, with zero saturation ticks. Those forces depend on assumed masses; they are not measured motor loads or force-authority tests.

Input reconstruction has a material limitation. Integrating recorded velocity from pulse start agrees with step-derived position to 0.011–0.046 mm RMS; double-integrating the 100 Hz acceleration snapshots gives 0.048–2.131 mm RMS and up to 3.837 mm maximum. Starting the production replay during the pulse after its 0.1 s initialization yields 5.69–15.95 mm maximum cart/count discrepancy over the remaining run, despite the nearly exact software servo. A small unmatched integrated velocity persists during the hold. The differing integration starts, 100 Hz snapshot reconstruction, and 1 ms hold are explicit approximations, not evidence of measured physical slip or a uniquely identified actuator defect. This replay validates equation implementation and conditional pole prediction; it does not establish exact firmware cart-trajectory fidelity.

The complementary **velocity-endpoint reconstruction resolves the apparent cart drift using existing data**, without new data collection or any parameter fit. For every original governor-velocity interval, acceleration is the average `delta(v)/delta(t)`. At a 1 ms physics tick it is `[v_interpolated(t+1ms)-v_interpolated(t)]/1ms`, so velocity follows the same interpolation through each recorded endpoint. The backend matches these 1 ms reconstructed velocity targets within 2.15e−13 m/s. Both methods start from exactly the same recorded count/governor-velocity and initial pole state. All original scored times are kept.

| Pulse | Velocity-reconstructed cart/count RMS / max (mm) | Optical RMS on common eligible support (px) |
|---|---:|---:|
| +10 mm | 0.018 / 0.073 | 0.229 |
| −10 mm | 0.022 / 0.103 | 0.187 |
| +20 mm | 0.052 / 0.178 | 0.288 |
| −20 mm | 0.066 / 0.221 | 0.276 |
| +30 mm | 0.125 / 0.292 | 0.316 |
| −30 mm | 0.090 / 0.286 | 0.299 |

The same-support optical residual from raw sampled-acceleration integration is 0.987–2.503 px, while counted-position projection is 0.177–0.239 px. The velocity reconstruction therefore recovers the observed pulse shape and counted hold. The frozen training pixel scale/lag and each pre-pulse pixel baseline are unchanged. Support includes only delivered valid raw frames inside the original −0.1..1.1 s pulse window after the replay's initialization; both methods use exactly the same frames. No missing optical samples are filled. See `velocity-reconstruction-v1/report.json` for exact initialization/source bounds and traces.

Pole RMS changes only from **1.43076° to 1.44662°** across the same 2,137 samples, with no force saturation and maximum assumed force 1.06340 N. Thus the numerical cart drift is an input-reconstruction artifact; it does not justify changing the cart plant or collecting another cart batch. It also does not explain the remaining faster predicted pole decay. This reconstruction uses recorded future interval endpoints offline; it is not an online causal differentiator. Governor velocity remains an internal commanded quantity, so the result supports local count-domain servo fidelity plus optical shape agreement, not independent physical metric calibration.

`backend-v1` retains an earlier otherwise identical numerical replay with the default 0.26 m rail assumption and its exact script. `backend-profile-v1` matches the training-profile rail and adds the independent discrete-servo check; no rail boundary was approached, so angle/force metrics are identical.

## Remaining physical-measurement limits

No new collection is required to resolve the reconstruction drift above, and no hardware action is requested while the user is collecting. Broader physical qualification would still require measuring optical rail scale independently at multiple known cart positions in the pole plane, tracking a fixed background landmark, and characterizing exposure/receipt timing uncertainty. It would also require repeated signed cart trajectories with direct optical motion, raw pole angle, direct command/governor telemetry and source-bound completion/STOP records. The existing velocity endpoints already reconstruct local count motion; exact 1 kHz command replay would need higher-rate governor history or a separately verified input reconstruction. Reserve fresh recordings before evaluating metrics. Include wider speed/acceleration/reversal conditions only under the existing collection protections; this audit authorizes no hardware action. Separately measuring mass/force authority is necessary before treating the 20 N force bound or mass/drag values as identified. Upright/full-swing observation and driven behavior remain outside this small hanging-pulse evidence.

## Reproduce

From the repository root, use new output locations. These tools perform only local reads, numerical calculations and evidence writes. `uv --offline` requires the declared dependencies in cache; it is not a data-download step.

```sh
MPLCONFIGDIR=/tmp/cartpole-friction-audit-mpl uv run --offline --script \
  evidence/friction-gym-20261017/cart-dynamics/audit.py \
  --repo . --output /tmp/NEW-cart-audit
uv run --offline --script evidence/friction-gym-20261017/cart-dynamics/verify.py \
  --repo . --report /tmp/NEW-cart-audit/report.json \
  --output /tmp/NEW-cart-audit/verification.json
MPLCONFIGDIR=/tmp/cartpole-friction-audit-mpl uv run --offline --script \
  evidence/friction-gym-20261017/cart-dynamics/backend_replay.py \
  --repo . --audit /tmp/NEW-cart-audit/report.json \
  --output /tmp/NEW-backend-audit
MPLCONFIGDIR=/tmp/cartpole-friction-audit-mpl uv run --offline --script \
  evidence/friction-gym-20261017/cart-dynamics/reconstruction_replay.py \
  --repo . --audit /tmp/NEW-cart-audit/report.json \
  --backend /tmp/NEW-backend-audit/report.json \
  --output /tmp/NEW-velocity-reconstruction
```

The reported run used cached NumPy 2.4.6, SciPy 1.16.3 and Matplotlib 3.11.2. The audit's independent DOP853 and archived 2 ms RK4 short-score RMS differ by at most 2.20e−7 degrees. Report/source bindings, six distinct identities, completion flags, unchanged clamps, equal scored short samples, causal initialization and friction dissipation were checked. All three current plot layouts were visually inspected. No production file, old evidence, hardware connection or git commit was changed by these audit scripts.
