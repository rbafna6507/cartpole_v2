# Post-tightening encoder and controller check — 2026-10-21

The user tightened the pendulum-to-encoder coupling and authorized autonomous verification. This campaign separates encoder reference error, angle-dependent sensor disagreement, and controller performance. No firmware was flashed or reset, and archived vision3 was untouched.

## What changed

- Initial live reference was **520**, not the previously reported 354. It was preserved for three baseline AUTO runs with bw 8 and jerk 150 m/s³.
- The user then presented their usual unassisted upright pose. Ten seconds of stopped readings were 533 ± 1 count. Camera tracking accepted 573/580 frames during that hold.
- Firmware captured and persisted **533** using its existing stable upright procedure. The 13-count correction is 1.1426°. This is a working natural-upright reference, not a plumb-line calibration.
- The camera was repositioned during upright setup. Old520 and new533 camera frames must not share a constant image-angle anchor.
- Current gains match every setting in `profiles/candidate-20261016-smoother-bw8.json`. A temporary bw6 comparison restores 8 afterward. Jerk stays 150; switch and motion protections stay enabled.

## Controller results

| Reference | Bandwidth | AUTO duration | First capture | Longest observed BAL interval |
|---|---:|---:|---:|---:|
| 520 | 8 | 15 s | none | 0 s |
| 520 | 8 | 25 s | 2.86 s | 0.608 s |
| 520 | 8 | 25 s | 4.50 s | 0.644 s |
| 533 | 8 | 25 s | 1.29 s | 23.704 s |
| 533 | 8 | 25 s | 3.60 s | 21.400 s |
| 533 | 6 | 25 s | none | 0 s |
| 533 | 8, fresh HOME | 25 s | 2.80 s | 0.112 s |

Durations count intervals with both endpoints observed in BAL, so are approximately 4 ms shorter than mode-transition timing. The two successful runs stayed in BAL through AUTO expiry. The last run failed to repeat that performance. Manual handling occurred before the bandwidth-6/final-bandwidth-8 trials; this is not a clean proof that bandwidth alone explains the difference. The separate upright-start BAL test held its full 10-second window.

Near upright in the first two successful runs, camera/encoder disagreement after the first two seconds of capture was 0.418°/0.404° RMS, with 95.8%/95.3% valid camera coverage. Counted cart means were +1.26/+0.98 cm; the final five-second means were +0.23/+1.90 cm. These runs did not show persistent rightward drift, but later capture reliability remains unresolved.

The repeat stopped upright measurement returned 538 instead of 533: +0.439°. The camera observed +0.284° of actual pose change, leaving +0.156° differential. Both measurements were steady and their pivot positions were close. This supports better local repeatability than treating every changed raw count as encoder drift. It does not validate the entire angular range: the same-view upright-to-hanging discrepancy remains about 8.2–8.5°, and the final trial had a camera-qualified hanging-rest differential of approximately −1.0°.

See `campaign-overview-complete/native-auto-overview.png`, `campaign-overview-complete/metrics.csv`, and `analysis-reference533-complete/report.json`. No gain update was promoted; the original bandwidth-8 profile and reference 533 remain the working baseline.

## Manual full-rotation check

The final 180-second recording remained healthy and motor-disabled throughout: 45,007 STATE samples, 714 in-recording INFO samples, and 10,010 camera records. The encoder traversed 372.66° unwrapped. Although 6,993 camera frames passed the filters overall, they were concentrated at upright and hanging: only 3 of 12 angular bins had support. Nine bins retained no camera measurements, and the longest accepted-camera gap was 12.23 seconds. Overall frame acceptance is therefore not a measure of calibration coverage.

Quiet upright/hanging comparisons reproduce a **7.91–8.08° difference between camera and encoder angle separations**. A constant zero adjustment cannot remove this difference. Neither sensor is certified as ground truth; these measurements do not establish whether the remaining cause is encoder mapping, mechanical play, or camera geometry. Opposite-direction angular coverage was inadequate, so no periodic correction was fitted or exported, and direction-dependent hysteresis remains unresolved.

Only tracking measurements were recorded, not raw video. Missing intermediate angles cannot be reconstructed afterward. Before another manual sweep, collection should preserve raw frames/video and verify tracking across the rotation; repeating the same capture unchanged would leave the same uncertainty. See `analysis-passive-map/report.json` and `analysis-passive-map/passive-map-diagnostics.png`.

## Recordings and exclusions

Raw archives preserve successful and failed attempts. The collector writes actual INFO/PARAM readbacks, 250 Hz STATE logs, independently recorded camera geometry, clock anchors and declared rest/AUTO phases. It records rest rather than performing a hanging recalibration. No hanging calibration was applied in this campaign.

- `preflight-01`, `stopped-01`: stopped diagnostics.
- `bw8-home-auto15-01`: timestamp argument collision before any motion; retained as failed.
- `bw8-home-auto15-02`, `bw8-auto25-01`, `bw8-auto25-02`: reference 520 baseline.
- `upright-check-01`: multiprocessing startup error before serial connection; retained as failed.
- `upright-check-02`: successful disabled upright measurement.
- `upright-calibration-533`: before/after native calibration readback.
- `ref533-bw8-bal10-01`: approximately 10 s continuous native BAL. The existing firmware reports fault 3 DURATION at a BAL deadline; only AUTO automatically returns home. The acquisition report therefore says unsuccessful completion. This is not an encoder fault or an aborted early balance hold. The known duration latch was cleared separately, then the cart rehomed.
- `ref533-after-bal-rehome`: stopped-only preflight rejected because SDK `healthy` includes absence of a fault. No motion occurred. `-02` checked the encoder-health bit, cleared the known DURATION latch through the SDK, and returned home.
- `ref533-bw8-auto25-01`, `-02`: corrected-reference comparisons.
- `ref533-bw6-auto25-01`: **exclude entirely**. User confirmed handling the pole; collector stopped before gain write or AUTO. This is not encoder-only drift and not a bandwidth6 performance trial.
- `ref533-bw6-auto25-02`: actual bandwidth6 comparison.
- `ref533-bw8-home-auto25-03`: return to bandwidth 8 with a fresh two-switch HOME after manual handling.
- `upright-check-03`: repeat natural upright; measurement only, with no reference write.
- `manual-map-after-tightening-01`: passive manual rotations, ending hanging; no motor motion or reference write.

The I²C error counter began at 6. Its absolute value is historical; inspect before/after differences. INFO `encoder_raw_age_us` means time since the raw count changed, **not sensor acquisition age**. STATE-derived raw counts and native INFO readings are reported separately. Counted cart position and commanded velocity are not independent physical cart metrology.

## Run another check on the Jetson

From the matching release, with camera service running and console closed:

```bash
./scripts/check-encoder-repeatability --expected-reference 533 --output runs/encoder-check-stopped-01
./scripts/check-encoder-repeatability --expected-reference 533 --output runs/encoder-check-auto-01 --execute --duration 25
```

The first command is stopped-only; the second runs one native AUTO trial and its native return-home. Add `--home` to seek both switches instead of returning to the already established counted home. Optional `--bw 6` temporarily changes only observer bandwidth and restores the original. Existing output directories are rejected; use a fresh name. The expected reference must match a known valid current upright calibration. Do not substitute a new number merely to bypass a mismatch.

`collect-v1.py`, `collect-v2.py` and `collect-v3.py` preserve exact versions used. Each later trial embeds its collector SHA. Current `collect.py` extends camera recording to 300 s to cover worst-case full homing plus settling; otherwise it retains the reviewed v3 behavior. Wrapper `./scripts/check-encoder-repeatability` uses uv with the hardware extra.

## Analyze the files

Extract raw archives into one working directory; they contain distinct `runs/encoder-tightening-20261021/` subdirectories. Keep excluded attempts for provenance. The analysis never commands hardware or applies a calibration/model.

```bash
uv run --locked --extra id --extra plots python evidence/encoder-tightening-20261021/analyze.py --input runs/encoder-tightening-20261021 --output runs/encoder-analysis-new --lag-from evidence/encoder-tightening-20261021/analysis-reference520/report.json
```

The frozen −17 ms alignment is a fitted proxy from the first reference 520 motion trial, not measured exposure latency. Data gaps remain gaps. Held-out residual fits are diagnostic comparisons, not approved encoder corrections. New 533 analysis must use its separate upright anchor and flag later unverified geometry changes. A single observed hanging angle cannot distinguish encoder error from a pole resting off vertical because of friction.

The simulation/Gym model and learned actor are unchanged by these native-controller checks. Do not export an encoder correction or refit dynamics from this campaign without the documented validation.

For the final reference-533 comparison and manual sweep analysis, after extracting the archives:

```bash
uv run --locked --extra id --extra plots python evidence/encoder-tightening-20261021/analyze_ref533.py \
  --input runs/encoder-tightening-20261021 \
  --upright runs/encoder-tightening-20261021/upright-check-02 \
  --repeat-upright runs/encoder-tightening-20261021/upright-check-03 \
  --lag-from evidence/encoder-tightening-20261021/analysis-reference520/report.json \
  --output runs/encoder-analysis-ref533-new

uv run --locked --extra id --extra plots python evidence/encoder-tightening-20261021/analyze_manual_map.py \
  --input runs/encoder-tightening-20261021/manual-map-after-tightening-01 \
  --lag-from evidence/encoder-tightening-20261021/analysis-reference520/report.json \
  --output runs/encoder-analysis-manual-new
```

## Final state and verification

`final-readback.json` records the final stopped board: mode 0, driver disabled, fault 0, home position x = 0, reference 533 saved, bandwidth 8, jerk 150 m/s³, both cart-switch interlocks enabled. The I²C error count remained 6, with no recoveries or new errors during this campaign. The final parameter values match `profiles/candidate-20261016-smoother-bw8.json`; the measured rail half-span is 0.3090375 m. The vision service remains running.

The five focused test files pass 27 tests; `verification.txt` preserves the command and result. Source hashes in the retained reports were checked against the input files. `SHA256SUMS` covers the retained evidence and executable collection wrapper; verify it from the repository root with `shasum -a 256 -c evidence/encoder-tightening-20261021/SHA256SUMS`.
