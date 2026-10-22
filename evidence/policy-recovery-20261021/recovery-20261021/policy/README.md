# Recovered combined PPO actors

Both actors are exported and staged in separate new directories on the Jetson release
`/home/rbafna/cartpole-v2-live/releases/id-20261021-policy-console`.
Recommend **step 102,400** for initial development trials; retain **step 460,800**
(the latest backup, 45% of the planned 1,024,000 steps) for comparison and training recovery.
Neither actor is hardware-accepted.

| Checkpoint | Nominal holds, SB3 / NumPy | Hanging mean capture, SB3 / NumPy | Upright peak absolute x | SDK max action discrepancy |
| --- | --- | --- | --- | --- |
| 102,400 | 8/8 / 8/8 | 5.498 / 5.463 s | 0.09779 m | 3.44e-6 m/s² |
| 460,800 | 8/8 / 8/8 | 8.613 / 8.015 s | 0.10254 m | 3.21e-6 m/s² |

Each nominal evaluation has four hanging and four upright starts, each lasting 25 s;
all completed without faults. SDK parity compared 2,000 actual `NeuralPolicy.act`
actions per candidate and rejected no inputs (tolerance 1e-5 m/s²). Forty trace
hashes, checkpoint/weight hashes and every frozen protocol binding were verified.
The NumPy actor files exactly match the files used in numeric evaluation and SDK parity.

These are repeatedly inspected development seeds, with no stress or held-out
confirmation in this recovery. All hanging simulations rely on native rail braking
and reach approximately 0.29408 m absolute cart position. This is no physical
swing-up or recovery demonstration. Small numerical differences can accumulate
into different trajectories even when individual actions meet parity tolerance.

## Existing console

With valid existing homing/reference and a centered, nearly stationary **upright**
start, enter the recommended candidate in the connected policy console:

```text
policy load training/candidates/combined-recovery-20261021-step000102400/actor.json
policy status
policy check
policy run 5
```

For the latest backup, select its separate file and repeat the check/trial:

```text
policy load training/candidates/combined-recovery-20261021-step000460800/actor.json
policy check
policy run 5
```

After an operator-inspected short trial, the existing command accepts `policy run 25`.
To select the preserved working BAL actor again:

```text
policy load training/candidates/balance-recovery-20261021/actor.json
```

**There is no hanging-start policy option in this console.** Admission still
requires absolute x <= 0.015 m, commanded velocity <= 0.025 m/s, raw/filtered
angle <= 0.07 rad, angular rate <= 0.15 rad/s, and no rail braking. The existing
`hanging` command and `--hanging-model` option concern calibration.
After upright admission, the rig profile has no host angular cutoff: a fall
alone does not stop the actor. Rail/speed, freshness, 20 ms lease and firmware
protections remain active. The display's `balance-only` label describes this
unchanged console wrapper, not how the network was trained.

For a new console session, use the previously verified launcher:

```sh
cd ~/cartpole-v2-live/releases/id-20261021-policy-console
sudo prlimit --pid $$ --rtprio=10:10
.venv/bin/python scripts/jetson-control \
  --camera-service cartpole-vision.service \
  --camera-cpus 0-3 --control-cpus 4-5 -- \
  chrt --rr 10 .venv/bin/python -m cartpole_sdk.rig.policy_console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --rate 250 --keep-board-params
```

Use the existing connected console when present. The 100 Hz filtered observation
contract, 25 m/s² action scale and executor snapshot match the preserved BAL actor.
Both files passed the actual Jetson console and NumPy loaders; 23 runtime/launcher
source hashes match local. Staging did not select or run an actor. No serial,
motion, calibration, firmware, live parameter or service/process changes were made.

Full hashes and results: [assessment.json](assessment.json),
[102400 staging](jetson-staged-000102400.json),
[460800 staging](jetson-staged-000460800.json).
