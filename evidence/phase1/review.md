# Independent Phase 1 whole-change review

Reviewed range: `2c5ebf2..c415886`, using `/tmp/cartpole-phase1/review-package.diff` and the corresponding checkout files in `/Users/rbafna/projects/cartpole_v2`. Read the specification, implementation plan including rulings, verification evidence, tunnel and recordings worker reports, production code, examples, documentation, and tests. Review was read-only on the checkout; probes used temporary files only. No remote command, network request, camera access, hardware motion, Git mutation, or subagent was used.

## Strengths

- Observation and action contracts make units, source, frame, quality, method, timing, session, and sequence explicit. Frozen tuples/dataclasses and bool/non-finite rejection prevent common accidental contract drift. Exact action expiration uses `now < expires_at`, and selection checks effective age rather than recent arrival.
- Recording parsing has exact schemas, nested duplicate-key rejection, ordered observations, and a mandatory count footer. It returns no observations until the complete recording validates. Exclusive writers preserve pre-existing outputs and clean up partial files even on iterator failure or interruption.
- Legacy mapping is careful about what the data can establish: console values retain unknown health and null effective/acquisition times; backward clocks segment or unwrap under a documented rule. Vision preserves independent cart validity, warmup and stale statuses, derivative timing, and spatial extrapolation. Detectable calibration loss fails instead of silently sharing a frame identity.
- Replay validates the entire observation stream before invoking a policy, distinguishes missing intent from zero, and models its zero-runtime open-loop scope honestly. CLI and editable example are small and runnable outside the checkout when installed.
- Tunnel discovery uses authenticated fixed read-only command arguments, strict existing host trust, bounded probes/timeouts, explicit fallback, and stable-before-temporary address selection. The tests include the real local OpenSSH configuration parser and nonstandard-port host identity.
- The archive preservation and genuine fixture provenance evidence is unusually concrete. Whole-file import evidence explains the one intentional calibration-epoch rejection rather than calling every input successful.

## Issues

### Critical (must fix)

None found.

### Important (should fix)

None found.

### Minor (nice to have)

1. **Normalize deeply nested JSON failures into the normal line-context input error.**
   - File: `src/cartpole_sdk/recording.py:39-41` (shared loader; affects both recording and vision import).
   - A JSON array nested roughly 1,100 levels raises `RecursionError` directly from `json.loads`. Reader/importer handlers and the CLI catch `ValueError`/`TypeError`, so this malformed input produces an unhandled traceback rather than the documented contextual input error. It still fails closed and creates no usable recording, so this is diagnostic polish, not a data-integrity blocker.
   - Reproduced locally with a temporary input containing `'[' * 1100 + '0' + ']' * 1100 + '\n'`; both `read_recording(path)` and `import_vision(path, 'review', 'camera:review')` raised `RecursionError`.
   - Suggested fix: translate `RecursionError` to `ValueError` in `strict_json_loads`, then add one small regression proving a line-numbered error and no CLI output artifact. Full resource quotas are a separate future concern.

2. **Expose the known SSH configuration limitations in user-facing tunnel documentation.**
   - File: `archive/README.md:57-62`.
   - This paragraph promises retention of the bootstrap SSH configuration without qualifying the `Hostname` override. The worker report correctly notes that `%h`-dependent identity/known-host paths change with that override, and that host certificates on nonstandard ports without an explicit alias can fail principal matching when the bracketed known-host identity becomes `HostKeyAlias`. These safe failures are currently described only in the temporary implementation report, which a future user will not have.
   - The practical effect is an otherwise working bootstrap followed by confusing authentication/trust failure on discovery. Preserve strict failure behavior and add the reported limitations plus the existing explicit-target escape hatch to the durable documentation; no weakening of verification is suggested.

## Verification performed during this review

- Read the supplied evidence for 67 SDK and 25 tunnel passing tests, wheel/entry-point checks, 70 matching preserved source hashes, and full archived-log import scans. These full suites were not redundantly rerun.
- Ran focused offline adversarial probes: deeply nested JSON in recording and vision readers; empty/truncated recording rejection; exponent-overflow JSON rejection; and writer interruption cleanup. Empty/truncated and overflow cases produced contextual `ValueError`; interrupted writing removed its output; nested JSON exposed Minor 1.
- Inspected archived vision estimator implementation to confirm that pole calibration and cart validity really are independent, that cart derivatives have their own effective timestamps, and that spatial extrapolation is not temporal prediction.

## Declined to judge

- Live balance/swing-up performance, physical acceleration limits, hardware interlocks, and real execution/transport latency: explicitly outside Phase 1, which never actuates hardware.
- Physical calibration correctness, cross-source alignment, and undetectable true-to-true/cart recalibration: legacy states cannot establish these; caller-verified epochs and distinct frames are explicit prerequisites.
- Reset-versus-wrap disambiguation near the uint32 boundary: the source lacks enough information; the specified half-range rule is documented and imported console samples remain unusable for valid-channel selection.
- Host-certificate deployment and exotic hostname-dependent SSH configurations beyond documented safe fallback: no such live environment was exercised; the user-facing documentation gap is reported above rather than silently discarded.
- Untrusted Python policy isolation and large-file resource quotas: policy execution is explicitly trusted/local, and session materialization/resource limitations are documented; process sandboxing and recorder-service retention are future work.
- CSV CRLF Git whitespace presentation: parent explicitly owns the pending `.gitattributes` fix; this review did not modify or re-encode fixtures.

## Assessment

**Ready to merge? Yes.** No critical or important defect was found in the implemented Phase 1 scope. The two minor improvements make failure diagnostics and tunnel expectations clearer; neither invalidates the strict data boundary, preserved SSH trust, or offline-only execution model.

## Resolution after review

Both minor findings were addressed in one local cleanup pass. The shared JSON
loader now translates parser-depth RecursionError into ValueError; a CLI regression
was observed failing for both recording replay and vision import, then passed
with line 2 context and no output artifact. The complete SDK suite passes 68 tests.
The archive tunnel README now documents hostname-dependent path and nonstandard-
port certificate caveats with strict explicit-target fallback. No second review
was run; the code change is covered by the new regression and full suite.

Scope decisions retained: live control/safety/performance and physical calibration
remain uncommissioned; unavailable legacy clock/epoch evidence is not invented;
trusted local policy execution remains distinct from future upload isolation and
resource quotas. CSV fixtures retain their original CRLF bytes using scoped Git
attributes. These boundaries are described in the usage guide.
