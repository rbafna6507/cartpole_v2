# Run system identification yourself

Use `scripts/system-id` to collect reproducible records, fit independent training and validation data, and export an explicitly scoped MuJoCo/Gym configuration. It resolves its repository from the script location, so it works from another directory. It uses `uv`: collection selects `hardware` plus `id` (NumPy), fitting selects `id`, and simulation/model commands select `sim`. Hardware collection does not require MuJoCo or Gymnasium, and help needs no optional extra. An installed SDK also provides `cartpole-id`.

```sh
ID=/absolute/path/to/cartpole_v2/scripts/system-id
"$ID" --help
"$ID" collect-passive --help
```

Help and offline commands never open serial. Hardware commands require an explicit port and a **new output directory**. They preserve source hashes, live parameters, saved reference/home identity, raw telemetry, timing, failures and STOP outcomes. Existing outputs are never overwritten. A failed run remains failed evidence; use another directory for the next attempt.

The scripts do not calibrate, home, clear faults, change parameters, flash firmware or change scheduler settings. Resolve preflight failures using the separate trusted rig console. Installed limit switches must remain enabled and released. Only one process may own serial.

## 1. Inspect the stopped rig

Purpose: record readiness, the complete live parameter catalog, and the currently saved reference and home epoch. Inspection connects stopped and sends STOP before completion.

```sh
PORT=/dev/serial/by-id/your-device
"$ID" inspect --port "$PORT" --output runs/inspection-01
```

Collection requires a healthy, homed, disabled executor, saved valid encoder reference, cart within 3 mm of counted home, settled governor, and a quiet hanging pole. It accepts the current saved reference/home rather than hardcoding a particular installation. Add `--expected-reference 330 --expected-home 14` when you intend to pin those exact values; use your inspected values.

## 2. Collect manual passive releases

Purpose: identify passive pole gravity/damping from free motion while the operator physically restrains the cart. The script **never arms**. Wait for its `"status":"recording","drivers_enabled":false` message, then displace and release the pole. Record several releases with different amplitudes and both directions. Keep hands clear of the pole during each selected free interval and distinguish handling from free motion in your annotations.

```sh
"$ID" collect-passive --port "$PORT" --seconds 120 \
  --output runs/passive-train-01
# On a separate recording, collect fresh validation releases after freezing
# the training model and the intended validation procedure.
"$ID" collect-passive --port "$PORT" --seconds 120 \
  --output runs/passive-validation-01
```

The default raw camera URL is `http://127.0.0.1:3090/api/sensing-stream?max_hz=100`. Camera work runs in a separate process. It inherits the launching process’s CPU affinity: run the integrated collector without `taskset -c 2`, which would pin both camera and control to the same CPU. The package does not change CPU affinity or scheduler settings. A fresh actual camera frame with valid source age is required before serial collection; advancing HTTP heartbeat envelopes alone do not establish camera readiness; camera failure during collection stops the procedure. Use `--camera-url URL` for an explicit endpoint, or `--no-camera` to deliberately record the absence of independent camera evidence. Raw images/geometry can support stationarity assessment, but uncalibrated pixels do not establish metric cart motion or global angle calibration.

Camera-enabled sessions also publish the current encoder session to the portal through the existing read-only UDP mirror. Mirrored or fused values in camera packets are display data. Fitting uses **direct Rig JSONL raw `theta`**, never `angle_hat`, mirrored encoder packets or filtered `omega`. Board `unwrapped_us` and raw camera `vision.t` have different clock meanings; no cross-host clock mapping or sensor fusion is inferred.

Ctrl-C preserves partial records and attempts STOP. A disconnected camera, stale/unhealthy telemetry, or lost logger records fails the run. Inspect `report.json` and `vision-report.json`, not just whether files exist.

## 3. Annotate free intervals before fitting

Find the `rig-*.jsonl` file in each run directory. Plain JSONL, `.jsonl.gz` and `archive.tar.gz::exact/member.jsonl` are supported. The hash in an annotation is the decompressed exact JSONL content hash. Loading is bounded to 256 MiB of decompressed JSONL, 4 MiB per line and 500,000 records; archive scans additionally cap entries and total declared bytes. Files are streamed and archive members are never extracted.

Keep each newly collected raw log with its sibling `report.json`, including when archiving or compressing it. Fitting requires that report to match the raw basename and decompressed hash, confirm completion and STOP, and record zero logger drops and no camera/collection failure. Raw termination errors and failed STOP records also reject admission. Historical raw-only recordings retain an explicitly labeled compatibility path; they do not acquire a new completion guarantee.

```sh
"$ID" annotations-template --input runs/passive-train-01/rig-EXACT.jsonl \
  --output runs/train-annotations.json
"$ID" annotations-template --input runs/passive-validation-01/rig-EXACT.jsonl \
  --output runs/validation-annotations.json
```

Edit each new template manually. Its time zero is the first recorded STATE. Supply a truthful restraint description and selection method, then add nonoverlapping hand-clear intervals:

```json
{
  "source_sha256": "keep the generated source hash",
  "selected_before_scoring": true,
  "operator_cart_restraint": "cart base physically restrained by operator",
  "selection_method": "hand-clear intervals marked from raw video before scoring",
  "episodes": [
    {"episode_id":"release-1", "board_relative_s":[8.2,11.2], "reason":"hand clear; freely decaying pole"},
    {"episode_id":"release-2", "board_relative_s":[16.1,19.1], "reason":"opposite direction free release"}
  ]
}
```

Do not choose intervals by whichever ones fit best. Static tails cannot validate a dynamic model. Separate recordings and source identities are required for training and validation; renaming a copy does not create a holdout. Exact repeated STATUS snapshots are counted and deduplicated only when every board field agrees; contradictory repeats and reversed clocks fail without rewriting the source.

## 4. Fit and validate passive dynamics

Declare the model before scoring validation. The default viscous model is directly representable in the current simulator. The optional `viscous_coulomb` model is useful for diagnosis but a nonzero Coulomb term cannot currently be exported.

```sh
"$ID" fit-passive \
  --training runs/passive-train-01/rig-EXACT.jsonl \
  --training-annotations runs/train-annotations.json \
  --validation runs/passive-validation-01/rig-EXACT.jsonl \
  --validation-annotations runs/validation-annotations.json \
  --model viscous --output runs/passive-fit-01.json
```

The copied, reviewed weak-form method retains the frozen numerical gates. Parameters and local gravity phase are estimated from training only. Reports include aggregate and per-episode validation, conditional uncertainty, raw/annotation/source hashes and rejection reasons. Gaps never join integration windows. Exit 0 means the configured scoped checks passed; exit 2 means rejection or invalid input. Rejected fit reports are saved with no recommended model.

Even a passed report is **conditional passive-down evidence**: physical cart restraint and angle mapping remain assumptions unless independently established. An inferred hanging-region phase is not a global encoder calibration. A short-horizon validation score does not validate upright, full-swing, motor force, actuator delay or hardware RL transfer. Existing archived training/heldout results are unchanged and do not become newly accepted models merely because this workflow exists.

## 5. Collect a bounded driven pulse

Purpose: excite the cart/pole coupling with a short known reference, return the cart toward counted home, and observe the response under active cart hold. Begin with signed **5 mm**. Inspect real motion, angle excursion, timing, health, camera evidence, clamping and return behavior before choosing a larger trial. The allowlist is not an automatic escalation schedule.

```sh
"$ID" collect-pulse --execute --port "$PORT" --amplitude-mm 5 --hold-seconds 3 \
  --output runs/pulse-plus5-01
# A separately chosen opposite-direction trial:
"$ID" collect-pulse --execute --port "$PORT" --amplitude-mm -5 --hold-seconds 3 \
  --output runs/pulse-minus5-01
```

The reference is `x=A*sin(pi*t/0.65)^4`, with zero position, velocity and acceleration at both endpoints. Allowed amplitudes are ±5/10/20/30 mm. At 30 mm its analytic peaks are 0.18836 m/s velocity, 2.80320 m/s² acceleration and 37.0662 m/s³ jerk. These are reference bounds, not measured trajectory guarantees.

The 100 Hz policy commands `a_ref + 80*(x_ref-x) + 14*(v_ref-v)`, clamped to ±3 m/s². It retains the MCU's unchanged 20 ms anchored lease, governor, rail and health checks. Runtime guards stop at |x|≥0.05 m, |v|≥0.3 m/s, departure from the initial hanging angle≥1 rad, |omega|≥10 rad/s, replay, or host/board gaps≥20 ms. The pulse is followed by **feedback cart hold** for an explicit `--hold-seconds` value from 3 through 12 s (default 12 s), with a bounded 40 ms deadline allowance; this is not zero-input passive decay or independently proven fixed-cart motion.

Logs distinguish requested acceleration, reference acceleration and sampled MCU governor acceleration. The 100 Hz command steps can reach the existing MCU jerk limit even when analytic reference jerk is lower. Full raw telemetry is still sampled at 100 Hz; fast driven fitting may require replaying the 1 kHz governor between samples. A policy clamp is explicitly recorded as a fitting protocol deviation.

The existing driven fitter is wrapped without changing its numerical fit or original gates:

```sh
"$ID" fit-driven --training runs/pulse-train/rig-EXACT.jsonl \
  --validation runs/pulse-validation/rig-EXACT.jsonl \
  --output runs/driven-fit-01.json
```

It uses direct raw angle and the MCU's jerk-limited `acceleration`, not demand. The CLI additionally requires validation angle span ≥0.15 rad and input standard deviation ≥0.05 m/s², using the existing excitation minima. This prevents a static, zero-error validation recording from certifying dynamics. Reports preserve the untouched `underlying_fit` and the supplemental check; overall rejection blocks model export. A single brief pulse may lack the existing fitter's minimum excitation/window coverage; such a result stays rejected. Plan sufficient distinct forcing before freezing fresh validation, rather than lowering gates after seeing rejection.

## 6. Export a scoped simulation model

Purpose: create a new immutable simulator configuration from an accepted fit, with every remaining assumed quantity visible.

```sh
"$ID" assumptions-template --output runs/assumptions-01.json
# Edit the full config and provide a nonempty rationale for assumed masses,
# rail, force authority, cart damping and other unmeasured dynamics.
"$ID" export-model --report runs/passive-fit-01.json --scope passive-down \
  --assumptions runs/assumptions-01.json --output runs/model-01.json
```

The template explicitly uses 1 ms physics and `control_steps=10`, so Gym operates at 100 Hz. Export changes only effective length and hinge damping:

`hinge_damping = gamma * I_pivot`, with `I_pivot = 0.75 * assumed_pole_mass * L_eff^2` for the simulator's uniform-rod convention.

It preserves the full fit report, its hash, source hashes, scope, assumptions and local-phase limitations. No live reference or default model is changed. Rejected fits cannot export. Unsupported Coulomb friction, non-unit driven input gain or nonzero driven delay also fail, because silently omitting them would misrepresent the model. An export always records `recommended_for_hardware_rl=false`.

## 7. Load in MuJoCo/Gym

```sh
"$ID" gym-smoke --model runs/model-01.json --steps 100 \
  --output runs/gym-smoke-01.json
uv run --project /absolute/path/to/cartpole_v2 --extra sim python \
  /absolute/path/to/cartpole_v2/examples/load_identified_model.py runs/model-01.json
```

The example creates `CartpoleEnv` from the verified content-hashed export, explicitly at 100 Hz. Its action is a cart acceleration intent in m/s². This simulation does not model SDK host timing or MCU action leases. Replace the example's zero action with an offline policy when ready; use fresh physical validation, actuator characterization and explicit domain-randomization assumptions before hardware RL. The smoke test checks loading and numerical execution, not model accuracy or transfer safety.
