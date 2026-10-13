# Settling candidate for the 175 mm pendulum

## Selected settings

Use **Acceleration → jerk-limited DDS**, with the calibrated plant unchanged:

| Parameter | Value |
|---|---:|
| Swing acceleration `amax_s` | **3 m/s²** |
| Balance acceleration `amax_b` | **5 m/s²** |
| Jerk `jmax` | **25 m/s³** |
| Speed `vmax` | **0.55 m/s** |
| Energy gain `ke` | **3.5** |
| Cart position gain `kpx` | 30 s⁻² |
| Cart velocity gain `kdx` | 0.5 s⁻¹ |
| Phase smoothing `phase_soft` | 1 rad/s |

All remaining controller/plant settings retain the simulator's recorded baseline. In particular, encoder updates remain 2 ms, effective plant length 165.776 mm, damping 0.402279 s⁻¹, control bandwidth 10 Hz, and total rail travel 300 mm. Nominal tracking is ideal; tracking sensitivity is tested separately. **Braking may use 5 m/s² even during swing-up** because the firmware governor uses the larger acceleration cap. The energy-gain change is part of the candidate; limits alone are not the same experiment.

Open `index.html?preset=settling` or choose **Settling candidate** from the preset menu and click **Run experiment**. This only changes simulator controls. Firmware and saved hardware-control defaults have not been changed by this search.

## What settled

A 60-second nominal simulation starting stationary and hanging at rail center:

- First upright capture: **5.636 s**; one capture, no subsequent loss.
- Continuously inside the UI's balance criterion from approximately **5.943 s** to the end.
- Tighter settling from **10.52 s**: thereafter within **2° upright**, **10 mm of center**, and **0.02 m/s** through the end of the simulation. This check uses the exported 10 ms trace.
- Last five seconds: **0.0348° angle RMS**, **1.25 mm position RMS**.
- Peak speed **0.55 m/s**, peak acceleration **4.925 m/s²**, peak jerk **25 m/s³**.
- Peak physical cart position **134.14 mm** from center, leaving **15.86 mm** to the physical rail end. This still uses much of the rail.

### Screening and limitations

The candidate settled in **15/15** screening cases, rerun for 60 seconds:

1. Nominal measured plant.
2. Each of the **three individual measured length/damping pairs**.
3. Starting angle ±1° from down.
4. Starting cart position ±5 mm.
5. Effective length 163 mm or 169 mm.
6. Equivalent damping 0.32 s⁻¹ or 0.48 s⁻¹.
7. Added encoder delay 2 ms.
8. First-order actuator lag 5 ms.
9. Physical velocity tracking fraction 0.98.

These are mostly one-factor-at-a-time tests, **not a probability of hardware success**. The same cases helped select the candidate, so this is screening rather than independent validation. Additional checks passed at ±10 mm cart offset, ±2° initial angle, 10 ms lag, and half integration step. It **did not settle** at tracking fraction 0.95 or in a combined case with length 163 mm, damping 0.48 s⁻¹, 5 ms lag and +5 mm starting position. There is no general robustness guarantee.

[Full results](settling_validation.json) include every test, explicit settings, metrics and the engine SHA-256. [Nominal trace](settling_trace.csv) preserves playback/export data.

## Why these are plausible motor test limits

For the configured 60T GT2 pulley, travel per revolution is 0.12 m and pitch radius is 0.01910 m:

- **0.55 m/s = 275 rpm**, versus 750 rpm at the recorded 1.5 m/s ceiling.
- At 200 steps/revolution and 1/16 microstepping: **14.67 kHz**, well below the recorded 62.5 kHz pulse ceiling. Pulse-rate margin is not torque margin.
- Ramping acceleration from zero to 3 m/s² at 25 m/s³ takes **120 ms**; to 5 m/s² takes **200 ms**.
- For an **illustrative, unmeasured 0.5 kg translating mass**, basic inertial torque `M × a × pulley_radius` is **0.0286 N·m** at the swing cap and **0.0477 N·m** at the braking cap. Each additional newton of drag requires approximately **0.0191 N·m** before transmission loss. Pendulum reaction, rotor/pulley inertia, friction and efficiency require additional torque; these figures are not a complete motor-sizing calculation.

These are lower command demands than the recorded 6 m/s², 150 m/s³, 1.5 m/s settings. They are a plausible starting candidate for a light, freely moving cart with a suitable 24 V NEMA 17 drive, **not established limits of the unidentified motor**. Frame size alone does not determine the available running torque. The motor model, actual phase-current limit and moving mass have not been supplied, so no defensible hardware torque margin can be claimed.

Manufacturer evidence: the [Big Easy Driver documentation](https://www.schmalzhaus.com/BigEasyDriver/) specifies operation up to about 2 A/phase and a suitable supply range including 24 V; it does not guarantee motor acceleration. [STEPPERONLINE's speed guidance](https://help.omc-stepperonline.com/hc/s/articles/max-motor-speed-and-recommend-motor-speed) explicitly makes practical speed conditional on driver voltage, load inertia and other operating conditions. Its [example 24 V NEMA 17 torque curve](https://www.omc-stepperonline.com/download/17HS16-2004S-C5_Torque_Curve.pdf) is for a specific 17HS16-2004S-C5 motor, DM332T driver and current/microstep setup; it must not be treated as the installed motor's curve. No holding-torque rating was substituted for running torque in selecting this candidate.

## Search and reproduce

The first 210-case limits-only grid found nominal solutions around 5 m/s², 30 m/s³ and 0.8 m/s, but they failed some plausible plant variations. Another 315 equal-cap and 576 split-cap evaluations improved nominal behavior, but did not pass the full screen. The final seeded search evaluated **2,000** bounded combinations of limits and swing gains: **92** settled nominally and **28** settled for all three individual calibration fits. The selected candidate was the only one in that sample to pass all 15 screening cases. This is a sampled search, not proof of a global optimum or infeasibility at lower limits.

```sh
node simulator175/search_settling.js
node simulator175/validate_settling.js
```

The first command writes search evidence; the second validates the selected candidate and rebuilds the preset, validation JSON and nominal trace. The preliminary searches are retained as `search_limits.js`, `search_refinement.js`, and `search_split_caps.js` with their JSON results. All searches run from the repository root and use the unchanged nonlinear engine.
