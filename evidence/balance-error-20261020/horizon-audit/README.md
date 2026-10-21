# Saved-forecast horizon audit

The large 0.5-second error is a conditional forecast-pipeline result. It does not isolate physical plant-model error. These saved predictions show substantial horizon amplification and sensitivity to the initial angular-rate estimate, with no new fitting or simulation.

Both validation trials retain exactly the same 44 original windows at all five horizons and for both initializers. Every saved point in those windows is labelled native balance mode. Exact-lead scores use 44 residuals each; prefix scores use 44, 220, 440, 880 and 2,200 residuals at 10, 50, 100, 200 and 500 ms. Initial zero-error points are excluded.

| Trial | Initial rate | Metric | 10 ms | 50 ms | 100 ms | 200 ms | 500 ms |
|---|---|---|---:|---:|---:|---:|---:|
| 001-coupled | causal_encoder | exact_lead | 1.187° | 7.622° | 15.271° | 36.104° | 111.990° |
| 001-coupled | causal_encoder | pooled_prefix | 1.187° | 4.931° | 9.456° | 19.371° | 74.659° |
| 001-coupled | recorded_omega | exact_lead | 1.191° | 5.058° | 7.330° | 15.550° | 104.659° |
| 001-coupled | recorded_omega | pooled_prefix | 1.191° | 3.510° | 5.149° | 8.709° | 48.511° |
| 002-coupled | causal_encoder | exact_lead | 1.486° | 8.453° | 17.870° | 42.600° | 105.939° |
| 002-coupled | causal_encoder | pooled_prefix | 1.486° | 5.621° | 10.816° | 23.397° | 73.379° |
| 002-coupled | recorded_omega | exact_lead | 1.410° | 4.464° | 6.932° | 13.774° | 103.417° |
| 002-coupled | recorded_omega | pooled_prefix | 1.410° | 3.361° | 4.773° | 8.276° | 46.822° |

The 500 ms causal prefix RMS is approximately 73–75°, while the exact 500 ms lead is 106–112°. At 10 ms both initializers are approximately 1.2–1.5°. Using firmware rate lowers the 500 ms prefix RMS to approximately 47–49°, yet exact 500 ms errors remain 103–105°. This establishes sensitivity, not that firmware rate is ground truth or that initialization explains all discrepancy.

The upright gravitational term amplifies departures. Recorded control actions depend on the real rig state; the diverging open-loop forecast never receives corrective actions based on its own predicted state. Differences can therefore combine initial angle/rate, phase, commanded-versus-physical acceleration, input reconstruction/delay, and model mismatch. No evident sign/unit/wrap defect was identified in the accompanying read-only review; these scores alone cannot rule one out or assign a causal share.

The existing forecast API is fixed at 0.5 seconds. Its saved points already support this shorter-horizon diagnostic. No frozen implementation, source prediction, raw dataset, or validation role was changed. The original forecast checks remain failed and hardware acceptance remains false.

## Limitations

- MCU acceleration is a command-state proxy; unit input gain and zero delay are assumptions, not measured actuator properties.
- Left-held 100Hz input omits intersample 1kHz governor ramps. Input history over each forecast is conditioned on recorded commands.
- Every 0.5s forecast reinitializes from past raw encoder data; full-episode open-loop accuracy is not established.
- Firmware-reference and pertrial local-hanging sensitivities are both retained; resting equilibrium may be shifted by friction. Neither establishes global angle calibration.
- Recorded firmware omega is a comparator only; the primary estimate uses seven past/current encoder samples.
- Pertrial forecast checks do not replace original full-model residual/calibration/physical-validity gates. Partial campaigns remain partial diagnostics.
- No vision is loaded; physical cart tracking, masses, force authority, input delay and metric actuator gain remain unmeasured.
- Post-hoc diagnostic of previously inspected validation data; no new holdout, model selection, fit, calibration, or acceptance test.
- This is conditional replay of recorded closed-loop command acceleration, not independent physical acceleration or closed-loop simulated feedback.
- Upright instability can amplify initialization and input/model discrepancy over 0.5s. This audit does not identify their separate contributions.
- Shorter lead errors and initializer sensitivity do not establish actuator calibration or hardware suitability; original failed forecast checks remain failed.
- The wholly-balance window subset differs slightly from the original pool of all points labelled balance, which can include phase-crossing windows.
- Circular residuals are bounded by pi; long-horizon error is not an unwrapped rotation error. Overlapping prefix scores are correlated, not independent experiments.

## Reproduce

Run from the repository root into a new output directory:

```sh
MPLCONFIGDIR=/tmp/cartpole-horizon-mpl .venv/bin/python /Users/rbafna/projects/cartpole_v2/evidence/balance-error-20261020/tools/audit_forecast_horizons.py \
  --input evidence/balance-error-20261020/driven-validation/analysis.json \
  --analysis-source src/cartpole_sdk/identification/driven_validation.py \
  --output /tmp/cartpole-horizon-audit-reproduction
```

`report.json` binds this script, input analysis, original analysis source, and model to SHA-256 hashes. Original raw/manifest/report hashes are preserved as inherited provenance; this script does not reread those raw inputs. The script refuses an existing output directory, checks the frozen analysis-source hash, checks saved residuals against predictions, and rejects missing exact leads rather than interpolating.
