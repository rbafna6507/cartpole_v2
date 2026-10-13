# Validation record — 2026-10-03

Validated locally on macOS with Python 3.13.5. No Teensy was connected, flashed or
commanded during these checks. No public endpoint was created. These results
verify the implementation, not physical safety or fidelity to the current rig.

| Check | Observed result |
|---|---|
| `.venv/bin/python -m pytest -q` | **85 passed, 22 subtests passed** in 6.80 s |
| `sh tests/native/run.sh` | **9 executor groups + sketch hardware-integration tests passed**, AddressSanitizer/UndefinedBehaviorSanitizer enabled |
| `sh firmware/build.sh` | **Teensy 4.1 compile passed**, Teensy core 1.62.0, QNEthernet 0.37.0 |
| Offline editable package install | Passed; `cartpole-deploy info` also ran outside the source directory |
| `python examples/controller.py` | Five seconds of bounded simulated cart commands, stopped normally |
| Capture → fit → separate capture → validate → export | Passed with actual headless MuJoCo physics |
| Independent code review | One important long-capture downsampling issue found, reproduced, fixed and regression-tested; no important findings remained |

Firmware build report: FLASH code 145172 B, data 20664 B; RAM1 variables 30048 B,
code 139864 B; RAM2 variables 55744 B. The build script prints a temporary output
directory and performs no upload. Both scripts were also tested with `TMPDIR`
unset, exercising their `/tmp` fallback.

The hardware SDK tests use localhost mock servers. They verify fragmented frames,
CRC errors, stream backlogs, timestamp wrap, device errors, deadline limits,
uncertain delivery and ownership-aware cleanup. The sandbox requires permission
to bind these local sockets; this test permission does not grant board access.
USB transport is implemented but has not been tested against a physical board.

Native tests exercise the actual executor, framing, source governor, pulse code
and sketch using I/O stubs. Coverage includes boot disabled, manual home without
enable, explicit arm, never pulsing Z, finite/bounded targets, strict sessions and
sequences, emitted-observation freshness, anchored expiry including timestamp
wrap, foreground stall, encoder fault, timer failure, pulse rail limit, malformed
frames, TCP/USB ownership/disconnect, bounded receive work, output queue overflow
and retained EEPROM calibration. Stubs cannot establish actual electrical or
interrupt timing; see [firmware validation](docs/firmware-validation.md).

Simulation tests cover physical inertia/sign/period/damping, clamp semantics,
encoder quantization/noise, finite actuator force, command lease/fault behavior,
velocity/position tracking, engine instability handling and Gymnasium seeded
determinism. The Python governor is compared against **800 cases compiled from
the C++ header**. GUI rendering was not exercised.

Identification tests recover parameters from an independently integrated synthetic
trace, reject invalid fitting data, validate a distinct release, prevent output
overwrite and retain early samples in long captures. Recording tests verify
motion acknowledgements, preserving partial data, stopping owned motion and
failing when stop cannot be confirmed. CLI integration tests use real MuJoCo
captures and verify that missing hardware motion acknowledgements fail before
opening a network connection.

The eight-second MuJoCo smoke fit estimated `L_eff=0.12446567 m` and
`damping=0.91285164 /s`, against configured `0.124454888 m` and `0.913383 /s`.
A separate 40-degree release had angle RMSE `0.00044834 rad` after the initial
100 ms. This is an implementation consistency check, **not measured rig accuracy**.
Versions and results are saved in [simulation-smoke.json](docs/simulation-smoke.json).

Four shared source headers match their original SHA-256 hashes exactly; hashes of
the reference sketch and historical fit are recorded in
[source-provenance.json](docs/source-provenance.json).

Still unverified: current assembly, encoder calibration, driver microsteps/pin
electrical levels, shared enable behavior, force and tracking limits, real sensor
timing, Jetson policy latency under load, missed steps, limits/inhibit wiring,
physical stop behavior, Linux/Jetson dependency installation and hostile-code
isolation. The next step is supervised bench commissioning and fresh
[characterization](docs/characterization.md), before public motion or RL transfer.
