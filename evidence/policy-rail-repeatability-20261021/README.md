# Policy HOME repeatability fix

The user-reported trained rail half-length was 0.309074998 m; the new HOME reported 0.308962494 m, a difference of 0.112504 mm. The previous compatibility tolerance allowed only two counted microsteps (0.075 mm). This now accepts up to 1 mm of half-length difference, plus two float32 ULPs. It is an engineering development allowance, not a switch repeatability measurement.

The current measured-home physical cap remains strict, and policy motion stays inside the smaller trained/live hard rail boundary. For these readings the host boundary is 0.298962504 m from center. Other parameters, motor limits, switches, angle admission, reference and 20 ms leases are unchanged. No board setting or firmware was changed.

The new isolated Jetson release is `/home/rbafna/cartpole-v2-live/releases/id-20261021-policy-rail1mm`. The old release and its running processes were not modified. The three new `*-rail1mm` actors differ only in explicit runtime provenance and content hashes. Every other actor field matches its parent, and all 4,096 numeric output comparisons per actor were identical. The active Colab job continues to use its immutable source bundle.

## Run

In the old console, enter `stop`, then `quit`. In the Jetson shell:

```bash
cd ~/cartpole-v2-live/releases/id-20261021-policy-rail1mm
sudo prlimit --pid $$ --rtprio=10:10
.venv/bin/python scripts/jetson-control \
  --camera-service cartpole-vision.service \
  --camera-cpus 0-3 --control-cpus 4-5 -- \
  chrt --rr 10 .venv/bin/python -m cartpole_sdk.rig.policy_console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --rate 250 --keep-board-params
```

Use `rehome` if the saved home is valid or `home` if needed; wait for completion. With the pole upright and the rig clear:

```text
policy load training/candidates/combined-recovery-20261021-step000102400-rail1mm/actor.json
policy check
policy run 5
```

After the short comparison, prepare the upright start again before `policy run 55`.
The other available files are:

- `training/candidates/combined-recovery-20261021-step000460800-rail1mm/actor.json`
- `training/candidates/balance-recovery-20261021-rail1mm/actor.json`

These are runtime-compatible copies of the previously staged policies; the recovered PPO checkpoints still have no hardware acceptance claim. Their console entry still requires upright, centered admission. Restarting is necessary because an existing Python console keeps its imported code in memory. No Teensy reflash is required.

## Verification and reproducibility

- Exact regression reproduced before the change; it now passes console check and scripted run.
- 169 focused tests passed, including smaller/larger rail intersection and out-of-bound rejection.
- Full suite: 2,034 passed, 8 skipped, 460 subtests passed.
- Independent review exercised the actual helper: ±1 mm accepted, ±1.001 mm refused; physical-cap and legacy-firmware checks retained.
- `jetson-verification.json` records source pins, actor load/inference checks and an offline reproduction of the supplied readings on the Jetson. No serial connection was opened.
- `prepare_actors.py` generates explicit new actor copies and asserts that only the reviewed runtime source changed. It refuses to overwrite an existing destination.
- `stage_jetson.py` verifies the archive and stages a new release; it refuses an existing release. `verify_jetson.py` performs offline checks from that release with its own Python environment.
