# System identification and multimodal RL readiness, 2026-10-17

Development training can start with the retained smooth-friction plant and the
new encoder/vision/fused profiles. No trained policy is approved for the rig.
The [operator training instructions](../../docs/rl-training.md) include the
headless Colab commands and acceptance checks.

## Physical data collected

A read-only inspection found a stopped, healthy, homed rig with switch protection,
reference330, home_epoch15 and unchanged complete executor settings. Reserved
magnet status bits were present (`0x67`); its MD/MH/ML bits meet the firmware's
healthy mask. There were5 historical I2C errors and no new collection faults.
The camera showed the full rail and hanging pole, with raw geometry around79 FPS.
Its angle calibration was unset, so only raw pivot pixels were used here.

Five serial pulses ran: a+5 mm/0.8 s pilot, then two interleaved pairs of±10 mm/0.45 s.
Each used the existing100 Hz collector,20 ms leases,3m/s² raw test ceiling and3 s
cart feedback hold, with existing switch/position/speed/pole guards. All five
completed, confirmed STOP, dropped zero log records and clipped zero commands.
No firmware upload, reference reset, homing or gain change occurred. Final recorded
state is stopped and disabled near counted home.

| Condition | MuJoCo pole RMS | Reconstructed cart/count RMS | Optical shape RMS |
|---|---:|---:|---:|
| +5 mm pilot |1.750°|.032mm|.874px|
| +10 mm first |1.175°|.074mm|.336px|
| −10 mm first |1.371°|.137mm|.168px|
| +10 mm repeat |.807°|.078mm|.317px|
| −10 mm repeat |.827°|.129mm|.139px|

Pooled pole RMS is**1.250°**,P95**1.905°** over1,699 future samples. The first
0.1 s estimates initial pole rate; raw angle at that endpoint is retained, and all
later samples are scored without correction. The prior local encoder phase and
physical coefficients remain fixed. MuJoCo receives1 ms interval acceleration
reconstructed from100 Hz governor velocity endpoints. This offline reconstruction
uses recorded future inputs; it is conditional replay, not an autonomous forecast.

The first signed10 mm pair defines one pixel/count scale1077.97 px/m and15 ms receipt
proxy lag, frozen before scoring the repeats. The repeats agree closely; valid
camera coverage is93.2–100% across pulse windows, with missing frames retained.
The pilot has a larger~0.75 px return shift, and the pole ends at different small
rest angles. The smooth law does not reproduce that static sticking/offset
exactly. The fixed camera/pole geometry and step-derived scale do not identify an
independent physical ruler scale, motor force or actuator latency. Maximum new
commanded speed was.101m/s and governor acceleration2.144m/s²; earlier signed30 mm
runs covered~.206m/s. Neither establishes full-speed/full-rail transfer.

[Measured versus predicted figure](cart-analysis/cart-and-pendulum-replay.png)
· [Full report](cart-analysis/report.json)
· [Raw-source hashes](cart-data/sources.json)
· [Raw recordings](cart-data/raw-recordings.tar.xz)
· [Preflight view](cart-data/preflight-camera.png)

## Model selection

[Eight training-only refit/initializer combinations](../passive-refinement-20261017/README.md)
used existing batch6 and newly authorized training8/9 data. Validation-labelled
8/9 stayed out of fitting, but were already inspected historically and are
regression holdouts. The selected refit improved training10.5%, then regression
RMS only3.77% while P95 worsened. It failed the declared5% promotion threshold;
its paired-release uncertainty interval spans no improvement. The default
remains the previous frozen model. All release/camera/coverage failures are kept.

## Learning evidence and limits

Two actual offline PPO pilots ran on immutable source snapshots. Neither learned
sustained balance; neither was powered on the rig.

| Pilot | Decisions | Mean raw score before→after | Five-second holds |
|---|---:|---:|---:|
| Unscaled optimizer rewards |51,200|−1.074→−.699|0/4|
| Reward scale.01 |20,480|−1.074→−.198|0/4|

The scaled critic's explained variance reached.458 versus near zero in the first
pilot, supporting better optimizer conditioning. Unequal budgets do not establish
a controlled performance improvement. The scaled actor used almost the full
configured rail/speed envelope and is unsuitable for deployment. Development
scores use two disjoint seeds with both hanging/upright starts. A long run and
larger fresh evaluation are still required. Local throughput was295–300 steps/s.

[Comparison plot](ppo-pilots/scaled-20480/pilot-comparison.png), full manifests,
source, checkpoints and logs are preserved in each pilot's `complete-pilot.tar.xz`.
Later reviewed runtime fixes deliberately invalidate those historical actor pins
against current source. Preserve their matching source to reproduce them; use a
fresh training export for the current SDK.

## Reproduce the new cart analysis

This requires no hardware access. The script declares its scientific dependencies:

```sh
mkdir -p runs/rl-cart-replay-inputs
 tar -xJf evidence/rl-readiness-20261017/cart-data/raw-recordings.tar.xz \
   -C runs/rl-cart-replay-inputs
uv run --script evidence/rl-readiness-20261017/tools/analyze_cart.py \
  --repo . --raw-root runs/rl-cart-replay-inputs \
  --output runs/rl-cart-replay-review
```

To collect another allowed pulse on the Jetson with the console closed:

```sh
./scripts/system-id inspect --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --output runs/my-inspection
./scripts/system-id collect-pulse --execute \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --amplitude-mm 5 --pulse-seconds .8 --hold-seconds 3 \
  --dataset-role development --run-label my-cart-pilot --output runs/my-cart-pilot
```

Start small and inspect each result before changing conditions. The collector
requires a healthy stopped homed rig with quiet hanging pole and unchanged
calibration; it will not clear faults or home automatically. Preserve original
reports/raw files and camera evidence. The five-run comparison script uses the
explicit archived experiment names; collecting unrelated runs does not silently
add them to that frozen evaluation.


## Final software and stopped-hardware verification

The final suite passed **1,403 tests**, with 7 skips and 456 subtests. An
independent integration review was completed; its findings were addressed with
regression tests. The last shadow-duration boundary fix passed its targeted
regressions and the full suite.

The final Jetson shadow run completed **201 inference calls in 1.999 seconds**
using the matching current numeric actor and SDK source. Its trace contains zero
ARM commands and zero acceleration commands, all states remained disabled, both
STOP requests were acknowledged, and termination reported no error or dropped
log records. The firmware's cumulative dropped counter did not increase. This
verifies stopped inference and cleanup; it does not qualify powered control.
See [verification summary](verification/shadow-final.json),
[raw shadow trace](verification/shadow-final.tar.xz), and
[full test output](verification/full-suite-final.txt).

`final-colab-bundles/{encoder,vision,fused}` each contain a complete immutable
launch bundle with matching source, model inputs, recipe, bootstrap and hashes.
These preserve the exact source used for the final local checks. The operator
instructions show how to prepare a new bundle from the checkout. No Colab login,
VM allocation or cloud training was performed.
