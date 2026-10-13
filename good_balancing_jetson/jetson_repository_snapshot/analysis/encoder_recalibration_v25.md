# v25: measured upright reference after the 125 mm arm swap

## Why recalibration came first

The user reported hard reversals inside the rail. The last two v24 sessions
remained inside roughly ±134 mm by commanded-step position, but reached
8.64–10.017 m/s² braking acceleration and spent 40–50% of active time in rail
recovery. Runtime settings were vmax=1.2, amax_s=amax_b=16, jmax=50–75.
Rail handoff speed stayed below .119 m/s and acceleration at or below 1.5 m/s².
The initial brake still uses the larger swing/balance acceleration cap.

More importantly, two `zero` operations recorded an angle about 48–49° from
the expected hanging direction. The user confirmed the arm was hanging freely.
`zero` records a diagnostic down reference; it does not replace the fixed upright.
The old upright raw3416 was therefore no longer a valid reference for this setup.

## Capture and rechecks

All motors were disabled. Twenty CRC-checked raw readings were saved per pose.
The first upright and left poses gave inconsistent quarter-turn spacing, so the
user rechecked both against a physical level/square. Original readings and the
two independent rechecks are retained, with hashes in the selected report.

| Physical pose | Selected raw count | Error from uniform scale anchored at down |
|---|---:|---:|
| Down, 0° | 1929.00 | 0° |
| Toward +cart, 90° | 918.65 | −1.20° |
| Upright, 180° (rechecked) | 3953.35 | +2.08° |
| Toward −cart, 270° (rechecked) | 3161.95 | −18.36° |

[Selected readings](../encoder_calibration/125mm_20260917/selected_calibration.json)
and [linearity plot](../encoder_calibration/125mm_20260917/selected_calibration_linearity.png).
The initial upright was 3773.15; its replacement was 3953.35. The initial left
pose was 3208.15; its replacement was 3161.95. Rechecks supersede rather than
erase these observations.

## Applied source change

Firmware v25 uses **upright_raw=3953**, the nearest count to the reference-checked
upright mean. This shifts the old reference by **47.20°**. Every control path
using encTheta—balance, capture, swing-up, observer and telemetry—uses this
reference. `home` remains cart-only; `zero` remains diagnostic. Zero messages
now print the shared reference constant instead of a hard-coded number.
Counts/turn remain 4096 and ENC_INVERT=0. No nonlinear mapping was fitted from
these four poses. Gains, motion limits, rail recovery and 35 rad/s spin trigger
remain unchanged so this correction can be assessed separately.

## Remaining hardware/measurement issue

The left-horizontal deviation remains large after the recheck. The down pose
had AGC=128 and ML set on all 20 readings, while the upright recheck had AGC=90
and no weak-field flag. There were no stale/invalid samples or reported I²C errors.
This does not prove the source of the nonlinearity: magnet centering/gap,
mechanical alignment or remaining reference-placement error need review.

The AS5600 defines ML as weak field / gain overflow, and recommends gain near
mid-range; its 3.3 V range is 0–128. Inspect magnet centering, gap and secure
attachment through a full turn, then repeat the four-pose check.
[Manufacturer datasheet, status and AGC registers](https://look.ams-osram.com/m/7059eac7531a86fd/original/AS5600-DS000365.pdf).
Updating the upright target does not establish accurate angles throughout the
whole revolution or prove the braking complaint is fully resolved.

## Validation / deployment

Encoder-reference and serial-parser/watchdog harnesses pass. Simulator and ESP32
build results are recorded in the current configuration. **v25 is uploaded and serial-verified; motion was not tested.**
[Readback](v25_upload_verification.json) confirms upright3953 and disabled idle.
All calibration sessions ended with STOP and the serial port closed.
