# v19 middle-of-run tuning review

Source: `logs/run_20260916_153109.csv` and its event log. The second accepted upright attempt remained in BALANCE from board time **21.417 to 61.121 s**, approximately **39.7 seconds**. Use **27–47 s** as the clean comparison window: after initial settling and before the two disturbances. The user confirms two taps and does not think the cart was physically off center. Therefore the logged cart position must not be interpreted as independently measured physical displacement.

No firmware, live gains, calibration, or motion limits were changed in this review.

## Measured middle behavior

| Quantity, board time 27–47 s | Result |
|---|---:|
| Samples | 495 |
| Mean angle relative to stored upright | +0.233° |
| Angle standard deviation | 0.541° |
| 95th percentile absolute angle error | 1.054° |
| Main angle/speed/acceleration oscillation | approximately 1.5–1.6 Hz |
| Mean pulse-inferred cart position | −93.5 mm |
| Position standard deviation | 7.94 mm |
| Commanded speed RMS | 0.0372 m/s |
| Commanded acceleration RMS | 0.509 m/s² |
| Acceleration range | −1.454 to +1.596 m/s² |
| Sample-to-sample acceleration slope above 90% of jerk cap | 0.2% |

The motion is a small periodic oscillation, not repeated saturation of the 12 m/s² acceleration or 0.8 m/s speed limits. There is no reason in this window to raise either limit. The sampled jerk statistic cannot exclude brief between-sample limiting at the 1 kHz control rate.

The first user tap, around board time **50 s**, caused a transient of about ±4° and the system recovered. The second, around **61 s**, produced roughly 12° error and commanded speed reaching 0.8 m/s, followed by **predictive rail recovery**. It was not the 50° angle cutoff. Keep the rail protection.

The event log contains malformed startup bytes before the firmware handshake, but no such errors during the analyzed middle episode. The later automatic swing-up segment is outside this analysis.

[Full upright episode plot](middle_balance.png) · [Numerical metrics/source hash](metrics.json)

## Next trial: soften the upright response by one setting

While stopped:

```text
stop
set bal_pw 7
params
```

Then raise the pole and use **START upright** / `bal` as before. This uses the existing v19 firmware; **no upload is required**. Keep `pz=.85`, cart poles −.8/−1.2, estimator bandwidth 10 Hz, and limits .8/12/12/60 unchanged. Do not send a start until ready.

This changes one pole-placement parameter, not a PID proportional gain alone. Its resulting angle and angular-rate feedback gains fall by approximately **12%**, and cart position/velocity feedback gains by about **23%/22%**. That should reduce correction aggressiveness and is a reasonable test for the observed periodic motion. It may also soften recovery and centering, so improvement is not guaranteed.

Repeat a similar near-vertical release, allow 5 seconds to settle, and compare a 20-second undisturbed interval. Desired improvement is reduced angle standard deviation from **0.54°**, smaller commanded speed/acceleration oscillations, and no loss of rail margin. Compare similar small taps only after that window. If it becomes less stable or drifts toward a boundary, stop and restore:

```text
set bal_pw 8
```

Parameters reset on reboot; the repository default remains 8 pending physical comparison.

## What simulation supports—and its limits

Using the production nonlinear simulator, unchanged motion bounds and **no trim**, both settings 7 and 8 settled in **9 of 12** sensitivity cases across actuator lags 0/20/40/60 ms and tracking fractions .6/.8/1.0. The 60 ms cases failed for both, so neither setting solves arbitrary delay.

In one illustrative case with a 40 ms actuator lag and ideal velocity tracking, lowering 8 → 7 reduced final-five-second angle RMS from **0.545° to 0.053°** and acceleration RMS from **0.576 to 0.071 m/s²**. This is not a predicted tenfold physical improvement: the actual actuator lag/tracking have not been identified. It demonstrates a plausible way that a slightly softer controller could suppress the observed oscillation.

A spectral diagnostic around 1.5–1.6 Hz showed the measured angle lagging the command acceleration by roughly 22–23°, while the simple calibrated model predicts approximately +1.5°. This suggests the ideal-actuator assumption is incomplete. It does not independently identify a 40 ms motor delay: closed-loop correlation, encoder scale, pivot friction, telemetry timing and actuator dynamics are confounded.

[Gain comparison results](gain_trial.json). Reproduce with:

```sh
node analysis/upright_middle_20260916/gain_trial.js
```

The larger grid in `screen.json` also explores hypothetical angle trim. Its trim is **not applied** and is not used as evidence for the no-trim physical trial.

## Position/reference discrepancy: verify before trimming

The controller reports x ≈ −94 mm, but the user recalls the cart physically near center. Possible causes include establishing the software origin away from the physical midpoint, movement while disabled, missed steps, or a scale mismatch. The current logs cannot distinguish these. A slow measured jog and a deliberate physical-center `home` reference are more informative than changing cart gains to chase the logged offset.

With the current gain matrix, the logged mean angle of +0.233° almost balances the position-feedback term from −94 mm: the static gain relation predicts +0.220°. This is consistent with a small upright-reference bias, but does **not** establish one independently. A +0.1 to +0.2° trim is worth considering only after the physical reference/tracking are checked. v19 has no `bal_trim` command; do not send a nonexistent setting or use `zero` (which does not change the absolute upright target).

The previous approximately 3° estimate from the hanging pose should **not** be applied. This successful upright data provides stronger local evidence and shows why half-turn extrapolation from a single down pose is unreliable here. No encoder target or inertia change is warranted for the next one-setting trial.
