# Native firmware oracle

`tests/oracle_support.py` compiles `harness.cpp` with the complete archived sketch
and the original headers. It generates `firmware_native.ino` into a temporary
build directory using four exact, single-match substitutions. The archive is
never written. This is an independent native execution of `controlTick`, not a
C++ translation of the Python controller.

Run from the repository:

```sh
.venv/bin/python -m unittest discover -s tests -p test_native_oracle.py -v
```

A C++17 compiler is required for native/parity tests. Compile failures fail the
tests. Normal float32 C++ math is retained; `-fno-fast-math` is explicit. The
Python helper caches compilation by compiler and content hash within a test
process. Each context manager gets a separate persistent subprocess and state.

`NativeOracle.reset` clears control state but retains parameters. Set all fields
from the saved swing-control preset through `set_parameters`; Z-axis settings
are excluded. Header defaults are otherwise retained. `tick` runs commands via
original `handleLine`, then original `controlTick`; it permits forward clock gaps
for timeout probes and enforces monotonic unwrapped microseconds. Native
`micros` and `millis` independently wrap to uint32. Duplicate time is permitted
only on the first tick following reset.

Wire1 injects healthy/failing transactions so original `encUpdate` exercises its
hold, consecutive-error and 50-error bus recovery logic. Successful reads supply
a neutral raw count; the allowed `encTheta` substitution supplies the held,
decoded angle. Encoder count calibration, timing and electrical behavior are
outside this oracle. Arduino delays/GPIO/interrupt controls, IntervalTimer,
network and LCD are no-ops; EEPROM is in-memory. No `setup`, `loop`, scheduler or
pulse ISR is run. The harness sets the step timer ready and injects calibrated
cart position directly.

The `oracle_demand` observation is assigned immediately before original
`cart_motion::advance`; it is zeroed before each tick. All numeric controller
branches and original control-header code are retained. Probe operations execute
original header functions for gains, estimator, motion governor and stopping
distance.

Source and generated-source SHA256, exact substitutions, original header hashes,
native support hashes, compiler and limitations are recorded in
`evidence/phase2/oracle-provenance.json`. Recompute that evidence after changing
native support files. At exactly pi, float32 `atan2f(sinf(theta),cosf(theta))` can
choose the opposite signed endpoint from Python float64; parity compares angular
differences and reports numerical tolerances rather than claiming bitwise
identity or whole-board equivalence.
