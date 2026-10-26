# Building a controller for this cartpole

The goal is one development path: understand the measurements, implement `reset/act`, test offline, submit an immutable artifact, inspect results, and request an approved physical trial. The local checkout provides a runnable starter, a shared versioned development simulation, numeric actor training/export, replay, and portal submission/collection. These starter, shared-profile worker, client and training changes have not been deployed to the rig. Hosted deployment and physical qualification remain separate operator work.

## What “raw encoder” means here

| Data | Available now | Meaning |
|---|---|---|
| Unfiltered pole angle | `Rig.observation()`, `source='magnetic'`, `quantity='angle'`, frame `encoder-zero` | Decoded encoder angle in radians, relative to saved upright, wrapped about upright. It has not passed through the host/control angle observer. It is not an unprocessed electrical measurement. |
| Filtered pole angle | `Rig.control_observation()`, `source='magnetic_filtered'` | Firmware observer estimate in radians. |
| Angular velocity | `source='magnetic'`, `quantity='angular_velocity'` | Filtered estimate in rad/s, not a separate rate sensor. |
| Native encoder integer | `ExecutorInfo.encoder_raw`, returned by INFO | 12-bit count, 0..4095. Diagnostic snapshot, not a count in every streaming state packet. `encoder_raw_age_us` is time since the value changed, not proof of a fresh read. |
| Cart position | `source='step'`, frame `cart-step-home` | Counted-step position in meters relative to home; not independently measured cart position. |
| Cart velocity / acceleration | Step channels | Commanded executor values; do not prove the motor physically tracked them. Acceleration is in the extended control observation. |
| Rail braking direction | Extended control observation | Executor governor state, not a separate sensor. |

The AS5600 and firmware conversion are documented in [the system README](../SYSTEM_README.md). Do not assume a linear full-angle calibration corrects the observed magnetic installation distortion: the fitted calibration was rejected. The saved upright reference, configured direction and encoder hardware filtering still affect the decoded value. “Unfiltered” here distinguishes the decoded angle from the additional firmware angle observer.

For controller authors who want their own filter, the unfiltered radian angle is available. For research requiring every native count and every acquisition, the current transport does **not** provide that guarantee. A versioned native-count stream and its simulation equivalent are future work, rather than a reason to repeatedly send INFO during control.

## Timing and transport

The firmware acquisition/control loop is 1 kHz. Serial telemetry supports 0, 100, 250, 500 or 1000 Hz; the convenient operator launcher uses 250 Hz. A telemetry rate is not a promise that every acquired sample reaches Python: firmware transmission and host processing use bounded paths, and callers must detect gaps.

SDK observations carry session and clock identifiers, board tick sequence, availability time and per-sample acquired/effective/received times, units, frame, method and validity. The ordinary rig observation uses the board acquisition snapshot as its timestamp proxy; its `received_ns` is **not** an independently synchronized host receipt. The underlying accepted `State` retains actual host monotonic receipt time and unwrapped board time separately. Do not subtract different clock domains. Use sequence gaps, source metadata and freshness validation; do not treat a repeated latest observation as a new measurement.

There is one serial owner. A submitted policy receives observations from the trusted worker; it never opens the serial device. Do not run a second `Rig` client beside the console to observe the same port.

The serial owner can publish a **read-only, latest-only** UDP mirror to `127.0.0.1:3096`. Its worker checks for a new snapshot every 5 ms, so it is not a lossless 250 Hz/1 kHz feed. Packets contain decoded angle/rate, timing provenance and `sdk_state`/`sdk_info`. A slow viewer loses display data without delaying control. The camera service already consumes this mirror; do not bind a competing consumer to its port.

The camera service fans out a bounded NDJSON sensing stream. With the camera service and serial-owner mirror running, inspect it on the Jetson:

```bash
curl --no-buffer 'http://127.0.0.1:3090/api/sensing-stream?max_hz=100'
```

From your laptop, forward the existing service:

```bash
ssh -N -L 3090:127.0.0.1:3090 rbafna@jetson
# In another terminal:
curl --no-buffer 'http://127.0.0.1:3090/api/sensing-stream?max_hz=100'
```

This is suitable for visualization, acquisition inspection and datasets with explicit gaps. It is not the physical controller's feedback transport. The camera API is separate from the submission portal and is not a public authenticated telemetry endpoint. Network viewers must never determine the control-loop timing.

The console writes bounded asynchronous JSONL rig records under `runs/rig` by default (`--log-dir` overrides it). These records are distinct from normalized SDK replay recordings. Check drop counters and provenance before analysis; do not claim losslessness. The portal can publish downloadable run bundles with observations, action requests, executor diagnostics and recording loss counters; see [run recording](RUN_RECORDING.md).

## Policy interface

An uploaded Python file defines `create_policy()`, returning an object with `reset(session)` and `act(observation)`. Reset clears estimator/recurrent state for each run. Act returns `Acceleration(value)` in m/s² or `None`. The return value is a request to the executor, not direct motor torque or velocity. `None` submits no renewal; it is neither a guaranteed immediate STOP nor permission to continue indefinitely. The MCU action lease expires independently.

Use exact channels and freshness checks, for example inside `act` on physical observations:

```python
from cartpole_sdk import Channel, select_channels

(theta,) = select_channels(
    observation,
    (Channel('pole', 'angle', 'magnetic', 'encoder-zero'),),
    now_ns=observation.available_ns,
    max_age_ns=20_000_000,
)
# theta.value is the unfiltered, upright-referenced radian angle.
```

The portal hardware bridge passes all seven available control channels: unfiltered and filtered magnetic angle, magnetic rate, step position/velocity, commanded acceleration and braking direction. The shared `RigCartpoleEnv` simulation profile supplies six channels with the selected filtered angle, estimated rate and executor feedback, all retaining `source='simulation'`. Simulation is never relabeled as magnetic sensing.

The starter uses `cartpole_sdk.developer.ObservationAdapter` with two declared channel maps: `simulation` and `magnetic-step`, and an explicit `angle_source='filtered'`. The first usable observation selects exactly one complete map. The map is pinned until reset; ambiguous, missing, stale, invalid, wrong-session or source-changing inputs are rejected. The example also checks observation sequence and 100 Hz cadence and latches faults until reset. `None` does not renew the action lease.

Numeric actors use their saved raw/filtered angle contract. The named nominal profile is filtered; a raw-angle actor needs a separately declared raw profile and is rejected by this runner. The local starter runner reads the same `actor.json` that the portal accepts; the standard numeric loader validates it and the adapter selects the appropriate source without editing weights. This supports the six-channel/21-feature actor contract, including commanded acceleration and braking direction. Local simulation does not prove that a physical execution profile, limits or inference deadline are acceptable.

The worker checks finite bounded acceleration, sequence/lease freshness and inference time. Existing defaults are 10 ms per inference, 1.5 s reset, 512 MiB address space, no network/devices/subprocesses, and a read-only filesystem. Hardware worker acceleration defaults to a conservative 0.25 m/s², versus 25 m/s² in generic simulation. This conservative setting is not enough to reproduce the successful recovery actor; approved execution profiles must bind and validate limits rather than allowing submissions to choose them.

## Develop, train, replay and submit the same artifact

Start from `examples/controller_starter/policy.py`. It implements `create_policy()`, `reset(session)` and `act(observation)` with bounded cart damping. It is a small editable integration example, not a swing-up controller. Local Python files are trusted code and execute in your process; uploaded code is isolated separately by the portal.

```bash
# Same source file, same named environment as the portal simulator:
uv run --locked --extra sim python examples/controller_starter/run.py simulate \
  --policy examples/controller_starter/policy.py --seconds 5 --output runs/starter-sim-001

# Replay exactly the observations that this controller received:
uv run --locked python examples/controller_starter/run.py replay \
  --policy examples/controller_starter/policy.py \
  --recording runs/starter-sim-001/observations.jsonl --output runs/starter-replay-001.jsonl
```

Simulation writes `observations.jsonl`, requested-action and executor-diagnostic `trace.jsonl` and `run.json` with the profile identity, effective configuration, initial truth, controller hash, seed and termination status. Output paths must be new. Replay does not change future observations: it tests causal processing and requested actions, not the resulting motion of a different controller. The older `examples/simulate_policy.py` remains an explicitly separate generic MuJoCo demonstration.

The unified profile is `rig-calibrated-20261021-v1`, loaded through `cartpole_sdk.sim.profiles`. Its packaged JSON and separately pinned content digest preserve the exact nominal experiment from `evidence/policy-recovery-20261021/combined-next/protocol.json`. Local starter simulation, portal simulation and the new training example consume this profile. Only episode duration changes at run time; training randomization is a separately recorded engineering coverage configuration.

The nominal model includes recorded rail/executor settings, passive length/friction coefficients, filtered 4096-count encoder sensing, 3 ms telemetry delay, 1 ms command delay, 100 Hz decisions, 1 kHz plant/governor integration and 20 ms leases. **“Calibrated” is a profile name, not full-system validation.** The profile retains `DEVELOPMENT_ONLY` and `hardware_accepted=false`: force authority, ideal acceleration tracking, transport assumptions, missed steps, backlash and global encoder accuracy remain limitations. No accepted global encoder correction or sim-to-real guarantee is claimed.

For a working training/export example:

```bash
# Short execution check: randomized training, frozen evaluation, numeric export.
uv run --locked --extra rl python examples/controller_starter/train.py \
  --output runs/controlled-smoke-001 --objective controlled-swing-v3 --steps 1024 --checkpoint-every 1024 --seconds 5

# Run and replay the exported numeric actor without changing its bytes:
uv run --locked --extra sim python examples/controller_starter/run.py simulate \
  --policy runs/controlled-smoke-001/actor.json --seconds 5 --output runs/actor-sim-001
uv run --locked python examples/controller_starter/run.py replay \
  --policy runs/controlled-smoke-001/actor.json \
  --recording runs/actor-sim-001/observations.jsonl --output runs/actor-replay-001.jsonl
```

The training entry point uses the existing PPO/numeric export machinery with the controlled-swing objective, reproducible engineering randomization, immutable checkpoints and held-out evaluation. It verifies numeric export parity and keeps hardware acceptance false. A 1024-step run checks execution only; it is not evidence of a competent controller. `--init-actor policies/working.json` starts from existing actor weights with a fresh optimizer. See the training command help for budgets and seeds, and the [command reference](../COMMAND_REFERENCE.md) for the older training workflows.

## Portal submission and recording

Use [portal setup and the developer client](portal.md) for invitations, credentials, local services, submission, waiting and collection. Submit `examples/controller_starter/policy.py` or the exported `actor.json` unchanged, selecting `simulation`. The Python client supports `.py`, validated `.zip` projects and numeric `.json` actors, an idempotency key, and an explicit recording option. Keep credentials in environment variables and use a new output path when collecting a recording.

After updating the API and worker together, submit that same starter artifact with the explicit CLI (credentials are read from the environment):

```bash
# Set CARTPOLE_PORTAL_URL and CARTPOLE_SUBMIT_TOKEN outside source control first.
uv run --locked python examples/controller_starter/submit.py \
  --artifact examples/controller_starter/policy.py --source simulation \
  --seconds 5 --key starter-sim-001 --recording detailed \
  --collect runs/starter-portal-001.zip --timeout 180
```

The command also accepts a ZIP project or numeric JSON as `--artifact`. Use the same `--key` and identical arguments after an uncertain response; it cannot create a second job. For physical requests, use `--source magnetic-step` and optionally `--reservation-id ID`; the command cannot grant operator approval.

Physical jobs require an operator-approved immutable request, an appropriate reservation/execution profile, and a prepared healthy rig. Simulation success and numeric parity do not grant physical approval. The trusted worker and MCU retain action bounds, deadlines, leases and safety authority. The downloadable portal bundle includes its own manifest and telemetry format; it is distinct from normalized local SDK `observations.jsonl`. Use [run recording](RUN_RECORDING.md) for its schema and loss accounting. Convert a collected bundle into normalized SDK replay and analysis tables offline:

```bash
uv run --locked python -m cartpole_sdk.portal.dataset runs/run.zip \
  --output runs/dataset-001 --sha256 <downloaded-bundle-sha256>
uv run --locked python examples/controller_starter/run.py replay \
  --policy examples/controller_starter/policy.py \
  --recording runs/dataset-001/policy-inputs.jsonl --output runs/collected-replay-001.jsonl
```

The converter separates actual policy-call inputs (`policy-inputs.jsonl`) from all recorded states (`observations.jsonl`). It preserves the source telemetry and exports `samples.csv`, `transitions.jsonl`, and `dataset.json`. Inspect validity, gaps, drops and action-pairing flags before using records for analysis or training. It does not invent rewards, terminal labels or physical action acknowledgments; `training_ready` remains false. Identical latest-state snapshots are deduplicated only in normalized replay, while the source telemetry retains them.

Video should use a replaceable source adapter separate from policy sensing. Replacing a camera must not silently change the controller's observation contract, calibration or clock alignment.

The selectable stream catalog and export commands are described in [DEVELOPER_STREAMS.md](DEVELOPER_STREAMS.md). The live service audit confirmed the deployed `/api/streams` catalog. Use that catalog and `/api/streams/ndjson` for supported selections; `--legacy-sensing` is only an explicit compatibility path. This deployed camera catalog is separate from the newer local starter and portal-worker changes described above.
