# Camera, balance-launcher and identification checks — October 21

The camera dashboard has its hanging angle reference again, and the deployed
balance launcher now mirrors encoder telemetry and reports the actual refused
acceleration. No actor weights, pinned runtime files, firmware, or simulation
parameters changed. No learned policy was powered during this session.

## Operator policy failure

Replay of the operator's latest log reproduces the first three accepted demands
and the fourth demand, **+3.120775815247386 m/s²**, exactly. That fourth demand
exceeded the explicit `--max-acceleration 3`; it was a valid `Acceleration`, not
an invalid type. ARM to failure was 32.764 ms. The requested 55-second run never
occurred. Earlier learned attempts also provide no sustained hardware balance.
See `operator-policy/report.md` and its portable replay command.

The actor's full declared action scale is ±25 m/s², matching its live executor
snapshot. To test that range, choose `--max-acceleration 25` explicitly. Raising
that cap removes this refusal cause; it does not establish learned balance or
swing-up. This actor remains balance-only and requires an upright start.

## Viewer and deployed fixes

- Missing angle: the live camera calibration initially had null angle and length
  references, despite detected geometry. A stopped, quiet hanging capture saved
  camera zero −0.018565937574014667 rad and marker spacing 155.96037524530877 px.
  This changes camera display calibration only. Cart metric scale remains unset.
- Camera crash: a fitted circle could put shaft-support samples outside its
  contour crop. The maintained detector now rejects those candidates before
  array access, including negative indices. Archived vision3 is unchanged.
- Encoder: the console and collectors already publish snapshots to UDP 3096;
  the balance CLI now does too, with `--no-vision-telemetry` opt-out. A stopped
  handoff check confirmed approximately 100 Hz and no mirror error. Data becomes
  stale when the serial owner closes; the viewer does not open serial itself.
- The purple comparison trace is display fusion, not an enabled SDK fused
  control policy. These experiments and the learned actor use the encoder.
- At the final check the camera service had zero restarts since deployment,
  valid camera angle/rate, no worker error and no remaining serial owner. The
  temporary tailnet archive-download listener was closed.

For normal viewing, from the Mac checkout:

```sh
python3 scripts/vision-view.py --host 100.126.59.18 --port 13090
```

Open http://127.0.0.1:13090. Stop an existing forward on 13090 first, or select a
free port. The original SSH route still works and permits calibration:

```sh
./scripts/vision-tunnel.sh rbafna@jetson 13091
```

Use http://127.0.0.1:13091 for that command. The tailnet viewing proxy uses separate
connections for video and telemetry, avoiding the observed SSH multiplexing
bottleneck. Camera numbers can still be blank for a rejected detection.

## Collected evidence and limits

All runs use saved encoder reference 330, home epoch 19, jerk 150, unchanged native
motion/switch limits, and the user's successful bw 8 setting for characterization.
The original bw 10 setting and all other original parameters were restored at the
end. No firmware reset/upload or encoder recalibration occurred.

| Recording | Result | Camera quality during motion |
|---|---|---|
| gentle-training-01 | Two complete ±10 mm pulse trials; third aborted on lease fault 1 | Complete trials had 84–94% valid excitation frames; failed campaign remains partial |
| coupled-training-01 | Native AUTO 25 s completed, returned home |93.8% valid frames; longest valid-geometry gap 160 ms exceeds 150 ms quality bound |
| coupled-validation-01 | Separate native AUTO 25 s completed, returned home |71.3% valid frames; longest gap 158 ms; insufficient coverage |
| gentle-training-02 | Four complete ±10/±20 mm pulses; stopped before fifth excitation on stale camera frame | Complete excitations 85.7–95.8% valid; whole campaign remains partial |

The first timeout occurred after the third pulse, with counted cart x=0 and tiny
hold demand. The last command write ended 20.466 ms after the preceding one; its
observed snapshot had already consumed part of the 20 ms anchored lease. Policy
computation was under 1 ms. This is timing evidence, not a mechanical stall. The
fault was explicitly cleared only after verifying disabled state, released
switches, reference 330 and home 19. The next pulse campaign, without concurrent
bulk transfers, completed four trials but stopped on camera freshness. This does
not prove transfer load was the timeout's cause. No lease or freshness limits
were increased, and there was no unattended fault-clear/retry loop.

The second campaign's camera failure occurred while waiting between trials;
no fifth excitation started. Both incomplete campaigns retain their original
`completed:false` and `stop_confirmed:false` results. Later independent checks
verified the board disabled and healthy; those checks do not rewrite the failed
campaigns as complete.

The native controller spent 22.53 s in BALANCE in the training run, but only 1.68 s
in the validation run. Those are mode occupancy totals, not a learned hold or
physical-angle acceptance result. The repeat returned to repeated swing-up and
rail recovery. Maximum counted travel was 0.191 m and 0.294 m respectively.

### What the frozen-model checks say

The existing passive pole law was evaluated without refitting: L=0.160303873 m,
viscous damping 0.006891975/s, Coulomb term 1.6268943 rad/s² and smoothing width
0.05 rad/s. These are 0.5-second predictions reinitialized from past encoder
samples and forced by recorded MCU commanded acceleration. They do not measure
physical cart acceleration or predict a whole episode autonomously.

For the six complete small pulses, raw firmware-reference RMS is 0.112–0.142 rad;
using each trial's preceding hanging reading as a phase sensitivity reduces it
to 0.010–0.036 rad. Only the two 20 mm pulse trials pass the existing excitation
and forecast checks under that sensitivity. This is useful local-down evidence,
not a globally calibrated angle map. The native-run raw-reference RMS is 1.340 rad
(training) and 0.697 rad(validation), so that same model/input/angle combination
is not qualified for full swing and upright prediction. Smaller pulses cannot
validate those regions.

Camera/encoder diagnostic plots use source host-read and serial-receipt clocks
on the same Jetson without fitting a time lag or angle correction. Exposure and
serial delays are uncalibrated; dynamic disagreement includes those effects.
Camera branches are shifted by multiples of 2π for display only. The stopped
handoff comparison showed about 6.2° disagreement between hanging-based camera
zero and saved encoder upright. Low-rate samples in `analysis/summary.json`
include turning points and are not claimed to be physically stationary.

No new physical model was exported or installed. An independent ruler-based cart
scale, global angle references, qualified fast-motion tracking and reliable host
command timing remain open. Future training can explore bounded uncertainties,
but these data do not establish the missing physical quantities.

## Reproduce analysis

The sealed raw archive is `live/camera-id-20261021.tar.gz`, SHA256
`a4e5205f3ebb52704ae1dc290e63f045d51b90a242ead1c85118bba3e72b27c9`.
It contains the deployment backup/hashes, exact parameters, preflight calibration,
all raw encoder/camera streams and manifests, failed runs, and final handoff.
Use fresh output directories:

```sh
mkdir -p /tmp/cartpole-oct21-input
# Run from the repository root.
tar -xzf evidence/camera-id-20261021/live/camera-id-20261021.tar.gz \
  -C /tmp/cartpole-oct21-input
uv run --locked --extra id --extra plots python \
  evidence/camera-id-20261021/tools/analyze_campaigns.py \
  --input /tmp/cartpole-oct21-input/runs/camera-id-20261021 \
  --output runs/camera-oct21-review
```

This verifies all four manifests, performs collection reviews, plots calibrated
camera-versus-encoder observations and evaluates the frozen pole law. Partial
trials are explicitly excluded; completed trials from partial campaigns remain
labeled diagnostic. It never opens hardware or exports a model. Outputs include
`summary.json`, each run's `sensor-comparison.png`, and
`frozen-prediction/*-prediction.png`. The original campaign review's raw-overview
plot intentionally uses separate image and encoder frames; use the new
sensor-comparison plot for the camera-calibrated angle convention.

The other scripts in `tools/` preserve the exact one-off preflight, bw change,
diagnosed-fault clear and handoff operations. They contain fixed run identities
and refuse existing output directories. They are provenance, not general-purpose
fault-recovery commands. Use the maintained `scripts/system-id-campaign` for new
collection.

## Next independent measurement

The highest-value manual step is six ruler-measured cart positions with the
camera fixed. The existing guided collector stays motor-disabled:

```sh
# On the Jetson, from the id-20261020 release, with the console closed:
./scripts/system-id-campaign collect --suite cart-map \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --cart-restraint 'Positioned by hand against ruler referenced to rail midpoint' \
  --dataset-role training --run-label cart-map-001 \
  --output runs/id-cart-map-001
```

Enter actual measured cart-pivot coordinates at each prompt, not assumed step
positions or physical switch-to-switch separation. The cart's finite width can
make switch separation different from its travel. After manually moving a
motor-disabled cart, run a fresh full HOME before further powered tests; REHOME
cannot reconstruct lost physical position. See `docs/system-id-campaign.md` for
independently measured angle-map and near-upright friction measurements.

## Verification

Full software suite: 1787 passed, 7 skipped, 456 subtests passed. Parent's focused
recheck: 94 passed, 16 subtests passed. Independent code review found no blocker.
Actor file/content and 18 runtime pins were preserved. Deployment hashes and
handoff are in `verification.json` and `live/`. The original agent verification
is retained with its historical provenance in `operator-policy/verification.json`.
