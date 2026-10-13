# 125 mm arm / 11.05 g, with two 5.85 g end weights

The user confirmed on 2026-09-17 that the original **100 mm** length label was
incorrect: it was always **125 mm**, mass **11.05 g**, with the same two
**5.85 g** end weights. Total arm and end-weight mass is **22.75 g**.
The pre-175 mm recordings are from this assembly.

Raw files stay in their historical directory; no old capture or metric was
rewritten. [Configuration](configuration.json) records the corrected geometry.
[Fit](controller_fit.json) includes source SHA-256 hashes and individual cycles.

## Refit

Same-side decaying peaks with both amplitudes 5–20°, at least six qualifying
cycles per run; identical selection criteria to the 175 mm fit. Median period
per run, then median effective length across runs. Twenty cycles from three
recordings give **0.7077035 s**, **0.124454888 m** effective length and
**0.913383 s⁻¹** equivalent viscous damping. Firmware rounds length to
**0.124 m**. Mass is not an independent gain in the acceleration-input model;
effective length captures the ratio of rotational inertia to gravity torque.

| Recording | Qualifying cycles | Effective length | Use |
|---|---:|---:|---|
| pendulum_20260915_165535 | 6 | 124.455 mm | Included |
| pendulum_20260915_170518 | 7 | 122.699 mm | Included |
| pendulum_20260915_170610 | 7 | 124.889 mm | Included |
| pendulum_20260915_164630 | 5 | — | Fewer than six qualifying cycles |
| pendulum_20260915_165853 | 5 | — | Fewer than six qualifying cycles |
| pendulum_20260915_170232 | 0 | — | Fewer than six qualifying cycles |
| pendulum_20260915_170334 | 5 | — | Fewer than six qualifying cycles |

## Reproduce

`python3 analysis/fit_125mm.py` from the repository, with NumPy and SciPy installed.
The script reads all seven original captures and writes only this derived fit.
Excluded captures remain preserved; this is not a claim that they are corrupt.
Damping is a descriptive low-angle estimate, not exact friction compensation.
A new free-swing recording is useful to check the reassembled arm, but the
existing data are sufficient to restore its prior measured model.
