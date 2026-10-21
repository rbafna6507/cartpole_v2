# Full-task robust swing pilot — 2026-10-20

Development-only offline warm transfer and engineering randomization. No newly trained deployment actor was exported and no hardware was accessed by this experiment. The original numeric actor is retained solely as warm-start provenance. The passive plant model was not refitted; recent hardware forecasting errors do not establish that these dynamics ranges cover the rig.

Implementation: `src/cartpole_sdk/learning/robust_swing.py`, CLI `scripts/robust-swing-learning`, tests `tests/test_robust_swing.py`. Ten new focused tests passed; the directly related robust/swing/error regression suite passed 35 tests. Independent read-only review found no blocking issue. Existing frozen training modules, profiles and prior actor bytes stayed unchanged.

## Recipe and provenance

Four runs: optimizer seeds 3/17 × nominal versus randomized, 20,480 decisions each, checkpoints 0/5120/10240/15360/20480. 25 second mixed hanging/upright episodes; actual completed episodes are recorded below. One CPU thread/worker, two workers. PPO LR 3e-6, std .05, gamma .999, GAE .98, 1024-step rollouts, batch 64, 10 epochs, 64-tanh-64-tanh actor; identical observed-zero projection in both arms. No ongoing teacher loss or controller fallback. The existing true-state balance/dwell reward is unchanged: cart and true-angle RMS are evaluation metrics, not a newly implemented RMS training objective.

Warm-start: anchored seed 17 checkpoint SHA 84444dbd0f0638021a12a899b41b2c32b41b91259a34aec4b0a7e7f5e12d7284; numeric actor file SHA 741d7950e0ebbd27faa9cd01824267308ea9b24ef27edb6d95a1c0bd29d082ae. Recipe/report/archive/demo/checkpoint/parity bindings and tensor equality were checked before copying only the three actor Linear weights/bias. Critic, optimizer and exploration are fresh. Current runtime source guards remain enabled; this is not a general bypass for incompatible archives. Copied raw actions agree with the old numeric actor on 96 current-profile/counterfactual inputs within 2.46752e-6 m/s² (tolerance 1e-5). This migration check precedes PPO and does not qualify new checkpoints for SDK deployment.

The original actor used observer bandwidth 6. The current bw10 profile was copied and rebuilt at bandwidth 8 for this experiment; its original files were not changed. Live hardware was subsequently restored to bandwidth 10. No policy here is qualified for either hardware configuration. Inputs are explicitly raw encoder-zero, feature order age_s/state/valid, 21 inputs, 100 Hz, scale 25; incompatible contracts are rejected.

Nominal arm uses no added bias/randomization. Randomized arm adds a private seeded uniform ±2 degree constant per-episode offset to actor sine/cosine after quantization, plus engineering effective-length ±5%, damping/friction ±20%, angle noise 0..0.003 rad, telemetry delay 0..5 ms, command delay 0..3 ms. Bias modifies actor inputs only; true state/reward, validity, ages, magnetic rate and leases are retained. A measured initial angle can be physical tilt or reference error; these scenarios do not identify the cause. This increment has no recurrent memory, drift model, nonlinear identification or physical cart sensor.

Training poses 22000..22127; development 68000 at initial/final; one-shot final heldout 69000. Both starts run 25 seconds in every scenario: nominal, ±1 degree, ±2 degree, combined-minus (length scale .95, damping/friction scale .8, noise .003 rad, delays 5/3 ms, bias −1 degree), and combined-plus (length scale 1.05, damping/friction scale 1.2, same noise/delay, bias +1 degree). The heldout split has no initialized-checkpoint evaluation; before/after claims use development only. Heldout results were inspected only after the final checkpoints were fixed. No candidate was selected. These pose seeds are now inspected evidence, not fresh seeds for future model selection.

A hold requires the full horizon without fault and the final 5 seconds continuously |theta|<.15 rad, |omega|<1 rad/s, |x|<.12 m. These are result criteria; this full-task simulator does not impose the old balance-only angular start/stop guard. Capture time means the first completed one-second continuous balanced interval. Simulated truth metrics are not measured hardware accuracy.

## Results

Each count below is across the two optimizer-seed policies on **one pose seed per start and split**, not two independent physical poses. Cells show H (hanging) and U (upright) holds, each out of 2. The initialized actor is identical across both arms; its initial development results are shown once.

| Scenario | Initial dev | Nominal final dev | Randomized final dev | Nominal final heldout | Randomized final heldout |
| --- | --- | --- | --- | --- | --- |
| nominal | H 2/2; U 2/2 | H 0/2; U 2/2 | H 2/2; U 2/2 | H 1/2; U 2/2 | H 1/2; U 2/2 |
| bias-minus1 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 |
| bias-plus1 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 |
| bias-minus2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 |
| bias-plus2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 |
| combined-minus | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 |
| combined-plus | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 | H 0/2; U 0/2 |

Nominal-scenario centering and capture metrics below average over the two optimizer seeds. Tail RMS covers the final 5 seconds; whole-episode true-angle RMS for hanging starts includes swing-up. Full seven-scenario per-episode metrics, capture times, dwell and traces remain in `comparison.json` and the archive.

| Split / arm | Start | Mean capture s (captured/2) | Tail cart RMS mm | Tail true-angle RMS deg | Worst absolute x mm |
| --- | --- | --- | --- | --- | --- |
| initial/nominal | hanging | 14.710 (2/2) | 5.346 | 0.0194 | 293.991 |
| initial/nominal | upright | 1.000 (2/2) | 3.209 | 0.0198 | 63.775 |
| final/nominal | hanging | none | 202.828 | 107.6947 | 294.009 |
| final/nominal | upright | 1.000 (2/2) | 1.509 | 0.0210 | 82.457 |
| final/randomized | hanging | 15.975 (2/2) | 10.096 | 0.0632 | 294.004 |
| final/randomized | upright | 1.000 (2/2) | 2.641 | 0.0202 | 80.294 |
| heldout/nominal | hanging | 13.800 (1/2) | 122.171 | 52.4449 | 294.011 |
| heldout/nominal | upright | 1.000 (2/2) | 6.925 | 0.0260 | 69.139 |
| heldout/randomized | hanging | 4.980 (1/2) | 95.221 | 59.3280 | 294.002 |
| heldout/randomized | upright | 1.000 (2/2) | 5.820 | 0.0226 | 62.549 |

Actual totals: **81,920 training decisions**, **420,000 proposed / 420,000 physically advanced evaluation decisions**, **168 evaluation episodes**. Completed training episodes per run: nominal-seed3=8, randomized-seed3=8, nominal-seed17=8, randomized-seed17=8.

This is about eight full-length training episodes per run, a retention/feasibility pilot rather than convergence evidence. No robustness guarantee follows, and failure to improve under this budget does not establish that domain randomization is generally ineffective. Bias/stress failures and pose sensitivity remain material. All failures and initialized checkpoints are retained.

## Exact commands

Use the existing repository RL environment. The archive retains `driver.py` with actual argv, the upfront protocol, per-run logs/return codes and checkpoint receipts. Example randomized arm (repeat seed 17; nominal arms omit `--randomized` and set bias 0 with distinct outputs):

```sh
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
scripts/robust-swing-learning \
  --profile training/profiles/rl-encoder-20261020 \
  --warm-run runs/local-swing-20261018/anchored-seed17 \
  --warm-parity runs/local-swing-20261018/stress-anchored-seed17/parity \
  --output runs/NEW-robust-seed3 --observer-bw 8 --seed 3 \
  --randomized --bias-degrees 2 --steps 20480 --every 5120 \
  --seconds 25 --evaluation-seconds 25 \
  --evaluation-seeds 68000 --heldout-seeds 69000 \
  --learning-rate .000003 --policy-std .05
```

The example intentionally reproduces already-inspected seeds. For a new experiment, predeclare fresh disjoint pose sets via `--training-seeds`, `--evaluation-seeds`, `--heldout-seeds`; do not reuse these final results for tuning. The CLI rejects overlapping sets and prior inspected ranges, non-raw contracts, changed input/source hashes and existing output folders. Preserve the archived module/runtime/dependency versions for replay. No CLI hardware action or new actor-export path exists.

## Archive

Archive SHA-256: `eba4d5f3f36c5434ae5060a8f483dd59211db47c0eb4b38326bb7f50c6797122`; 87,347,206 bytes, 278 payloads. Every compressed payload was read back and SHA-256 verified. 20 new checkpoints plus four preserved source checkpoints are included. `archive-manifest.json` binds every payload and archive part. No evidence file exceeds 90 MB.

Reassemble in filename order before extraction:

```sh
cat local-robust-swing-20261020.tar.gz.part* > /tmp/local-robust-swing-20261020.tar.gz
shasum -a256 /tmp/local-robust-swing-20261020.tar.gz
tar -xzf /tmp/local-robust-swing-20261020.tar.gz
```
