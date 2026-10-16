# Native-run identification: rejected

All **11 full-model assessments reject** under the existing acceptance gates. No parameter is recommended or applied. This analyzes six earlier successful native AUTO recordings. It opened no serial connection and changed no service, calibration, controller or simulation setting.

The `jitter-20261016` cohort used reference 330, home epoch 9, a 16,509-step switch span, native control at 1 kHz and telemetry at 250 Hz. A1/A2 used observer bandwidth 10; B1 used 9; C1/C2/C3 used 8. The [plan](analysis-plan.json) froze A1 as training and A2 as separate validation, with the others as transfer checks. These results do not characterize later Python-control recordings or home epochs.

## Results

A1's rejected candidate is length **0.167324 m**, composite input gain **1.090577**, damping **0.557941/s**, and delay **5 ms**. Its 6,250 samples provide 71 windows. Training integral NRMSE is **0.175982** against the 0.15 limit. The input-zero diagnostic is **+0.220716 rad**, exceeding 0.02 rad; gravity-zero is −0.013455 rad. Delays of 0, 5 and 10 ms lie within the 5% training-loss band; 5 ms is not measured motor latency.

| Frozen A1 model, held-out run | Prediction RMSE (rad) | p95 (rad) | Integral NRMSE |
|---|---:|---:|---:|
| A2 | 1.119138 | 2.687823 | 0.183926 |
| B1 | 1.195738 | 2.723372 | 0.227841 |
| C1 | 1.077473 | 2.571034 | 0.205410 |
| C2 | 0.948226 | 2.415407 | 0.211649 |
| C3 | 1.072016 | 2.546065 | 0.240980 |
| Existing limits | 0.08 | 0.15 | 0.15 |

Independent C1→C2 fitting also rejects: length 0.156010 m, negative damping −0.320726/s, input-zero 0.341701 rad and held-out RMSE 1.048034 rad. Wider causal rate histories leave primary A2 RMSE at 0.859–1.185 rad. They do not change acceptance or isolate every source of initialization error.

Applying **only A1's** pretrial hanging offset, −0.12126378851042818 rad, identically to training and all held-out runs worsens training integral NRMSE to 0.401603. No held-out zero was fitted. This local hanging offset is not independently verified global upright calibration.

## Passive clue and next measurements

Each recording has about four seconds of stopped ringing. Separate fits conditional on a fixed cart, using the same A1 offset throughout, cluster at length **0.158251–0.166015 m** and damping 0.207–0.398/s. A1 gives 0.159918 m and 0.269749/s. Its fixed parameters predict A2's tail with RMSE 0.078994 rad, p95 0.174213 rad and integral NRMSE 0.050246. C2's RMSE of 0.238079 rad shows remaining mismatch.

These results **do not accept a model**: each tail has 11 windows, below the 20-window default; the motor is disabled; physical cart stationarity is unverified; input gain/delay lack excitation. Fixed step-derived position does not prove a physically fixed cart. See the [passive diagnostic](results/passive-tail-diagnostic.json).

Prioritize independently verified hanging, upright and intermediate-angle mapping, then separate 20-second fixed-cart decays at different amplitudes/directions with independent cart-motion observation. Small-angle periods for lengths of 0.124 m and 0.160 m are 0.706 s and 0.802 s, providing a direct discriminator.

The [waveform checker](check_waveform.py) and [proposal](waveform-proposal.json) specify a subsequent 20-second multisine pair with two-second quintic ramps. Nominal training bounds are 6.494 mm, 0.066014 m/s and 0.616596 m/s²; held-out bounds are 5.169 mm, 0.057845 m/s and 0.625541 m/s². They do not bound feedback corrections or actual motion. Retain current interlocks and the established stop path. Do not run the historical executor procedure unchanged: it hardcodes reference 3485 and disables switches. The [full assessment](assessment.txt) supplies the protocol and unchanged gates.

Commanded-input data can support effective gain/delay if validated. Physical acceleration, tracking/slip and actuator latency require independent motion and timing measurements. Cart/pole masses, force gain and physical hinge torque damping remain unidentified. All six camera-series files are empty; no camera signal was used.

## Provenance and reproduction

The preserved `fit.py` and `rig_logs.py` exactly match checkpoint `8d6c8e8`. The [summary](results/summary.json), individual reports and metadata retain source/canonical hashes, configurations, admission counts and residual diagnostics. [remote-source-manifest.json](remote-source-manifest.json) lists exact original Jetson paths and hashes. The 25.9 MB raw JSONL remain under `/home/rbafna/cartpole-v2-runs/jitter-20261016/`; they are not copied here. Source hashes matched the earlier compact evidence.

On a machine with those original files, copy this bundle's scripts to scratch and run the commands below. Analysis used Python 3.11.17 and NumPy 2.4.6. Preserve checked-in results: scripts overwrite adjacent output files.

```sh
mkdir -p /tmp/cartpole-id-reproduction
cp analysis-plan.json analyze_current.py passive_tails.py fit.py rig_logs.py /tmp/cartpole-id-reproduction/
OPENBLAS_NUM_THREADS=1 /home/rbafna/cartpole_v2/.venv/bin/python /tmp/cartpole-id-reproduction/analyze_current.py
OPENBLAS_NUM_THREADS=1 /home/rbafna/cartpole_v2/.venv/bin/python /tmp/cartpole-id-reproduction/passive_tails.py
```

Copy `check_waveform.py` to scratch and run it with Python 3 to reproduce the proposal without hardware access. Endpoint, derivative and continuous-bound assertions passed. Scripts compile; all 11 full reports reject; unchanged gates and frozen training parameters were verified. [verification.json](verification.json) records the original offline checks. [SHA256SUMS](SHA256SUMS) covers this durable bundle.
