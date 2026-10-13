# From characterization to vision RL

## The sequence

1. **System identification.** Collect the passive/static/drive data in this package. Measure masses/COM, drive conversion and real motion. Keep recording metadata so changed hardware is not accidentally pooled with old data.
2. **Update and validate MuJoCo.** Set actual geometry, masses, inertia and friction, plus the firmware's velocity/acceleration/jerk limits, pulse conversion and command semantics. Predict separate recordings. Match both cart motion and pole response, not only free-decay period. Separate idealized actuator behavior from measured drive behavior.
3. **Train a state-based policy.** Begin with near-upright balance on clean simulated state, then swing-up. Inputs for one link include x, xdot, sin(theta), cos(theta), theta_dot and any maintained command state needed to make the dynamics Markov. The action must match the eventual hardware interface, e.g. requested cart acceleration or velocity target; the firmware enforces bounds. Evaluate fresh episodes, seeds and disturbances. No camera/CNN is needed for this initial stage.
4. **Build and validate visual state estimation.** Marker/keypoint tracking is a good first implementation. Calibrate image coordinates, find cart/pivot/joints/tip, derive angles and estimate velocities from timestamped history. One frame cannot uniquely determine angular velocity. Compare against the AS5600 for the first link. A CNN is optional: supervised image→keypoint/pose training replaces part of the estimator. Synthetic labels can help, but independent real labels and real-scene validation are still needed.
5. **Train/test for transfer, then deploy.** Reproduce measured camera/estimator errors, delays, frame timing/dropouts and motor behavior in the observation/action pipeline. Retrain or fine-tune the state policy with those effects and plausible parameter variation. Run shadow mode, then bounded near-upright trials, then swing-up. Policy weights are normally frozen on hardware: inference is fast evaluation, not continuing RL learning. Compare failures against a conventional encoder-based controller when useful.
6. **Add the second link, then the third.** Identify every link/joint and coupled dynamics, expand the visual state and retrain. Later MuJoCo hinge angles are relative to their parents; camera segment orientations usually are absolute. Convert consistently. The first-link AS5600 alone does not provide all later angles. More links increase occlusion/identity issues and introduce faster unstable modes. Do not reuse one-link physical parameters for every link.

Steps 3 and 4 can proceed in parallel after the basic model is credible. Your proposed steps “train on camera frames” and “implement the camera CNN” are not both required in a state-policy architecture. The state RL policy consumes the estimator's output. End-to-end pixel RL is a separate optional architecture, with a different training/data problem.

## Jetson + camera + Ethernet + Teensy

Proposed architecture:

    Camera → Jetson pose estimator → timestamped state/velocity estimator
           → frozen state policy → small Ethernet command packet
           → Teensy bounds/watchdogs + 1 kHz motion update → step ISR

Frames stay on the Jetson. Commands/telemetry cross Ethernet. Teensy generates individual step pulses; do not stream individual STEP edges across the network. A 7 µs pulse timer, 1 kHz motion update, policy inference rate and camera frame rate are four different quantities.

Teensy 4.1 provides 10/100 Mbit Ethernet. For scale, a 64-byte payload at 1000 packets/s is 0.512 Mbit/s before overhead. Even a three-link state plus one cart action is small. That bandwidth calculation does NOT prove packet latency, scheduling jitter, control stability or the motor's ability to follow. QNEthernet is an available lwIP-based Teensy implementation, but the network transport must be integrated and benchmarked separately.

At 80 camera frames/s, the interval is 12.5 ms. The actual observation age also includes exposure/readout, USB/driver buffering, queued frames, processing, inference, transport and actuator scheduling. Running the policy at 1 kHz on an 80 Hz pose stream does not create fresh visual measurements. Between frames, a model-based estimator can predict state forward; it must be trained/tested under its actual error distribution.

Measure on your exact Jetson/camera setup; the Jetson model and actual negotiated camera mode are not specified here. As a chosen starting engineering goal, aim for consistently low, roughly one-frame-scale observation-to-command delay for the single link, then determine acceptable limits by delay sweeps. This is NOT a universal 12.5 ms stability threshold or a claim about achieved hardware latency.

For perspective only, a pure 20 ms delay adds 72 degrees of phase lag at 10 Hz. That arithmetic shows why high packet throughput can coexist with poor control. The actual relevant unstable modes and bandwidths must come from your calibrated one-, two-, or three-link model; the ~0.71 s downward free-swing period alone does not specify a safe control rate.

| System | Assessment before timing measurements |
|---|---|
| Single pendulum | The proposed split is a reasonable architecture to test; benchmark and validate closed-loop behavior |
| Double pendulum | State/packet size remains small, but the estimator must identify both links and the controller tolerate faster coupled dynamics |
| Triple pendulum | Bandwidth still small; no defensible promise that an 80 fps camera and unspecified Jetson will be sufficient. Test delay, observability/occlusion and actuator authority first |

If camera timing is insufficient, options include lower latency capture, smaller processing images, better estimation, faster camera modes, or hybrid encoders/IMUs plus vision. Bigger policy networks or more training cannot recover information that arrives too late or is consistently occluded.

## Timing measurements to collect later

- Actual unique-frame rate, exposure and buffer depth; exposure timestamps where supported, not just frame arrival.
- Capture→pose and pose→state latency, tracking error, angular-velocity error, confidence/occlusion behavior.
- Policy inference wall time and GPU-completion time on the actual Jetson. Synchronize GPU timing appropriately; enqueue time alone can underreport completion time. Benchmark batch=1 in the full live pipeline, including preprocessing/transfers and thermal load.
- Network RTT plus command receipt→application timestamps; p50/p95/p99/max, loss, reordering and deadline violations under concurrent camera/logging load.
- End-to-end observable event→physical motion latency using a synchronized reference/LED or instrument. An MCU pulse event is not proof of cart motion. Unsynchronized host and MCU clocks cannot yield trustworthy one-way delay by direct subtraction.
- Delay sweeps in MuJoCo, e.g. 0, 5, 10, 15, 20, 30 and 50 ms, plus jitter/dropouts. These are test cases, not recommended operating delays. Measure success and rail excursions with realistic actions for each link count.

Use only fresh commands at the Teensy. A later UDP command protocol can include version/length, session/arm token, sequence number, time/expiry semantics, mode and bounded setpoint. Reject stale, duplicate, reordered, malformed and nonfinite commands; accept only an explicit motion mode. Sequence numbers alone cannot reveal that the most recent packet is already old in a queue; use clock alignment or a defined freshness/lease protocol. Define expiry and fallback independently in firmware. UDP avoids TCP head-of-line retransmission but does not guarantee delivery or timing. TCP may still be useful for setup/logging, separate from time-critical commands.

The 300 ms host lease in this slow characterization firmware is not a future high-speed balance safety specification. Recompute expiry, braking and travel margins for the deployed controller. Firmware must be able to stop on stale commands or local faults regardless of what the Jetson is doing. Driver disable does not instantly arrest physical motion, and step counts alone cannot detect every unsafe state.

## References

- PJRC Teensy 4.1 specifications: https://www.pjrc.com/store/teensy41.html
- QNEthernet implementation and API: https://github.com/ssilverman/QNEthernet
- NVIDIA TensorRT benchmarking/performance workflow: https://docs.nvidia.com/deeplearning/tensorrt/latest/performance/best-practices.html
- Stable-Baselines3 evaluation and RL practice: https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html

The architecture assessments and proposed experiment sequence above are engineering judgments for this project, not hardware performance guarantees from these sources.
