Legacy AUTO budget fixture investigation, 2026-10-16.

The integrated run recorded 1 failure, 852 passed, 7 skipped and 384 passed subtests. The failure was the inherited V5ReturnTests.test_legacy_auto_keeps_early_stopping_budget test, where the next Rig.start was rejected because executor fault 1 remained latched. Its isolated original run passed.

Root cause: the test reused one ReturnFirmware instance across three legacy identities. Each 100 ms run depended on the host delivering STOP in a 10 ms margin before the fixture's duration deadline. If STOP was delayed past expiry, the fixture correctly latched fault 1. The test asserted only disabled state, so that iteration could pass; its next new Rig session saw the preserved board fault and correctly refused to start. No production guard or CRC semantics were responsible for allowing a start; the guard rejected it as designed.

A deterministic offline PTY reproduction added 30 ms delay before STOP writes. The first _wait_run returned disabled with firmware fault 1 and rig.error='executor fault 1'; the second identity then failed Rig.start with exactly 'latched rig error: executor fault 1'. Full records are in legacy-budget-race-reproduction.json. No hardware/network was used.

Changed only tests/test_rig_rehome.py::ReturnTests.test_legacy_auto_keeps_early_stopping_budget. It now uses the existing scripted clock/transport test utility with native MODE duration semantics, retaining real Rig.start, _wait_run, and stop guards. It verifies a 100 ms host deadline, STOP at 90 ms (allowing only a 1 ns float-rounding remainder), MODE auto 100 followed by STOP, no automatic return and no latched error. Other PTY tests still exercise real lease expiry, return lifecycle and transport behavior. The scripted wait honors timeout rather than always jumping to the next 10 ms publication.

Verification: `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_rig_rehome.py tests/test_rig_calibration_model.py tests/test_rig.py` passed 86 tests and 55 subtests in 7.23s. `git diff --check` was clean. During fixture development, the first draft exposed that the reused scripted helper ignored tiny wait timeouts: six subtests failed when 0.1 - 0.01 rounded just above 90 ms. That test-only wait behavior was corrected; no production change was necessary.

A separate in-memory mutation removed _wait_run's early-stop margin without changing source files. All three legacy identity subtests then failed at scripted duration expiry. This proves the revised fixture still catches loss of the early-stop behavior; evidence is legacy-budget-mutation-check.json. Integrated rerun remains with the primary agent.

No production file, safety bound, CRC code, firmware or gains changed in this follow-up. No commit was made.
