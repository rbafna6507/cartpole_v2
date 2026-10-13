# 175 mm pendulum — 14.2 g

Free-swing captures collected on 2026-09-15. Run labels follow original filename timestamps.
Each capture keeps its original CSV, plot and metrics filename; `_metadata.json` adds its run label and context.

| Run | Capture time¹ | Duration | Period² | Effective length² | Recorded peak | End reason | Files |
|---|---|---:|---:|---:|---:|---|---|
| Run 01 | 18:47:43 | 45.00 s | 0.8259 s | 169.42 mm | 65.6° | 45 s timeout (old detector) | [CSV](pendulum_20260915_184743.csv) · [plot](pendulum_20260915_184743.png) · [metrics](pendulum_20260915_184743_metrics.json) |
| Run 02 | 18:49:05 | 45.00 s | 0.8339 s | 172.74 mm | 104.2° | 45 s timeout (old detector) | [CSV](pendulum_20260915_184905.csv) · [plot](pendulum_20260915_184905.png) · [metrics](pendulum_20260915_184905_metrics.json) |
| Run 03 | 18:56:27 | 22.69 s | 0.8311 s | 171.57 mm | 93.2° | Quiet (normal) | [CSV](pendulum_20260915_185627.csv) · [plot](pendulum_20260915_185627.png) · [metrics](pendulum_20260915_185627_metrics.json) |

¹ Times come from original filenames; timezone was not recorded in those files.

² Values are the original analysis outputs, preserved unchanged. All three recordings include large-angle motion. These are provisional estimates; inspect the decay and fit the small-angle portion before choosing controller parameters.

All three captures report **zero I²C errors and zero dropped sequence samples**. The first two timeout endings reflect the old quiet detector, not evidence that their raw data are unusable.

## Configuration and provenance

- [Configuration snapshot](configuration.json): 175 mm physical length, 14.2 g pendulum mass, 300 mm cart travel.
- The existing two 5.85 g end weights are recorded separately; their masses were not remeasured here.
- [Summary JSON](summary.json) and per-capture metadata provide machine-readable labels.
- [Collection manifest](../../manifest.json) maps original paths to new locations and records SHA-256 hashes.
- [Controller fit](controller_fit.json) separately refits 33 cycles at 5–20°; the revised controller uses **0.166 m** effective length. The original aggregate metrics above remain unchanged.

## Additional captures

From the repository root, keep new captures in this configuration/date folder:

```bash
python3 characterize_pendulum.py --port /dev/cu.usbserial-0001 --out pendulum_characterization/175mm_14p2g/2026-09-15
```

Use a new date directory on a different day, and a new configuration directory if the rod or weights change. Additional captures retain timestamp filenames and should be added to this index after completion.
