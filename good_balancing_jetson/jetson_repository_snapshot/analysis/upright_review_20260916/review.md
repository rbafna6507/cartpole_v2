# Upright physical runs: direction and reference checks before inertia or gain changes

## Finding

**A mismatch between cart motion direction and encoder angle sign is the leading suspect.** The user reports that in most trials they released the pole, briefly held it in one trial, and thinks the cart moved away from the falling side. Near upright, the stabilizing cart action is toward the falling side. A relative polarity error turns angle/rate feedback into positive feedback.

No firmware settings, serial connection, or physical motion were changed during this review.

## Evidence from the actual runs

Primary source: `logs/run_20260916_152135.csv` and its event sidecar, firmware **v18**. Nine `bal` requests: seven accepted, two rejected. Every accepted trial used the same settings: `bal_pw=8`, `pz=.85`, cart poles −.8/−1.2, bandwidth 10 Hz, limits **.8 / 12 / 12 / 60**. This is not a comparison between gains 7 and 8.

The earlier `145702` session contains automatic v16 attempts and a board-clock reset; it is not pooled with the upright trials.

| Trial | Last sampled angle before start | BALANCE sample span to abort | First recovery angle | First recovery cart speed | First recovery inferred position |
|---|---:|---:|---:|---:|---:|
| 1 | −0.35° | .201 s | +12.2° | +.465 m/s | +36.6 mm |
| 2 | +3.78° | .081 s | +13.4° | +.419 m/s | +18.6 mm |
| 3 | −1.50° | .605 s | +17.6° | +.792 m/s | +33.8 mm |
| 4 | +1.67° | .161 s | +12.4° | +.502 m/s | +25.4 mm |
| 5 | −2.29° | .161 s | −12.8° | −.508 m/s | −25.8 mm |
| 6 | +2.64° | .122 s | +21.4° | +.520 m/s | +34.1 mm |
| 7 | +2.73° | .162 s | +17.8° | +.535 m/s | +32.5 mm |

These durations have approximately one 40 ms telemetry interval of boundary uncertainty; the first telemetry row is not the exact accepted-start state. Event receipt times also include UART/host delay. The user did not identify which trial included hand contact, so no individual trial is asserted to be a clean release.

**All seven exits were predictive rail aborts, not the 50° angle cutoff.** Their inferred positions were still only 19–37 mm from center, but their outward velocity/acceleration required most of the remaining rail to brake. The recovery trajectories then peaked at **128–132 mm**, and all seven ended in IDLE within **1.5–1.9 mm** of the inferred center. Do not remove or postpone this rail protection to seek longer balance time.

The balance samples only reached **3.37–5.87 m/s²** acceleration, below the 12 m/s² cap. A higher acceleration ceiling is therefore not the first remedy. Several acceleration slopes approach the jerk limit, so acceleration slew matters once polarity/reference are correct. At 60 m/s³, a +5 to −5 m/s² reversal takes at least **167 ms**; the current pendulum's gravity-only characteristic falling time is about **130 ms**. This comparison is explanatory, not an instruction to increase jerk.

Telemetry had a median 40 ms interval and maximum 94 ms gap, no logged parser/reader/timeout errors, and sampled BALANCE loop execution up to 763 μs. These observations do not establish all control deadlines or actual motor tracking. `x`, `v`, and `accel` are pulse-based commands; no cart encoder measures physical motion.

[Trial traces](upright_trials.png) · [Machine-readable review and source hashes](review.json)

## Hypothesis comparison

`compare_models.js` runs an isolated copy of the existing nonlinear simulator. It changes only the sign of cart acceleration's effect on the pole and, separately, a possible angle-reference bias. The production simulator/firmware remain unchanged. Initial states come from the last pre-start telemetry samples, not a fitted release model. Assumptions include perfect acceleration tracking, calibrated length/damping, and no hand contact.

| Assumption | Seven starting states |
|---|---|
| Existing model: correct relative direction, accurate upright zero | 7/7 remain balanced through 10 s |
| Reverse the cart-to-pole acceleration relationship | 7/7 abort; first aborts at .104–.221 s |
| Correct direction but 2.90° reference bias | 7/7 abort at .500–.878 s |
| Reversed direction and 2.90° reference bias | 7/7 abort at .104–.172 s |

The reversed-direction experiment resembles six short hardware failures far better than the nominal model. This, combined with the user's observation, makes direction the highest-priority check. It is not conclusive identification: hand contact, actuator tracking, encoder geometry, and unmeasured delays remain possible contributors. An approximate raw-angle-curvature regression also prefers a reversed response but has large residuals; it is explicitly not used to claim an identified delay or motor gain.

[Reproducible model comparison](model_comparison.json)

## Recommended order of work

1. **Verify the physical sign relationship at low speed.** With the pendulum hanging and the cart near center, identify which physical way a positive manual cart command moves. Stop the cart; lean the pole toward that same direction and verify that reported upright error is positive. In a balance attempt, the first corrective movement must chase the falling side. If encoder sign is correct for the chosen +x direction but positive motor commands move the opposite way, invert the cart direction mapping only. If motor mapping is correct but encoder sign is opposite, invert encoder sign only. `CART_INVERT` and `ENC_INVERT` are the relevant source constants; changing both preserves the relative sign error. Do not run more high-gain attempts as a substitute for this check.
2. **Recheck true vertical independently.** The first 207 stationary samples report hanging at **−3.091 rad**, with only .092° range. Under a uniform encoder scale, the opposite gravitational upright would be **+2.899°** relative to the stored target, approximately raw count **3449 instead of 3416**. This is a hypothesis, not permission to overwrite the calibrated target: one rest angle can be biased by pivot friction, the arm's center-of-mass direction, encoder nonlinearity, or holding. Compare repeated free hanging approaches from both sides with an independently aligned upright pose. A few degrees of target bias can force continuous cart drift.
3. **Then retest the existing gains before changing the mechanism.** Start nearly vertical and compare `bal_pw=7` against 8 with matched releases. Keep travel/jerk/speed/acceleration bounds fixed. If failures persist after direction and reference are established, measure cart motion versus commanded pulses using an encoder or time-synchronized video, and log angle, estimated angle/rate, requested acceleration, applied acceleration, and exact start/abort board timestamps. Higher-rate local buffered logging is preferable to assuming the present 25 Hz stream captures release and reversals.
4. **Make the model account for real actuator behavior before further gain optimization.** Measured actuator lag, deadband/missed steps and current acceleration are more useful next additions than an integral term. The present controller assumes acceleration can be requested immediately; the governor then changes it at a bounded rate. Once tracking is characterized, an acceleration-state controller or a short prediction horizon with jerk/rail constraints is a reasonable improvement to evaluate offline. It is not yet demonstrated necessary or superior on this hardware.

## Added inertia: what helps and what does not

For a rigid pendulum with pivot inertia `I_p` and gravitational first moment `S = Σ m_i r_i`:

```text
I_p * theta_ddot = S * (g*sin(theta) - a*cos(theta)) - damping torque
L_eff = I_p / S
characteristic falling time ≈ sqrt(L_eff/g)
energy increase from down to up = 2*g*S
```

The prescribed-cart-acceleration form follows the passive pendulum equation; the standard cart-pole equations and energy-based swing-up formulation are in [MIT's Underactuated Robotics notes](https://underactuated.mit.edu/acrobot.html). The pivot-inertia/center-of-mass generalization and calculations here are our derivations.

**More tip weight at the existing 175 mm radius provides very little slowing.** Measured `L_eff` is already **165.8 mm**. Adding point mass at radius `r` gives `(I_p + Δm*r²)/(S + Δm*r)`, which approaches `r` as mass grows. Thus for added mass at 175 mm, even the limiting falling-time improvement is only **2.74%**. Each additional 10 g there raises the swing-up energy barrier by approximately **34.3 mJ** and adds moving load. Actual inertia/first moment cannot be inferred from arm mass alone; the saved 14.2 g arm and two 5.85 g endpoint weights do not specify all mass locations.

**A longer effective pendulum offers a meaningful time benefit:**

| Effective length (not necessarily physical rod length) | Characteristic falling time | Increase from current |
|---|---:|---:|
| 165.8 mm, measured current | 130 ms | — |
| 225 mm | 151 ms | 16.5% |
| 250 mm | 160 ms | 22.8% |
| 300 mm | 175 ms | 34.5% |

These are design-study targets, not recommended modifications yet. Increasing length or relocating mass also changes swing-up energy, pumping response, clearance, friction and load; controller length and energy logic must be retuned.

Another possibility is adding rigid inertia with little net first moment, such as a balanced crosspiece or a ring centered on the pivot. That slows gravitational divergence without the same increase in the down-to-up gravitational energy barrier, but it also weakens angular response to cart acceleration and adds cart load/friction. It does not provide free control authority.

**Swing-up compatibility has not been established for a modified arm.** A limited 28-case ideal-actuator screen varied effective length (.166/.225/.25/.30 m) and energy gain (1/2/3/4/5/6/8), with matching controller length and unchanged motion limits. None sustained balance; six current-length cases briefly captured, while longer cases did not capture. This small search does not prove longer arms cannot swing up. It does rule out promising that a simple inertia increase will work with the current controller/settings. [Screen results](length_swing_screen.json)

The immediate recommendation is to establish correct direction and vertical reference, then evaluate the existing arm. Those corrections are likely to matter substantially more than extra tip mass.

## Reproduce

```sh
cd /Users/sajivshah/Documents/GitHub/cartpole_inverted_pendulum
python3 analysis/upright_review_20260916/review.py
node analysis/upright_review_20260916/compare_models.js
```
