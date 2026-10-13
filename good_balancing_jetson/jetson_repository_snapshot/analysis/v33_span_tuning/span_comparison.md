# Swing-up time and occupied rail span

A qualified hold stays in balance within ±0.1 rad for 10 seconds. Time is the start of that interval. Bounds are step-pulse estimates. Failed captures do not qualify as successful space reductions. Deliberate disturbances are annotated in the underlying records.

| Trial | Jerk | ke / kpx / kdx / bw | Time to hold (s) | −x / +x before hold (mm) | Span before hold (mm) | Whole-run span (mm) | Longest hold (s) | Result |
|---|---:|---|---:|---|---:|---:|---:|---|
| 025_tighter_capture | 100 | 4 / 40 / 2 / 30 | 19.98 | -134.59 / 134.51 | 269.10 | 269.10 | 30.01 | held_upright_30_seconds |
| 026_tight_bw20 | 100 | 4 / 40 / 2 / 20 | — | — | — | 269.40 | 0.00 | duration_elapsed |
| 027_tight_bw40 | 100 | 4 / 40 / 2 / 40 | — | — | — | 269.07 | 9.57 | duration_elapsed |
| 028_repeat_tight_bw30 | 100 | 4 / 40 / 2 / 30 | — | — | — | 269.06 | 0.06 | duration_elapsed |
| 032_jerk150_bw30 | 150 | 4 / 40 / 2 / 30 | 13.85 | -134.63 / 134.81 | 269.44 | 269.44 | 30.00 | held_upright_30_seconds |
| 033_repeat_jerk150_bw30 | 150 | 4 / 40 / 2 / 30 | 4.53 | -134.66 / 133.99 | 268.65 | 268.65 | 30.01 | held_upright_30_seconds |
| 034_jerk150_bw40 | 150 | 4 / 40 / 2 / 40 | 29.84 | -134.63 / 134.25 | 268.88 | 268.88 | 30.01 | held_upright_30_seconds |
| 035_jerk150_ke3 | 150 | 3 / 40 / 2 / 30 | 31.14 | -131.40 / 134.81 | 266.21 | 266.21 | 17.35 | duration_elapsed |
| 036_jerk150_kdx3 | 150 | 4 / 40 / 3 / 30 | 6.32 | -132.94 / 134.32 | 267.26 | 267.26 | 30.00 | held_upright_30_seconds |
| 037_jerk150_kpx80 | 150 | 4 / 80 / 3 / 30 | — | — | — | 269.29 | 0.02 | duration_elapsed |
| 038_jerk150_kdx4 | 150 | 4 / 40 / 4 / 30 | — | — | — | 255.56 | 0.00 | duration_elapsed |
| 039_jerk150_kdx35 | 150 | 4 / 40 / 3.5 / 30 | — | — | — | 267.79 | 0.00 | duration_elapsed |
| 043_span240 | 150 | 4 / 40 / 2 / 30 | — | — | — | 239.33 | 0.00 | duration_elapsed |
| 044_span240_ke3 | 150 | 3 / 40 / 2 / 30 | 14.20 | -119.85 / 119.59 | 239.44 | 239.44 | 10.01 | held_upright_10_seconds |
| 045_span210_ke3 | 150 | 3 / 40 / 2 / 30 | — | — | — | 209.32 | 0.00 | duration_elapsed |
| 046_span210_early_approach | 150 | 3 / 40 / 2 / 30 | — | — | — | 209.29 | 0.00 | duration_elapsed |
| 047_span225_ke3 | 150 | 3 / 40 / 2 / 30 | — | — | — | 224.67 | 0.60 | duration_elapsed |
| 048_compact_validation | 150 | 3 / 40 / 2 / 30 | — | — | — | 186.34 | 0.00 | aborted |
| 052_compact_validation | 150 | 3 / 40 / 2 / 30 | — | — | — | 28.69 | 0.00 | aborted |
| 056_powered_compact_validation | 150 | 3 / 40 / 2 / 30 | — | — | — | 239.48 | 0.02 | duration_elapsed |
| 057_span240_ke25 | 150 | 2.5 / 40 / 2 / 30 | — | — | — | 231.08 | 0.00 | duration_elapsed |
| 058_span255_ke4 | 150 | 4 / 40 / 2 / 30 | — | — | — | 254.29 | 2.81 | duration_elapsed |
| 059_span240_earlier_capture | 150 | 3 / 40 / 2 / 30 | — | — | — | 239.84 | 0.00 | duration_elapsed |
| 060_span240_ke5_early_capture | 150 | 5 / 40 / 2 / 30 | — | — | — | 239.55 | 0.00 | duration_elapsed |
| 061_full_span_reference | 150 | 4 / 40 / 2 / 30 | 31.55 | -134.96 / 134.18 | 269.14 | 269.14 | 30.01 | held_upright_30_seconds |
| 062_span255_ke3 | 150 | 3 / 40 / 2 / 30 | 13.29 | -127.28 / 127.24 | 254.52 | 254.52 | 10.01 | held_upright_10_seconds |
| 063_span255_ke3_long | 150 | 3 / 40 / 2 / 30 | — | — | — | 254.82 | 0.00 | duration_elapsed |
