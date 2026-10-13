# Simple software-stepped sine-wave cart

Open `cart_simple.ino` in Arduino IDE, select **ESP32 Dev Module**, and upload.
No additional Arduino library is required. Open Serial Monitor at **115200 baud**
with **Newline** selected. The sketch starts idle and treats its reset position
as center. Physically center the cart before powering/resetting it.

```text
sine 25 0.5
```

Amplitude is millimeters **each way**: this requests ±25 mm at 0.5 Hz.
`stop` shrinks the amplitude and returns toward center; `halt` stops in place.
`center` physically returns toward the stored center, whereas `zero` declares
the current position to be center. `help` lists the remaining commands.
These commands differ from the [FastAccelStepper sketch](../cart_sine/README.md).

This existing sketch is retained without changes to its motion code. It uses
software pulses with a 10,000-pulse/s ceiling (375 mm/s at its calibration).
STEP is GPIO18, DIR is GPIO19, and shared active-LOW ENABLE is GPIO27; the old
inline D25/D26 comments do not match the numeric pin assignments.
Calibration is **200 full steps/rev, 1/16 microstepping, 60T GT2, 120 mm/rev**,
or 26.667 pulses/mm. The repository's `swingup` sketch also uses this 60T conversion; wiring and motion commands differ.

The existing `MAX_AMP_MM = 400` is an input ceiling, not protection for the
repository's 300 mm rail. Choose amplitude to fit the actual centered travel.
Position is inferred from pulses; there is no homing or physical cart feedback.
Shared ENABLE also controls the height motors, so `disable` releases them.

From the repository root, compile both standalone cart sketches with:

```sh
./scripts/build_cart_sketches.sh
```

The build script compiles only; it does not upload or move hardware.
