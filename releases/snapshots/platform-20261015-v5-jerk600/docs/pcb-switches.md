# PCB switch wiring and bounded homing

Electrical inspection performed 2026-10-13 against the current original design, read-only. Source hashes, net nodes, pad UUIDs, routed segment UUIDs, and Gerber comparisons are recorded in `evidence/phase3/pcb-switches.json`. This establishes design intent and connectivity; it does not establish which revision was assembled or commission the hardware. On 2026-10-14 the owner confirmed switches 1 and 2 are installed, with 1 at the left and 2 at the right. Switches 3 and 4 are not installed. Electrical polarity, disconnect response and homing direction still need physical commissioning.

## Verified wiring

| Switch label | PCB connector | Signal pad | Teensy GPIO / carrier pad | Parallel screw-terminal signal | Pull-up |
|---|---|---|---|---|---|
| limit_switch_1 | J8 | 1 | D26 / U3 J6_4 | J5 pin 9 | R5, 1 kΩ to 3.3 V |
| limit_switch_2 | J11 | 1 | D27 / U3 J6_3 | J5 pin 10 | R6, 1 kΩ to 3.3 V |
| limit_switch_3 | J10 | 1 | D28 / U3 J6_2 | J5 pin 11 | R7, 1 kΩ to 3.3 V |
| limit_switch_4 | J9 | 1 | D29 / U3 J6_1 | J5 pin 12 | R8, 1 kΩ to 3.3 V |

For every J8–J11 connector, solder pad **1 (square, SIG) to the switch NC terminal** and pad **2 (round, GND) to COM**. Leave NO unused. The footprint description explicitly states this wiring. Each signal is independently routed; these are not a series chain. J5 provides parallel access to the same signals, with ground at J5 pin 1; J5 pin 2 carries +12 V and is not a switch supply. Use connector/pad numbers when working from the underside because the view reverses.

The pull-ups connect to U3 J7_2, the carrier's 3.3 V output, and not to 5 V or motor power. A closed NC contact reads LOW (healthy, unpressed), and an actuated NC contact reads HIGH (opened). An unplugged/broken wire also reads HIGH. Nominal closed-contact current is 3.3 mA per input. A short to ground cannot be distinguished from a healthy closed contact; homing must require observed open and close transitions to catch a stuck-low channel. The PCB contains no series input resistor, capacitor, RC debounce, optoisolator, or added clamp on these channels. Configure GPIOs as inputs, never outputs; internal pull-up can supplement the fitted external pull-up but must not substitute for confirming R5–R8 are populated.

[The PJRC reference card](https://www.pjrc.com/teensy/card11b_rev3_web.pdf) confirms Teensy 4.1 GPIOs are not 5 V tolerant. These connectors are for dry contacts to ground; an externally powered switch output must meet the 3.3 V input requirement.

## Driver enable and pin reservations

GPIO D8 (U3 J7_10 / J4 pin 10) is a single direct copper net connected to Enable pin 1 on cart U2, left U4, and right U5. There is no AND/OR gate, switch-to-enable connection, or independent per-driver enable on this board. A limit opening does not directly stop a driver: firmware must suppress all step pulses and raise D8. The Big Easy Driver enable convention is LOW enabled, HIGH disabled, consistent with the archived working firmware and [the SparkFun hardware guide](https://learn.sparkfun.com/tutorials/big-easy-driver-hookup-guide/hardware-overview). The carrier board adds no pull-up/down to D8. Driver module logic jumpers and module-local bias are outside this PCB and were not physically inspected; reset/high-impedance D8 is therefore not proven fail-safe. Firmware must establish disabled D8 before enabling step outputs. Shared disable de-energizes the Z drivers too; mechanical holding/support cannot be inferred from this schematic.

| Function | Reserved Teensy GPIOs |
|---|---|
| Cart step / direction | 2 / 3 |
| Left Z1 step / direction | 4 / 5 |
| Right Z2 step / direction | 6 / 7 |
| Shared driver enable | 8 |
| Magnetic encoder SDA / SCL | 17 / 16 |
| MPU6050 SDA / SCL / interrupt | 25 / 24 / 38 |
| Carrier LCD CS / DC / MOSI / SCLK / reset / backlight | 10 / 9 / 11 / 13 / 32 / 33 |
| Switch inputs | 26 / 27 / 28 / 29 |

Switch GPIOs do not overlap these functions. Carrier J6_* and J7_* identifiers are PCB pad identifiers; they are not Arduino GPIO numbers. The magnetic encoder measures pendulum angle; there is no cart linear position feedback in this PCB. Homing positions and measured stroke are based on issued step counts, so lost steps are not independently detected.

## What the PCB does and does not establish

All exported schematic component pad nets match corresponding PCB pad nets, with zero mismatches. Routed segment/via chains join each switch signal to its pull-up, Teensy pad, and J5 pin; the pull-up rail joins U3 3.3 V. D8 joins all three driver enable pads. GND is assigned to every switch pad 2 and represented by filled copper zones on both board layers. No electrical gates occur in the component inventory.

The PCB labels only `limit_switch_1` through `limit_switch_4`. It does **not** identify cart negative/positive ends, Z reference locations, motor positive direction, switch trigger positions, mechanical travel, homing order, or gravity behavior. The cart assignment below is now confirmed by the owner; the Z assignment remains a recommendation, not a deduction from the design:

| GPIO | Recommended installation role |
|---|---|
| 26 / J8 | Cart left / negative end (installed) |
| 27 / J11 | Cart right / positive end (installed) |
| 28 / J10 | Z1 reference |
| 29 / J9 | Z2 reference |

This mapping must be the same in firmware, console labels, harness labels, and physical installation. Z reference polarity and geometry need commissioning before Z homing is enabled. Two Z inputs support one reference switch per Z motor under this mapping; they do not provide upper and lower limits on each Z axis. A different four-input allocation is possible, but software must explicitly configure and validate it.

## Production and switchless commissioning

Production starts disabled and unhomed, samples all configured required channels, and refuses motion when any NC channel is HIGH outside an expected homing contact phase. Treat raw HIGH as an immediate pulse-inhibit condition. Do not delay a normal-operation stop for debounce. Latch faults, raise shared enable, invalidate homed state, and require an explicit reset and new homing request; clearing an input must never automatically restart motion. A production reset requires healthy stable inputs.

The `executor-v2-cart2` build requires the two installed cart switches by a fixed compile-time mask `0x03`. Uninstalled D28/D29 remain raw telemetry only, and both Z step outputs are blocked. It never infers installation from levels or bypasses a missing cart input. The former all-four-input profile rejected HOME when uninstalled 3/4 read HIGH. A separate explicit switchless commissioning profile may permit previously bounded operator motion from the operator-declared center with conservative software limits. It must expose that limits are absent, expire with the motion lease/watchdog, and never report physical homing or use missing inputs as evidence of end position. It must not silently select itself from all-HIGH inputs or persist as the default after reset. Physical limit events or any unexpected opening of channels that are installed still stop motion.

## Recommended cart homing state machine

A homing request owns motion exclusively. Other move, auto, and external-policy commands are rejected until it finishes or cancels. Configure direction, maximum seek steps/distance, elapsed-time deadline, slow approach speed, backoff distance, release deadline, acceptable measured stroke interval, and chatter budget explicitly. Direction and stroke are installation parameters, not PCB facts. Use finite bounds for every phase and the entire operation; a step budget alone cannot detect an unpowered/stalled motor and a time budget alone cannot contain a wrong speed.

1. **Precheck:** require commissioned mapping/direction, no commissioning bypass, healthy fresh samples, zero commanded speed, drivers disabled, and both cart contacts stable LOW. Reject an already-HIGH contact because the input cannot distinguish a pressed switch from a disconnected wire. The operator must release/repair it before a fresh request. D28/D29 are not required by this cart-only build.
2. **Seek negative:** emit bounded negative cart steps at the configured seek speed. Stop pulses immediately on raw D26 HIGH. Any D27 opening is an unexpected-limit fault. While stopped, require D26 to remain HIGH for the debounce interval (5 ms is a recommended starting value); excess chatter or deadline expiry faults.
3. **Back off negative:** permit only bounded positive recovery steps while the expected D26 contact is HIGH. Require stable LOW within the release budget, then continue to the configured clearance. An opposite cart opening always faults. Backoff is allowed only by this state; arbitrary motion into an open circuit is prohibited.
4. **Slow negative latch:** approach negative at the lower latch speed, stop immediately on HIGH, verify stable contact while stopped, and capture the negative edge step count. Back off until stable LOW plus clearance. Failure to reopen or reclose within budgets faults.
5. **Seek and latch positive:** repeat the seek, release/backoff, and slow reapproach sequence for D27 with reversed directions. Capture the positive edge. D26 must remain healthy during the positive seek.
6. **Validate span:** require positive edge > negative edge and a stroke inside the configured acceptable interval. Reject impossible, zero, reversed, or implausibly small/large spans. Store this as measured step span, not externally measured rail length.
7. **Center:** move at a bounded speed to the step midpoint using counted pulses, with both cart contacts stable LOW and software margins inside the measured edges. Require the commanded center to be reached within the step/time budgets. Only then set the center coordinate to zero, publish a new homing epoch/span, mark the cart homed, and finish disabled.

All phases cancel immediately on operator stop, lease/watchdog expiry, communication loss, unexpected raw limit, both cart contacts HIGH, invalid input/configuration, excessive chatter, total deadline, phase timeout, or step budget violation. A fault must never zero coordinates or preserve an old homed flag. The expected homing contact is allowed only to stop an approach and permit finite motion away from it. Debounce qualifies contact/release transitions while the immediate raw stop remains active. Schedule input sampling with the pulse generator so no further pulse can be issued after the raw trip has been sampled; document measured sample-to-inhibit latency during commissioning.

A single-end homing variant can reference a known endpoint only with an explicitly commissioned stroke; it cannot discover the rail center from this PCB alone.

## Z homing boundaries

Z1 and Z2 can each use one configured reference contact, a bounded seek, stable trigger, bounded release, slow reapproach, and a final offset. Keep Z homing disabled until mounting, safe direction, finite available stroke, clearance, and shared-disable mechanics are verified. Do not infer a safe simultaneous squaring routine or allow an unbounded second Z to keep moving when the first triggers. A paired routine needs independently bounded pulse counts, a maximum skew limit, and verified mechanics, even though the motors share enable. Cart homing and Z homing should be explicit operations; their order depends on verified mechanical clearance.

## Verification limits and commissioning checks

The current PCB copper geometry, re-exported with KiCad 10.0.6, matches the copper Gerbers in `gerbers/`, `gerbers/gerbers_final/`, and `gerbers 2/` exactly after removing only metadata/comments. The older root-level September 24 copper Gerbers differ. Match the assembled board to the documented pinout before soldering. The original design was not edited. KiCad CLI full DRC with schematic parity terminated with exit 134 and produced no report, so this inspection is not a passing DRC claim. Manual pad parity and selected routed connectivity checks succeeded.

Before any homing motion: with driver power disabled, verify R5–R8 population, SIG-to-corresponding-Teensy continuity and absence of cross-wiring, ground continuity, LOW unpressed/HIGH pressed and disconnected telemetry for each channel, and the console's physical role labels. Validate pulse direction with a bounded commissioning move, then test raw limit stop and fault reset. Only after those checks run the finite homing routine and measure stroke repeatability, center error, latency, and available stopping clearance. None of these physical checks have been performed for the new switches.
