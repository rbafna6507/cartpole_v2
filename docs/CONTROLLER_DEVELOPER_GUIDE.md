# Building a controller for this cartpole

The goal is one development path: understand the measurements, implement `reset/act`, test offline, submit an immutable artifact, inspect results, and request an approved physical trial. The SDK already implements the measurement/action contracts, replay, simulation, learned-policy export and isolated Python execution. The hosted portal and full training-to-submission path are still being built.

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

The console writes bounded asynchronous JSONL rig records under `runs/rig` by default (`--log-dir` overrides it). These records are distinct from normalized SDK replay recordings. Check drop counters and provenance before analysis; do not claim losslessness. The future portal should publish downloadable run records containing observations, requested and applied actions, timestamps, safety events, configuration identities and loss counters.

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

The portal hardware bridge now passes all seven available control channels: unfiltered and filtered magnetic angle, magnetic rate, step position/velocity, commanded acceleration and braking direction. The simulation bridge adds its two available governor channels to the ordinary four, with `source='simulation'` and frame `sim:upright+x`. This source distinction is deliberate: simulated ground truth is not magnetic sensing. A portable policy must explicitly support both contracts or use a documented adapter; it must not silently relabel source data.

Our trained recovery actor uses a richer filtered observation and executor feedback contract. The generic portal bridge is **not yet a drop-in runner for that actor**. Completing that parity is a prerequisite for accepting trained policies through the portal. The existing trusted console remains the supported execution path for `policies/working.json` and `policies/1m.json`.

The worker checks finite bounded acceleration, sequence/lease freshness and inference time. Existing defaults are 10 ms per inference, 1.5 s reset, 512 MiB address space, no network/devices/subprocesses, and a read-only filesystem. Hardware worker acceleration defaults to a conservative 0.25 m/s², versus 25 m/s² in generic simulation. This conservative setting is not enough to reproduce the successful recovery actor; approved execution profiles must bind and validate limits rather than allowing submissions to choose them.

## Develop and test

From the repository:

```bash
# Existing editable SDK-policy example; offline MuJoCo simulation:
uv run --locked --extra sim python examples/simulate_policy.py runs/my-controller-sim

# View the actual learned-policy training environment:
uv run --locked --extra sim cartpole-view-policy --actor policies/working.json

# Inspect supported replay input/options:
uv run --locked python examples/replay_policy.py --help
```

The illustrative simulation and replay examples use explicitly different source channels; neither is the tuned physical swing-up controller. Replay checks causal processing on recorded observations but cannot measure how a new controller would change the plant. Closed-loop simulation provides that experiment, with model and sensor limitations.

For training, checkpoint export, numeric parity and evaluation, use the [command cheat sheet](../COMMAND_CHEATSHEET.md#start-a-training-loop) and [full CLI reference](../COMMAND_REFERENCE.md). The `RigCartpoleEnv` learned-policy environment models sampled sensing, delay, actuator dynamics and the governor; the generic portal simulator is a separate executor wrapper. They must be offered as named, versioned environments, not described as interchangeable.

## Submit and approve: current first increment

Start the local portal using [portal setup](portal.md). Invited users receive a submission credential. Upload a UTF-8 Python file (current limit 64 KiB). Simulation jobs can be claimed immediately. Physical jobs enter `awaiting_approval`; an operator sees the job, artifact hash, duration and sensor selection and approves that exact immutable request. The UI asks for confirmation; the API independently checks the operator role and reviewed values. Approval does not move or prepare the rig. The existing trusted worker still requires a homed, healthy, stopped rig and an available lease.

The agreed hosted design uses Vercel UI, private artifact storage and a durable cloud queue, with outbound Jetson polling. Planned intake limits are 10 MiB uploaded, 50 MiB expanded and 256 files, fixed dependencies and validated numeric policy files. These planned limits are **not** implemented in the current source-only API. ZIP extraction, numeric-policy isolation, account invitation, cloud queue deployment, authenticated read-only telemetry/video and detailed downloadable results remain subsequent portal work.

Video should use a replaceable source adapter separate from policy sensing. Replacing a camera must not silently change the controller's observation contract, calibration or clock alignment.

The selectable stream catalog and export commands are described in [DEVELOPER_STREAMS.md](DEVELOPER_STREAMS.md). The currently running Jetson service supports explicit `--legacy-sensing` collection; new catalog endpoints require the updated camera-service version.
