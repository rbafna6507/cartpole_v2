# Train an SDK policy with MuJoCo, Gymnasium and PPO

The encoder, tracked-vision and fused-angle training paths are implemented. Use
**encoder first**. The simulator is adequate for development experiments; it is
not a globally validated model of the rig, and completing training does not
establish that its policy can swing up, balance or transfer safely.

MuJoCo supplies physics; Gymnasium supplies the environment API; Stable
Baselines3 PPO learns the actor. A numeric `actor.json` runs through the Python
SDK without Torch. The Teensy still governs motion at 1 kHz. Policy decisions
are 100 Hz raw acceleration requests with 20 ms action leases.

## Current model and evidence

Use the **20261021 profiles** below for new training. They retain the supported
passive plant, refresh the recorded rail/executor settings, and add per-episode
encoder bias and angle-dependent distortion before quantization and the 1 kHz
observer. Both reported angle and rate therefore change coherently. Nominal
encoder distortion is zero; the failed fitted calibration is not applied.
The bounds (bias ±1°, sine coefficient ±4°, cosine coefficient ±5°) are engineering
coverage, not measured confidence intervals. Camera-only movement is recorded as
a view change. See [the refresh evidence and tests](../evidence/simulation-refresh-20261021/README.md).

Each profile contains `randomization.json` and a complete hash manifest. The Colab
builder now freezes that exact recipe. Existing immutable bundles retain their
original recipes; prepare a fresh bundle to use these changes. The two local
4096-step execution checks produced checkpoints but no sustained holds, so they
are not deployment candidates.


The default retains the frozen batch-6 smooth-friction model, checked against
later recordings. A new training-only refit using batch6 plus training8/9
improved training RMS by 10.5%, but validation8/9 RMS only by 3.77% and P95
slightly worsened. It failed the predeclared promotion rule. See
[refinement results](../evidence/passive-refinement-20261017/README.md).

Five additional camera-recorded cart pulses completed without faults or command
clipping. Frozen production MuJoCo replay gives 1.25° pooled continuous angle
RMS; repeated signed10 mm pulse optical errors are 0.14–0.32 px under the first
pair's pixel/count map. These strengthen local motion evidence; they do not
independently identify metric scale, motor force, backlash or full-speed behavior.
[Measured versus predicted plots and raw sources](../evidence/rl-readiness-20261017/README.md).

No additional passive batches are needed to start development training. Remaining
physical qualifications are global angle calibration, larger/faster driven
motion, force authority and closed-loop transfer. The simulator retains assumed
masses and an ideal acceleration servo. Force saturation terminates a rollout;
missed steps, slip and motor-disabled stopping are not modeled. Jerk remains
150 m/s³; the executor settings are explicit and unchanged.

## Choose an observation profile

| Profile under `training/profiles/` | Actor angle | Actor angular rate |
|---|---|---|
| `rl-encoder-20261021` | Raw magnetic angle | Firmware-style magnetic observer |
| `rl-vision-20261021` | Tracked camera angle | Maintained camera derivative estimator |
| `rl-fused-20261021` | SDK complementary fused angle | Aligned magnetic observer |

All retain emitted-step cart position, commanded velocity/acceleration and brake
direction. Camera-only here means **vision for pole angle/rate**, not vision for
cart position and not raw-pixel RL. Train a separate actor for each profile;
changing a loaded actor's modality is rejected.

The actor has seven state features: x, commanded v, sin(angle), cos(angle), rate,
commanded acceleration and brake direction, plus seven validity flags and seven
ages. Simulation and SDK share the feature encoder, source contract, causal
camera derivative and `AngleFusion`. Ground truth is used for reward/diagnostics
only. The simulator independently schedules camera capture/delivery and preserves
sensor age. Camera warmup evolves the plant under its zero-acceleration servo;
this is not a motor-disabled physical dynamics model.

Nominal camera assumptions are80 FPS,20 ms delivery latency,.003 rad angle noise and
.001 rad quantization. The camera age budget is150 ms; cart/magnetic freshness and
action leases remain20 ms. Training varies frame period12.5–25 ms, latency10–30 ms,
and camera noise. Explicit invalid tracking stops a vision actor. Fused output
retains the last accepted bounded correction only until its age limit, then
becomes invalid. There is no silent raw-encoder substitution. Random invalid
frames default to zero for learning; test them separately because they are
faults, not recoveries the actor can learn around. Missing frame delivery may
retain the previous genuine sample within its age budget.

Live vision currently needs a fresh camera calibration and direct upright/sign
alignment. The camera service was tracking at~79 FPS but had no valid angle zero
when inspected. Training these variants works without the camera; powered
vision/fused use is not commissioned by the simulator tests.


To regenerate a profile from the preserved evidence (no hardware access), use a
new output directory:

```sh
./scripts/prepare-rig-training --angle-source raw --output runs/regenerated-profile
```

Use `--angle-source vision` or `fused` for those variants. For local training with
these profiles, pass `--randomization PROFILE/randomization.json` to
`examples/train_ppo.py train`; `--randomize` intentionally means the older generic
preset and does not load the profile's additional encoder terms.

## Launch through the official headless Colab CLI

Run these on your laptop from this checkout. The wrapper targets
[`google-colab-cli`0.7.4](https://pypi.org/project/google-colab-cli/0.7.4/) using the
[official CLI](https://github.com/googlecolab/google-colab-cli). Local CLI Python
is3.12; the isolated remote training environment is locked to Python3.11.7 and
uv0.8.11. First authentication prints an OAuth URL: approve it yourself and paste
the code into the terminal. Training itself needs no notebook browser or Drive
mount. Cloud setup and training were exercised. The original three October17 runtimes
were gone by the next morning without a local checkpoint download; their final
training outcomes are unknown. See [recovery evidence](../evidence/colab-recovery-20261018/README.md).

Install the CLI once:

```sh
uv venv --python 3.12 runs/colab-cli-venv
uv pip install --python runs/colab-cli-venv/bin/python google-colab-cli==0.7.4
```

Prepare an immutable bundle, then launch a uniquely named CPU session:

```sh
./scripts/prepare-colab-training \
  --profile training/profiles/rl-encoder-20261021 \
  --steps 102400 --checkpoint-every 20480 --seed 20261021 \
  --output runs/colab-encoder-20261021-001

./scripts/colab-training start runs/colab-encoder-20261021-001 \
  --session cartpole-encoder-20261021-001
```

`prepare` validates model/configuration and profile hashes, then packages selected
source, lockfile and complete input provenance. It includes neither raw recordings
nor credentials. `start` allocates the VM, uploads and verifies the archives,
installs the locked environment, and launches a background training/evaluation
job. It returns after launching; it does not mean training finished. A Google VM
can still expire or disconnect. The current learner uses CPU; requesting a GPU
would not accelerate this implementation.

Check progress and download checkpoints/results:

```sh
./scripts/colab-training status runs/colab-encoder-20261021-001 \
  --session cartpole-encoder-20261021-001

./scripts/colab-training download runs/colab-encoder-20261021-001 \
  --session cartpole-encoder-20261021-001 --output runs/colab-encoder-20261021-results-001.zip
```

For new bundles, keep a local watcher running while training. It checks real
supervisor liveness and optimizer progress, and downloads a SHA256/CRC-verified
snapshot whenever a new complete checkpoint appears and on completion/failure:

```sh
./scripts/colab-training watch runs/colab-encoder-20261021-001 \
  --session cartpole-encoder-20261021-001 --output runs/colab-encoder-20261021-001-backups
```

The output directory must be new. Keep this laptop awake and connected; on macOS,
prefix the command with `caffeinate -i` to prevent idle sleep while it runs.
Closing the watcher or losing connectivity stops future local backups; it does
not stop remote training. Existing snapshots remain usable. Restart the watcher
with a new output directory after checking session status. The watcher stops on
errors or its eight-hour default polling deadline (`--max-seconds` changes this).
The deadline is checked between operations; an in-flight bounded operation can
overrun it (downloads have a600-second timeout). It never
allocates or relaunches a VM. Check its `watch-status.json` and `events.jsonl`.
Polling does not guarantee VM survival or extend Colab's resource limits.

Old immutable bundles support `status` and manual `download`, but lack structured
status for `watch`; prepare a new bundle rather than editing their pinned files.
`--checkpoint-every 20480` during preparation gives more frequent recovery points
than the original102400 default. Each saved ZIP includes all checkpoints so far,
so frequent downloads increase local disk use. For example, use the same learning
recipe with a shorter first budget:

```sh
./scripts/prepare-colab-training \
  --profile training/profiles/rl-encoder-20261021 \
  --steps 102400 --checkpoint-every 20480 \
  --output runs/colab-encoder-20261021-002
./scripts/colab-training start runs/colab-encoder-20261021-002 --session cartpole-encoder-20261021-002
./scripts/colab-training watch runs/colab-encoder-20261021-002 \
  --session cartpole-encoder-20261021-002 --output runs/colab-encoder-20261021-002-backups
```

Training/evaluation seeds remain disjoint. `--evaluation-seeds` during preparation
can bound an execution pilot's evaluation cost; a tiny pilot is not qualification.
For manual downloads, use a **new filename**, and download once more when status
says `completed`. The ZIP contains source, inputs, manifests, checkpoints, portable
actor, episode records, optimizer CSV and the final nominal evaluation report.
An active-job download may include an unfinished final run; only a checkpoint
with all validated manifest/actor/archive files is resumable. Preserve the ZIP
before stopping the VM:

```sh
./scripts/colab-training stop runs/colab-encoder-20261021-001 \
  --session cartpole-encoder-20261021-001
```

Never repeat `start` after a timeout: inspect status first. The wrapper reserves
the session name locally before allocation and rejects reused names, including
after failure; this prevents accidentally allocating a second VM. Use a new
name for a new experiment, after checking/stopping any old session. Its default
registry is `~/.config/colab-cli/sessions.json`; `--state-file` selects an explicit
alternative for all commands. Remote actions require a nonce-bound success
receipt because CLI0.7.4 can return exit0 for remote Python exceptions. Subsequent
commands also verify that the selected VM belongs to the supplied bundle.

For vision or fusion, repeat preparation with `rl-vision-20261021` or
`rl-fused-20261021`, a new output and a distinct session name. The same commands
then train that modality. You can run them sequentially to compare results.

## Training recipe and acceptance

Default budget is2,097,152 decisions,25 s episodes,128 seeds with alternating
hanging/upright starts,1024-step PPO rollouts,64-sample minibatches,10 epochs,
64×64 tanh networks and checkpoints every102,400 decisions. Gamma=.999,
GAE=.98 and learning rate=.0003. Optimizer reward scale=.01 improves conditioning;
raw evaluation scores and balance criteria are unchanged. Budgets must be a
multiple of1024; `--steps 102400` is a shorter pilot.

Training randomizes effective length±5%, angular viscous/dry-friction
coefficients±20%, encoder noise0–.003 rad, telemetry delay0–5 ms and command delay
0–3 ms, plus the camera ranges above for camera profiles. Torque conversion
preserves the changed inertia. These are engineering robustness ranges, not a
fitted uncertainty posterior. Executor rail, speed, acceleration, jerk and leases
are never randomized. Each episode records its actual settings.

Reward favors upright angle and time balanced, penalizing cart displacement,
angular speed and raw demand. Balance requires |angle|<.15 rad, |rate|<1 rad/s and
|x|<.12m. Final evaluation uses16 disjoint seeds, both hanging/upright starts, and
reports capture time, sustained balance, travel, saturation and faults separately.
Five-second hold success requires a complete fault-free episode with its final
five seconds inside those bounds. The old one-second metric remains for comparison.

The local pilots verified actual learning, checkpoint reload and numeric actor
parity, but **neither learned sustained balance**. The51,200-step unscaled pilot
improved mean raw development score−1.074→−.699; the20,480-step scaled pilot
reached−.198, still0/4 five-second holds. The budgets differ, so this is not a
controlled policy-performance comparison. The scaled critic fitted substantially
better. Training ran near300 steps/s locally; Colab runtime is not benchmarked.
The2M budget is a first experiment, not a convergence guarantee.

Before deployment, inspect `runs/ppo-001-heldout.json`. Require consistent
five-second success **from hanging and upright**, examine oscillation/action
smoothness and rail use, then evaluate a frozen policy on at least100 fresh seeds
per start plus separate parameter/timing/invalid-sensor stress cases. Do not keep
calling inspected seeds blind validation. A good nominal score alone is insufficient.

## Local training, evaluation and resume

The same inputs and implementation run locally:

```sh
PROFILE=training/profiles/rl-encoder-20261021
./scripts/train-ppo train \
  --model "$PROFILE/model.json" \
  --executor-parameters "$PROFILE/executor-parameters.json" \
  --observation-config "$PROFILE/observation-config.json" \
  --prior-parameters "$PROFILE/prior-parameters.json" \
  --development-only --randomize --seed 20261017 \
  --steps 102400 --seconds 25 --output runs/ppo-local-001

./scripts/train-ppo evaluate runs/ppo-local-001 \
  --seeds 20000 20001 20002 20003 --hold-seconds 5 \
  --output runs/ppo-local-001-evaluation.json
```

For resume, repeat the exact training configuration with a new output directory,
`--resume PATH_TO_COMPLETE_CHECKPOINT` and an additional step budget. Restore the
source/input files and exact Python/dependency versions from the downloaded ZIP
first. The loader rejects changed model, sensors, training settings, source or
versions. Episodes restart from the recorded seed pool; continuation is not
bitwise-equivalent to an uninterrupted run. Only load SB3 ZIPs you created or
trust; the portable numeric actor contains no serialized executable Python.

## SDK inference and later rig deployment

Copy the **actor and matching SDK source from its training bundle**, not just an
SB3 checkpoint, to a separate Jetson checkout. Existing tuned console settings
are not overwritten. Start with stopped shadow inference:

```sh
./scripts/run-neural-policy \
  --actor runs/ppo-001/actor.json \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --development-only --duration 2 --log-dir runs/neural-shadow-001
```

This reads the rig and logs predicted actions but never arms. It requires100 Hz
telemetry, healthy saved magnetic configuration, real switch-protected home and
an exact compatible complete executor readback. A source/hash/modality mismatch
fails closed. Camera modes also require `--sensing-config` with measured
calibration, direct upright/sign anchors and a current bounded clock mapping;
see [live sensor bindings](sensing.md#neural-policy-sensor-bindings).

Only after simulation and shadow qualification, explicitly add `--execute` for
bounded physical tests. The default raw-action ceiling is.25m/s²; excess demands
stop rather than being clipped into a different policy. Raise that explicit test
ceiling only as justified by accepted results. The usual SDK runner and Teensy
retain final motion authority and STOP on completion/error. No arbitrary neural
actor in this change is hardware-approved, and no pilot actor was powered on the
rig.

The older `examples/train_policy.py` remains CEM search over a handwritten
controller's gains. It is separate from PPO. Rebuild model profiles with
`scripts/prepare-training-model`; see the
[identification workflow](system-identification-workflow.md). The archived
`passive-20261017` profile remains unchanged.

For short local experiments, multiple-seed comparisons and balance-first gates,
see [the RL development cycle](rl-development-cycle.md).
