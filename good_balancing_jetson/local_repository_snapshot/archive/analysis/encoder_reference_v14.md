# v14: use the recorded upright count as the balance reference

Source: `encoder_calibration/encoder_20260916_135926_031977.json`.

| Reference | Saved raw count | Unwrapped count | Error from ideal scale anchored at down |
|---|---:|---:|---:|
| 0° down | 1403 | 1403 | 0° |
| 90° toward +cart | 597 | 597 | −19.16° |
| 180° upright | 3416 | −680 | +3.08° |
| 270° toward −cart | 2650 | −1446 | −19.60° |

Counts decrease in the chosen reference direction. Unwrapping removes the
4095→0 discontinuity so linearity can be compared with a straight line.
The four quadrant spans are 806, 1277, 766 and 1247 counts; an ideal encoder
would give 1024 each. These saved points deviate substantially from that model.
A single manually positioned reading per pose does not isolate encoder error.

## Data integrity limits

The session contains missing/corrupted serial characters. In particular the
upright snapshot reports `zero_raw=403` while the other three report 1403,
without a zero command between them; its status field is also 3 rather than
103. Other lines visibly lose characters. Those fields cannot be treated as
reliable sensor evidence. The requested upright raw count **3416** is used exactly
as saved; its accuracy should be checked at physical upright after flashing.
No nonlinear remapping is fitted to these four readings.

## Firmware change

`swingup/encoder_reference.h` sets `upright_raw=3416` and
`encTheta()` now returns the wrapped difference from this absolute raw count,
scaled by 2π/4096 (with existing ENC_INVERT polarity). The observer, capture gate,
balance law, energy calculation, spin monitor and telemetry share this reference.
At raw 3416, measured theta is exactly zero. The observer may have transient
lag during motion, but a stationary reading there converges to zero.

Previously the target was startup-down + 2048 counts: for down=1403, raw 3451.
The measured target changes that by −35 counts, or −3.076° in the encoder's
positive-count direction. Boot/manual down-zero still records a diagnostic
reference but cannot overwrite the calibrated upright. `params` reports
`encoder_upright_raw 3416`. Remounting the encoder/magnet would require an updated
absolute calibration. Gains and motion limits remain 0.8/12/12/60.

## Validation

- Actual `encTheta()` compiled into a C++ harness: raw 3416 produces zero;
  changing relative ticks/down-zero does not shift it; sign around upright,
  4095→0 continuity, opposite polarity and full-count-range bounds pass.
- Existing firmware serial/watchdog and GPIO/DDS disable tests pass.
- ESP32 compile passes: 339,587 program bytes, 22,736 global bytes.
- All 14 simulator test groups pass with the updated configuration/source hashes.
- Software validation only. Firmware has not been uploaded and physical balance
  at the recorded target has not been tested.

Reproduce the plot with:

```bash
python3 analysis/plot_encoder_calibration.py encoder_calibration/encoder_20260916_135926_031977.json
```
