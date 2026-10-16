# Offline jerk comparison

Run with explicit trial directories, in acquisition order:

```sh
python3 /tmp/cartpole-retune-20261015/jerk-analysis/analyze.py \
  /path/to/j150a /path/to/j300a /path/to/j300b /path/to/j150b \
  --firmware-manifest /tmp/cartpole-retune-20261015/jerk-release-manifest.json \
  --out /tmp/cartpole-retune-20261015/jerk-analysis/abba-results.json
```

Inputs are report.json, camera.json and rig-*.jsonl in each directory. The script
never opens serial/network interfaces or imports production SDK modules.

Native metrics preserve the earlier analysis: actual unwrapped board timestamps,
requested-duration window, duration-weighted residuals/jerk, bounded contiguous
mode3 episodes, rail modes, and native/camera quality. Jerk saturation is named
`near_cap` and uses95% of each trial's recorded jmax. Demand slew is compared with
that same cap; demand amplitude is compared with the recorded mode acceleration
limit. Residual threshold uses the trial's recorded catch_da. Full parameters are
preserved, with no implication that they have been tuned by this script.

Additional per-trial fields:

- `settled_hanging`: recorded settling result plus the actual final one-board-
  second window before motion, raw-count decoding residual, native angle/rate,
  healthy/disabled status, and current camera-relative hanging statistics.
- `home_return`: reported horizontal camera displacement, independently
  recomputed pixel XY displacement, full saved start/end pose metadata, and
  final counted position. Pixel displacement is not a calibrated distance.
- `firmware_provenance`: INFO version, initial/final reference, release name,
  firmware hex SHA256, manifest hash and association semantics. A per-trial
  firmware-manifest.json takes precedence over the CLI manifest. Version
  mismatches or ambiguous firmware artifacts fail explicitly. No manifest means
  hash=null; INFO itself does not provide a binary hash readback.

The supplied v5 release manifest associates the firmware version
executor-v5-calmodel with hex SHA256
baf8b176fcb026c9d76cdc8a75f27698845f4e34a98e3733810c4103765f6e26.
This is artifact provenance, not a new device attestation. The manifest's original
staged deployment field is retained as source data; it is not used to infer
current hardware state.

Camera working anchor remains-0.009445365634260372rad and descriptive effective
alignment19ms. No camera correction map is applied. Missing camera samples are
reported as unavailable without destroying native episode metrics. Firmware-
commanded acceleration remains distinct from physical acceleration.

Verification: five focused offline tests pass. They cover irregular board-time
episode durations, gaps splitting continuity, actual cap normalization150→300
using an explicitly synthetic parameter-only fixture, missing camera data,
firmware mismatch rejection, and unchanged native baseline results. CLI smoke
output is baseline-smoke.json; it is an old v4 data smoke test, not new v5 evidence.

## Candidate next gains comparison, after jerk ABBA

Do not change gain parameters during the jerk comparison. If higher jerk does
not consistently improve the repeated trials, retain the lower validated setting.
If it improves demand tracking but rail exits still dominate, the next useful
factor is cart-state feedback/approach behavior, rather than an acceleration cap
that the baseline never reached. A modest scale of the pc1/pc2 cart-pole pair can
be evaluated as one factor with pw,bw,approach settings held fixed; it changes
both position/velocity and angle/rate gains through the coupled pole-placement
formula, so it is not an isolated position gain. If high capture velocity is the
remaining discriminator, compare approach_v alone and retain the existing
capture/rail guards. Both changes can trade capture time against stopping margin.

For AUTO, `pw` selects feedback gains; `bal_pw` applies only to upright-only
balance. A bal_pw-only change cannot test AUTO capture/balance. Existing pw4.5
versus6 evidence did not establish a repeatable6 advantage, and lower bw20 did
not help repeatability. Avoid combining a gain increase with the first higher-
jerk comparison: demand chatter and changed stopping margin would be confounded.
No gain recommendation or performance claim is made before the new ABBA logs.
