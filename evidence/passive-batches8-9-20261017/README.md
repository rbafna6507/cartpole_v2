# Batches 8 and 9 — unchanged batch-6 candidate validation

**Decision: retain the frozen batch-6 coefficients for development training; these four validation recordings do not justify another global passive refit now.** They support the model across 47 releases, while leaving measurable phase, small-angle decay-tail and initialization errors. Prioritize observation timing/angle characterization and initialization, alongside the separate driven-cart qualification, before attempting a more complex passive fit. The result remains DEVELOPMENT_ONLY and does not establish physical-model or hardware approval.

Both recordings labeled `training` and both labeled `validation` are independent validation in this review. No coefficient, friction law, analysis method or acceptance gate changed. The batch-6 freeze remains SHA-256 `2874d85349664109404ea0066fb4037fec568f422cdbbc740f57a55790db1b59`. All four raw hashes are distinct and absent from its development hashes.

## All four recordings

RMS / P95 below are degrees. Continuous predictions use one 0.5 s initialization per free release, excluded from scoring, followed by no further measurements. Short predictions use 0.5 s forecast windows and causal history up to 0.2 s. Both declared continuous initialization histories are retained.

| Recording | Releases | Short RMS / P95 | Continuous, 0.5 s history | Continuous, 0.25 s history |
| --- | ---: | ---: | ---: | ---: |
| training8 | 12 | 2.409 / 4.960 | 2.851 / 5.742 | 5.953 / 13.304 |
| validation8 | 11 | 2.313 / 4.960 | 4.061 / 7.858 | 3.570 / 7.386 |
| training9 | 12 | 2.368 / 4.865 | 3.052 / 6.280 | 3.483 / 6.834 |
| validation9 | 12 | 2.332 / 4.971 | 3.187 / 6.100 | 3.737 / 6.955 |
| **Batch 8 pooled** | **23** | **2.363 / 4.962** | **3.495 / 6.855** | **4.936 / 8.791** |
| **Batch 9 pooled** | **24** | **2.350 / 4.925** | **3.120 / 6.218** | **3.612 / 6.896** |
| **All four pooled** | **47** | **2.356 / 4.940** | **3.312 / 6.528** | **4.324 / 7.648** |

All four pooled: 80,707 short-forecast samples and 79,006 continuous samples at 0.5 s history. All 47 releases pass the frozen short numeric and minimum-window coverage gates; none was skipped. The earlier viscous model gives 8.883 / 19.981 continuous error on exactly the same samples, versus 3.312 / 6.528 for the batch-6 candidate. The earlier batch-5 friction candidate gives 4.302 / 8.536.

Camera free-interval consistency passes 43/47 releases, and held-pose qualification passes 38/47. Failed screens remain in every aggregate. The final partial release of validation-9 still has 7.18° continuous RMS; its camera interval and held pose both fail their original agreement bounds. The model is therefore useful as a development simulator with residual uncertainty, while the measurement and driven-model qualifications remain unresolved.

Viewed all four model plots: phase accumulation is prominent in validation-8 release 6 and validation-9 release 12; several smaller releases have predicted tails that decay sooner than the measured residual motion. The batch-9 aggregate stays near batch 8 and does not show a progressive global loss of fit. These observations support keeping the current coefficients, not declaring the remaining error solved.

[Training-8 comparison](training8/model-comparison.png) · [Validation-8 comparison](validation8/model-comparison.png) · [Training-9 comparison](training9/model-comparison.png) · [Validation-9 comparison](validation9/model-comparison.png)

## Batch 8 results

All 23 observed releases are retained: 12 from training-8, including the final partial decay, and 11 from validation-8. Validation-8 ends during a new hand raise; there is no twelfth observed release before STOP. That raw setup interval is documented before its model scoring, rather than treated as a failed forecast.

RMS / P95 below are degrees. Continuous means one initialization per annotated free interval, with its first 0.5 s excluded from scoring and no later observations. It does not bridge the intervening handling. Short predictions are 0.5 s forecasts, initialized from up to 0.2 s of past observations (about 0.1 s at the first forecast). Initial-state samples are excluded from error. Every release retains the original minimum three-window rule and 0.08 rad RMS / 0.15 rad P95 numeric limits.

| Recording | Releases | Short RMS / P95 | Continuous, 0.5 s history | Continuous, 0.25 s history |
| --- | ---: | ---: | ---: | ---: |
| training8 | 12 | 2.409 / 4.960 | 2.851 / 5.742 | 5.953 / 13.304 |
| validation8 | 11 | 2.313 / 4.960 | 4.061 / 7.858 | 3.570 / 7.386 |
| **Batch 8 pooled** | **23** | **2.363 / 4.962** | **3.495 / 6.855** | **4.936 / 8.791** |
| Prior completed batch 7, context | 11 | 2.283 / 4.772 | 2.629 / 5.024 | 2.712 / 5.403 |

The pooled batch-8 short score uses 40,357 samples; continuous 0.5 s uses 39,428. Pooled RMS and P95 are computed from individual residual samples, not averages of recording summaries. All 23 releases pass short numeric and coverage gates. The larger continuous residual in validation-8 is retained.

| Frozen comparison | Short RMS / P95 | Continuous, 0.5 s history |
| --- | ---: | ---: |
| weak_viscous, original | 7.655 / 12.384 | 8.826 / 20.047 |
| weak_viscous, history_rawq:0.20 | 2.514 / 5.010 | 8.826 / 20.047 |
| batch5_weak_coulomb, history_rawq:0.20 | 2.358 / 4.888 | 4.532 / 9.166 |
| weak_coulomb, history_rawq:0.20 | 2.363 / 4.962 | 3.495 / 6.855 |

## Measurement and release qualifications

Training-8 passes the free-interval camera screen for 11/12 releases. Its final partial release exceeds the original 5° RMS / 10° P95 camera/encoder disagreement bounds. Held poses 5, 6 and 12 fail camera/encoder agreement; these failures are not removed from prediction scoring. Validation-8 passes the free-interval camera screen for all 11 releases, but held pose 6 fails agreement (encoder −86.40°, camera −92.97°).

Apparent held encoder angles span about ±30°, ±60° and ±85–87°. The camera reaches approximately ±90–93° for the large poses. These are experiment-relative projected angles, not an absolute calibration. A passing fixed-pivot pixel screen does not prove physical cart stationarity or out-of-plane stability; hand-clear timing remains unverified.

The validation-8 release-6 continuous result changes from 7.07° RMS with 0.5 s history to 3.79° with 0.25 s history. Both declared histories remain reported. Its plot shows growing phase/amplitude disagreement during the decay; short forecasts remain substantially better. The held-pose sensor mismatch and initialization sensitivity prevent treating this as independent proof that the plant coefficients need refitting. The lower-amplitude releases also show residual tail differences. No favorable history or interval was substituted.

### Every observed release

Held encoder/camera angles are signed degrees relative to the collection hanging baseline. Continuous columns show RMS / P95; short columns also show RMS / P95. `C/P` means camera free-interval screen / held-pose screen. All listed short coverage and numeric gates pass.

| Recording/release | Held encoder / camera | Short | Continuous 0.5 s | Continuous 0.25 s | Forecast windows | C/P |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| training8/release-01 | 32.21 / 32.37 | 2.093 / 3.916 | 2.946 / 5.666 | 2.558 / 5.242 | 9 | pass/pass |
| training8/release-02 | -29.62 / -31.09 | 1.844 / 3.399 | 2.093 / 4.301 | 1.782 / 3.591 | 8 | pass/pass |
| training8/release-03 | 61.44 / 59.29 | 2.154 / 4.375 | 3.736 / 6.701 | 2.525 / 5.112 | 16 | pass/pass |
| training8/release-04 | -63.28 / -59.80 | 2.165 / 4.576 | 2.185 / 4.347 | 3.328 / 5.662 | 16 | pass/pass |
| training8/release-05 | 83.98 / 89.31 | 2.517 / 5.355 | 2.466 / 5.422 | 14.452 / 26.608 | 21 | pass/FAIL |
| training8/release-06 | -85.08 / -90.51 | 2.650 / 5.486 | 3.059 / 6.524 | 3.058 / 5.299 | 21 | pass/FAIL |
| training8/release-07 | 34.37 / 34.20 | 2.506 / 4.936 | 1.931 / 3.882 | 2.587 / 5.139 | 9 | pass/pass |
| training8/release-08 | -29.44 / -31.12 | 1.953 / 3.548 | 2.130 / 4.066 | 1.481 / 2.842 | 8 | pass/pass |
| training8/release-09 | 61.35 / 61.68 | 2.147 / 4.297 | 3.074 / 5.474 | 2.282 / 4.923 | 16 | pass/pass |
| training8/release-10 | -58.80 / -59.95 | 1.879 / 3.802 | 2.079 / 4.476 | 4.254 / 7.346 | 16 | pass/pass |
| training8/release-11 | 86.13 / 90.55 | 3.051 / 6.493 | 2.607 / 4.914 | 4.612 / 8.272 | 21 | pass/pass |
| training8/release-12 | -86.75 / -92.51 | 3.296 / 7.446 | 5.783 / 10.768 | 3.416 / 6.105 | 5 | FAIL/FAIL |
| validation8/release-01 | 32.43 / 31.94 | 1.993 / 4.037 | 2.764 / 4.790 | 1.833 / 3.785 | 9 | pass/pass |
| validation8/release-02 | -29.09 / -31.94 | 2.081 / 4.220 | 2.099 / 3.631 | 2.355 / 4.126 | 7 | pass/pass |
| validation8/release-03 | 58.36 / 60.97 | 1.885 / 4.241 | 3.133 / 5.377 | 2.565 / 5.733 | 16 | pass/pass |
| validation8/release-04 | -58.54 / -60.79 | 2.462 / 5.211 | 2.550 / 4.379 | 4.775 / 7.990 | 15 | pass/pass |
| validation8/release-05 | 85.43 / 90.18 | 2.839 / 5.968 | 4.436 / 7.780 | 5.494 / 10.947 | 21 | pass/pass |
| validation8/release-06 | -86.40 / -92.97 | 2.360 / 5.221 | 7.067 / 13.623 | 3.790 / 7.941 | 22 | pass/FAIL |
| validation8/release-07 | 32.96 / 32.04 | 2.010 / 3.778 | 1.721 / 3.601 | 1.781 / 3.615 | 9 | pass/pass |
| validation8/release-08 | -29.71 / -32.36 | 2.048 / 3.949 | 1.750 / 3.077 | 2.320 / 4.009 | 8 | pass/pass |
| validation8/release-09 | 59.59 / 60.90 | 1.845 / 3.704 | 3.849 / 6.521 | 2.719 / 4.623 | 15 | pass/pass |
| validation8/release-10 | -58.80 / -60.96 | 2.443 / 5.124 | 2.573 / 4.761 | 3.081 / 5.300 | 15 | pass/pass |
| validation8/release-11 | 86.40 / 90.88 | 2.489 / 5.643 | 4.195 / 7.347 | 3.214 / 5.843 | 20 | pass/pass |

## Preserved sources

All four collections completed with successful STOP and zero logger drops. Four source files per recording are preserved unchanged: raw Rig JSONL, vision NDJSON, completion report and vision report. Remote hashes were recomputed before and after read-only streaming transfer, then every archive member and extracted copy was checked locally. No remote file, hardware connection, firmware, reference or service was changed.

| Recording | Board session | Raw SHA-256 |
| --- | --- | --- |
| training8 | 2954534650 | `7cc5112f451dd10489bf48b8f3326030f54936ce15ed2f843d71ec01a0c56a21` |
| validation8 | 2678669349 | `4f5aa90a2017e73815a4616e17067f208dd9b257f1da493830e609819a0a116e` |

All four raw hashes differ from each other and from every development hash in the frozen candidate. Directory and protocol labels are preserved in the manifests, but do not determine their role in this investigation. All four batch-8/9 recordings were used exclusively for validation; no refit is authorized by this evidence.

## Evidence

- `batch8-summary.json` contains exact pooled metrics, every release, all quality reasons, both histories and source hashes.
- Each recording subdirectory contains `original.tar.xz`, `manifest.json`, raw plots, frozen `annotations.json`, the full `model-check/report.json.gz`, summary and model comparison plot.
- `freeze-verification.json` preserves the frozen candidate and method hashes.
- `tools/acquire_completed.py` refuses incomplete, unsuccessful-STOP, dropped-record or failed-camera collections. It uses low-priority single-thread xz, with no remote temporary files.
- `tools/summarize.py` reconstructs short forecast residuals only from saved frozen initial states and verifies every original RMS/P95 before pooling.

No model is accepted or exported by these checks. The candidate remains DEVELOPMENT_ONLY.


## Batch 9 release details

Both batch-9 recordings contain 12 observed releases, including a final partial decay in each. Their original archives and local copies were verified before analysis. Both annotation files were frozen before either batch-9 evaluation began.

Training-9 fails the free-interval camera screen on releases 11 and 12, and held-pose agreement on releases 6 and 12. Validation-9 fails the free-interval camera screen on release 12; held-pose agreement fails on releases 6 and 12, and release 7 is not stationary within the original pose-variability bound. All failures remain scored.

| Recording/release | Held encoder / camera | Short | Continuous 0.5 s | Continuous 0.25 s | Forecast windows | C/P |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| training9/release-01 | 31.29 / 30.94 | 2.089 / 4.069 | 2.613 / 4.590 | 3.163 / 5.811 | 8 | pass/pass |
| training9/release-02 | -29.62 / -31.77 | 2.143 / 3.848 | 1.855 / 3.353 | 2.568 / 4.299 | 7 | pass/pass |
| training9/release-03 | 59.85 / 61.73 | 1.907 / 4.006 | 3.961 / 6.864 | 2.434 / 5.459 | 16 | pass/pass |
| training9/release-04 | -58.89 / -60.79 | 2.356 / 5.036 | 2.524 / 4.521 | 3.656 / 6.325 | 16 | pass/pass |
| training9/release-05 | 86.84 / 91.41 | 2.457 / 5.302 | 2.438 / 5.207 | 5.125 / 9.116 | 21 | pass/pass |
| training9/release-06 | -87.28 / -93.50 | 2.497 / 4.867 | 4.531 / 9.265 | 3.675 / 6.182 | 21 | pass/FAIL |
| training9/release-07 | 35.42 / 35.22 | 2.017 / 4.123 | 2.514 / 4.475 | 2.672 / 5.197 | 9 | pass/pass |
| training9/release-08 | -29.44 / -31.73 | 1.889 / 4.076 | 1.561 / 3.080 | 2.279 / 4.197 | 8 | pass/pass |
| training9/release-09 | 58.80 / 60.51 | 1.972 / 4.422 | 3.780 / 6.293 | 2.350 / 4.397 | 15 | pass/pass |
| training9/release-10 | -59.15 / -61.45 | 2.325 / 4.888 | 2.239 / 4.018 | 4.676 / 7.815 | 15 | pass/pass |
| training9/release-11 | 89.82 / 94.13 | 2.820 / 6.009 | 2.191 / 5.119 | 2.456 / 4.438 | 20 | FAIL/pass |
| training9/release-12 | -83.23 / -89.51 | 3.670 / 8.409 | 2.988 / 6.848 | 3.060 / 5.538 | 5 | FAIL/FAIL |
| validation9/release-01 | 35.16 / 34.53 | 2.016 / 4.449 | 2.451 / 4.573 | 2.928 / 5.267 | 8 | pass/pass |
| validation9/release-02 | -28.65 / -31.34 | 1.895 / 4.152 | 1.678 / 2.927 | 2.179 / 3.843 | 8 | pass/pass |
| validation9/release-03 | 58.62 / 61.10 | 1.895 / 4.393 | 3.846 / 6.474 | 3.916 / 6.725 | 15 | pass/pass |
| validation9/release-04 | -59.85 / -62.53 | 2.211 / 4.864 | 1.989 / 3.331 | 4.269 / 7.388 | 15 | pass/pass |
| validation9/release-05 | 88.33 / 92.22 | 2.373 / 5.105 | 2.776 / 4.869 | 3.130 / 5.639 | 21 | pass/pass |
| validation9/release-06 | -84.64 / -91.22 | 2.736 / 5.739 | 3.354 / 7.585 | 2.889 / 4.802 | 20 | pass/FAIL |
| validation9/release-07 | 32.34 / 32.05 | 2.081 / 4.440 | 2.237 / 4.434 | 2.471 / 4.495 | 8 | pass/FAIL |
| validation9/release-08 | -29.36 / -32.00 | 2.141 / 4.342 | 1.537 / 2.968 | 1.625 / 3.183 | 7 | pass/pass |
| validation9/release-09 | 59.59 / 62.05 | 1.867 / 4.218 | 3.448 / 5.888 | 3.638 / 6.259 | 15 | pass/pass |
| validation9/release-10 | -59.15 / -61.79 | 2.314 / 4.973 | 1.815 / 3.662 | 2.378 / 4.203 | 16 | pass/pass |
| validation9/release-11 | 85.34 / 89.96 | 2.517 / 5.653 | 2.727 / 4.694 | 6.274 / 12.034 | 20 | pass/pass |
| validation9/release-12 | -83.94 / -90.03 | 3.211 / 6.539 | 7.175 / 12.346 | 4.048 / 6.902 | 9 | FAIL/FAIL |

| Recording | Board session | Raw SHA-256 |
| --- | --- | --- |
| training9 | 781240700 | `58e9f55951b85846e40b280db86de19f2bb5477dcf8fd0d021203ced610fa384` |
| validation9 | 3754275768 | `6c3f08f84b3cbb3053a035ae64d3f5b8a8d9ce9bcd099dac6f99a693216d4cfe` |

## Reproduce and verify

`commands.json` records acquisition, raw-preview, onset-zoom, frozen-evaluation, plot and pooling arguments for every recording. Use new output/cache paths when rerunning; scripts refuse overwrite. The exact remote archive command and per-file hashes are in each `manifest.json`. Training-8 used xz level 1; subsequent transfers used level 6 to reduce transfer size. Both use low priority and one compression thread.

The original frozen evaluator is reused from `../system-id-model-review-20261017/tools/evaluate.py`; none of its method-hashed scripts changed. `tools/summarize.py` rebuilds short residuals from saved initial states, verifies every original RMS/P95, then pools individual samples. It never fits coefficients or initial states. `batch8-summary.json` was preserved before batch 9 and correctly retains `batch9_scored: false`; `batch9-summary.json` and `all4-summary.json` correctly report true.

Final offline verification checked 16 archived original files and 16 extracted copies, four independent raw hashes, all 47 frozen annotations against evaluation identities, unchanged model/method hashes, no skipped intervals, both histories, equal comparison sample counts, pooled sample counts and helper syntax. See `verification.json`. All four raw, onset and model-comparison plots were visually inspected. Evaluator stdout logs are preserved byte-for-byte as gzip.

From the repository root, repeat the verification into a new file:

```bash
python3 evidence/passive-batches8-9-20261017/tools/verify_evidence.py \
  --output /tmp/passive-batches8-9-verification.json
```

On another checkout without the ignored extracted `runs` copies, add `--archives-only` to verify the committed originals and analysis bindings. The output explicitly records that local copies were not checked. Both acquisition and verification find `xz` on PATH; `--xz /path/to/xz` overrides it.

No hardware command, serial access, service restart, source correction or refit occurred. The source archives and annotations remain unchanged after scoring.
