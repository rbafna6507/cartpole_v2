Rollover fixture investigation, 2026-10-16.

The second integrated run reported 1 failed, 852 passed, 7 skipped, 390 passed subtests. The failure was RigTests.test_board_tick_and_microsecond_rollovers_are_independent: unwrapped_us=42904 was not greater than UINT32_MAX. The isolated original test passed.

The fixture started its microsecond counter at 0xfffff000, only 4.096 ms before wrap, but performed a real host-scheduled handshake before obtaining its first sample. If that handshake ran after wrap, the first observed microseconds were already small. unwrap32 correctly uses the first raw sample as the initial epoch; it cannot infer an unobserved earlier wrap. The independent millisecond tick counter could still have a pre-wrap sample because its wrap was 16 ms away.

A deterministic 10 ms delay before handshake reproduced this: first raw tick=4294967294 and us=9904; later unwrapped_tick=4294967324 but unwrapped_us=39904. The old assertion then fails exactly as expected. See rollover-epoch-reproduction.json. This demonstrates an initial-epoch assumption in the test, not a CRC or unwrap regression.

Changed only tests/test_rig.py::RigTests.test_board_tick_and_microsecond_rollovers_are_independent. A local firmware subclass freezes elapsed board milliseconds through handshake; rate=0 and command publications disabled ensure the first validated frame is the requested STATUS snapshot. The test verifies initial pre-wrap values, publishes the 5 ms state (only microseconds wrapped), then the 20 ms state (both counters wrapped). Literal raw/unwrapped expectations and observation sequence/timestamps are checked. The real PTY, CRC encode/decode, parse_state, Rig._accept and unwrap32 paths remain active. No sleeps or increased production tolerances are used.

Related suites tests/test_rig.py, test_rig_protocol.py, test_rig_crc.py, test_rig_rehome.py and test_rig_calibration_model.py passed 94 tests and 66 subtests in 9.60s. The final rollover test also passed in 0.09s after the last STATUS-only fixture refinement. git diff --check was clean. An in-memory mutation bypassing unwrap32 produced the expected assertion failure at the microsecond-only wrap; evidence is rollover-mutation-check.json.

No production code, firmware, CRC implementation, hardware/network, guards or gains changed. Integrated rerun remains with the primary agent; no commit was made.
