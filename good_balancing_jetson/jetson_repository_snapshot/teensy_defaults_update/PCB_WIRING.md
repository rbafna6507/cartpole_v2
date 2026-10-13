# Wiring for the reviewed PCB

PCB references and Copperhill header references are different namespaces. In particular, PCB J5 is a screw terminal; Copperhill J5 is the unused I2C pad header. This mapping follows the uploaded PCB pad nets and the supplied working Teensy firmware. Confirm physical header pin 1 against the actual carrier before wiring.

| Function | Teensy GPIO | Copperhill header | PCB connection / exposed terminal |
|---|---:|---|---|
| Cart STEP | 2 | J7_4 | U2 pad 9; J4.4 |
| Cart DIR | 3 | J7_5 | U2 pad 10; J4.5 |
| Left/Z1 STEP | 4 | J7_6 | U4 pad 9; J4.6 |
| Left/Z1 DIR | 5 | J7_7 | U4 pad 10; J4.7 |
| Right/Z2 STEP | 6 | J7_8 | U5 pad 9; J4.8 |
| Right/Z2 DIR | 7 | J7_9 | U5 pad 10; J4.9 |
| Shared driver ENABLE | 8 | J7_10 | U2/U4/U5 pad 1; J4.10 |
| Encoder SDA / Wire1 | 17 | J7_13 | U1.3; J5.3 |
| Encoder SCL / Wire1 | 16 | J7_14 | U1.4; J5.4 |
| Limit 1 signal | 26 | J6_4 | J8.1; J5.9; R5 pull-up |
| Limit 2 signal | 27 | J6_3 | J11.1; J5.10; R6 pull-up |
| Limit 3 signal | 28 | J6_2 | J10.1; J5.11; R7 pull-up |
| Limit 4 signal | 29 | J6_1 | J9.1; J5.12; R8 pull-up |
| MPU SDA / Wire2 | 25 | J6_5 | J12.3; J5.8 |
| MPU SCL / Wire2 | 24 | J6_6 | J12.4; J5.7 |
| MPU interrupt | 38 | J6_7 | J12.5; J5.6 |
| Spare | 39 | J6_8 | J5.5 |
| Spare | 21 | J7_11 | J4.11 |
| Spare | 20 | J7_12 | J4.12 |
| 5 V output | — | J7_1 | J4.1 |
| 3.3 V | — | J7_2 | J4.2; encoder U1.1; MPU J12.1; resistor pull-ups |
| Common GND | — | J7_3 | J4.3; encoder U1.2 and U1.5/DIR; MPU J12.2 and J12.6/AD0; all switch pin 2 connections; driver grounds |

## Firmware coverage

The updated firmware controls the three motors, reads the AS5600 encoder, and retains the onboard screen. It does NOT read GPIO26–29 limit switches or initialize/read the MPU6050. The switches therefore do not stop motion in this version. Software rail limits depend on the position estimate; they are not physical limit-switch protection.

## Motor outputs

| Motor | Driver | PCB motor connector |
|---|---|---|
| Cart | U2 | J3 |
| Left/Z1 | U4 | J2 |
| Right/Z2 | U5 | J1 |

For each motor connector: pin 1 → driver pad 16 (coil A); pin 2 → pad 15 (coil A); pin 3 → pad 14 (coil B); pin 4 → pad 13 (coil B). Connect one measured coil pair to pins 1/2 and the other pair to 3/4. Coil polarity affects direction; verify direction before automatic operation.

Driver pad 11 is M+/12 V; pads 12 and 8 are common GND. Pad 7 is the module's VCC output and remains unconnected on this PCB. Keep the existing working 3.3 V logic configuration. No GPIO microstep control is added; the firmware assumes 1/16 stepping.

## Power wiring

External 12 V supply positive → PCB J6 large +12 V pad. Supply negative → PCB J7 large GND pad. These feed the three drivers and PCB J5 pins 2 (+12 V) and 1 (GND).

Use external wires from PCB J5.2 to the Copperhill J3 terminal marked +12 V, and PCB J5.1 to its GND terminal. The carrier power input is not part of the J6/J7 socket connection. Do not feed 12 V into bare Teensy VIN, 5 V output, 3.3 V, or GPIO.

## Limit switches

For each switch, wire NC → connector pin 1 (signal), COM → connector pin 2 (GND), and leave NO unused. The existing 1 kΩ resistor connects signal to 3.3 V. Released switch reads LOW; actuated switch or broken signal wire reads HIGH. A closed switch draws approximately 3.3 mA through its resistor. These nets are also exposed at PCB J5, so the pull-ups affect those screw-terminal signals too. No disconnect jumper was added.

## MPU6050 connection

PCB J12: 1 = 3.3 V, 2 = GND, 3 = SDA/GPIO25, 4 = SCL/GPIO24, 5 = INT/GPIO38, 6 = AD0/GND. AD0 grounded selects address 0x68. Use wires matching the actual module's labels: this custom six-pin order is not a guaranteed plug-in match for an eight-pin breakout. XDA/XCL are unused. Verify the module supports the chosen 3.3 V supply and pulls SDA/SCL to 3.3 V. If it has no pull-ups, add them. MPU software support remains to be implemented.

## Review limits / before fabrication

- The uploaded board has two copper layers and no +12 V vias; +12 V uses front-layer 3 mm tracks with 1.5 mm sections.
- The uploaded board contains no saved filled polygons. Refill zones (B), save, and rerun full DRC including unconnected items. Final ground-path continuity/current capacity has not been certified.
- Female-header footprints U2/U3/U4/U5: 1.02 mm drills, 1.8 mm pads, 2.54 mm local pitch. Both 4- and 12-pin terminal footprints: 3.5 mm pitch, 1.2 mm drills, 2.032 mm pads. These are file measurements, not a physical fit certification.
- Socket fit also depends on header locations and module revision. Print at 1:1 without scaling and physically overlay the actual modules/connectors before ordering.
- U3 courtyard is only 53.5 mm across its narrow dimension, so it does not model the stated approximately 63 mm connector envelope. Extend its mechanical envelope to include protrusions and cable access.
- Four 4.5 mm non-plated mounting holes exist; rename REF** to H1–H4 and check actual screw-head/standoff clearance.
- Footprint/library mismatch warnings can be intentional local edits. Preserve those edits; blindly updating from the library can overwrite them.
- Silkscreen body-line clipping is cosmetic. Inspect all clipped signal/power labels and the separate rule-area warnings in the Gerber preview.
- Input protection is not provided by this carrier PCB. Use a fused/current-limited supply; size current paths using simultaneous driver input current, actual copper weight, and connector ratings.

Sources for operation/pin checks: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html ; https://copperhilltech.com/content/teensy41_triple_can_rev_A.pdf ; https://cdn.sparkfun.com/datasheets/Robotics/BigEasyDriver_v16a.pdf
