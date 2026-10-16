# Python feedback commissioning and identification — 2026-10-16

This is an experimental commissioning checkpoint. Native AUTO/BAL and the working bw10 gain profile remain available. The firmware and direct upright reference 330 were not changed. Python AUTO works on the physical rig, but repeated reliable operation has not yet been established. Standalone physical Python BAL remains pending.

## Main results

- Best recorded Python AUTO: capture at 3.172 s, continuous balance for 21.816 s of a 25 s run, then counted return home. This single success does not establish repeatability.
- A later Python run completed 25 s but held balance only 0.976 s. Its recorded policy actions and capture decisions reproduce correctly against the frozen implementation and native C++ forecast.
- Matched native comparison: capture at 2.476 s, then approximately 22.520 s balance; the same 41 live settings and reference were used.
- Host observations sometimes skip board frames despite all intermediate frames being present in logs. A zero-demand test actually expired its 20 ms command lease. Firmware disabled correctly. The failure interval used 22.314 ms wall time but only 1.997 ms caller-thread CPU.
- Removing JSON logging and encoder display mirroring reduces, but does not eliminate, timing gaps. A reversible CPU-placement comparison reduced long gaps from 67 to 9 per 20 s, but eight clustered in one second. A second isolated repeat had zero long gaps. These mixed results are not a reliability pass.
- Temporary vision CPU affinities were restored, including new threads. The vision stream was not stopped or redeployed by this task. No scheduler privilege or real-time OS setting was applied.
- Three bounded physical identification runs completed. Both fresh train/held-out fits and all 11 earlier full-model assessments were rejected under the existing gates. No new RL plant model or encoder calibration was promoted.

## Implementation and checks

The Python controller consumes explicit cart position, commanded velocity, filtered magnetic angle/rate, commanded acceleration and brake direction from one board snapshot, retaining raw angle separately for safety. It sends acceleration requests through the SDK; the Teensy retains its 1 kHz observer/governor, pulses and interlocks. Ordinary four-channel observations remain unchanged.

The opt-in 250 Hz gap allowance accepts at most two 8/12 ms gaps per rolling second and leaves the 20 ms anchored lease unchanged. It remains off by default. A real trial correctly rejected a third gap; this feature is not a substitute for bounded execution latency.

A reproduced STOP-reporting race is fixed: an untagged late action error cannot be mistaken for rejection of STOP. The client still requires STOP's own acknowledgement and a confirmed disabled state, and retains the original fault latch. Missing acknowledgement or enabled state still fails verification.

Final root verification: 853 tests, 7 skipped, and 390 subtests passed. The earlier release-directory suite passed 848 tests and 384 subtests; the final packaged-source check passed 194 tests and 25 subtests. Two timing-dependent test fixtures were corrected without production changes, with deterministic failure reproduction and mutation checks. The stopped diagnostic harness has 9 checks; its analysis and capture audits have their own recorded verification. See `verification/` and per-audit reports for commands and source hashes.

## Evidence map

- `hardware/runs/manifest.json`: original file paths, uncompressed SHA-256 hashes and sizes. JSONL files are stored as gzip. Reports include actual parameters, reference, state, failure and STOP outcomes.
- `hardware/`: exact commissioning, full-home/rehome, recovery and disabled timing scripts. These are rig-specific experiment records, not a general unattended production launcher.
- `capture-audit/`: frozen policy, Python/native forecast comparison, recorded-state analysis.
- `reliability-audit/`: actual balance intervals, capture loss, native comparison and precise host/board timelines.
- `timing-audit/`: stage wall/CPU separation, logging/mirroring comparisons, CPU placement and restoration records.
- `gap-validation/`: 1 ms executor/physics experiments with intentionally skipped host decisions, including rejection and lease-expiry checks.
- `characterization/` and `native-identification/`: bounded input experiments, held-out analysis and rejected candidate fits.
- `vision-audit/`: camera framing/calibration findings and the independently tested cart-measurement bug fix.

The operator subsequently confirmed the rig clear. An isolated 20 s zero-demand run passed; Python AUTO then captured at 3.140 s and held for 21.848 s. Its immediate repeat expired the 20 ms lease after 2.748 s, with the last accepted action expiring exactly at its board deadline. The diagnosed expiry was cleared only after released-switch/health checks, then the cart returned to the retained home.

A wire-equivalent standard-library CRC fast path removes per-bit Python work; exhaustive short-input and seeded full-length checks preserve protocol bytes. It is an overhead improvement, not proof of the cause of the intermittent send delay. With that change, the final 20 s zero trial and 25 s AUTO passed. AUTO captured at 3.172 s and held 21.816 s (4.095 degree raw-angle RMS), then returned home. One 8 ms observation gap remained within the explicit experimental allowance. No gains, encoder reference, firmware, lease or interlocks changed.

At the user's request, further Python scheduling investigation is parked while system identification proceeds. The known timing limitation remains; this is not a production reliability certification. All temporary camera CPU settings were restored. The subsequent passive identification recording verified the driver disabled throughout; its first 180 s window contained only the stationary arm and is not a free-decay dataset. New identification work is tracked in `../system-id-20261016/`.
