# Explicit learned swing-up through the console

New release: `~/cartpole-v2-live/releases/id-20261021-policy-swingup`.
Parent: `id-20261021-policy-rail1mm`. No firmware or actor weights changed.
The three `*-rail1mm` actor artifacts remain byte-for-byte unchanged and retain
exact runtime validation. No serial device was opened by this deployment.

Stop and quit the old console. In a normal Jetson terminal:

```sh
cd ~/cartpole-v2-live/releases/id-20261021-policy-swingup
sudo prlimit --pid $$ --rtprio=10:10
.venv/bin/python scripts/jetson-control \
  --camera-service cartpole-vision.service \
  --camera-cpus 0-3 --control-cpus 4-5 -- \
  chrt --rr 10 .venv/bin/python -m cartpole_sdk.rig.policy_console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --rate 250 --keep-board-params
```

Keep the valid saved upright reference. If a counted home already exists, use
`rehome`; otherwise `home`. Wait for completion and a settled freely hanging
pole, with hands clear. Do not issue `hanging ideal`: that changes calibration.

```text
policy load training/candidates/combined-recovery-20261021-step000102400-rail1mm/actor.json
policy check swingup
policy swingup 25
```

This runs the learned actor for both swing-up and balance, with no native AUTO/BAL
fallback. Default swingup duration is 25 seconds, maximum 60. Ctrl-C stops and
returns to the console. At normal expiry the motor is stopped/disabled; issue
`rehome` explicitly, wait and settle before another attempt. `policy run 25`
continues to require an upright start. `policy shadow swingup 1` evaluates demands
while disabled, without predicting motion.

To compare the later checkpoint, after rehome/settling:

```text
policy load training/candidates/combined-recovery-20261021-step000460800-rail1mm/actor.json
policy check swingup
policy swingup 25
```

Start limits: |x| <= 0.015 m, |commanded velocity| <= 0.025 m/s, |angular rate|
<= 0.15 rad/s, no rail braking, and both raw and selected filtered angles within
0.35 rad (20 degrees) of down using circular distance. This window tolerates the
observed hanging/upright offset, but is not a calibration or robustness claim.
The saved upright reference is never overwritten. During execution there is no
host angle/rate cutoff. Firmware interlocks/braking, trained/live rail intersection,
native speed limits, 100 Hz control telemetry and 20 ms leases remain.

The existing 1 mm half-rail compatibility allowance is included. The operator
console restores its prior telemetry rate after the run. Policy logs are in
`runs/rig/`; look for `swingup_balance_boundary` and `neural_preflight` with the
actor hash, source hash, reference and actual limits.

Validation is recorded in `verification.json`, `local-verification.json` and
`jetson-verification.json`. Local replay uses the eight previously generated
25-second nominal hanging trajectories (20,000 actions), synthesizing raw guard
angle from the stored filtered angle. This checks admission/inference compatibility,
not a new simulation, independent sensor accuracy or physical success. Both
combined actors remain DEVELOPMENT_ONLY and not hardware-accepted.
