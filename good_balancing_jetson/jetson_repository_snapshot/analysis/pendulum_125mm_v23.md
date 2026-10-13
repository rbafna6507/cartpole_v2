# v23: restore the measured 125 mm arm

Prepared firmware `swingup-125mm-60t-v23`; **not uploaded or physically tested**.

The user corrected the original 100 mm label: that arm was always **125 mm**,
mass **11.05 g**, with the same **two 5.85 g end weights**. Combined mass is
**22.75 g**. The user explicitly identified the pre-175 mm recordings as this
arm. The initial scaled-length estimate was replaced with a fit of those data.

## Calibration used

Seven earlier recordings were examined using the same low-angle cycle selection
as the 175 mm fit. Three contain at least six qualifying cycles each, for
**20 cycles** total. Four shorter low-angle records are excluded by that
criterion; they remain preserved. No raw recording or original metric changed.

- Median small-angle period: **0.7077035 s**.
- Effective length from the measured period: **0.124454888 m**.
- Firmware effective length: **0.124 m**, rounded to 1 mm.
- Simulator equivalent viscous damping: **0.913383 s⁻¹**.

[Corrected configuration, source selection and fit](../pendulum_characterization/125mm_11p05g/2026-09-15/README.md).
The raw folder keeps its old name for existing links; the manifest now labels
its geometry correctly and retains the previous classification as provenance.
Archived 175 mm data and presets retain their own geometry and measurements.

## Controller changes

The acceleration-input controller uses effective length, rather than a separate
mass multiplier. The new `leff` automatically updates automatic balance gains,
upright-only gains, swing-up normalized energy and the capture prediction.
Pole choices remain pw=7, bal_pw=8, pz=.85, pc1=−.8, pc2=−1.2; energy/centering
gains remain ke=2, kpx=30, kdx=.5. These are not LQR weight changes.

Automatic balance uses `a = -(k1*theta + k2*theta_dot + k3*x + k4*v)`:

| Gain | 175 mm / leff=.166 | 125 mm / leff=.124 |
|---|---:|---:|
| k1 | −22.186294 | −19.029970 |
| k2 | −2.614769 | −1.895109 |
| k3 | −0.795988 | −0.594593 |
| k4 | −1.851619 | −1.383137 |

60T pulley, cart STEP25/DIR26, 300 mm rail, v22 controlled rail recovery,
vmax=.8, amax_s=amax_b=12, jmax=60 and fixed upright encoder count 3416 remain.
No motor command or serial connection was made during preparation.

## Validation

- ESP32 compilation passes: 342447 program bytes, 22720 global bytes.
- 17 simulator groups pass, including C++/JavaScript gain and motion parity,
  current-versus-historical preset geometry, measured decay and recovery checks.
- Capture gate, GPIO/driver-disable and serial-parser/watchdog harnesses pass.
- Browser checks pass: current 125 mm preset, historical presets, four input
  styles, 27-case sweep, calibration/recording views, exports and mobile layout.
- Source hashes preserve the original calibration recordings.

The current default simulated swing-up does not establish sustained balance;
passing tests verifies the model/configuration and protections, not hardware
swing-up success. The existing measurements support restoring this arm's model.
A new free-swing check is useful if reassembly changed pivot friction or weight
position; if the shaft/magnet was re-indexed, check the upright encoder reference.
