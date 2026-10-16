# Manual free-decay training freeze, 2026-10-16

**No physical model is accepted or installed.** The declared viscous comparison passes training checks and is frozen as the candidate for a separate heldout recording. The predeclared viscous+Coulomb primary model rejects because its fitted viscous damping is negative. No heldout data were read, no threshold was relaxed, no reference or calibration was changed, and neither MuJoCo nor the controller was modified.

The original forced-input characterization remains rejected. This is a separate passive estimate of pole dynamics, conditional on a fixed cart, free motion after release and valid angular measurement. It cannot identify cart/pole masses, input gain, motor force/friction, physical actuator delay or absolute hinge torque.

## Sources and admission

Original source directory: `/home/rbafna/cartpole-v2-runs/system-id-20261016/manual-ringdown-train-02/`. The compact lossless column export `columns.json.gz` is 939500 bytes, SHA256 `47cac6f910a794cbae30a4c3e90a3a0036beacb65f26b7deee7bf7fcd068b37e`. It preserves selected original columns without interpolation. Original raw source identities:

| Source | SHA256 |
|---|---|
| `rig-1792182247276281695-187204064.jsonl` | `fc3f5cd4cb663f2f6e518a5b98f2738b3e173ad0bf6aeec5d5ede69fc0261229` |
| `vision.ndjson` | `1e764ceece29240740925a53400dcb94a465343fadbfc11d7dbe4b7631c61852` |
| `report.json` | `287003c3acc8ae4782ac918ad8f965295d777d4ef73a60686a58bcf0ffeef8af` |
| `vision-report.json` | `0a18b030ae69df447215461164cbe34b9f4e9574c823613ca8344f97fe07d908` |

There are 31730 state rows, including one identical board snapshot duplicate with a different host receipt timestamp. Equality of all other fields was verified before removing that duplicate, leaving 31729 unique states and 6301 camera rows over about 126.9 seconds. All recorded states have flags205, fault0, mode0: the driver remained disabled. Counted cart x is constant; a disabled step counter is not independent physical stationarity evidence. Reference330 and home epoch14 remain unchanged.

The user confirmed holding the cart **by hand throughout**, without a clamp. They reported three releases, but the trace contains only two clearly admissible periodic free-decay sequences. We do not invent a third. Irregular lifting/holding at approximately57.5–64.25 and72.75–79.4 seconds, the first release transient of each sequence and settled suffixes are excluded. The first, static manual-01 recording is not a fitting dataset.

## Frozen episode annotations

Time origin is the first board timestamp, `unwrapped_us=2800748050`. Boundaries were selected from motion/free-decay structure before fitting, not by minimizing residual. The frozen exact intervals are:

| Episode | Requested board-relative interval (s) | Included interval (s) | Board tick endpoints | Samples |
|---|---|---|---|---:|
| free_decay_1 |64.8–69.4|64.801–69.397|84465410–84470006|1150|
| free_decay_2 |80.0–87.4|80.001–87.397|84480610–84488006|1850|

No fitted window crosses an episode or a gap over50ms. Canonical selected raw magnetic and provisional camera arrays are in `manual-ringdown-train-02-selected.json.gz`; the large originals remain in the source directory. Future heldout episodes must be from another raw recording hash, annotated from release/handling structure without consulting fit residuals, with neither offset nor parameters refitted. Collect both release directions and at least20 usable weak windows total; preserve all camera losses rather than selecting only frames that make stationarity pass.

## Frozen coefficients and training checks

The model is `qdd = A sin(q) + B cos(q) - gamma qdot - c sign(qdot)`; the viscous comparison fixes c=0. `q` is the raw magnetic angle in radians. Effective length is `9.81/hypot(A,B)`. The reported offset is `atan2(-B,A)`: a **fitted gravity-phase offset in sensor coordinates**, not a uniquely established encoder-zero error. Static torque, geometric orientation, local angular distortion and model error can confound its interpretation. No reference330 correction is implied.

| Parameter or diagnostic | Frozen viscous candidate | Rejected viscous+Coulomb primary |
|---|---:|---:|
| A, s⁻² |60.64177253375597|60.73651765237396|
| B, s⁻² |6.8885413950367065|6.853590495372735|
| Effective length, m |0.16073596568158666|0.16049873073394127|
| Gamma, s⁻¹ |0.4631556778357131|−0.15334390446676427|
| Coulomb angular acceleration, rad/s² |0|2.1248699344276534|
| Fitted gravity-phase offset, rad |−0.11310915597373176|−0.11236603096224441|
| Integral NRMSE |0.10406585349424709|0.09758489279452653|
| Scaled condition number |1.3943053272208294|4.481178688188728|
| Weak windows / rank |32 / 3|32 / 4|
| Training checks |pass|**fail: negative gamma**|
| Heldout validation |not provided|not provided|

The smaller Coulomb residual does not override its physical rejection; gamma was not clipped. Selecting the already declared viscous comparison is based only on training. Both parameter sets and their status are preserved before heldout collection. `statistical_checks_pass` remains false and `recommended_model` remains null in every training-only report.

Unchanged passive gates are at least20 weak windows; angle span≥0.15rad; condition≤1000; length0.05–1.5m; gamma0–5/s; Coulomb0–20rad/s²; |phase offset|≤0.35rad; maximum within-segment gap50ms; integral NRMSE≤0.15. Independent heldout forecasts use0.5s horizons, past-only raw-angle initialization, at least3 prediction windows, angular RMSE≤0.08rad and p95 absolute error≤0.15rad, plus the same integral residual gate. `passive-plan.json` is unchanged from its pre-data freeze. Its SHA256 is `9f6cad7f95531bb33ef4ca3ad75ff36e6dd53e9c6de32a136e2a66fb317220a4`.

Measured same-direction crossing periods, using a52ms moving-average diagnostic and the training fitted hanging phase, are0.8053–0.8274s (median0.8163s) and0.8057–0.8550s (median0.8242s). These observed amplitude-dependent periods are consistent with a length near0.16m; the period diagnostic does not prove calibration, fixed cart or friction form.

## Provisional raw-camera comparison

Old live camera calibration is ignored. Raw image angle is transformed as `q_camera=unwrap(pi-image_angle_rad)` with an integer2π branch shift nearπ. This is an image-plane projection, not a calibrated world angle. Camera fitting retains original timestamps and splits gaps; it does not interpolate missing frames. Cross-sensor comparison alone interpolates magnetic angle onto camera host timestamps; camera exposure timing and encoder transport delay are uncalibrated.

| Diagnostic | Episode1 | Episode2 |
|---|---:|---:|
| Valid pivot frames / total |219 / 230|318 / 368|
| Valid geometry coverage |95.22%|86.41%|
| Pivot radial p95 / max, pixels |0.340 / 0.511|0.384 / 0.573|
| Longest valid camera gap, s |0.06165|0.10143|
| Frozen pixel stationarity diagnostic |pass|**fail: coverage and gap**|
| Image arm length min–max, pixels |165.14–176.51|164.34–176.27|
| Median magnetic−camera angle, rad |−0.12978|−0.12682|
| Offset-removed comparison RMS, rad |0.05543|0.07335|

Observed pivots are quiet, supporting the intended hand restraint, but the second episode fails the preset90% coverage and100ms gap checks. Missing frames cannot be assumed stationary. Pixel stability is not metric cart-motion proof and cannot exclude out-of-plane motion. Image arm-length variation and uncalibrated timing preclude treating the camera as a global angular calibration. A training-only linear camera comparison has scale≈1.057–1.058 and RMS≈0.053–0.069rad after offset/scale fitting; timing, projection and encoder distortion remain confounded.

As predeclared before any heldout read, the separate provisional camera viscous fit gives length0.1588148280927987m, gamma0.5663001511618595/s, fitted image-frame phase+0.014154947447730147rad, NRMSE0.041166493338412616,20 windows over15 continuous segments. Its similar length supports the period estimate, but it is not an accepted physical model. Camera Coulomb fitting has **zero usable windows** with derivative/sign support, and rejects. No sparse-gap interpolation or threshold change was used to force acceptance.

## Verification, reproduction and next decision

Eleven focused local tests passed, including independent synthetic recovery, bad heldout rejection without parameter changes, duplicate/reused data rejection, static and constant-speed handling rejection, gap isolation, stiction, raw pixel translation, absent-heldout semantics and sparse derivative support. A discovered degree-zero polynomial indexing failure was fixed by excluding Coulomb windows lacking at least two derivative-neighborhood samples; viscous fitting never needs that derivative. A review also reproduced that static heldout data could satisfy error-only checks; heldout now must meet the existing0.15rad excitation requirement. This admission correction was made before any heldout data were read and does not relax a threshold. Timestamp reversals are rejected before exact duplicate removal. The magnetic coefficients above are exactly unchanged. Tests are estimator verification, not hardware validation.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover \
  -s evidence/system-id-20261016/analysis -p test_passive_fit.py -v
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  evidence/system-id-20261016/analysis/analyze_manual_train_02.py \
  --input /tmp/manual-ringdown-train-02-columns.json.gz \
  --output-dir /tmp/manual02-fresh-reproduction
```

Exact candidate values, selections, source identities and file hashes are frozen in `manual-ringdown-train-02-summary.json` and `manual-ringdown-train-02-freeze.json`. The next admissible step is an independent disabled-driver manual heldout recording with explicit hand-clear releases and cart restraint. Assess it against these parameters without refitting. Failed physical admission or statistical gates must remain failures. Any later opt-in MuJoCo profile must retain its assumptions: mapping gamma to hinge torque damping requires an assumed pivot inertia (`gamma*I_pivot`); a uniform-rod surrogate has `I_pivot=0.75*m*L_eff²`. No input-gain or mass claim follows from passive success.
