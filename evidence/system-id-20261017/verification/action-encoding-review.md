# Acceleration wire underflow fix — 2026-10-17

Implemented, independently inspected and tested. No commit, hardware/SSH access, firmware edit, gain change, calibration change, deployment or lease change.

## Root cause reproduced

The production `executor::realValue` in `firmware/teensy_executor/executor_core.h` delegates decimal conversion to `strtof` and rejects `errno == ERANGE`. Native compilation reproduced the exact pilot tokens: `1.19172592e-38` is accepted, while `1.01935274e-38` and its negative are rejected with errno 34. The latter is below the minimum normal binary32 value (about 1.17549435e-38). The SDK's previous nine-significant-digit scientific notation preserved these finite Python values as underflowing tokens.

The regression sends actual SDK CRC-framed action bytes through a compiled production `executor::Core::command`, so it covers the real parser rather than a Python float approximation. The exact old pilot token remains rejected by this unchanged parser.

## Change

Only `src/cartpole_sdk/rig/client.py` and new `tests/test_rig_action_encoding.py` were changed by this task.

A shared private acceleration formatter now uses nine digits after the decimal point for both `Rig.step(ActionRequest)` and `Rig.set_acceleration`. Finite/range validation still runs before formatting. Decimal quantization is at most 5e-10 m/s² in absolute value before the firmware's existing float32 conversion; every nonzero emitted magnitude is at least 1e-9. This is defined encoding precision, not a controller-specific physical deadband. The manual velocity path is unchanged.

Sequence, observed tick, expiry, TTL checks and the 20 ms action lease are unchanged. The native regression verifies observed tick 100 still expires at tick 120. Requested full-precision values remain in action-request records and emitted decimal values remain visible in command records.

## Verification

- Test-first red: old production implementation produced 20 failed / 25 passed cases. Failures included actual native rejection of both signs of the pilot token and float underflow boundaries.
- Focused new tests after fix: 45 passed. Cases cover signed zero, signed pilot values, smallest Python floats, minimum normal binary32 magnitude, both sides of the 5e-10 quantization boundary, ordinary signed fractional values, ±25 bounds, nonfinite and out-of-range rejection, actual CRC framing, native acceptance and lease anchoring.
- Related rig/native suite: 242 passed, 24 subtests passed in 6.95 seconds.
- Initial sandbox full run: 885 passed, 7 skipped, 390 subtests passed; 13 existing local socket tests failed solely on PermissionError. Affected cases were portal HTTP authentication, cross-origin, slow body, size/path, submit/list, UI and worker-claim tests; portal worker HTTP end-to-end, redirect and slow-response tests; vision process comparison and both UDP encoder-feed tests. No source was changed to address these environmental errors.
- Full rerun with local HTTP/UDP binding available: 898 passed, 7 skipped, 390 subtests passed in 44.74 seconds.
- `git diff --check` passed.

Logs:
- `/tmp/cartpole-python-id-20261016/action-encoding-red.txt`
- `/tmp/cartpole-python-id-20261016/action-encoding-focused.txt`
- `/tmp/cartpole-python-id-20261016/action-encoding-full-suite.txt` (sandbox bind restrictions)
- `/tmp/cartpole-python-id-20261016/action-encoding-full-suite-local.txt` (passing final suite)

Source SHA256 at verification:
- client.py: `5a427ad08eda72c909048f0eae054cde05e0de3acb8f063aa4d684cee92ff93f`
- test_rig_action_encoding.py: `c7651ac506796d4a69ca90b87fe094c98f8ded5a8bdbe27213761715a629d82a`
- unchanged executor_core.h: `55ea99a855a10457b0b1ff55676fb61e21f21ec76c5db6259ca5a7f04cf13d7b`
