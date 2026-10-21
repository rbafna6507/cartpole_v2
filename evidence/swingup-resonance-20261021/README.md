# Native swing-up recovery and encoder checks — 2026-10-21

This campaign resumed user-authorized native AUTO tests after the encoder mapping experiments. Firmware, upright reference 533, jerk limit 150 m/s³, and switch protection stayed in place. Observer bandwidth started at 8 Hz and was later compared with 10 Hz. No periodic encoder model was applied: the full-angle fit failed independent stationary and freefall validation (see `../encoder-map-repeat-20261021/README.md`).

Each powered trial starts after a recorded hanging rest and return to the counted home. The hanging measurement is diagnostic, not a recalibration; recalibrating it would erase the known direct upright reference. The existing collector logs 250 Hz executor STATE, native parameter/INFO readbacks, raw camera geometry, clock anchors, AUTO phases, return home, and post-run hanging rest. Faulted runs remain in the dataset. Cart position is step-counted; speed/acceleration are commands, not measured motor motion.

## Findings

The repeated swing-up loop is present in both raw camera geometry and encoder telemetry. In baseline03, after an unsuccessful catch, the pole settles into roughly one-second cycles near horizontal and remains outside the approach/capture zone. During 10–24 seconds it never gets closer than 74.3° to upright according to the firmware observer. It is all SWINGUP mode, not repeated rail-brake recovery. Commanded speed reaches the 1.5 m/s ceiling but is at that ceiling only about 5% of the late interval.

Reconstructing the native energy command reveals a pumping/damping balance. At baseline03's stalled orbit, normalized model-energy contributions average +1.12/s from the pump, −1.03/s from cart-velocity damping, and −0.06/s from cart centering; the limited acceleration command contributes −0.028/s. These are diagnostics from the firmware's observer/model and commanded acceleration, not a measured energy budget or causal decomposition of saturated actuator output. Increasing energy gain alone to 5 produces more pumping but also more speed limiting, and did not reliably remove the orbit.

There is a distinct capture issue. Failed captures in baseline02/03 enter with cart velocity −0.272/−0.259 m/s; the successful baseline01 enters at +0.027 m/s. Both failed baseline holds exit into rail braking after about 0.61/0.77 seconds. The later I²C fault in baseline02 does not explain that earlier loss. The existing 180 ms capture forecast accepts these entries and underestimates their later motion. Increasing balance damping pz in that forecast does not resolve the discrepancy. Camera/encoder disagreements during rapid transitions are another unresolved source of prediction error.

The ke5 trial01 catches twice; the second capture at +0.181 m/s holds for 18.424 seconds through the AUTO deadline. Its first failed entry is again about −0.261 m/s. This motivates an isolated catch-speed limit of 0.20 m/s, retaining the observed successful entry snapshots while rejecting the observed failed snapshots. It does not prove the changed trajectory will succeed or resolve the separate late swing-up orbit.

## Interpretation for learned policies

Reliable swing-up and balance with the native controller demonstrates controllability for those tested conditions. A repeatable nonlinear or biased observation can be learned. It does not validate a particular learned policy, simulator, or encoder correction. For simulation-trained transfer, observation distortion, delay, actuator limits, and physical dynamics must be represented or covered by validated variation. Successful native trials are valuable evidence, but cannot make a failed held-out calibration fit valid.

## Reproduction

Collection uses the existing `scripts/check-encoder-repeatability` wrapper; the exact collector used on the Jetson is retained here by SHA. Parameter writes use the stopped-only helper and native readback. The helper does not restore changes automatically; recorded restore steps must be preserved. Recovery scripts only clear the known ENCODER latch after repeated fresh stopped healthy samples, stable error counts, reference/configuration checks, and then perform full two-switch HOME. They do not bypass faults or flash/reset the board.

Offline analysis requires the repository's id/plots dependencies. Extract the raw archives to a work directory; distinct trial directories are preserved. Then run the documented scoreboard with that input root. It compares the camera's raw marker geometry to encoder readings using the previously frozen −17 ms timing proxy; it never refits alignment or uses fused/mirrored encoder angles as camera evidence.

## Final outcomes and limitations

Twelve powered trials were attempted: seven completed their 25-second AUTO window, and five ended on ENCODER fault 4. Four of the seven completed trials finished balanced; three remained in the unsuccessful swing-up cycle. The 60-second attempt ended early and is not a long-hold validation. `analysis/campaign/metrics.csv` and `report.json` retain all outcomes, readbacks, camera geometry and source hashes.

| Setting | Outcome |
|---|---|
| Original bw8, ke4, kdx2 | Holds of 21.276 s, 0.604 s, 0.768 s across three trials. Only the first held through expiry; the second later faulted. |
| ke5 only | One 18.424 s final hold after an initial lost catch; one sensor-interrupted run; one complete run with no capture. Not promoted. |
| ke5, kdx1.5 | No capture before an encoder fault at about9.4 s. Inconclusive as a full-duration comparison; not promoted. |
| Original pumping, catch_v0.20 | Complete 25 s run without capture. Not promoted. |
| Original pumping/catch, bw10 | Two complete runs, longest holds 21.892 s and 19.428 s, both through expiry. A third 25 s attempt and the 60 s attempt lost short catches before later encoder faults. Promising candidate, not a reliable fix. |

The first bw10 run captured in 3.104 s; the second recovered from an initial failed catch and began its lasting hold at 5.568 s. Settled encoder RMS was about 1.35° and 1.40°. A third bw10 trial held only 0.124 s, and the 60 s attempt only 0.120 s. Do not exclude their earlier capture failures merely because they later ended with an I²C fault. No gain or observer setting has yet demonstrated robust repeatability.

The I²C counter increased from 6 to 12 over the campaign, across five interrupted trials. Recovery required stable stopped health and rehoming; firmware protections were never bypassed. Source inspection shows `encoderHealthy()` requires zero consecutive angle-read errors plus valid recent magnet/configuration checks; `executor_state.sample()` can therefore fault on a single failed transaction. The separate five-consecutive-errors comment/check is not the effective executor health policy. This explains abrupt stops but does not identify the electrical cause of those transactions.

### Camera geometry changed

Before the bw10 group, the home pivot shifted from approximately (549,204) pixels to (212,387), and the view became oblique with the left rail end outside the image. Compare `camera-before.png` and `camera-at-stop.png`. Absolute image-vertical angles across these views are not comparable. The approximately 8° camera RMS in the bw10 rows is **not evidence of 8° encoder drift**. The camera was never used as feedback during these runs. A clarification was requested about whether only the camera or also the rig was handled; further motion is waiting on that answer.

### Board left stopped

`stopped-readback.json` confirms motor disabled, mode 4/fault 4 latched, commanded velocity/acceleration zero, counted x −0.032775m, reference 533 retained, encoder configuration valid, I²C 12, home epoch 31. The fault invalidates homing; no further clear or home was issued while the camera/rig-clear question was pending.

All 40 writable settings match the existing `profiles/candidate-20261016-bw10.json`, also the console's existing default. This is not a new promoted gain set. The temporary ke/kdx/catch_v changes were restored. The bw10 collector's final automatic restoration failed on the faulted attempts, which is recorded; the stopped readback confirms bandwidth10 remains live. No firmware, production SDK code, simulation model, trained actor, or archived baseline was changed by this campaign.

## Exact commands

After the rig is clear, the camera is fixed on the full rail, and the stopped encoder fault has been diagnosed/cleared and homing re-established, run one short native trial from the repository/release:

```bash
./scripts/check-encoder-repeatability --expected-reference 533 --bw 10 \
  --execute --duration 25 --output runs/my-bw10-repeat-01
```

Use a fresh output directory. The reference must be a known valid upright reference, not simply a number copied to bypass a mismatch. The collector records hanging rest without resetting calibration, returns home after normal AUTO expiry, and stops on a fault. Its bw override is restored afterward only when the board permits the stopped parameter write; inspect the report.

For the retained longer-duration collector (same protocol, bounded to 60 s, camera budget 360s):

```bash
uv run --locked --extra hardware python \
  evidence/swingup-resonance-20261021/tools/collect_long_tuning.py \
  --expected-reference 533 --bw 10 --execute --duration 60 \
  --output runs/my-bw10-long-01
```

Offline reproduction from the repository root:

```bash
mkdir -p runs/resonance-replay
for archive in evidence/swingup-resonance-20261021/raw/*.tar.gz; do
  tar -xzf "$archive" -C runs/resonance-replay
done
uv run --locked --extra id --extra plots python \
  evidence/swingup-resonance-20261021/tools/analyze_tuning_campaign.py \
  --repo . --input runs/resonance-replay/runs/encoder-tuning-resume-20261021 \
  --score-script evidence/swingup-resonance-20261021/tools/score_native_trial.py \
  --output runs/resonance-analysis-new
uv run --locked --extra id --extra plots python \
  evidence/swingup-resonance-20261021/tools/analyze_cycle.py \
  --input runs/resonance-replay/runs/encoder-tuning-resume-20261021/bw8-auto25-03 \
  --output runs/resonance-cycle-new
c++ -std=c++17 -O2 -I firmware/teensy_executor \
  evidence/swingup-resonance-20261021/capture-audit/forecast.cpp \
  -o /tmp/cartpole-forecast
/tmp/cartpole-forecast < evidence/swingup-resonance-20261021/capture-audit/forecast-inputs.txt
```

The capture-audit Python scratch scripts preserve the original analysis paths for provenance; the main campaign/cycle tools above accept input/output paths. The forecast uses frozen recorded states, not a new hardware trial. `verification.txt` records 54 passing focused tests (plus 19 subtests), exact forecast-output reproduction, duration guard checks, archive consolidation checks, and the stopped 40-setting profile comparison. These checks do not imply hardware acceptance.
