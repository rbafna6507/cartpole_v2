# Pulse batch independent review — 2026-10-17

Final reviewed analyzer SHA256: 75e2418db08d325339d7d7bcff08a7f8d007f7a809593083cfa304dd2b745fa1.
Workflow serialization-fix SHA256: 8b9d1bbc9d643a1604cc766e4fb6ee4bfd39284827e99c4bd9805e30c308556d.

One confirmed admission issue was corrected: the inherited driven fitter accepted entirely static independent validation (theta=pi, acceleration=0), with seven forecasts, RMS5.6e-15rad and integral NRMSE7.8e-5. The new batch-level per-run validation excitation checks use the existing FitConfig minima (angle span0.15rad, acceleration standard deviation0.05m/s²), reject static-only and mixed active/static validation, and preserve the original underlying fit report. No coefficients or original fitter gates were altered.

Independent final run: 53 passed in6.45s across tests/test_pulse_batch_analysis.py, tests/test_system_id_cli.py and tests/test_system_id_workflow.py. Tests cover invalid/gap boundaries, independent sessions/clocks, duplicate source and normalized measurement copies, failed completion reports, unchanged training parameters under altered validation, immutable CLI output and the accepted-fit JSON serialization fix.

The adapter retains every adapted state, raw input/source/completion hashes and run identity. Its per-group analysis-clock translations preserve within-run deltas and add1s separators; identity changes independently split windows, so no interpolation, regression or forecast crosses runs. Bound modern successful collection reports are required. The explicit nonzero angle offset is labeled diagnostic; commanded MCU acceleration remains distinct from independently measured physical acceleration. Training±10/20mm and validation±30mm are prospectively selected by the primary, not selected by this review.

The bool/float serialization fix is narrow and correct; its accepted CLI regression passes. Independently verified all10 artifact hashes in /tmp/cartpole-system-id-workflow-verification-20261017-5al572i_/verification.json, including its successful synthetic fit/export/Gym chain. These are software checks, not physical validation.

No remaining substantive blocker found in the requested scope. No repository edits, hardware, SSH or network access by this review. Scientific acceptance remains conditional commanded-input evidence, not independent angle calibration, physical cart-gain measurement or hardware RL readiness.


Follow-up: the production fit_driven_logs wrapper now applies the same existing heldout excitation minima after preserving an exact deepcopy of underlying_fit. The two static/dynamic CLI tests pass; no coefficient/default gate change was introduced. Frozen original workflow bytes remain in the analysis frozen-sources directory. Current wrapper SHA256 c7585a23db9f3635835f96f7dc7e3c1b2db0e569c90ae708bec66bb38b400b5b. Latest independent focused run including the new camera diagnostic:62 passed in7.68s.
