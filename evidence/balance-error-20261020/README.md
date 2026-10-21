# Hardware characterization and policy follow-up — 2026-10-20

See [the complete handoff](../../docs/checkpoint-20261020-followup.md) for live
commands, results, limitations and remaining measurements.

- `live/`: complete raw characterization, original operator trial, successful
  native console comparison, and separate full-HOME audit archives. Failed
  trials are retained; incomplete trials are excluded from physics scores.
- `operator-trial/`: the 70 ms balance-wrapper angular-rate refusal.
- `driven-validation/`: frozen-model conditional replay; no fit/export.
- `horizon-audit/`: shorter-lead diagnostics of the same saved predictions,
  separating initialization sensitivity from an unproven physical-model cause.
- `timing/`: measured command-renewal failure evidence, not a timing fix.
- `native-success/`, `native-validation/`: firmware AUTO capture and balance metrics.
- `home-audit/`: physical switch contact/count repeatability. Home 17 became 18;
  span repeated at 16,506 steps, all 41 settings/reference 330 unchanged.
- `angle-error-learning/`: completed small upright bias-learning pilot.
- `deployment.json`: explicit wider balance runtime profile installed in the
  isolated Jetson release. No learned actor was powered by this update.
- `tests.txt`, `verification.json`: full SDK verification and recorded handoff.
- `tools/`: runnable offline analysis and the bounded native HOME collector.

No firmware flash or encoder calibration occurred. The rig was left disabled at
home. Camera measurements were omitted at the operator's request due lighting.
Command/count fields are never relabeled as independent physical motion.

The independent full-task randomized training results are preserved under
[robust-swing-20261020](../robust-swing-20261020/README.md). Original frozen sources,
profiles and actor bytes remain intact; no simulator parameter fit was promoted.

To repeat a HOME audit from a hardware-enabled checkout, with the rig clear,
console closed and a quiet hanging pole, use a new output directory and read the
current reference/home identities first:

```sh
uv run --extra hardware python evidence/balance-error-20261020/tools/collect_home_audit.py \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --expected-reference 330 --expected-home 18 \
  --output runs/NEW-home-audit --execute
```

This moves to both switches and advances the home epoch; it does not merely
return to saved home. STOP is attempted on every exit; faults are not cleared.
To plot a completed audit offline:

```sh
uv run --extra plots python evidence/balance-error-20261020/tools/analyze_home_audit.py \
  --input runs/NEW-home-audit --output runs/NEW-home-audit-analysis
```
