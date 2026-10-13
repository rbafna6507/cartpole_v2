# Source provenance

Based on the supplied `01-teensy_defaults_update.zip`.

The characterization fork preserves the supplied cart pulse method, pin assignments, mechanical conversion and cart-motion primitives, while replacing swing-up/balance with guided bounded experiments.

Unmodified source headers:

- `cart_motion.h` SHA-256: `bba693c6f651731b51032d76e8f2b66cfbf3016f2048b6a4648a6d1f8042ab6f`

- `cart_mechanics.h` SHA-256: `61791786622ddfb7622494fefd43578827b669eac4b347d16fe0e8f1d4c228b9`


`motor_io.h` adapts the source pulse ISR for cart-only operation and adds fault handling. The main sketch, guided Python interface and test orchestration are characterization-specific. Source geometry comments are recorded as unconfirmed in equipment.json; they are not substituted for measurements.
