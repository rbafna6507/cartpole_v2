# Model-bound PPO training

MuJoCo computes the cart-pole physics. Gymnasium gives the learner a standard
environment interface. PPO, from Stable Baselines3, trains the neural policy.
The older `examples/train_policy.py` is CEM search over ten gains of a handwritten
controller. It remains a useful baseline and is not neural-network training.

The new `examples/train_ppo.py` runs on a laptop or Google Colab, with no device
connection. It uses `RigCartpoleEnv`: 1 ms physics and governor ticks, 100 Hz policy
decisions, explicit executor parameters, encoder quantization, the causal firmware
angle/rate observer, and configured telemetry/command delays. It preserves the
ideal acceleration-servo assumption; force saturation ends a rollout because
physical tracking beyond that point is unsupported. No motor, slip, backlash or
disabled-motor stopping model is claimed.

## Model qualification comes first

Use the [collection, fitting and export workflow](system-identification-workflow.md)
to produce a content-hashed model export. A rejected fit cannot be used as an
identified model, and this trainer does not bypass the export gate. Non-unit
input gain, input delay and Coulomb friction must be represented by the plant
before an identified export containing those terms can be used; dropping a
fitted term is not supported.

The current model export scopes are `passive-down` and `driven`. Neither certifies
global swing-up/balance or hardware transfer. Consequently this version requires
the conspicuous `--development-only` flag for those scopes and records
`task_qualified=false` and `hardware_accepted=false`. The flag permits exploratory
simulation only; it does not turn a rejected fit into a valid export. A future
global-qualification schema needs independently validated task coverage. Do not
start physical-policy training from the currently rejected recordings.

There is also a separate `cartpole-development-model-v1` fixture format for
software tests. Its required fields are `status: "DEVELOPMENT_ONLY"`, a complete
`simulation_config`, nonempty `rationale` and `limitations`, and `content_sha256`
(SHA-256 of canonical sorted compact JSON before adding the hash). It has no
accepted-fit claim and is never an identification export.

## Prepare four explicit inputs

Keep these together with the fitting evidence:

- `model.json`: the immutable identified export, including fit report and scope.
- `executor-parameters.json`: a complete recorded `ControllerParameters` object,
  or a `Rig.save_parameters()` profile with `schema_version: 1` and `parameters`.
  Missing settings are rejected. The model and executor rail must match.
- `observation-config.json`: every field of `RigObservationConfig`, including the
  raw/filtered angle selection, encoder resolution, noise, delays and dropout.
  These are declared assumptions until measured.
- `prior-parameters.json`: every field of `HostPolicyParameters`. This is an
  explicit comparison prior, not action labels or neural pretraining. Its
  effective length is recorded separately from the plant length.

For example, after saving a complete executor readback, this writes explicit
starting assumptions for review. It does not connect to or modify the rig:

An existing `scripts/system-id inspect` report contains the actual readback in
its `result.parameters` field. Extract it without replacing missing fields with defaults:

```python
import json
from pathlib import Path
inspection = json.loads(Path('runs/inspection-01/report.json').read_text())
Path('executor-parameters.json').write_text(json.dumps(inspection['result']['parameters'], indent=2))
```

Use the report corresponding to the model's recorded setup. This extraction
does not make the old snapshot current; retain its firmware/reference/time
metadata with the experiment evidence.

```python
import json
from dataclasses import asdict
from pathlib import Path
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.policies import HostPolicyParameters
from cartpole_sdk.sim.rig_gym_env import RigObservationConfig

profile = json.loads(Path('executor-parameters.json').read_text())
values = profile['parameters'] if profile.get('schema_version') == 1 else profile
parameters = ControllerParameters(**values)  # Trainer separately requires all fields.
observations = RigObservationConfig(
    angle_source='raw', encoder_counts=4096, angle_noise_std=0.,
    telemetry_delay_steps=0, command_delay_steps=0, dropout_probability=0.)
prior = HostPolicyParameters.from_controller(parameters)
Path('observation-config.json').write_text(json.dumps(asdict(observations), indent=2))
Path('prior-parameters.json').write_text(json.dumps(asdict(prior), indent=2))
```

Zero noise/delay in this example is an explicit development assumption. Observer
bandwidth comes from the executor snapshot; it is not replaced with perfect
angular velocity. Reset starts the observer at zero rate and obtains the first
healthy snapshot through causal pre-arm warmup under the 20 ms lease. The plant
continues to evolve during that delay. Later unavailable or stale policy input
ends the episode; ground truth is never substituted into actor features.

## Train, save and resume

Install only on the training machine. The `rl` extra includes MuJoCo, Gymnasium,
NumPy, Torch and Stable Baselines3. Base and hardware-only installations do not
gain neural dependencies. The separate `plots` extra is for recording review.

```sh
./scripts/train-ppo train \
  --model runs/model.json \
  --executor-parameters runs/executor-parameters.json \
  --observation-config runs/observation-config.json \
  --prior-parameters runs/prior-parameters.json \
  --development-only --training-seeds 11 12 13 --seed 20261017 \
  --seconds 10 --steps 2048 --n-steps 1024 --batch-size 64 --epochs 10 \
  --checkpoint-every 1024 --output runs/ppo-001
```

Start with this small execution check, then choose a larger training budget in a
new run. Steps must be a multiple of `n-steps`; batch size must divide it. The
implementation uses one CPU environment, a 64×64 tanh actor and value network,
and a fixed training seed pool spanning hanging/upright initial-state families.
No domain randomization is currently implemented. Fit standard errors are
conditional regression uncertainties, not a complete plant posterior.
PPO uses a 0.99 discount factor during optimization; the reported evaluation
score is the undiscounted finite-episode benchmark used for controller comparison.

Each run contains `experiment.json`, `manifest.json`, `checkpoint.zip`, numeric
`actor.json`, and periodic checkpoint directories. The manifest records model
content/file/fit hashes, scope, assumptions, full simulation/executor/observation
settings, algorithm settings, seeds, versions and source hashes. It records the
actual number of steps. Outputs are immutable; choose a new directory per run.
Keep the original model and input JSON files with the run.

Resume by repeating the same command with a new output and
`--resume runs/ppo-001`. `--steps` is the additional budget. Model, input settings,
seed pool, algorithm settings, source hashes and dependency versions must match.
Moving identical input files to another directory is allowed. Optimizer state
and timestep count continue; episodes restart from the fixed training pool, so
this is not a promise of bitwise equivalence to uninterrupted training. Only
load SB3 archives you created or trust: their format includes serialized Python
objects. Numeric `actor.json` does not contain executable serialization.

## Frozen evaluation and SDK inference

Evaluate after freezing the checkpoint. The evaluator rejects training-seed
overlap, never updates weights, and reports every hanging/upright episode:

```sh
./scripts/train-ppo evaluate runs/ppo-001 \
  --seeds 1001 1002 1003 1004 1005 1006 --output runs/ppo-001-heldout.json
```

Metrics include reward, final continuous balance time, success, peak cart travel
and speed, saturation, braking and faults. Success requires the full last second
inside the declared x/angle/rate bounds and no fault. A short smoke run cannot
establish success. Preserve final test seeds; changing the policy after inspecting
them makes them development data, requiring a new held-out set.
The training horizon is an actual terminal condition for this finite objective,
so SB3 does not bootstrap a continuing value past the final balance-time bonus.

The actor consumes the same shared encoding of six explicit SDK channels as the
simulator: x, commanded velocity, angle, filtered angular velocity, commanded
acceleration and brake direction. Angle becomes sine/cosine, yielding seven
state features plus masks and ages. PPO predicts a scalar in [-1,1], mapped once
to raw acceleration in m/s². The trusted executor governs that demand once.

```python
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.rig_observation import rig_channels

# Factory only: this does not open a device, arm, or approve hardware use.
policy = load_neural_policy('runs/ppo-001/actor.json',
                            channels=rig_channels(angle_source='raw'))
# Trusted runner calls policy.reset(session), then
# policy.act(rig.control_observation()) -> Acceleration or None.
```

Use `Rig.control_observation()` for the governor feedback channels; the ordinary
four-channel observation is insufficient. Raw/filtered source must match the
training manifest. Session, source/frame, freshness, skew, cadence and replay
checks fail closed. The portable actor uses only Python/stdlib plus the SDK and
checks its inference source hashes. It does not apply a second governor. This
does not add a portal submission path or authorize a hardware runner. Recorded
shadow testing, timing measurements and bounded physical acceptance remain
separate work.

## Colab

Open [`notebooks/train_ppo_colab.ipynb`](../notebooks/train_ppo_colab.ipynb). From
this checkout, prepare the source archive (include the new files):

```sh
python -m zipfile -c cartpole-source.zip pyproject.toml README.md uv.lock src examples scripts
```

Upload that archive and the four reviewed input JSON files when the notebook
prompts. The notebook installs CPU Torch and the optional RL extra, trains via
the same CLI, supports resume, evaluates on disjoint seeds, and downloads the
checkpoint/actor/report bundle. No Google Drive mounting, SSH or device control
is required. Colab execution itself has not been claimed tested by local smoke
results; the same training CLI and real learn/save/reload/resume path were tested
locally.
The source archive contains only the selected project files; do not add SSH
keys, environment files, credentials, or unrelated raw recordings. A private
repository does not need to be made public or cloned with a token inside Colab.

Official references: [SB3 PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html),
[SB3 checkpoint format](https://stable-baselines3.readthedocs.io/en/master/guide/save_format.html),
[Gymnasium environment API](https://gymnasium.farama.org/api/env/).
