# Passive refinement — training-only selection and frozen regression

**Recommendation: retain frozen baseline.** The training-selected candidate is `pooled_weak/frozen_rawq`. Model family remains smooth viscous plus dry friction. No production or training profile was edited, and no model was exported.

The candidate reduces primary regression RMS by 3.77%, below the fixed 5% criterion, while P95 increases from 7.138° to 7.204°. The descriptive paired-release interval for its RMS change spans zero. On validation8 it worsens releases 05 and 11 (4.44°→5.53° and 4.20°→5.08°) while improving release 06 (7.07°→5.08°); that release’s failed held-pose screen remains failed. This pattern does not establish whether residual error comes from sensing, initialization or plant dynamics.

Validation8 and validation9 were previously inspected. They are regression holdouts in this experiment, not a novel blind validation. Both original batch-6 recordings were already development; training8 and training9 were newly authorized for fitting. All 66 annotated releases across six recordings remain in the evidence.

Frozen parameters: effective length 0.160565923 m, viscous coefficient 0.036911493 /s, dry-friction coefficient 1.515359117 rad/s², local raw-angle phase -0.112852980 rad. This phase is an inference in the encoder coordinate, not global angle calibration.

## Paired results

RMS / P95 in degrees. Short forecasts use 0.5 s horizons and up to 0.2 s causal history. Continuous forecasts use one 0.25 s or 0.5 s history, exclude that history from errors, then receive no more measurements. The 0.5 s history is primary.

| Recording | Baseline short | Candidate short | Baseline cont .5 | Candidate cont .5 | Baseline cont .25 | Candidate cont .25 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| training6 | 2.421 / 5.013 | 2.420 / 4.981 | 3.717 / 8.424 | 3.193 / 6.398 | 3.076 / 6.797 | 2.622 / 5.257 |
| development6 | 2.204 / 4.716 | 2.189 / 4.672 | 3.906 / 8.657 | 3.357 / 6.638 | 8.369 / 22.813 | 7.272 / 18.992 |
| training8 | 2.409 / 4.960 | 2.396 / 4.927 | 2.851 / 5.742 | 2.798 / 5.697 | 5.953 / 13.304 | 5.394 / 11.108 |
| training9 | 2.368 / 4.865 | 2.359 / 4.854 | 3.052 / 6.280 | 2.759 / 5.452 | 3.483 / 6.834 | 3.914 / 7.923 |
| validation8 | 2.313 / 4.960 | 2.305 / 4.907 | 4.061 / 7.858 | 3.915 / 8.330 | 3.570 / 7.386 | 3.211 / 6.747 |
| validation9 | 2.332 / 4.971 | 2.317 / 4.942 | 3.187 / 6.100 | 3.058 / 6.225 | 3.737 / 6.955 | 3.692 / 7.111 |
| **Regression pooled** | 2.323 / 4.968 | 2.311 / 4.930 | 3.644 / 7.138 | 3.506 / 7.204 | 3.656 / 7.151 | 3.464 / 6.943 |
| **Latest four pooled** | 2.356 / 4.940 | 2.345 / 4.911 | 3.312 / 6.528 | 3.160 / 6.367 | 4.324 / 7.648 | 4.147 / 7.823 |

Pooled metrics use all individual prediction residuals, not averages of recording summaries. Both parameter and initializer candidates were evaluated on identical samples. Baseline latest-four scores reproduce the prior evidence within 1e-8 degree.

## Selection and regression decision

The method was written before fitting. Training selection used equal-recording mean continuous 0.5 s RMS, with fixed short, quarter-history, per-recording and gate-regression constraints. Candidate selection was frozen before this experiment loaded validation measurements. No alternative was chosen after regression scoring.

| Candidate | Training mean short RMS | Training mean cont .5 RMS | Training mean cont .25 RMS | Eligible |
| --- | ---: | ---: | ---: | :---: |
| baseline/frozen_rawq | 2.350 | 3.381 | 5.220 | False |
| baseline/robust_history | 2.368 | 3.184 | 4.206 | False |
| pooled_weak/frozen_rawq | 2.341 | 3.027 | 4.801 | True |
| pooled_weak/robust_history | 2.360 | 3.085 | 3.675 | False |
| robust_weak/frozen_rawq | 2.367 | 4.695 | 6.555 | False |
| robust_weak/robust_history | 2.388 | 4.034 | 6.244 | False |
| robust_trajectory/frozen_rawq | 2.369 | 3.448 | 5.537 | False |
| robust_trajectory/robust_history | 2.394 | 3.002 | 5.048 | False |

Frozen regression criteria:

- `primary_improves_at_least_5pct`: **False**.
- `each_recording_primary_within_10pct`: **True**.
- `short_within_5pct`: **True**.
- `quarter_history_within_5pct`: **True**.
- `preserves_short_gates`: **True**.

## Uncertainty and measurements

Regression camera screens pass 22/23; held poses pass 19/23. Across the latest four recordings these remain 43/47 and 38/47. Every failed screen is preserved in `per-release.json` and marked on plots. Better prediction does not resolve those failures.

Descriptive conditional paired release bootstrap stratified within each of only two regression recordings. It does not account for recording-level dependence, calibration bias, prior inspection or model selection; not a confidence guarantee for new sessions.

| Metric | Candidate minus baseline RMS | Descriptive 95% bootstrap interval |
| --- | ---: | ---: |
| short | -0.012° | -0.014° to -0.009° |
| .25 | -0.192° | -0.602° to 0.233° |
| .5 | -0.137° | -0.697° to 0.371° |

Across all six recordings, baseline/candidate short numeric passes are 66/66 of 66, and coverage passes are 65/65 of 66. Training6 release-09 is a preserved 1.356 s partial interval with only two short forecasts; its original three-window coverage gate remains failed. The initial scorer abort on this failure was corrected without changing the gate, annotations, fits, or selection method; original script and log are preserved in `coverage-correction.json`.

The robust weak leave-one-recording-out parameter spread is in `training.json.gz`. This is a stability diagnostic, not a calibrated confidence interval. Full-trajectory fitting uses per-release initial states as training nuisance parameters only; evaluation always estimates state from causal history. Friction, phase, encoder distortion, release handling and residual cart motion can still be confounded. A passing pixel pivot screen cannot certify physical cart stationarity. Absolute angle calibration, driven-cart input gain/delay and hardware approval remain unresolved.

## Every release

Each numeric cell is RMS / P95 degrees. C/P denotes original camera free-interval and held-pose screens. Short numeric/coverage flags and all exact failure reasons are in `per-release.json`.

| Recording / release | Baseline short | Candidate short | Baseline cont .5 | Candidate cont .5 | Baseline cont .25 | Candidate cont .25 | C/P |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| training6/release-01 | 1.498 / 3.262 | 1.493 / 3.239 | 2.438 / 4.933 | 2.104 / 4.236 | 1.636 / 3.304 | 1.644 / 3.403 | pass/pass |
| training6/release-02 | 1.702 / 3.198 | 1.699 / 3.169 | 1.551 / 3.510 | 1.307 / 2.803 | 1.604 / 3.013 | 1.399 / 2.479 | pass/FAIL |
| training6/release-03 | 1.985 / 4.232 | 1.974 / 4.186 | 3.194 / 5.629 | 3.141 / 5.502 | 2.373 / 5.470 | 2.309 / 5.349 | pass/pass |
| training6/release-04 | 2.464 / 5.326 | 2.453 / 5.273 | 2.099 / 3.963 | 2.041 / 3.869 | 2.840 / 4.854 | 2.741 / 4.734 | pass/pass |
| training6/release-05 | 3.386 / 6.533 | 3.403 / 6.474 | 2.323 / 4.252 | 2.876 / 5.320 | 2.090 / 4.400 | 2.337 / 4.509 | pass/pass |
| training6/release-06 | 2.194 / 5.218 | 2.185 / 5.263 | 7.124 / 13.631 | 5.515 / 11.027 | 5.403 / 10.606 | 3.964 / 8.443 | pass/pass |
| training6/release-07 | 2.625 / 6.144 | 2.629 / 6.212 | 2.264 / 4.222 | 1.964 / 3.756 | 2.209 / 4.441 | 1.909 / 3.729 | pass/pass |
| training6/release-08 | 2.014 / 4.039 | 2.007 / 4.067 | 1.254 / 2.598 | 1.171 / 2.086 | 1.684 / 3.029 | 1.503 / 2.683 | pass/FAIL |
| training6/release-09 | 2.706 / 4.962 | 2.702 / 4.912 | 1.610 / 4.094 | 1.544 / 3.909 | 3.723 / 7.490 | 3.693 / 7.269 | FAIL/pass |
| development6/release-01 | 1.700 / 3.033 | 1.702 / 2.948 | 1.740 / 3.564 | 1.469 / 3.050 | 1.319 / 2.691 | 1.288 / 2.454 | pass/pass |
| development6/release-02 | 1.826 / 4.039 | 1.821 / 4.036 | 1.397 / 2.952 | 1.269 / 2.507 | 1.739 / 3.619 | 1.518 / 2.947 | pass/pass |
| development6/release-03 | 2.003 / 4.109 | 1.990 / 4.099 | 2.848 / 5.013 | 2.774 / 4.909 | 2.480 / 5.770 | 2.421 / 5.657 | pass/pass |
| development6/release-04 | 2.322 / 4.882 | 2.316 / 4.884 | 1.985 / 3.778 | 1.913 / 3.613 | 3.147 / 5.467 | 3.019 / 5.278 | pass/FAIL |
| development6/release-05 | 2.809 / 6.255 | 2.774 / 6.177 | 2.191 / 3.953 | 3.175 / 5.823 | 20.496 / 37.630 | 17.624 / 32.170 | pass/pass |
| development6/release-06 | 2.054 / 4.404 | 2.032 / 4.394 | 8.031 / 15.129 | 5.940 / 11.794 | 2.218 / 4.943 | 2.353 / 4.443 | pass/pass |
| development6/release-07 | 1.992 / 3.134 | 1.993 / 3.073 | 2.299 / 4.293 | 2.013 / 3.718 | 1.509 / 3.114 | 1.428 / 2.767 | pass/pass |
| development6/release-08 | 2.042 / 4.087 | 2.039 / 4.051 | 1.393 / 3.123 | 1.272 / 2.578 | 1.610 / 2.927 | 1.456 / 2.665 | pass/FAIL |
| development6/release-09 | 1.780 / 3.716 | 1.769 / 3.755 | 3.815 / 6.651 | 3.748 / 6.553 | 2.137 / 4.979 | 2.058 / 4.775 | pass/pass |
| development6/release-10 | 2.621 / 5.315 | 2.610 / 5.266 | 2.858 / 4.880 | 2.866 / 4.950 | 3.685 / 6.314 | 3.625 / 6.263 | pass/FAIL |
| training8/release-01 | 2.093 / 3.916 | 2.091 / 3.836 | 2.946 / 5.666 | 2.618 / 4.959 | 2.558 / 5.242 | 2.264 / 4.634 | pass/pass |
| training8/release-02 | 1.844 / 3.399 | 1.839 / 3.357 | 2.093 / 4.301 | 1.851 / 3.621 | 1.782 / 3.591 | 1.523 / 3.097 | pass/pass |
| training8/release-03 | 2.154 / 4.375 | 2.139 / 4.347 | 3.736 / 6.701 | 3.698 / 6.583 | 2.525 / 5.112 | 2.472 / 4.944 | pass/pass |
| training8/release-04 | 2.165 / 4.576 | 2.155 / 4.513 | 2.185 / 4.347 | 2.119 / 4.323 | 3.328 / 5.662 | 3.222 / 5.532 | pass/pass |
| training8/release-05 | 2.517 / 5.355 | 2.488 / 5.269 | 2.466 / 5.422 | 2.453 / 4.909 | 14.452 / 26.608 | 11.919 / 22.473 | pass/FAIL |
| training8/release-06 | 2.650 / 5.486 | 2.631 / 5.433 | 3.059 / 6.524 | 2.556 / 5.148 | 3.058 / 5.299 | 4.123 / 7.377 | pass/FAIL |
| training8/release-07 | 2.506 / 4.936 | 2.512 / 4.938 | 1.931 / 3.882 | 1.637 / 3.298 | 2.587 / 5.139 | 2.298 / 4.490 | pass/pass |
| training8/release-08 | 1.953 / 3.548 | 1.949 / 3.559 | 2.130 / 4.066 | 1.913 / 3.538 | 1.481 / 2.842 | 1.436 / 2.838 | pass/pass |
| training8/release-09 | 2.147 / 4.297 | 2.131 / 4.250 | 3.074 / 5.474 | 3.042 / 5.462 | 2.282 / 4.923 | 2.232 / 4.778 | pass/pass |
| training8/release-10 | 1.879 / 3.802 | 1.870 / 3.792 | 2.079 / 4.476 | 2.036 / 4.316 | 4.254 / 7.346 | 4.140 / 7.141 | pass/pass |
| training8/release-11 | 3.051 / 6.493 | 3.045 / 6.452 | 2.607 / 4.914 | 3.559 / 6.675 | 4.612 / 8.272 | 5.708 / 10.302 | pass/pass |
| training8/release-12 | 3.296 / 7.446 | 3.257 / 7.401 | 5.783 / 10.768 | 4.736 / 8.604 | 3.416 / 6.105 | 3.748 / 7.112 | FAIL/FAIL |
| training9/release-01 | 2.089 / 4.069 | 2.082 / 3.998 | 2.613 / 4.590 | 2.358 / 4.217 | 3.163 / 5.811 | 2.904 / 5.328 | pass/pass |
| training9/release-02 | 2.143 / 3.848 | 2.132 / 3.861 | 1.855 / 3.353 | 1.665 / 2.875 | 2.568 / 4.299 | 2.330 / 3.993 | pass/pass |
| training9/release-03 | 1.907 / 4.006 | 1.897 / 3.967 | 3.961 / 6.864 | 3.901 / 6.704 | 2.434 / 5.459 | 2.359 / 5.326 | pass/pass |
| training9/release-04 | 2.356 / 5.036 | 2.347 / 5.009 | 2.524 / 4.521 | 2.443 / 4.387 | 3.656 / 6.325 | 3.513 / 6.091 | pass/pass |
| training9/release-05 | 2.457 / 5.302 | 2.441 / 5.252 | 2.438 / 5.207 | 2.642 / 5.058 | 5.125 / 9.116 | 6.181 / 11.150 | pass/pass |
| training9/release-06 | 2.497 / 4.867 | 2.483 / 4.859 | 4.531 / 9.265 | 3.120 / 6.459 | 3.675 / 6.182 | 4.974 / 8.773 | pass/FAIL |
| training9/release-07 | 2.017 / 4.123 | 2.008 / 4.120 | 2.514 / 4.475 | 2.289 / 4.213 | 2.672 / 5.197 | 2.382 / 4.572 | pass/pass |
| training9/release-08 | 1.889 / 4.076 | 1.880 / 4.017 | 1.561 / 3.080 | 1.409 / 2.557 | 2.279 / 4.197 | 2.003 / 3.846 | pass/pass |
| training9/release-09 | 1.972 / 4.422 | 1.963 / 4.416 | 3.780 / 6.293 | 3.674 / 6.147 | 2.350 / 4.397 | 2.245 / 4.147 | pass/pass |
| training9/release-10 | 2.325 / 4.888 | 2.316 / 4.857 | 2.239 / 4.018 | 2.152 / 3.859 | 4.676 / 7.815 | 4.506 / 7.583 | pass/pass |
| training9/release-11 | 2.820 / 6.009 | 2.822 / 6.131 | 2.191 / 5.119 | 2.315 / 4.367 | 2.456 / 4.438 | 3.434 / 6.321 | FAIL/pass |
| training9/release-12 | 3.670 / 8.409 | 3.649 / 8.361 | 2.988 / 6.848 | 2.283 / 5.406 | 3.060 / 5.538 | 3.234 / 6.033 | FAIL/FAIL |
| validation8/release-01 | 1.993 / 4.037 | 1.983 / 4.054 | 2.764 / 4.790 | 2.510 / 4.504 | 1.833 / 3.785 | 1.793 / 3.887 | pass/pass |
| validation8/release-02 | 2.081 / 4.220 | 2.069 / 4.112 | 2.099 / 3.631 | 1.938 / 3.488 | 2.355 / 4.126 | 2.129 / 3.961 | pass/pass |
| validation8/release-03 | 1.885 / 4.241 | 1.876 / 4.232 | 3.133 / 5.377 | 3.051 / 5.231 | 2.565 / 5.733 | 2.495 / 5.607 | pass/pass |
| validation8/release-04 | 2.462 / 5.211 | 2.453 / 5.189 | 2.550 / 4.379 | 2.441 / 4.259 | 4.775 / 7.990 | 4.614 / 7.724 | pass/pass |
| validation8/release-05 | 2.839 / 5.968 | 2.835 / 5.953 | 4.436 / 7.780 | 5.528 / 9.906 | 5.494 / 10.947 | 4.062 / 8.404 | pass/pass |
| validation8/release-06 | 2.360 / 5.221 | 2.348 / 5.186 | 7.067 / 13.623 | 5.084 / 10.266 | 3.790 / 7.941 | 2.661 / 5.379 | pass/FAIL |
| validation8/release-07 | 2.010 / 3.778 | 2.008 / 3.690 | 1.721 / 3.601 | 1.462 / 2.944 | 1.781 / 3.615 | 1.899 / 3.733 | pass/pass |
| validation8/release-08 | 2.048 / 3.949 | 2.036 / 3.915 | 1.750 / 3.077 | 1.619 / 2.883 | 2.320 / 4.009 | 2.098 / 3.642 | pass/pass |
| validation8/release-09 | 1.845 / 3.704 | 1.831 / 3.716 | 3.849 / 6.521 | 3.719 / 6.298 | 2.719 / 4.623 | 2.586 / 4.423 | pass/pass |
| validation8/release-10 | 2.443 / 5.124 | 2.437 / 5.092 | 2.573 / 4.761 | 2.516 / 4.594 | 3.081 / 5.300 | 2.951 / 5.137 | pass/pass |
| validation8/release-11 | 2.489 / 5.643 | 2.482 / 5.624 | 4.195 / 7.347 | 5.083 / 9.078 | 3.214 / 5.843 | 4.069 / 7.430 | pass/pass |
| validation9/release-01 | 2.016 / 4.449 | 2.010 / 4.425 | 2.451 / 4.573 | 2.135 / 4.021 | 2.928 / 5.267 | 2.676 / 4.965 | pass/pass |
| validation9/release-02 | 1.895 / 4.152 | 1.880 / 4.095 | 1.678 / 2.927 | 1.527 / 2.672 | 2.179 / 3.843 | 1.951 / 3.643 | pass/pass |
| validation9/release-03 | 1.895 / 4.393 | 1.880 / 4.405 | 3.846 / 6.474 | 3.738 / 6.335 | 3.916 / 6.725 | 3.777 / 6.450 | pass/pass |
| validation9/release-04 | 2.211 / 4.864 | 2.198 / 4.823 | 1.989 / 3.331 | 1.864 / 3.135 | 4.269 / 7.388 | 4.150 / 7.236 | pass/pass |
| validation9/release-05 | 2.373 / 5.105 | 2.354 / 5.080 | 2.776 / 4.869 | 3.746 / 6.862 | 3.130 / 5.639 | 4.064 / 7.478 | pass/pass |
| validation9/release-06 | 2.736 / 5.739 | 2.719 / 5.735 | 3.354 / 7.585 | 2.246 / 5.195 | 2.889 / 4.802 | 3.937 / 6.987 | pass/FAIL |
| validation9/release-07 | 2.081 / 4.440 | 2.072 / 4.383 | 2.237 / 4.434 | 2.040 / 4.283 | 2.471 / 4.495 | 2.253 / 4.162 | pass/FAIL |
| validation9/release-08 | 2.141 / 4.342 | 2.147 / 4.364 | 1.537 / 2.968 | 1.434 / 2.809 | 1.625 / 3.183 | 1.441 / 2.802 | pass/pass |
| validation9/release-09 | 1.867 / 4.218 | 1.856 / 4.233 | 3.448 / 5.888 | 3.347 / 5.791 | 3.638 / 6.259 | 3.530 / 6.086 | pass/pass |
| validation9/release-10 | 2.314 / 4.973 | 2.303 / 4.953 | 1.815 / 3.662 | 1.733 / 3.361 | 2.378 / 4.203 | 2.203 / 3.961 | pass/pass |
| validation9/release-11 | 2.517 / 5.653 | 2.495 / 5.564 | 2.727 / 4.694 | 3.710 / 6.737 | 6.274 / 12.034 | 4.798 / 9.722 | pass/pass |
| validation9/release-12 | 3.211 / 6.539 | 3.186 / 6.433 | 7.175 / 12.346 | 5.406 / 9.779 | 4.048 / 6.902 | 4.901 / 8.856 | FAIL/FAIL |

## Reproduce

Run from the repository root, using an output directory that does not contain prior outputs:

```bash
uv run --offline --script evidence/passive-refinement-20261017/tools/refine.py train --output /tmp/passive-refinement-repeat
uv run --offline --script evidence/passive-refinement-20261017/tools/refine.py regression --output /tmp/passive-refinement-repeat
uv run --offline --script evidence/passive-refinement-20261017/tools/verify_causality.py --output /tmp/passive-refinement-repeat/causality-verification.json
MPLCONFIGDIR=/tmp/passive-refinement-mpl uv run --offline --script evidence/passive-refinement-20261017/tools/report.py --evidence /tmp/passive-refinement-repeat
```

The scripts use preserved archives if ignored extracted recordings are absent. Online dependency installation may be needed on a new machine; the recorded run used cached environments only. Sources, annotations, original archive hashes and exact fit method hashes are recorded in the training and regression reports. Candidate freeze and baseline freeze hashes remain separate. All outputs are developmental evidence.

Plots:

- [training6 comparison](training6-comparison.png)
- [development6 comparison](development6-comparison.png)
- [training8 comparison](training8-comparison.png)
- [training9 comparison](training9-comparison.png)
- [validation8 comparison](validation8-comparison.png)
- [validation9 comparison](validation9-comparison.png)

Read-only integrity check: `python3 evidence/passive-refinement-20261017/tools/verify_bundle.py`. Intermediate per-model checkpoints were moved to ignored `runs/passive-refinement-20261017-cache`; their complete content remains in `training.json.gz`.
