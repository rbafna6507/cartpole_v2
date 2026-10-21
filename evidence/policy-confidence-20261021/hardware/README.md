# Short balance hardware iterations

These scripts run the existing console policy implementation and retain SDK JSONL traces. An operation completing is not evidence of successful balance. All actors remain development-only.

The first candidate is `training/candidates/balance-20261021-confidence/actor.json`: optimizer seed 47, final 20,480-decision balance checkpoint. It completed eight uninterrupted 60-second nominal simulation trials. Four thousand SDK emission comparisons passed with maximum discrepancy 4.12e-6 m/s²; NumPy replay matched the SDK to 1.78e-14 m/s². A separate upstream encoder-bias test failed centering at every tested nonzero offset, starting at ±0.25°. See `balance47-encoder-sensitivity/report.json`; this is a material unresolved transfer risk.

The live release is `/home/rbafna/cartpole-v2-live/releases/id-20261021-policy-console`. `confidence_trial.py` is the staged copy of `trial.py`; its source digest is saved in each report. The verified CPU partition launcher restores camera thread affinities after each invocation.

With the rig clear, the console closed, and a previously confirmed upright reference, a one-second trial is:

```sh
cd ~/cartpole-v2-live/releases/id-20261021-policy-console
.venv/bin/python scripts/jetson-control \
  --camera-service cartpole-vision.service --camera-cpus 0-3 --control-cpus 4-5 -- \
  .venv/bin/python confidence_trial.py run \
  --actor training/candidates/balance-20261021-confidence/actor.json \
  --reference REFERENCE_COUNT --duration 1 \
  --out runs/policy-confidence-live-20261021/UNIQUE_RUN_NAME
```

Replace the reference with the count actually saved from the confirmed upright pose. The runner refuses a different saved count. It never calibrates, homes, clears a fault, or writes parameters implicitly.

Use `shadow` in place of `run` for disabled inference, and `inspect` for stopped state/parameter capture. `upright` explicitly captures the current stationary pole as upright while disabled; only invoke it when that pose has been established. `rehome` explicitly returns to the existing counted home. Keep hands clear during motion and leave the policy's existing firmware protections enabled. No firmware upload or reset is part of this procedure.

The initial preparation used `prepare_home.py`: it recorded a pre-existing encoder fault, checked that magnetic/configuration health had recovered with no further I2C errors, then cleared that isolated latch and ran physical two-switch homing. This historical script pins reference 533 and one output directory; do not rerun it blindly after calibration.

Before each trial, record the camera sensing stream separately on the Jetson when available. Match its source-host timestamps to the trial's own telemetry; embedded encoder packets can belong to an older SDK session. Counted cart position and commanded velocity are not independent physical measurements. The encoder reference, camera geometry, commanded/executed acceleration, timing, and faults must be assessed separately.

## Longer trials and timing diagnosis

The user requested longer balance tests. `trial-timed-v2.py` supports up to 60 seconds through the actual console implementation and requires the sibling `timing_instrumentation.py`. It optionally accepts `--no-mirror --no-logger` to retain records in memory and serialize them after STOP and close. Those toggles did not establish a reliable timing fix. Preserve existing source versions and use unique output directories.

The original candidate held the encoder within about ±1° for 7.22 seconds before lease expiry; it travelled ±11–12 cm from counted center. See `balance47-run10-gil1-analysis` and `balance47-run10-camera04`. That hold did not repeat in the later 25-second run after a fresh upright reference: measured angle crossed 5° at 0.05 s despite no timing fault. No reliable hardware balance or centered balance is claimed. See `startup-comparison` and `balance47-run25-camera06`.

`zero-timing-v2.py` performs a scheduling experiment, deliberately bypassing the initial upright-pose gate and emitting zero acceleration. It retains sensor/cadence, rail/speed, request and firmware checks. Its frozen comment mentioning a runtime reference check is overly broad: it supplies no reference-guard callback. It is not a full console-admission-equivalence test. The ordinary trial path does retain the console reference checks.

A detailed zero-command trace showed a completed healthy-state notification followed by 10.40 ms before the main thread resumed; inference and final serial write were short. User-space timing alone does not distinguish all OS, GIL and futex causes. `analyze-detailed-timing.py` saves that timeline. Logging/mirror removal, a 1 ms GIL switch interval, and CPU affinity alone did not consistently prevent expiry.

A temporary higher-priority comparison requires administrator assistance on this Jetson (`ulimit -r` is zero). The scoped method is to open a dedicated test shell, verify its PID/user/command, then have an administrator run `sudo prlimit --pid VERIFIED_SHELL_PID --rtprio=10:10`. From that shell only, launch the ordinary launcher and put `chrt --rr 10` after its `--` separator: `.venv/bin/python scripts/jetson-control --camera-service cartpole-vision.service --camera-cpus 0-3 --control-cpus 4-5 -- chrt --rr 10 .venv/bin/python zero-timing-v2.py ...`. This elevates the controller child, not the launcher that periodically scans `/proc`. Applying priority to the entire launcher produced a distinct delayed-telemetry failure; the child-only 60-second memory-recording test completed successfully. Check every reported thread's scheduling policy and priority; the grant alone does not change policy. Wait for STOP, close and child-process exit, then close the shell. No persistent limits file, CPU governor, lease, or firmware change is part of this experiment. Do not reuse a PID from an older session.

The controller-only priority test also passed 30 seconds with normal logging/mirroring, followed by the original actor’s full 25-second operation with no timing fault. The actor lost balance during that run; operation duration is not hold duration. The temporary shell was closed afterward. Final state: rehomed, disabled, healthy, saved upright reference 553, I2C errors 13. See the consolidated `../EXPERIMENTS.md` for outcomes and the next identification target.
