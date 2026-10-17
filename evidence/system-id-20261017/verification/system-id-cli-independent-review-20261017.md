# Independent system-ID CLI review — 2026-10-17

Read-only review of maintained `identification/experiments.py`, `workflow.py`, `passive.py`, `cli.py`, their new tests, and `scripts/system-id`. No SSH, serial, hardware, network, source edits or service changes. Camera diagnosis is separately recorded in `camera-measurement-review-20261017.md` in this directory.

## Findings and disposition

1. **P1, corrected: camera readiness trusted stream heartbeat rather than actual camera freshness.** The original collector accepted increasing envelope sequence with unchanged source frame, `stale=true`, large source age and `worker_error`; a local fake-stream reproduction returned ready=true, two frames, no failure. The corrected collector checks actual source frame seq/t, finite source host clock/age, explicit non-stale status, worker error, bounded source age, and source progression. It counts bounded repeated heartbeat frames separately. New tests cover stale startup, runtime stale/error/age/reversal and valid duplicate heartbeat. No cross-host monotonic subtraction was introduced.
2. **P2, corrected: offline source reads/decompression were unbounded.** Reviewed `load_records` materializes arbitrary plain/gzip/tar input and every decoded line without byte/line/record limits. Requested bounded decompressed reads and explicit generous limits, including tar member sizes and small-limit tests.
3. **P2, corrected: failed raw evidence could lose its failure status on offline admission.** Passive collection writes some failures only to sibling `report.json`, while the fitter reads raw JSONL alone. Additionally, the reviewed passive parser admits `termination(error=...,records_dropped=0)` and `termination(error=null,records_dropped=1)`. Both were independently reproduced with the ordinary raw-log fixture: six episodes admitted. Requested direct rejection of terminal errors/drops/STOP failures, plus exact hash-bound matching collection report admission for new runs, including archive siblings and missing-report detection. Historical raw-only recordings need explicit compatibility. No collector changes requested during the primary's frozen pilot.

## Verified behavior

The current focused suite independently passed **84 tests in 4.53 s** with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_system_id_experiments.py tests/test_system_id_workflow.py tests/test_system_id_cli.py`.

The pulse path requires explicit CLI execution, exact amplitude allowlist, healthy homed stopped preflight, saved valid encoder reference/home, all 41 parameters, quiet hanging/centered start and a 500 ms quiet board-time interval. Runtime retains 20 ms leases, strict host/board gaps below 20 ms, sequence/source coherence, cart/angle/rate bounds and STOP cleanup. The explicit 3–12 s hold changes duration without changing the lease. Passive collection never arms. Missing camera startup prevents serial opening; camera failure causes STOP. Current-session encoder publication is separate display data; fitting uses direct Rig raw theta and MCU acceleration.

Two complete historical driven JSONLs were parsed locally through the new loader and existing raw adapter: the older +5 mm pilot had 2917 records, 726 states and 630 eligible states; the later +5 mm trial had 5586 records, 1363 states and 1269 eligible states. These checks establish format compatibility, not successful or usable experiments. Original passive raw JSONL was not locally available in this review; compact column exports are not the CLI's raw-log input format.

Passive coefficients are fitted from training only; validation cannot refit them. Source hashes, session identities and source-bound explicit manual annotations preserve the intended split. The new workflow adds per-episode gates to the aggregate checks, so the archived historical aggregate pass must not be silently promoted to new workflow acceptance. A local gravity-phase estimate remains an assumption-conditioned model parameter, not an encoder calibration. Short forecasts reinitialize from past angles and do not establish full-episode, driven, upright or full-swing prediction.

Export checks acceptance/scope, rejects unsupported Coulomb friction, nonunit driven input gain and nonzero delay, and maps only effective length plus hinge damping `gamma * 0.75 * assumed_pole_mass * L_eff^2`. Other full SimulationConfig fields remain explicit assumptions. The local phase is recorded but not applied to production sensors or global calibration. No additional export mapping or train/validation leakage defect was found. The headless Gym smoke check establishes software loading/execution only.

## Final verification

All three findings are corrected in the reviewed source. `load_records` now bounds decompressed bytes (256 MiB), line bytes (4 MiB), records (500,000), archive entries (10,000) and archive bytes (2 GiB), reads incrementally and preserves exact decompressed-byte hashes. Collection admission rejects terminal errors/drops and explicit failure events; modern sources require a matching successful, STOP-confirmed, zero-drop report bound by exact raw filename/hash, including archive siblings without extraction. Historical raw-only/report compatibility is explicit. Old ringdown scripts use a provenance list and are distinguished from the new collector's provenance dictionary.

Final independent focused run: **103 passed in 6.59 s** across the same three test files. The old recorded-error pilot now correctly rejects. The later successful historical +5 mm trial still admits 5586 records / 1269 eligible states and preserves its historical report hash; the historical stopped preflight has zero eligible states. Lazy imports and command-specific launcher extras keep help independent of numerical/simulation packages and hardware collection independent of MuJoCo/Gym.

No remaining substantive blocker was found within this review's scope. This is code/evidence-workflow review, not hardware validation, independent physical stationarity certification, or RL readiness.


Reviewed source/test pins:

```json
{
  "src/cartpole_sdk/identification/experiments.py": "fd5dfb950db1ca4e08c370b27cc1f40d111b7b32f93f18835541585969499f64",
  "src/cartpole_sdk/identification/workflow.py": "2a5793ab305f5e67d3ba0098514510cd16f16259c4d10f73b40d857cc1050ae5",
  "src/cartpole_sdk/identification/passive.py": "5dc850ec634e1b71ff417bac0f6a31c4bc53b0bad7e82516235e3606dbf66deb",
  "src/cartpole_sdk/identification/cli.py": "341b32c09f6281e45d18e0d197d64301c10899302205e390d22ba41b8e682758",
  "src/cartpole_sdk/identification/__init__.py": "f0b85dad78f84dfa71c0af0df02ca52e5fc281fae580d78669e01eb5e8d8a325",
  "scripts/system-id": "b895e120a54ea494d9eb5b0c887a0d67c1e43404f89cba21a68ad81c59474c7d",
  "tests/test_system_id_experiments.py": "f9cb750ea36e597b06325b3d9188ac17e4faa755b8820f8837bb513f9ca63ab2",
  "tests/test_system_id_workflow.py": "86c91730db43145bc9f4180da59457e915eca24ae93fb61d7ae7f53ae7ab485b",
  "tests/test_system_id_cli.py": "2e2c120790bacf8f61940ab4548510ecc6fa5a4f36cad7fa3a086b0cb8e21337"
}
```
