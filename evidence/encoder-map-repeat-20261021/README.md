# Repeat encoder mapping and independent validation — 2026-10-21

**No calibration was accepted or applied.** The rotation data now cover the whole circle in both directions, but the fitted periodic curve does not explain independent stationary upright readings or the earlier successful balance runs. Keep reference **533**, bandwidth **8**, and jerk **150 m/s³** as the existing working baseline. This campaign did not change gains, reference, firmware, simulation, Gym, or a learned actor, and did not enable the motor.

## What the repeat established

The first direction of passive rotation03 was used to fit a cyclic camera-minus-encoder residual. Orders 0–6 were compared with six interleaved angular-bin folds using only that direction. Each fit balances angular bins; the held-fold CV score pools frames and is frame-weighted. Order 4 was selected; the opposite direction and later recordings were not used to select coefficients or order. Both directions cover all 12 angular bins. The model is mathematically monotonic on the sampled grid, but that does not establish physical validity.

| Check | Frozen curve result | Interpretation |
|---|---:|---|
| Training-direction angular cross-validation | 0.549° RMS | Model-order selection only |
| Opposite slow rotation | 0.817° RMS; 1.467° absolute p95 | Good descriptive fit to the manual sweep |
| Independent stationary upright04 | 4.542° RMS across qualified windows | Fails the 0.5° agreement target |
| Contact05 qualified quiet windows | 4.418° RMS | Upright failure persists |
| Earlier successful AUTO runs, capture + 2 s onward | 4.631° / 4.650° RMS | Earlier upright-anchored raw encoder gave 0.418° / 0.404° |
| Intentional free decays06 | 6.149° / 6.342° RMS | Lower than raw disagreement, but still poor and strongly timing-sensitive |

These rows use different scopes and must not be interpreted as directly comparable controller scores. Camera angles are raw `atan2(bob_x-pivot_x, pivot_y-bob_y)` image geometry, not camera-calibrated theta, fused estimates, or certified gravity-relative angles. The historical AUTO camera frame differs slightly; that comparison establishes failed transfer, not an encoder-only mechanism.

See [the validation plot](analysis/calibration-validation.png), [free-fall observations](analysis/freefall-observations.png), and [the full report](analysis/report.json). The report retains `calibration_accepted: false` and `hardware_accepted: false`. No SDK-loadable approved calibration was exported.

## Touch test and free falls

In contact05, the initial-to-final encoder change was −9 counts = −0.7910°. The camera observed −0.7901° of pose change. The net difference is negligible compared with these sensors' resolution. Sustained quiet epochs differed by at most 0.213° after subtracting camera-visible pose change; a brief 1.29-second epoch differed by 0.527° and remains in the report. Exact contact/release event timestamps were not recorded, so this does not prove or exclude a load-dependent mechanism.

The end of rotation03 and the start of upright04 both read raw 2490 while hanging, with only a 0.032° camera-median difference. Those hanging windows fail the strict camera-stationarity criterion; their medians are diagnostic. There is no evidence of a sudden reference jump between those recordings. The slow sweep did not contain a qualified stationary upright pause.

For freefall06, the user reported an accidental initial drop followed by intentional releases 20–30° from upright on both sides. The accidental drop and assisted raising remain in the raw data but are excluded from the intentional-decay aggregates. The review selects onset from sustained angular motion and scores after an additional 80 ms; it does not claim a measured hand-release timestamp. The two scored windows are approximately 63.723–75.2 s and 88.015–99.6 s. Raw image geometry during the pre-release holds is used to assess pose, not the requested nominal angle.

The frozen −17 ms timing value is a proxy from an earlier run. Timing sensitivity affects fast free-fall errors substantially and cannot identify exposure delay independently. It cannot remove the prolonged stationary mismatch. Independent review retained timing sensitivity, geometry checks, missing-camera intervals, and native INFO versus reconstructed STATE counts under `review/`.

## Narrower hanging-to-upright conversion

Two observed pose pairs suggest a correction after the ideal half-turn:

```
upright_raw = (hanging_raw + 2048 + offset_counts) mod 4096
```

- Upright04: hanging 2490 → upright 548 implies **+106 counts (9.316°)**. The hanging camera window is not strictly qualified.
- Freefall06: upright 539 → hanging 2483 implies **+104 counts (9.141°)**. Both endpoint windows pass the camera quiet-pose filter.

Freezing the exploratory +106-count conversion from04 would predict 541 in06, versus the observed upright 539: **2 counts / 0.176°** count-only difference assuming an ideal half-turn. Accounting for the camera-observed pose separations gives exploratory excesses of 108.942 and 103.976 counts, a **0.436°** difference. The unstable04 hanging-camera window prevents treating either number as certified physical-angle accuracy. This is useful evidence, not an accepted reference conversion. The poses were natural resting positions, not independently fixed physical angles. There are only two pose pairs, not enough independent approach/session coverage or native window/stability evidence for the SDK's hanging-calibration acceptance checks. Multiple quiet fragments of one upright pose must not be counted as new calibration trials.

Do not use `hanging ideal` to overwrite the working upright reference on the assumption that the raw sensor spans exactly 2048 counts between these two resting poses. Do not apply the rejected periodic curve to compensate for this offset. They are different models with different evidence requirements.

## Recordings and provenance

All sessions remained motor-disabled and healthy. Reference533, home epoch27, I²C error count6, and recovery count0 remained unchanged. The firmware's raw-age field means time since the raw count changed, not sensor sample age. Counted cart x=0 is not independent physical cart-position metrology.

| Recording | Purpose / disposition |
|---|---|
| manual-map-after-tightening-02 | Initial attempt stopped on stale camera input before rotations. Retained as failed; not fitted. |
| manual-map-after-tightening-03 | Successful slow full rotations. 264 raw PNG snapshots at 2 Hz plus full-rate measurements. |
| manual-map-upright-verification-04 | Independent stationary upright. 248 PNG snapshots. |
| manual-map-upright-contact-05 | Light support / hands-off comparison. 307 PNG snapshots. |
| manual-map-freefall-06 | Accidental first drop and two requested free decays. 281 PNG snapshots. |

`raw/*metadata.tar.gz` preserves STATE/INFO logs, camera measurement streams, clock anchors, snapshot manifests, and acquisition reports. Exact collectors used for03–06 are in `collectors/`; their hashes match the acquisition reports. The original02 collector version was superseded before archival; its source hash remains in the raw report, but the exact source is not asserted to be retained. Snapshot HTTP request bounds are recorded, not exposure timestamps. Camera gaps are preserved and rejected offline; the powered-test recorder's freshness requirements were not weakened.

Full raw images remain on the Jetson under `/home/rbafna/cartpole-v2-live/releases/id-20261021-policy-console/runs/encoder-tightening-20261021/`. All264 rotation03 images also reside in the local ignored `runs/encoder-tightening-20261021/manual-map-after-tightening-03/images/` directory. Three representative stationary images are preserved in `raw/encoder-stationary-selected-images.tar.gz`; selected rotation images are in `images/`. Raw large-image archives are deliberately not committed to Git. Keep the full image directories when archiving the remote release.

The exact experiment collectors are provenance sources, with their original fixed output names/reference. They reject an existing output directory; they are not a newly generalized capture CLI. The reusable command added here is the offline analysis below. It opens no hardware.

## Reproduce the analysis locally

From the repository root, choose fresh output directories:

```bash
mkdir runs/encoder-map-repro
for archive in evidence/encoder-map-repeat-20261021/raw/*metadata.tar.gz; do
  tar -xzf "$archive" -C runs/encoder-map-repro
done

uv run --locked --extra id --extra plots python \
  evidence/encoder-map-repeat-20261021/analyze_repeat.py \
  --raw-root runs/encoder-map-repro/runs/encoder-tightening-20261021 \
  --output runs/encoder-map-validation-01
```

This regenerates the first-direction fit, frozen opposite-direction evaluation, independent stationary checks, source hashes and plots. It never refits on the independent checks. `fit_candidate.py` exposes the lower-level fit/check CLI and functions; its tests cover held-out independence, incomplete coverage, angular wrapping/derivatives, and stationary failure despite a perfect moving fit.

Independent review scripts under `review/` preserve the exact analysis used, including their original local paths. Their outputs and source hashes are retained for audit; the command above is the portable main reproduction path.

## What remains before a control correction

A single static angle-only curve has not been validated across manual movement, natural resting poses, and unassisted motion. Possible fixture/magnet loading, sensor mapping, camera geometry, and acquisition timing effects are not yet separated. The evidence does not identify a failed encoder component.

The next discriminating measurement is a sequence of reproducible stationary poses across the circle from both directions, with hands removed where mechanically supported, interleaved with repeated upright/hanging pairs. Record support state and true release events. Inspect shaft/magnet seating and relative motion before changing the fixture again; any physical change requires a new calibration dataset. A simple hanging offset needs independent repeated pairs with stable native windows; the full-angle model additionally needs unseen dynamic validation with characterized timing. Until then, use a direct upright calibration for native/learned-controller comparisons and keep this curve offline.
