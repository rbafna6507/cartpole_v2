# Passive camera and hanging-zero collector verification

Verified 2026-10-17. Staged checkout: `/home/rbafna/cartpole-v2-live/staging/operator-id-20261017-camera-zero`. Base commit `81ebdad`; `source-manifest.json` identifies the working-tree snapshot shipped before this evidence commit. All 136 source-file hashes were verified remotely. The manifest SHA-256 is `8db1420429b1a6dd3af16a9ee7ad5597bf34d79901c5aa7cf8378ddc65e8f149`. Later plan/evidence additions are not part of that staged snapshot.

## Verification

- Full local suite: **1,233 passed, 8 skipped, 390 subtests passed** in 71.89 seconds using `MPLCONFIGDIR=/tmp/cartpole-id-matplotlib .venv/bin/python -m pytest -q`.
- Locked Jetson hardware/id/plots installation and `collect-passive --help` succeeded.
- Camera-only live smoke: 363 frames in about five seconds (roughly 72 FPS); all 363 raw records had valid independent marker geometry. The latest-frame preview sampled 361 of them, all valid.
- Start/end HTTP clock uncertainty: 5.250076 ms / 3.014197 ms. These are host-read proxies, not exposure timestamps.
- Quiet camera baseline: 143 distinct frames, full valid coverage, angle P95–P5 about 0.113 degrees, maximum frame gap about 26 ms. See `source-and-camera-check.json`.
- No serial port opened, no motion commanded, no live encoder baseline attempted, no firmware/upright reference/gain changes.

`vision.ndjson.gz` is losslessly compressed raw camera geometry, not a video file. Its decompressed SHA-256 is `56a6aed7e9edead5397c7a4688334053d7e9b507bff15cc14b6e3333d6c8340a`. Other reports are unchanged copies from the Jetson smoke output.

## Repeating the camera-only check

From a checkout containing this evidence and a running vision service:

```sh
uv run --locked --extra hardware --extra id --extra plots python \
  evidence/passive-camera-baseline-20261017/camera_smoke.py \
  --output runs/camera-smoke-new
```

The evidence script preserves the executed smoke procedure; its docstring was corrected to say it never *opens* serial. It imports SDK modules. Choose a new output directory each time. The staged precommit checkout has the original executed script at `/tmp/cartpole-passive-camera-smoke.py`.

The operator's next training/validation recordings are still pending. This evidence verifies software and stationary camera collection only; it does not accept a system-identification model or establish camera accuracy during fast swings.
