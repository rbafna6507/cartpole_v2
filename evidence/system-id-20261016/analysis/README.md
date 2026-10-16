# Offline identification preparation

No new physical model is accepted. The original forced-input fitter and all of its acceptance gates remain unchanged. `passive-plan.json` freezes a separate passive model and validation protocol before new dynamic releases are read. The first manual recording was diagnosed from its recorded data as containing only a static arm; it is not a training dataset and was not fitted here. The subsequent dynamic training-only result and frozen candidates are in `manual-ringdown-train-02-report.md` and its JSON summary.

`passive_fit.py` takes explicitly selected free-release episodes from separate recording identities. It has no rig, camera, network or simulator side effects. Each episode is a dictionary with `run_id` (the raw recording hash), `episode_id`, and matching SI arrays `t_s` and `theta_rad`. The caller must preserve the source hashes and annotation provenance. Do not treat user lifting/holding, cart motion or static suffixes as free decay. Timestamps are monotonic within each episode; neither fitting nor prediction crosses an episode or an excessive sample gap.

```python
from passive_fit import fit_passive, camera_stationarity

report = fit_passive(training_episodes, heldout_episodes,
                     model="viscous_coulomb")
comparison = fit_passive(training_episodes, heldout_episodes,
                         model="viscous")
pixels = camera_stationarity(raw_sensing_stream_rows)
```

The model fits gravity sine/cosine coefficients, viscous damping and optional Coulomb angular friction. Effective length and constant angular bias follow from the gravity coefficients. Bias is estimated from training only; no filtered firmware omega initializes forecasts. Parameter estimation never consumes heldout measurements. Both model classes are declared in advance; heldout results cannot choose a different model or threshold retroactively.

`statistical_checks_pass` describes only the declared passive checks. `recommended_model` is always null: fixed physical cart, free release and the magnetic angle mapping require their own evidence. The passive experiment does not identify commanded-input gain/delay, cart/pole masses, motor forces or absolute hinge torque coefficients. Mapping angular damping to MuJoCo hinge damping requires a declared pivot inertia: `hinge_damping = gamma * I_pivot`; similarly Coulomb torque is `c * I_pivot`. With the current uniform-rod surrogate, `I_pivot = 0.75 * pole_mass * effective_length**2`. Assumed mass and force saturation remain assumptions even if pole dynamics validate.

The raw camera audit checks image-plane `pivot_px` stability and ignores all calibrated/fused fields. Pixel stability can support the operator's physically restrained cart condition, but cannot establish metric displacement, out-of-plane stationarity, lens correction or an independent global angle calibration. Raw camera angle and image length should be retained for a later separately validated geometry/timing comparison.

Eleven local tests passed. Synthetic data use an independently implemented 0.25 ms midpoint integrator; predictions use 1 ms RK4. Tests recover known length/damping/friction/bias, prove heldout changes cannot alter training parameters, reject reused recordings, static data and constant-speed handling, prevent cross-gap windows, check static friction and detect raw pixel translation. Training-only calls cannot invent heldout scores. A completely static heldout cannot validate a dynamic training model: the existing0.15rad excitation requirement also applies to heldout admission. Sparse camera samples lacking derivative support cannot invent Coulomb signs: those weak windows are excluded; the viscous model needs no derivative estimate. These are estimator tests, not physical validation. No repository-wide or hardware test was run by this analysis task. The initial eight-test `verification.json` remains historical; `manual-ringdown-train-02-freeze.json` pins the final training-only files.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover \
  -s evidence/system-id-20261016/analysis -p test_passive_fit.py -v
```

## Why the previous characterization still rejects

`existing_characterization_diagnostics.py` adds exploratory diagnostics using **pilot and training only**; the prior heldout run is not used for new model exploration. It checks the original fitter/adapter hashes and reproduces the frozen rejected baseline residual exactly. Results and original compressed/raw source hashes are in `existing-characterization-diagnostics.json`.

Doubling the same multisine excitation from pilot to training changed the 1.3 Hz angle/commanded-acceleration gain from 0.23645 to 0.31047 rad/(m/s²), about 31%, and phase from −1.1796 to −1.4610 rad. This is evidence against treating the two records as one exact amplitude-invariant linear response. It does not establish friction as the unique cause; settling, sensor mapping and actual cart motion remain confounded.

The quiet preflight angle changed from 3.060292 rad in the pilot to 3.038966 rad in training. The training tail then averaged 3.025001 rad, another −0.013966 rad from its own preflight. A quiet hanging reading is therefore not sufficient evidence of a unique true vertical reference.

| Training-only model diagnostic | Integral NRMSE |
|---|---:|
| Original three terms, frozen hanging offset | 0.348298 |
| Add symmetric Coulomb term | 0.314250 |
| Add constant torque term | 0.184911 |
| Add both terms | 0.168893 |
| Existing five-term angle-offset diagnostic | 0.184205 |

Extra coefficients necessarily improve in-sample fit; none of these numbers is independent validation, and every value still exceeds the unchanged 0.15 residual gate. No candidate is promoted. The constant-torque improvement and drifting quiet positions motivate bidirectional releases and physical angle/cart checks; they do not justify silently correcting calibration or changing the simulator.

For a fresh reproduction output:

```sh
PYTHONPATH=src .venv/bin/python \
  evidence/system-id-20261016/analysis/existing_characterization_diagnostics.py \
  --output /tmp/fresh-characterization-diagnostics.json
```
