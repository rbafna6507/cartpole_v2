# Gentle driven training: conditional prediction, 2026-10-20

The fixed pole model passes the limited forecast and excitation checks for four gentle ±20 mm trials only when evaluated with each trial's pre-motion hanging anchor. The raw firmware-reference baseline fails those forecasts. Both baselines fail native AUTO prediction. This is **training data, not independent validation**, and no model or global encoder calibration is accepted or changed.

The complete sealed `runs/id-live-20261020/gentle-train-02` campaign contains one timing hold, six actuator trials, and one 15 s native AUTO trial. All eight completed with confirmed stops and no dropped log records. The scored states retain healthy continuity: maximum board gap is 10.001 ms; maximum host receipt gap is 12.901 ms. All six actuator trials report zero policy clamps and zero policy jerk-limited commands. Those counters do not establish the intersample MCU trajectory or physical cart tracking. Vision was deliberately excluded.

## Frozen model and scoring scope

The unchanged equation is `qdd = (9.81*sin(q) - a_MCU*cos(q))/L - gamma*omega - c*tanh(omega/0.05)`, with `L=0.160303873 m`, `gamma=0.006891975 /s`, and `c=1.6268943 rad/s²`. Unit commanded-input gain and zero delay are assumptions. `a_MCU` is the recorded command-state proxy, held left-constant between 100 Hz samples. It is not an independent physical acceleration measurement, and it omits intersample 1 kHz governor ramps.

Every 0.5 s forecast reinitializes from the current raw encoder angle and a quadratic derivative of seven past/current encoder samples. Recorded firmware omega is a separate comparator, never a replacement chosen by its score. Forecast forcing uses the subsequently recorded input history. This evaluates conditional short-horizon predictions; it does not establish full-episode open-loop accuracy, autonomous input prediction, masses, actuator gain/delay, physical cart stationarity, or a globally valid encoder map.

The two predeclared baselines are retained separately: `firmware_reference` has zero offset; `local_hanging_anchor` subtracts `wrap(initial_hanging-pi)` from a pretrial quiet observation. Actuator offsets range from −0.090505 to −0.084369 rad. Resting equilibrium can be displaced by friction, so the local anchor is a sensitivity check, not proven true vertical or an upright calibration. The native trial's anchor is −0.102777 rad. No phase was selected by residual score, and the prior passive phase was not reused globally.

The limited pertrial checks require at least three forecasts, encoder span ≥0.15 rad, commanded acceleration RMS ≥0.05 m/s², causal forecast RMS ≤0.08 rad and absolute-error p95 ≤0.15 rad. Continuity gaps ≥20 ms reject a trajectory. These checks do not replace the original full-model residual, physical-validity, or calibration gates. `hardware_accepted=false` and `recommended_model=null` remain explicit.

## Results

Errors below are radians using causal encoder initialization. The full-trial columns include the 3 s feedback cart hold. Excitation-only errors are shown separately to expose quiet-tail averaging. Pulse paths are `0,A,0`; reversal paths are `0,A,-A,0`, with 0.4 s per segment.

| Excitation | Encoder span | Command a RMS (m/s²) | Raw-phase RMS | Local-anchor RMS / p95 | Local excitation-only RMS / p95 | Local limited checks |
|---|---:|---:|---:|---:|---:|---|
| +10 mm pulse | 0.12272 | 0.15413 | 0.09589 | 0.00774 / 0.02208 | 0.01354 / 0.02492 | Fail: insufficient angle span |
| −10 mm pulse | 0.13039 | 0.15402 | 0.10126 | 0.01964 / 0.04818 | 0.01985 / 0.03521 | Fail: insufficient angle span |
| +20 mm pulse | 0.32827 | 0.30842 | 0.10926 | 0.01988 / 0.04473 | 0.02957 / 0.05623 | Pass, conditional training only |
| −20 mm pulse | 0.31907 | 0.30736 | 0.11722 | 0.03586 / 0.09874 | 0.02320 / 0.04978 | Pass, conditional training only |
| +20 mm reversal | 0.70256 | 0.50700 | 0.13188 | 0.03407 / 0.07705 | 0.02455 / 0.04590 | Pass, conditional training only |
| −20 mm reversal | 0.69029 | 0.50801 | 0.12612 | 0.02367 / 0.04406 | 0.03005 / 0.05462 | Pass, conditional training only |

The static timing trial has span 0.001534 rad and zero input RMS, so its local-anchor RMS of 0.00151 rad is ineligible as dynamics validation. The native AUTO trial fails strongly: raw-phase RMS/p95 are 0.79796/1.94196 rad; local-anchor values are 0.84841/2.17277 rad. Native recorded-omega initialization still fails (RMS 0.77792 raw / 0.78772 local). Thus initial-rate estimation alone does not explain the native mismatch. Command reconstruction, phase validity away from hanging, and pole-model mismatch remain confounded; these records do not uniquely identify a physical cause.

For the −20 mm pulse, local-anchor full-trial RMS changes from 0.03586 to 0.01877 rad with recorded omega. The initialization sensitivity is material, but it is not consistently beneficial across the six trials and is not used to change the primary metric. Exact window starts, initial rates, per-phase errors and both predictions are in `analysis.json` and the eight plots.

## Native capture and actual hold

The separate mode audit finds swing from 0–2.51 s, balance from **2.51–3.51 s (1.00 s, 100 recorded mode-3 samples)**, modes 5/6 from 3.51–3.71 s, then swing through the 15 s AUTO limit. Normal return occupies 15.00–18.49 s before disabled state. Transition times are quantized by approximately 10 ms telemetry. Counting first capture through the run end would falsely report 12.49 s of balance.

Within enabled mode-3 samples only, raw firmware-reference angle RMS is 4.97623° and absolute-angle p95 is 8.09472°. Maximum absolute **counted** cart position over AUTO and normal return is 0.2932875 m; no fault is recorded. This is not an independent physical cart displacement measurement. `native-summary.json` preserves the full mode intervals.

## Implication and provenance

The ±20 mm pulses and reversals provide more informative near-hanging excitation than ±10 mm here. A fresh independent repeat of these declared trials can test the unchanged model and both predeclared phase baselines. Any newly tuned phase, delay, friction, or input gain would need training-only fitting followed by new unseen validation. These results do not support promoting this model for upright hardware control or claiming the full coupled dynamics are identified. No pinned model, training profile, calibration, board parameter, or default was changed by this analysis.

Source identities:

- Campaign manifest SHA-256: `0abb8b3b061b156a5efb587f228d48b9077c4dfcf78a824d7aad1c7f837ee1fa`.
- Raw `rig-1792542554363258349-770265025.jsonl`: `9f9f9f714dcd6b8e42a742154e8adecd3dd39e9d13cfd91da3a6e44e866a4991`.
- Campaign report: `1e5ba3d2426912663ecdb382beca1a5dc7cdfeef7e927fb487f12ebb68444d2b`.
- Analyzer: `46f79474ae00415a6ead5f3360439a13c1bb574d89db22b62bc783506efd3439`.
- Frozen model JSON: `ad41557a386da4c927d56ebb4a0fa3e64c349e7e234c65c2c0d5e0f70123a43d`.

Reproduce from the repository root using a new output directory (the analyzer refuses overwrite):

```sh
MPLCONFIGDIR=/tmp/cartpole-id-matplotlib PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m cartpole_sdk.identification.driven_validation --training runs/id-live-20261020/gentle-train-02 --output /tmp/gentle-train-02-reproduction
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python evidence/system-id-20261020/driven-gentle-v1/summarize_native.py runs/id-live-20261020/gentle-train-02
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_driven_validation.py -q -p no:cacheprovider
```

The analyzer's 18 focused tests passed. Representative +20 mm and native plots were visually inspected; all eight retain both phase baselines. File pins and source verification are in `verification.json`.
