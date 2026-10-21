Use `scripts/policy-console` with the same arguments as the existing console. It delegates to `cartpole_sdk.rig.console.main` after setting Python's GIL switch interval to 1 ms, then restores the caller's saved interval in `finally`. Importing the new module does not start the console. Help follows the existing parser and creates no Rig.

The shell follows `scripts/run-balance-policy`: it resolves the repository independently of the working directory, forwards arguments intact, and requests the hardware/inference extras except for help. It performs no scheduling escalation. Existing console startup, actor validation, operator commands, leases, gains, and reference handling are delegated unchanged.

Recorded checks:

- `red.txt`: 12 expected missing-feature failures before implementation.
- `green.txt`: 70 tests and 3 subtests passed across the launcher and existing console suites.
- `initial-green-rounding.txt`: initial strict float equality failures exposed CPython's 1 µs get/set truncation at 7 ms. Tests now allow that API resolution; production passes the exact saved float to restoration.
- `module-help.txt`: actual module entrypoint help smoke; shell syntax also passed.
- `review.txt`: independent review, no Important/Critical findings, 12 focused tests independently passed.
- `full-suite.txt`: complete repository test output; final status is in `verification.json` when available.

This work used no hardware or network. Runtime timing efficacy of a hardware launch remains outside these offline checks.
