# Vision audit — 2026-10-16

Read-only audit of maintained vision at checkpoint `8d6c8e8960b3d515a8b563ca078ecfef56d3e64c`, before any subsequent camera recalibration. Existing-service HTTP GETs and offline analysis only; no camera opened, serial accessed, motion commanded, or service/configuration changed during the audit.

- `findings.txt`: findings, limitations, narrow proposed fixes, and missing system-identification measurements.
- `passive-summary.json`: 801 distinct processed source frames over 10.494 s; all detected the pole, all rejected the obsolete camera length calibration. No video clients were connected. Full snapshots before/after the stream cover a longer interval and are not a rate denominator.
- `current-frame.png`: one existing-service snapshot, visually verified. Current rail orientation and actual screw/bob differ from the saved camera framing; raw image angle near -90 degrees is consistent with the hanging pole in this image.
- `boundary-reproductions.json`: offline proofs made before the subsequent Engine fix. An invalid-length arm previously suppressed a valid independent cart template; the maintained fix and regression tests now cover this case. This file preserves the original failure, not post-fix output.

The audit does not establish physical angle/cart accuracy or control eligibility. Camera metric cart anchors and template were unset. A fresh camera reference, independent physical cart scale, workspace visibility, and dynamic timing/accuracy evidence are still required. Magnetic trim330 is the current working reference; no full-angle magnetic model is accepted. SDK vision fusion remains shadow-only.

Only selected compact artifacts are preserved here. The raw passive stream, offline scripts and additional rejection frames remain under `/tmp/cartpole-vision-audit-20261016/` and are not committed as bulk evidence. The report contains original temporary artifact paths for provenance.
